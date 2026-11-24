"""Guided enrollment atop the installed operator contract."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote

from .codex_runtime import CodexExecRuntime
from .config import Config, remote_identity, safe_path
from .discovery import complete_snapshot
from .discovery_github import GitHubDiscoveryAdapter, ReadOnlyTransport
from .discovery_schema import digest, typed
from .discovery_types import Snapshot
from .errors import ADPError
from .execution_privacy import credential_shaped
from .git import author, git, value
from .memory import Memory
from .operator_authority import OperatorAuthority, remote_semantics
from .operator_controller import InstalledProject, READ_PERMISSIONS
from .operator_decisions import exchange
from .operator_profile import OperatorProfile, Trust, _validate_profile, load_profile, private_file
from .operator_setup import ENROLLMENT_RECORD, PreviewBinding, guided_binding, preview, setup, status, verify_enrollment
from .policy_schema import branch as git_branch
from .project_validation_types import EvidenceRequest, ProjectObservation
from .schema import encode, fields, require, string
from .storage import atomic, locked, temporary_slot

SCHEMA = 1
LIMIT = 131072
ENDPOINT = re.compile(r"https://github\.com/([A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}?)(?:\.git)?")
PROFILE = "profile.json"
INTENT = "intent.json"
FAILURES = (ADPError, OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration)


class Blocked(ADPError):
    def __init__(self, code: str, action: str, *, status: str = "BLOCKED"):
        super().__init__(action)
        self.reason, self.status = code, status


def public(value_: object) -> None:
    require(not credential_shaped(value_), "Private credential-shaped value in enrollment protocol")


def local_checkout(root: Path, remote: str) -> dict:
    root = safe_path(root.absolute())
    cfg = Config.discover(root, remote=remote)
    require(cfg.root == root, "Select the actual checkout root")
    url = value(root, "remote", "get-url", cfg.remote)
    match = ENDPOINT.fullmatch(url)
    require(match, "Select the canonical HTTPS GitHub remote")
    ref = value(root, "symbolic-ref", "--quiet", "HEAD")
    head = value(root, "rev-parse", "HEAD")
    require(ref.startswith("refs/heads/"), "Select an existing local branch")
    facts = {"path": str(root), "remote": cfg.remote, "repository": match[1], "ref": ref, "head": head}
    public(facts)
    return facts


def canonical(transport: ReadOnlyTransport, name: str, expected: str | None) -> dict:
    response = transport.get("/repos/" + name)
    if response.status in (401, 403):
        raise Blocked("DISCOVERY_CREDENTIAL_REFUSED", "Provide a current read credential for the selected GitHub repository.")
    if response.status != 200 or type(response.body) is not dict:
        raise Blocked("REPOSITORY_UNAVAILABLE", "Confirm access to the selected canonical GitHub repository.", status="UNKNOWN")
    metadata = response.body
    rid = metadata.get("id")
    if type(rid) is not int or rid <= 0 or metadata.get("full_name") != name or expected not in (None, str(rid)):
        raise Blocked("REPOSITORY_IDENTITY_MISMATCH", "Confirm the immutable repository ID and canonical HTTPS remote.")
    node = metadata.get("node_id")
    string(node)
    default = metadata.get("default_branch")
    if type(default) is not str or not default:
        default = None
    facts = {"repository_id": str(rid), "database_id": rid, "node_id": node, "name": name, "default_branch": default}
    public(facts)
    return facts


def branch_rules(transport: ReadOnlyTransport, name: str, branch: str) -> dict:
    git_branch(branch)
    suffix = quote(branch, safe="")
    base = "/repos/" + name
    branch_response = transport.get(base + "/branches/" + suffix)
    rules = transport.get(base + "/rules/branches/" + suffix)
    protected = None
    if (branch_response.status == 200 and type(branch_response.body) is dict
            and branch_response.body.get("name") == branch
            and type(branch_response.body.get("protected")) is bool):
        protected = branch_response.body["protected"]
    known = (rules.status == 200 and type(rules.body) is list and len(rules.body) <= 100
             and all(type(row) is dict for row in rules.body))
    checks = []
    if known:
        for row in rules.body:
            if row.get("type") != "required_status_checks":
                continue
            entries = row.get("parameters", {}).get("required_status_checks") if type(row.get("parameters")) is dict else None
            if (type(entries) is not list or len(entries) > 32
                    or any(type(item) is not dict or type(item.get("context")) is not str
                           or not 0 < len(item["context"]) <= 128 for item in entries)):
                known = False
                break
            checks.extend(item["context"] for item in entries if not credential_shaped(item["context"]))
    return {"ref": "refs/heads/" + branch, "protected": protected,
            "rules": "OBSERVED" if known else "UNKNOWN",
            "required_check_contexts": sorted(set(checks)) if known else [],
            "rules_digest": digest(rules.body) if known else None}


def checkout_files(checkout: dict) -> dict:
    records = git(Path(checkout["path"]), "ls-tree", "-rz", checkout["head"], "--",
                  "AGENTS.md", "CONTRIBUTING.md", ".github/CODEOWNERS", ".github/workflows", limit=65536)
    files = []
    for entry in filter(None, records.split(b"\0")):
        info, name = entry.split(b"\t", 1)
        mode, kind, oid = info.decode("ascii").split()
        path = os.fsdecode(name)
        if mode in ("100644", "100755") and kind == "blob" and not credential_shaped(path):
            if path in {"AGENTS.md", "CONTRIBUTING.md", ".github/CODEOWNERS"} or re.fullmatch(
                    r"\.github/workflows/[A-Za-z0-9_.-]{1,128}\.ya?ml", path):
                files.append({"path": path, "git_object": oid})
    require(len(files) <= 128, "Committed governance and workflow inventory exceeds enrollment bounds")
    return {"governance": [f for f in files if not f["path"].startswith(".github/workflows/")],
            "workflows": [f for f in files if f["path"].startswith(".github/workflows/")]}


def runtime_capability(state: Path) -> dict:
    cap = CodexExecRuntime(state / "runtime").capabilities()
    return {"status": "SUPPORTED" if cap.independent_contexts else "UNKNOWN",
            "independent_contexts": cap.independent_contexts, "qualification": "NOTRUN"}


@dataclass(frozen=True)
class Observation:
    facts: dict
    snapshot: Snapshot

    @property
    def checkout(self) -> dict:
        return self.facts["checkout"]

    @property
    def repository(self) -> dict:
        return self.facts["repository"]


def inspect_project(checkout: dict, transport: ReadOnlyTransport, expected: str | None, *, personal_owner=None) -> Observation:
    repo = canonical(transport, checkout["repository"], expected)
    cfg = Config.discover(Path(checkout["path"]), remote=checkout["remote"], repository_id=repo["repository_id"])
    try:
        adapter = GitHubDiscoveryAdapter
        if personal_owner is not None:
            from .personal_discovery import PersonalGitHubDiscoveryAdapter
            adapter = PersonalGitHubDiscoveryAdapter
        snapshot = adapter(repo["name"], transport, expected_id=repo["repository_id"], config=cfg).discover()
    except FAILURES as exc:
        raise Blocked("DISCOVERY_UNAVAILABLE", "Refresh complete repository, issue, and dependency observations.", status="UNKNOWN") from exc
    require((snapshot.repository.checkout_ref, snapshot.repository.checkout_sha) == (checkout["ref"], checkout["head"]),
            "Checkout changed during discovery")
    # Read the canonical metadata again to fence identity and default-branch changes.
    require(canonical(transport, repo["name"], repo["repository_id"]) == repo, "Repository metadata changed during discovery")
    branch = checkout["ref"].removeprefix("refs/heads/")
    default = repo["default_branch"]
    require(default is None or len(default) <= 255, "Invalid GitHub default branch")
    def rules(name):
        if personal_owner is not None:
            from .personal_rules import enrollment_rules
            return enrollment_rules(transport, repo, personal_owner, name)
        return branch_rules(transport, repo["name"], name)
    branches = [rules(name) for name in dict.fromkeys(
        [branch] + ([default] if default else []))]
    files = checkout_files(checkout)
    require(local_checkout(Path(checkout["path"]), checkout["remote"]) == checkout, "Checkout changed during inspection")
    issues = [{"number": i.number, "id": i.identity.issue_id, "state": i.state, "revision": i.revision,
               "native_dependencies": [{"repository": r.target.repository, "number": r.target.number,
                                        "id": r.target.issue_id, "kind": r.kind}
                                       for r in i.relations if r.confidence == "NATIVE"
                                       and r.kind in ("BLOCKED_BY", "SUB_ISSUE")]}
              for i in snapshot.issues]
    facts = {"checkout": checkout, "repository": repo, "issues": issues,
             "discovery": "COMPLETE" if complete_snapshot(snapshot) else "UNKNOWN",
             "discovery_digest": remote_semantics((snapshot,)), "branch_rules": branches, **files}
    public(facts)
    encode(facts, LIMIT)
    return Observation(facts, snapshot)


def protected_path(path: Path, *, optional_leaf: bool = False) -> Path:
    path = safe_path(path)
    require(path != Path("/"), "Select a private enrollment directory")
    for parent in (path, *path.parents):
        marker = parent / ".git"
        require(not (marker.is_file() or marker.is_symlink() or (marker / "HEAD").is_file()),
                "Enrollment authority must be outside Git worktrees")
    directory = path if path.exists() or not optional_leaf else path.parent
    info = directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
            "Use an owned private directory (0700) for enrollment")
    return path


def disjoint(first: Path, second: Path) -> bool:
    return not first.is_relative_to(second) and not second.is_relative_to(first)


def installer_root() -> Path:
    return Path.home() / ".local/share/adp-codex-install"


def product_roots(checkout: dict) -> tuple[Path, ...]:
    root = Path(checkout["path"])
    locations = [safe_path(Path(value(root, "rev-parse", "--path-format=absolute", "--git-common-dir")))]
    entries = git(root, "-c", "core.quotePath=false", "worktree", "list", "--porcelain", limit=65536)
    for row in entries.splitlines():
        if row.startswith(b"worktree "):
            path = Path(os.fsdecode(row[9:]))
            require(path.is_absolute(), "Noncanonical linked checkout path")
            locations.append(safe_path(path))
    require(root in locations, "Selected product worktree registration unavailable")
    return tuple(locations)


class PreviewProfile(OperatorProfile):
    """An authenticated proposal is usable only through the read-only ports."""
    def _current_profile(self):
        return self.trust.verify_document(self.evidence.document, "profile", self.repository_id)

    def live(self, *, retain=False):
        require(not retain, "An in-memory enrollment proposal cannot retain authority")
        return super().live()


def match_checkout(profile: OperatorProfile, checkout: dict) -> None:
    target = profile.payload["repository"]
    require(target["name"] == checkout["repository"] and target["remote"] == checkout["remote"]
            and any(task.workspace == Path(checkout["path"]) for task in profile.tasks),
            "Selected checkout differs from the authenticated enrollment")
    require(checkout["ref"] in profile.delegation["branches"], "Checkout is outside the authenticated enrollment branch")


def match_observation(profile: OperatorProfile, observation: Observation, issue: int) -> None:
    checkout, repo = observation.checkout, observation.repository
    match_checkout(profile, checkout)
    target = profile.payload["repository"]
    require(profile.repository_id == repo["repository_id"] and target["database_id"] == repo["database_id"]
            and target["node_id"] == repo["node_id"], "Signed profile targets a different immutable repository")
    selected = [i for i in observation.snapshot.issues if i.number == issue and i.state == "open"]
    require(len(selected) == 1 and len(profile.tasks) == 1, "Select one open issue and one existing feature checkout")
    task = profile.tasks[0]
    require(task.number == issue and task.issue_id == selected[0].identity.issue_id
            and task.expected_revision == checkout["head"]
            and profile.delegation["issues"] == [task.issue_id]
            and profile.delegation["branches"] == [checkout["ref"]]
            and checkout["ref"] != "refs/heads/" + (repo["default_branch"] or "")
            and profile.delegation["allow_setup"] and profile.delegation["allow_claim"],
            "Proposal differs from the selected issue, feature branch, revision or setup authority")


def profile_from_proposal(directory: Path, trust_path: Path, raw: dict) -> OperatorProfile:
    path = directory / PROFILE
    if path.exists():
        require(private_file(path, limit=65536) == raw, "Persisted enrollment profile differs from the retained intent")
        return load_profile(path, trust_path)
    encode(raw, 65536)
    profile = _validate_profile(path, Trust(trust_path), raw, profile_class=PreviewProfile)
    profile.live()
    return profile


def local_effects(profile: OperatorProfile, directory: Path, checkout: dict) -> tuple[dict, Memory]:
    cfg = profile.memory_config()
    bare = Path(remote_identity(value(cfg.root, "remote", "get-url", cfg.remote), cfg.root)[5:])
    bare = safe_path(bare)
    memory = Memory(cfg, pinned_local_remote=bare)
    common = safe_path(Path(value(cfg.root, "rev-parse", "--path-format=absolute", "--git-common-dir")))
    require(value(cfg.root, "remote", "get-url", cfg.remote) in (str(bare), bare.as_uri()),
            "Use a direct canonical local coordination remote")
    roots = (directory, cfg.root, bare, memory.path, profile.state)
    require(all(disjoint(a, b) for index, a in enumerate(roots) for b in roots[index + 1:]),
            "Use separate operator, coordination, bare remote, memory and evidence paths")
    require(all(disjoint(root, other) for root in (*roots, common)
                for other in (*product_roots(checkout), installer_root())),
            "Enrollment targets cannot overlap any product worktree or Git administration")
    require(all(disjoint(common, root) for root in (directory, bare, memory.path, profile.state)),
            "Keep enrollment and evidence outside coordination Git administration")
    for root in (cfg.root, common, bare, memory.path, profile.state):
        existing = next(candidate for candidate in (root, *root.parents) if candidate.exists())
        info = existing.stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
                "Use owner-controlled coordination and state paths")
    author(cfg.root)
    effects = {"enrollment_directory": str(directory), "profile": str(directory / PROFILE),
               "intent": str(directory / INTENT), "lock": str(directory / "lock"),
               "coordination_checkout": str(cfg.root), "coordination_git_directory": str(common),
               "coordination_control": str(memory.control),
               "local_bare_remote": str(bare), "memory_worktree": str(memory.path),
               "private_evidence": str(profile.state), "enrollment_record": str(profile.state / ENROLLMENT_RECORD),
               "memory_ref": "refs/heads/" + memory.branch,
               "authority": "EXACT_DIGEST_AND_EXPLICIT_MEMORY_WRITE_REQUIRED"}
    public(effects)
    return effects, memory


def provider_inputs(profile: OperatorProfile) -> tuple[InstalledProject, dict]:
    providers = profile.payload["providers"]
    authority = OperatorAuthority(profile)
    rid = profile.repository_id
    roles = ("project-policy", "scope-reviewer", "token-issuer")
    if providers["validation"]["kind"] == "signed":
        roles += ("project-check",)
    principals = profile.trust._root()
    reserved = {profile.evidence.principal, profile.payload["authority"]}
    private_paths = [profile.trust.path, *(Path(row["key_file"]) for row, _ in principals.values()),
                     *(Path(providers[k]) for k in ("policy", "assessment", "decisions", "revocations")),
                     *(Path(path) for path in (*providers["credentials"].values(),
                        providers["decision_socket"], providers["validation"]["path"]) if path is not None)]
    require(all(disjoint(path, installer_root()) for path in private_paths),
            "Provider and trust material must be outside the M9-A managed installer")
    # Every required external role must be provisioned by the explicit trust root.
    for role in roles:
        eligible = {name for name, (row, _) in principals.items()
                    if role in row["roles"] and rid in row["repositories"] and name not in reserved}
        if not eligible:
            raise Blocked("MISSING_TRUST_ROLE", f"Provision an independent {role} verifier for this repository.")
    bindings = {}
    signers = set(reserved)
    for kind, code in (("policy", "PROJECT_POLICY_REQUIRED"), ("assessment", "INDEPENDENT_SCOPE_REQUIRED"),
                       ("project-evidence", "PROJECT_CHECK_PROVIDER_REQUIRED")):
        location = providers["validation"]["path"] if kind == "project-evidence" else providers[kind]
        if kind == "project-evidence" and providers["validation"]["kind"] != "signed":
            continue
        try:
            require(location is not None, "Select a current signed provider bootstrap file")
            source = authority.signed(kind, location)
            require(source.principal not in signers, "Provider roles must stay independent")
            signers.add(source.principal)
            if kind == "project-evidence":
                body = source.payload
                fields(body, "repository_id request results observed_at complete coverage")
                request = typed(EvidenceRequest, body["request"])
                task = profile.tasks[0]
                observation = typed(ProjectObservation, {"query_digest": digest(request),
                    "results": body["results"], "observed_at": body["observed_at"],
                    "complete": body["complete"], "coverage": body["coverage"],
                    "evidence": None, "action_key": None})
                age = profile.trust.clock() - observation.observed_at
                require(request.repository_id == rid and request.revision == task.expected_revision
                        and request.source_ref in profile.delegation["branches"] and request.task_id == task.task_id
                        and request.phase in {check.phase for check in profile.checks}
                        and source.issued_at <= observation.observed_at < source.expires_at
                        and 0 <= age <= providers["validation"]["maximum_age"],
                        "Signed check bootstrap does not match the selected checkout, check phase, or freshness budget")
            bindings[kind] = source.fingerprint
        except FAILURES as exc:
            raise Blocked(code, f"Supply current repository-bound signed data from the independent {kind} provider.") from exc
    from .network_http import GitHubHTTPTransport
    from .github_product import GitHubForgeHTTPTransport
    from .ticket_publication import GitHubTicketHTTPTransport
    needs = {"read": READ_PERMISSIONS, "cas": GitHubHTTPTransport.permissions, "forge": GitHubForgeHTTPTransport.permissions}
    if "TICKET_EDIT" in profile.delegation["operations"]:
        needs["ticket"] = GitHubTicketHTTPTransport.permissions
    for kind, permissions in needs.items():
        try:
            path = providers["credentials"][kind]
            require(path is not None, "Select an issuer-provided scoped credential file")
            source = authority.signed("credential", path)
            require(source.principal not in signers, "Credential issuer cannot stand in for other authorities")
            authority.credential(path, permissions)
            # Never include a token-derived fingerprint in the interactive output.
        except FAILURES as exc:
            raise Blocked("SCOPED_CREDENTIAL_REQUIRED", f"Obtain the current repository-scoped {kind} credential from the trusted issuer.") from exc
    try:
        decisions = private_file(Path(providers["decisions"]))
        fields(decisions, "schema_version decisions")
        require(type(decisions["schema_version"]) is int and decisions["schema_version"] == 1
                and type(decisions["decisions"]) is list and len(decisions["decisions"]) <= 64,
                "Unsupported decision inventory")
        for envelope in decisions["decisions"]:
            kind = envelope["kind"]
            require(kind in ("decision", "operator-decision"), "Unrecognized decision purpose")
            verified = profile.trust.verify_document(envelope, kind, rid, current=False)
            fields(verified.payload, "repository_id purpose subject context_digest")
    except FAILURES as exc:
        raise Blocked("DECISION_CONFIGURATION_INVALID", "Install the protected decision inventory from the trusted provider.") from exc
    bindings["decisions"] = digest(decisions)
    revocation = profile.live()
    bindings["revocations"] = revocation.fingerprint
    return InstalledProject(profile), bindings


def inspect_profile(profile: OperatorProfile, observation: Observation) -> tuple[dict, PreviewBinding]:
    try:
        installed, bindings = provider_inputs(profile)
        repo = observation.repository
        expected = PreviewBinding(observation.facts["discovery_digest"], bindings["policy"], bindings["assessment"],
                                  observation.checkout["ref"], observation.checkout["head"],
                                  (repo["database_id"], repo["node_id"], repo["name"], repo["default_branch"]))
        preview(profile, installed=installed, expected=expected)
    except Blocked:
        raise
    except FAILURES as exc:
        raise Blocked("CONFIGURATION_STALE_OR_UNAVAILABLE",
                      "Refresh independently signed issue, policy, and provider observations for this checkout.", status="UNKNOWN") from exc
    return bindings, expected


def read_intent(directory: Path) -> dict | None:
    path = safe_path(directory / INTENT)
    if not path.exists():
        return None
    intent = private_file(path, limit=LIMIT)
    fields(intent, "schema_version approval profile_digest trust_digest repository_id issue phase document effects")
    require(type(intent["schema_version"]) is int and intent["schema_version"] == SCHEMA
            and intent["phase"] in ("PENDING", "COMPLETE")
            and all(type(intent[k]) is str and re.fullmatch("[0-9a-f]{64}", intent[k])
                    for k in ("approval", "profile_digest", "trust_digest"))
            and type(intent["issue"]) is int and intent["issue"] > 0
            and type(intent["effects"]) is dict
            and digest(intent["document"]) == intent["profile_digest"],
            "Retained enrollment intent is invalid; preserve local records for inspection")
    return intent


def selected_directory(directory: Path, checkout: dict) -> Path:
    require(directory.is_absolute() and safe_path(directory) == directory, "Select an absolute normalized enrollment directory")
    directory = protected_path(directory, optional_leaf=True)
    require(all(disjoint(directory, root) for root in product_roots(checkout)),
            "Keep the enrollment directory outside every product checkout")
    require(disjoint(directory, installer_root()), "Keep project enrollment outside the M9-A managed installer")
    return directory


def check_enrollment_contents(directory: Path) -> None:
    if not directory.exists():
        return
    files = (directory / INTENT, directory / PROFILE)
    allowed = {"lock", INTENT, PROFILE, *(temporary_slot(path).name for path in files)}
    require(all(path.name in allowed and not path.is_symlink() for path in directory.iterdir()),
            "Enrollment directory contains unrelated contents")
    lock = directory / "lock"
    if lock.exists():
        info = lock.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and info.st_nlink == 1 and not info.st_mode & 0o077, "Unsafe enrollment lock")


def selected_authority(path: Path, checkout: dict) -> Path:
    require(path.is_absolute() and safe_path(path) == path, "Select an absolute normalized authority location")
    protected_path(path.parent)
    require(all(disjoint(path.parent, root) for root in product_roots(checkout)),
            "Select authority outside every product checkout and Git administration")
    require(disjoint(path, installer_root()), "Keep trust and service locations outside the M9-A managed installer")
    return path


def request_profile(socket: Path, trust: Trust, observation: Observation, issue: int, directory: Path) -> dict:
    require(observation.facts["discovery"] == "COMPLETE",
            "Current complete GitHub observation is required before requesting a proposal")
    require(observation.repository["default_branch"] is not None,
            "Determine the canonical default branch before choosing a feature workspace")
    require(observation.checkout["ref"] != "refs/heads/" + observation.repository["default_branch"],
            "Select an existing feature checkout")
    rows = [row for row in observation.facts["issues"] if row["number"] == issue and row["state"] == "open"]
    require(len(rows) == 1, "Select a current open issue")
    context = {"repository": observation.repository, "checkout": observation.checkout,
               "issue": rows[0], "discovery_digest": observation.facts["discovery_digest"],
               "enrollment_directory": str(directory)}
    public(context)
    challenge = {"schema_version": SCHEMA, "purpose": "enrollment/profile",
                 "required_kind": "profile", "repository_id": observation.repository["repository_id"],
                 "trust_digest": trust.fingerprint, "context_digest": digest(context), "context": context}
    try:
        response = exchange(socket, challenge)
        trust.verify_document(response, "profile", observation.repository["repository_id"])
        return response
    except FAILURES as exc:
        raise Blocked("OPERATOR_PROPOSAL_REQUIRED",
                      "Connect the trusted operator service and obtain a current signed proposal for the exact selection.") from exc


@dataclass(frozen=True)
class Plan:
    summary: dict
    profile: OperatorProfile
    expected: PreviewBinding

    @property
    def approval(self) -> str:
        return digest(self.summary)

    @property
    def directory(self) -> Path:
        return self.profile.path.parent


def prepare(observation: Observation, directory: Path, trust_path: Path, issue: int | None,
            socket: Path | None) -> Plan:
    check_enrollment_contents(directory)
    trust = Trust(trust_path)
    intent = read_intent(directory)
    if intent is None:
        require(not (directory / PROFILE).exists(), "Existing profile requires explicit reconnect; no adoption")
        require(type(issue) is int and issue > 0 and socket is not None, "Select an issue and an operator proposal service")
        document = request_profile(socket, trust, observation, issue, directory)
    else:
        require((issue is None or issue == intent["issue"]) and trust.fingerprint == intent["trust_digest"]
                and observation.repository["repository_id"] == intent["repository_id"],
                "Trust, issue, or repository differs from the retained enrollment")
        issue, document = intent["issue"], intent["document"]
    try:
        profile = profile_from_proposal(directory, trust_path, document)
        require(profile.trust.fingerprint == trust.fingerprint, "Trust root changed during enrollment inspection")
        match_observation(profile, observation, issue)
    except FAILURES as exc:
        raise Blocked("PROPOSAL_CONFLICT", "Reconcile the signed proposal with the selected branch, issue, repository, trust and protected paths.") from exc
    try:
        effects, writer = local_effects(profile, directory, observation.checkout)
        memory = writer.inspect()
        existing = safe_path(profile.state / ENROLLMENT_RECORD)
        if intent is None:
            require(memory["health"] == "UNINITIALIZED" and not existing.exists() and not profile.state.exists(),
                    "Previously established state requires explicit reconnect")
        else:
            check_initial_or_continuation(profile, memory, intent)
    except Blocked:
        raise
    except FAILURES as exc:
        raise Blocked("LOCAL_STATE_REQUIRES_RECONCILIATION",
                      "Confirm isolated owned paths, local bare coordination, and the retained enrollment before setup.") from exc
    bindings, expected = inspect_profile(profile, observation)
    summary = {"repository": observation.repository, "checkout": observation.checkout, "issue": issue,
               "observation_digest": digest(observation.facts), "profile_digest": profile.fingerprint,
               "trust_digest": profile.trust.fingerprint, "provider_binding_digest": digest(bindings),
               "delegation": {key: profile.delegation[key] for key in ("operations", "branches", "merge_mode", "merge_methods", "reviews")},
               "window": profile.payload["window"],
               "checks": [{"name": c.name, "phase": str(c.phase)} for c in profile.checks],
               "check_provider": profile.payload["providers"]["validation"]["kind"],
               "effects": effects}
    public(summary)
    encode(summary, LIMIT)
    result = Plan(summary, profile, expected)
    require(intent is None or intent["approval"] == result.approval,
            "Current facts no longer match the approved interrupted enrollment")
    return result


def check_initial_or_continuation(profile: OperatorProfile, memory: dict, intent: dict) -> None:
    require(intent["profile_digest"] == profile.fingerprint and intent["trust_digest"] == profile.trust.fingerprint,
            "Retained enrollment cannot adopt a different profile or trust root")
    require(memory["health"] in ("UNINITIALIZED", "SYNCED"), "Use existing M1 recovery for interrupted or foreign state")
    if memory["health"] == "SYNCED":
        verify_enrollment(profile)
        require(guided_binding(profile) == str(profile.path.parent), "Guided enrollment provenance is missing or changed")
        state = memory["state"]
        initialized = state["schema_version"] == 3 and state["execution"]["schema_version"] == 3
        if not initialized:
            if not memory["local_owner"]:
                raise Blocked("M1_OWNERSHIP_REQUIRED",
                              "Reconcile the existing checkpoint and establish its original ownership through M1 before resuming.")
    else:
        require(intent["phase"] == "PENDING", "Completed enrollment has lost its memory; preserve retained evidence")


def completed(profile: OperatorProfile, memory: dict) -> bool:
    state = memory.get("state", {})
    if memory["health"] == "SYNCED" and state.get("schema_version") == 3 and state["execution"]["schema_version"] == 3:
        verify_enrollment(profile)
        return True
    return False


def apply_plan(plan: Plan, *, approved: str, authorized: bool) -> dict:
    require(authorized and approved == plan.approval, "Approve the exact plan digest and explicitly authorize memory writes")
    directory, profile = plan.directory, plan.profile
    checkout = plan.summary["checkout"]
    require(selected_directory(directory, checkout) == directory, "Enrollment directory changed")
    directory.mkdir(mode=0o700, exist_ok=True)
    protected_path(directory)
    check_enrollment_contents(directory)
    with locked(directory):
        require(local_checkout(Path(checkout["path"]), checkout["remote"]) == checkout, "Checkout changed after approval")
        require(profile.trust.fingerprint == Trust(profile.trust.path).fingerprint,
                "Trust changed after plan approval")
        profile.live()
        _, bindings = provider_inputs(profile)
        require(digest(bindings) == plan.summary["provider_binding_digest"],
                "Provider bootstrap inputs changed after approval")
        intent = read_intent(directory)
        effects, writer = local_effects(profile, directory, checkout)
        require(effects == plan.summary["effects"], "Local coordination effects changed after approval")
        memory = writer.inspect()
        if intent is None:
            require(not profile.path.exists() and not profile.state.exists() and memory["health"] == "UNINITIALIZED",
                    "Existing state requires its original enrollment")
            intent = {"schema_version": SCHEMA, "approval": approved, "profile_digest": profile.fingerprint,
                      "trust_digest": profile.trust.fingerprint, "repository_id": profile.repository_id,
                      "issue": plan.summary["issue"], "phase": "PENDING", "document": profile.evidence.document,
                      "effects": effects}
            atomic(directory / INTENT, encode(intent, LIMIT))
        else:
            require(intent["approval"] == approved and intent["effects"] == effects,
                    "Existing enrollment has a different approved intent")
            check_initial_or_continuation(profile, memory, intent)
        if not profile.path.exists():
            require(intent["phase"] == "PENDING" and memory["health"] == "UNINITIALIZED",
                    "Preserve completed enrollment; restore the original protected profile")
            atomic(profile.path, encode(intent["document"]))
        installed = load_profile(profile.path, profile.trust.path)
        require(installed.fingerprint == intent["profile_digest"] and installed.trust.fingerprint == intent["trust_digest"],
                "Published profile or trust differs from the original approved intent")
        if completed(installed, memory):
            outcome = "ALREADY_ENROLLED"
            generation = memory["state"]["generation"]
        else:
            answer = setup(installed, authorized=True, expected_preview=plan.expected, bound_memory=writer)
            outcome, generation = "ENROLLED", answer["generation"]
        if intent["phase"] != "COMPLETE":
            atomic(directory / INTENT, encode(dict(intent, phase="COMPLETE"), LIMIT))
    return {"status": outcome, "repository_id": profile.repository_id, "generation": generation,
            "profile": str(profile.path), "execution": "NOT_STARTED"}


def read_enrollment(directory: Path | None, profile_path: Path | None, trust: Path, checkout: dict,
                    command: str, discovery_factory) -> dict:
    explicit = profile_path is not None
    intent = read_intent(directory) if directory is not None else None
    if profile_path is None:
        require(directory is not None, "Select an enrollment directory or an existing protected profile")
        profile_path = directory / PROFILE
        if not profile_path.exists():
            return {"status": "PENDING" if intent else "NOT_ENROLLED", "next_action": "Use the original approved plan to apply setup."}
        require(intent is not None, "Restore the original protected guided enrollment intent")
    profile = load_profile(profile_path, trust)
    match_checkout(profile, checkout)
    binding = guided_binding(profile)
    if binding is None and (explicit or safe_path(profile.state / ENROLLMENT_RECORD).exists()):
        raise Blocked("GUIDED_RECORD_REQUIRED",
                      "Restore the original guided enrollment record. Use the installed operator commands for an earlier M7 profile.")
    if binding is not None:
        original = selected_directory(Path(binding), checkout)
        require(directory is None or directory == original, "Reconnect through the original guided enrollment")
        directory = original
        intent = read_intent(directory)
        require(intent is not None, "Restore the original protected enrollment intent before reconnecting")
    require(directory is not None and intent is not None, "Restore the original guided enrollment intent")
    require(profile.fingerprint == intent["profile_digest"] and profile.trust.fingerprint == intent["trust_digest"],
            "Persisted profile or trust does not match the enrollment intent")
    effects, writer = local_effects(profile, directory, checkout)
    require(effects == intent["effects"], "Local coordination no longer matches the retained enrollment destination")
    observed = status(profile, bound_memory=writer, recovery=True)
    report = {key: observed[key] for key in ("repository_id", "memory_health", "local_owner", "generation", "enrollment", "execution_liveness")}
    memory = writer.inspect(recovery=True)
    report["status"] = "ENROLLED" if completed(profile, memory) else "PENDING"
    if report["status"] == "ENROLLED":
        require(binding is not None, "Restore the original guided enrollment provenance")
    state = memory.get("state", {})
    journal = memory.get("recovery_journal")
    slots = memory.get("recovery_slots", [])
    recoverable = (command == "status" and binding is not None and observed["enrollment"] == "MATCHED"
                   and state.get("schema_version") == 3 and state["execution"]["schema_version"] == 3
                   and memory.get("local_owner") is True
                   and (memory["health"] == "REMOTE_MISMATCH" and memory["remote_head"] is not None
                        or memory["health"] == "RECOVERY_REQUIRED" and (journal is not None or bool(slots))))
    if report["status"] == "ENROLLED" or recoverable:
        require(memory["health"] == observed["memory_health"] and memory["local_owner"] == observed["local_owner"]
                and state["generation"] == observed["generation"], "Coordination observation changed")
        if recoverable:
            verify_enrollment(profile)
        track = state["execution"].get("track")
        report["invocation"] = {"profile_digest": profile.fingerprint, "trust_digest": profile.trust.fingerprint,
                                "checkout": checkout,
                                "checkpoint": memory["local_head"], "remote_checkpoint": memory["remote_head"],
                                "recovery_journal": journal,
                                "recovery_slots": digest(slots),
                                "issues": [task.number for task in profile.tasks],
                                "operations": profile.delegation["operations"],
                                "merge_mode": profile.delegation["merge_mode"],
                                "checks": [{"name": check.name, "phase": str(check.phase)} for check in profile.checks],
                                "window": profile.payload["window"],
                                "track_current": (track is not None and track["id"] == profile.payload["window"]["id"]
                                                  and track["generation"] == state["generation"]),
                                "used_rounds": track["used_rounds"] if track else 0}
    if command == "reconnect":
        verify_enrollment(profile)
        require(report["status"] == "ENROLLED", "Restore synchronized memory before reconnecting")
        authority = OperatorAuthority(profile)
        token = authority.credential(profile.payload["providers"]["credentials"]["read"], READ_PERMISSIONS)
        remote = canonical(discovery_factory(token.token), checkout["repository"], profile.repository_id)
        require(remote["node_id"] == profile.payload["repository"]["node_id"], "Canonical GitHub node identity changed")
        report["status"] = "RECONNECTED"
    if command in ("doctor", "preview"):
        if command == "doctor":
            report["runtime"] = runtime_capability(profile.state)
        try:
            installed, _ = provider_inputs(profile)
            inspected = preview(profile, installed=installed)
            report["configuration"] = inspected["status"]
            report["tasks"] = [{"issue_id": row["issue_id"],
                                "status": row["status"],
                                "assessment": "AVAILABLE" if row.get("packet_preview") else "UNKNOWN"}
                               for row in inspected["tasks"]]
        except Blocked as exc:
            report["configuration"] = "UNKNOWN"
            report["blocker"] = {"code": exc.reason, "action": str(exc)}
        except FAILURES:
            report["configuration"] = "UNKNOWN"
        if report["configuration"] != "CONFIGURATION_VERIFIED":
            report["status"] = "UNKNOWN"
            report["next_action"] = "Restore current independent policy, scope, check and credential providers."
    report["profile"] = str(profile_path)
    public(report)
    return report
