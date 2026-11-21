"""Bounded presentation and explicit dispatch for the installed Codex Skill."""
from __future__ import annotations

from argparse import Namespace
import re
import unicodedata

from . import enrollment_cli, operator_cli
from .codex_runtime import CodexExecRuntime
from .discovery_schema import digest
from .enrollment import (Blocked, FAILURES, LIMIT, PROFILE, installer_root, local_checkout, public,
                         selected_authority, selected_directory)
from .git import SHA
from .operator_profile import SUPPORTED
from .schema import encode, fields, integer, require, string

ENROLLMENT = ("inspect", "plan", "apply", "status", "doctor", "preview", "reconnect")
EXECUTION = ("run", "resume", "handoff")
ACTIONS = ("capabilities", *ENROLLMENT, *EXECUTION)
QUESTIONS = {
    "enrollment_directory": ("absolute_path", "--directory"),
    "operator_trust": ("absolute_path", "--operator-trust"),
    "issue": ("issue_number", "--issue"),
    "operator_proposal_service": ("absolute_path", "--operator-socket"),
}
SUCCESS = {
    "inspect": ("OBSERVED",), "plan": ("PROPOSED",), "apply": ("ENROLLED", "ALREADY_ENROLLED"),
    "status": ("ENROLLED",), "doctor": ("ENROLLED",), "preview": ("ENROLLED",), "reconnect": ("RECONNECTED",),
}
BLOCKED = ("BLOCKED", "UNKNOWN", "PENDING", "NOT_ENROLLED")
HINTS = {
    "DISCOVERY_CREDENTIAL_REQUIRED": "Authenticate gh for github.com outside the chat, or select the environment variable holding a read credential.",
    "DISCOVERY_CREDENTIAL_INVALID": "Select a valid read credential input outside the chat.",
    "DISCOVERY_CREDENTIAL_REFUSED": "Check the authenticated account's read access to the selected GitHub repository.",
    "REPOSITORY_UNAVAILABLE": "Confirm the canonical remote and the selected account's repository access.",
    "REPOSITORY_IDENTITY_MISMATCH": "Confirm the selected HTTPS remote and immutable GitHub repository ID.",
    "DISCOVERY_UNAVAILABLE": "Restore complete GitHub issue and dependency observations.",
    "AUTHORITY_NOT_ESTABLISHED": "Select the independent trust root and operator proposal service before setup.",
    "CONFIGURATION_REQUIRED": "Answer the outstanding setup questions.",
    "TRUST_ROOT_REQUIRED": "Select the protected independent trust root.",
    "OPERATOR_PROPOSAL_REQUIRED": "Confirm the trusted proposal service is running and the Codex session has approved access to its local socket.",
    "PROPOSAL_CONFLICT": "Reconcile the signed proposal with the selected project, issue, checkout and trust.",
    "MISSING_TRUST_ROLE": "Ask the project operator to provision separate verifiers for the required independent providers.",
    "PROJECT_POLICY_REQUIRED": "Obtain current repository-bound data from the independent policy provider.",
    "INDEPENDENT_SCOPE_REQUIRED": "Obtain the independent scope review for the selected issue and checkout.",
    "PROJECT_CHECK_PROVIDER_REQUIRED": "Restore fresh, scoped evidence from the independent project check provider.",
    "SCOPED_CREDENTIAL_REQUIRED": "Ask the trusted issuer for the repository-scoped installation credentials required by the selected profile.",
    "DECISION_CONFIGURATION_INVALID": "Ask the trusted provider to restore its protected decision inventory.",
    "CONFIGURATION_STALE_OR_UNAVAILABLE": "Refresh independently signed inputs and remote metadata for the selected checkout.",
    "LOCAL_STATE_REQUIRES_RECONCILIATION": "Reconcile protected paths and retained ownership before retrying setup.",
    "M1_OWNERSHIP_REQUIRED": "Use the accepted M1 ownership procedure for the existing checkpoint.",
    "GUIDED_RECORD_REQUIRED": "Restore the original guided record, or use the existing operator interface for an earlier M7 profile.",
    "OPERATOR_APPROVAL_REQUIRED": "Approve the exact plan and its coordination-memory writes.",
    "APPROVAL_MISMATCH": "Review the current plan and obtain fresh confirmation.",
    "UNSAFE_STALE_OR_UNAVAILABLE": "Check the selected checkout, retained intent, protected paths and provider access.",
    "PROTOCOL_BOUND": "Select a project within the supported observation bounds.",
}


