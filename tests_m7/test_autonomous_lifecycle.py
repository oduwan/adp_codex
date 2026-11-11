"""Frozen #22 focused cases: actual accepted ports, disposable products only."""
import copy
import hashlib
import json
from dataclasses import fields, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from lifecycle_fixtures import LifecycleFixture
from test_config import run
from adp.autonomous_track import AutonomousTrack, PreparationInputs, TaskSpec, TrackWindow
from adp.discovery_schema import digest, typed
from adp.discovery_types import Identity, Relation, Status, Target
from adp.errors import ADPError, AuthorityError
from adp.execution_schema import execution_schema
from adp.execution_types import Role, RuntimeStatus
from adp.guard_types import DecisionKind, Outcome, data
from adp.lifecycle import TaskLifecycle
from adp.network_http import Response, NetworkTransportError
from adp.policy_types import CandidateValidationRequest, Operation, OutcomeCount, Qualifications, Request
from adp.project_validation import capture_candidate, action_subject, policy_subject
from adp.project_validation_types import CandidateEvidenceGate, EvidenceGate, Phase, ResultStatus
from adp.schema import key
from adp.ticket_http_child import validate_request
from adp.ticket_preparation import preparation_subject
from adp.ticket_publication import DependencyEdit, TicketPublisher
from adp.ticket_types import ChangeKind, Clause, TicketChange


class Cases(unittest.TestCase):
    def fixture(self, *, attach=False, mode="CANDIDATE"):
        fixture = LifecycleFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        if attach:
            fixture.attach(mode=mode)
        return fixture

    def checked(self, f):
        aid, job = f.conductor._job(f.admission, Role.DEVELOPER, f.generation)
        result, job = f.conductor._worker(f.admission, aid, job, f.generation)
        source = capture_candidate(f.root)
        return aid, job, source, f.life._check(f.admission, aid, job, source)


class CandidateEvidenceTests(Cases):
    def test_legacy_sha_requests_and_subjects_remain_unchanged(self):
        from adp.project_validation_types import EvidenceRequest, ProjectResult
        self.assertNotIn("candidate", {f.name for f in fields(EvidenceRequest)})
        self.assertNotIn("candidate_digest", {f.name for f in fields(ProjectResult)})
        self.assertNotIn("candidate", data(Request(Operation.VALIDATE)))
        f = self.fixture(attach=True, mode="COMMITTED")
        aid, job = f.conductor._job(f.admission, Role.COORDINATION, f.generation)
        provider, plan, auth, validation = f.life._validator(f.admission, job)
        request = validation.request(Phase.BEFORE_PR, authorization=auth)
        self.assertEqual(type(request).__name__, "EvidenceRequest")
        self.assertNotIn("candidate", data(request))

    def test_candidate_requests_require_current_base_index_and_worktree(self):
        f = self.fixture(attach=True)
        aid, job = f.conductor._job(f.admission, Role.DEVELOPER, f.generation)
        source = capture_candidate(f.root)
        (f.root / "product.py").write_text("changed\n")
        with self.assertRaises(ADPError):
            f.life._validator(f.admission, job, source)
        self.assertNotEqual(capture_candidate(f.root), source)
        # Source identity is independent of legitimate staging of a deletion
        # or rename. These are disposable unadmitted source observations, not
        # authorization to edit paths outside a product packet.
        root = f.base / "staging-source"
        run(f.base, "clone", str(f.remote), str(root))
        original = (root / "product.py").read_bytes()
        (root / "product.py").unlink()
        deleted = capture_candidate(root)
        run(root, "add", "--", "product.py")
        self.assertEqual(capture_candidate(root).content_digest, deleted.content_digest)
        (root / "renamed.py").write_bytes(original)
        renamed = capture_candidate(root)
        run(root, "add", "--", "renamed.py")
        self.assertEqual(capture_candidate(root).content_digest, renamed.content_digest)
        self.assertNotEqual(capture_candidate(root).index_digest, renamed.index_digest)

    def test_candidate_results_cannot_satisfy_committed_sha_gates(self):
        f = self.fixture(attach=True)
        _, _, _, gate = self.checked(f)
        self.assertTrue(gate.qualified)
        self.assertIs(type(gate), CandidateEvidenceGate)
        with self.assertRaises(ADPError):
            typed(EvidenceGate, data(gate))

    def test_candidate_observation_rejects_foreign_or_changed_content(self):
        f = self.fixture(attach=True)
        f.foreign = True
        _, _, _, gate = self.checked(f)
        self.assertEqual(gate.status, ResultStatus.UNKNOWN)
        self.assertIn("unit", gate.missing)
        self.assertFalse(gate.qualified)

    def test_candidate_action_uses_actual_queued_memory_reservation(self):
        f = self.fixture(attach=True)
        f.action_id = "project:unit"
        class Action:
            def request(self, request, action_id, action_key):
                f.action_count += 1
                self.requested = request
        f.life.action = Action()
        _, _, _, gate = self.checked(f)
        self.assertEqual(f.action_count, 1)
        self.assertTrue(gate.qualified)
        self.assertTrue(f.queries[-1].action_key)

    def test_candidate_action_missing_authority_or_unknown_delivery_refuses(self):
        f = self.fixture(attach=True)
        f.action_id = "project:unit"
        f.authority.denied.add("project-validation/candidate-action")
        class Action:
            def request(self, *args):
                raise AssertionError("Unauthorized project action")
        f.life.action = Action()
        with self.assertRaises(AuthorityError):
            self.checked(f)
        self.assertEqual(f.action_count, 0)
        self.assertEqual(f.conductor._task(f.admission)["revision"], f.initial)

    def test_candidate_partial_pending_and_job_counts_remain_honest(self):
        f = self.fixture(attach=True)
        f.check_status, f.complete, f.coverage = ResultStatus.PENDING, False, "PARTIAL"
        _, _, _, gate = self.checked(f)
        self.assertEqual(gate.status, ResultStatus.UNKNOWN)
        self.assertEqual(gate.results[0].status, ResultStatus.PENDING)
        self.assertIsNone(gate.results[0].denominator)
        self.assertFalse(gate.qualified)

    def test_candidate_pass_requires_unchanged_source_through_staging(self):
        f = self.fixture()
        exclude = Path(run(f.root, "rev-parse", "--git-path", "info/exclude"))
        if not exclude.is_absolute(): exclude = f.root / exclude
        exclude.write_text(".project-cache/\n")
        f.attach()
        f.action_id = "project:existing-unit"
        class ExistingProjectCheck:
            def request(self, *args):
                (f.root / ".project-cache").mkdir()
                (f.root / ".project-cache/result").write_text("project-owned ignored output\n")
        f.life.action = ExistingProjectCheck()
        _, job, _, gate = self.checked(f)
        self.assertTrue(gate.qualified)
        # Exact parent-owned post-check full-workspace checkpoint permits
        # interrupted delivery without relaxing the live worker outside seal.
        aid = f.life.record(f.admission)["job"]
        f.conductor._worker(f.admission, aid, job, f.generation)
        run(f.root, "add", "product.py")
        f.life.before_commit(f.admission, job, f.generation)
        cache = f.root / ".project-cache/result"
        original_cache = cache.read_bytes()
        cache.write_text("unobserved later ignored drift\n")
        with self.assertRaises(ADPError):
            f.conductor._worker(f.admission, aid, job, f.generation)
        with self.assertRaises(ADPError):
            f.life.before_commit(f.admission, job, f.generation)
        cache.write_bytes(original_cache)
        run(f.root, "add", "-f", "--", ".project-cache/result")
        with self.assertRaises(ADPError):
            f.life.before_commit(f.admission, job, f.generation)
        run(f.root, "rm", "--cached", "--", ".project-cache/result")
        (f.root / "product.py").write_text("unchecked\n")
        with self.assertRaises(ADPError):
            f.life.before_commit(f.admission, job, f.generation)
        run(f.root, "update-index", "--assume-unchanged", "product.py")
        with self.assertRaisesRegex(ADPError, "Hidden index"):
            f.life._visible_index(f.root)


