"""Focused offline personal composition; patched runtime is NOT genuine proof."""
from dataclasses import replace
from pathlib import Path
import json
import shutil
from unittest.mock import patch

from adp.codex_runtime import CodexExecRuntime
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.execution_types import Capabilities, RuntimeObservation, RuntimeStatus, WorkerResult
from adp.git import value
from adp.execution_containment import admin_seal
from adp.execution_ports import index_digest, tree_index_digest
from adp.guard_types import Outcome, DecisionKind
from adp.personal_enrollment import apply_personal
from adp.personal_runner import PersonalCoordinator
from adp.personal_storage import approval
from adp.schema import key
from adp.storage import atomic
from adp.schema import encode
from personal_fixtures import NativePersonalReads, PersonalFixture
from test_config import run, snapshot


class PersonalExecutionTests(PersonalFixture):
    def test_commit_recovery_selects_current_attempt_not_sorted_action_order(self):
        run(self.a, "checkout", "-b", "work/issue-1")
        self.enroll()
        self.c.initialize_run()
        base = value(self.a, "rev-parse", "HEAD")
        message = self.personal.plan["commit_message"]
        (self.a / "product").write_text("first admitted fixture change\n")
        run(self.a, "add", "product")
        run(self.a, "commit", "-m", message)
        first = value(self.a, "rev-parse", "HEAD")
        self.c.memory.set_revision(self.c.task_id, first)
        row = self.c.record()
        row.update(revision=first, phase="COMMIT", developer="0" * 64)
        old = {"operation": "COMMIT", "revision": base, "source_ref": "refs/heads/work/issue-1",
            "target": "refs/heads/work/issue-1", "expected_target": None,
            "payload": {"subject": message, "body": "", "index_digest": tree_index_digest(self.a, first)},
            "status": "OBSERVED", "observation": {"status": "PRESENT", "reference": "commit:" + first, "revision": first, "body_digest": None}}
        (self.a / "product").write_text("second admitted fixture change\n")
        run(self.a, "add", "product")
        current = {**old, "revision": first, "status": "PREPARED", "observation": None,
            "payload": {"subject": message, "body": "", "index_digest": index_digest(self.a)}}
        row["actions"] = {"commit:" + "f" * 64: old, "commit:" + "0" * 64: current}
        self.c.save(row)
        run(self.a, "commit", "-m", message)
        second = value(self.a, "rev-parse", "HEAD")
        self.assertEqual(self.c.fresh().checkout["head"], second)
        self.assertEqual(self.c.record()["revision"], first)
        self.assertEqual(self.c.memory.inspect()["tasks"][key(self.c.task_id)]["source_revision"], first)
        self.assertEqual(self.requests, [])

    def test_same_valued_git_redirection_after_construction_is_refused(self):
        original_root = self.a
        self.a = self.base / "enrollment-checkout"
        run(original_root, "worktree", "add", "-b", "selected", str(self.a))
        self.enroll()
        before = admin_seal(self.a)
        common = original_root / ".git"
        copied = self.base / "same-valued-administration"
        shutil.copytree(common, copied)
        directory = Path(value(self.a, "rev-parse", "--absolute-git-dir"))
        (self.a / ".git").write_text("gitdir: " + str(copied / directory.relative_to(common)) + "\n")
        self.assertEqual(admin_seal(self.a), before)
        # The old value-only seal is unchanged; physical identity must refuse.
        with self.assertRaises(ADPError):
            self.c.live()
        self.assertEqual(self.requests, [])

    def test_coordinator_allocation_recovers_the_original_guard_permit(self):
        self.enroll()
        self.c.initialize_run()
        original_save = self.c.save
        def interrupted(row):
            if row["coordination"] is not None and row["coordination"]["permit"] is not None:
                raise OSError("Synthetic interruption after canonical guard allocation")
            return original_save(row)
        with patch.object(self.c, "save", side_effect=interrupted), self.assertRaises(OSError):
            self.c.reserve("focused-recovery")
        requirement = self.c.requirement("develop")
        before = self.c.guard._snapshot(self.c.task_id, requirement)[2]
        token = before["active"]["id"]
        self.assertIsNone(self.c.record()["coordination"]["permit"])
        with patch.object(self.c.guard, "begin", side_effect=AssertionError("Never allocate a second permit")):
            recovered = self.c.reserve("focused-recovery")
        self.assertEqual(recovered.token, token)
        self.assertEqual(self.c.guard._snapshot(self.c.task_id, requirement)[2], before)
        self.assertEqual(self.requests, [])

    def test_check_transition_recovers_accounting_without_another_observation(self):
        self.enroll()
        self.c.initialize_run()
        permit = self.c.reserve("focused-check-transition")
        row = self.c.record()
        gate = {"status": "UNKNOWN", "qualified": False}
        row.update(phase="CHECKS_TRANSITION", gates=[gate])
        self.c.save(row)
        original_save = self.c.save
        def interrupted(row):
            if row["coordination"] is None:
                raise OSError("Synthetic interruption after actual guard accounting")
            return original_save(row)
        with patch.object(self.c, "save", side_effect=interrupted), self.assertRaises(OSError):
            self.c.finish_transition()
        accounted = self.c.guard._snapshot(self.c.task_id, permit.decision.baseline.requirement_id)[2]
        self.assertIsNone(accounted["active"])
        with patch.object(self.c, "observe_checks", side_effect=AssertionError("Never observe a second check")), \
             patch.object(self.c.guard, "begin", side_effect=AssertionError("Never allocate a second permit")):
            self.c.finish_transition()
        self.assertEqual(self.c.guard._snapshot(self.c.task_id, permit.decision.baseline.requirement_id)[2], accounted)
        self.assertIsNone(self.c.record()["coordination"])
        self.assertEqual(self.c.record()["phase"], "LOCAL_DRAFT_CODE_REVIEWED")

    def test_check_entry_recovers_a_permit_missing_after_canonical_allocation(self):
        self.enroll()
        self.c.initialize_run()
        row = self.c.record()
        row.update(phase="CHECKS", developer="synthetic-only-accounting-fixture")
        self.c.save(row)
        original_save = self.c.save
        def interrupted(row):
            if row["coordination"] is not None and row["coordination"]["permit"] is not None:
                raise OSError("Synthetic check-stage permit persistence failure")
            return original_save(row)
        with patch.object(self.c, "save", side_effect=interrupted), self.assertRaises(OSError):
            self.c.check_stage()
        self.assertEqual(self.c.record()["phase"], "CHECKS")
        self.assertIsNone(self.c.record()["coordination"]["permit"])
        item = self.c.guard._snapshot(self.c.task_id, self.c.requirement("develop"))[2]
        token = item["active"]["id"]
        with patch.object(self.c.guard, "begin", side_effect=AssertionError("Never allocate another check permit")), \
             patch.object(self.c, "observe_checks", return_value={"status": "UNKNOWN", "qualified": False}) as observer:
            self.c.check_stage()
        observer.assert_called_once()
        item = self.c.guard._snapshot(self.c.task_id, self.c.requirement("develop"))[2]
        self.assertIsNone(item["active"])
        self.assertEqual(item["last"]["action"]["hypothesis"], "personal:checks:synthetic-only-accounting-fixture")
        self.assertEqual(self.c.record()["coordination"], None)
        self.assertEqual(observer.call_args.args[0].token, token)

    def test_lost_check_delivery_stays_unknown_without_reobserving(self):
        self.enroll()
        self.c.initialize_run()
        row = self.c.record()
        row.update(phase="CHECKS", developer="synthetic-only-accounting-fixture")
        self.c.save(row)
        with patch.object(self.c, "observe_checks", side_effect=OSError("Synthetic lost check delivery")) as observer, self.assertRaises(OSError):
            self.c.check_stage()
        observer.assert_called_once()
        self.assertEqual(self.c.record()["coordination"]["check_state"], "SUBMITTED")
        with patch.object(self.c, "observe_checks", side_effect=AssertionError("Never replay missing check delivery")) as observer:
            self.c.check_stage()
        observer.assert_not_called()
        self.assertEqual(self.c.record()["gates"][-1]["status"], "UNKNOWN")
        self.assertEqual(self.c.record()["gates"][-1]["reason"], "LOST_CHECK_DELIVERY")
        self.assertIsNone(self.c.record()["coordination"])
        # No code receipt was supplied by this accounting-only fixture.
        self.assertEqual(self.c.status()["status"], "BLOCKED_CODE_REVIEW")

    def test_rejected_candidate_transition_recovers_the_same_observation(self):
        self.enroll()
        self.c.initialize_run()
        permit = self.c.reserve("focused-candidate-transition")
        row = self.c.record()
        row.update(phase="CANDIDATE_REJECTED", candidate="synthetic-only-accounting-fixture",
            feedback=[{"outcome": "FAIL", "approved": False, "criteria": [], "summary": "Synthetic in-scope feedback", "forensic": None}])
        self.c.save(row)
        with patch.object(self.c.guard, "observe", side_effect=OSError("Synthetic interruption before guard observation")), self.assertRaises(OSError):
            self.c.finish_transition()
        retained = self.c.record()["coordination"]["observation"]
        self.assertEqual(retained["outcome"], "FAIL")
        with patch.object(self.c.guard, "begin", side_effect=AssertionError("Never allocate another candidate recovery permit")):
            self.c.finish_transition()
        actual = self.c.guard._snapshot(self.c.task_id, permit.decision.baseline.requirement_id)[2]
        self.assertEqual(actual["last"]["observation"], retained)
        self.assertIsNone(actual["active"])
        self.assertEqual(self.c.record()["phase"], "DEVELOP")

    def test_submitted_absent_worktree_is_not_launched_again(self):
        self.enroll()
        self.c.initialize_run()
        original = self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.record()
        row.update(original_review=original["request"]["id"], phase="FEATURE")
        self.c.save(row)
        from adp.git import git as actual_git
        def interrupted(root, *args, **kwargs):
            if "worktree" in args and args[args.index("worktree") + 1] == "add":
                raise OSError("Synthetic loss before known worktree outcome")
            return actual_git(root, *args, **kwargs)
        with patch("adp.execution_ports.git", side_effect=interrupted), self.assertRaises(OSError):
            self.c.prepare_feature()
        self.assertFalse(self.personal.feature.exists())
        with patch("adp.execution_ports.git", side_effect=interrupted) as launch, self.assertRaises(ADPError):
            self.c.prepare_feature()
        self.assertFalse(any("worktree" in call.args and call.args[call.args.index("worktree") + 1] == "add" for call in launch.call_args_list))

    def test_feature_worktree_write_ignores_a_late_git_redirection(self):
        original_root = self.a
        self.a = self.base / "enrollment-checkout"
        run(original_root, "worktree", "add", "-b", "selected", str(self.a))
        self.enroll()
        self.c.initialize_run()
        reviewed = self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.record()
        row.update(original_review=reviewed["request"]["id"], phase="FEATURE")
        self.c.save(row)
        common = original_root / ".git"
        original_directory = Path(value(self.a, "rev-parse", "--absolute-git-dir"))
        copied = self.base / "foreign-feature-administration"
        from adp.git import git as actual_git
        def redirected(root, *args, **kwargs):
            if "worktree" in args and args[args.index("worktree") + 1] == "add":
                shutil.copytree(common, copied)
                (self.a / ".git").write_text("gitdir: " + str(copied / original_directory.relative_to(common)) + "\n")
            return actual_git(root, *args, **kwargs)
        with patch("adp.execution_ports.git", side_effect=redirected), self.assertRaises(ADPError):
            self.c.prepare_feature()
        registered = value(original_root, "worktree", "list", "--porcelain")
        self.assertIn("worktree " + str(self.personal.feature), registered)
        self.assertNotIn("worktree " + str(self.personal.feature), value(copied, "worktree", "list", "--porcelain"))

    def enroll(self, ci_transport=None):
        p, original, docs = self.plan(ci_transport=ci_transport)
        self.personal = apply_personal(p, original, docs, approved=approval(p), authorized=True,
            transport=self.transport, ci_transport=ci_transport, clock=lambda: self.now)
        self.runtime = CodexExecRuntime(self.personal.state / "runtime")
        self.observed, self.requests = {}, []
        self.c = PersonalCoordinator(self.personal, self.transport, ci_transport, runtime=self.runtime, clock=lambda: self.now)
        self.caps = Capabilities("codex-exec", self.runtime.host, "SYNTHETIC_TEST_ONLY", True, True, True, True, 1)
        self.addCleanup(patch.stopall)
        patch.object(self.runtime, "capabilities", return_value=self.caps).start()
        patch.object(self.runtime, "observe", side_effect=lambda identity: self.observed.get(identity,
            RuntimeObservation(identity, self.runtime.host, RuntimeStatus.NOT_STARTED, None, None, "runtime:not-started", 0))).start()
        patch.object(self.runtime, "dispatch", side_effect=self.dispatch).start()

    def dispatch(self, request):
        self.requests.append(request)
        purpose = json.loads(request.prompt.split("\n", 1)[1])["purpose"]
        if purpose == "develop":
            (Path(request.workspace) / "product").write_text("original ticket implemented\n")
        result = WorkerResult(Outcome.PASS, purpose != "develop", () if purpose == "develop" else (purpose,), "Synthetic offline fixture verdict")
        if purpose == "develop":
            result = replace(result, summary=json.dumps({"change": "Synthetic in-scope fixture change",
                "checks": [{"command": "fixture-local-check", "outcome": "PASS", "result": "Synthetic validation; not real Codex or CI"}],
                "limitations": "Patched runtime fixture only"}))
        observed = RuntimeObservation(request.id, self.runtime.host, RuntimeStatus.COMPLETED, "synthetic-context:" + request.id,
            result, "runtime:synthetic:" + request.id, 1, digest(request), 1, 100, True)
        self.observed[request.id] = observed
        return observed

    def test_preview_decline_and_separate_execution_consent_are_read_only(self):
        self.enroll()
        before = snapshot(self.base)
        view, reviewed = self.c.invocation()
        self.assertEqual(view["maximum_tasks"], 1)
        self.assertEqual(view["maximum_rounds"], 1)
        self.assertEqual(view["maximum_parallel"], 1)
        for authorized, token in ((False, reviewed), (True, approval(self.personal.plan)), (True, "personal-run:" + "0" * 64)):
            with self.subTest(authorized=authorized, token=token), self.assertRaises(ADPError):
                self.c.run(reviewed=token, authorized=authorized)
        self.assertEqual(snapshot(self.base), before)
        self.assertEqual(self.requests, [])

    def test_synthetic_local_draft_uses_distinct_roles_and_exact_commit(self):
        self.enroll()
        main = value(self.a, "rev-parse", "HEAD")
        remote_before = snapshot(self.remote)
        _, reviewed = self.c.invocation()
        result = self.c.run(reviewed=reviewed, authorized=True)
        self.assertEqual(result["status"], "LOCAL_DRAFT_CODE_REVIEWED")
        self.assertEqual(result["product_acceptance"], "NOT_ACCEPTED")
        self.assertEqual(result["runtime_qualification"], "NOTRUN")
        self.assertEqual(value(self.a, "rev-parse", "HEAD"), main)
        self.assertEqual(value(self.a, "symbolic-ref", "HEAD"), "refs/heads/trunk")
        self.assertNotEqual(result["revision"], main)
        self.assertEqual(value(self.personal.feature, "rev-parse", "HEAD^"), main)
        self.assertEqual([json.loads(r.prompt.split("\n", 1)[1])["purpose"] for r in self.requests],
                         ["original", "develop", "candidate", "code"])
        self.assertEqual(len({o.context_id for o in self.observed.values()}), 4)
        self.assertEqual(self.requests[-1].revision, result["revision"])
        self.assertEqual(result["check_results"][0]["status"], "UNKNOWN")
        self.assertFalse(result["check_results"][0]["qualified"])
        # Discovery legitimately GETs issue comments; no forge write port exists.
        self.assertNotIn("/merges", str(self.transport.calls))
        self.assertEqual(snapshot(self.remote), remote_before)
        observed = self.c.memory.inspect()
        self.assertTrue(observed["local_owner"])
        self.assertEqual(len(observed["tasks"]), 1)
        self.assertEqual(observed["state"]["execution"]["tasks"], {})
        item = self.c.guard._snapshot(self.c.task_id, self.c.requirement("develop"))[2]
        self.assertEqual(item["unresolved"], [self.personal.plan["criterion"]])
        self.assertIsNotNone(item["approval"])
        before = snapshot(self.base)
        status = self.c.status()
        self.assertEqual(status["status"], result["status"])
        self.assertEqual(snapshot(self.base), before)
        _, reviewed = self.c.invocation("resume")
        self.c.run(reviewed=reviewed, authorized=True, operation="resume")
        self.assertEqual(len(self.requests), 4)
        run(self.personal.feature, "commit", "--allow-empty", "-m", "External source change invalidates review")
        with self.assertRaises(ADPError):
            self.c.verify_draft()

    def test_native_project_validation_preserves_pass_failure_and_foreign_origin(self):
        run(self.a, "checkout", "-b", "work/issue-1")
        self.choices = replace(self.choices, checks=("unit",), accept_native_job_records=True)
        native = NativePersonalReads(self)
        self.enroll(ci_transport=native)
        self.assertEqual(self.personal.plan["required_check_names"], ["unit"])
        self.assertEqual(self.personal.plan["checks"][0]["origin"], "github-app:9")
        self.c.initialize_run()
        reviewed = self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.record()
        row.update(original_review=reviewed["request"]["id"], phase="DEVELOP")
        self.c.save(row)
        permit = self.c.reserve("focused-native-check")
        first = self.c.observe_checks(permit)
        self.assertEqual(first["status"], "PASS")
        self.assertTrue(first["qualified"])
        native.conclusion = "failure"
        second = self.c.observe_checks(permit)
        self.assertEqual(second["status"], "FAIL")
        self.assertFalse(second["qualified"])
        native.app = 999
        third = self.c.observe_checks(permit)
        self.assertFalse(third["qualified"])
        self.assertIn(third["status"], ("UNKNOWN", "NOTRUN"))
        self.assertEqual(self.c.record()["observations"], 3)
        with self.assertRaises(ADPError):
            self.c.observe_checks(permit)
        self.assertEqual(self.c.status()["product_acceptance"], "NOT_ACCEPTED")

    def test_accounted_developer_recovery_does_not_allocate_a_second_context(self):
        self.enroll()
        original_save = self.c.save
        interrupted = []
        def stop_before_stage(row):
            if row["phase"] == "STAGE" and not interrupted:
                interrupted.append(True)
                raise OSError("Synthetic crash after Developer accounting, before phase transition")
            return original_save(row)
        with patch.object(self.c, "save", side_effect=stop_before_stage):
            _, reviewed = self.c.invocation()
            with self.assertRaises(OSError):
                self.c.run(reviewed=reviewed, authorized=True)
        self.assertEqual(self.c.record()["phase"], "DEVELOP")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(sum(r["purpose"] == "develop" for r in self.c.workers.records()), 1)
        # Recover the exact accepted request without launching another worker.
        self.runtime.dispatch.reset_mock()
        recovered = self.c.workers.execute("develop", self.c.context("develop"), self.personal.feature)
        self.assertEqual(recovered["phase"], "ACCOUNTED")
        self.runtime.dispatch.assert_not_called()

    def test_missing_stop_never_supplies_scope_authority(self):
        self.enroll()
        self.c.initialize_run()
        original_dispatch = self.dispatch
        def missing_stop(request):
            observed = replace(original_dispatch(request), stopped=False)
            self.observed[request.id] = observed
            return observed
        self.runtime.dispatch.side_effect = missing_stop
        with self.assertRaises(ADPError):
            self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.workers.records()[0]
        self.assertEqual(self.c.guard.inspect(self.c.task_id, row["requirement"]).kind, DecisionKind.STOP_UNSAFE)
        self.assertFalse(self.personal.feature.exists())

    def test_reused_runtime_context_is_not_an_independent_candidate(self):
        self.enroll()
        self.c.initialize_run()
        original = self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.record()
        row.update(original_review=original["request"]["id"], phase="FEATURE")
        self.c.save(row)
        self.c.prepare_feature()
        original_dispatch = self.dispatch
        def reused(request):
            observed = replace(original_dispatch(request), context_id=original["observation"]["context_id"])
            self.observed[request.id] = observed
            return observed
        self.runtime.dispatch.side_effect = reused
        with self.assertRaisesRegex(ADPError, "independent"):
            self.c.workers.execute("candidate", self.c.context("candidate"), self.personal.feature)
        self.assertEqual(value(self.personal.feature, "rev-parse", "HEAD"), self.personal.plan["checkout"]["head"])
        self.assertFalse(any(a["operation"] == "COMMIT" for a in self.c.record()["actions"].values()))

    def test_developer_self_approval_is_a_terminal_authority_violation(self):
        run(self.a, "checkout", "-b", "work/issue-1")
        self.enroll()
        self.c.initialize_run()
        original = self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.record()
        row.update(original_review=original["request"]["id"], phase="DEVELOP")
        self.c.save(row)
        original_dispatch = self.dispatch
        def self_approved(request):
            observed = original_dispatch(request)
            observed = replace(observed, result=replace(observed.result, approved=True))
            self.observed[request.id] = observed
            return observed
        self.runtime.dispatch.side_effect = self_approved
        with self.assertRaisesRegex(ADPError, "self-approve"):
            self.c.workers.execute("develop", self.c.context("develop"), self.a)
        self.assertEqual(self.c.guard.inspect(self.c.task_id, self.c.requirement("develop")).kind, DecisionKind.STOP_UNSAFE)
        self.assertFalse(any(a["operation"] == "COMMIT" for a in self.c.record()["actions"].values()))

    def test_unavailable_runtime_and_native_blocker_never_launch(self):
        self.enroll()
        self.runtime.capabilities.return_value = replace(self.caps, independent_contexts=False)
        _, reviewed = self.c.invocation()
        with self.assertRaises(ADPError):
            self.c.run(reviewed=reviewed, authorized=True)
        self.assertIsNone(self.c.record())
        self.assertEqual(self.requests, [])
        self.assertFalse(self.personal.feature.exists())

    def test_lost_private_journal_cannot_reset_canonical_work(self):
        self.enroll()
        self.c.initialize_run()
        self.c.path.unlink()
        _, reviewed = self.c.invocation()
        with self.assertRaisesRegex(ADPError, "reset"):
            self.c.run(reviewed=reviewed, authorized=True)
        self.assertEqual(self.requests, [])

    def test_stale_preview_and_expiry_never_start_workers(self):
        self.enroll()
        _, reviewed = self.c.invocation()
        self.c.initialize_run()
        with self.assertRaises(ADPError):
            self.c.run(reviewed=reviewed, authorized=True)
        self.now = self.personal.plan["window"]["expires_at"]
        with self.assertRaises(ADPError):
            self.c.invocation("resume")
        self.assertEqual(self.requests, [])

    def test_submitted_with_missing_runtime_receipt_never_redispatches(self):
        self.enroll()
        self.c.initialize_run()
        context = self.c.context("original")
        self.runtime.dispatch.side_effect = OSError("Synthetic loss after durable submission intent")
        with self.assertRaises(OSError):
            self.c.workers.execute("original", context, self.a)
        self.assertEqual(self.c.workers.records()[0]["phase"], "SUBMITTED")
        self.runtime.dispatch.reset_mock()
        with self.assertRaisesRegex(ADPError, "redispatch"):
            self.c.workers.execute("original", context, self.a)
        self.runtime.dispatch.assert_not_called()
        with self.assertRaises(ADPError):
            self.c.workers.fence()

    def test_missing_worker_ledger_cannot_replenish_role_budget(self):
        self.enroll()
        self.c.initialize_run()
        result = self.c.workers.execute("original", self.c.context("original"), self.a)
        (self.c.workers.directory / (result["request"]["id"] + ".json")).unlink()
        self.runtime.dispatch.reset_mock()
        with self.assertRaisesRegex(ADPError, "unmapped"):
            self.c.workers.execute("original", self.c.context("original"), self.a)
        self.runtime.dispatch.assert_not_called()

    def test_approved_semantic_result_after_guard_deadline_never_authorizes(self):
        self.enroll()
        self.c.initialize_run()
        context = self.c.context("original")
        original_dispatch = self.dispatch
        def late(request):
            result = original_dispatch(request)
            self.now = request.deadline + 1
            return result
        self.runtime.dispatch.side_effect = late
        with self.assertRaises(ADPError):
            self.c.workers.execute("original", context, self.a)
        result = self.c.workers.records()[0]
        self.assertEqual(result["phase"], "ACCOUNTED")
        self.runtime.dispatch.reset_mock()
        with self.assertRaises(ADPError):
            self.c.workers.execute("original", context, self.a)
        self.runtime.dispatch.assert_not_called()
        self.assertFalse(self.personal.feature.exists())

    def test_rejected_scope_does_not_prepare_feature_or_start_developer(self):
        run(self.a, "checkout", "-b", "unrelated")
        (self.a / "AGENTS.md").write_text("Use only topic branches. Checks must precede commit.\n")
        run(self.a, "add", "AGENTS.md")
        run(self.a, "commit", "-m", "Add actual project governance")
        self.enroll()
        original_dispatch = self.dispatch
        def rejected(request):
            self.assertIn("Checks must precede commit", request.prompt)
            observed = original_dispatch(request)
            observed = replace(observed, result=WorkerResult(Outcome.FAIL, False, (), "Synthetic policy rejection: unsupported precommit evidence"))
            self.observed[request.id] = observed
            return observed
        self.runtime.dispatch.side_effect = rejected
        _, reviewed = self.c.invocation()
        with self.assertRaises(ADPError):
            self.c.run(reviewed=reviewed, authorized=True)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.personal.feature.exists())

    def test_handoff_after_expiry_revokes_without_renewing_window(self):
        self.enroll()
        expires = self.personal.plan["window"]["expires_at"]
        self.now = expires
        _, reviewed = self.c.invocation("handoff")
        result = self.c.run(reviewed=reviewed, authorized=True, operation="handoff")
        self.assertEqual(result["status"], "HANDED_OFF")
        self.assertFalse(self.c.memory.inspect()["local_owner"])
        self.assertEqual(self.personal.plan["window"]["expires_at"], expires)
        self.assertEqual(self.requests, [])