def add_commands(commands) -> None:
    codex = commands.add_parser("codex", help="Versioned presentation for the installed ADP Codex Skill")
    stages = codex.add_subparsers(dest="enroll_command", required=True)
    stages.add_parser("capabilities")
    for name in ENROLLMENT:
        command = stages.add_parser(name)
        enrollment_cli.selectors(command, name)
        if name in ("preview", "status"):
            command.add_argument("--for-operation", choices=("run",) if name == "preview" else ("resume", "handoff"))
            invocation_limits(command)
    for name in EXECUTION:
        command = stages.add_parser(name)
        enrollment_cli.selectors(command, "status")
        command.add_argument("--reviewed", help="Review token from the current preview or status")
        command.add_argument("--authorize-execution", action="store_true")
        if name != "handoff":
            invocation_limits(command)


def invocation_limits(command):
    command.add_argument("--rounds", type=int, default=1)
    command.add_argument("--maximum-parallel", type=int, default=1)


def label(value, maximum=4096):
    string(value, maximum)
    require(all(unicodedata.category(c) not in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in value),
            "Unsafe display label")
    return value


def choice(value, options):
    require(type(value) is str and value in options, "Unsupported protocol value")
    return value


def number(value, minimum=0):
    integer(value, minimum)
    return value


def hex_digest(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "Invalid digest")
    return value


def boolean(value):
    require(type(value) is bool, "Invalid protocol boolean")
    return value


def revision(value):
    require(type(value) is str and SHA.fullmatch(value), "Invalid Git revision")
    return value


def rows(value, parse, maximum=512):
    require(type(value) is list and len(value) <= maximum, "Unsupported protocol array")
    return [parse(row) for row in value]


def checkout(row):
    return {"path": label(row["path"]), "remote": label(row["remote"], 128),
            "repository": label(row["repository"], 202), "ref": label(row["ref"], 255), "head": revision(row["head"])}


def repository(row):
    identity = number(row["database_id"], 1)
    require(row["repository_id"] == str(identity), "Conflicting repository identity")
    return {"name": label(row["name"], 202), "database_id": identity,
            "default_branch": label(row["default_branch"], 255) if row["default_branch"] is not None else None}


def runtime():
    caps = CodexExecRuntime(installer_root() / "runtime").capabilities()
    # A version is informational. Capability support comes only from the accepted probe.
    version = (caps.version if re.fullmatch(r"(?:codex-cli )?[0-9]+(?:\.[0-9]+)+(?:[-+][0-9A-Za-z.-]+)?",
                                           caps.version) else "UNKNOWN")
    return {"status": "SUPPORTED" if caps.independent_contexts else "UNSUPPORTED_RUNTIME",
            "version": version, "qualification": "NOTRUN"}


def observed_runtime(row):
    return {"status": choice(row["status"], ("SUPPORTED", "UNKNOWN")),
            "qualification": choice(row["qualification"], ("NOTRUN",))}


def facts(row):
    def issue(item):
        return {"number": number(item["number"], 1), "state": choice(item["state"], ("open", "closed")),
                "native_dependencies": rows(item["native_dependencies"], lambda edge: {
                    "repository": label(edge["repository"], 202), "number": number(edge["number"], 1),
                    "kind": choice(edge["kind"], ("BLOCKED_BY", "SUB_ISSUE")),
                })}
    return {"repository": repository(row["repository"]), "checkout": checkout(row["checkout"]),
            "discovery": choice(row["discovery"], ("COMPLETE", "UNKNOWN")),
            "issues": rows(row["issues"], issue),
            "branch_rules": rows(row["branch_rules"], lambda rule: {
                "ref": label(rule["ref"], 255),
                "protected": boolean(rule["protected"]) if rule["protected"] is not None else None,
                "rules": choice(rule["rules"], ("OBSERVED", "UNKNOWN")),
                "required_check_contexts": rows(rule["required_check_contexts"], lambda name: label(name, 128)),
            }, 2),
            "governance": rows(row["governance"], lambda file: label(file["path"])),
            "workflows": rows(row["workflows"], lambda file: label(file["path"])),
            "runtime": observed_runtime(row["runtime"]),
            "local_enrollment": choice(row["local_enrollment"], ("PENDING", "COMPLETE", "UNSELECTED", "ABSENT"))}