class AutonomousLifecycleTests(Cases):
    def test_explicit_v3_upgrade_preserves_accepted_state_and_old_readers(self):
        f = self.fixture()
        execution = f.conductor.journal.inspect()["state"]["execution"]
        self.assertEqual(execution["schema_version"], 3)
        execution_schema(execution, f.config.identity)
        old = copy.deepcopy(execution)
        old.update(schema_version=2)
        for field in ("track", "lifecycles", "ticket_effects"):
            del old[field]
        execution_schema(old, f.config.identity)
        before = f.memory.inspect()["local_head"]
        with self.assertRaises(AuthorityError):
            f.conductor.journal.upgrade_track()
        self.assertEqual(before, f.memory.inspect()["local_head"])

    def test_window_status_is_readonly_and_has_no_execution_authority(self):
        f = self.fixture()
        before = f.memory.inspect()["local_head"]
        self.assertIsNone(f.track.status()["track"])
        self.assertEqual(f.track.status()["background_work"], "UNKNOWN")
        self.assertEqual(before, f.memory.inspect()["local_head"])
        self.assertEqual(f.runtime.dispatch_count, 0)

    def test_window_missing_authority_and_stale_generation_refuse(self):
        f = self.fixture()
        with self.assertRaises(AuthorityError):
            f.track.run()
        f.authority.denied.add("track/window")
        with self.assertRaises(AuthorityError):
            f.track.run(authorized=True)
        self.assertEqual(f.runtime.dispatch_count, 0)
        f.authority.denied.clear()
        f.track._window(create=True)
        f.conductor.journal.change(lambda execution, state, tasks: execution["track"].update(generation=f.generation + 1))
        with self.assertRaises(ADPError):
            f.track.run(authorized=True)

    def test_prepared_packet_drives_project_specific_worker_instructions(self):
        f = self.fixture(attach=True)
        prompt = f.life.prompt(f.admission, Role.DEVELOPER, f.initial)
        packet = f.life.packet()
        self.assertIn(packet.goal, prompt)
        self.assertIn("Use project-owned unit evidence", prompt)
        self.assertNotIn("Use python -B", prompt)
        self.assertIn("do not invent or execute a test runner", prompt)
        self.assertIn("approved=false and criteria=[]", prompt)
        self.assertIn("implementation activity only", prompt)
        self.assertIn("Never claim a check ran or passed", prompt)
        review = f.life.prompt(f.admission, Role.REVIEWER, f.initial)
        self.assertIn("approved=true only", review)
        self.assertIn("report only admitted acceptance_ids you independently verified", review)
        self.assertEqual(packet.execution_authority, "UNKNOWN")

    def test_unapproved_product_test_and_integration_scope_stops_before_dispatch(self):
        f = self.fixture()
        original_assess = f.spec.assess
        def expanded(original, track, inspection):
            inputs = original_assess(original, track, inspection)
            change = TicketChange("extra", ChangeKind.ADDITION, "SCOPE", "", "new integration",
                added_clauses=(Clause("extra-check", "CHECK", "new integration campaign"),), added_checks=("new-suite",))
            proposal = replace(inputs.proposal, changes=(change,), parts=(replace(inputs.proposal.parts[0],
                clauses=(*inputs.proposal.parts[0].clauses, "extra-check")),))
            review = replace(inputs.review, evidence=None)
            review = replace(review, evidence=f.authority.grant(purpose="ticket/preparation",
                subject=preparation_subject(original, inputs.scope, proposal, review, track)))
            return replace(inputs, proposal=proposal, review=review)
        spec = replace(f.spec, assess=expanded)
        track = AutonomousTrack(f.conductor, f.window, (spec,))
        track._window(create=True)
        self.assertIsNone(track._prepare(spec, f.readiness.observe()))
        self.assertEqual(f.runtime.dispatch_count, 0)
        self.assertEqual(track.status()["track"]["slots"][digest(spec.identity)]["status"], "BLOCKED_OPERATOR")

    def test_edited_issue_split_and_dependency_scope_laundering_refuse(self):
        f = self.fixture(attach=True)
        candidate = f.readiness.observe().candidates[0]
        changed = replace(candidate, issue=replace(candidate.issue, body="new original requirements"))
        with self.assertRaises(ADPError):
            f.life.scope.verify(f.admission, changed, f.initial)
        with self.assertRaises(ADPError):
            f.scope.preparer.archive.freeze(replace(f.discovery.snapshot, issues=(changed.issue,)), changed.identity)

    def test_candidate_check_failure_corrects_before_policy_commit(self):
        f = self.fixture(attach=True)
        f.statuses = [ResultStatus.FAIL, ResultStatus.PASS]
        f.runtime.serial_corrections = True
        f.conductor._develop(f.admission, f.generation)
        self.assertEqual(run(f.root, "rev-parse", "HEAD"), f.initial)
        self.assertEqual(f.life.record(f.admission)["phase"], "REQUIRES_CORRECTION")
        first = f.queries[-1].request.candidate
        f.conductor._develop(f.admission, f.generation)
        self.assertNotEqual(run(f.root, "rev-parse", "HEAD"), f.initial)
        self.assertNotEqual(f.queries[-1].request.candidate, first)
        self.assertEqual([q.request.revision for q in f.queries], [f.initial, f.initial])
        self.assertEqual(f.runtime.develop_count, 2)

    def test_committed_check_failure_corrects_and_checks_new_sha(self):
        f = self.fixture(attach=True, mode="COMMITTED")
        f.statuses = [ResultStatus.ERROR, ResultStatus.PASS]
        f.runtime.serial_corrections = True
        f.conductor._develop(f.admission, f.generation)
        first = run(f.root, "rev-parse", "HEAD")
        self.assertFalse(f.life.before_review(f.admission, f.generation))
        self.assertEqual(f.queries[-1].request.revision, first)
        self.assertEqual(f.conductor._task(f.admission)["stage"], "DEVELOP")
        f.conductor._develop(f.admission, f.generation)
        second = run(f.root, "rev-parse", "HEAD")
        self.assertNotEqual(first, second)
        self.assertEqual(f.guard.inspect(f.admission.task_id, f.conductor._requirement(f.admission)).kind,
                         DecisionKind.FORENSIC_REQUIRED)
        f.conductor._forensic(f.admission, f.generation)
        self.assertTrue(f.life.before_review(f.admission, f.generation))
        self.assertEqual(f.queries[-1].request.revision, second)

    def test_post_pr_pending_retains_iteration_and_current_pr(self):
        f = self.fixture(attach=True, mode="POST_PR")
        f.phases = (Phase.AFTER_PR,)
        f.check_status = ResultStatus.PENDING
        f.conductor._cycle(f.admission, f.generation)
        flow = f.conductor.projects["one"].product_flow
        self.assertEqual(flow._flow(f.admission)["phase"], "PENDING_VALIDATION")
        self.assertEqual(len(f.server.pulls), 1)
        self.assertIsNone(f.conductor._task(f.admission)["review"])
        self.assertEqual(f.conductor._task(f.admission)["product_iteration"], 1)

    def test_review_rejection_requires_correction_commit_and_new_context(self):
        f = self.fixture(attach=True)
        f.runtime.reject_reviews = 1
        f.runtime.serial_corrections = True
        f.conductor._cycle(f.admission, f.generation)
        first = run(f.root, "rev-parse", "HEAD")
        self.assertEqual(f.conductor._task(f.admission)["stage"], "DEVELOP")
        f.conductor._develop(f.admission, f.generation)
        second = run(f.root, "rev-parse", "HEAD")
        self.assertNotEqual(first, second)
        # Default M2 correction limits are retained: reassess independently if
        # the two corrections exhausted the no-progress allowance.
        for _ in range(2):
            if len([r for r in f.runtime.requests.values() if r.role == Role.REVIEWER]) == 2:
                break
            f.conductor._cycle(f.admission, f.generation)
        reviews = [r for r in f.runtime.requests.values() if r.role == Role.REVIEWER]
        self.assertEqual([r.revision for r in reviews], [first, second])
        self.assertNotEqual(reviews[0].id, reviews[1].id)

    def test_changed_sha_cannot_reuse_review_or_gate(self):
        f = self.fixture(attach=True)
        f.conductor._develop(f.admission, f.generation)
        f.conductor._review(f.admission, f.generation)
        (f.root / "product.py").write_text("def answer():\n    return 7\n")
        run(f.root, "add", "product.py")
        run(f.root, "commit", "-m", "external exact source drift")
        with self.assertRaises(ADPError):
            f.conductor._publish(f.admission, f.generation)
        self.assertEqual(len(f.server.pulls), 0)

    def test_foreign_reused_or_unavailable_worker_context_refuses(self):
        f = self.fixture(attach=True)
        original = f.runtime.capabilities
        f.runtime.capabilities = lambda: replace(original(), independent_contexts=False, reason="synthetic unsupported")
        result = f.track.run(authorized=True)
        self.assertEqual(result["status"], "UNSUPPORTED")
        self.assertEqual(f.runtime.dispatch_count, 0)

    def test_guard_stalls_use_bounded_forensics_and_terminal_stop(self):
        f = self.fixture(attach=True)
        f.runtime.fail_developers = 8
        for _ in range(3):
            result = f.conductor._cycle(f.admission, f.generation)
        self.assertTrue(any(r.role == Role.FORENSIC for r in f.runtime.requests.values()))
        for _ in range(3):
            result = f.conductor._cycle(f.admission, f.generation)
            if result["status"] == "BLOCKED":
                break
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(f.guard.inspect(f.admission.task_id, f.conductor._requirement(f.admission)).kind,
                      (DecisionKind.STOP_UNSAFE, DecisionKind.OPERATOR_DECISION_REQUIRED))

    def test_restart_observes_worker_without_duplicate_dispatch(self):
        f = self.fixture(attach=True)
        f.runtime.lose_response = True
        with self.assertRaises(OSError):
            f.conductor._develop(f.admission, f.generation)
        f.conductor._develop(f.admission, f.generation)
        self.assertEqual(f.runtime.dispatch_count, 1)
        self.assertEqual(f.conductor._task(f.admission)["stage"], "REVIEW")
        self.assertEqual(len(f.runtime.requests), 1)

    def test_restart_between_check_commit_and_delivery_reconciles_exact_effect(self):
        f = self.fixture(attach=True)
        deliver = f.conductor._deliver
        def interrupted(*args, **kwargs):
            deliver(*args, **kwargs)
            raise OSError("synthetic crash after immutable delivery")
        with patch.object(f.conductor, "_deliver", side_effect=interrupted):
            with self.assertRaises(OSError):
                f.conductor._develop(f.admission, f.generation)
        revision, queries = run(f.root, "rev-parse", "HEAD"), len(f.queries)
        f.conductor._develop(f.admission, f.generation)
        self.assertEqual(run(f.root, "rev-parse", "HEAD"), revision)
        self.assertEqual(len(f.queries), queries)
        self.assertEqual(f.runtime.dispatch_count, 1)

    def test_restart_pending_ci_does_not_manufacture_pass(self):
        f = self.fixture(attach=True)
        f.check_status = ResultStatus.PENDING
        f.conductor._develop(f.admission, f.generation)
        self.assertEqual(f.life.record(f.admission)["phase"], "PENDING_VALIDATION")
        f.conductor._develop(f.admission, f.generation)
        self.assertEqual(f.runtime.develop_count, 1)
        self.assertEqual(run(f.root, "rev-parse", "HEAD"), f.initial)
        self.assertIsNone(f.conductor._task(f.admission)["review"])

    def test_fresh_track_advances_only_independently_ready_prerequisites(self):
        f = self.fixture()
        track, second = f.dependent_track()
        observed = f.readiness.observe()
        self.assertEqual(next(c for c in observed.candidates if c.identity == second.identity).status, Status.BLOCKED_DEPENDENCY)
        result = track.run(rounds=3, authorized=True)
        self.assertEqual(f.conductor._task(f.admission)["stage"], "COMPLETE", result)
        self.assertEqual(track.status()["track"]["slots"][digest(f.admission.identity)]["status"], "COMPLETE")
        self.assertTrue(any(r.task_id == second.task_id and r.role == Role.DEVELOPER for r in f.runtime.requests.values()), result)
        self.assertTrue(any(r.task_id == second.task_id and r.role == Role.REVIEWER for r in f.runtime.requests.values()), result)
        self.assertEqual(sum(method == "PUT" for method, _, _ in f.server.calls), 1)
        self.assertEqual(len(f.server.comments), 1)
        self.assertEqual(track.status()["track"]["used_rounds"], 3)

    def test_cycles_duplicates_and_missing_specs_never_dispatch(self):
        f = self.fixture()
        rows = f.discovery.snapshot.issues
        relations = [Relation("BLOCKED_BY", Target("demo/project", rows[1-i].number, rows[1-i].identity.issue_id), "NATIVE", "fixture:native")
                     for i in range(2)]
        f.discovery.snapshot = replace(f.discovery.snapshot, issues=tuple(replace(row, relations=(relations[i],)) for i, row in enumerate(rows)))
        result = f.track.run(authorized=True)
        self.assertEqual(f.runtime.dispatch_count, 0)
        self.assertTrue(f.readiness.observe().cycles)
        self.assertNotEqual(result["status"], "COMPLETE")

    def test_consumed_identity_and_alias_cannot_repeat_completed_work(self):
        f = self.fixture()
        alias = replace(f.spec, task_id="new-task-alias", workspace_key="two")
        with self.assertRaises(ADPError):
            AutonomousTrack(f.conductor, replace(f.window, maximum_tasks=2), (f.spec, alias))
        before = f.runtime.dispatch_count
        f.track._window(create=True)
        with self.assertRaises(ADPError):
            f.track._attach(replace(f.spec, task_id="alias"), f.scope.packet_reference)
        self.assertEqual(f.runtime.dispatch_count, before)

    def test_window_bounds_survive_resume_and_cannot_be_expanded(self):
        f = self.fixture()
        f.track._window(create=True)
        expanded = AutonomousTrack(f.conductor, replace(f.window, maximum_rounds=9), (f.spec,))
        with self.assertRaises(ADPError):
            expanded.run(authorized=True)
        reviews = f.readiness.reviews
        f.readiness.reviews = lambda snapshots: ()
        f.track.run(authorized=True)
        f.readiness.reviews = reviews
        self.assertEqual(f.track.status()["track"]["used_rounds"], 1)
        old_generation = f.generation
        f.memory.handoff()
        f.memory.claim("new-finite-track-owner")
        resumed = AutonomousTrack(f.conductor, f.window, (f.spec,))
        with self.assertRaises(ADPError):
            resumed.run(authorized=True)
        resumed.adopt_generation(authorized=True)
        self.assertGreater(resumed.status()["generation"], old_generation)
        self.assertEqual(resumed.status()["track"]["used_rounds"], 1)
        self.assertEqual(resumed.status()["track"]["maximum_rounds"], f.window.maximum_rounds)
        f.now = f.window.expires_at
        with self.assertRaises(ADPError):
            f.track.run(authorized=True)
        self.assertEqual(f.runtime.dispatch_count, 0)

    def test_parallel_lanes_require_independent_workspaces_and_configured_limits(self):
        f = self.fixture()
        second = replace(f.spec, identity=f.admissions[1].identity, task_id=f.admissions[1].task_id)
        with self.assertRaises(ADPError):
            AutonomousTrack(f.conductor, replace(f.window, maximum_tasks=2, maximum_parallel=2), (f.spec, second))
        second = replace(second, workspace_key="two")
        parallel = AutonomousTrack(f.conductor, replace(f.window, maximum_tasks=2, maximum_parallel=2), (f.spec, second))
        with self.assertRaises(ADPError):
            parallel.run(maximum_parallel=3, authorized=True)
        from threading import Barrier
        from adp.execution_types import RuntimeObservation
        window, _ = f.dependent_track(dependent=False)
        barrier = Barrier(2)
        dispatch = f.runtime.dispatch
        def asynchronous(request):
            if request.role != Role.DEVELOPER:
                return dispatch(request)
            f.runtime.requests[request.id] = request
            observation = RuntimeObservation(request.id, f.runtime.host, RuntimeStatus.RUNNING, None, None,
                "fixture:running", 0, digest(request))
            f.runtime.observations[request.id] = observation
            return observation
        def wait(request_id):
            request = f.runtime.requests[request_id]
            if request.role == Role.DEVELOPER:
                barrier.wait(timeout=5)
                f.runtime.observations.pop(request_id)
                return dispatch(request)
            return f.runtime.observe(request_id)
        f.runtime.dispatch, f.runtime.wait = asynchronous, wait
        result = window.run(rounds=1, maximum_parallel=2, authorized=True)
        self.assertEqual(f.runtime.develop_count, 2, result)
        self.assertEqual(len([r for r in f.runtime.requests.values() if r.role == Role.REVIEWER]), 2, result)
        self.assertEqual({r.workspace for r in f.runtime.requests.values() if r.role == Role.DEVELOPER},
            {str(f.projects["one"].root), str(f.projects["two"].root)})

    def test_multiple_project_profiles_keep_distinct_memory_policy_and_ids(self):
        # The existing second project profile is separate; a single repository
        # window cannot smuggle a foreign opaque identity into its M1.
        f = self.fixture()
        foreign = replace(f.spec, identity=Identity("unrelated-repository-B", "same-opaque-issue"))
        with self.assertRaises(ADPError):
            AutonomousTrack(f.conductor, f.window, (foreign,))
        self.assertNotEqual(f.projects["one"].root, f.projects["two"].root)
        self.assertEqual(f.conductor.memory.config.identity, f.spec.identity.repository_id)
        from lifecycle_fixtures import SecondProfileFixture
        second = SecondProfileFixture()
        second.setUp()
        self.addCleanup(second.doCleanups)
        result = second.track.run(rounds=2, authorized=True)
        self.assertTrue(any(r.role == Role.DEVELOPER for r in second.runtime.requests.values()), result)
        self.assertTrue(any(r.role == Role.REVIEWER for r in second.runtime.requests.values()), result)
        self.assertNotEqual(second.memory.config.identity, f.memory.config.identity)
        self.assertEqual(run(second.root, "branch", "--show-current"), "change/one")
        self.assertTrue(run(second.root, "log", "-1", "--format=%s").startswith("repair: "))
        self.assertFalse(any(method == "PUT" for method, _, _ in second.server.calls))
        self.assertEqual(len(second.server.pulls), 1, result)
        self.assertTrue(second.queries)
        self.assertTrue(all(query.request.phase == Phase.AFTER_PR for query in second.queries))

    def test_handoff_refuses_unknown_actions_or_worker_stop(self):
        f = self.fixture(attach=True)
        f.life._save(f.admission, phase="CHECKING")
        with self.assertRaisesRegex(ADPError, "Unobserved"):
            f.life.before_handoff()
        f.authority.denied.add("track/adopt-generation")
        with self.assertRaises(ADPError):
            f.track.adopt_generation(authorized=True)
        self.assertEqual(f.track.status()["track"]["generation"], f.generation)
        f.life._save(f.admission, phase="DEVELOP")
        f.conductor._develop(f.admission, f.generation)
        f.conductor._review(f.admission, f.generation)
        with self.assertRaisesRegex(ADPError, "UNSUPPORTED_CURRENT_CONTEXT_REAPPROVAL"):
            f.life.before_handoff()

    def test_manual_and_draft_readiness_wait_without_authority_inference(self):
        f = self.fixture(attach=True)
        f.merge_mode = "MANUAL"
        f.conductor._cycle(f.admission, f.generation)
        self.assertEqual(len(f.server.pulls), 1)
        self.assertTrue(f.server.pulls[0]["draft"])
        f.conductor._cycle(f.admission, f.generation)
        self.assertFalse(any(method == "PUT" for method, _, _ in f.server.calls))
        self.assertNotEqual(f.conductor._task(f.admission)["stage"], "COMPLETE")

    def test_delegated_merge_and_one_product_outcome_reuse_accepted_ports(self):
        f = self.fixture(attach=True)
        f.conductor._cycle(f.admission, f.generation)
        self.assertEqual(len(f.server.pulls), 1)
        f.server.pulls[0]["draft"] = False  # explicit independent external actor
        for _ in range(3):
            f.conductor._cycle(f.admission, f.generation)
            if f.conductor._task(f.admission)["stage"] == "COMPLETE":
                break
        self.assertEqual(f.conductor._task(f.admission)["stage"], "COMPLETE")
        self.assertEqual(len(f.server.comments), 1)
        self.assertEqual(sum(method == "PUT" for method, _, _ in f.server.calls), 1)
        self.assertNotIn("fixture:", f.server.comments[0]["body"])

    def test_ordinary_correction_keeps_original_scope_and_check_inventory(self):
        f = self.fixture(attach=True)
        f.check_status = ResultStatus.FAIL
        packet = f.life.packet()
        f.conductor._develop(f.admission, f.generation)
        self.assertEqual(f.life.packet(), packet)
        self.assertEqual(f.life.packet().checks, ("unit",))
        self.assertEqual(f.life.packet().allowed_paths, ("product.py",))
        self.assertEqual(f.life.record(f.admission)["gate"]["results"][0]["status"], "FAIL")
        self.assertIsNone(f.conductor._task(f.admission)["review"])


