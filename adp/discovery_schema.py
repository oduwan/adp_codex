"""Closed bounded preview schemas, independent from canonical memory schemas."""
from __future__ import annotations

import hashlib
import json
import re
import types
from dataclasses import fields as dc_fields, is_dataclass
from enum import Enum
from typing import get_args, get_origin, get_type_hints

from .errors import ADPError
from .guard_types import data
from .schema import JOB, KEY, bundle, encode, integer, require, string
from .git import SHA
from .discovery_types import (Candidate, Coverage, Identity, Issue, ProgressRecord,
    ReadinessReview, Repository, Snapshot, Status, Target, Track)

MAX_BYTES = 16 * 1024 * 1024
MAX_ITEMS = 256
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
COVERAGE = {"COMPLETE", "PARTIAL", "UNKNOWN", "FORBIDDEN", "RATE_LIMITED", "NOTRUN", "CHANGED"}


def digest(value: object) -> str:
    return hashlib.sha256(encode(data(value) if is_dataclass(value) else value, MAX_BYTES)).hexdigest()


def key(identity: Identity) -> str:
    validate_identity(identity)
    return digest(data(identity))


def json_value(raw: bytes, limit: int = MAX_BYTES):
    require(len(raw) <= limit, "Discovery JSON exceeds size limit")
    def pairs(items):
        result = {}
        for name, value in items:
            require(name not in result, "Duplicate discovery JSON key")
            result[name] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ADPError("Malformed discovery JSON") from exc


def typed(cls, value):
    """Load only the declared closed dataclass schema; no dynamic imports."""
    origin, args = get_origin(cls), get_args(cls)
    if origin is types.UnionType:
        for choice in args:
            try:
                return typed(choice, value)
            except ADPError:
                pass
        raise ADPError("Invalid discovery union value")
    if origin is tuple:
        require(type(value) is list and len(value) <= 4096, "Invalid bounded discovery list")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(typed(args[0], v) for v in value)
        require(len(value) == len(args), "Invalid discovery tuple")
        return tuple(typed(t, v) for t, v in zip(args, value))
    if cls is type(None):
        require(value is None, "Expected null")
        return None
    if isinstance(cls, type) and issubclass(cls, Enum):
        require(type(value) is str and value in set(cls), "Invalid discovery enum")
        return cls(value)
    if is_dataclass(cls):
        require(type(value) is dict and set(value) == {f.name for f in dc_fields(cls)}, "Invalid closed discovery fields")
        hints = get_type_hints(cls)
        return cls(**{name: typed(hints[name], v) for name, v in value.items()})
    require(cls in (str, int, bool) and type(value) is cls, "Invalid discovery primitive")
    return value


def validate_identity(identity):
    require(type(identity) is Identity and identity.forge == "github", "Invalid provider identity")
    string(identity.repository_id)
    string(identity.issue_id)


def exact(value, nullable=True):
    require(nullable and value is None or isinstance(value, str) and SHA.fullmatch(value), "Invalid exact discovery SHA")


def compact(values, maximum=32, length=512):
    require(type(values) is tuple and len(values) <= maximum and len(set(values)) == len(values), "Invalid bounded unique discovery values")
    for v in values:
        string(v, length)


def text(value, maximum=65536):
    require(type(value) is str and len(value.encode("utf-8")) <= maximum and "\x00" not in value, "Invalid untrusted text size")


def validate_repository(repo):
    require(type(repo) is Repository and NAME.fullmatch(repo.name), "Invalid GitHub repository name")
    string(repo.id)
    require(repo.url == "https://github.com/" + repo.name, "Repository URL/identity mismatch")
    if repo.memory_id is not None:
        string(repo.memory_id)
    if repo.checkout_ref is not None:
        string(repo.checkout_ref)
    exact(repo.checkout_sha)


def validate_target(target):
    require(type(target) is Target and NAME.fullmatch(target.repository), "Invalid relationship repository")
    integer(target.number, 1)
    if target.issue_id is not None:
        string(target.issue_id)


