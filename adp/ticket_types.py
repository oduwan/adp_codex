"""Preparation-only contracts; ticket text and packets confer no execution rights."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .discovery_types import Identity, Issue, Repository, Snapshot, Status
from .guard_types import Attestation


class ChangeKind(StrEnum):
    CLARIFICATION = "IN_SCOPE_CLARIFICATION"
    SPLIT = "IN_SCOPE_SPLIT"
    ADDITION = "OUT_OF_SCOPE_ADDITION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Clause:
    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class OriginalTicket:
    repository: Repository
    issue: Issue
    observed_at: int
    schema_version: int = 1


@dataclass(frozen=True)
class OriginalScope:
    original_reference: str
    goal: str
    clauses: tuple[Clause, ...]
    allowed_paths: tuple[str, ...]
    checks: tuple[str, ...]
    dependencies: tuple[Identity, ...]
    evidence: Attestation | None = None


@dataclass(frozen=True)
class Part:
    id: str
    clauses: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class TicketChange:
    id: str
    kind: ChangeKind
    field: str
    before: str
    after: str
    added_clauses: tuple[Clause, ...] = ()
    added_paths: tuple[str, ...] = ()
    added_checks: tuple[str, ...] = ()
    added_dependencies: tuple[Identity, ...] = ()


@dataclass(frozen=True)
class Proposal:
    original_reference: str
    expected_issue_revision: str
    policy_digest: str
    parts: tuple[Part, ...]
    changes: tuple[TicketChange, ...] = ()
    instructions: tuple[str, ...] = ()
    exit_conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeAdditionApproval:
    change_id: str
    original_reference: str
    change_digest: str
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None


@dataclass(frozen=True)
class PreparationReview:
    preparer: str
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None


class PreparationAuthority(Protocol):
    """Authenticate canonical roles, provenance and the exact reviewed subject.

    ticket/original-scope: complete interpretation of the frozen original.
    ticket/preparation: independent scope classification/conservation, exact
    changes and specification assessment; never just a schema or hash check.
    ticket/scope-addition: external operator approval of this particular diff
    and added functionality, not delegated ticket editing or merge authority.
    No permissive implementation or text-based approval is supplied.
    """
    def verify(self, evidence: Attestation, *, purpose: str, subject: str) -> bool: ...


@dataclass(frozen=True)
class CodexPacket:
    identity: Identity
    original_reference: str
    original_issue_revision: str
    prepared_issue_revision: str
    repository: Repository
    base_ref: str
    base_sha: str
    policy_digest: str
    preparation_digest: str
    preparation_reference: str
    goal: str
    clauses: tuple[Clause, ...]
    allowed_paths: tuple[str, ...]
    checks: tuple[str, ...]
    dependencies: tuple[Identity, ...]
    parts: tuple[Part, ...]
    instructions: tuple[str, ...]
    exit_conditions: tuple[str, ...]
    execution_authority: str = "UNKNOWN"
    blocked_integrations: tuple[str, ...] = ("PROJECT_VALIDATION:#21", "GITHUB_EXECUTION:#16")
    schema_version: int = 1


@dataclass(frozen=True)
class PreparationResult:
    status: Status
    reasons: tuple[str, ...]
    packet: CodexPacket | None = None
    packet_reference: str | None = None


class TrackObserver(Protocol):
    """Accepted GET-only M4 adapters supply independently refreshed snapshots."""
    def discover(self) -> Snapshot: ...


@dataclass(frozen=True)
class DependencyEdit:
    dependency: Identity
    database_id: int
    add: bool
