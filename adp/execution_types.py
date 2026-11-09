"""Bounded Conductor contracts. Runtime receipts never grant operator rights."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .discovery_types import Identity, Track
from .guard_types import Attestation, ForensicReport, Outcome, Requirement
from .policy_types import Authorization, OutcomeCount, Plan


class Role(StrEnum):
    RESEARCH = "RESEARCH"
    DEVELOPER = "DEVELOPER"
    REVIEWER = "REVIEWER"
    FORENSIC = "FORENSIC"
    COORDINATION = "COORDINATION"


class RuntimeStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED_RUNTIME = "UNSUPPORTED_RUNTIME"


@dataclass(frozen=True)
class Capabilities:
    backend: str
    host: str
    version: str
    independent_contexts: bool
    workspace_write: bool
    observe: bool
    cancel: bool
    maximum_parallel: int
    reason: str = ""


@dataclass(frozen=True)
class WorkerRequest:
    id: str
    task_id: str
    generation: int
    role: Role
    revision: str
    workspace: str
    prompt: str
    seconds: int
    deadline: int | None = None
    samples: int = 1000
    payload_bytes: int = 1048576


@dataclass(frozen=True)
class WorkerResult:
    outcome: Outcome
    approved: bool
    criteria: tuple[str, ...]
    summary: str
    forensic: ForensicReport | None = None


@dataclass(frozen=True)
class RuntimeObservation:
    request_id: str
    host: str
    status: RuntimeStatus
    context_id: str | None
    result: WorkerResult | None
    receipt: str
    elapsed_seconds: int
    request_digest: str | None = None
    samples: int = 0
    payload_bytes: int = 0
    stopped: bool | None = None


class WorkerRuntime(Protocol):
    def capabilities(self) -> Capabilities: ...
    def dispatch(self, request: WorkerRequest) -> RuntimeObservation: ...
    def observe(self, request_id: str) -> RuntimeObservation: ...
    def wait(self, request_id: str) -> RuntimeObservation: ...
    def cancel(self, request_id: str) -> RuntimeObservation: ...


@dataclass(frozen=True)
class Admission:
    identity: Identity
    task_id: str
    branch_slug: str
    workspace_key: str
    expected_revision: str
    requirement: Requirement
    product_goal: str
    summary: str
    allowed_paths: tuple[str, ...]
    iteration_kind: str = "PRODUCT"
    seconds: int = 300


class ExecutionAuthority(Protocol):
    """Trusted operator/independent evidence service, outside worker contexts.

    grant is an approval request, not automatic authority. Implementations must
    verify accepted policy/role/provenance before supplying a receipt; None denies.
    Workers must never receive this service or its credentials.
    """
    def grant(self, *, purpose: str, subject: str, context: dict | None = None) -> Attestation | None: ...
    def verify(self, evidence: Attestation, *, purpose: str, subject: str) -> bool: ...


class ReadinessService(Protocol):
    def observe(self) -> Track: ...


class PolicyAuthorizer(Protocol):
    def authorize(self, plan: Plan) -> Authorization | None: ...


@dataclass(frozen=True)
class CheckCommand:
    name: str
    argv: tuple[str, ...]
    seconds: int
    denominator: int


@dataclass(frozen=True)
class ValidationResult:
    name: str
    revision: str
    outcome: Outcome
    denominator: int
    passed: int
    evidence: str
    counts: tuple[OutcomeCount, ...] = ()
    quarantined: int = 0


@dataclass(frozen=True)
class ExternalObservation:
    status: str
    reference: str | None = None
    revision: str | None = None
    body_digest: str | None = None


class ForgeBackend(Protocol):
    """No implicit network authority. Unknown delivery must never be retried.

    observe must be authoritative: ABSENT is safe only before first submission
    or with a backend's atomic idempotency facility; eventual search is UNKNOWN.
    """
    def observe(self, key: str, operation: str, payload: dict, *, attempted: bool = False) -> ExternalObservation: ...
    def submit(self, key: str, operation: str, payload: dict, *, authorization: Attestation | None = None,
               plan_digest: str | None = None) -> ExternalObservation: ...
