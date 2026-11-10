"""Freeze original scope, assess conserved proposals and admit read-only packets.

This independent #22 slice has no worker, Git, CI, issue-edit, PR, merge or
report executor. M1/M2/M5 execution is not replaced by an additional journal.
"""
from __future__ import annotations

import os
import stat
import time
from dataclasses import replace
from pathlib import Path

from .config import safe_path
from .discovery import DependencyPlanner
from .discovery_schema import (compact, digest, exact, json_value, key, text, typed,
    validate_identity, validate_issue, validate_repository, validate_snapshot)
from .discovery_types import Identity, Status
from .execution_privacy import credential_shaped
from .guard_types import Attestation, data
from .policy import PolicyProvider
from .policy_schema import product_path
from .schema import KEY, encode, integer, require, string
from .storage import atomic, locked
from .ticket_types import (ChangeKind, Clause, CodexPacket, OriginalScope, OriginalTicket,
    PreparationResult, PreparationReview, Proposal, ScopeAdditionApproval)

MAX_ARTIFACT = 1024 * 1024
MAX_ARTIFACTS = 64
MAX_ARCHIVE = 16 * 1024 * 1024
ORIGINAL = "ticket-original:"
PACKET = "ticket-packet:"
PREPARATION = "ticket-preparation:"


def _hash(value):
    return digest(value)


def _receipt(evidence, authority, purpose, subject, excluded=()):
    if type(evidence) is not Attestation or authority is None:
        return False
    string(evidence.reviewer, 128)
    string(evidence.reference, 512)
    return (evidence.subject == subject and evidence.reviewer not in excluded
            and authority.verify(evidence, purpose=purpose, subject=subject) is True)


def _fresh(start, end, now):
    integer(start)
    integer(end)
    return start <= now <= end and 0 < end - start <= 3600


def _clauses(values):
    require(type(values) is tuple and 1 <= len(values) <= 64, "Bounded original clauses required")
    compact(tuple(c.id for c in values), 64, 128)
    for clause in values:
        require(type(clause) is Clause and clause.kind in
                {"OBJECTIVE", "ACCEPTANCE", "INTERFACE", "CHECK", "DEPENDENCY"}, "Unknown scope clause")
        string(clause.text, 2048)


def _paths(values):
    compact(values, 32, 240)
    for path in values:
        product_path(path)


def _identities(values):
    require(type(values) is tuple and len(values) <= 64 and len(set(values)) == len(values), "Invalid dependency identities")
    for value in values:
        validate_identity(value)


def original_scope_subject(scope: OriginalScope) -> str:
    require(type(scope) is OriginalScope, "Expected original scope interpretation")
    return _hash({"domain": "ticket/original-scope", "scope": data(replace(scope, evidence=None))})


def change_digest(change) -> str:
    return _hash({"domain": "ticket/change", "change": data(change)})


def addition_subject(approval: ScopeAdditionApproval) -> str:
    require(type(approval) is ScopeAdditionApproval, "Expected specific external scope approval")
    return _hash({"domain": "ticket/scope-addition", "approval": data(replace(approval, evidence=None))})


def preparation_subject(original, scope, proposal, review, track) -> str:
    """Bind original, complete diff/interpretation, policy and actual M4 context."""
    return _hash({"domain": "ticket/preparation", "original": data(original),
        "scope": data(scope), "proposal": data(proposal),
        "review": data(replace(review, evidence=None)), "track": data(track)})


def preparation_value(original, scope, proposal, review, additions, track):
    return {"schema_version": 1, "original_reference": scope.original_reference,
        "scope": data(scope), "proposal": data(proposal), "review": data(review),
        "additions": [data(approval) for approval in additions], "track": data(track),
        "subject": preparation_subject(original, scope, proposal, review, track)}


