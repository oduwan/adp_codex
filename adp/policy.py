"""External policy decisions, provenance and authorization. No Git execution."""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable

from .errors import ADPError
from .guard_types import Attestation, Baseline, Decision as GuardDecision, DecisionKind, data
from .policy_schema import (FORBIDDEN, GATED, MAX_SOURCES, METHODS, STATUSES, branch,
    digest, fingerprint, fresh, ref, render, sha, strings, validate_rules,
    validate_snapshot, validate_task)
from .policy_types import (Authorization, BranchPlan, Check, CommitPlan, Decision,
    DeploymentPlan, Effect, Inspection, MergePlan, Operation, OutcomeCount, Plan, PolicyAuthority,
    Protection, Provenance, PullRequestPlan, Qualifications, ReleasePlan, RepositoryAdapter,
    Request, Review, Rules, Safety, SafetyAdapter, SourceClaim, SourceKind, Task,
    PushPlan, ValidationPlan)
from .schema import integer, key, require, string

RANK = {SourceKind.OPERATOR: 0, SourceKind.GOVERNANCE: 1,
        SourceKind.CONTRACT: 1, SourceKind.PROFILE: 2}
PROTECTED = {Operation.PR, Operation.PUSH, Operation.MERGE, Operation.RELEASE, Operation.DEPLOY}


