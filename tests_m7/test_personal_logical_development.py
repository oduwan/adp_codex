"""Actual personal coordinator/M1/M2/Git, synthetic Codex receipts; no pilot."""
from dataclasses import replace
import json
import subprocess
import sys
import secrets
from unittest.mock import patch

from adp.errors import ADPError
from adp.codex_runtime import CodexExecRuntime
from adp.discovery_schema import digest
from adp.execution_containment import admin_seal, source_seal
from adp.execution_types import Role, WorkerRequest, WorkerResult
from adp.git import value
from adp.guard import ProgressGuard
from adp.guard_types import Action, ActionKind, DecisionKind, Limits, Observation, Outcome, data
from adp.personal_storage import create_private, PersonalBlocked
from adp.personal_workers import prompt
from adp.schema import encode, key
from adp.storage import atomic
import test_guard as guard_fixtures
from personal_fixtures import PersonalFixture
import test_personal_execution as existing
from test_config import run


class LogicalDevelopmentTests(PersonalFixture):
    enroll = existing.PersonalExecutionTests.enroll

    def dispatch(self, request):
        observed = existing.PersonalExecutionTests.dispatch(self, request)
        purpose = json.loads(request.prompt.split("\n", 1)[1])["purpose"]
        if purpose == "develop":
            command = [sys.executable, "-B", "-c", "assert open('product').read() == 'original ticket implemented\\n'"]
            local = subprocess.run(command, cwd=request.workspace, capture_output=True, timeout=10, check=False)
            self.assertEqual(local.returncode, 0, local.stderr)
            summary = json.dumps({"change": "Original fixture implementation", "checks": [{
                "command": "python -B -c '<original product assertion>'", "outcome": "PASS", "result": "exit 0"}],
                "limitations": "Real local Python assertion; synthetic Codex receipt, no CI"})
            observed = replace(observed, result=replace(observed.result, summary=summary))
            developers = sum(r.role == "DEVELOPER" for r in self.requests)
            if developers == 1:
                observed = replace(observed, result=replace(observed.result, outcome=Outcome.NOTRUN,
                    summary="Recorded first-attempt noncompletion; candidate not accepted"))
        elif purpose == "code" and getattr(self, "reject_code", False):
            observed = replace(observed, result=replace(observed.result, outcome=Outcome.FAIL, approved=False,
                criteria=(), summary="Concrete independent exact-SHA fixture finding"))
        self.observed[request.id] = observed
        return observed

    def setup_attempt(self):
        run(self.a, "checkout", "-b", "work/issue-1")
        self.enroll()
        specification = self.c.specification
        # Stricter than the accepted limits: never enlarge any budget.
        patch.object(self.c, "specification", side_effect=lambda purpose:
            replace(specification(purpose), limits=Limits(corrections=1, stalls=2))
            if purpose in ("develop", "code", "product") else specification(purpose)).start()
        self.traces = []
        for name in ("observe", "observe_stage"):
            actual = getattr(self.c.guard, name)
            def retained(*args, actual=actual, name=name, **kwargs):
                decision = actual(*args, **kwargs)
                _, _, item = self.c.guard._snapshot(args[0], args[1])
                self.traces.append((name, item["last"]["action"]["kind"], item["last"]["action"]["exit_criteria"],
                    dict(item["counters"]), item["last"]["observation"]["outcome"]))
                return decision
            patch.object(self.c.guard, name, side_effect=retained).start()

    def test_last_permitted_developer_reaches_actual_independent_exact_sha_review(self):
        self.setup_attempt()
        window = dict(self.personal.plan["window"])
        _, reviewed = self.c.invocation()
        result = self.c.run(reviewed=reviewed, authorized=True)
        self.assertEqual(result["status"], "LOCAL_DRAFT_CODE_REVIEWED")
        self.assertEqual(result["product_acceptance"], "NOT_ACCEPTED")
        purposes = [json.loads(r.prompt.split("\n", 1)[1])["purpose"] for r in self.requests]
        self.assertEqual(purposes, ["original", "develop", "develop", "candidate", "code"])
        self.assertEqual(self.requests[-1].revision, value(self.personal.feature, "rev-parse", "HEAD"))
        self.assertEqual(len({o.context_id for o in self.observed.values()}), 5)
        logical = [r for r in self.traces if "personal-development/2:" in r[2]]
        self.assertEqual([(r[0], r[1], r[3]["corrections"], r[3]["stalls"]) for r in logical], [
            ("observe", "CHECK", 0, 1), ("observe_stage", "CORRECTION", 0, 1),
            ("observe_stage", "CORRECTION", 0, 1), ("observe", "CORRECTION", 0, 0)])
        self.assertEqual(self.personal.plan["window"], window)

    def test_unsuccessful_last_evaluation_accounts_once_and_blocks_further_development(self):
        self.reject_code = True
        self.setup_attempt()
        _, reviewed = self.c.invocation()
        with self.assertRaises(ADPError) as failed:self.c.run(reviewed=reviewed, authorized=True)
        self.assertEqual(getattr(failed.exception, "subreason", None), "FORENSIC_REQUIRED")
        item = self.c.guard._snapshot(self.c.task_id, self.c.requirement("develop"))[2]
        self.assertEqual(self.c.guard.inspect(self.c.task_id, self.c.requirement("develop")).kind, DecisionKind.FORENSIC_REQUIRED)
        self.assertEqual((item["counters"]["corrections"], item["counters"]["stalls"]), (1, 2))
        self.assertEqual(item["last"]["action"]["kind"], "CORRECTION")
        self.assertEqual(item["last"]["observation"]["outcome"], Outcome.FAIL)
        self.assertEqual(self.c.record()["developer"], next(r.id for r in reversed(self.requests) if r.role == "DEVELOPER"))
        self.assertEqual(self.c.record()["feedback"][-1]["outcome"], Outcome.FAIL)
        before = self.c.memory.inspect()
        self.runtime.dispatch.reset_mock()
        with self.assertRaises(ADPError):self.c._run()
        self.runtime.dispatch.assert_not_called()
        self.assertEqual(self.c.memory.inspect(), before)

    def test_legacy_stopped_receipt_remains_authentic_but_live_continuation_refuses(self):
        self.enroll()
        self.c.initialize_run()
        legacy = self.c.record(); legacy["schema_version"] = 1
        self.c.save(legacy)  # Construct owned synthetic historical data, never a pilot migration.
        context = self.c.context("develop")
        request = WorkerRequest(secrets.token_hex(32), self.c.task_id, legacy["generation"], Role.DEVELOPER,
            value(self.a, "rev-parse", "HEAD"), str(self.a), prompt("develop", context), 300, self.now + 300)
        assignment = self.c.memory.assign(self.c.task_id, "worker:" + request.id)
        authority = guard_fixtures.SyntheticAuthority()
        historical_guard = ProgressGuard(self.c.memory, authority=authority, clock=lambda: self.now)
        spec = self.c.specification("develop")
        requirement = historical_guard.register(self.c.task_id, spec,
            authority.attest(historical_guard.admission_subject(self.c.task_id, spec), "admission"))
        permit = historical_guard.begin(self.c.task_id, requirement,
            Action("worker:" + request.id, ActionKind.CORRECTION, "worker:" + request.id, "Original bounded Developer"))
        active = historical_guard._snapshot(self.c.task_id, requirement)[2]["active"]
        create_private(self.runtime.directory)
        result = WorkerResult(Outcome.NOTRUN, False, (), "Synthetic historical NOTRUN; never genuine Codex evidence")
        self.runtime._save(request.id, {"host": self.runtime.host, "request_digest": digest(request), "status": "COMPLETED",
            "pid": 50001, "start_time": "synthetic-only", "context": "synthetic-legacy:" + request.id,
            "result": data(result), "elapsed": 1, "samples": 1, "payload_bytes": 100, "stopped": True})
        stop = self.runtime.directory / (request.id + ".stop.json")
        atomic(stop, encode({"request_digest": digest(request), "pid": 50001, "status": "EXITED", "stopped": True, "cli_exit": 0}))
        with patch.object(self.runtime, "observe", side_effect=lambda identifier: CodexExecRuntime.observe(self.runtime, identifier)):
            actual = self.runtime.observe(request.id)
            row = {"schema_version": 1, "purpose": "develop", "request": data(request), "context": context,
                "assignment": assignment, "requirement": requirement, "permit": data(permit), "phase": "ACCOUNTED",
                "observation": data(actual), "source": source_seal(self.a), "admin": admin_seal(self.a),
                "outside": source_seal(self.a, tuple(self.personal.plan["paths"])), "result_source": source_seal(self.a),
                "result_admin": admin_seal(self.a), "expires_at": self.personal.plan["window"]["expires_at"],
                "host": self.runtime.host, "guard_context": active["context"]}
            self.c.memory.deliver({"schema_version": 1, **assignment, "result": self.c.workers.result(row)})
            self.c.memory.accept(assignment["assignment_id"])
            historical_guard.observe(self.c.task_id, requirement, permit,
                Observation(Outcome.NOTRUN, (actual.receipt,), tuple(spec.acceptance), elapsed_seconds=1, samples=1, payload_bytes=100))
            self.c.workers.save(row)
            before = self.c.memory.inspect()
            stop_bytes = stop.read_bytes()
            self.assertEqual(self.c.workers.records(), [row])
            self.assertEqual(self.c.workers.actual(row, accounted=True), actual)
            self.assertEqual(self.c.workers.result(row)["outcome"], Outcome.UNKNOWN)
            self.runtime.dispatch.reset_mock()
            with self.assertRaises(PersonalBlocked) as refused:self.c.run(reviewed="old-consent", authorized=True)
            self.assertEqual(refused.exception.subreason, "LEGACY_PROTOCOL")
            self.runtime.dispatch.assert_not_called()
            self.assertEqual(self.c.memory.inspect(), before)
            self.assertEqual(stop.read_bytes(), stop_bytes)

    def test_lost_m1_and_stage_replies_reconcile_original_developer_without_double_charge(self):
        run(self.a, "checkout", "-b", "work/issue-1")
        self.enroll()
        self.runtime.dispatch.side_effect = existing.PersonalExecutionTests.dispatch.__get__(self)
        self.c.initialize_run()
        review = self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.record(); row.update(original_review=review["request"]["id"], phase="FEATURE")
        self.c.save(row); self.c.prepare_feature()
        context = self.c.context("develop")
        accept = self.c.memory.accept
        def lost_accept(identity):
            accept(identity)
            raise OSError("Synthetic lost M1 accept reply")
        with patch.object(self.c.memory, "accept", side_effect=lost_accept), self.assertRaises(OSError):
            self.c.workers.execute("develop", context, self.personal.feature)
        worker = next(r for r in self.c.workers.records() if r["purpose"] == "develop")
        assignment = worker["assignment"]["assignment_id"]
        self.assertEqual(worker["phase"], "STOPPED")
        self.assertEqual(self.c.memory.inspect()["tasks"][key(self.c.task_id)]["assignments"][assignment]["status"], "accepted")
        save = self.c.workers.save
        def lost_stage(row):
            if row["purpose"] == "develop" and row["phase"] == "ACCOUNTED":
                raise OSError("Synthetic lost stage-accounting reply")
            return save(row)
        with patch.object(self.c.workers, "save", side_effect=lost_stage), self.assertRaises(OSError):
            self.c.workers.execute("develop", context, self.personal.feature)
        before = self.c.guard._snapshot(self.c.task_id, worker["requirement"])[2]
        self.assertIsNone(before["active"])
        self.assertEqual((before["counters"]["stalls"], before["counters"]["corrections"]), (0, 0))
        self.runtime.dispatch.reset_mock()
        with patch.object(self.c.guard, "observe_stage", side_effect=AssertionError("Never account the stage twice")):
            recovered = self.c.workers.execute("develop", context, self.personal.feature)
        self.runtime.dispatch.assert_not_called()
        self.assertEqual(recovered["request"]["id"], worker["request"]["id"])
        self.assertEqual(self.c.guard._snapshot(self.c.task_id, worker["requirement"])[2], before)
        self.assertEqual(self.c.record()["developer"], worker["request"]["id"])
        self.assertEqual(self.c.record()["phase"], "STAGE")
        self.assertEqual(len(self.requests), 2)