class TicketPublicationTests(Cases):
    def publication(self, f, *, changes=None):
        track = f.readiness.observe()
        original = f.scope.preparer.archive.original(f.scope.preparer.archive.frozen_reference(f.admission.identity))
        f.scope.preparer.policy = f.spec.policy_factory()
        inputs = f.assess(original, track, f.scope.preparer.policy.inspect_repository())
        changes = changes or (TicketChange("clarify", ChangeKind.CLARIFICATION, "TITLE", original.issue.title, "Clarified bounded ticket"),)
        proposal = replace(inputs.proposal, changes=changes)
        review = replace(inputs.review, evidence=None)
        review = replace(review, evidence=f.authority.grant(purpose="ticket/preparation",
            subject=preparation_subject(original, inputs.scope, proposal, review, track)))
        inputs = replace(inputs, proposal=proposal, review=review)
        server_request = f.server.request
        def request(method, path, body=None, *, seconds):
            base = "/repos/demo/project"
            if path.startswith(base + "/issues/") and not path.endswith("/comments"):
                f.server.calls.append((method, path, copy.deepcopy(body)))
                row = f.discovery.snapshot.issues[int(path.split("/issues/")[1].split("/")[0])-1]
                if method == "GET":
                    return Response(200, json.dumps({"node_id": row.identity.issue_id, "id": row.number + 100,
                        "number": row.number, "title": row.title, "body": row.body}).encode())
                if f.server.before_write:
                    callback, f.server.before_write = f.server.before_write, None
                    callback()
                if f.server.loss == "before":
                    f.server.loss = None
                    raise NetworkTransportError("synthetic lost before")
                if method == "PATCH":
                    updated = replace(row, **body, revision=digest({"before": row.revision, "body": body}))
                else:
                    dependency = f.discovery.snapshot.issues[1]
                    relation = Relation("BLOCKED_BY", Target("demo/project", dependency.number, dependency.identity.issue_id), "NATIVE", "fixture:native")
                    updated = replace(row, relations=(relation,) if method == "POST" else (),
                        revision=digest({"before": row.revision, "method": method}))
                f.discovery.snapshot = replace(f.discovery.snapshot, issues=tuple(updated if v.identity == row.identity else v for v in f.discovery.snapshot.issues))
                if f.server.loss == "after":
                    f.server.loss = None
                    raise NetworkTransportError("synthetic lost after")
                return Response(204, b'') if method == "DELETE" else Response(200, b'{}')
            return server_request(method, path, body, seconds=seconds)
        f.server.request = request
        return TicketPublisher(f.conductor, f.admission, f.service), inputs, track

    def test_ticket_preflight_requires_original_scope_independent_review_and_m3(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        invalid = replace(inputs, review=replace(inputs.review, evidence=None))
        with self.assertRaises(ADPError):
            publisher.publish(invalid, track=track, preparer=f.scope.preparer)
        class NotTheAcceptedProvider:
            def plan(self, *args):
                raise AssertionError("An unqualified provider must never evaluate an effect")
            def decide(self, *args):
                raise AssertionError("A stub ALLOW is not accepted M3 authority")
        f.conductor.projects["one"] = replace(f.conductor.projects["one"],
            policy_factory=lambda *args: NotTheAcceptedProvider())
        with self.assertRaisesRegex(ADPError, "Actual accepted M3 policy provider"):
            publisher.publish(inputs, track=track, preparer=f.scope.preparer)
        self.assertFalse(any(method == "PATCH" for method, _, _ in f.server.calls))

    def test_ticket_missing_edit_or_observed_version_assent_prevents_write(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        for denied in ("ticket/edit", "ticket/observed-version"):
            f.authority.denied = {denied}
            with self.assertRaises(AuthorityError):
                publisher.publish(inputs, track=track, preparer=f.scope.preparer)
        self.assertFalse(any(method == "PATCH" for method, _, _ in f.server.calls))
        wrong = TicketPublisher(f.conductor, replace(f.admission, task_id="alias"), f.service)
        with self.assertRaisesRegex(ADPError, "Publisher must bind"):
            AutonomousTrack(f.conductor, f.window, (replace(f.spec, ticket_publisher=wrong),))

    def test_ticket_stale_version_or_repository_prevents_first_effect(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        f.discovery.snapshot = replace(f.discovery.snapshot, issues=tuple(replace(v, revision="f" * 64) if v.identity == f.admission.identity else v for v in f.discovery.snapshot.issues))
        with self.assertRaises(ADPError):
            publisher.publish(inputs, track=track, preparer=f.scope.preparer)
        self.assertFalse(any(method == "PATCH" for method, _, _ in f.server.calls))

    def test_ticket_title_body_and_dependency_changes_preserve_scope(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        from adp.ticket_types import ScopeAdditionApproval
        from adp.ticket_preparation import addition_subject, change_digest
        original = f.scope.preparer.archive.original(inputs.scope.original_reference)
        dependency = f.discovery.snapshot.issues[1].identity
        body = TicketChange("body", ChangeKind.CLARIFICATION, "BODY", original.issue.body, original.issue.body + "\nExplanatory detail.")
        addition = TicketChange("particular-dependency", ChangeKind.ADDITION, "SCOPE", "", "Specifically approved prerequisite",
            added_clauses=(Clause("dep", "DEPENDENCY", "Specifically approved prerequisite"),), added_dependencies=(dependency,))
        proposal = replace(inputs.proposal, changes=(*inputs.proposal.changes, body, addition),
            parts=(replace(inputs.proposal.parts[0], clauses=(*inputs.proposal.parts[0].clauses, "dep")),))
        approval = ScopeAdditionApproval(addition.id, inputs.scope.original_reference, change_digest(addition), f.now, f.now + 300)
        approval = replace(approval, evidence=f.authority.grant(purpose="ticket/scope-addition", subject=addition_subject(approval)))
        review = replace(inputs.review, evidence=None)
        review = replace(review, evidence=f.authority.grant(purpose="ticket/preparation",
            subject=preparation_subject(original, inputs.scope, proposal, review, track)))
        inputs = replace(inputs, proposal=proposal, review=review, additions=(approval,))
        result = publisher.publish(inputs, track=track, preparer=f.scope.preparer,
            dependency_edits=(DependencyEdit(dependency, 102, True),))
        self.assertEqual(result, "PREPARING")
        self.assertEqual(f.discovery.snapshot.issues[0].title, "Clarified bounded ticket")
        self.assertEqual(f.discovery.snapshot.issues[0].body, body.after)
        self.assertTrue(any(r.kind == "BLOCKED_BY" and r.confidence == "NATIVE" for r in f.discovery.snapshot.issues[0].relations))
        self.assertEqual(f.scope.preparer.archive.original(inputs.scope.original_reference).issue.title, inputs.proposal.changes[0].before)
        self.assertEqual(sum(method == "PATCH" for method, _, _ in f.server.calls), 1)
        self.assertEqual(sum(method == "POST" for method, _, _ in f.server.calls), 1)
        self.assertEqual(f.runtime.dispatch_count, 0)
        g = self.fixture()
        row, prerequisite = g.discovery.snapshot.issues
        unwanted = Relation("BLOCKED_BY", Target("demo/project", prerequisite.number, prerequisite.identity.issue_id), "NATIVE", "fixture:external-drift")
        g.discovery.snapshot = replace(g.discovery.snapshot, issues=(replace(row, revision="e" * 64, relations=(unwanted,)), prerequisite))
        removal, inputs, track = self.publication(g)
        self.assertEqual(removal.publish(inputs, track=track, preparer=g.scope.preparer,
            dependency_edits=(DependencyEdit(prerequisite.identity, 102, False),)), "PREPARING")
        self.assertEqual(g.discovery.snapshot.issues[0].relations, ())
        self.assertEqual(sum(method == "DELETE" for method, _, _ in g.server.calls), 1)

    def test_ticket_partial_bundle_requires_fresh_complete_dag_before_code(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        f.server.loss = "before"
        self.assertEqual(publisher.publish(inputs, track=track, preparer=f.scope.preparer), "UNKNOWN")
        self.assertEqual(f.runtime.dispatch_count, 0)
        self.assertEqual(f.conductor._task(f.admission)["stage"], "DEVELOP")
        g = self.fixture()
        publisher, inputs, track = self.publication(g)
        g.server.before_write = lambda: setattr(g.guard, "clock", lambda: g.now + 301)
        self.assertEqual(publisher.publish(inputs, track=track, preparer=g.scope.preparer), "BLOCKED")
        effects = g.conductor.journal.inspect()["state"]["execution"]["ticket_effects"]
        effect = next(iter(effects.values()))
        self.assertEqual(effect["status"], "OBSERVED")
        self.assertEqual(g.guard.inspect(g.admission.task_id, effect["requirement"]).kind, DecisionKind.STOP_UNSAFE)
        with self.assertRaisesRegex(ADPError, "preparation guard"):
            g.conductor._admit(g.admission, g.readiness.observe(), g.generation)
        self.assertEqual(g.runtime.dispatch_count, 0)

    def test_ticket_lost_response_before_after_never_blindly_retries(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        f.server.loss = "after"
        self.assertEqual(publisher.publish(inputs, track=track, preparer=f.scope.preparer), "PREPARING")
        self.assertEqual(publisher.publish(inputs, track=track, preparer=f.scope.preparer), "PREPARING")
        self.assertEqual(sum(method == "PATCH" for method, _, _ in f.server.calls), 1)
        effects = f.conductor.journal.inspect()["state"]["execution"]["ticket_effects"]
        self.assertTrue(all(row["status"] == "OBSERVED" for row in effects.values()))

    def test_ticket_restart_and_generation_fences_preserve_intent(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        f.server.loss = "before"
        self.assertEqual(publisher.publish(inputs, track=track, preparer=f.scope.preparer), "UNKNOWN")
        self.assertEqual(publisher.publish(inputs, track=track, preparer=f.scope.preparer), "UNKNOWN")
        self.assertEqual(sum(method == "PATCH" for method, _, _ in f.server.calls), 1)
        with self.assertRaises(ADPError):
            f.conductor.handoff(authorized=True)
        with self.assertRaisesRegex(ADPError, "ticket effects"):
            f.memory.handoff()
        g = self.fixture()
        publisher, inputs, track = self.publication(g)
        spec = replace(g.spec, ticket_publisher=publisher)
        controller = AutonomousTrack(g.conductor, g.window, (spec,))
        controller._window(create=True)
        # Window checkpoint moves exact policy state; independently review the
        # current preparation context before the one publication.
        publisher, inputs, track = self.publication(g)
        self.assertEqual(publisher.publish(inputs, track=track, preparer=g.scope.preparer), "PREPARING")
        g.conductor.handoff(authorized=True)
        g.memory.claim("new-ticket-recovery-owner")
        fresh = AutonomousTrack(g.conductor, g.window, (spec,))
        fresh.adopt_generation(authorized=True)
        self.assertTrue(publisher.recover(preparer=g.scope.preparer))
        self.assertEqual(sum(method == "PATCH" for method, _, _ in g.server.calls), 1)

    def test_ticket_specific_scope_addition_needs_external_exact_approval(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        change = TicketChange("extra", ChangeKind.ADDITION, "SCOPE", "", "new behavior",
            added_clauses=(Clause("extra", "ACCEPTANCE", "new requirement"),))
        proposal = replace(inputs.proposal, changes=(*inputs.proposal.changes, change), parts=(replace(inputs.proposal.parts[0],
            clauses=(*inputs.proposal.parts[0].clauses, "extra")),))
        original = f.scope.preparer.archive.original(inputs.scope.original_reference)
        review = replace(inputs.review, evidence=None)
        review = replace(review, evidence=f.authority.grant(purpose="ticket/preparation",
            subject=preparation_subject(original, inputs.scope, proposal, review, track)))
        with self.assertRaisesRegex(ADPError, "scope-addition"):
            publisher.publish(replace(inputs, proposal=proposal, review=review), track=track, preparer=f.scope.preparer)
        self.assertEqual(f.runtime.dispatch_count, 0)

    def test_ticket_forbidden_routes_credentials_and_unrelated_writes_refuse(self):
        for method, path, body in (("POST", "/repos/demo/project/issues", {"title": "new"}),
            ("PATCH", "/repos/demo/project/issues/1", {"state": "closed"}),
            ("POST", "/repos/demo/project/issues/1/comments", {"body": "spam"}),
            ("DELETE", "/repos/demo/project", None), ("PATCH", "https://evil.invalid/issues/1", {"title": "bad"})):
            with self.assertRaises(ValueError):
                validate_request(method, path, body, 1)
        self.assertEqual(json.loads(validate_request("PATCH", "/repos/demo/project/issues/1", {"title": "clarified"}, 1)), {"title": "clarified"})
        from test_network_http import ScopeAuthority, scoped_record
        from adp.ticket_publication import GitHubTicketHTTPTransport
        # An otherwise authenticated contents-write token is not a ticket token.
        authority = ScopeAuthority()
        with self.assertRaises(ADPError):
            GitHubTicketHTTPTransport(scoped_record(authority), authority=authority, clock=lambda: 100)

    def test_ticket_observed_version_limit_and_atomic_policy_refusal_are_explicit(self):
        f = self.fixture()
        publisher, inputs, track = self.publication(f)
        publisher.envelope = "ATOMIC_VERSION"
        with self.assertRaisesRegex(ADPError, "no atomic"):
            publisher.publish(inputs, track=track, preparer=f.scope.preparer)
        self.assertFalse(any(method == "PATCH" for method, _, _ in f.server.calls))


if __name__ == "__main__":
    unittest.main()