class PolicyProvider:
    """Pure decision core over trusted observational adapters and verified data.

    File presence/parsing, labels in snapshots and Git credentials never grant
    permissions. Every operation needs its own final exact-plan authorization.
    A returned ALLOW is a point-in-time decision, never an executed side effect.
    """
    def __init__(self, adapter: RepositoryAdapter, *, sources: tuple[SourceClaim, ...] = (),
                 protections: tuple[Protection, ...] = (), authority: PolicyAuthority | None = None,
                 safety: SafetyAdapter | None = None, clock: Callable[[], int] | None = None):
        require(type(sources) is tuple and len(sources) <= MAX_SOURCES, "Too many policy claims")
        require(type(protections) is tuple and len(protections) <= 32, "Too many protection observations")
        require(all(type(s) is SourceClaim for s in sources), "Expected typed source claims")
        require(all(type(p) is Protection for p in protections), "Expected typed protection observations")
        strings([s.reference for s in sources], MAX_SOURCES)
        strings([p.ref for p in protections], 32)
        self.adapter, self.sources, self.protections = adapter, sources, protections
        self.authority, self.safety = authority, safety
        self.clock = clock or (lambda: int(time.time()))

    def _now(self) -> int:
        now = self.clock()
        integer(now)
        return now

    def _verified(self, evidence: Attestation | None, purpose: str, subject: str) -> bool:
        if not isinstance(evidence, Attestation) or self.authority is None:
            return False
        string(evidence.reviewer, 128)
        string(evidence.reference)
        if evidence.subject != subject:
            return False
        return self.authority.verify(evidence, purpose="policy/" + purpose, subject=subject) is True

    @staticmethod
    def _repository_scope(snapshot) -> dict:
        return {"repository_id": snapshot.repository_id, "remote": snapshot.remote,
                "remote_fingerprint": snapshot.remote_fingerprint,
                "source_ref": snapshot.source_ref, "revision": snapshot.revision}

    def source_subject(self, source: SourceClaim, snapshot=None) -> str:
        snapshot = snapshot or self.adapter.inspect()
        validate_snapshot(snapshot)
        require(type(source) is SourceClaim, "Expected typed source claim")
        require(isinstance(source.kind, str) and source.kind in set(RANK) | {SourceKind.UNTRUSTED}, "Invalid policy source kind")
        string(source.reference)
        fingerprint(source.document_digest)
        validate_rules(source.rules)
        integer(source.observed_at)
        integer(source.expires_at)
        payload = data(source)
        payload.pop("evidence")
        return digest({"scope": self._repository_scope(snapshot), "source": payload})

    def protection_subject(self, protection: Protection, snapshot=None) -> str:
        snapshot = snapshot or self.adapter.inspect()
        validate_snapshot(snapshot)
        require(type(protection) is Protection, "Expected typed protection snapshot")
        ref(protection.ref)
        sha(protection.revision, nullable=True)
        for flag in (protection.known, protection.push_allowed, protection.merge_allowed):
            require(type(flag) is bool, "Invalid protection flag")
        strings(protection.checks, 32, 128)
        strings(protection.unsupported, 16, 128)
        strings(protection.merge_methods, 3, 32)
        if protection.mergeable_methods is not None:
            strings(protection.mergeable_methods, 3, 32)
            require(all(m in METHODS for m in protection.mergeable_methods), "Unknown mergeability method")
        require(all(m in METHODS for m in protection.merge_methods), "Unsupported protected merge method")
        require(type(protection.reviews) is int and 0 <= protection.reviews <= 16, "Invalid protected review obligation")
        string(protection.reference)
        integer(protection.observed_at)
        integer(protection.expires_at)
        payload = data(protection)
        payload.pop("evidence")
        return digest({"scope": self._repository_scope(snapshot), "protection": payload})

    def inspect_repository(self) -> Inspection:
        snapshot = self.adapter.inspect()
        validate_snapshot(snapshot)
        now = self._now()
        docs = {d.reference: d for d in snapshot.documents}
        provenance, accepted, conflicts = [], [], []
        for document in snapshot.documents:
            provenance.append(Provenance(document.reference, document.kind, document.digest,
                "OBSERVED", "Committed/injected data only; presence grants no authority"))
        for source in self.sources:
            subject = self.source_subject(source, snapshot)
            reason = ""
            document = docs.get(source.reference)
            if source.kind == SourceKind.UNTRUSTED:
                provenance.append(Provenance(source.reference, source.kind, source.document_digest,
                    "IGNORED", "Issue/PR text cannot grant or override policy"))
                continue
            if source.kind != SourceKind.OPERATOR and (document is None or document.kind != source.kind
                    or document.digest != source.document_digest):
                reason = "Source does not match the exact observed document/provenance"
            elif source.kind == SourceKind.PROFILE and document.profile != source.rules:
                reason = "Interpreted profile differs from the closed parsed data"
            elif source.kind == SourceKind.CONTRACT and (any(p.effect == Effect.ALLOW for p in source.rules.permissions)
                    or any(getattr(source.rules, name) is not None for name in ("base_branch", "branch_template",
                        "subject_template", "body_template", "subject_limit", "pr_title_template", "pr_draft",
                        "merge_method", "release_template"))):
                reason = "Accepted task contracts may constrain policy, never grant operation rights"
            elif not fresh(source.observed_at, source.expires_at, now):
                reason = "Policy provenance is stale or has an unsupported lifetime"
            elif not self._verified(source.evidence, source.kind.lower(), subject):
                reason = "Policy identity, interpretation, acceptance or provenance is unverified"
            if reason:
                conflicts.append(source.reference + ": " + reason)
                provenance.append(Provenance(source.reference, source.kind, source.document_digest, "UNVERIFIED", reason))
            else:
                accepted.append(source)
                provenance.append(Provenance(source.reference, source.kind, source.document_digest,
                    "VERIFIED", "Externally verified exact repository/revision interpretation"))
        for document in snapshot.documents:
            if document.kind != SourceKind.UNTRUSTED and not any(s.reference == document.reference for s in accepted):
                conflicts.append(document.reference + ": observed governance/profile/contract has no verified interpretation")
        identity = digest({"snapshot": data(snapshot), "sources": [data(s) for s in accepted],
                           "provenance": [data(p) for p in provenance], "conflicts": conflicts})
        return Inspection(snapshot, tuple(accepted), tuple(provenance), tuple(conflicts), identity)

    @staticmethod
    def _value(inspection: Inspection, field: str, reasons: list[str], *, required: bool = True):
        candidates = [(RANK[s.kind], s.reference, getattr(s.rules, field)) for s in inspection.sources
                      if getattr(s.rules, field) is not None]
        if not candidates:
            if required:
                reasons.append("Missing external rule: " + field)
            return None
        priority = min(c[0] for c in candidates)
        winners = [c for c in candidates if c[0] == priority]
        if any(c[2] != winners[0][2] for c in winners):
            reasons.append("Conflicting " + field + " at equal authority: " + ", ".join(c[1] for c in winners))
            return None
        return winners[0][2]

    @staticmethod
    def _rule_provenance(inspection: Inspection) -> list[Provenance]:
        traces = list(inspection.provenance)
        for field in ("base_branch", "branch_template", "subject_template", "body_template", "subject_limit",
                      "pr_title_template", "pr_draft", "merge_method", "release_template"):
            candidates = [s for s in inspection.sources if getattr(s.rules, field) is not None]
            if not candidates:
                continue
            priority = min(RANK[s.kind] for s in candidates)
            winners = [s for s in candidates if RANK[s.kind] == priority]
            conflict = any(getattr(s.rules, field) != getattr(winners[0].rules, field) for s in winners)
            for source in candidates:
                status = "SUPERSEDED" if RANK[source.kind] != priority else "CONFLICT" if conflict else "SELECTED"
                traces.append(Provenance(source.reference, source.kind, source.document_digest, status,
                                         "External rule " + field + "; priority " + str(RANK[source.kind])))
        for source in inspection.sources:
            if source.rules.checks or source.rules.reviews is not None or source.rules.gate_operations:
                traces.append(Provenance(source.reference, source.kind, source.document_digest, "REQUIRED",
                    "Check/review/gate constraints combine restrictively across verified sources"))
            if source.rules.environments is not None:
                traces.append(Provenance(source.reference, source.kind, source.document_digest, "CONSTRAINT",
                    "Environment selection follows authority priority; accepted contracts can only restrict it"))
        traces.append(Provenance("adp:mandatory-safety", SourceKind.INVARIANT, digest({"minimum_reviews": 1}),
            "REQUIRED", "M1 ownership, M2 guard and independent exact-SHA approval cannot be waived; no operation rights granted"))
        return traces

    @staticmethod
    def _scope(plan: Plan) -> dict:
        return {"repository_id": plan.task.repository_id, "remote": plan.remote,
                "remote_fingerprint": plan.remote_fingerprint, "task_id": plan.task.task_id,
                "source_ref": plan.task.source_ref, "revision": plan.task.revision,
                "operation": plan.request.operation, "target_ref": plan.target_ref,
                "policy_digest": plan.policy_digest}

    def _safety(self, task: Task) -> Safety | None:
        if self.safety is None:
            return None
        value = self.safety.observe(task)
        require(type(value) is Safety and type(value.owns_memory) is bool, "Invalid trusted safety observation")
        strings(value.authors, 16, 128)
        sha(value.memory_head)
        # Validate all M2 binding fields without changing M2 or its schemas.
        require(type(value.guard) is GuardDecision and type(value.guard.baseline) is Baseline, "Expected an actual typed M2 decision")
        baseline = value.guard.baseline
        require(isinstance(value.guard.kind, str) and value.guard.kind in set(DecisionKind) and value.guard.scope == "attempt", "Invalid guard decision scope")
        require((baseline.repository_id, baseline.task_key, baseline.revision, baseline.requirement_id,
                 baseline.generation, baseline.task_epoch, baseline.iteration) ==
                (task.repository_id, key(task.task_id), task.revision, task.requirement_id,
                 task.generation, task.task_epoch, task.iteration), "Safety observation is not bound to the exact admitted task")
        fingerprint(baseline.record_digest)
        require(value.approval is None or value.approval == baseline, "M2 approval is stale or from another guard context")
        return value

    def plan(self, task: Task, request: Request) -> Plan:
        validate_task(task)
        require(type(request) is Request and isinstance(request.operation, str)
                and request.operation in set(Operation), "Unsupported policy operation")
        for text in (request.summary, request.version, request.environment):
            require(isinstance(text, str) and len(text) <= 256 and all(ord(c) >= 32 for c in text), "Invalid bounded operation input")
        inspection = self.inspect_repository()
        snapshot, op = inspection.snapshot, request.operation
        reasons = list(inspection.conflicts)
        denied = []
        payload, target = None, snapshot.source_ref
        required_checks = tuple(sorted({c for s in inspection.sources for c in s.rules.checks}))
        reviews = max([1] + [s.rules.reviews for s in inspection.sources if s.rules.reviews is not None])
        gated = op in GATED or any(op in s.rules.gate_operations for s in inspection.sources)
        permissions = [(RANK[s.kind], s.reference, p.effect) for s in inspection.sources
                       for p in s.rules.permissions if p.operation == op]
        if op in FORBIDDEN:
            denied.append("Automatic force/history rewrite/rebase is not supported; no fallback exists")
        if any(effect == Effect.DENY for _, _, effect in permissions):
            denied.append("Explicit external denial: " + ", ".join(name for _, name, e in permissions if e == Effect.DENY))
        if not permissions:
            reasons.append("No verified external permission for " + op)
        elif not any(e == Effect.DENY for _, _, e in permissions):
            best = min(p[0] for p in permissions)
            if any(e != Effect.ALLOW for rank, _, e in permissions if rank == best):
                reasons.append("External permission remains unknown at the controlling authority")
        if (task.repository_id, task.revision, task.source_ref) != (snapshot.repository_id, snapshot.revision, snapshot.source_ref):
            denied.append("Task repository/ref/revision differs from the inspected checkout")
        if not snapshot.worktree_clean:
            reasons.append("Unstaged or untracked product changes require a new clean inspection")
        local = {r.name: r.revision for r in snapshot.local_refs}
        remote = {r.name: r.revision for r in snapshot.remote_refs}
        branch_template = self._value(inspection, "branch_template", reasons,
                                      required=op in {Operation.BRANCH, Operation.COMMIT, Operation.PR, Operation.PUSH, Operation.MERGE})
        task_ref = "refs/heads/" + render(branch_template, slug=task.branch_slug) if branch_template else None
        if task_ref:
            ref(task_ref)
        base = self._value(inspection, "base_branch", reasons,
                           required=op in {Operation.PR, Operation.MERGE, Operation.RELEASE, Operation.DEPLOY})
        base_ref = "refs/heads/" + base if base else None
        if op == Operation.BRANCH and task_ref:
            target = task_ref
            if target in local and local[target] != task.revision:
                denied.append("Existing branch points elsewhere; no branch overwrite is permitted")
            payload = BranchPlan(task_ref[11:], task.revision, target in local)
        elif op == Operation.COMMIT:
            if task_ref and snapshot.source_ref != task_ref:
                denied.append("Commit source is not the externally admitted task branch")
            subject_rule = self._value(inspection, "subject_template", reasons)
            body_rule = self._value(inspection, "body_template", reasons)
            limit = self._value(inspection, "subject_limit", reasons)
            string(request.summary, 256)
            if subject_rule is not None and body_rule is not None and limit is not None:
                subject = render(subject_rule, task=task.task_id, summary=request.summary)
                if not subject.strip() or len(subject) > limit:
                    denied.append("Commit subject violates the destination's explicit limit")
                payload = CommitPlan(subject, render(body_rule, task=task.task_id, summary=request.summary), snapshot.index_digest)
        elif op == Operation.VALIDATE:
            if not required_checks:
                reasons.append("No external validation/check matrix was specified")
            payload = ValidationPlan(required_checks)
        elif op in (Operation.PR, Operation.MERGE) and base_ref and task_ref:
            target = base_ref
            if snapshot.source_ref != task_ref or task_ref == base_ref:
                denied.append("PR/merge source is not the destination's admitted task branch")
            if op == Operation.PR:
                title_rule = self._value(inspection, "pr_title_template", reasons)
                draft = self._value(inspection, "pr_draft", reasons)
                string(request.summary, 256)
                if title_rule is not None and draft is not None:
                    payload = PullRequestPlan(task_ref, base_ref, render(title_rule, task=task.task_id, summary=request.summary), draft)
                    gated = gated or not draft
            else:
                method = self._value(inspection, "merge_method", reasons)
                if base_ref not in remote:
                    reasons.append("Merge base remote revision is unknown or absent")
                elif method:
                    payload = MergePlan(task_ref, base_ref, task.revision, remote[base_ref], method)
        elif op == Operation.PUSH and task_ref:
            target = task_ref
            if snapshot.source_ref != task_ref:
                denied.append("Push source is not the admitted task branch")
            if snapshot.push_relation == "DIVERGED":
                denied.append("Remote branch diverged; ordinary push cannot reconcile it")
            elif snapshot.push_relation == "UNKNOWN":
                reasons.append("Fast-forward ancestry is unverified; no fetch/force fallback")
            payload = PushPlan(snapshot.remote, target, task.revision, remote.get(target))
        elif op == Operation.RELEASE:
            release = self._value(inspection, "release_template", reasons)
            string(request.version, 96)
            if release:
                name = render(release, version=request.version)
                branch(name)
                target = "refs/tags/" + name
                if target in remote or target in local:
                    denied.append("Release tag already exists; no tag rewrite")
                payload = ReleasePlan(target, task.revision)
            if base_ref != snapshot.source_ref:
                denied.append("Release source is not the external policy base branch")
        elif op == Operation.DEPLOY:
            string(request.environment, 128)
            governing = replace(inspection, sources=tuple(s for s in inspection.sources if s.kind != SourceKind.CONTRACT))
            chosen = self._value(governing, "environments", reasons)
            environments = set(chosen or ())
            for source in inspection.sources:
                if source.kind == SourceKind.CONTRACT and source.rules.environments is not None:
                    environments &= set(source.rules.environments)
            if request.environment not in environments:
                denied.append("Deployment environment is not explicitly admitted")
            if base_ref != snapshot.source_ref:
                denied.append("Deployment source is not the external policy base branch")
            payload = DeploymentPlan(request.environment, task.revision)
        protection_values = []
        provenance = self._rule_provenance(inspection)
        if op in PROTECTED:
            if not snapshot.remote_refs_known:
                reasons.append("Remote-ref metadata is inaccessible; no write authority inferred")
            protection = next((p for p in self.protections if p.ref == target), None)
            if protection is None:
                reasons.append("Missing authenticated protection metadata for " + target)
            else:
                subject = self.protection_subject(protection, snapshot)
                provenance.append(Provenance(protection.reference, SourceKind.PROTECTION, subject, "OBSERVED",
                    "Exact source/ref protection and mergeability metadata; restricts but never grants rights"))
                if (not protection.known or protection.revision != remote.get(target)
                        or not fresh(protection.observed_at, protection.expires_at, self._now())
                        or not self._verified(protection.evidence, "protection", subject)):
                    reasons.append("Protection state/provenance/revision is unverified for " + target)
                elif protection.unsupported:
                    reasons.append("Unsupported protection requirements: " + ", ".join(protection.unsupported))
                else:
                    protection_values.append(data(protection))
                    provenance.append(Provenance(protection.reference, SourceKind.PROTECTION, subject, "VERIFIED",
                        "Verified target constraints and method-specific mergeability"))
                    required_checks = tuple(sorted(set(required_checks) | set(protection.checks)))
                    reviews = max(reviews, protection.reviews)
                    if op == Operation.PUSH and not protection.push_allowed:
                        denied.append("Protection prohibits direct push")
                    if op == Operation.MERGE and (not protection.merge_allowed or isinstance(payload, MergePlan)
                            and payload.method not in protection.merge_methods):
                        denied.append("Protection prohibits this merge operation/method")
                    if op == Operation.MERGE and isinstance(payload, MergePlan):
                        if protection.mergeable_methods is None:
                            reasons.append("Exact source/base mergeability is unverified")
                        elif payload.method not in protection.mergeable_methods:
                            denied.append("Exact source/base is not mergeable with this method")
        if payload is None and op not in FORBIDDEN:
            reasons.append("Required external operation semantics are incomplete")
        effect = Effect.DENY if denied else Effect.UNKNOWN if reasons else Effect.ALLOW
        safety = self._safety(task) if not denied else None
        policy_digest = digest({"inspection": inspection.digest, "protections": protection_values})
        return Plan(task, request, digest(snapshot), policy_digest, snapshot.remote, snapshot.remote_fingerprint,
            target, remote.get(target), payload, effect, tuple(denied + reasons), tuple(provenance),
            required_checks, reviews, gated, safety)

    def check_subject(self, plan: Plan, result: Check) -> str:
        self._validate_check(result)
        payload = data(result)
        payload.pop("evidence")
        return digest({"scope": self._scope(plan), "check": payload})

    @staticmethod
    def _validate_check(result: Check) -> None:
        require(type(result) is Check, "Expected typed check evidence")
        string(result.name, 128)
        sha(result.revision)
        integer(result.denominator, 1)
        integer(result.quarantined)
        require(result.quarantined <= result.denominator, "Invalid check quarantine count")
        require(type(result.counts) is tuple and len(result.counts) <= len(STATUSES)
                and all(type(c) is OutcomeCount for c in result.counts), "Expected typed outcome counts")
        strings([c.outcome for c in result.counts], len(STATUSES), 16)
        for count in result.counts:
            require(isinstance(count.outcome, str) and count.outcome in STATUSES, "Invalid check outcome")
            integer(count.count)
        require(sum(c.count for c in result.counts) == result.denominator, "Check denominator/coverage mismatch")
        integer(result.observed_at)
        integer(result.expires_at)

    def review_subject(self, plan: Plan, result: Review) -> str:
        require(type(result) is Review and type(result.approved) is bool, "Expected typed review evidence")
        string(result.reviewer, 128)
        sha(result.revision)
        integer(result.observed_at)
        integer(result.expires_at)
        payload = data(result)
        payload.pop("evidence")
        return digest({"scope": self._scope(plan), "review": payload})

    @staticmethod
    def authorization_subject(plan: Plan, qualifications: Qualifications = Qualifications()) -> str:
        require(type(plan) is Plan and type(qualifications) is Qualifications, "Expected typed operation authorization")
        return digest({"plan": data(plan), "qualifications": data(qualifications)})

    def decide(self, plan: Plan, authorization: Authorization | None = None) -> Decision:
        require(type(plan) is Plan, "Expected a typed policy plan")
        current = self.plan(plan.task, plan.request)
        reasons, pending = [], []
        effect = current.policy_effect
        if current != plan:
            effect = Effect.DENY
            reasons.append("Plan is stale or edited: repository, refs, index, rules, protection or guard evidence changed")
        elif effect != Effect.ALLOW:
            reasons.extend(current.reasons)
            if effect == Effect.UNKNOWN:
                pending.extend(current.reasons)
        safety = current.safety
        if effect == Effect.ALLOW:
            if safety is None:
                effect = Effect.UNKNOWN
                pending.append("Supply fresh M1 ownership and M2 guard observations through a trusted safety adapter")
            elif not safety.owns_memory:
                effect = Effect.DENY
                reasons.append("Current M1 Conductor ownership is absent")
            elif safety.guard.kind != DecisionKind.ALLOW:
                effect = Effect.DENY
                reasons.append("Mandatory M2 guard refuses this operation: " + safety.guard.reason)
        require(authorization is None or type(authorization) is Authorization, "Expected typed operation authorization")
        qualifications = authorization.qualifications if authorization is not None else Qualifications()
        require(type(qualifications) is Qualifications, "Invalid operation qualifications")
        require(type(qualifications.checks) is tuple and len(qualifications.checks) <= 32
                and type(qualifications.reviews) is tuple and len(qualifications.reviews) <= 16,
                "Invalid bounded qualification lists")
        for check in qualifications.checks:
            self._validate_check(check)
        for review in qualifications.reviews:
            self.review_subject(current, review)
        strings([c.name for c in qualifications.checks], 32, 128)
        strings([r.reviewer for r in qualifications.reviews], 16, 128)
        if effect == Effect.ALLOW and current.gated:
            if safety.approval is None:
                pending.append("Current canonical M2 independent exact-revision approval is required")
            if safety.guard.baseline.unresolved:
                effect = Effect.DENY
                reasons.append("M2 acceptance requirements remain unresolved")
            now = self._now()
            checks = {c.name: c for c in qualifications.checks}
            for name in current.required_checks:
                result = checks.get(name)
                if result is None:
                    pending.append("Required check evidence missing: " + name)
                    continue
                subject = self.check_subject(current, result)
                if (result.revision != current.task.revision or not fresh(result.observed_at, result.expires_at, now)
                        or not self._verified(result.evidence, "check", subject)):
                    pending.append("Required check is stale or unverified: " + name)
                elif result.quarantined or any(c.count and c.outcome != "PASS" for c in result.counts):
                    effect = Effect.DENY
                    reasons.append("Non-PASS/quarantined coverage cannot qualify: " + name)
            reviewers = set()
            for result in qualifications.reviews:
                subject = self.review_subject(current, result)
                if result.reviewer in set(current.task.authors) | set(safety.authors):
                    effect = Effect.DENY
                    reasons.append("Source author cannot provide independent exact-SHA review")
                elif (result.revision == current.task.revision
                        and fresh(result.observed_at, result.expires_at, now)
                        and result.evidence is not None and result.evidence.reviewer == result.reviewer
                        and self._verified(result.evidence, "review", subject)):
                    if result.approved:
                        reviewers.add(result.reviewer)
                    else:
                        effect = Effect.DENY
                        reasons.append("A verified exact-SHA review requests changes")
            if len(reviewers) < current.required_reviews:
                pending.append("Independent exact-SHA approvals required: " + str(current.required_reviews))
        if authorization is None and effect != Effect.DENY:
            pending.append("Explicit exact-operation operator authorization required; credentials grant no rights")
        elif authorization is not None and effect != Effect.DENY and not self._verified(authorization.evidence, "operation", self.authorization_subject(current, qualifications)):
            pending.append("Exact-operation operator identity/provenance/authorization is unverified")
        if effect == Effect.ALLOW and pending:
            effect = Effect.UNKNOWN
        return Decision(effect, current, digest(current), tuple(reasons), current.required_checks,
                        current.required_reviews, tuple(pending))

    # Small named extension surface; no hidden invocation of Git/CI/PR tools.
    def determine_branch(self, task: Task) -> Plan:
        return self.plan(task, Request(Operation.BRANCH))

    def determine_validation(self, task: Task) -> Plan:
        return self.plan(task, Request(Operation.VALIDATE))

    def determine_commit(self, task: Task, summary: str) -> Plan:
        return self.plan(task, Request(Operation.COMMIT, summary=summary))

    def determine_pr(self, task: Task, summary: str) -> Plan:
        return self.plan(task, Request(Operation.PR, summary=summary))

    def authorize_merge(self, task: Task, authorization: Authorization | None = None) -> Decision:
        return self.decide(self.plan(task, Request(Operation.MERGE)), authorization)