def validate_issue(issue, repo):
    require(type(issue) is Issue, "Expected typed issue")
    validate_identity(issue.identity)
    require(issue.identity.repository_id == repo.id, "Foreign issue identity")
    integer(issue.number, 1)
    require(issue.url == f"{repo.url}/issues/{issue.number}", "Issue URL mismatch")
    text(issue.title, 1024)
    text(issue.body)
    require(issue.state in ("open", "closed"), "Unknown issue state")
    if issue.state_reason is not None:
        string(issue.state_reason, 128)
    string(issue.updated_at, 64)
    require(KEY.fullmatch(issue.revision), "Invalid issue revision")
    compact(issue.labels, 64, 128)
    compact(issue.assignees, 32, 128)
    compact(issue.authors, 64, 128)
    compact(issue.notices, 256, 512)
    require(len(issue.comments) <= 256 and len(issue.relations) <= 256, "Issue metadata exceeds bounds")
    compact(tuple(c.id for c in issue.comments), 256)
    for comment in issue.comments:
        text(comment.body)
        string(comment.author, 128)
        string(comment.updated_at, 64)
        string(comment.source, 512)
    for relation in issue.relations:
        require(relation.kind in {"BLOCKED_BY", "SUB_ISSUE", "PULL_REQUEST", "DUPLICATE_OF", "SUPERSEDED_BY", "RELATED"}
                and relation.confidence in {"NATIVE", "INFERRED"}, "Invalid relationship kind/confidence")
        validate_target(relation.target)
        string(relation.source, 512)


def validate_snapshot(snapshot):
    require(type(snapshot) is Snapshot and snapshot.schema_version == 1 and snapshot.kind == "DISCOVERY", "Unsupported discovery schema")
    # Enforce field types even when a caller bypasses JSON loading.
    typed(Snapshot, data(snapshot))
    validate_repository(snapshot.repository)
    integer(snapshot.observed_at)
    require(len(snapshot.issues) <= MAX_ITEMS and len(snapshot.pulls) <= MAX_ITEMS
            and len(snapshot.coverage) <= 4096, "Inventory exceeds bounds")
    compact(tuple(i.identity.issue_id for i in snapshot.issues), MAX_ITEMS)
    compact(tuple(str(i.number) for i in snapshot.issues), MAX_ITEMS)
    compact(tuple(p.identity.issue_id for p in snapshot.pulls), MAX_ITEMS)
    require(not ({i.identity.issue_id for i in snapshot.issues} & {p.identity.issue_id for p in snapshot.pulls}), "Issue/PR identity collision")
    compact(tuple(str(p.number) for p in snapshot.pulls), MAX_ITEMS)
    for issue in snapshot.issues:
        validate_issue(issue, snapshot.repository)
    for pr in snapshot.pulls:
        validate_identity(pr.identity)
        require(pr.identity.repository_id == snapshot.repository.id, "Foreign PR identity")
        integer(pr.number, 1)
        require(pr.url == f"{snapshot.repository.url}/pull/{pr.number}", "PR URL mismatch")
        require(pr.state in {"open", "closed"}, "Unknown PR state")
        string(pr.updated_at, 64)
        require(KEY.fullmatch(pr.revision), "Invalid PR revision")
        exact(pr.head_sha)
        exact(pr.base_sha)
        for field in (pr.head_ref, pr.base_ref, pr.head_repository_id):
            if field is not None:
                string(field)
    compact(tuple(c.name for c in snapshot.coverage), 4096)
    for item in snapshot.coverage:
        require(item.status in COVERAGE and KEY.fullmatch(item.digest), "Invalid metadata coverage")
        string(item.source, 512)
        text(item.detail, 512)
        integer(item.pages)
        if item.retry_after is not None:
            integer(item.retry_after)
    encode(data(snapshot), MAX_BYTES)


def validate_review(review):
    require(type(review) is ReadinessReview, "Expected typed readiness review")
    typed(ReadinessReview, data(review))
    validate_identity(review.identity)
    text(review.scope, 2048)
    compact(review.acceptance, 16, 512)
    compact(review.policy_references, 16, 512)
    require(review.specification in {"KNOWN", "AMBIGUOUS", "UNKNOWN"}
            and review.policy in {"KNOWN", "DENIED", "UNKNOWN"}, "Invalid readiness assessment")
    require(len(review.confirmed_dependencies) <= 64 and len(review.active_prs) <= 32, "Too many confirmed dependencies/PRs")
    require(len(set(review.confirmed_dependencies)) == len(review.confirmed_dependencies)
            and len(set(review.active_prs)) == len(review.active_prs), "Duplicate assessed dependencies/PRs")
    for dep in (*review.confirmed_dependencies, *review.active_prs, *((review.duplicate_of,) if review.duplicate_of else ())):
        validate_identity(dep)
    compact(review.dismissed_inferences, 256, 64)
    compact(review.conflicts, 16, 512)
    integer(review.observed_at)
    integer(review.expires_at)
    if review.evidence is not None:
        string(review.evidence.reviewer, 128)
        string(review.evidence.reference, 512)
        require(KEY.fullmatch(review.evidence.subject), "Invalid readiness receipt subject")


