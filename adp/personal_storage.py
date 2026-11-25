"""Protected, explicit-consent state for the opt-in personal backend.

These are local operator records, not signed provider documents or portable
authority. Product workers never receive this directory or its contents.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import time

from .config import Config, load_json, safe_path
from .discovery_schema import digest
from .errors import ADPError
from .execution_privacy import credential_shaped
from .git import author, git, value
from .memory import Memory
from .schema import encode, fields, require
from .storage import atomic, locked

LIMIT = 131072
INTENT = "personal.json"
TOKEN = re.compile(r"p1\.([0-9]{1,12})\.([0-9]{1,12})\.([0-9a-f]{32})\.([0-9a-f]{64})\Z")
ROLE_LIMITS = {"maximum_tasks": 1, "maximum_rounds": 1, "maximum_parallel": 1,
               "scope_reviewers": 1, "developers": 2, "candidate_reviewers": 2,
               "code_reviewers": 2, "forensic_reviewers": 2,
               "maximum_check_observations": 3, "worker_seconds": 300}


class PersonalBlocked(ADPError):
    def __init__(self, code, action, *, status="BLOCKED"):
        super().__init__(action)
        self.reason, self.status = code, status


def disjoint(a: Path, b: Path) -> bool:
    return not a.is_relative_to(b) and not b.is_relative_to(a)


def private_directory(path: Path, *, missing=False) -> Path:
    require(path.is_absolute() and safe_path(path) == path and path != Path("/"),
            "Select an absolute normalized personal-state directory")
    current = path
    while not current.exists():
        require(missing, "Retained personal state is unavailable")
        current = current.parent
    info = current.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and not info.st_mode & 0o022, "Use an owned directory without group/other write access")
    if path.exists():
        require(stat.S_IMODE(path.stat().st_mode) == 0o700,
                "Personal state requires an owned mode-0700 directory")
    return path


def create_private(path: Path) -> None:
    private_directory(path, missing=True)
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    private_directory(path)


def read_private(path: Path, *, optional=False):
    from .personal_read_frame import private_path
    private_path(path)
    safe_path(path)
    if not path.exists() and optional:
        from .personal_read_frame import consumed
        consumed(path)
        return None
    return load_json(path, LIMIT, protected=True)


def token_parts(token: str, now: int):
    match = TOKEN.fullmatch(token or "")
    require(match is not None, "Review the current personal plan or invocation")
    issued, expires = int(match[1]), int(match[2])
    require(0 <= issued <= now < expires and 0 < expires - issued <= 3600,
            "Personal approval window is expired or invalid")
    return issued, expires, match[3], match[4]


def approval(plan: dict) -> str:
    window = plan["window"]
    return ".".join(("p1", str(window["issued_at"]), str(window["expires_at"]),
                     window["nonce"], digest(plan)))


def assert_public(value_) -> None:
    require(not credential_shaped(value_), "Private credential-shaped data cannot enter personal output")
    encode(value_, LIMIT)


def validate_plan(plan, directory):
    """Closed personal data never widens an existing signed or M2 contract."""
    from .discovery_schema import typed
    from .git import SHA
    from .policy_schema import branch, product_path
    from .project_validation_types import RequiredCheck, Phase
    from .enrollment import installer_root
    from .schema import integer, string
    fields(plan, "schema_version mode repository owner checkout administration issue issue_id original_digest discovery_digest "
        "governance_digest governance native_prerequisites admission feature paths criterion commit_message commit_body "
        "checks check_requirements required_check_names check_identity_status unresolved_check_names accept_native_job_records "
        "branch_rules operations merge_mode publication author window guard effects")
    require(type(plan["schema_version"]) is int and plan["schema_version"] == 1 and plan["mode"] == "PERSONAL",
            "Unsupported personal plan")
    repository, checkout, feature, window, effects = (plan[name] for name in ("repository", "checkout", "feature", "window", "effects"))
    fields(repository, "repository_id database_id node_id name default_branch")
    integer(repository["database_id"], 1)
    require(repository["repository_id"] == str(repository["database_id"]), "Personal repository identity differs")
    fields(plan["owner"], "account_id repository_id read_access push_access admin_access")
    integer(plan["owner"]["account_id"], 1)
    require(plan["owner"]["repository_id"] == repository["repository_id"]
            and plan["owner"]["read_access"] is True, "Personal owner/access identity differs")
    fields(checkout, "path remote repository ref head")
    from .personal_git import administration
    require(plan["administration"] == administration(Path(checkout["path"])), "Original product Git administration changed")
    require(repository["name"] == checkout["repository"] and SHA.fullmatch(checkout["head"])
            and checkout["ref"].startswith("refs/heads/"), "Invalid personal source binding")
    fields(feature, "workspace branch prepare preparation")
    require(type(feature["prepare"]) is bool and feature["branch"] != repository["default_branch"],
            "Personal features cannot target the default branch")
    require(feature["preparation"] == ("AFTER_INDEPENDENT_POLICY_REVIEW" if feature["prepare"] else "EXISTING"),
            "Feature preparation cannot bypass independent policy review")
    branch(feature["branch"])
    fields(window, "issued_at expires_at nonce " + " ".join(ROLE_LIMITS))
    integer(window["issued_at"])
    integer(window["expires_at"], 1)
    require(60 <= window["expires_at"] - window["issued_at"] <= 3600
            and type(window["nonce"]) is str and re.fullmatch("[0-9a-f]{32}", window["nonce"]), "Invalid personal finite window")
    require(all(type(window[name]) is int and window[name] == maximum for name, maximum in ROLE_LIMITS.items()),
            "Personal role/resource limits cannot be expanded")
    fields(effects, "directory coordination coordination_remote memory private marker memory_ref")
    from .guard_types import Limits, data
    require(plan["guard"] == {"limits": data(Limits()), "forensic_backend": "UNSUPPORTED_STOP", "budget_reset": "NOT_PERMITTED"}
            and effects["memory_ref"] == "refs/heads/adp/personal", "Accepted guard limits or original coordination ref changed")
    require(effects["directory"] == str(directory) and effects["coordination"] == str(directory / "coordination")
            and effects["coordination_remote"] == str(directory / "coordination.git")
            and effects["memory"] == str(directory / "memory") and effects["private"] == str(directory / "private"),
            "Personal coordination destinations changed")
    common = Path(value(Path(checkout["path"]), "rev-parse", "--path-format=absolute", "--git-common-dir"))
    require(disjoint(directory, Path(checkout["path"])) and disjoint(directory, common)
            and disjoint(directory, Path(__file__).resolve().parents[1]) and disjoint(directory, installer_root()),
            "Personal state cannot overlap source, Git administration or engine")
    expected_marker = common / "adp-personal" / (digest({"repository": repository["repository_id"],
                                                       "issue": plan["issue_id"]}) + ".json")
    require(effects["marker"] == str(expected_marker), "Personal enrollment marker destination changed")
    for name in ("path",):
        path = Path(checkout[name])
        require(path.is_absolute() and safe_path(path) == path, "Invalid source location")
    workspace = Path(feature["workspace"])
    require(workspace.is_absolute() and safe_path(workspace) == workspace and disjoint(workspace, directory)
            and disjoint(workspace, installer_root()),
            "Feature and private state overlap")
    require(type(plan["paths"]) is list and 0 < len(plan["paths"]) <= 32
            and len(set(plan["paths"])) == len(plan["paths"]), "Bounded unique original source paths are required")
    for path in plan["paths"]:
        product_path(path)
    integer(plan["issue"], 1)
    string(plan["issue_id"])
    for name in ("original_digest", "discovery_digest", "governance_digest"):
        require(type(plan[name]) is str and re.fullmatch("[0-9a-f]{64}", plan[name]), "Invalid personal evidence digest")
    expected_ops = ["INSPECT", "EDIT", "STAGE", "COMMIT", "VALIDATE"] + (["BRANCH"] if feature["prepare"] else [])
    require(plan["operations"] == expected_ops and plan["merge_mode"] == "MANUAL"
            and plan["publication"] == "NOT_DELEGATED", "Personal mode has no implicit external effects")
    require(plan["check_requirements"] in ("PRESENT", "VERIFIED_ABSENT", "UNKNOWN")
            and plan["check_identity_status"] in ("NOT_REQUESTED", "OBSERVED", "UNKNOWN")
            and type(plan["accept_native_job_records"]) is bool, "Invalid check knowledge or provenance choice")
    checks = tuple(typed(RequiredCheck, row) for row in plan["checks"])
    require(len(checks) <= 32 and len({row.name for row in checks}) == len(checks)
            and all(row.phase == Phase.BEFORE_PR and row.provider in ("github-check", "github-status") for row in checks),
            "Invalid native personal check policy")
    for name in ("required_check_names", "unresolved_check_names"):
        require(type(plan[name]) is list and len(plan[name]) <= 32 and len(set(plan[name])) == len(plan[name]),
                "Invalid check identity inventory")
        for item in plan[name]:
            string(item, 128)
    require(set(plan["required_check_names"]) == {row.name for row in checks} | set(plan["unresolved_check_names"]),
            "Prescribed check names cannot disappear")
    if plan["check_requirements"] == "VERIFIED_ABSENT":
        require(not plan["required_check_names"] and not plan["governance"] and not feature["prepare"]
                and plan["branch_rules"] and all(row["rules"] == "OBSERVED" for row in plan["branch_rules"]),
                "Unknown requirements cannot become an absence claim")
    require(type(plan["author"]) is list and len(plan["author"]) == 2, "Approved Git author required")
    for item in plan["author"]:
        string(item, 256)
    assert_public(plan)


@dataclass(frozen=True)
class PersonalState:
    directory: Path
    intent: dict

    @property
    def plan(self):
        return self.intent["plan"]

    @property
    def repository_id(self):
        return self.plan["repository"]["repository_id"]

    @property
    def state(self):
        return self.directory / "private"

    @property
    def feature(self):
        return Path(self.plan["feature"]["workspace"])

    def memory(self):
        cfg = Config.discover(self.directory / "coordination", remote="memory",
                              repository_id=self.repository_id, branch="adp/personal",
                              storage=self.directory / "memory")
        require(cfg.root == self.directory / "coordination", "Coordination root changed")
        require(value(cfg.root, "remote", "get-url", "memory") == str(self.directory / "coordination.git"),
                "Coordination endpoint changed")
        require(value(self.directory / "coordination.git", "rev-parse", "--is-bare-repository") == "true",
                "The original owned coordination remote is required")
        return Memory(cfg, pinned_local_remote=self.directory / "coordination.git")

    def live(self, now, *, owner=False):
        current = load_state(self.directory)
        require(current.intent == self.intent, "Personal enrollment changed; preserve the original intent")
        window = self.plan["window"]
        require(window["issued_at"] <= now < window["expires_at"], "Personal window expired")
        if owner:
            observed = self.memory().inspect()
            require(observed["health"] == "SYNCED" and observed["local_owner"],
                    "The original synchronized M1 owner is required")
        return self


def load_state(directory: Path) -> PersonalState:
    private_directory(directory)
    from .personal_read_frame import present
    if present(directory / "episode.json"):
        from .personal_episode import load_episode
        return load_episode(directory)
    row = read_private(directory / INTENT)
    fields(row, "schema_version kind phase plan original governance approval")
    require(type(row["schema_version"]) is int and row["schema_version"] == 1
            and row["kind"] == "PERSONAL" and row["phase"] in ("PREPARED", "ENROLLED")
            and type(row["plan"]) is dict and row["approval"] == approval(row["plan"]),
            "Unsupported or changed personal enrollment")
    require(row["plan"]["effects"]["directory"] == str(directory),
            "Personal enrollment cannot move or adopt another state directory")
    validate_plan(row["plan"], directory)
    expected_marker = {"schema_version": 1, "directory": str(directory), "approval": row["approval"]}
    require(read_private(Path(row["plan"]["effects"]["marker"]), optional=True) == expected_marker,
            "The original personal enrollment marker is missing or changed")
    require(row["plan"]["original_digest"] == digest(row["original"])
            and row["plan"]["governance_digest"] == digest(row["governance"]),
            "Retained original or governance evidence changed")
    require(row["original"]["identity"]["repository_id"] == row["plan"]["repository"]["repository_id"]
            and row["original"]["identity"]["issue_id"] == row["plan"]["issue_id"]
            and row["original"]["number"] == row["plan"]["issue"]
            and row["plan"]["criterion"] == "original-ticket:" + row["original"]["revision"],
            "Original ticket and personal scope identity differ")
    return PersonalState(directory, row)


def persist_intent(directory, plan, original, governance):
    """The caller already reobserved and compared explicit operator consent."""
    validate_plan(plan, directory)
    create_private(directory)
    with locked(directory):
        path = directory / INTENT
        row = {"schema_version": 1, "kind": "PERSONAL", "phase": "PREPARED", "plan": plan,
               "original": original, "governance": governance, "approval": approval(plan)}
        if path.exists():
            current = load_state(directory)
            require({**current.intent, "phase": "PREPARED"} == row,
                    "An existing personal enrollment cannot be replaced or renewed")
            return current
        require(set(p.name for p in directory.iterdir()) <= {"lock"},
                "Do not adopt unrelated private files or an interrupted unknown intent")
        atomic(path, encode(row, LIMIT), replace=False)
        return PersonalState(directory, row)


def initialize_coordination(personal: PersonalState, *, clock=None):
    """Create only exact, approved local destinations, retaining partial intent.

    An existing Git root is accepted only after verifying the immutable intent
    and its exact destination/configuration. Canonical M1 initialization and
    ownership are deliberately separate and use their existing initial-only CAS.
    """
    root = personal.directory
    read_clock = clock or (lambda: int(time.time()))
    personal.live(read_clock())
    require(load_state(root).intent == personal.intent, "Original personal intent is required")
    name, email = personal.plan["author"]
    for leaf in ("coordination", "coordination.git", "private"):
        personal.live(read_clock())
        path = root / leaf
        if not path.exists():
            path.mkdir(mode=0o700)
        private_directory(path)
    bare, checkout = root / "coordination.git", root / "coordination"
    if not (bare / "HEAD").exists():
        personal.live(read_clock())
        require(not any(bare.iterdir()), "Unknown partial coordination remote requires reconciliation")
        git(bare, "init", "--bare", "--initial-branch=coordination")
    require(value(bare, "rev-parse", "--is-bare-repository") == "true", "Coordination remote changed")
    if not (checkout / ".git").exists():
        personal.live(read_clock())
        require(not any(checkout.iterdir()), "Unknown coordination checkout requires reconciliation")
        git(checkout, "init", "--initial-branch=coordination")
    require(value(checkout, "rev-parse", "--show-toplevel") == str(checkout), "Coordination root changed")
    require(value(checkout, "rev-parse", "--path-format=absolute", "--git-common-dir") == str(checkout / ".git")
            and value(checkout, "rev-parse", "--absolute-git-dir") == str(checkout / ".git"),
            "Coordination Git administration differs from the approved destination")
    from .git import optional_config
    for key, expected in (("user.name", name), ("user.email", email),
                          ("remote.memory.url", str(bare))):
        actual = optional_config(checkout, key)
        require(actual in (None, expected), "An existing coordination setting differs from the approved plan")
        if actual is None:
            personal.live(read_clock())
            git(checkout, "config", key, expected)
    require(author(checkout) == (name, email), "Approved coordination author changed")


def complete_setup(personal: PersonalState, *, clock=None):
    from .execution_memory import ExecutionJournal
    read_clock = clock or (lambda: int(time.time()))
    personal.live(read_clock())
    with locked(personal.directory):
        initialize_coordination(personal, clock=read_clock)
        personal.live(read_clock())
        memory = personal.memory()
        observed = memory.inspect()
        if observed["health"] == "UNINITIALIZED":
            personal.live(read_clock())
            memory.initialize(authorized=True, initial_only=True)
            observed = memory.inspect()
        require(observed["health"] == "SYNCED", "Use retained M1 recovery; never reset personal memory")
        if observed["state"]["owner"] is None:
            personal.live(read_clock())
            # Only the pristine, never-claimed original namespace is recoverable.
            # M1's initial_only CAS rejects released, foreign and advanced state.
            require(personal.intent["phase"] == "PREPARED", "Released enrollment cannot reclaim ownership")
            memory.claim("personal-operator", initial_only=True)
        else:
            require(observed["local_owner"], "A foreign M1 owner cannot be adopted")
        if memory.inspect()["state"]["schema_version"] == 1:
            personal.live(read_clock())
            memory.upgrade_guard(authorized=True)
        personal.live(read_clock())
        ExecutionJournal(memory).upgrade(authorized=True)
        current = load_state(personal.directory)
        if current.intent["phase"] != "ENROLLED":
            personal.live(read_clock())
            atomic(personal.directory / INTENT, encode({**current.intent, "phase": "ENROLLED"}, LIMIT))
    return load_state(personal.directory)
