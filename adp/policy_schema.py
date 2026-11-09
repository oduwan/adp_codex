"""Closed policy data, bounded rendering and repository-scoped evidence hashes."""
from __future__ import annotations

import hashlib
import re
from dataclasses import fields as dataclass_fields

from .errors import ADPError
from .git import SHA
from .guard_types import data
from .schema import KEY, decode, encode, fields, integer, require, string
from .policy_types import (Document, Operation, Permission, Ref, RepositorySnapshot, Rules, SourceKind, Task)

MAX_BYTES = 1048576
MAX_SOURCES = 16
MAX_REFS = 4096
MAX_AGE = 3600
METHODS = {"merge", "squash", "ff_only"}
STATUSES = {"PASS", "FAIL", "ERROR", "TIMEOUT", "SKIP", "NOTRUN", "UNKNOWN"}
FORBIDDEN = {Operation.FORCE_PUSH, Operation.REBASE, Operation.REWRITE}
GATED = {Operation.MERGE, Operation.RELEASE, Operation.DEPLOY, Operation.REPORT}


def digest(value: object) -> str:
    normalized = data(value) if not isinstance(value, dict) else value
    return hashlib.sha256(encode(normalized, MAX_BYTES)).hexdigest()


def sha(value: object, *, nullable: bool = False) -> None:
    require(nullable and value is None or isinstance(value, str) and SHA.fullmatch(value), "Invalid exact policy revision")


def fingerprint(value: object) -> None:
    require(isinstance(value, str) and KEY.fullmatch(value), "Invalid policy digest")


def strings(values: object, limit: int = 32, length: int = 256) -> None:
    require(isinstance(values, (tuple, list)) and len(values) <= limit, "Policy list exceeds bounds")
    for value in values:
        string(value, length)
    require(len(set(values)) == len(values), "Duplicate policy values")


def ref(value: object) -> None:
    string(value, 255)
    require(value.startswith(("refs/heads/", "refs/tags/")), "A full branch/tag ref is required")
    branch(value.split("/", 2)[2])


def branch(value: object) -> None:
    string(value, 240)
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value)
            and not any(part in value for part in ("..", "//", "@{"))
            and not value.endswith(("/", "."))
            and all(part and not part.startswith(".") and not part.endswith(".lock") for part in value.split("/")),
            "Unsafe branch/tag name")


def product_path(value: object) -> None:
    from pathlib import PurePosixPath
    string(value, 240)
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and not value.startswith("-")
            and all(p not in (".", "..", ".git") for p in path.parts)
            and "\\" not in value and ":" not in value, "Unsafe product path")


def template(value: str, tokens: set[str], *, multiline: bool = False) -> None:
    require(isinstance(value, str) and len(value) <= 2048, "Invalid policy template")
    require(all(ord(c) >= 32 or multiline and c == "\n" for c in value), "Control characters in template")
    remainder = value
    for token in tokens:
        remainder = remainder.replace("{" + token + "}", "")
    require("{" not in remainder and "}" not in remainder, "Unsupported policy template expression")


def render(value: str, *, task: str = "", slug: str = "", summary: str = "", version: str = "") -> str:
    values = {"task": task, "slug": slug, "summary": summary, "version": version}
    return re.sub(r"\{(task|slug|summary|version)\}", lambda match: values[match[1]], value)


def validate_rules(value: Rules) -> None:
    require(type(value) is Rules, "Expected typed external rules")
    require(type(value.permissions) is tuple and len(value.permissions) <= len(Operation), "Invalid permission list")
    for permission in value.permissions:
        require(type(permission) is Permission and isinstance(permission.operation, str)
                and permission.operation in set(Operation) and isinstance(permission.effect, str)
                and permission.effect in {"ALLOW", "DENY", "UNKNOWN"}, "Invalid operation permission")
    strings([p.operation for p in value.permissions], len(Operation), 32)
    if value.base_branch is not None:
        branch(value.base_branch)
    for name, allowed in (("branch_template", {"slug"}), ("subject_template", {"task", "summary"}),
                          ("body_template", {"task", "summary"}), ("pr_title_template", {"task", "summary"}),
                          ("release_template", {"version"})):
        item = getattr(value, name)
        if item is not None:
            template(item, allowed, multiline=name == "body_template")
    if value.branch_template is not None:
        require(value.branch_template.count("{slug}") == 1, "Branch template needs exactly one explicit slug")
        branch(render(value.branch_template, slug="sample"))
    if value.release_template is not None:
        require(value.release_template.count("{version}") == 1, "Release template needs one version")
        branch(render(value.release_template, version="sample"))
    if value.subject_limit is not None:
        require(type(value.subject_limit) is int and 1 <= value.subject_limit <= 256, "Invalid subject limit")
    if value.pr_draft is not None:
        require(type(value.pr_draft) is bool, "Explicit boolean PR mode required")
    if value.merge_method is not None:
        require(isinstance(value.merge_method, str) and value.merge_method in METHODS, "Unsupported merge method")
    if value.reviews is not None:
        require(type(value.reviews) is int and 0 <= value.reviews <= 16, "Invalid review obligation")
    strings(value.checks, 32, 128)
    if value.environments is not None:
        strings(value.environments, 16, 128)
    strings(value.gate_operations, len(Operation), 32)
    require(all(isinstance(op, str) and op in set(Operation) for op in value.gate_operations), "Invalid gate operation")
    encode(data(value), MAX_BYTES)