class TicketArchive:
    """Private immutable evidence, never canonical coordination or authority.

    The first observed version for an identity cannot be overwritten. An external
    verifier must still authenticate that this was the originally admitted scope;
    creating another directory is not a way to obtain scope authorization.
    """
    def __init__(self, directory: Path, *, protected_roots: tuple[Path, ...]):
        require(type(protected_roots) is tuple and protected_roots, "Explicit protected product/memory roots required")
        self.directory = safe_path(directory)
        for root in protected_roots:
            root = safe_path(root)
            require(not self.directory.is_relative_to(root) and not root.is_relative_to(self.directory),
                    "Ticket evidence must be outside product and memory roots")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._directory()

    def _directory(self):
        info = safe_path(self.directory).stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700, "Private owned ticket evidence directory required")

    def _read(self, path):
        self._directory()
        info = safe_path(path).stat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= MAX_ARTIFACT,
                "Unsafe private ticket artifact")
        return path.read_bytes()

    def _put(self, prefix, value):
        raw = encode(value, MAX_ARTIFACT)
        fingerprint = _hash(value)
        path = self.directory / (prefix + fingerprint + ".json")
        existing = tuple(self.directory.iterdir())
        require(len(existing) <= MAX_ARTIFACTS + 1, "Ticket evidence capacity exhausted")
        size = 0
        for item in existing:
            if item.name == "lock":
                continue
            size += len(self._read(item))
        require(size + (0 if path.exists() else len(raw)) <= MAX_ARCHIVE,
                "Ticket evidence byte capacity exhausted")
        if path.exists():
            require(self._read(path) == raw, "Immutable ticket evidence differs")
        else:
            require(len(existing) < MAX_ARTIFACTS + 1, "Ticket evidence capacity exhausted")
            atomic(path, raw, replace=False)
        return fingerprint

    def freeze(self, snapshot, identity: Identity) -> str:
        validate_snapshot(snapshot)
        validate_identity(identity)
        matches = tuple(i for i in snapshot.issues if i.identity == identity)
        require(len(matches) == 1, "Original ticket must be uniquely observed")
        original = OriginalTicket(snapshot.repository, matches[0], snapshot.observed_at)
        value = data(original)
        with locked(self.directory):
            baseline = self.directory / ("baseline-" + key(identity) + ".json")
            if baseline.exists():
                saved = json_value(self._read(baseline), MAX_ARTIFACT)
                require(saved == value, "Original ticket already frozen; edited scope cannot replace it")
            fingerprint = self._put("original-", value)
            if not baseline.exists():
                # Immutable identity index, not a mutable task/run journal.
                atomic(baseline, encode(value, MAX_ARTIFACT), replace=False)
        return ORIGINAL + fingerprint

    def original(self, reference: str) -> OriginalTicket:
        require(type(reference) is str and reference.startswith(ORIGINAL)
                and KEY.fullmatch(reference[len(ORIGINAL):]), "Invalid opaque original reference")
        fingerprint = reference[len(ORIGINAL):]
        value = json_value(self._read(self.directory / ("original-" + fingerprint + ".json")), MAX_ARTIFACT)
        require(_hash(value) == fingerprint, "Original evidence hash mismatch")
        original = typed(OriginalTicket, value)
        require(original.schema_version == 1, "Unsupported original ticket schema")
        validate_repository(original.repository)
        validate_issue(original.issue, original.repository)
        integer(original.observed_at)
        baseline = json_value(self._read(self.directory / ("baseline-" + key(original.issue.identity) + ".json")), MAX_ARTIFACT)
        require(baseline == value, "Original identity baseline differs")
        return original

    def save_packet(self, packet: CodexPacket) -> str:
        with locked(self.directory):
            return PACKET + self._put("packet-", data(packet))

    def save_preparation(self, original, scope, proposal, review, additions, track):
        value = preparation_value(original, scope, proposal, review, additions, track)
        with locked(self.directory):
            return PREPARATION + self._put("preparation-", value)

    def preparation(self, reference):
        require(type(reference) is str and reference.startswith(PREPARATION)
                and KEY.fullmatch(reference[len(PREPARATION):]), "Invalid private preparation reference")
        fingerprint = reference[len(PREPARATION):]
        value = json_value(self._read(self.directory / ("preparation-" + fingerprint + ".json")), MAX_ARTIFACT)
        require(_hash(value) == fingerprint, "Preparation evidence hash mismatch")
        require(type(value) is dict and set(value) == {"schema_version", "original_reference", "scope", "proposal",
                "review", "additions", "track", "subject"} and value["schema_version"] == 1,
                "Invalid private preparation schema")
        return value


