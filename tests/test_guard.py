"""Table-driven synthetic boundary tests; real Git integration is separate."""
from __future__ import annotations

import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from adp.config import load_json
from adp.errors import ADPError, AuthorityError, Conflict
from adp.guard import GuardRefusal, ProgressGuard
from adp.guard_schema import digest, requirement_id
from adp.guard_types import (Action, ActionKind, Attestation, Campaign, Classification,
    DecisionKind, ForensicPlan, ForensicReport, Limits, Observation, Outcome,
    Progress, ProgressKind, Requirement)
from adp.memory import Memory
from adp.schema import MAX_JOURNAL, bundle, encode, key
from adp.storage import atomic


class SyntheticAuthority:
    """Out-of-band fixture roster, never a self-assertion accepted by the guard."""
    def __init__(self):
        self.accepted = set()

    def attest(self, subject, purpose, reviewer=None):
        reviewer = reviewer or ("operator" if purpose in ("admission", "campaign") else "independent-reviewer")
        result = Attestation(reviewer, "fixture:verified-" + purpose, subject)
        self.accepted.add((result, purpose))
        return result

    def verify(self, evidence, *, purpose, subject):
        return evidence.subject == subject and (evidence, purpose) in self.accepted


class Checkpoints:
    """Fast JSON checkpoint fixture; production Memory is tested with two clones.

    Reopening this fixture rereads the actual persisted state. It validates the
    real closed schema and writes through the same atomic file primitive.
    """
    def __init__(self, path):
        self.control = path / "control"
        self.path = path
        self.config = SimpleNamespace(identity="synthetic:repository")
        self.file = path / "checkpoint.json"
        path.mkdir(parents=True, exist_ok=True)
        if not self.file.exists():
            task = self.make_task("task-A")
            state = {"schema_version": 2, "repository_id": self.config.identity,
                     "revision": 1, "generation": 1, "owner": {"id": "owner", "label": "fixture", "token_hash": "a" * 64},
                     "task_keys": [task["key"]], "assignment_sequence": 0,
                     "progress_guard": {"schema_version": 1, "requirements": {}, "task_epochs": {task["key"]: 1}}}
            atomic(self.file, encode({"state": state, "tasks": {task["key"]: task}}, MAX_JOURNAL))

    def make_task(self, identifier):
        return {"schema_version": 1, "key": key(identifier), "id": identifier,
                "repository_id": self.config.identity, "iteration": 1, "phase": "active",
                "source_revision": "a" * 40, "assignments": {}, "blockers": [], "last_published_iteration": None}

    def inspect(self):
        content = load_json(self.file, MAX_JOURNAL)
        bundle(content["state"], content["tasks"], self.config.identity)
        return {"health": "SYNCED", **content}

    _task = staticmethod(Memory._task)

    def _start(self):
        inspected = self.inspect()
        return "b" * 40, inspected["state"], inspected["tasks"]

    def _checkpoint(self, head, state, tasks):
        state["revision"] += 1
        state["task_keys"] = sorted(tasks)
        epochs = state["progress_guard"]["task_epochs"]
        state["progress_guard"]["task_epochs"] = {
            task_key: epochs.get(task_key, state["revision"]) for task_key in tasks}
        bundle(state, tasks, self.config.identity)
        atomic(self.file, encode({"state": state, "tasks": tasks}, MAX_JOURNAL))
        return self.inspect()

    def mutate_task(self, identifier, *, revision=None, generation=None, add=False):
        _, state, tasks = self._start()
        if add:
            tasks[key(identifier)] = self.make_task(identifier)
        if revision:
            tasks[key(identifier)]["source_revision"] = revision
            tasks[key(identifier)]["iteration"] += 1
        if generation:
            state["generation"] = generation
        self._checkpoint(None, state, tasks)


class GuardFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="adp-guard-")
        self.addCleanup(self.temp.cleanup)
        self.now = 100
        self.authority = SyntheticAuthority()
        self.memory = Checkpoints(Path(self.temp.name) / "memory")
        self.guard = ProgressGuard(self.memory, authority=self.authority, clock=lambda: self.now)
        self.spec = Requirement("contract:accepted-digest", "gate:stable", ("criterion-A", "criterion-B"), ("dependency-A",))
        self.identifier = self.register(self.spec)

    def register(self, spec, task="task-A"):
        subject = self.guard.admission_subject(task, spec)
        return self.guard.register(task, spec, self.authority.attest(subject, "admission"))

    def counters(self):
        return self.memory.inspect()["state"]["progress_guard"]["requirements"][self.identifier]["counters"]

    def item(self):
        return self.memory.inspect()["state"]["progress_guard"]["requirements"][self.identifier]

    def run_attempt(self, *, outcome=Outcome.FAIL, kind=ActionKind.CHECK, finding=None,
                    actor="author-A", hypothesis="hypothesis-A", task="task-A", exit_criteria="falsifiable exit"):
        permit = self.guard.begin(task, self.identifier, Action(actor, kind, hypothesis, exit_criteria))
        measured = Observation(outcome, ("fixture:measurement",), tuple(self.item()["unresolved"]), finding=finding)
        return self.guard.observe(task, self.identifier, permit, measured)

    def stall(self):
        for _ in range(3):
            self.run_attempt()
        self.assertEqual(self.guard.inspect("task-A", self.identifier).kind, DecisionKind.FORENSIC_REQUIRED)

    def review(self, classification=Classification.UNCLASSIFIED, *, finite=True, reviewer=None):
        request = self.guard.request_forensic("task-A", self.identifier)
        plan = ForensicPlan("one discriminating question", "specific positive observation", "specific negative observation",
                            "uncertainty retained", ("safety risk", "deadline")) if finite else None
        result = ForensicReport(request["id"], classification, ("fixture:independent-positive-evidence",), "bounded independent diagnosis", plan)
        subject = self.guard.forensic_subject("task-A", self.identifier, result)
        decision = self.guard.accept_forensic("task-A", self.identifier, result,
            self.authority.attest(subject, "forensic", reviewer))
        return result, decision

    def bounded(self, plan):
        return self.guard.begin("task-A", self.identifier,
            Action("author-A", ActionKind.DIAGNOSTIC, plan.action, plan.pass_means))


class ThresholdTests(GuardFixture):
    def test_failure_trigger_survives_new_hypothesis_actor_and_restart(self):
        self.run_attempt(hypothesis="original", actor="author-A")
        self.run_attempt(hypothesis="cosmetically renamed", actor="author-B")
        self.memory = Checkpoints(self.memory.path)
        self.guard = ProgressGuard(self.memory, authority=self.authority, clock=lambda: self.now)
        decision = self.run_attempt(hypothesis="another alias", actor="author-C")
        self.assertEqual(decision.kind, DecisionKind.FORENSIC_REQUIRED)
        self.assertEqual(self.counters()["failures"], 3)
        with self.assertRaises(GuardRefusal):
            self.run_attempt(actor="replacement-worker")

    def test_each_other_threshold_is_enforced(self):
        cases = [(ActionKind.CORRECTION, Outcome.UNKNOWN, None, "exit", 2, "corrections"),
                 (ActionKind.DIAGNOSTIC, Outcome.PASS, None, None, 3, "explorations"),
                 (ActionKind.REVIEW, Outcome.UNKNOWN, "same-finding", "exit", 3, "reviews"),
                 (ActionKind.CHECK, Outcome.PASS, None, "exit", 3, "stalls")]
        for index, (kind, outcome, finding, exit_criteria, threshold, counter) in enumerate(cases):
            with self.subTest(counter=counter):
                self.identifier = self.register(replace(self.spec, gate=f"gate:{index}"))
                for _ in range(threshold - 1):
                    self.assertEqual(self.run_attempt(kind=kind, outcome=outcome, finding=finding,
                        exit_criteria=exit_criteria).kind, DecisionKind.ALLOW)
                if counter == "explorations":
                    with self.assertRaises(GuardRefusal) as refused:
                        self.run_attempt(kind=kind, outcome=outcome, exit_criteria=exit_criteria)
                    decision = refused.exception.decision
                else:
                    decision = self.run_attempt(kind=kind, outcome=outcome, finding=finding, exit_criteria=exit_criteria)
                self.assertEqual(decision.kind, DecisionKind.FORENSIC_REQUIRED)
                self.assertEqual(self.counters()[counter], threshold)

    def test_alias_binding_and_reregistration_do_not_reset(self):
        self.run_attempt()
        self.run_attempt()
        self.memory.mutate_task("renamed-task", add=True)
        self.assertEqual(self.register(self.spec, "renamed-task"), self.identifier)
        self.assertEqual(self.counters()["failures"], 2)
        decision = self.run_attempt(task="renamed-task", actor="new-worker", hypothesis="new fixture text")
        self.assertEqual(decision.kind, DecisionKind.FORENSIC_REQUIRED)
        self.register(self.spec)
        self.assertEqual(self.counters()["failures"], 3)

    def test_thresholds_and_accepted_contract_cannot_be_relaxed(self):
        for invalid in (Limits(failures=4), Limits(corrections=3), Limits(explorations=3), Limits(reviews=4), Limits(stalls=4)):
            with self.subTest(limits=invalid), self.assertRaises(ADPError):
                self.register(replace(self.spec, limits=invalid))
        with self.assertRaises(ADPError):
            self.register(replace(self.spec, acceptance=("new-alias",)))
        subject = self.guard.admission_subject("task-A", replace(self.spec, gate="new-alias"))
        forged = Attestation("operator", "unverified assertion", subject)
        with self.assertRaises(AuthorityError):
            self.guard.register("task-A", replace(self.spec, gate="new-alias"), forged)
        self.identifier = self.register(replace(self.spec, gate="stricter", limits=Limits(failures=2)))
        self.run_attempt()
        self.assertEqual(self.run_attempt().kind, DecisionKind.FORENSIC_REQUIRED)

    def test_reservation_prevents_alternate_worker_or_duplicate_terminal_result(self):
        permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "hypothesis"))
        with self.assertRaises(GuardRefusal):
            self.guard.begin("task-A", self.identifier, Action("author-B", ActionKind.CHECK, "alias"))
        observed = Observation(Outcome.FAIL, ("fixture:one",), self.spec.acceptance)
        self.guard.observe("task-A", self.identifier, permit, observed)
        with self.assertRaises(Conflict):
            self.guard.observe("task-A", self.identifier, permit, observed)