def window(row):
    fields(row, "id issued_at expires_at maximum_rounds maximum_tasks maximum_parallel")
    return {"id": hex_digest(row["id"]), **{key: number(row[key], 1) for key in row if key != "id"}}


def checks(value):
    return rows(value, lambda check: {"name": label(check["name"], 256),
                "phase": choice(check["phase"], ("BEFORE_PR", "AFTER_PR"))}, 32)


def plan(row):
    effects = row["effects"]
    fields(effects, "enrollment_directory profile intent lock coordination_checkout coordination_git_directory "
           "coordination_control local_bare_remote memory_worktree private_evidence enrollment_record memory_ref authority")
    delegation = row["delegation"]
    return {"repository": repository(row["repository"]), "checkout": checkout(row["checkout"]),
            "issue": number(row["issue"], 1), "window": window(row["window"]),
            "operations": rows(delegation["operations"], lambda name: choice(name, SUPPORTED), 16),
            "merge_mode": choice(delegation["merge_mode"], ("MANUAL", "DELEGATED")),
            "required_reviews": number(delegation["reviews"], 1),
            "checks": checks(row["checks"]),
            "check_provider": choice(row["check_provider"], ("signed", "github")),
            "effects": {key: label(value) for key, value in effects.items()}}


def result(row):
    output = {"status": choice(row["status"], (*BLOCKED, "ENROLLED", "ALREADY_ENROLLED", "RECONNECTED"))}
    for key in ("repository_id", "profile"):
        if key in row:
            output[key] = label(row[key])
    if "generation" in row:
        output["generation"] = number(row["generation"]) if row["generation"] is not None else None
    if "memory_health" in row:
        output.update(memory_health=choice(row["memory_health"], ("SYNCED", "UNINITIALIZED", "REMOTE_AVAILABLE",
                      "RECOVERY_REQUIRED", "REMOTE_MISMATCH")), local_owner=boolean(row["local_owner"]),
                      execution_liveness=choice(row["execution_liveness"], ("UNKNOWN",)))
    if "configuration" in row:
        output["configuration"] = choice(row["configuration"], ("CONFIGURATION_VERIFIED", "UNKNOWN"))
    if "runtime" in row:
        output["runtime"] = observed_runtime(row["runtime"])
    if "tasks" in row:
        output["tasks"] = rows(row["tasks"], lambda task: {"issue_id": label(task["issue_id"], 128),
            "status": display_status(task["status"]), "assessment": choice(task["assessment"], ("AVAILABLE", "UNKNOWN"))}, 8)
    if "invocation" in row:
        scope = row["invocation"]
        output["invocation"] = {"profile_digest": hex_digest(scope["profile_digest"]),
                                "trust_digest": hex_digest(scope["trust_digest"]), "checkout": checkout(scope["checkout"]),
                                "checkpoint": revision(scope["checkpoint"]),
                                "remote_checkpoint": revision(scope["remote_checkpoint"]) if scope["remote_checkpoint"] is not None else None,
                                "recovery_journal": hex_digest(scope["recovery_journal"]) if scope["recovery_journal"] is not None else None,
                                "issues": rows(scope["issues"], lambda n: number(n, 1), 8),
                                "operations": rows(scope["operations"], lambda name: choice(name, SUPPORTED), 16),
                                "merge_mode": choice(scope["merge_mode"], ("MANUAL", "DELEGATED")),
                                "checks": checks(scope["checks"]),
                                "window": window(scope["window"]), "used_rounds": number(scope["used_rounds"])}
    return output