def validate_proposal(original, scope, proposal):
    """Structural conservation supplements independent semantic scope review."""
    require(type(scope) is OriginalScope and type(proposal) is Proposal, "Expected typed preparation inputs")
    typed(OriginalScope, data(scope))
    typed(Proposal, data(proposal))
    require(scope.original_reference == proposal.original_reference, "Foreign original scope")
    string(scope.goal, 2048)
    _clauses(scope.clauses)
    require(any(c.kind == "OBJECTIVE" for c in scope.clauses)
            and any(c.kind == "ACCEPTANCE" for c in scope.clauses), "Original goal and acceptance required")
    _paths(scope.allowed_paths)
    require(scope.allowed_paths, "Original allowed paths required")
    compact(scope.checks, 32, 128)
    _identities(scope.dependencies)
    require(original.issue.identity not in scope.dependencies, "Original task cannot depend on itself")
    require(KEY.fullmatch(proposal.expected_issue_revision) and KEY.fullmatch(proposal.policy_digest),
            "Exact issue and policy bindings required")
    compact(proposal.instructions, 16, 512)
    compact(proposal.exit_conditions, 16, 512)
    require(proposal.exit_conditions, "Explicit preparation exit conditions required")
    require(type(proposal.changes) is tuple and len(proposal.changes) <= 16, "Too many proposed changes")
    compact(tuple(c.id for c in proposal.changes), 16, 128)
    clauses, paths, checks, dependencies = list(scope.clauses), list(scope.allowed_paths), list(scope.checks), list(scope.dependencies)
    fields_seen = set()
    for change in proposal.changes:
        require(change.kind in set(ChangeKind) and change.field in {"EXPLANATION", "TITLE", "BODY", "PARTITION", "SCOPE"},
                "Unknown proposal classification or field")
        require(change.field not in fields_seen, "Conflicting proposed field edits")
        fields_seen.add(change.field)
        text(change.before)
        text(change.after)
        if change.field in {"TITLE", "BODY"}:
            require(change.before == getattr(original.issue, change.field.lower()), "Diff does not preserve original text")
        if change.kind != ChangeKind.ADDITION:
            require(not (change.added_clauses or change.added_paths or change.added_checks or change.added_dependencies),
                    "Unapproved functionality cannot hide inside a clarification or split")
        else:
            require(change.field == "SCOPE" and change.added_clauses, "Scope addition must identify exact added functionality")
            _clauses(change.added_clauses)
            _paths(change.added_paths)
            compact(change.added_checks, 32, 128)
            _identities(change.added_dependencies)
            clauses.extend(change.added_clauses)
            paths.extend(change.added_paths)
            checks.extend(change.added_checks)
            dependencies.extend(change.added_dependencies)
    _clauses(tuple(clauses))
    _paths(tuple(paths))
    compact(tuple(checks), 32, 128)
    _identities(tuple(dependencies))
    require(type(proposal.parts) is tuple and 1 <= len(proposal.parts) <= 16, "Bounded prepared parts required")
    compact(tuple(p.id for p in proposal.parts), 16, 128)
    claimed = []
    graph = {part.id: set(part.prerequisites) for part in proposal.parts}
    for part in proposal.parts:
        compact(part.clauses, 64, 128)
        require(part.clauses, "Empty split part")
        compact(part.prerequisites, 16, 128)
        require(graph[part.id] <= graph.keys() and part.id not in graph[part.id], "Invalid split dependency")
        claimed.extend(part.clauses)
    require(len(claimed) == len(set(claimed)) and set(claimed) == {c.id for c in clauses},
            "Split must conserve every original clause exactly once, without extra scope")
    order, remaining = [], dict(graph)
    while remaining:
        ready = sorted(node for node, deps in remaining.items() if deps <= set(order))
        require(ready, "Split dependency cycle")
        order.extend(ready)
        for node in ready:
            del remaining[node]
    if len(proposal.parts) > 1:
        require(any(c.kind == ChangeKind.SPLIT and c.field == "PARTITION" for c in proposal.changes),
                "Split requires independent scope-conservation assessment")
    return tuple(clauses), tuple(paths), tuple(checks), tuple(dependencies)


