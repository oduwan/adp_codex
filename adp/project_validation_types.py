"""Project-owned check observations; no command, runtime or merge authority."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .guard_types import Attestation
from .policy_types import OutcomeCount


class Phase(StrEnum):
    BEFORE_PR = "BEFORE_PR"
    AFTER_PR = "AFTER_PR"


class ResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    SKIP = "SKIP"
    NOTRUN = "NOTRUN"
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class RequiredCheck:
    name: str
    provider: str
    origin: str
    phase: Phase
    denominator: int | None = None
    native_record_is_attempt: bool = False


@dataclass(frozen=True)
class EvidencePolicy:
    policy_digest: str
    checks: tuple[RequiredCheck, ...]
    observed_at: int
    expires_at: int
    maximum_age: int = 300
    action_id: str | None = None
    evidence: Attestation | None = None
    result_maximum_age: int | None = None


@dataclass(frozen=True)
class PullIdentity:
    id: str
    number: int
    repository_id: str


@dataclass(frozen=True)
class EvidenceRequest:
    repository_id: str
    source_ref: str
    revision: str
    policy_digest: str
    phase: Phase
    task_id: str
    generation: int
    task_epoch: int
    iteration: int
    pull: PullIdentity | None = None


@dataclass(frozen=True)
class ObservationQuery:
    request: EvidenceRequest
    observation_id: str
    budget_ms: int = 1000
    action_key: str | None = None


@dataclass(frozen=True)
class ProjectResult:
    name: str
    provider: str
    origin: str
    repository_id: str
    revision: str
    run_id: str
    attempt_id: str | None
    status: ResultStatus
    reported_at: int | None
    complete: bool = True
    current: bool = True
    denominator: int | None = None
    counts: tuple[OutcomeCount, ...] = ()
    quarantined: int = 0
    provider_status: str = "unavailable"


@dataclass(frozen=True)
class ProjectObservation:
    query_digest: str
    observed_at: int
    complete: bool
    results: tuple[ProjectResult, ...]
    coverage: str = "COMPLETE"
    evidence: Attestation | None = None
    action_key: str | None = None


@dataclass(frozen=True)
class EvidenceGate:
    request: EvidenceRequest
    status: ResultStatus
    results: tuple[ProjectResult, ...]
    missing: tuple[str, ...]
    complete: bool
    reason: str
    evidence: str

    @property
    def qualified(self) -> bool:
        """Qualifies this phase only, never independent review or final acceptance."""
        return self.status == ResultStatus.PASS and self.complete and not self.missing


class ProjectEvidenceSource(Protocol):
    def observe(self, query: ObservationQuery) -> ProjectObservation: ...


class ProjectValidationAction(Protocol):
    """Trusted project-owned integration; ADP does not prepare its environment."""
    def request(self, request: EvidenceRequest, action_id: str, key: str) -> None: ...
