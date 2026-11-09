"""Frozen discovery observations and planning proposals; no execution rights."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .guard_types import Attestation


class Status(StrEnum):
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
    NEEDS_SPEC = "NEEDS_SPEC"
    BLOCKED_OPERATOR = "BLOCKED_OPERATOR"
    DONE = "DONE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, order=True)
class Identity:
    repository_id: str
    issue_id: str
    forge: str = "github"


@dataclass(frozen=True)
class Repository:
    id: str
    name: str
    url: str
    memory_id: str | None = None
    checkout_ref: str | None = None
    checkout_sha: str | None = None


@dataclass(frozen=True)
class Target:
    repository: str
    number: int
    issue_id: str | None = None


@dataclass(frozen=True)
class Relation:
    kind: str
    target: Target
    confidence: str
    source: str


@dataclass(frozen=True)
class Text:
    id: str
    body: str
    author: str
    updated_at: str
    source: str


@dataclass(frozen=True)
class Issue:
    identity: Identity
    number: int
    url: str
    title: str
    body: str
    state: str
    state_reason: str | None
    updated_at: str
    revision: str
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    authors: tuple[str, ...]
    comments: tuple[Text, ...]
    relations: tuple[Relation, ...]
    notices: tuple[str, ...] = ()


@dataclass(frozen=True)
class PullRequest:
    identity: Identity
    number: int
    url: str
    state: str
    updated_at: str
    revision: str
    head_sha: str | None
    head_ref: str | None
    head_repository_id: str | None
    base_sha: str | None
    base_ref: str | None
    merged: bool | None
    draft: bool | None


@dataclass(frozen=True)
class Coverage:
    name: str
    status: str
    source: str
    digest: str
    pages: int
    detail: str = ""
    retry_after: int | None = None


@dataclass(frozen=True)
class Snapshot:
    repository: Repository
    issues: tuple[Issue, ...]
    pulls: tuple[PullRequest, ...]
    coverage: tuple[Coverage, ...]
    observed_at: int
    schema_version: int = 1
    kind: str = "DISCOVERY"


@dataclass(frozen=True)
class ReadinessReview:
    identity: Identity
    scope: str
    acceptance: tuple[str, ...]
    policy_references: tuple[str, ...]
    specification: str = "UNKNOWN"
    policy: str = "UNKNOWN"
    completed: bool = False
    duplicate_of: Identity | None = None
    active_prs: tuple[Identity, ...] = ()
    confirmed_dependencies: tuple[Identity, ...] = ()
    dismissed_inferences: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    observed_at: int = 0
    expires_at: int = 0
    evidence: Attestation | None = None


class ReadinessAuthority(Protocol):
    """Trusted independent assessment of scope/disposition, never Git authority.

    Authenticate canonical reviewer, independence, provenance, and the exact
    discovery/readiness subject. An issue author cannot self-approve readiness.
    """
    def verify(self, evidence: Attestation, *, purpose: str, subject: str) -> bool: ...


@dataclass(frozen=True)
class MemoryBinding:
    identity: Identity
    task_id: str


@dataclass(frozen=True)
class ProgressRecord:
    identity: Identity
    memory_repository_id: str
    checkpoint: str
    generation: int
    task_json: str


@dataclass(frozen=True)
class Candidate:
    identity: Identity
    issue: Issue
    repository: Repository
    status: Status
    reasons: tuple[str, ...]
    prerequisites: tuple[Identity, ...]
    pull_heads: tuple[tuple[str, str | None], ...]
    progress: tuple[ProgressRecord, ...]
    reviews: tuple[ReadinessReview, ...]
    observed: bool = True
    head_history: tuple[tuple[str, str | None], ...] = ()
    observation_history: tuple[str, ...] = ()


@dataclass(frozen=True)
class Track:
    snapshots: tuple[Snapshot, ...]
    candidates: tuple[Candidate, ...]
    order: tuple[Identity, ...]
    cycles: tuple[tuple[Identity, ...], ...]
    diagnostics: tuple[str, ...]
    previous_digest: str | None = None
    schema_version: int = 1
    kind: str = "TRACK"
    mode: str = "READ_ONLY"
    execution_authority: str = "UNKNOWN"


class DiscoveryAdapter(Protocol):
    def discover(self) -> Snapshot: ...