class ProgressEvidenceTests(GuardFixture):
    def test_each_meaningful_progress_kind_resets_on_positive_evidence(self):
        cases = [(ProgressKind.CAUSE_NARROWED, "cause-1", Outcome.FAIL, self.spec.acceptance),
                 (ProgressKind.REQUIREMENT_VERIFIED, "criterion-A", Outcome.PASS, ("criterion-B",)),
                 (ProgressKind.DEPENDENCY_RESOLVED, "dependency-A", Outcome.UNKNOWN, self.spec.acceptance),
                 (ProgressKind.CORRECTION_APPROVED, "correction-1", Outcome.PASS, self.spec.acceptance)]
        for index, (kind, fact, outcome, unresolved) in enumerate(cases):
            with self.subTest(kind=kind):
                self.identifier = self.register(replace(self.spec, gate=f"meaningful:{index}"))
                self.run_attempt()
                self.run_attempt()
                permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "new proof"))
                measured = Observation(outcome, ("fixture:measurement",), unresolved,
                    Progress(kind, fact, (f"fixture:verified-{index}",)))
                subject = self.guard.progress_subject("task-A", self.identifier, permit, measured)
                evidence = self.authority.attest(subject, "progress")
                decision = self.guard.observe("task-A", self.identifier, permit, measured, evidence=evidence)
                self.assertEqual(decision.kind, DecisionKind.ALLOW)
                self.assertEqual(set(self.counters().values()), {0})

    def test_unverified_cosmetic_and_replayed_facts_cannot_reset(self):
        self.run_attempt()
        permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "proof"))
        proof = Progress(ProgressKind.CAUSE_NARROWED, "cause-1", ("fixture:root-cause",))
        measured = Observation(Outcome.FAIL, ("fixture:measured",), self.spec.acceptance, proof)
        before = self.memory.inspect()
        with self.assertRaises(AuthorityError):
            self.guard.observe("task-A", self.identifier, permit, measured)
        self.assertEqual(before, self.memory.inspect())
        subject = self.guard.progress_subject("task-A", self.identifier, permit, measured)
        self.guard.observe("task-A", self.identifier, permit, measured,
                           evidence=self.authority.attest(subject, "progress"))
        self.run_attempt(hypothesis="fixture text changed")
        self.run_attempt(hypothesis="more raw logs exist")
        permit = self.guard.begin("task-A", self.identifier, Action("author-B", ActionKind.CHECK, "renamed same fact"))
        renamed = replace(measured, progress=replace(proof, fact="alias", parent_cause="cause-1"))
        subject = self.guard.progress_subject("task-A", self.identifier, permit, renamed)
        with self.assertRaisesRegex(ADPError, "Replayed"):
            self.guard.observe("task-A", self.identifier, permit, renamed,
                               evidence=self.authority.attest(subject, "progress"))
        decision = self.guard.observe("task-A", self.identifier, permit, replace(renamed, progress=None))
        self.assertEqual(decision.kind, DecisionKind.FORENSIC_REQUIRED)

    def test_acceptance_drop_and_self_review_are_refused(self):
        permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "proof"))
        with self.assertRaises(ADPError):
            self.guard.observe("task-A", self.identifier, permit, Observation(Outcome.PASS, ("fixture:unproved",), ()))
        measured = Observation(Outcome.PASS, ("fixture:measured",), self.spec.acceptance,
            Progress(ProgressKind.CORRECTION_APPROVED, "fix", ("fixture:review",)))
        subject = self.guard.progress_subject("task-A", self.identifier, permit, measured)
        with self.assertRaises(AuthorityError):
            self.guard.observe("task-A", self.identifier, permit, measured,
                evidence=self.authority.attest(subject, "progress", "author-A"))
        self.guard.observe("task-A", self.identifier, permit, measured,
                           evidence=self.authority.attest(subject, "progress"))
        self.guard.require_approval("task-A", self.identifier)
        self.memory.mutate_task("task-A", revision="b" * 40)
        with self.assertRaises(GuardRefusal):
            self.guard.require_approval("task-A", self.identifier)
        self.memory.mutate_task("task-A", revision="a" * 40)
        with self.assertRaises(GuardRefusal):
            self.guard.require_approval("task-A", self.identifier)

    def test_generation_drift_requires_explicit_unknown_abandonment(self):
        permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "pending"))
        self.memory.mutate_task("task-A", generation=2)
        with self.assertRaises(Conflict):
            self.guard.observe("task-A", self.identifier, permit, Observation(Outcome.PASS, ("fixture:stale",), self.spec.acceptance))
        with self.assertRaises(GuardRefusal):
            self.run_attempt(actor="new-conductor")
        self.guard.abandon("task-A", self.identifier, evidence_reference="fixture:lost-environment")
        self.assertEqual(self.item()["last"]["observation"]["outcome"], Outcome.UNKNOWN)
        self.assertEqual(self.counters()["stalls"], 1)

    def test_persisted_approval_cannot_self_certify_a_new_authority_context(self):
        permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "review"))
        measured = Observation(Outcome.PASS, ("fixture:observation",), self.spec.acceptance,
            Progress(ProgressKind.CORRECTION_APPROVED, "fix", ("fixture:independent",)))
        subject = self.guard.progress_subject("task-A", self.identifier, permit, measured)
        self.guard.observe("task-A", self.identifier, permit, measured,
            evidence=self.authority.attest(subject, "progress"))
        self.guard.require_approval("task-A", self.identifier)
        unauthenticated = ProgressGuard(self.memory, clock=lambda: self.now)
        with self.assertRaises(AuthorityError):
            unauthenticated.require_approval("task-A", self.identifier)



