"""Typed, data-only Progress Guard boundary; no execution or policy provider."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol, TypedDict


class DecisionKind(StrEnum):
    ALLOW = "ALLOW"
    FORENSIC_REQUIRED = "FORENSIC_REQUIRED"
    STOP_UNSAFE = "STOP_UNSAFE"
    OPERATOR_DECISION_REQUIRED = "OPERATOR_DECISION_REQUIRED"


class Outcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    SKIP = "SKIP"
    NOTRUN = "NOTRUN"
    UNKNOWN = "UNKNOWN"


class ActionKind(StrEnum):
    CHECK = "CHECK"
    CORRECTION = "CORRECTION"
    DIAGNOSTIC = "DIAGNOSTIC"
    REVIEW = "REVIEW"


class ProgressKind(StrEnum):
    CAUSE_NARROWED = "CAUSE_NARROWED"
    REQUIREMENT_VERIFIED = "REQUIREMENT_VERIFIED"
    DEPENDENCY_RESOLVED = "DEPENDENCY_RESOLVED"
    CORRECTION_APPROVED = "CORRECTION_APPROVED"


class Classification(StrEnum):
    PRODUCT_DEFECT = "PRODUCT_DEFECT"
    TEST_CORRUPTED = "TEST_CORRUPTED"
    INFRA_DEFECT = "INFRA_DEFECT"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    DEPENDENCY_DEFECT = "DEPENDENCY_DEFECT"
    UNCLASSIFIED = "UNCLASSIFIED"


@dataclass(frozen=True)
class Limits:
    failures: int = 3
    corrections: int = 2
    explorations: int = 2
    reviews: int = 3
    stalls: int = 3


@dataclass(frozen=True)
class Requirement:
    contract: str
    gate: str
    acceptance: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    limits: Limits = Limits()


@dataclass(frozen=True)
class Attestation:
    reviewer: str
    reference: str
    subject: str


class EvidenceAuthority(Protocol):
    """Trusted external verification, never inferred from a label in input data.

    Verify authenticated identity, role, provenance and exact subject. `admission`
    and `campaign` need operator authority; `progress` and `forensic` need an
    independent reviewer. The guard additionally excludes all recorded authors.
    Implementations must be observational and return an actual bool.
    """

    def verify(self, evidence: Attestation, *, purpose: str, subject: str) -> bool: ...


@dataclass(frozen=True)
class Action:
    actor: str
    kind: ActionKind
    hypothesis: str
    exit_criteria: str | None = None
    seconds: int = 300
    samples: int = 1000
    payload_bytes: int = 1048576


@dataclass(frozen=True)
class Progress:
    kind: ProgressKind
    fact: str
    evidence: tuple[str, ...]
    parent_cause: str | None = None


@dataclass(frozen=True)
class Observation:
    outcome: Outcome
    evidence: tuple[str, ...]
    unresolved: tuple[str, ...]
    progress: Progress | None = None
    finding: str | None = None
    risk: str | None = None
    elapsed_seconds: int = 0
    samples: int = 0
    payload_bytes: int = 0


class ForensicRequest(TypedDict):
    id: str
    round: int
    context: dict
    baseline: str
    excluded_authors: list[str]
    evidence: list[str]
    contract: str
    gate: str
    unresolved: list[str]
    counters: dict[str, int]
    hypothesis: str | None
    outcome: str | None
    observation_context: dict
    cause: str | None
    reason: str


@dataclass(frozen=True)
class ForensicPlan:
    action: str
    pass_means: str
    fail_means: str
    unknown_means: str
    stop_conditions: tuple[str, ...]
    seconds: int = 300
    samples: int = 1000
    payload_bytes: int = 1048576


@dataclass(frozen=True)
class ForensicReport:
    request_id: str
    classification: Classification
    evidence: tuple[str, ...]
    diagnosis: str
    plan: ForensicPlan | None = None


@dataclass(frozen=True)
class Campaign:
    inventory: tuple[str, ...]
    evidence_reference: str
    quarantined: tuple[str, ...] = ()
    seconds: int = 3600
    samples: int = 10000
    payload_bytes: int = 1048576


@dataclass(frozen=True)
class Baseline:
    requirement_id: str
    contract: str
    gate: str
    task_key: str
    revision: str | None
    iteration: int
    generation: int
    task_epoch: int
    sequence: int
    record_digest: str
    unresolved: tuple[str, ...]


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: str
    baseline: Baseline
    scope: str = "attempt"


@dataclass(frozen=True)
class Permit:
    token: str
    decision: Decision


@dataclass(frozen=True)
class CasePermit:
    token: str
    case_id: str
    decision: Decision


def data(value: object) -> dict:
    """Normalize dataclass tuples/enums into the bounded JSON representation."""
    import json
    from .errors import ADPError
    try:
        return json.loads(json.dumps(asdict(value), allow_nan=False))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ADPError("Malformed typed guard input") from exc