class TicketPreparer:
    """Read-only, independently assessed admission; never an execution engine."""
    def __init__(self, *, adapters, planner, policy, authority, archive, clock=None):
        require(type(adapters) is tuple and 1 <= len(adapters) <= 16, "Explicit bounded discovery adapters required")
        require(type(planner) is DependencyPlanner and type(policy) is PolicyProvider
                and type(archive) is TicketArchive, "Use accepted M3/M4 and private original archive")
        self.adapters, self.planner, self.policy = adapters, planner, policy
        self.authority, self.archive = authority, archive
        self.clock = clock or (lambda: int(time.time()))

    def observe(self, *, reviews=(), previous=None):
        snapshots = tuple(adapter.discover() for adapter in self.adapters)
        return self.planner.plan(snapshots, reviews=reviews, previous=previous)

    def prepare(self, scope, proposal, review, *, readiness_reviews=(), additions=(), previous=None):
        require(type(scope) is OriginalScope and type(proposal) is Proposal, "Expected typed preparation inputs")
        original = self.archive.original(scope.original_reference)
        clauses, paths, checks, dependencies = validate_proposal(original, scope, proposal)
        now = self.clock()
        integer(now)
        require(type(review) is PreparationReview, "Independent preparation review required")
        typed(PreparationReview, data(review))
        string(review.preparer, 128)
        excluded = (*original.issue.authors, review.preparer)
        if not _receipt(scope.evidence, self.authority, "ticket/original-scope", original_scope_subject(scope), excluded):
            return PreparationResult(Status.BLOCKED_OPERATOR, ("Original scope interpretation is not independently authenticated",))
        if any(c.kind == ChangeKind.UNKNOWN for c in proposal.changes):
            return PreparationResult(Status.BLOCKED_OPERATOR, ("Unclassified change requires a concrete external scope decision",))
        require(type(additions) is tuple and len(additions) <= 16, "Invalid external additions")
        for approval in additions:
            require(type(approval) is ScopeAdditionApproval, "Expected typed external scope approval")
            typed(ScopeAdditionApproval, data(approval))
        require(len({a.change_id for a in additions}) == len(additions), "Conflicting scope approvals")
        needed = {c.id: c for c in proposal.changes if c.kind == ChangeKind.ADDITION}
        require({a.change_id for a in additions} <= needed.keys(), "Unrelated scope approval")
        for change_id, change in needed.items():
            approval = next((a for a in additions if a.change_id == change_id), None)
            if (type(approval) is not ScopeAdditionApproval or approval.original_reference != scope.original_reference
                    or approval.change_digest != change_digest(change)
                    or not _fresh(approval.observed_at, approval.expires_at, now)
                    or not _receipt(approval.evidence, self.authority, "ticket/scope-addition", addition_subject(approval))):
                return PreparationResult(Status.BLOCKED_OPERATOR, ("Specific external operator approval of added scope is missing",))
        track = self.observe(reviews=readiness_reviews, previous=previous)
        candidates = tuple(c for c in track.candidates if c.identity == original.issue.identity)
        if len(candidates) != 1:
            return PreparationResult(Status.UNKNOWN, ("Original task is absent or ambiguous in refreshed track",))
        candidate = candidates[0]
        if candidate.status != Status.READY:
            return PreparationResult(candidate.status, candidate.reasons)
        if candidate.issue.revision != proposal.expected_issue_revision:
            return PreparationResult(Status.UNKNOWN, ("Prepared issue version is stale",))
        expected_title, expected_body = original.issue.title, original.issue.body
        for change in proposal.changes:
            if change.field == "TITLE":
                expected_title = change.after
            elif change.field == "BODY":
                expected_body = change.after
        if (candidate.issue.title, candidate.issue.body) != (expected_title, expected_body):
            return PreparationResult(Status.UNKNOWN, ("Current issue differs from the frozen original and exact proposed diff",))
        if tuple(candidate.prerequisites) != tuple(sorted(dependencies)):
            return PreparationResult(Status.BLOCKED_OPERATOR, ("Refreshed dependencies differ from approved original scope",))
        inspection = self.policy.inspect_repository()
        source = inspection.snapshot
        if (inspection.conflicts or not inspection.sources or inspection.digest != proposal.policy_digest
                or (source.repository_id, source.source_ref, source.revision) !=
                (candidate.repository.id, candidate.repository.checkout_ref, candidate.repository.checkout_sha)):
            return PreparationResult(Status.BLOCKED_OPERATOR, ("Project policy or exact repository/ref/source binding is unavailable or changed",))
        required_checks = tuple(sorted({name for claim in inspection.sources for name in claim.rules.checks}))
        if set(checks) != set(required_checks):
            return PreparationResult(Status.BLOCKED_OPERATOR, ("Original/project-prescribed check identities differ; do not invent or remove checks",))
        subject = preparation_subject(original, scope, proposal, review, track)
        if (not _fresh(review.observed_at, review.expires_at, now)
                or not _receipt(review.evidence, self.authority, "ticket/preparation", subject, excluded)):
            return PreparationResult(Status.BLOCKED_OPERATOR, ("Independent exact-context preparation review is missing or stale",))
        current_reviews = tuple(r for r in candidate.reviews
            if self.planner._verified(track.snapshots, candidate.issue, r, now))
        acceptance = tuple(c.text for c in clauses if c.kind == "ACCEPTANCE")
        if not any(r.scope == scope.goal and r.acceptance == acceptance for r in current_reviews):
            return PreparationResult(Status.BLOCKED_OPERATOR, ("READY assessment does not preserve the approved original acceptance",))
        require(candidate.identity in track.order and not track.cycles, "Ready task is not in a complete dependency DAG")
        exact(source.revision, False)
        preparation_reference = PREPARATION + _hash(preparation_value(original, scope, proposal, review, additions, track))
        packet = CodexPacket(candidate.identity, scope.original_reference, original.issue.revision,
            candidate.issue.revision, candidate.repository, source.source_ref, source.revision,
            inspection.digest, subject, preparation_reference, scope.goal, clauses, paths, checks, dependencies,
            proposal.parts, proposal.instructions, proposal.exit_conditions)
        require(not credential_shaped(data(packet)), "Sensitive preparation output refused; retain original privately")
        self.archive.save_preparation(original, scope, proposal, review, additions, track)
        reference = self.archive.save_packet(packet)
        return PreparationResult(Status.READY, ("Prepared scope only; execution and dependent integration remain blocked",), packet, reference)

    def submit_ticket_changes(self, *args, **kwargs):
        return PreparationResult(Status.BLOCKED_DEPENDENCY,
            ("No accepted owner/generation/Progress-Guard-fenced ticket-effect integration; proposal only",))

    def execute(self, *args, **kwargs):
        return PreparationResult(Status.BLOCKED_DEPENDENCY,
            ("Project evidence #21 and GitHub execution #16 are not accepted integration dependencies",))


def ready_window(track, identities: tuple[Identity, ...], *, consumed: tuple[Identity, ...] = ()):
    """Bounded proposal of current READY work; not a scheduler or progress writer."""
    from .discovery_schema import validate_track
    validate_track(track)
    _identities(identities)
    _identities(consumed)
    require(1 <= len(identities) <= 8, "Bounded admitted track window required")
    selected = {c.identity for c in track.candidates if c.status == Status.READY and c.observed}
    return tuple(identity for identity in track.order
                 if identity in identities and identity in selected and identity not in consumed)
