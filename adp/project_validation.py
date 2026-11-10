"""Finite, authenticated project validation evidence, separate from execution.

The local journal is private observation/request bookkeeping, not canonical M1
memory or a replacement for its owner and the caller's mandatory M2 reservation.
No test command, CI workflow, runner, cancellation or GitHub mutation is defined.
"""
from __future__ import annotations

import os
import secrets
import stat
import time
from dataclasses import replace
from pathlib import Path

from .config import load_json, safe_path
from .discovery_schema import typed
from .errors import ADPError
from .execution_privacy import credential_shaped
from .guard_types import Attestation, data
from .policy_schema import digest, fingerprint, fresh, ref, sha
from .policy_types import Authorization, Effect, Operation, OutcomeCount, Request, CandidateSource, CandidateValidationRequest
from .project_validation_types import (EvidenceGate, EvidencePolicy, EvidenceRequest,
    ObservationQuery, Phase, ProjectObservation, ProjectResult, RequiredCheck, ResultStatus,
    CandidateEvidenceRequest, CandidateObservationQuery, CandidateProjectResult,
    CandidateProjectObservation, CandidateEvidenceGate)
from .schema import encode, fields, integer, require, string
from .storage import atomic, locked

COUNTS = {"PASS", "FAIL", "ERROR", "TIMEOUT", "SKIP", "NOTRUN", "UNKNOWN"}
COVERAGE = {"COMPLETE", "PARTIAL", "UNKNOWN", "RATE_LIMITED", "FORBIDDEN", "CHANGED"}


def _public(value: str, maximum: int = 256) -> None:
    string(value, maximum)
    require(not credential_shaped(value), "Sensitive validation identifier refused")


def policy_subject(plan, policy: EvidencePolicy) -> str:
    require(type(policy) is EvidencePolicy, "Expected typed project evidence policy")
    fingerprint(policy.policy_digest)
    require(type(policy.checks) is tuple and 1 <= len(policy.checks) <= 32, "Invalid project check inventory")
    identities = []
    for item in policy.checks:
        require(type(item) is RequiredCheck and item.phase in set(Phase), "Invalid phase-specific check")
        for text in (item.name, item.provider, item.origin):
            _public(text, 128)
        if item.denominator is not None:
            integer(item.denominator, 1)
        require(type(item.native_record_is_attempt) is bool, "Invalid native provenance rule")
        identities.append((item.name, item.phase))
    require(len(set(identities)) == len(identities), "Duplicate phase-specific required check")
    integer(policy.observed_at)
    integer(policy.expires_at)
    require(type(policy.maximum_age) is int and 1 <= policy.maximum_age <= 3600, "Invalid evidence freshness budget")
    if policy.result_maximum_age is not None:
        integer(policy.result_maximum_age, 1)
    if policy.action_id is not None:
        _public(policy.action_id)
    payload = data(policy)
    payload.pop("evidence")
    return digest({"plan": data(plan), "policy": payload})


def observation_subject(query: ObservationQuery, observation: ProjectObservation) -> str:
    candidate = type(query) is CandidateObservationQuery
    require(type(observation) is (CandidateProjectObservation if candidate else ProjectObservation), "Expected typed project observation")
    require(observation.query_digest == digest(query), "Observation query binding differs")
    integer(observation.observed_at)
    require(type(observation.complete) is bool and observation.coverage in COVERAGE, "Invalid observation completeness")
    if observation.action_key is not None:
        fingerprint(observation.action_key)
    require(type(observation.results) is tuple and len(observation.results) <= 256, "Observation inventory exceeds bounds")
    for result in observation.results:
        require(type(result) is (CandidateProjectResult if candidate else ProjectResult), "Expected typed check result")
        if candidate:
            fingerprint(result.candidate_digest)
        for text in (result.name, result.provider, result.origin, result.repository_id, result.run_id, result.provider_status):
            _public(text)
        sha(result.revision)
        if result.attempt_id is not None:
            _public(result.attempt_id)
        require(result.status in set(ResultStatus), "Invalid check status")
        if result.reported_at is not None:
            integer(result.reported_at)
        require(type(result.complete) is bool and type(result.current) is bool, "Invalid result completeness/current marker")
        integer(result.quarantined)
        require(type(result.counts) is tuple and len(result.counts) <= len(COUNTS)
                and all(type(c) is OutcomeCount and c.outcome in COUNTS for c in result.counts)
                and len({c.outcome for c in result.counts}) == len(result.counts), "Invalid outcome counts")
        for count in result.counts:
            integer(count.count)
        if result.denominator is not None:
            integer(result.denominator, 1)
            require(sum(c.count for c in result.counts) <= result.denominator
                    and result.quarantined <= result.denominator, "Original denominator/counts differ")
    payload = data(observation)
    payload.pop("evidence")
    subject = {"query": data(query), "observation": payload}
    if candidate:
        subject["domain"] = "project-validation/candidate-observation"
    return digest(subject)


