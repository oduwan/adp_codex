"""Focused synthetic receipt accounting; never a genuine M8/runtime claim."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from adp.execution_types import RuntimeObservation, RuntimeStatus, WorkerResult
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.guard_types import Limits, Outcome, data
from adp.personal_archive import proposal, _terminal
from adp.personal_workers import PersonalWorkers
from adp.personal_storage import read_private
from adp.schema import bundle, encode, key, result_schema
from adp.storage import atomic, locked
from adp.cli import parser
from adp.personal_cli import run as personal_run
from stopped_notrun_fixtures import StoppedNotRunFixture
from test_config import snapshot


class NotRunBridgeTests(unittest.TestCase):
    def row(self, outcome=Outcome.NOTRUN):
        return {"purpose": "develop", "observation": data(RuntimeObservation("a" * 64, "b" * 64,
            RuntimeStatus.COMPLETED, "synthetic-context", WorkerResult(outcome, False, (), "Synthetic outcome"),
            "runtime:" + "a" * 64 + ":" + "c" * 64, 1, "d" * 64, 1, 100, True))}

    def test_stopped_notrun_maps_only_delivery_to_unknown_and_keeps_raw_receipt(self):
        observed = RuntimeObservation("a" * 64, "b" * 64, RuntimeStatus.COMPLETED,
            "synthetic-context", WorkerResult(Outcome.NOTRUN, False, (), "Synthetic not-run evidence"),
            "runtime:" + "a" * 64 + ":" + "c" * 64, 1, "d" * 64, 1, 100, True)
        row = {"purpose": "develop", "observation": data(observed)}
        before = deepcopy(row)
        result = PersonalWorkers.result(row)
        self.assertEqual(result["outcome"], Outcome.UNKNOWN)
        result_schema(result)
        self.assertEqual(result["evidence"], [observed.receipt])
        self.assertEqual(row, before)
        self.assertEqual(row["observation"]["result"]["outcome"], Outcome.NOTRUN)
        self.assertFalse(row["observation"]["result"]["approved"])
        self.assertIn("NOTRUN", result["summary"])

    def test_existing_m1_outcomes_and_unsupported_timeout_are_not_coerced(self):
        for outcome in (Outcome.PASS, Outcome.FAIL, Outcome.ERROR, Outcome.SKIP, Outcome.UNKNOWN):
            with self.subTest(outcome=outcome):
                row = self.row(outcome)
                result = PersonalWorkers.result(row)
                self.assertEqual(result["outcome"], outcome)
                self.assertEqual(result["summary"], "Observed personal develop context")
                result_schema(result)
        result = PersonalWorkers.result(self.row(Outcome.TIMEOUT))
        self.assertEqual(result["outcome"], Outcome.TIMEOUT)
        with self.assertRaises(ADPError):
            result_schema(result)

    def test_old_m1_contract_still_rejects_raw_notrun_without_schema_expansion(self):
        raw = {"outcome": "NOTRUN", "summary": "Synthetic original result", "evidence": ["fixture:original"]}
        before = deepcopy(raw)
        with self.assertRaisesRegex(ADPError, "Invalid result outcome"):
            result_schema(raw)
        self.assertEqual(raw, before)

    def test_partial_or_ambiguous_notrun_never_becomes_an_m1_result(self):
        changes = (("approved", True), ("criteria", ["unproved"]), ("forensic", {}))
        for field, value in changes:
            with self.subTest(field=field), self.assertRaises(ADPError):
                row = self.row()
                row["observation"]["result"][field] = value
                PersonalWorkers.result(row)
        for field, value in (("stopped", False), ("result", None), ("status", "UNKNOWN")):
            with self.subTest(field=field), self.assertRaises(ADPError):
                row = self.row()
                row["observation"][field] = value
                PersonalWorkers.result(row)


class ArchivalProposalTests(StoppedNotRunFixture):
    def test_expired_original_proposal_is_repeatable_read_only_and_not_authority(self):
        row = self.expired()
        before = snapshot(self.base)
        first = proposal(self.c, row["request"]["id"])
        second = proposal(self.c, row["request"]["id"])
        self.assertEqual(first, second)
        self.assertEqual(snapshot(self.base), before)
        self.assertEqual(first["status"], "ARCHIVAL_PROPOSAL_ONLY")
        self.assertEqual(first["stage"], "TERMINAL_GUARD_REQUIRED")
        self.assertEqual(first["m2_disposition"]["decision"], "STOP_UNSAFE")
        self.assertEqual(first["worker_outcome"], "NOTRUN")
        self.assertEqual(first["delivery_outcome"], "UNKNOWN")
        self.assertEqual(first["product_acceptance"], "NOT_ACCEPTED")
        self.assertEqual(first["execution_authority"], "NOT_DELEGATED")
        self.assertEqual(first["apply"], "UNSUPPORTED_READ_ONLY_INTERFACE")
        self.assertTrue(first["timeliness"].startswith("UNKNOWN"))
        self.assertEqual(first["deadlines"]["request"], row["request"]["deadline"])
        self.assertEqual(len(self.requests), 2)
        canonical = self.c.memory.inspect()
        job = canonical["tasks"][key(self.c.task_id)]["assignments"][row["assignment"]["assignment_id"]]
        self.assertEqual(job["status"], "pending")
        self.assertEqual(canonical["inbox_count"], 0)
        self.assertEqual(digest(self.c.worker(row["request"]["id"])), digest(row))
        with patch.object(self.runtime, "capabilities", side_effect=AssertionError("No runtime probe")), \
             patch.object(self.runtime, "dispatch", side_effect=AssertionError("No worker")), \
             patch("adp.personal_cli.discovery_token", side_effect=AssertionError("No credentials/network")):
            views = []
            for entry in ("personal", "codex"):
                args = [entry, "archive-preview", "--repo", str(self.a), "--remote", "forge",
                    "--directory", str(self.directory), "--request", row["request"]["id"]]
                if entry == "codex":
                    args.append("--personal")
                report, status = personal_run(parser().parse_args(args), runtime=self.runtime, clock=lambda: self.now)
                self.assertEqual(status, 0)
                self.assertEqual(report["mode"], "READ_ONLY")
                self.assertIsNone(report["approval"])
                views.append(report["result"])
            self.assertEqual(views, [first, first])
        self.assertEqual(snapshot(self.base), before)
        self.assertNotIn(row["request"]["prompt"], json.dumps(first))

    def test_contemporary_notrun_accounts_unknown_but_m2_keeps_original_notrun(self):
        row = self.stopped()
        raw = self.runtime._path(row["request"]["id"]).read_bytes()
        stop = (self.runtime.directory / (row["request"]["id"] + ".stop.json")).read_bytes()
        observed = self.c.workers.finish(row)
        self.assertEqual(observed["phase"], "ACCOUNTED")
        canonical = self.c.memory.inspect()
        job = canonical["tasks"][key(self.c.task_id)]["assignments"][row["assignment"]["assignment_id"]]
        self.assertEqual(job["result"]["outcome"], "UNKNOWN")
        guard = canonical["state"]["progress_guard"]["requirements"][row["requirement"]]
        self.assertEqual(guard["last"]["observation"]["outcome"], "NOTRUN")
        self.assertEqual(guard["counters"], {"failures": 0, "corrections": 1, "explorations": 0, "reviews": 0, "stalls": 1})
        self.assertIsNone(guard["active"])
        self.assertIsNone(guard["approval"])
        self.assertEqual(guard["unresolved"], [self.personal.plan["criterion"]])
        self.assertEqual(self.runtime._path(row["request"]["id"]).read_bytes(), raw)
        self.assertEqual((self.runtime.directory / (row["request"]["id"] + ".stop.json")).read_bytes(), stop)
        self.assertEqual(len(self.requests), 2)

    def test_expired_window_or_reservation_and_changed_source_refuse_before_delivery(self):
        row = self.stopped()
        start = self.now
        item = self.c.guard._snapshot(self.c.task_id, row["requirement"])[2]
        for when in (item["active"]["deadline"] + 1, self.personal.plan["window"]["expires_at"] + 1, start - 1):
            self.now = when
            before = snapshot(self.base)
            with self.subTest(clock=when), self.assertRaises(ADPError):
                self.c.workers.finish(self.c.worker(row["request"]["id"]))
            self.assertEqual(snapshot(self.base), before)
        self.now = start
        path = self.personal.feature / "product"
        path.write_text("Synthetic post-stop changed source\n")
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            self.c.workers.finish(self.c.worker(row["request"]["id"]))
        self.assertEqual(snapshot(self.base), before)
        self.assertEqual(self.c.memory.inspect()["inbox_count"], 0)

    def test_lost_delivery_accept_and_guard_replies_reconcile_same_receipt_once(self):
        row = self.stopped()
        request = row["request"]["id"]
        deliver = self.c.memory.deliver
        def lost(envelope):
            deliver(envelope)
            raise OSError("Synthetic lost immutable-delivery reply")
        with patch.object(self.c.memory, "deliver", side_effect=lost) as send, self.assertRaises(OSError):
            self.c.workers.finish(row)
        send.assert_called_once()
        self.assertEqual(self.c.memory.inspect()["inbox_count"], 1)
        checkpoint = self.c.memory._checkpoint
        def accepted(*args, **kwargs):
            checkpoint(*args, **kwargs)
            raise OSError("Synthetic crash after accepted checkpoint, before inbox cleanup")
        with patch.object(self.c.memory, "_checkpoint", side_effect=accepted), self.assertRaises(OSError):
            self.c.workers.finish(self.c.worker(request))
        state = self.c.memory.inspect()
        self.assertEqual(state["tasks"][key(self.c.task_id)]["assignments"][row["assignment"]["assignment_id"]]["status"], "accepted")
        self.assertEqual(state["inbox_count"], 1)
        save = self.c.workers.save
        def interrupted(value):
            if value["phase"] == "ACCOUNTED":
                raise OSError("Synthetic interruption after exact guard observation")
            return save(value)
        with patch.object(self.c.workers, "save", side_effect=interrupted), self.assertRaises(OSError):
            self.c.workers.finish(self.c.worker(request))
        accounted = self.c.memory.inspect()
        self.assertEqual(accounted["inbox_count"], 0)
        with patch.object(self.runtime, "dispatch", side_effect=AssertionError("Never redispatch")), \
             patch.object(self.c.guard, "observe", side_effect=AssertionError("Never recount")), \
             patch.object(self.c.memory, "deliver", side_effect=AssertionError("Never redeliver")):
            self.c.workers.finish(self.c.worker(request))
            self.c.workers.finish(self.c.worker(request))
        self.assertEqual(self.c.memory.inspect(), accounted)
        self.assertEqual(len(self.requests), 2)

    def test_consumed_notrun_recovery_preserves_forensic_stop_and_counts(self):
        self.stricter_limits = Limits(corrections=1)
        row = self.stopped()
        with patch.object(self.c.workers, "save", side_effect=OSError("Synthetic post-accounting interruption")), self.assertRaises(OSError):
            self.c.workers.finish(row)
        state = self.c.memory.inspect()
        item = state["state"]["progress_guard"]["requirements"][row["requirement"]]
        self.assertEqual(item["mode"], "forensic")
        self.assertEqual(item["last"]["observation"]["outcome"], "NOTRUN")
        with patch.object(self.c.guard, "observe", side_effect=AssertionError("Never recount")), self.assertRaises(ADPError):
            self.c.workers.finish(self.c.worker(row["request"]["id"]))
        self.assertEqual(self.c.memory.inspect(), state)
        self.assertEqual(self.c.worker(row["request"]["id"])["phase"], "ACCOUNTED")

    def test_archival_guard_first_checkpoints_and_inbox_interruption_are_observational(self):
        row = self.expired()
        request = row["request"]["id"]
        initial = proposal(self.c, request)
        args = {"checkpoint": initial["checkpoint"], "expected": initial["reference"]}
        self.c.guard.abandon(self.c.task_id, row["requirement"], evidence_reference=initial["abandon_evidence_reference"])
        guard_state = self.c.memory.inspect()
        before = snapshot(self.base)
        self.assertEqual(proposal(self.c, request, **args)["stage"], "M1_RECONCILIATION_REQUIRED")
        self.assertEqual(snapshot(self.base), before)
        envelope = {"schema_version": 1, **row["assignment"], "result": self.c.workers.result(row)}
        self.c.memory.deliver(envelope)
        before = snapshot(self.base)
        self.assertEqual(proposal(self.c, request, **args)["stage"], "M1_RECONCILIATION_REQUIRED")
        self.assertEqual(snapshot(self.base), before)
        checkpoint = self.c.memory._checkpoint
        def interrupted(*a, **kw):
            checkpoint(*a, **kw)
            raise OSError("Synthetic accepted archival checkpoint before cleanup")
        with patch.object(self.c.memory, "_checkpoint", side_effect=interrupted), self.assertRaises(OSError):
            self.c.memory.accept(row["assignment"]["assignment_id"])
        before = snapshot(self.base)
        self.assertEqual(proposal(self.c, request, **args)["stage"], "EXACT_ACCEPTED_INBOX_CLEANUP_REQUIRED")
        self.assertEqual(snapshot(self.base), before)
        self.c.memory.cleanup_inbox()
        before = snapshot(self.base)
        final = proposal(self.c, request, **args)
        self.assertEqual(final["stage"], "TERMINAL_UNKNOWN_OBSERVED")
        self.assertEqual(final, proposal(self.c, request, **args))
        self.assertEqual(final["reference"], initial["reference"])
        self.assertEqual(snapshot(self.base), before)
        self.assertEqual(self.c.memory.inspect()["state"]["progress_guard"], guard_state["state"]["progress_guard"])
        self.assertEqual(len(self.requests), 2)

    def test_m1_first_history_cannot_masquerade_as_guard_first(self):
        row = self.expired()
        initial = proposal(self.c, row["request"]["id"])
        self.c.memory.deliver({"schema_version": 1, **row["assignment"], "result": self.c.workers.result(row)})
        self.c.memory.accept(row["assignment"]["assignment_id"])
        self.c.guard.abandon(self.c.task_id, row["requirement"], evidence_reference=initial["abandon_evidence_reference"])
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            proposal(self.c, row["request"]["id"], checkpoint=initial["checkpoint"], expected=initial["reference"])
        self.assertEqual(snapshot(self.base), before)

    def test_missing_malformed_or_changed_receipts_and_permits_refuse_without_writes(self):
        row = self.expired()
        request = row["request"]["id"]
        initial = proposal(self.c, request)
        worker = self.c.workers.directory / (request + ".json")
        runtime = self.runtime._path(request)
        stop = self.runtime.directory / (request + ".stop.json")
        changes = ((worker, lambda v: v["request"].update(generation=2)),
            (worker, lambda v: v["assignment"].update(assignment_id="1-99")),
            (worker, lambda v: v["permit"].update(token="f" * 64)),
            (worker, lambda v: v["guard_context"].update(iteration=2)),
            (worker, lambda v: v["observation"]["result"].update(outcome="PASS")),
            (worker, lambda v: v.update(result_source="f" * 64)),
            (runtime, lambda v: v.update(host="f" * 64)),
            (runtime, lambda v: v.update(status="UNKNOWN")),
            (runtime, lambda v: v.update(result=None)),
            (stop, lambda v: v.update(stopped=False)),
            (stop, lambda v: v.update(pid=1)),
            (stop, lambda v: v.update(cli_exit=1)),
            (stop, lambda v: v.update(status="UNKNOWN")))
        for path, change in changes:
            saved = path.read_bytes()
            v = json.loads(saved);change(v);path.write_bytes(encode(v, 131072))
            before = snapshot(self.base)
            with self.subTest(path=path.name, value=digest(v)), self.assertRaises(ADPError):
                proposal(self.c, request)
            self.assertEqual(snapshot(self.base), before)
            path.write_bytes(saved)
        saved = stop.read_bytes()
        for raw in (b'{', None):
            if raw is None:stop.unlink()
            else:stop.write_bytes(raw)
            before = snapshot(self.base)
            with self.subTest(raw=raw), self.assertRaises(ADPError):proposal(self.c, request)
            self.assertEqual(snapshot(self.base), before)
            stop.write_bytes(saved);stop.chmod(0o600)
        saved_runtime, saved_worker = runtime.read_bytes(), worker.read_bytes()
        v = json.loads(saved_runtime);v["result"]["summary"] = "Changed but structurally valid synthetic raw evidence"
        runtime.write_bytes(encode(v, 32768))
        w = json.loads(saved_worker);w["observation"] = data(self.runtime.observe(request));worker.write_bytes(encode(w, 131072))
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            proposal(self.c, request, checkpoint=initial["checkpoint"], expected=initial["reference"])
        self.assertEqual(snapshot(self.base), before)

    def test_source_owner_and_canonical_permit_changes_preserve_blocked_evidence(self):
        row = self.expired()
        request = row["request"]["id"]
        initial = proposal(self.c, request)
        for path in (self.personal.feature / "product", self.personal.feature / "outside", self.a / "product"):
            saved = path.read_bytes() if path.exists() else None
            path.write_text("Synthetic changed source\n")
            before = snapshot(self.base)
            with self.subTest(path=path.name), self.assertRaises(ADPError):proposal(self.c, request)
            self.assertEqual(snapshot(self.base), before)
            if saved is None:path.unlink()
            else:path.write_bytes(saved)
        with locked(self.c.memory.control):
            head, state, tasks = self.c.memory._start()
            state["progress_guard"]["requirements"][row["requirement"]]["active"]["id"] = "e" * 64
            self.c.memory._checkpoint(head, state, tasks)
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            proposal(self.c, request, checkpoint=initial["checkpoint"], expected=initial["reference"])
        self.assertEqual(snapshot(self.base), before)
        self.c.memory.handoff()
        before = snapshot(self.base)
        with self.assertRaises(ADPError):proposal(self.c, request)
        self.assertEqual(snapshot(self.base), before)
        self.c.memory.claim("synthetic-different-generation")
        before = snapshot(self.base)
        with self.assertRaises(ADPError):proposal(self.c, request)
        self.assertEqual(snapshot(self.base), before)

    def test_unexpired_non_notrun_and_conflicting_inbox_are_not_archival_authority(self):
        row = self.stopped()
        request = row["request"]["id"]
        before = snapshot(self.base)
        with self.assertRaises(ADPError):proposal(self.c, request)
        self.assertEqual(snapshot(self.base), before)
        self.now = self.personal.plan["window"]["expires_at"] + 1
        initial = proposal(self.c, request)
        envelope = {"schema_version": 1, **row["assignment"], "result": self.c.workers.result(row)}
        self.c.memory.deliver(envelope)
        path = self.c.memory.path / "inbox" / (key(row["assignment"]["assignment_id"]) + ".json")
        v = read_private(path);v["result"]["summary"] = "Conflicting immutable delivery";path.write_bytes(encode(v))
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            proposal(self.c, request, checkpoint=initial["checkpoint"], expected=initial["reference"])
        self.assertEqual(snapshot(self.base), before)
        for flag in ("--authorize-execution", "--authorize-memory-write"):
            with self.subTest(flag=flag), patch("sys.stderr"), self.assertRaises(SystemExit):
                parser().parse_args(["personal", "archive-preview", "--repo", str(self.a), "--remote", "forge",
                    "--directory", str(self.directory), "--request", request, flag])
