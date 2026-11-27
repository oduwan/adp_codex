"""Bounded diagnostic retention is observational, never execution authority."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.errors import ADPError
from adp import runtime_limits as limits
from adp.personal_cli import _retain_measurements, run
from test_runtime_limits import Clock, service


class PersonalCostTests(unittest.TestCase):
    def test_failed_scope_entry_keeps_measurement_and_resets_context(self):
        client = service()
        with self.assertRaises(ADPError), client.bounded(seconds=0):
            self.fail("Expired derived allowance entered")
        self.assertEqual(len(client.measurements), 1)
        self.assertEqual(client.measurements[-1]["outcome"], "ERROR")
        self.assertIsNone(limits.current_budget())
        self.assertEqual(client.transport.calls, [])

    def test_time_count_request_and_consent_are_distinct_and_never_renewed(self):
        for kind, expected in (("count", "REQUEST_COUNT_EXHAUSTED"), ("time", "OPERATION_TIME_EXHAUSTED"),
                ("both", "OPERATION_AND_REQUEST_COUNT_EXHAUSTED"), ("request", "REQUEST_DEADLINE_EXHAUSTED"),
                ("consent", "CONSENT_EXPIRED")):
            with self.subTest(kind=kind):
                clock, client = Clock(), service()
                with patch("time.monotonic", clock), self.assertRaises(ADPError), client.bounded() as budget:
                    end = budget.end
                    if kind in ("count", "both"):
                        budget.calls = budget.maximum_calls + 1
                    if kind in ("time", "both"):
                        clock.advance(150)
                    if kind == "request":
                        deadline = budget.request_deadline()
                        clock.advance(10)
                        budget.check_request(deadline)
                    elif kind == "consent":
                        limits.bind_consent({"expires_at": 1000, "runtime_limits": limits.DEFAULTS.values()}, 1000)
                    else:
                        budget.check()
                    self.assertEqual(budget.end, end)
                row = client.measurements[-1]
                self.assertEqual(row["final_refusal"], expected)
                self.assertEqual(row["observed_refusals"], (expected,))
                self.assertEqual(client.transport.calls, [])

    def test_caught_inner_refusal_does_not_become_cause_of_returned_unknown(self):
        client = service()
        with client.bounded() as budget:
            try:
                with client.bounded():
                    budget.check_request(0)
            except ADPError:
                pass  # Accepted reader can return UNKNOWN rather than propagate.
        row = client.measurements[-1]
        self.assertEqual(row["outcome"], "RETURNED")
        self.assertIsNone(row["final_refusal"])
        self.assertEqual(row["observed_refusals"], ("REQUEST_DEADLINE_EXHAUSTED",))

    def test_recording_failure_does_not_mask_original_error_and_truncation_is_explicit(self):
        client, error = service(), KeyboardInterrupt()
        with limits.capture_measurements() as capture:
            with patch.object(limits.Budget, "summary", side_effect=RuntimeError("private recording error")):
                with self.assertRaises(KeyboardInterrupt) as caught, client.bounded():
                    raise error
                self.assertIs(caught.exception, error)
            self.assertEqual(capture["errors"], 1)
            for _ in range(65):
                with client.bounded():
                    pass
            self.assertEqual((len(capture["rows"]), capture["dropped"]), (64, 1))
            with client.bounded() as budget:
                for _ in range(17):
                    try:
                        budget.check_request(0)
                    except ADPError:
                        pass
            self.assertEqual(capture["rows"][-1]["refusals_dropped"], 1)

    def test_actual_requests_and_invocation_collector_do_not_leak_across_clients_or_restarts(self):
        client = service()  # Constructed before invocation, like injected ports.
        for count in (2, 1):
            with limits.capture_measurements() as capture:
                rows = capture["rows"]
                with client.bounded(name="publication.publish"):
                    for _ in range(count):
                        client.request("GET", "/fixture")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["request_attempts"], count)
                self.assertEqual(rows[0]["transport_calls"], count)
                self.assertEqual(rows[0]["boundaries"]["response.validated"], count)
                self.assertEqual(rows[0]["requests_remaining"], 128 - count)
        self.assertEqual(len(client.measurements), 0)
        client.request("GET", "/fixture")
        self.assertEqual(len(client.measurements), 1)

    def test_private_latest_projection_is_bounded_sanitized_and_not_read_as_authority(self):
        with TemporaryDirectory() as root:
            state = Path(root); state.chmod(0o700)
            personal = SimpleNamespace(state=state)
            client = service()
            with client.bounded(name="publication.publish") as budget:
                budget.work["private ghp_do_not_retain"] = {"calls": 1, "seconds": 0.1}
                budget.settings = limits.RuntimeSettings(diagnostics=(limits.Diagnostic("CONFIGURATION_FAILURE",
                    rejected="ghp_do_not_retain", error="private path and credential"),))
                budget.latencies = [0.001] * 10000
            receipt = _retain_measurements(personal, {"rows": client.measurements, "dropped": 0, "errors": 0}, 1)
            self.assertEqual(receipt["status"], "RETAINED")
            path = state / "runtime-diagnostics.json"
            raw = path.read_bytes()
            self.assertLessEqual(len(raw), 131072)
            self.assertNotIn(b"ghp_do_not_retain", raw)
            self.assertNotIn(b"private path", raw)
            self.assertTrue(json.loads(raw)["truncated"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            # A corrupt old diagnostic is replaced, never parsed for a gate.
            path.write_text("not authority")
            self.assertEqual(_retain_measurements(personal, {"rows": [], "dropped": 0, "errors": 0}, 2)["status"], "RETAINED")
            with patch("adp.storage.atomic", side_effect=OSError("private payload")):
                self.assertEqual(_retain_measurements(personal, {"rows": [], "dropped": 0, "errors": 0}, 2)["status"], "UNAVAILABLE")

    def test_cli_failure_retains_costs_without_changing_outcome_or_masking_exception(self):
        with TemporaryDirectory() as root:
            state = Path(root); state.chmod(0o700)
            personal, client = SimpleNamespace(state=state), service()
            def operation(*a, **k):
                try:
                    with client.bounded(name="publication.publish"):
                        client.request("GET", "/fixture")
                        raise ADPError("private refusal")
                except ADPError:
                    return {"status": "BLOCKED", "blockers": [{"subreason": "UNKNOWN"}]}, 4
            args = SimpleNamespace(enroll_command="publish")
            with patch("adp.personal_cli.retained", return_value=personal), \
                    patch("adp.personal_history_track.cli_port", return_value=None), \
                    patch("adp.personal_cli._run", side_effect=operation):
                report, code = run(args)
            self.assertEqual((report["status"], code), ("BLOCKED", 4))
            self.assertEqual(report["runtime_diagnostics"]["status"], "RETAINED")
            row = json.loads((state / "runtime-diagnostics.json").read_text())["operations"][0]
            self.assertEqual((row["outcome"], row["request_attempts"]), ("ERROR", 1))
            error = RuntimeError("unrelated product exception")
            with patch("adp.personal_cli.retained", return_value=personal), \
                    patch("adp.personal_history_track.cli_port", return_value=None), \
                    patch("adp.personal_cli._run", side_effect=error), \
                    patch("adp.storage.atomic", side_effect=OSError("retention failure")):
                with self.assertRaises(RuntimeError) as caught:
                    run(args)
                self.assertIs(caught.exception, error)