def project(command: str, raw: dict, code: int) -> dict:
    encode(raw, LIMIT)
    fields(raw, "schema_version command mode status facts questions plan approval result blockers execution_authority")
    require(type(raw["schema_version"]) is int and raw["schema_version"] == 1 and raw["command"] == command
            and raw["execution_authority"] == "UNKNOWN" and raw["mode"] == ("MUTATING" if command == "apply" else "READ_ONLY"),
            "Unsupported enrollment response")
    status = choice(raw["status"], (*SUCCESS[command], *BLOCKED))
    require(type(code) is int and code == (0 if status in SUCCESS[command] else 4), "Inconsistent enrollment outcome")

    def question(row):
        identifier = choice(row["id"], QUESTIONS)
        require((row["type"], row["argument"]) == QUESTIONS[identifier], "Unrecognized setup question")
        return {"id": identifier, "type": row["type"], "argument": row["argument"]}

    def blocker(row):
        name = row["code"]
        if type(name) is not str or name not in HINTS:
            return {"code": "UNKNOWN_BLOCKER", "action": "Inspect the current engine and independently trusted provider configuration."}
        return {"code": name, "action": HINTS[name]}

    output = {"schema_version": 1, "command": command, "status": status, "mode": raw["mode"],
              "execution_authority": "UNKNOWN", "questions": rows(raw["questions"], question, 4),
              "blockers": rows(raw["blockers"], blocker, 16)}
    if raw["facts"] is not None:
        output["facts"] = facts(raw["facts"])
    if raw["plan"] is not None and status == "PROPOSED" and command == "plan":
        output.update(plan=plan(raw["plan"]), approval=hex_digest(raw["approval"]))
    if raw["result"] is not None:
        output["result"] = result(raw["result"])
        require(output["result"]["status"] == status, "Conflicting enrollment result")
    require((status != "OBSERVED" or "facts" in output) and (status != "PROPOSED" or "plan" in output)
            and (status not in ("ENROLLED", "ALREADY_ENROLLED", "RECONNECTED") or "result" in output),
            "Missing enrollment result")
    public(output)
    encode(output, LIMIT)
    return output


def refused(command, code, action, *, status="BLOCKED"):
    return {"schema_version": 1, "command": command, "status": status, "execution_authority": "UNKNOWN",
            "blockers": [{"code": code, "action": action}]}


def display_status(value):
    return value if isinstance(value, str) and re.fullmatch("[A-Z][A-Z0-9_]{0,63}", value) else "UNKNOWN"


def invocation(view, operation, rounds, parallel):
    observed = view.get("result", {})
    scope = observed.get("invocation")
    recovering = operation == "resume" and view["status"] == "PENDING" and (
        observed.get("memory_health") in ("RECOVERY_REQUIRED", "REMOTE_MISMATCH"))
    if (view["status"] != "ENROLLED" and not recovering or scope is None or observed.get("local_owner") is not True
            or operation == "run" and observed.get("configuration") != "CONFIGURATION_VERIFIED"):
        return None, "INVOCATION_UNAVAILABLE"
    request = {"operation": operation, "recover_checkpoint": recovering}
    if operation != "handoff":
        limits = scope["window"]
        if not (1 <= rounds <= min(4, limits["maximum_rounds"] - scope["used_rounds"])
                and 1 <= parallel <= limits["maximum_parallel"]):
            return None, "INVOCATION_LIMIT"
        request.update(rounds=rounds, maximum_parallel=parallel)
    preimage = digest({"request": request, "observation": observed})
    token = ".".join(("v1", scope["profile_digest"], scope["trust_digest"], preimage))
    return {"invocation_request": request, "invocation_review": token}, None