def action_subject(request: EvidenceRequest, action_id: str, key: str) -> str:
    return digest({"request": data(request), "action_id": action_id, "key": key})


def reobservation_subject(original, current, action_key):
    return digest({"domain": "project-validation/reobserve", "original": data(original),
                   "current": data(current), "action_key": action_key})


def capture_candidate(root: Path) -> CandidateSource:
    """Observe actual content and Git index without staging or executing checks."""
    import hashlib
    from .execution_containment import source_seal
    from .git import git
    from .policy_adapters import working_tree_digest
    return CandidateSource(source_seal(root), hashlib.sha256(git(root, "ls-files", "--stage", "-z")).hexdigest(),
                           working_tree_digest(root))


class ReportedEvidence:
    """Trusted project integration supplies a fresh authenticated observation.

    It can read a project-reported receipt, query an external service, or delegate
    to a separately authorized project action. This class runs no command.
    """
    def __init__(self, observer):
        self.observer = observer

    def observe(self, query: ObservationQuery) -> ProjectObservation:
        return self.observer(query)


class ProjectValidation:
    def __init__(self, provider, task, policy: EvidencePolicy, source, *, directory: Path,
                 protected_roots: tuple[Path, ...], maximum_observations: int = 8, clock=None,
                 candidate: CandidateSource | None = None, candidate_root: Path | None = None,
                 retain_requests: bool = False):
        require(type(maximum_observations) is int and 1 <= maximum_observations <= 32,
                "Invalid finite observation limit")
        self.provider, self.task, self.policy, self.source = provider, task, policy, source
        self.candidate, self.candidate_root = candidate, candidate_root
        if candidate is not None:
            require(type(candidate) is CandidateSource and candidate_root is not None
                    and getattr(getattr(provider.adapter, "config", None), "root", None) == candidate_root,
                    "Candidate evidence requires the actual configured project root")
            for item in (candidate.content_digest, candidate.index_digest, candidate.worktree_digest):
                fingerprint(item)
        self.clock = clock or (lambda: int(time.time()))
        self.directory = safe_path(directory)
        require(protected_roots and all(not self.directory.is_relative_to(safe_path(p))
                    for p in protected_roots), "Private evidence must be outside protected roots")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
                "Private evidence directory must be owned mode0700")
        self._directory_identity = (info.st_dev, info.st_ino)
        self.maximum_observations = maximum_observations
        require(type(retain_requests) is bool, "Explicit request-retention selection required")
        self.retain_requests = retain_requests

    def _check_directory(self):
        info = safe_path(self.directory).stat()
        require((info.st_dev, info.st_ino) == self._directory_identity and stat.S_ISDIR(info.st_mode)
                and info.st_uid == os.getuid() and not info.st_mode & 0o077,
                "Private journal was replaced or its security state changed")

    def _verify(self, evidence, purpose, subject):
        require(type(evidence) is Attestation and evidence.subject == subject
                and self.provider.authority is not None, "Missing authenticated project evidence")
        for item in (evidence.reviewer, evidence.reference):
            _public(item, 512)
        require(self.provider.authority.verify(evidence, purpose="project-validation/" + purpose,
                    subject=subject) is True, "Unverified project evidence provenance")

    def request(self, phase: Phase, *, authorization: Authorization, pull=None) -> EvidenceRequest:
        require(phase in set(Phase), "Unknown validation phase")
        if self.candidate is not None:
            from .git import value
            require(phase == Phase.BEFORE_PR and pull is None and capture_candidate(self.candidate_root) == self.candidate
                    and value(self.candidate_root, "rev-parse", "HEAD") == self.task.revision
                    and value(self.candidate_root, "symbolic-ref", "HEAD") == self.task.source_ref,
                    "Candidate source changed or phase is not precommit")
        request = CandidateValidationRequest(Operation.VALIDATE, candidate=self.candidate) if self.candidate else Request(Operation.VALIDATE)
        plan = self.provider.plan(self.task, request)
        require(self.provider.decide(plan, authorization).effect == Effect.ALLOW,
                "Current exact M3 validation authorization is required")
        subject = policy_subject(plan, self.policy)
        self._verify(self.policy.evidence, "candidate-policy" if self.candidate else "policy", subject)
        require(self.policy.policy_digest == plan.policy_digest
                and {c.name for c in self.policy.checks} == set(plan.required_checks),
                "Project evidence policy differs from current M3 requirements")
        require(fresh(self.policy.observed_at, self.policy.expires_at, self.clock()), "Project evidence policy is stale")
        require(any(c.phase == phase for c in self.policy.checks), "No project checks prescribed for this phase")
        require(phase != Phase.AFTER_PR or pull is not None, "Post-PR evidence requires an exact PR identity")
        if pull is not None:
            from .project_validation_types import PullIdentity
            require(type(pull) is PullIdentity, "Invalid PR identity")
            _public(pull.id)
            integer(pull.number, 1)
            require(pull.repository_id == self.task.repository_id, "PR repository differs")
        values = (self.task.repository_id, self.task.source_ref, self.task.revision,
            digest({"m3": plan.policy_digest, "project": subject}), phase, self.task.task_id,
            self.task.generation, self.task.task_epoch, self.task.iteration, pull)
        return CandidateEvidenceRequest(*values, candidate=self.candidate) if self.candidate else EvidenceRequest(*values)

    def _path(self, request):
        return safe_path(self.directory / (digest(request) + ".json"))

    def _state(self, request):
        self._check_directory()
        path = self._path(request)
        if path.exists():
            state = load_json(path)
            self._validate_state(state)
            require(state["request"] == digest(request)
                    and state["maximum_observations"] == self.maximum_observations, "Resume context or budget differs")
            return state
        count = 0
        with os.scandir(self.directory) as entries:
            for index, entry in enumerate(entries):
                require(index < 65, "Private evidence directory exceeds bounds")
                if entry.name.endswith(".json"):
                    count += 1
                    require(count < 32, "Private evidence capacity exhausted")
        state = {"schema_version": 2 if self.retain_requests else 1, "request": digest(request), "maximum_observations": self.maximum_observations,
            "session": secrets.token_hex(32), "observations": 0, "inflight": False,
            "last_observed": 0, "last_digest": None, "trigger": "NOT_REQUESTED", "action_key": None, "reconciliation": None}
        if self.retain_requests:
            state["original_request"] = data(request)
        return state

    @staticmethod
    def _validate_state(state):
        version = state.get("schema_version") if type(state) is dict else None
        fields(state, "schema_version request maximum_observations session observations inflight last_observed last_digest trigger action_key reconciliation"
               + (" original_request" if version == 2 else ""))
        require(type(state["schema_version"]) is int and state["schema_version"] in (1, 2), "Unsupported private evidence journal")
        if state["schema_version"] == 2:
            original = typed(CandidateEvidenceRequest | EvidenceRequest, state["original_request"])
            require(digest(original) == state["request"], "Retained original request identity differs")
        fingerprint(state["request"])
        fingerprint(state["session"])
        integer(state["observations"])
        integer(state["last_observed"])
        require(type(state["maximum_observations"]) is int and 1 <= state["maximum_observations"] <= 32
                and state["observations"] <= state["maximum_observations"] and type(state["inflight"]) is bool
                and state["trigger"] in ("NOT_REQUESTED", "SUBMITTED", "RETURNED", "RECONCILED"), "Invalid private observation journal")
        if state["last_digest"] is not None:
            fingerprint(state["last_digest"])
        if state["trigger"] == "NOT_REQUESTED":
            require(state["action_key"] is None and state["reconciliation"] is None, "Unrequested action has unexpected receipt")
        else:
            fingerprint(state["action_key"])
            if state["trigger"] == "RECONCILED":
                proof = state["reconciliation"]
                fields(proof, "request action_key observation observed_at")
                require(proof["request"] == state["request"] and proof["action_key"] == state["action_key"],
                        "Action reconciliation differs from durable request")
                fingerprint(proof["observation"])
                integer(proof["observed_at"])
            else:
                require(state["reconciliation"] is None, "Unconfirmed action has unexpected reconciliation")

    def _unknown_action_exists(self):
        # The same retained private directory fences every context, not just the
        # current SHA/policy/generation filename. Never infer absent delivery by
        # selecting a different context or silently ignoring malformed history.
        self._check_directory()
        found, count = False, 0
        with os.scandir(self.directory) as entries:
            for index, entry in enumerate(entries):
                require(index < 65, "Private action history exceeds bounds")
                if not entry.name.endswith(".json"):
                    continue
                count += 1
                require(count <= 32, "Private action history capacity exhausted")
                fingerprint(entry.name[:-5])
                state = load_json(safe_path(self.directory / entry.name))
                self._validate_state(state)
                require(state["request"] == entry.name[:-5], "Private action history identity differs")
                found |= state["trigger"] in ("SUBMITTED", "RETURNED")
        return found

    def retained_request(self, current):
        """Find one exact, retained unfinished intent; never infer a lost payload."""
        matches = []
        expected = data(current); expected.pop("policy_digest")
        self._unknown_action_exists()  # bounded whole-history schema validation
        for path in self.directory.glob("*.json"):
            state = load_json(safe_path(path))
            if state["trigger"] not in ("SUBMITTED", "RETURNED"):
                continue
            require(state["schema_version"] == 2, "Original action request is unavailable; external reconciliation required")
            original = typed(CandidateEvidenceRequest | EvidenceRequest, state["original_request"])
            proposed = data(original); proposed.pop("policy_digest")
            if proposed == expected:
                matches.append(original)
        require(len(matches) <= 1, "Multiple unfinished project actions need authoritative reconciliation")
        return matches[0] if matches else None

    def _reserved_action(self):
        from .execution_policy import ReservedSafety
        from .guard import ProgressGuard
        from .memory import Memory
        from .execution_memory import QueuedMemory
        safety = self.provider.safety
        memory = getattr(getattr(safety, "guard", None), "memory", None)
        actual = memory._memory if type(memory) is QueuedMemory else memory
        require(type(safety) is ReservedSafety and type(safety.guard) is ProgressGuard
                and type(actual) is Memory and safety.permit is not None
                and safety.forensic_request is None, "Actual current M2 action reservation is required")
        # Accepted _active/context/deadline/current ownership checks are reused;
        # generic inspect(ALLOW) and a forged Decision are insufficient.
        require(safety.observe(self.task).owns_memory, "Current reserved M1 ownership is required")

    def _write(self, request, state):
        self._check_directory()
        atomic(self._path(request), encode(state))

    def _unknown(self, request, reason):
        names = tuple(c.name for c in self.policy.checks if c.phase == request.phase)
        cls = CandidateEvidenceGate if type(request) is CandidateEvidenceRequest else EvidenceGate
        return cls(request, ResultStatus.UNKNOWN, (), names, False, reason, "project-validation:unknown")

    def _evaluate(self, query: ObservationQuery, observation: ProjectObservation, *, last_observed=0) -> EvidenceGate:
        subject = observation_subject(query, observation)
        candidate = type(query) is CandidateObservationQuery
        self._verify(observation.evidence, "candidate-observation" if candidate else "observation", subject)
        now = self.clock()
        require(last_observed <= observation.observed_at <= now
                and now - observation.observed_at <= self.policy.maximum_age, "Stale/replayed project observation")
        request = query.request
        required = tuple(c for c in self.policy.checks if c.phase == request.phase)
        results, missing = [], []
        complete = observation.complete and observation.coverage == "COMPLETE"
        if query.action_key is not None and observation.action_key != query.action_key:
            complete = False  # An old green run cannot reconcile an uncertain new request.
        for check in required:
            candidates = [r for r in observation.results if r.name == check.name and r.current]
            if len(candidates) != 1:
                missing.append(check.name)
                complete = False
                continue
            result = candidates[0]
            if candidate and result.candidate_digest != digest(request.candidate):
                missing.append(check.name)
                complete = False
            if (result.provider != check.provider or result.origin != check.origin
                    or result.repository_id != request.repository_id or result.revision != request.revision
                    or not result.complete or result.reported_at is None or result.reported_at > observation.observed_at
                    or self.policy.result_maximum_age is not None and now - result.reported_at > self.policy.result_maximum_age
                    or result.attempt_id is None and not check.native_record_is_attempt
                    or check.denominator is not None and result.denominator != check.denominator):
                missing.append(check.name)
                complete = False
            if (result.denominator is None and result.counts or result.denominator is not None
                    and (len(result.counts) != len(COUNTS) or sum(c.count for c in result.counts) != result.denominator)):
                complete = False  # Preserve partial counts without inventing missing outcomes.
            results.append(result)
        statuses = {r.status for r in results}
        if not complete:
            status = ResultStatus.UNKNOWN
        elif statuses == {ResultStatus.PASS}:
            status = ResultStatus.PASS if all(r.quarantined == 0 and (r.denominator is None or
                next(c.count for c in r.counts if c.outcome == "PASS") == r.denominator) for r in results) else ResultStatus.FAIL
        elif ResultStatus.PENDING in statuses:
            status = ResultStatus.PENDING
        elif ResultStatus.UNKNOWN in statuses:
            status = ResultStatus.UNKNOWN
        else:
            status = next(r.status for r in results if r.status != ResultStatus.PASS)
        reason = "PROJECT_CHECKS_QUALIFIED" if status == ResultStatus.PASS else "PENDING_PROJECT_CHECKS" if status == ResultStatus.PENDING else "ACTIONABLE_PROJECT_FAILURE" if status in (ResultStatus.FAIL, ResultStatus.ERROR, ResultStatus.TIMEOUT, ResultStatus.CANCELLED) else "INCOMPLETE_PROJECT_EVIDENCE"
        cls = CandidateEvidenceGate if candidate else EvidenceGate
        return cls(request, status, tuple(results), tuple(missing), complete, reason,
                            "project-validation:" + subject)

    def observe(self, phase: Phase, *, authorization: Authorization, pull=None, budget_ms=1000) -> EvidenceGate:
        require(type(budget_ms) is int and 1 <= budget_ms <= 300000, "Invalid observation deadline")
        request = self.request(phase, authorization=authorization, pull=pull)
        return self._observe_request(request, authorization, budget_ms, current=request)

    def reobserve(self, original, *, authorization: Authorization, evidence: Attestation, budget_ms=1000):
        """Read the same retained project action under fresh exact authority.

        No action is submitted, context budget reset, or old result promoted.
        The external verifier authenticates the old/current policy mapping.
        """
        require(type(original) in (EvidenceRequest, CandidateEvidenceRequest), "Actual retained check request required")
        require(type(budget_ms) is int and 1 <= budget_ms <= 300000, "Invalid observation deadline")
        current = self.request(original.phase, authorization=authorization, pull=original.pull)
        old, new = data(original), data(current)
        old.pop("policy_digest"); new.pop("policy_digest")
        require(type(original) is type(current) and old == new, "Reobservation source/owner/task context changed")
        state = self._state(original)
        require(self._path(original).is_file(), "Original observation history is missing")
        self._verify(evidence, "reobserve", reobservation_subject(original, current, state["action_key"]))
        return self._observe_request(original, authorization, budget_ms, current=current)

    def _observe_request(self, request, authorization, budget_ms, *, current):
        with locked(self.directory):
            state = self._state(request)
            if state["observations"] >= self.maximum_observations:
                return self._unknown(request, "OBSERVATION_BUDGET_EXHAUSTED")
            state["observations"] += 1
            state["inflight"] = True
            self._write(request, state)  # A crash consumes this observation; restart never trusts cached PASS.
            action_key = self._action_key(request, state) if state["trigger"] != "NOT_REQUESTED" else None
            cls = CandidateObservationQuery if self.candidate else ObservationQuery
            query = cls(request, digest({"session": state["session"], "sequence": state["observations"]}),
                                     budget_ms, action_key)
            deadline = time.monotonic() + budget_ms / 1000
            try:
                observed = self.source.observe(query)
                require(time.monotonic() <= deadline, "Project observation deadline exceeded")
                gate = self._evaluate(query, observed, last_observed=state["last_observed"])
                # Source/policy/guard may have changed during the external observation.
                require(self.request(current.phase, authorization=authorization, pull=current.pull) == current,
                        "Validation source or policy changed during observation")
                state["last_observed"], state["last_digest"] = observed.observed_at, gate.evidence.split(":", 1)[1]
                if (state["trigger"] in ("SUBMITTED", "RETURNED") and gate.complete
                        and observed.action_key == state["action_key"]):
                    state["trigger"] = "RECONCILED"
                    state["reconciliation"] = {"request": state["request"], "action_key": state["action_key"],
                        "observation": state["last_digest"], "observed_at": observed.observed_at}
            except (ADPError, OSError, ValueError, TypeError, KeyError, AttributeError):
                gate = self._unknown(request, "UNVERIFIED_OR_UNAVAILABLE_PROJECT_EVIDENCE")
            state["inflight"] = False
            self._write(request, state)
            return gate

    def poll(self, phase: Phase, *, authorization: Authorization, pull=None, maximum=1, seconds=1) -> EvidenceGate:
        require(type(maximum) is int and 1 <= maximum <= 32 and type(seconds) is int and 1 <= seconds <= 300,
                "Invalid finite poll budget")
        deadline = time.monotonic() + seconds
        result = None
        for _ in range(maximum):
            if time.monotonic() >= deadline:
                break
            result = self.observe(phase, authorization=authorization, pull=pull,
                                  budget_ms=max(1, int((deadline - time.monotonic()) * 1000)))
            if result.status != ResultStatus.PENDING:
                return result
        if result is None:
            request = self.request(phase, authorization=authorization, pull=pull)
            return self._unknown(request, "POLL_BUDGET_EXHAUSTED")
        return result

    def request_action(self, phase: Phase, *, authorization: Authorization, evidence: Attestation,
                       action, pull=None) -> str:
        request = self.request(phase, authorization=authorization, pull=pull)
        require(self.policy.action_id is not None, "Project exposes no validation action")
        with locked(self.directory):
            state = self._state(request)
            key = self._action_key(request, state)
            self._verify(evidence, "candidate-action" if self.candidate else "action", action_subject(request, self.policy.action_id, key))
            if state["trigger"] != "NOT_REQUESTED":
                return "UNKNOWN_DELIVERY_REOBSERVE" if state["trigger"] == "SUBMITTED" else "REQUEST_ALREADY_RETURNED_REOBSERVE"
            if self._unknown_action_exists():
                return "UNKNOWN_DELIVERY_REOBSERVE"
            self._reserved_action()
            state["trigger"] = "SUBMITTED"
            state["action_key"] = key
            self._write(request, state)  # No retry even after a lost response or process interruption.
            try:
                require(self.request(phase, authorization=authorization, pull=pull) == request,
                        "Source or authority changed before requesting project action")
                self._reserved_action()
                action.request(request, self.policy.action_id, key)
            except (ADPError, OSError):
                return "UNKNOWN_DELIVERY_REOBSERVE"
            state["trigger"] = "RETURNED"
            self._write(request, state)
            return "REQUEST_RETURNED_REOBSERVE"  # Neither completion nor cancellation is inferred.

    def action_key(self, phase: Phase, *, authorization: Authorization, pull=None) -> str:
        """Prepare the exact subject for a separately authorized project action."""
        request = self.request(phase, authorization=authorization, pull=pull)
        with locked(self.directory):
            state = self._state(request)
            self._write(request, state)
            return self._action_key(request, state)

    def _action_key(self, request, state):
        return digest({"session": state["session"], "request": data(request), "action": self.policy.action_id})
