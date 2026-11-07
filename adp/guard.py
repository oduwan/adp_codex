"""Mandatory, durable Progress Guard boundary. Never executes a product action."""
from __future__ import annotations

import copy
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from typing import TypeVar

from .errors import ADPError, AuthorityError, Conflict
from .guard_schema import (COUNTERS, MAX_FACTS, action, campaign_spec, digest,
                           limits, observation, record, report, requirement_id,
                           strings)
from .guard_types import (Action, ActionKind, Attestation, Baseline, Campaign, CasePermit,
                          Classification, Decision, DecisionKind, EvidenceAuthority,
                          ForensicReport, ForensicRequest, Observation, Outcome, Permit, ProgressKind,
                          Requirement, data)
from .memory import Memory
from .schema import encode, integer, require, string
from .storage import locked

T = TypeVar("T")
BAD_OUTCOMES = {Outcome.FAIL, Outcome.ERROR, Outcome.TIMEOUT}


class GuardRefusal(Conflict):
    """A denied boundary operation carries its exact accepted baseline."""

    def __init__(self, decision: Decision):
        self.decision = decision
        super().__init__(decision.reason)


class ProgressGuard:
    """The owning Conductor persists every reservation and material observation.

    New guard data cannot be enabled implicitly. The external authority verifies
    operator admissions and independently supplied review evidence; no authority
    object means no authenticated progress/review/admission. It is never derived
    from issue text or a worker's claimed role. No public reset/override exists.
    """

    def __init__(self, memory: Memory, *, authority: EvidenceAuthority | None = None,
                 clock: Callable[[], int] | None = None):
        self.memory = memory
        self.authority = authority
        self.clock = clock or (lambda: int(time.time()))

    def _now(self) -> int:
        now = self.clock()
        integer(now)
        return now

    @staticmethod
    def _context(state: dict, task: dict) -> dict:
        return {"task_key": task["key"], "revision": task["source_revision"],
                "iteration": task["iteration"], "generation": state["generation"],
                "task_epoch": state["progress_guard"]["task_epochs"][task["key"]]}

    @staticmethod
    def _requirements(state: dict) -> dict:
        if state["schema_version"] != 2:
            raise AuthorityError("Explicit guard-upgrade is required; read-only inspection never migrates M1")
        return state["progress_guard"]["requirements"]

    @staticmethod
    def _get(state: dict, task: dict, identifier: str) -> dict:
        requirements = ProgressGuard._requirements(state)
        require(isinstance(identifier, str), "Invalid requirement identifier")
        if identifier not in requirements or task["key"] not in requirements[identifier]["tasks"]:
            raise AuthorityError("Task/requirement baseline has not been independently admitted")
        return requirements[identifier]

    @staticmethod
    def _baseline(identifier: str, state: dict, task: dict, item: dict) -> Baseline:
        return Baseline(identifier, item["contract"], item["gate"], task["key"],
                        task["source_revision"], task["iteration"], state["generation"],
                        state["progress_guard"]["task_epochs"][task["key"]], item["sequence"], digest(item), tuple(item["unresolved"]))

    def _decision(self, identifier: str, state: dict, task: dict, item: dict) -> Decision:
        kind = {"normal": DecisionKind.ALLOW, "forensic": DecisionKind.FORENSIC_REQUIRED,
                "ready": DecisionKind.ALLOW, "running": DecisionKind.FORENSIC_REQUIRED,
                "operator": DecisionKind.OPERATOR_DECISION_REQUIRED,
                "unsafe": DecisionKind.STOP_UNSAFE}[item["mode"]]
        reason = item["reason"]
        if item["active"] is not None:
            kind = DecisionKind.FORENSIC_REQUIRED
            reason = "Finish or explicitly abandon the reserved attempt; replacement workers cannot bypass it"
        campaign = item["campaign"]
        if campaign and campaign["stopped"] is None and None in campaign["results"]:
            kind = DecisionKind.FORENSIC_REQUIRED
            reason = "Only the authorized finite campaign may continue; ordinary attempts are blocked"
        if item["mode"] in ("unsafe", "operator"):
            kind = DecisionKind.STOP_UNSAFE if item["mode"] == "unsafe" else DecisionKind.OPERATOR_DECISION_REQUIRED
            reason = item["reason"]
        return Decision(kind, reason, self._baseline(identifier, state, task, item))

    def _snapshot(self, task_id: str, identifier: str) -> tuple[dict, dict, dict]:
        inspected = self.memory.inspect()
        if inspected["health"] != "SYNCED":
            raise Conflict("Guard needs a synchronized canonical checkpoint; inspect recovery")
        state = inspected["state"]
        task = self.memory._task(inspected["tasks"], task_id)
        return state, task, self._get(state, task, identifier)

    def inspect(self, task_id: str, identifier: str) -> Decision:
        """Read-only; freshness and approval are evaluated against the live task."""
        return self._decision(identifier, *self._snapshot(task_id, identifier))

    def _change(self, task_id: str, identifier: str,
                transition: Callable[[dict, dict, dict], T]) -> tuple[T, Decision]:
        with locked(self.memory.control):
            head, state, tasks = self.memory._start()
            task = self.memory._task(tasks, task_id)
            item = self._get(state, task, identifier)
            before = encode(item)
            value = transition(state, task, item)
            if encode(item) != before:
                item["sequence"] += 1
                record(item, identifier)
                self.memory._checkpoint(head, state, tasks)
            return value, self._decision(identifier, state, task, item)

    def _verify(self, evidence: Attestation | None, purpose: str, subject: str,
                *, authors: list[str] | None = None) -> None:
        if not isinstance(evidence, Attestation) or self.authority is None:
            raise AuthorityError("Independently supplied verified evidence is required")
        string(evidence.reviewer, 128)
        string(evidence.reference)
        require(evidence.subject == subject, "Review evidence does not bind the exact accepted baseline and payload")
        if authors and evidence.reviewer in authors:
            raise AuthorityError("The author cannot act as the independent reviewer")
        if self.authority.verify(evidence, purpose=purpose, subject=subject) is not True:
            raise AuthorityError("External evidence authority refused identity, role or provenance")

    def admission_subject(self, task_id: str, spec: Requirement) -> str:
        spec_data = data(spec)
        limits(spec_data["limits"])
        strings(spec_data["acceptance"], 16, 128, nonempty=True)
        strings(spec_data["dependencies"], 16, 128)
        inspected = self.memory.inspect()
        require(inspected["health"] == "SYNCED", "Admission requires synchronized memory")
        task = self.memory._task(inspected["tasks"], task_id)
        return digest({"repository": self.memory.config.identity,
                       "task_key": task["key"], "requirement": spec_data})

    def register(self, task_id: str, spec: Requirement, evidence: Attestation) -> str:
        identifier = requirement_id(spec.contract, spec.gate)
        subject = self.admission_subject(task_id, spec)
        self._verify(evidence, "admission", subject)
        with locked(self.memory.control):
            head, state, tasks = self.memory._start()
            task = self.memory._task(tasks, task_id)
            requirements = self._requirements(state)
            spec_data = data(spec)
            if identifier in requirements:
                item = requirements[identifier]
                for name in ("contract", "gate", "acceptance", "dependencies", "limits"):
                    require(item[name] == spec_data[name], "An accepted baseline/threshold cannot be changed or reset")
                if task["key"] in item["tasks"]:
                    return identifier
                item["tasks"] = sorted([*item["tasks"], task["key"]])
                item["sequence"] += 1
            else:
                item = {**spec_data, "tasks": [task["key"]], "sequence": 0,
                    "mode": "normal", "counters": {name: 0 for name in COUNTERS.split()},
                    "authors": [], "seen_facts": [], "cause": None,
                    "unresolved": list(spec.acceptance), "pending_dependencies": list(spec.dependencies),
                    "last": None, "last_event": None, "active": None, "forensic_round": 0, "request": None,
                    "plan": None, "approval": None, "campaign": None, "campaign_runs": 0,
                    "reason": "Admitted baseline; a bounded attempt may be reserved"}
                requirements[identifier] = item
            record(item, identifier)
            self.memory._checkpoint(head, state, tasks)
            return identifier

    @staticmethod
    def _terminal(item: dict, reason: str, *, unsafe: bool = False) -> None:
        item["mode"] = "unsafe" if unsafe else "operator"
        item["reason"] = reason

    @staticmethod
    def _threshold(item: dict) -> None:
        if item["mode"] != "normal":
            return
        for name, threshold in item["limits"].items():
            actual = item["counters"][name]
            # Two unfalsifiable exploratory proposals are tolerated; block #3.
            reached = actual > threshold if name == "explorations" else actual >= threshold
            if reached:
                item["mode"] = "forensic"
                item["reason"] = f"{name} threshold reached without independently established progress"
                return

    def begin(self, task_id: str, identifier: str, proposal: Action) -> Permit:
        proposed = data(proposal)
        action(proposed)
        def transition(state: dict, task: dict, item: dict) -> str | None:
            decision = self._decision(identifier, state, task, item)
            if decision.kind != DecisionKind.ALLOW:
                return None
            require(task["source_revision"] is not None, "An attempt requires an exact source revision")
            bounded = item["mode"] == "ready"
            if bounded:
                if item["request"]["context"] != self._context(state, task):
                    item["mode"] = "forensic"
                    item["request"] = None
                    item["plan"] = None
                    item["reason"] = "Reviewed source/generation changed; re-review before a bounded attempt"
                    return None
                plan = item["plan"]["report"]["plan"]
                require(proposal.hypothesis == plan["action"] and proposal.exit_criteria == plan["pass_means"],
                        "Bounded action must match the independently reviewed discriminating plan")
                require(all(proposed[k] <= plan[k] for k in ("seconds", "samples", "payload_bytes")),
                        "Reviewed action containment cannot be raised")
            elif proposal.kind == ActionKind.DIAGNOSTIC and proposal.exit_criteria is None:
                item["counters"]["explorations"] += 1
                self._threshold(item)
                if item["mode"] != "normal":
                    return None
            if proposal.actor not in item["authors"]:
                item["authors"].append(proposal.actor)
            now = self._now()
            token = digest({"baseline": asdict(self._baseline(identifier, state, task, item)), "action": proposed})
            item["active"] = {"id": token, "context": self._context(state, task), "action": proposed,
                              "bounded": bounded, "started": now, "deadline": now + proposal.seconds}
            if bounded:
                item["mode"] = "running"
            return token
        token, decision = self._change(task_id, identifier, transition)
        if token is None:
            raise GuardRefusal(decision)
        return Permit(token, Decision(DecisionKind.ALLOW, "One exact bounded reservation; no execution authority granted",
                                      decision.baseline))

    @staticmethod
    def _active(state: dict, task: dict, item: dict, token: str) -> dict:
        active = item["active"]
        if active is None or active["id"] != token:
            raise Conflict("Attempt token is absent, stale or already terminal")
        if active["context"] != ProgressGuard._context(state, task):
            raise Conflict("Attempt revision/generation changed; explicitly abandon it as incomplete")
        return active

    def progress_subject(self, task_id: str, identifier: str, permit: Permit, measured: Observation) -> str:
        state, task, item = self._snapshot(task_id, identifier)
        self._active(state, task, item, permit.token)
        observation(data(measured))
        return digest({"baseline": asdict(self._baseline(identifier, state, task, item)),
                       "permit": permit.token, "observation": data(measured)})

    def _progress(self, state: dict, task: dict, item: dict, measured: dict,
                  evidence: Attestation | None, subject: str) -> bool:
        proof = measured["progress"]
        if proof is None:
            require(measured["unresolved"] == item["unresolved"], "Acceptance cannot disappear without verified evidence")
            return False
        self._verify(evidence, "progress", subject, authors=item["authors"])
        kind = proof["kind"]
        identity = (proof["fact"] if kind in (ProgressKind.REQUIREMENT_VERIFIED, ProgressKind.DEPENDENCY_RESOLVED)
                    else task["source_revision"] if kind == ProgressKind.CORRECTION_APPROVED
                    else sorted(proof["evidence"]))
        fact = digest({"kind": kind, "identity": identity})
        require(fact not in item["seen_facts"], "Replayed evidence is not new progress")
        require(len(item["seen_facts"]) < MAX_FACTS, "Progress evidence capacity requires operator disposition")
        expected = list(item["unresolved"])
        kind = proof["kind"]
        if kind == ProgressKind.REQUIREMENT_VERIFIED:
            require(measured["outcome"] == Outcome.PASS and proof["fact"] in expected,
                    "Verification requires a newly satisfied admitted requirement and measured PASS")
            expected.remove(proof["fact"])
        elif kind == ProgressKind.DEPENDENCY_RESOLVED:
            require(proof["fact"] in item["pending_dependencies"], "Dependency was not admitted or already resolved")
            item["pending_dependencies"].remove(proof["fact"])
        elif kind == ProgressKind.CAUSE_NARROWED:
            require(proof["parent_cause"] == item["cause"] and proof["fact"] != item["cause"],
                    "Narrowing must extend the accepted cause chain")
            item["cause"] = proof["fact"]
        elif kind == ProgressKind.CORRECTION_APPROVED:
            require(measured["outcome"] == Outcome.PASS, "An independently approved correction requires measured PASS")
            item["approval"] = {"context": self._context(state, task), "reviewer": evidence.reviewer,
                                "reference": evidence.reference, "subject": subject}
        require(measured["unresolved"] == expected, "Unresolved acceptance set differs from proved transition")
        item["unresolved"] = expected
        item["seen_facts"].append(fact)
        return True

    @staticmethod
    def _account(item: dict, action_data: dict, measured: dict, meaningful: bool) -> None:
        if meaningful:
            item["counters"] = {name: 0 for name in COUNTERS.split()}
            item["forensic_round"] = 0
            item["request"] = None
            item["plan"] = None
            item["campaign_runs"] = 0
            item["mode"] = "normal"
            item["reason"] = "Independently established progress against the accepted baseline"
            return
        counters = item["counters"]
        counters["stalls"] += 1
        if measured["outcome"] in BAD_OUTCOMES:
            counters["failures"] += 1
        if action_data["kind"] == ActionKind.CORRECTION:
            counters["corrections"] += 1
        if measured["finding"] is not None:
            counters["reviews"] += 1

    def observe(self, task_id: str, identifier: str, permit: Permit,
                measured: Observation, *, evidence: Attestation | None = None) -> Decision:
        require(isinstance(measured, Observation), "Expected a typed guard observation")
        input_error = None
        try:
            supplied = data(measured)
            observation(supplied)
        except ADPError as exc:
            supplied = None
            input_error = exc
        def transition(state: dict, task: dict, item: dict) -> None:
            active = item["active"]
            if active is None or active["id"] != permit.token:
                raise Conflict("Attempt token is absent, stale or already terminal")
            now = self._now()
            risk = measured.risk if isinstance(measured.risk, str) and measured.risk in (
                "safety", "authority", "contamination", "containment") else None
            exceeded = any(type(getattr(measured, name)) is int and getattr(measured, name) > active["action"][budget]
                           for name, budget in (("elapsed_seconds", "seconds"), ("samples", "samples"),
                                                ("payload_bytes", "payload_bytes")))
            unsafe = risk is not None or now < active["started"] or now > active["deadline"] or exceeded
            if unsafe:
                # A reported hazard takes precedence over inadmissible progress
                # or ancillary malformed fields. Never leave a reusable permit.
                measured_data = copy.deepcopy(supplied) if supplied is not None else data(
                    Observation(Outcome.UNKNOWN, ("guard:invalid-payload-with-risk",), (), risk=risk or "containment"))
                measured_data["progress"] = None
                measured_data["unresolved"] = list(item["unresolved"])
                measured_data["risk"] = risk or "containment"
                meaningful = False
            else:
                self._active(state, task, item, permit.token)
                if input_error is not None:
                    raise input_error
                measured_data = supplied
                subject = digest({"baseline": asdict(self._baseline(identifier, state, task, item)),
                                  "permit": permit.token, "observation": measured_data})
                meaningful = self._progress(state, task, item, measured_data, evidence, subject)
            self._account(item, active["action"], measured_data, meaningful)
            item["last_event"] = "attempt"
            item["last"] = {"context": active["context"], "action": active["action"],
                            "observation": measured_data, "counters": copy.deepcopy(item["counters"])}
            item["active"] = None
            if unsafe:
                self._terminal(item, "Safety, authority, contamination or containment violation; operator disposition required", unsafe=True)
            elif active["bounded"] and not meaningful:
                if item["forensic_round"] >= 2:
                    self._terminal(item, "Both bounded proofs failed without narrowing; further exploration requires an operator decision")
                else:
                    item["mode"] = "forensic"
                    item["reason"] = "Bounded proof did not narrow uncertainty; one renewed independent reassessment remains"
                    item["request"] = None
                    item["plan"] = None
            else:
                self._threshold(item)
        _, decision = self._change(task_id, identifier, transition)
        return decision

    def abandon(self, task_id: str, identifier: str, *, evidence_reference: str) -> Decision:
        """Acknowledge interrupted/stale work as UNKNOWN; never silently retry it."""
        string(evidence_reference)
        def transition(state: dict, task: dict, item: dict) -> None:
            active = item["active"]
            require(active is not None, "There is no reserved attempt to abandon")
            expired = self._now() < active["started"] or self._now() > active["deadline"]
            measured = data(Observation(Outcome.UNKNOWN, (evidence_reference,), tuple(item["unresolved"])))
            self._account(item, active["action"], measured, False)
            item["last_event"] = "attempt"
            item["last"] = {"context": active["context"], "action": active["action"],
                            "observation": measured, "counters": copy.deepcopy(item["counters"])}
            item["active"] = None
            if expired:
                self._terminal(item, "An interrupted attempt exceeded containment; operator disposition required", unsafe=True)
            elif active["bounded"]:
                if item["forensic_round"] >= 2:
                    self._terminal(item, "Second bounded proof interrupted; operator decision required")
                else:
                    item["mode"] = "forensic"
                    item["reason"] = "Interrupted bounded proof needs the final independent reassessment"
                    item["request"] = None
                    item["plan"] = None
            else:
                self._threshold(item)
        _, decision = self._change(task_id, identifier, transition)
        return decision

    def request_forensic(self, task_id: str, identifier: str) -> ForensicRequest:
        def transition(state: dict, task: dict, item: dict) -> dict:
            if item["mode"] != "forensic" or item["active"] is not None:
                raise GuardRefusal(self._decision(identifier, state, task, item))
            campaign = item["campaign"]
            require(campaign is None or campaign["stopped"] is not None or None not in campaign["results"],
                    "Complete the finite campaign before independent reassessment")
            existing = item["request"]
            context = self._context(state, task)
            if existing is not None and existing["context"] == context:
                return copy.deepcopy(existing)
            if existing is None:
                require(item["forensic_round"] < 2, "No further forensic reassessment is permitted")
                item["forensic_round"] += 1
            baseline = digest(item)
            from_campaign = item["last_event"] == "campaign"
            refs = ([campaign["spec"]["evidence_reference"]] if from_campaign else
                    item["last"]["observation"]["evidence"] if item["last"] else ["guard:unfalsifiable-proposals"])
            observed = [outcome for outcome in campaign["results"] if outcome is not None] if from_campaign else []
            latest_context = campaign["context"] if from_campaign else item["last"]["context"] if item["last"] else context
            request = {"id": digest({"baseline": baseline, "context": context}),
                       "round": item["forensic_round"], "context": context, "baseline": baseline,
                       "excluded_authors": list(item["authors"]), "evidence": refs,
                       "contract": item["contract"], "gate": item["gate"], "unresolved": list(item["unresolved"]),
                       "counters": copy.deepcopy(item["counters"]),
                       "hypothesis": ("Finite campaign method: " + campaign["spec"]["inventory"][len(observed) - 1]
                                      if from_campaign else item["last"]["action"]["hypothesis"] if item["last"] else None),
                       "outcome": observed[-1] if from_campaign else item["last"]["observation"]["outcome"] if item["last"] else None,
                       "observation_context": copy.deepcopy(latest_context),
                       "cause": item["cause"], "reason": item["reason"]}
            item["request"] = request
            return copy.deepcopy(request)
        request, _ = self._change(task_id, identifier, transition)
        return request

    def forensic_subject(self, task_id: str, identifier: str, result: ForensicReport) -> str:
        _, _, item = self._snapshot(task_id, identifier)
        report(data(result))
        return digest({"request": item["request"], "report": data(result)})

    def accept_forensic(self, task_id: str, identifier: str, result: ForensicReport,
                        evidence: Attestation) -> Decision:
        result_data = data(result)
        report(result_data)
        def transition(state: dict, task: dict, item: dict) -> None:
            request = item["request"]
            require(item["mode"] == "forensic" and request is not None
                    and result.request_id == request["id"], "Forensic result is stale or unsolicited")
            require(request["context"] == self._context(state, task), "Forensic exact revision/generation changed")
            self._verify(evidence, "forensic", digest({"request": request, "report": result_data}),
                         authors=item["authors"])
            item["plan"] = {"report": result_data, "reviewer": evidence.reviewer,
                            "reference": evidence.reference}
            if result.classification in (Classification.SCOPE_MISMATCH, Classification.DEPENDENCY_DEFECT):
                self._terminal(item, "Independent finding requires the responsible owner/operator; no in-scope execution admitted")
            elif result.plan is None:
                self._terminal(item, "Independent review supplied no finite discriminating exit; operator decision required")
            else:
                item["mode"] = "ready"
                item["reason"] = "One independently reviewed bounded proof is available; uncertainty remains explicit"
        _, decision = self._change(task_id, identifier, transition)
        return decision

    def require_approval(self, task_id: str, identifier: str) -> Baseline:
        state, task, item = self._snapshot(task_id, identifier)
        decision = self._decision(identifier, state, task, item)
        if (decision.kind != DecisionKind.ALLOW or item["approval"] is None
                or item["approval"]["context"] != self._context(state, task)):
            raise GuardRefusal(Decision(DecisionKind.FORENSIC_REQUIRED,
                "Independent correction approval is absent or invalidated by source/generation change", decision.baseline))
        approval = item["approval"]
        self._verify(Attestation(approval["reviewer"], approval["reference"], approval["subject"]),
                     "progress", approval["subject"], authors=item["authors"])
        return decision.baseline

    def campaign_subject(self, task_id: str, identifier: str, spec: Campaign) -> str:
        state, task, item = self._snapshot(task_id, identifier)
        campaign_spec(data(spec))
        return digest({"baseline": asdict(self._baseline(identifier, state, task, item)), "campaign": data(spec)})

    def start_campaign(self, task_id: str, identifier: str, spec: Campaign,
                       evidence: Attestation) -> str:
        proposed = data(spec)
        campaign_spec(proposed)
        def transition(state: dict, task: dict, item: dict) -> str:
            if item["mode"] in ("unsafe", "operator", "ready", "running") or item["active"] is not None:
                raise GuardRefusal(self._decision(identifier, state, task, item))
            require(item["request"] is None, "Finish the outstanding forensic request before starting a campaign")
            require(item["campaign_runs"] == 0, "Another census without verified progress requires operator disposition")
            subject = digest({"baseline": asdict(self._baseline(identifier, state, task, item)), "campaign": proposed})
            self._verify(evidence, "campaign", subject)
            require(task["source_revision"] is not None, "Campaign requires an exact source revision")
            now = self._now()
            campaign = {"id": subject, "context": self._context(state, task), "spec": proposed,
                        "results": [None] * len(spec.inventory), "started": now, "deadline": now + spec.seconds,
                        "last_time": now, "samples": 0, "payload_bytes": 0, "stopped": None,
                        "active_case": None, "interruption": None}
            item["campaign"] = campaign
            item["campaign_runs"] = 1
            # Reserve the worst-case representation before admitting the survey.
            campaign["results"] = [Outcome.TIMEOUT] * len(spec.inventory)
            encode(state)
            campaign["results"] = [None] * len(spec.inventory)
            return subject
        token, _ = self._change(task_id, identifier, transition)
        return token

    def next_case(self, task_id: str, identifier: str, token: str) -> CasePermit:
        """Durably reserve exactly one next method before returning a case permit."""
        def transition(state: dict, task: dict, item: dict) -> dict | None:
            campaign = item["campaign"]
            require(campaign is not None and campaign["id"] == token, "Campaign token is stale")
            if item["mode"] in ("unsafe", "operator") or campaign["stopped"] is not None:
                return None
            if campaign["active_case"] is not None:
                return None
            if None not in campaign["results"]:
                raise Conflict("Campaign is complete")
            now = self._now()
            if (campaign["context"] != self._context(state, task) or now < campaign["last_time"]
                    or now > campaign["deadline"]):
                campaign["stopped"] = "stale source/generation, clock or deadline"
                self._terminal(item, "Campaign containment no longer holds", unsafe=True)
                return None
            index = campaign["results"].index(None)
            case_id = campaign["spec"]["inventory"][index]
            case = {"id": digest({"campaign": token, "index": index, "sequence": item["sequence"]}),
                    "case_id": case_id, "index": index, "started": now}
            campaign["active_case"] = case
            campaign["last_time"] = now
            return copy.deepcopy(case)
        case, decision = self._change(task_id, identifier, transition)
        if case is None:
            if decision.kind not in (DecisionKind.STOP_UNSAFE, DecisionKind.OPERATOR_DECISION_REQUIRED):
                decision = Decision(DecisionKind.FORENSIC_REQUIRED,
                    "Record or explicitly abandon the already reserved case before admitting another", decision.baseline, "campaign")
            raise GuardRefusal(decision)
        return CasePermit(case["id"], case["case_id"], Decision(DecisionKind.ALLOW,
            "Only this reserved method in the fixed campaign is admitted", decision.baseline, "campaign"))

    @staticmethod
    def _case(item: dict, token: str, permit: CasePermit) -> tuple[dict, dict]:
        campaign = item["campaign"]
        require(campaign is not None and campaign["id"] == token, "Campaign token is stale")
        if item["mode"] in ("unsafe", "operator") or campaign["stopped"] is not None:
            raise Conflict("Campaign is stopped")
        case = campaign["active_case"]
        if (not isinstance(permit, CasePermit) or case is None
                or case["id"] != permit.token or case["case_id"] != permit.case_id):
            raise Conflict("An exact durably reserved case permit is required")
        return campaign, case

    def record_case(self, task_id: str, identifier: str, token: str, permit: CasePermit,
                    outcome: Outcome, *, samples: int = 0, payload_bytes: int = 0,
                    risk: str | None = None) -> Decision:
        recognized_risk = risk if isinstance(risk, str) and risk in ("safety", "authority", "contamination", "containment") else None
        try:
            require(isinstance(outcome, str) and outcome in set(Outcome) - {Outcome.UNKNOWN}, "Invalid campaign measured outcome")
            integer(samples)
            integer(payload_bytes)
            if risk is not None:
                require(recognized_risk is not None, "Invalid campaign stop reason")
        except ADPError:
            if recognized_risk is None:
                raise
            # An explicit hazard is never discarded due to malformed ancillary
            # measurements. ERROR describes an invalid runner report, not PASS.
            outcome = outcome if isinstance(outcome, str) and outcome in set(Outcome) - {Outcome.UNKNOWN} else Outcome.ERROR
            samples = samples if type(samples) is int and 0 <= samples < 10**18 else 0
            payload_bytes = payload_bytes if type(payload_bytes) is int and 0 <= payload_bytes < 10**18 else 0
            risk = recognized_risk
        def transition(state: dict, task: dict, item: dict) -> None:
            campaign, case = self._case(item, token, permit)
            index = case["index"]
            now = self._now()
            stale = campaign["context"] != self._context(state, task)
            exceeded = (now < campaign["last_time"] or now > campaign["deadline"]
                        or campaign["samples"] + samples > campaign["spec"]["samples"]
                        or campaign["payload_bytes"] + payload_bytes > campaign["spec"]["payload_bytes"])
            campaign["results"][index] = outcome
            campaign["active_case"] = None
            campaign["last_time"] = now
            campaign["samples"] += samples
            campaign["payload_bytes"] += payload_bytes
            measured = data(Observation(Outcome(outcome), (campaign["spec"]["evidence_reference"],), tuple(item["unresolved"])))
            self._account(item, {"kind": ActionKind.CHECK}, measured, False)
            item["last_event"] = "campaign"
            if stale or exceeded or risk is not None:
                campaign["stopped"] = "stale revision/generation" if stale else risk or "containment"
                self._terminal(item, "Campaign stopped for a real safety, contamination or containment constraint", unsafe=True)
            else:
                self._threshold(item)
        _, decision = self._change(task_id, identifier, transition)
        state, task, item = self._snapshot(task_id, identifier)
        campaign = item["campaign"]
        if campaign["stopped"] is None and None in campaign["results"]:
            return Decision(DecisionKind.ALLOW, "Only another durably reserved remaining case may proceed", decision.baseline, "campaign")
        return decision

    def abandon_case(self, task_id: str, identifier: str, token: str, permit: CasePermit,
                     *, evidence_reference: str) -> Decision:
        """Acknowledge a lost runner result as ERROR and stop the affected census."""
        string(evidence_reference)
        def transition(state: dict, task: dict, item: dict) -> None:
            campaign, case = self._case(item, token, permit)
            campaign["results"][case["index"]] = Outcome.ERROR
            campaign["active_case"] = None
            campaign["interruption"] = {"case_id": case["case_id"], "evidence": evidence_reference}
            campaign["stopped"] = "interrupted case; runner outcome unavailable"
            measured = data(Observation(Outcome.ERROR, (evidence_reference,), tuple(item["unresolved"])))
            self._account(item, {"kind": ActionKind.CHECK}, measured, False)
            item["last_event"] = "campaign"
            self._terminal(item, "Interrupted in-flight method needs operator disposition; no method PASS is inferred", unsafe=True)
        _, decision = self._change(task_id, identifier, transition)
        return decision

    def campaign_summary(self, task_id: str, identifier: str) -> dict:
        _, _, item = self._snapshot(task_id, identifier)
        campaign = item["campaign"]
        require(campaign is not None, "No campaign has been admitted")
        inventory = campaign["spec"]["inventory"]
        quarantined = set(campaign["spec"]["quarantined"])
        results = [outcome or Outcome.NOTRUN for outcome in campaign["results"]]
        raw = Counter(results)
        effective = Counter(outcome for case, outcome in zip(inventory, results) if case not in quarantined)
        counts = {outcome.value: effective[outcome] for outcome in Outcome if outcome != Outcome.UNKNOWN}
        counts["QUARANTINED"] = len(quarantined)
        return {"original_denominator": len(inventory), "inventory_digest": digest({"inventory": inventory}),
                "counts": counts, "raw_counts": {outcome.value: raw[outcome] for outcome in Outcome if outcome != Outcome.UNKNOWN},
                "observed": sum(outcome is not None for outcome in campaign["results"]),
                "attempted": sum(outcome not in (Outcome.SKIP, Outcome.NOTRUN) for outcome in results),
                "complete": None not in campaign["results"], "stopped": campaign["stopped"],
                "all_observed_pass": campaign["stopped"] is None and not quarantined and all(outcome == Outcome.PASS for outcome in results),
                "formal_acceptance": False}