def execution(args):
    operation = args.enroll_command
    if not args.authorize_execution or not args.reviewed:
        return refused(operation, "EXECUTION_CONFIRMATION_REQUIRED",
                       "Confirm the current invocation and explicitly authorize execution."), 4
    if not re.fullmatch(r"v1(?:\.[0-9a-f]{64}){3}", args.reviewed):
        return refused(operation, "INVOCATION_CHANGED", "Obtain the current invocation review token."), 4
    _, profile_digest, trust_digest, _ = args.reviewed.split(".")
    observed = "preview" if operation == "run" else "status"
    if operation != "handoff" and runtime()["status"] != "SUPPORTED":
        return refused(operation, "UNSUPPORTED_RUNTIME",
                       "Use a Codex CLI and host with the accepted runtime capabilities.", status="UNSUPPORTED_RUNTIME"), 7
    rounds = getattr(args, "rounds", 1)
    parallel = getattr(args, "maximum_parallel", 1)
    approved_state = None

    def observe(stage):
        raw, code = enrollment_cli.run(Namespace(**{**vars(args), "enroll_command": stage}))
        return project(stage, raw, code)

    def state(view):
        current = view.get("result", {})
        return {key: current.get(key) for key in ("status", "repository_id", "profile", "memory_health",
                                                  "local_owner", "generation", "invocation")}

    def before_effects():
        nonlocal approved_state
        changed = Blocked("INVOCATION_CHANGED", "Review current enrollment, scope and ownership, then confirm the invocation again.")
        if approved_state is None:
            view = observe(observed)
            reviewed, _ = invocation(view, operation, rounds, parallel)
            if reviewed is None or reviewed["invocation_review"] != args.reviewed:
                raise changed
            approved_state = state(view)
        # The provider preview can take time. Observe the actual ref and both
        # heads again locally, and repeat this check after native port assembly.
        if state(observe("status")) != approved_state:
            raise changed

    try:
        selected = local_checkout(args.repo, args.remote)
        require(args.operator_trust is not None and (args.directory is None) != (args.operator_profile is None),
                "Select one guided directory or profile and explicit trust")
        trust = selected_authority(args.operator_trust, selected)
        profile = (selected_directory(args.directory, selected) / PROFILE if args.directory is not None
                   else selected_authority(args.operator_profile, selected))
        native, code = operator_cli.run(Namespace(command=operation, operator_profile=profile,
                                                   operator_trust=trust, authorize_execution=True,
                                                   rounds=rounds, maximum_parallel=parallel),
                                        expected_binding=(profile_digest, trust_digest), before_effects=before_effects)
    except Blocked as exc:
        return refused(operation, exc.reason, str(exc)), 4
    except FAILURES:
        return refused(operation, "OPERATOR_REFUSED", "Reconcile the exact installed delegation and retained execution state before retrying."), 4
    # Reasons and provider text stay in the native evidence. Only fixed status codes cross into chat.
    def task(row):
        return {"issue_id": label(row["issue_id"], 128), "status": display_status(row["status"])}

    output = {"schema_version": 1, "command": operation, "status": display_status(native["status"]),
              "tasks": rows(native["tasks"], task, 8), "generation": number(native["generation"]),
              "background_work": native["background_work"] if type(native["background_work"]) is bool else "UNKNOWN",
              "unconfirmed_context_count": len(native["unconfirmed_contexts"])}
    public(output)
    return output, code


def run(args):
    command = args.enroll_command
    try:
        if command == "capabilities":
            return {"schema_version": 1, "interface": "adp-codex", "command": command,
                    "status": "AVAILABLE", "actions": list(ACTIONS), "runtime": runtime()}, 0
        if command in EXECUTION:
            return execution(args)
        raw, code = enrollment_cli.run(args)
        view = project(command, raw, code)
        operation = getattr(args, "for_operation", None)
        if operation is not None:
            proposed, blocker = invocation(view, operation, args.rounds, args.maximum_parallel)
            if proposed is None:
                action = "Check current ownership, configuration and remaining finite limits."
                if view.get("result", {}).get("memory_health") in ("RECOVERY_REQUIRED", "REMOTE_MISMATCH"):
                    action = "Reconcile the retained checkpoint using the accepted M1 operator recovery procedure."
                view["blockers"].append({"code": blocker, "action": action})
                return view, 4
            view.update(proposed)
            return view, 0
        return view, code
    except (*FAILURES, RecursionError, OverflowError):
        return refused(command, "PROTOCOL_UNAVAILABLE",
                       "Verify the paired managed engine and Skill, or inspect the retained operation state.", status="UNKNOWN"), 4
