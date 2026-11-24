"""Explicit personal consent and automatic local coordination, no providers.

Setup never starts a model, creates a product branch or writes to GitHub.
Approved feature preparation is deferred until independent policy/scope review
in a separately authorized finite invocation.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
import time

from .config import safe_path
from .discovery import complete_snapshot
from .discovery_schema import digest
from .enrollment import inspect_project, installer_root, local_checkout, product_roots
from .errors import ADPError
from .git import author, git, value
from .guard_types import Limits, data
from .personal_ci import native_inventory, prescribed_checks
from .personal_github import owned_repository
from .personal_git import administration
from .personal_storage import (INTENT, LIMIT, PersonalBlocked, PersonalState, approval, assert_public,
    complete_setup, create_private, disjoint, load_state, persist_intent, private_directory,
    read_private, token_parts)
from .personal_storage import validate_plan
from .policy_schema import branch, product_path
from .project_validation_github import GitHubValidationHTTP
from .schema import encode, fields, require, string
from .storage import atomic, locked


@dataclass(frozen=True)
class PersonalChoices:
    issue: int
    directory: Path
    paths: tuple[str, ...]
    branch: str | None = None
    workspace: Path | None = None
    commit_message: str | None = None
    commit_body: str = ""
    checks: tuple[str, ...] = ()
    accept_native_job_records: bool = False
    seconds: int = 1800


def governance(root):
    """Bounded committed data; no config, workflow or prose is executed."""
    rows = git(root, "ls-tree", "-rz", "HEAD", limit=1048576).split(b"\0")
    require(len(rows) <= 4097, "Source inventory exceeds the supported bound")
    result = []
    for entry in filter(None, rows):
        info, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode("utf-8", "strict")
        if not (Path(path).name == "AGENTS.md" or path in ("CONTRIBUTING.md", ".github/CODEOWNERS", ".adp.json")
                or path.startswith(".github/workflows/")):
            continue
        mode, kind, oid = info.decode("ascii").split()
        require(mode in ("100644", "100755") and kind == "blob", "Governance must be a committed regular file")
        content = git(root, "cat-file", "blob", oid, limit=65536).decode("utf-8", "strict")
        result.append({"path": path, "object": oid, "content": content})
    require(len(result) <= 64, "Governance inventory exceeds the supported bound")
    return result


def selection(repo, remote, expected_id, transport):
    checkout = local_checkout(repo, remote)
    owner = owned_repository(transport, checkout["repository"], expected_id)
    observation = inspect_project(checkout, transport, owner["repository_id"])
    require(complete_snapshot(observation.snapshot), "Complete native discovery is required for personal setup")
    return observation, owner


def marker(checkout, repository_id, issue_id):
    common = safe_path(Path(value(Path(checkout["path"]), "rev-parse", "--path-format=absolute", "--git-common-dir")))
    return common / "adp-personal" / (digest({"repository": repository_id, "issue": issue_id}) + ".json")


def plan_personal(observation, owner, choices: PersonalChoices, *, approved=None,
                  ci_transport=None, clock=None):
    read_clock = clock or (lambda: int(time.time()))
    now = read_clock()
    checkout, repository = observation.checkout, observation.repository
    root, directory = Path(checkout["path"]), choices.directory
    require(type(choices.issue) is int and choices.issue > 0, "Select one original open issue")
    selected = [issue for issue in observation.snapshot.issues if issue.number == choices.issue and issue.state == "open"]
    require(len(selected) == 1, "Select one observed open issue")
    original = selected[0]
    require(type(choices.paths) is tuple and 0 < len(choices.paths) <= 32
            and len(set(choices.paths)) == len(choices.paths), "Select the bounded paths needed by the original ticket")
    for path in choices.paths:
        product_path(path)
    require(type(choices.accept_native_job_records) is bool, "Explicit native evidence choice is required")
    private_directory(directory, missing=True)
    if directory.exists():
        intent_path = directory / INTENT
        if intent_path.exists():
            retained = load_state(directory)
            require(approved == retained.intent["approval"], "Use status/reconnect for the existing enrollment")
        else:
            require(not any(directory.iterdir()), "Do not adopt an unrelated private directory")
        lock = directory / "lock"
        if lock.exists() or lock.is_symlink():
            info = lock.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and info.st_nlink == 1 and not info.st_mode & 0o077, "Unsafe personal enrollment lock")
    roots = product_roots(checkout)
    engine = Path(__file__).resolve().parents[1]
    require(all(disjoint(directory, candidate) for candidate in (*roots, engine, installer_root())),
            "Keep personal state outside product checkouts, Git administration and the trusted engine")
    docs = governance(root)
    # The complete original is the acceptance contract. This opaque criterion
    # names it without rewriting, truncating or inventing acceptance prose.
    criterion = "original-ticket:" + original.revision
    current_branch = checkout["ref"].removeprefix("refs/heads/")
    default = repository["default_branch"]
    require(default is not None, "Observe the default branch before feature preparation")
    selected_branch = choices.branch or (current_branch if current_branch != default else f"adp/issue-{choices.issue}")
    branch(selected_branch)
    require(len(selected_branch.split("/")[-1]) <= 96,
            "The selected branch needs a task slug supported by the existing M3 port")
    require(selected_branch != default, "Personal mode never develops on the default branch")
    prepare_feature = current_branch != selected_branch
    require(not value(root, "status", "--porcelain", "--untracked-files=all"), "Select a clean source checkout")
    feature = (choices.workspace or root.parent / (root.name + "-adp-" + str(choices.issue))) if prepare_feature else root
    require(feature.is_absolute() and safe_path(feature) == feature, "Select an absolute normalized feature workspace")
    require(disjoint(feature, directory) and disjoint(feature, engine) and disjoint(feature, installer_root()),
            "Keep feature and private/engine roots separate")
    if prepare_feature:
        require(all(disjoint(feature, candidate) for candidate in roots), "Use an isolated feature workspace")
        require(not feature.exists(), "Do not adopt or overwrite an existing feature destination")
        known = value(root, "for-each-ref", "--format=%(refname)", "refs/heads/" + selected_branch)
        require(not known, "The proposed feature branch already exists; select it explicitly or choose another")
    else:
        require(feature == root, "Existing feature selection cannot redirect the workspace")
    if approved:
        issued, expires, nonce, _ = token_parts(approved, now)
    else:
        require(type(choices.seconds) is int and 60 <= choices.seconds <= 3600, "Select a finite personal window")
        issued, expires, nonce = now, now + choices.seconds, secrets.token_hex(16)
    required = tuple(sorted({name for row in observation.facts["branch_rules"] for name in row["required_check_contexts"]}))
    check_names = tuple(sorted(set(required) | set(choices.checks)))
    checks = ()
    inventory, identity_status = {}, "NOT_REQUESTED"
    if check_names:
        identity_status = "UNKNOWN"
        if ci_transport is not None:
            try:
                inventory = native_inventory(repository["name"], repository["repository_id"], checkout["ref"],
                                             checkout["head"], ci_transport)
                identity_status = "OBSERVED"
            except (ADPError, OSError):
                # An unpublished SHA or unavailable API is not an absent check.
                # Preserve every prescribed name and keep its evidence pending.
                inventory = {}
        checks = prescribed_checks(tuple(name for name in check_names if name in inventory), inventory,
                                   accept_native_job_records=choices.accept_native_job_records)
    rules_known = all(row["rules"] == "OBSERVED" for row in observation.facts["branch_rules"])
    check_requirement = ("PRESENT" if check_names else "VERIFIED_ABSENT" if rules_known and not docs
                         and not prepare_feature else "UNKNOWN")
    original_data = data(original)
    document_digest = digest(docs)
    commit_message = choices.commit_message or original.title
    string(commit_message, 256)
    require(commit_message.strip(), "Select an actual commit message")
    require(type(choices.commit_body) is str and len(choices.commit_body) <= 2048
            and all(ord(c) >= 32 or c == "\n" for c in choices.commit_body), "Select a bounded commit body")
    require("{" not in choices.commit_body and "}" not in choices.commit_body,
            "Literal commit-body braces are unsupported by the existing M3 template port; do not reinterpret project text")
    public_docs = [{"path": row["path"], "object": row["object"]} for row in docs]
    pointer = marker(checkout, repository["repository_id"], original.identity.issue_id)
    existing = read_private(pointer, optional=True)
    if existing is not None:
        require(existing.get("directory") == str(directory) and existing.get("approval") == approved,
                "An existing enrollment cannot be replaced with another directory, plan or budget")
    proposed = {
        "schema_version": 1, "mode": "PERSONAL", "repository": repository, "owner": owner,
        "checkout": checkout, "administration": administration(root), "issue": original.number, "issue_id": original.identity.issue_id,
        "original_digest": digest(original_data), "discovery_digest": observation.facts["discovery_digest"],
        "governance_digest": document_digest, "governance": public_docs,
        "native_prerequisites": [data(edge) for edge in original.relations if edge.confidence == "NATIVE" and edge.kind == "BLOCKED_BY"],
        "admission": "BLOCKED_DEPENDENCY" if any(edge.confidence == "NATIVE" and edge.kind == "BLOCKED_BY"
                                                for edge in original.relations) else "INDEPENDENT_SCOPE_REVIEW_REQUIRED",
        "feature": {"workspace": str(feature), "branch": selected_branch, "prepare": prepare_feature,
                    "preparation": "AFTER_INDEPENDENT_POLICY_REVIEW" if prepare_feature else "EXISTING"},
        "paths": list(choices.paths), "criterion": criterion, "commit_message": commit_message,
        "commit_body": choices.commit_body,
        "checks": [data(check) for check in checks], "check_requirements": check_requirement,
        "required_check_names": list(check_names), "check_identity_status": identity_status,
        "unresolved_check_names": [name for name in check_names if name not in inventory],
        "accept_native_job_records": choices.accept_native_job_records,
        "branch_rules": observation.facts["branch_rules"],
        "operations": ["INSPECT", "EDIT", "STAGE", "COMMIT", "VALIDATE"] + (["BRANCH"] if prepare_feature else []),
        "merge_mode": "MANUAL", "publication": "NOT_DELEGATED", "author": list(author(root)),
        "window": {"issued_at": issued, "expires_at": expires, "nonce": nonce,
                   "maximum_tasks": 1, "maximum_rounds": 1, "maximum_parallel": 1,
                   "scope_reviewers": 1, "developers": 2, "candidate_reviewers": 2, "code_reviewers": 2,
                   "forensic_reviewers": 2,
                   "maximum_check_observations": 3, "worker_seconds": 300},
        "guard": {"limits": data(Limits()), "forensic_backend": "UNSUPPORTED_STOP", "budget_reset": "NOT_PERMITTED"},
        "effects": {"directory": str(directory), "coordination": str(directory / "coordination"),
                    "coordination_remote": str(directory / "coordination.git"), "memory": str(directory / "memory"),
                    "private": str(directory / "private"), "marker": str(pointer), "memory_ref": "refs/heads/adp/personal"},
    }
    assert_public(proposed)
    validate_plan(proposed, directory)
    # No worker receives an incomplete original, policy or governance context.
    encode({"original": original_data, "governance": docs, "plan": proposed}, 32768)
    if approved:
        require(approval(proposed) == approved, "Personal plan changed; review the exact current plan")
    require(issued <= read_clock() < expires, "Personal plan expired during observation")
    return proposed, original_data, docs


def apply_personal(plan, original, docs, *, approved, authorized, transport, ci_transport=None, clock=None,
                   _track_link=None):
    read_clock = clock or (lambda: int(time.time()))
    now = read_clock()
    require(authorized and approved == approval(plan), "Approve the exact personal plan and local memory writes")
    token_parts(approved, now)
    if _track_link is not None:
        # Internal next-intent composition only: mark the child as track-bound
        # before setup can expose an ENROLLED standalone execution entry point.
        fields(_track_link, "schema_version root index identity directory setup snapshot parent")
        from .policy_schema import fingerprint
        fingerprint(_track_link["index"]); fingerprint(_track_link["snapshot"])
        require(type(_track_link["schema_version"]) is int and _track_link["schema_version"] == 1
                and _track_link["directory"] == plan["effects"]["directory"]
                and _track_link["setup"] == approved and _track_link["identity"] == original["identity"]
                and _track_link["parent"] is not None, "Next setup requires its exact retained track identity")
    checkout = plan["checkout"]
    observation, owner = selection(Path(checkout["path"]), checkout["remote"],
                                   plan["repository"]["repository_id"], transport)
    retained = Path(plan["effects"]["directory"]) / INTENT
    if retained.exists():
        existing = load_state(retained.parent)
        require(existing.plan == plan and existing.intent["approval"] == approved,
                "The original enrollment cannot be reapproved or replaced")
        existing.live(read_clock(), owner=existing.intent["phase"] == "ENROLLED")
        if existing.intent["phase"] == "ENROLLED":
            if _track_link is not None:
                require(read_private(existing.state / "track-link.json", optional=True) == _track_link,
                        "Do not adopt an enrolled standalone task into an unfinished track intent")
            candidates = [row for row in observation.snapshot.issues if row.identity.issue_id == plan["issue_id"]]
            require(observation.checkout == checkout and owner == plan["owner"] and len(candidates) == 1
                    and digest(data(candidates[0])) == plan["original_digest"]
                    and digest(governance(Path(checkout["path"]))) == plan["governance_digest"],
                    "Personal access, original ticket or governance changed")
            return existing
    choices = PersonalChoices(plan["issue"], Path(plan["effects"]["directory"]), tuple(plan["paths"]),
        branch=plan["feature"]["branch"], workspace=Path(plan["feature"]["workspace"]),
        commit_message=plan["commit_message"], commit_body=plan["commit_body"],
        checks=tuple(plan["required_check_names"]),
        accept_native_job_records=plan["accept_native_job_records"],
        seconds=plan["window"]["expires_at"] - plan["window"]["issued_at"])
    current, current_original, current_docs = plan_personal(observation, owner, choices,
        approved=approved, ci_transport=ci_transport, clock=read_clock)
    require((current, current_original, current_docs) == (plan, original, docs),
            "Current source, original ticket, policy or personal plan changed")
    directory = Path(plan["effects"]["directory"])
    pointer = Path(plan["effects"]["marker"])
    token_parts(approved, read_clock())
    create_private(pointer.parent)
    with locked(pointer.parent):
        token_parts(approved, read_clock())
        require(local_checkout(Path(checkout["path"]), checkout["remote"]) == checkout,
                "Checkout changed before personal setup writes")
        expected = {"schema_version": 1, "directory": str(directory), "approval": approved}
        existing = read_private(pointer, optional=True)
        require(existing in (None, expected), "Do not overwrite a previous personal enrollment marker")
        if existing is None:
            atomic(pointer, encode(expected), replace=False)
        personal = persist_intent(directory, plan, original, docs)
        if _track_link is not None:
            from .personal_track import immutable
            immutable(personal.state / "track-link.json", _track_link)
        return complete_setup(personal, clock=read_clock)