class ForensicTests(GuardFixture):
    def test_two_bounded_proofs_then_terminal_operator_boundary(self):
        self.stall()
        for round_number in (1, 2):
            result, decision = self.review()
            self.assertEqual(self.item()["forensic_round"], round_number)
            self.assertEqual(decision.kind, DecisionKind.ALLOW)
            self.assertEqual(self.item()["plan"]["report"]["classification"], Classification.UNCLASSIFIED)
            permit = self.bounded(result.plan)
            with self.assertRaises(GuardRefusal):
                self.bounded(result.plan)
            decision = self.guard.observe("task-A", self.identifier, permit,
                Observation(Outcome.UNKNOWN, ("fixture:no-narrowing",), self.spec.acceptance))
            expected = DecisionKind.FORENSIC_REQUIRED if round_number == 1 else DecisionKind.OPERATOR_DECISION_REQUIRED
            self.assertEqual(decision.kind, expected)
        with self.assertRaises(GuardRefusal) as denied:
            self.run_attempt(actor="new-worker")
        self.assertEqual(denied.exception.decision.kind, DecisionKind.OPERATOR_DECISION_REQUIRED)
        with self.assertRaises(GuardRefusal):
            self.guard.request_forensic("task-A", self.identifier)
        self.register(self.spec)
        self.assertEqual(self.guard.inspect("task-A", self.identifier).kind, DecisionKind.OPERATOR_DECISION_REQUIRED)

    def test_each_classification_and_positive_corruption_evidence(self):
        for index, classification in enumerate(Classification):
            with self.subTest(classification=classification):
                self.identifier = self.register(replace(self.spec, gate=f"classify:{index}"))
                self.stall()
                result, decision = self.review(classification)
                expected = (DecisionKind.OPERATOR_DECISION_REQUIRED if classification in
                    (Classification.SCOPE_MISMATCH, Classification.DEPENDENCY_DEFECT) else DecisionKind.ALLOW)
                self.assertEqual(decision.kind, expected)
                self.assertNotEqual(self.item()["last"]["observation"]["outcome"], Outcome.PASS)
                if classification == Classification.TEST_CORRUPTED:
                    with self.assertRaises(ADPError):
                        self.guard.forensic_subject("task-A", self.identifier, replace(result, evidence=()))

    def test_no_plan_self_attestation_and_stale_review_are_refused(self):
        self.stall()
        with self.assertRaises(AuthorityError):
            self.review(reviewer="author-A")
        request = self.guard.request_forensic("task-A", self.identifier)
        result = ForensicReport(request["id"], Classification.TEST_CORRUPTED, ("fixture:positive-proof",), "fixture defect")
        subject = self.guard.forensic_subject("task-A", self.identifier, result)
        with self.assertRaises(AuthorityError):
            self.guard.accept_forensic("task-A", self.identifier, result, Attestation("reviewer", "self-asserted", subject))
        self.memory.mutate_task("task-A", revision="b" * 40)
        with self.assertRaises(ADPError):
            self.guard.accept_forensic("task-A", self.identifier, result, self.authority.attest(subject, "forensic"))
        _, decision = self.review(finite=False)
        self.assertEqual(decision.kind, DecisionKind.OPERATOR_DECISION_REQUIRED)

    def test_bounded_plan_cannot_widen_or_survive_source_change(self):
        self.stall()
        result, _ = self.review(Classification.PRODUCT_DEFECT)
        with self.assertRaises(ADPError):
            self.guard.begin("task-A", self.identifier,
                Action("author-A", ActionKind.DIAGNOSTIC, result.plan.action, result.plan.pass_means, samples=1001))
        self.memory.mutate_task("task-A", revision="b" * 40)
        with self.assertRaises(GuardRefusal):
            self.bounded(result.plan)
        self.assertEqual(self.guard.inspect("task-A", self.identifier).kind, DecisionKind.FORENSIC_REQUIRED)

    def test_safety_and_expired_abandonment_cannot_be_reset(self):
        for index, risk in enumerate(("safety", "authority", "contamination", "containment", None)):
            with self.subTest(risk=risk):
                self.identifier = self.register(replace(self.spec, gate=f"risk:{index}"))
                permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "hypothesis"))
                if risk is None:
                    self.now += 301
                    decision = self.guard.abandon("task-A", self.identifier, evidence_reference="fixture:interrupted")
                else:
                    decision = self.guard.observe("task-A", self.identifier, permit,
                        Observation(Outcome.ERROR, ("fixture:risk",), self.spec.acceptance, risk=risk))
                self.assertEqual(decision.kind, DecisionKind.STOP_UNSAFE)
                with self.assertRaises(GuardRefusal):
                    self.run_attempt()

    def test_reported_risk_latches_even_with_progress_or_invalid_ancillary_fields(self):
        cases = [dict(risk="safety"), dict(risk="contamination"), dict(samples=1001), dict(elapsed_seconds=301)]
        for index, hazard in enumerate(cases):
            self.identifier = self.register(replace(self.spec, gate=f"hazard-progress:{index}"))
            permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "risk with a claim"))
            measured = Observation(Outcome.PASS, ("fixture:reported-hazard",), (),
                Progress(ProgressKind.CORRECTION_APPROVED, "unsafe-fix", ("fixture:claim",)), **hazard)
            decision = self.guard.observe("task-A", self.identifier, permit, measured)
            self.assertEqual(decision.kind, DecisionKind.STOP_UNSAFE)
            self.assertEqual(self.item()["unresolved"], list(self.spec.acceptance))
            self.assertEqual(self.item()["seen_facts"], [])
            with self.assertRaises(Conflict):
                self.guard.observe("task-A", self.identifier, permit,
                    Observation(Outcome.PASS, ("fixture:resubmission",), self.spec.acceptance))
            with self.assertRaises(GuardRefusal):
                self.run_attempt()
        self.identifier = self.register(replace(self.spec, gate="malformed-hazard"))
        permit = self.guard.begin("task-A", self.identifier, Action("author-A", ActionKind.CHECK, "malformed hazard"))
        malformed = Observation(Outcome.PASS, (), (), progress=Progress(ProgressKind.CAUSE_NARROWED, "bad", ()), risk="safety")
        self.assertEqual(self.guard.observe("task-A", self.identifier, permit, malformed).kind, DecisionKind.STOP_UNSAFE)

    def test_impossible_ready_and_running_records_are_controlled_refusals(self):
        original = self.memory.inspect()
        for mode in ("ready", "running"):
            state = copy.deepcopy(original["state"])
            state["progress_guard"]["requirements"][self.identifier]["mode"] = mode
            with self.subTest(mode=mode), self.assertRaises(ADPError):
                bundle(state, original["tasks"], self.memory.config.identity)