def parse_profile(raw: bytes) -> Rules:
    value = decode(raw)
    fields(value, "schema_version rules")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "Unsupported policy profile version")
    rules = value["rules"]
    require(type(rules) is dict and not set(rules) - {f.name for f in dataclass_fields(Rules)}, "Unknown external rule")
    try:
        converted = dict(rules)
        if "permissions" in converted:
            require(type(converted["permissions"]) is list, "Permissions must be structured entries")
            for entry in converted["permissions"]:
                fields(entry, "operation effect")
            converted["permissions"] = tuple(Permission(Operation(p["operation"]), p["effect"]) for p in converted["permissions"])
        for name in ("environments", "checks", "gate_operations"):
            if name in converted:
                if name == "environments" and converted[name] is None:
                    continue
                require(type(converted[name]) is list, "Invalid profile list")
                converted[name] = tuple(converted[name])
        result = Rules(**converted)
    except (ValueError, TypeError) as exc:
        raise ADPError("Malformed external profile") from exc
    validate_rules(result)
    return result


def fresh(observed: int, expires: int, now: int) -> bool:
    integer(observed)
    integer(expires)
    return observed <= now <= expires and 0 < expires - observed <= MAX_AGE


def validate_snapshot(value) -> None:
    require(type(value) is RepositorySnapshot, "Expected typed repository snapshot")
    string(value.repository_id)
    string(value.remote, 128)
    fingerprint(value.remote_fingerprint)
    ref(value.source_ref)
    sha(value.revision)
    fingerprint(value.index_digest)
    if value.worktree_digest is not None:
        fingerprint(value.worktree_digest)
    require(type(value.worktree_clean) is bool and type(value.remote_refs_known) is bool, "Invalid repository status")
    strings(value.diagnostics, 16, 512)
    require(isinstance(value.push_relation, str) and value.push_relation in {"CREATE", "SAME", "FAST_FORWARD", "DIVERGED", "UNKNOWN"}, "Invalid push ancestry observation")
    for refs in (value.local_refs, value.remote_refs):
        require(type(refs) is tuple and len(refs) <= MAX_REFS, "Ref snapshot too large")
        require(all(type(item) is Ref for item in refs), "Expected typed refs")
        strings([item.name for item in refs], MAX_REFS)
        for item in refs:
            ref(item.name)
            sha(item.revision)
    require(type(value.documents) is tuple and len(value.documents) <= MAX_SOURCES, "Too many policy sources")
    require(all(type(d) is Document for d in value.documents), "Expected typed policy documents")
    strings([d.reference for d in value.documents], MAX_SOURCES)
    for document in value.documents:
        string(document.reference)
        fingerprint(document.digest)
        require(isinstance(document.kind, str) and document.kind in set(SourceKind) - {SourceKind.PROTECTION, SourceKind.INVARIANT}, "Invalid document source kind")
        if document.profile is not None:
            validate_rules(document.profile)
    encode(data(value), MAX_BYTES)


def validate_task(task) -> None:
    require(type(task) is Task, "Expected a typed admitted task")
    string(task.repository_id)
    string(task.task_id)
    require(isinstance(task.branch_slug, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", task.branch_slug), "Explicit safe task slug required")
    sha(task.revision)
    ref(task.source_ref)
    fingerprint(task.requirement_id)
    for value in (task.generation, task.task_epoch, task.iteration):
        integer(value, 1)
    strings(task.authors, 16, 128)
    require(bool(task.authors), "Authenticated source author identities required")