def validate_progress(record):
    require(type(record) is ProgressRecord, "Expected typed retained progress")
    typed(ProgressRecord, data(record))
    validate_identity(record.identity)
    string(record.memory_repository_id)
    exact(record.checkpoint, False)
    integer(record.generation)
    task = json_value(record.task_json.encode(), 65536)
    require(type(task) is dict and task.get("repository_id") == record.memory_repository_id, "Retained task repository mismatch")
    assignments = task.get("assignments")
    require(type(assignments) is dict and all(type(job) is str and JOB.fullmatch(job) for job in assignments), "Malformed retained assignments")
    task_key = task.get("key")
    require(type(task_key) is str and KEY.fullmatch(task_key), "Invalid retained task key")
    # Reuse the accepted M1 task validator in a non-authoritative validation
    # envelope. This is temporary data, never a coordination checkpoint/write.
    state = {"schema_version": 1, "repository_id": record.memory_repository_id,
        "revision": 1, "generation": record.generation,
        "owner": {"id": "validation-only", "label": "historical", "token_hash": "0" * 64} if record.generation else None,
        "task_keys": [task_key], "assignment_sequence": max([0] + [int(job.split("-")[1]) for job in assignments])}
    bundle(state, {task_key: task}, record.memory_repository_id)


def validate_track(track):
    require(type(track) is Track and track.schema_version == 1 and track.kind == "TRACK"
            and track.mode == "READ_ONLY" and track.execution_authority == "UNKNOWN", "Invalid read-only track")
    typed(Track, data(track))
    require(len(track.snapshots) <= 16 and len(track.candidates) <= MAX_ITEMS, "Track exceeds bounds")
    for snapshot in track.snapshots:
        validate_snapshot(snapshot)
    compact(tuple(key(c.identity) for c in track.candidates), MAX_ITEMS, 64)
    observed = {i.identity: (s.repository, i) for s in track.snapshots for i in s.issues}
    for candidate in track.candidates:
        validate_identity(candidate.identity)
        require(candidate.identity == candidate.issue.identity, "Candidate identity mismatch")
        validate_repository(candidate.repository)
        require(candidate.repository.id == candidate.identity.repository_id, "Retained repository identity mismatch")
        validate_issue(candidate.issue, candidate.repository)
        if candidate.observed:
            require(observed.get(candidate.identity) == (candidate.repository, candidate.issue), "Observed candidate differs from its snapshot")
        for dependency in candidate.prerequisites:
            validate_identity(dependency)
        require(len(candidate.progress) <= 8 and len(candidate.reviews) <= 8, "Retained evidence capacity exhausted")
        require(len(candidate.head_history) <= 64 and len(candidate.observation_history) <= 8, "Retained observation capacity exhausted")
        for pr_key, sha in (*candidate.pull_heads, *candidate.head_history):
            require(KEY.fullmatch(pr_key), "Invalid retained PR identity")
            exact(sha)
        for revision in candidate.observation_history:
            require(KEY.fullmatch(revision), "Invalid retained observation digest")
        for record in candidate.progress:
            validate_progress(record)
            require(record.identity == candidate.identity, "Foreign retained progress")
        for review in candidate.reviews:
            validate_review(review)
            require(review.identity == candidate.identity, "Foreign retained review")
    for identity in track.order:
        validate_identity(identity)
    require(len(track.order) == len(set(track.order)) and set(track.order) <= {c.identity for c in track.candidates}, "Invalid track order")
    if track.previous_digest is not None:
        require(KEY.fullmatch(track.previous_digest), "Invalid previous track digest")
    encode(data(track), MAX_BYTES)


def load_snapshot(value) -> Snapshot:
    result = typed(Snapshot, value)
    validate_snapshot(result)
    return result


def load_track(value) -> Track:
    result = typed(Track, value)
    validate_track(result)
    return result
