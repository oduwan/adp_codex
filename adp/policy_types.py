"""Data-only Git policy contracts. A plan is never a Git executor."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .guard_types import Attestation, Baseline, Decision as GuardDecision


class Effect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class Operation(StrEnum):
    BRANCH = "BRANCH"
    COMMIT = "COMMIT"
    STAGE = "STAGE"
    EDIT = "EDIT"
    INSPECT = "INSPECT"
    VALIDATE = "VALIDATE"
    PR = "PR"
    PUSH = "PUSH"
    MERGE = "MERGE"
    RELEASE = "RELEASE"
    DEPLOY = "DEPLOY"
    REPORT = "REPORT"
    FORCE_PUSH = "FORCE_PUSH"
    REBASE = "REBASE"
    REWRITE = "REWRITE"


class SourceKind(StrEnum):
    OPERATOR = "OPERATOR"
    GOVERNANCE = "GOVERNANCE"
    CONTRACT = "CONTRACT"
    PROFILE = "PROFILE"
    UNTRUSTED = "UNTRUSTED"
    PROTECTION = "PROTECTION"
    INVARIANT = "INVARIANT"


@dataclass(frozen=True)
class Permission:
    operation: Operation
    effect: Effect


@dataclass(frozen=True)
class Rules:
    permissions: tuple[Permission, ...] = ()
    base_branch: str | None = None
    branch_template: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    subject_limit: int | None = None
    pr_title_template: str | None = None
    pr_draft: bool | None = None
    merge_method: str | None = None
    release_template: str | None = None
    environments: tuple[str, ...] | None = None
    checks: tuple[str, ...] = ()
    reviews: int | None = None
    gate_operations: tuple[Operation, ...] = ()


@dataclass(frozen=True)
class Document:
    reference: str
    kind: SourceKind
    digest: str
    profile: Rules | None = None


@dataclass(frozen=True)
class Ref:
    name: str
    revision: str


@dataclass(frozen=True)
class RepositorySnapshot:
    repository_id: str
    remote: str
    remote_fingerprint: str
    source_ref: str
    revision: str
    index_digest: str
    worktree_clean: bool
    local_refs: tuple[Ref, ...]
    remote_refs: tuple[Ref, ...]
    documents: tuple[Document, ...]
    remote_refs_known: bool = True
    diagnostics: tuple[str, ...] = ()
    push_relation: str = "UNKNOWN"
    worktree_digest: str | None = None


@dataclass(frozen=True)
class SourceClaim:
    kind: SourceKind
    reference: str
    document_digest: str
    rules: Rules
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None


@dataclass(frozen=True)
class Protection:
    ref: str
    revision: str | None
    known: bool
    push_allowed: bool
    merge_allowed: bool
    checks: tuple[str, ...]
    reviews: int
    merge_methods: tuple[str, ...]
    unsupported: tuple[str, ...]
    reference: str
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None
    mergeable_methods: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Task:
    repository_id: str
    task_id: str
    branch_slug: str
    revision: str
    source_ref: str
    requirement_id: str
    generation: int
    task_epoch: int
    iteration: int
    authors: tuple[str, ...]


@dataclass(frozen=True)
class Request:
    operation: Operation
    summary: str = ""
    version: str = ""
    environment: str = ""
    paths: tuple[str, ...] = ()
    report_target: str = ""
    report_body: str = ""


@dataclass(frozen=True)
class Safety:
    guard: GuardDecision
    owns_memory: bool
    authors: tuple[str, ...]
    memory_head: str
    approval: Baseline | None = None


class RepositoryAdapter(Protocol):
    def inspect(self) -> RepositorySnapshot: ...


class SafetyAdapter(Protocol):
    """Trusted observational port: read current M1 ownership and M2 inspect."""
    def observe(self, task: Task) -> Safety: ...


class PolicyAuthority(Protocol):
    """Verify canonical principal, purpose, provenance and exact subject offline.

    `policy/operation` and `policy/operator` need operator authority;
    governance/profile/contract/protection need accepted repository provenance;
    check/review need authenticated validation/independent-review provenance.
    This interface is observational. No credential or document text is a grant.
    """
    def verify(self, evidence: Attestation, *, purpose: str, subject: str) -> bool: ...


@dataclass(frozen=True)
class Provenance:
    reference: str
    kind: SourceKind
    digest: str
    status: str
    reason: str


@dataclass(frozen=True)
class Inspection:
    snapshot: RepositorySnapshot
    sources: tuple[SourceClaim, ...]
    provenance: tuple[Provenance, ...]
    conflicts: tuple[str, ...]
    digest: str


@dataclass(frozen=True)
class BranchPlan:
    name: str
    start_revision: str
    reuse: bool


@dataclass(frozen=True)
class CommitPlan:
    subject: str
    body: str
    index_digest: str


@dataclass(frozen=True)
class StagePlan:
    paths: tuple[str, ...]
    index_digest: str
    worktree_digest: str


@dataclass(frozen=True)
class EditPlan:
    paths: tuple[str, ...]
    worktree_digest: str
    request_id: str


@dataclass(frozen=True)
class ReportPlan:
    target: str
    body: str


@dataclass(frozen=True)
class ValidationPlan:
    checks: tuple[str, ...]


@dataclass(frozen=True)
class PullRequestPlan:
    head_ref: str
    base_ref: str
    title: str
    draft: bool


@dataclass(frozen=True)
class PushPlan:
    remote: str
    target_ref: str
    revision: str
    expected_revision: str | None
    force: bool = False


@dataclass(frozen=True)
class MergePlan:
    head_ref: str
    base_ref: str
    revision: str
    expected_base: str
    method: str


@dataclass(frozen=True)
class ReleasePlan:
    tag_ref: str
    revision: str


@dataclass(frozen=True)
class DeploymentPlan:
    environment: str
    revision: str


Payload = BranchPlan | CommitPlan | StagePlan | EditPlan | ReportPlan | ValidationPlan | PullRequestPlan | PushPlan | MergePlan | ReleasePlan | DeploymentPlan


@dataclass(frozen=True)
class Plan:
    task: Task
    request: Request
    snapshot_digest: str
    policy_digest: str
    remote: str
    remote_fingerprint: str
    target_ref: str
    expected_target: str | None
    payload: Payload | None
    policy_effect: Effect
    reasons: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    required_checks: tuple[str, ...]
    required_reviews: int
    gated: bool
    safety: Safety | None


@dataclass(frozen=True)
class OutcomeCount:
    outcome: str
    count: int


@dataclass(frozen=True)
class Check:
    name: str
    revision: str
    denominator: int
    counts: tuple[OutcomeCount, ...]
    quarantined: int
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None


@dataclass(frozen=True)
class Review:
    reviewer: str
    revision: str
    approved: bool
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None


@dataclass(frozen=True)
class Qualifications:
    checks: tuple[Check, ...] = ()
    reviews: tuple[Review, ...] = ()


@dataclass(frozen=True)
class ProjectCheck:
    """Authenticated #21 evidence; unknown case counts remain unknown."""
    name: str
    revision: str
    phase: str
    request_digest: str
    observation_digest: str
    provider: str
    origin: str
    run_id: str
    attempt_id: str | None
    status: str
    denominator: int | None
    counts: tuple[OutcomeCount, ...]
    quarantined: int
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None


@dataclass(frozen=True)
class ProjectQualifications:
    """Separate opt-in representation; legacy authorization bytes are unchanged.

    policy_evidence authenticates the complete phase inventory and the project's
    acceptance of job-only evidence. Each check also needs its own provenance.
    """
    checks: tuple[ProjectCheck, ...]
    reviews: tuple[Review, ...]
    required: tuple[tuple[str, str], ...]
    policy_evidence: Attestation | None = None


@dataclass(frozen=True)
class Authorization:
    evidence: Attestation
    qualifications: Qualifications | ProjectQualifications = Qualifications()


@dataclass(frozen=True)
class Decision:
    effect: Effect
    plan: Plan
    plan_digest: str
    reasons: tuple[str, ...]
    required_checks: tuple[str, ...]
    required_reviews: int
    operator_decisions: tuple[str, ...]


class GitWorkflowProvider(Protocol):
    def inspect_repository(self) -> Inspection: ...
    def plan(self, task: Task, request: Request) -> Plan: ...
    def decide(self, plan: Plan, authorization: Authorization | None = None) -> Decision: ...
