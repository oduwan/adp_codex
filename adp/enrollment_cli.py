"""Versioned, bounded non-secret frontend for guided enrollment."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from .discovery_github import GitHubHTTPTransport
from .enrollment import (
    Blocked, FAILURES, LIMIT, SCHEMA, apply_plan, inspect_project, installer_root, local_checkout,
    prepare, read_enrollment, read_intent, runtime_capability, selected_authority, selected_directory,
)
from .schema import encode, require


def add_commands(commands) -> None:
    enroll = commands.add_parser("enroll", help="Inspect and configure an explicitly selected GitHub project")
    stages = enroll.add_subparsers(dest="enroll_command", required=True)
    for name in ("inspect", "plan", "apply", "status", "doctor", "preview", "reconnect"):
        stage = stages.add_parser(name)
        stage.add_argument("--repo", required=True, type=Path)
        stage.add_argument("--remote", required=True)
        stage.add_argument("--github-id", help="Expected immutable GitHub database ID")
        stage.add_argument("--directory", type=Path, help="Private guided enrollment directory")
        if name in ("inspect", "plan", "apply"):
            stage.add_argument("--token-env", default="GH_TOKEN", help="Read credential environment variable name")
        if name != "inspect":
            stage.add_argument("--operator-trust", type=Path, help="Explicit protected existing operator trust root")
        if name in ("plan", "apply"):
            stage.add_argument("--operator-socket", type=Path, help="Protected local proposal service")
            stage.add_argument("--issue", type=int, help="Select one open issue on this feature checkout")
        if name in ("status", "doctor", "preview", "reconnect"):
            stage.add_argument("--operator-profile", type=Path, help="Guided profile with its retained enrollment record")
        if name == "apply":
            stage.add_argument("--approve", help="Exact approved plan digest")
            stage.add_argument("--authorize-memory-write", action="store_true")


def discovery_token(name: str) -> str:
    require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name), "Invalid credential environment variable name")
    token = os.environ.get(name)
    if token:
        return token
    if name == "GH_TOKEN":
        try:
            # Use only an explicit github.com login. The token never enters an
            # argument, diagnostic, file, provider proposal or prompt.
            raw = subprocess.check_output(["gh", "auth", "token", "--hostname", "github.com"],
                                          stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if 0 < len(raw) <= 4096:
                return raw.decode("ascii").strip()
        except (OSError, subprocess.SubprocessError, UnicodeError):
            pass
    raise Blocked("DISCOVERY_CREDENTIAL_REQUIRED",
                  "Authenticate GitHub CLI for github.com or supply a read credential in the selected environment variable.")


def question(identifier: str, kind: str, argument: str, action: str) -> dict:
    return {"id": identifier, "type": kind, "argument": argument, "action": action}


def missing_questions(args, intent) -> list:
    questions = []
    for identifier, attribute, argument, action in (
        ("enrollment_directory", "directory", "--directory", "Select an owned private directory outside the project."),
        ("operator_trust", "operator_trust", "--operator-trust", "Select the independently provisioned operator trust root."),
    ):
        if getattr(args, attribute) is None:
            questions.append(question(identifier, "absolute_path", argument, action))
    if not intent:
        if args.issue is None:
            questions.append(question("issue", "issue_number", "--issue", "Select one current open issue."))
        if args.operator_socket is None:
            questions.append(question("operator_proposal_service", "absolute_path", "--operator-socket",
                                      "Select the trusted operator proposal service."))
    return questions


def run(args) -> tuple[dict, int]:
    command = args.enroll_command
    report = {"schema_version": SCHEMA, "command": command,
              "mode": "MUTATING" if command == "apply" else "READ_ONLY",
              "status": "UNKNOWN", "facts": None, "questions": [], "plan": None,
              "approval": None, "result": None, "blockers": [], "execution_authority": "UNKNOWN"}
    try:
        _run(args, report)
        encode(report, LIMIT)
    except Blocked as exc:
        report["status"] = exc.status
        report["blockers"].append({"code": exc.reason, "action": str(exc)})
    except FAILURES:
        report["status"] = "BLOCKED"
        report["blockers"].append({"code": "UNSAFE_STALE_OR_UNAVAILABLE",
                                   "action": "Reconcile the exact target, protected paths, retained intent and current authority. Preserve existing state."})
    # Facts plus a plan are bounded as a whole. Never fall back to raw errors.
    try:
        encode(report, LIMIT)
    except FAILURES:
        report.update(status="UNKNOWN", facts=None, plan=None, approval=None, result=None,
                      blockers=[{"code": "PROTOCOL_BOUND", "action": "Inspect a repository within the supported observation bounds."}])
    return report, 0 if report["status"] in ("OBSERVED", "PROPOSED", "ENROLLED", "ALREADY_ENROLLED", "RECONNECTED") else 4


def _run(args, report: dict) -> None:
    command = args.enroll_command
    checkout = local_checkout(args.repo, args.remote)
    directory = selected_directory(args.directory, checkout) if args.directory else None
    if command not in ("inspect", "plan", "apply"):
        if args.operator_trust is None:
            raise Blocked("TRUST_ROOT_REQUIRED", "Select the already provisioned protected operator trust root.")
        require(directory is None or args.operator_profile is None,
                "Choose a guided enrollment directory or its retained guided profile")
        trust = selected_authority(args.operator_trust, checkout)
        profile = selected_authority(args.operator_profile, checkout) if args.operator_profile else None
        result = read_enrollment(directory, profile, trust, checkout, command, GitHubHTTPTransport)
        if args.github_id is not None and result.get("repository_id") not in (None, args.github_id):
            raise Blocked("REPOSITORY_IDENTITY_MISMATCH", "Reconnect using the original immutable repository ID.")
        blocker = result.pop("blocker", None)
        if blocker is not None:
            report["blockers"].append(blocker)
        report.update(status=result["status"], result=result)
        return
    try:
        transport = GitHubHTTPTransport(discovery_token(args.token_env))
    except Blocked:
        raise
    except FAILURES as exc:
        raise Blocked("DISCOVERY_CREDENTIAL_INVALID", "Supply a bounded read credential via the supported authentication input.") from exc
    observation = inspect_project(checkout, transport, args.github_id)
    intent = read_intent(directory) if directory is not None else None
    launcher = installer_root() / "current/bin/adp"
    report["facts"] = {**observation.facts, "runtime": runtime_capability(installer_root()),
                       "installation": {"engine": "AVAILABLE",
                                        "managed_launcher": "OBSERVED" if launcher.is_file() else "UNKNOWN"},
                       "local_enrollment": intent["phase"] if intent else "UNSELECTED" if directory is None else "ABSENT"}
    if command == "inspect":
        report["questions"] = [
            question("enrollment_directory", "absolute_path", "--directory", "Select an owned private enrollment directory."),
            question("operator_trust", "absolute_path", "--operator-trust", "Select the independently provisioned trust root."),
            question("issue", "issue_number", "--issue", "Select one open issue on an existing feature checkout."),
            question("operator_proposal_service", "absolute_path", "--operator-socket", "Select the trusted operator proposal service."),
        ] if not intent else []
        report["status"] = "OBSERVED" if observation.facts["discovery"] == "COMPLETE" else "UNKNOWN"
        report["blockers"] = [{"code": "AUTHORITY_NOT_ESTABLISHED",
                               "action": "Use plan with the trusted service. GitHub observations establish no execution authorization."}]
        return
    report["questions"] = missing_questions(args, intent)
    if report["questions"]:
        raise Blocked("CONFIGURATION_REQUIRED", "Answer the outstanding enrollment questions.")
    if command == "apply" and (not args.authorize_memory_write or not re.fullmatch("[0-9a-f]{64}", args.approve or "")):
        raise Blocked("OPERATOR_APPROVAL_REQUIRED", "Approve the exact plan digest and explicitly authorize memory writes.")
    trust = selected_authority(args.operator_trust, checkout)
    socket = selected_authority(args.operator_socket, checkout) if args.operator_socket else None
    plan = prepare(observation, directory, trust, args.issue, socket)
    report.update(status="PROPOSED", plan=plan.summary, approval=plan.approval)
    if command == "apply":
        if args.approve != plan.approval:
            raise Blocked("APPROVAL_MISMATCH", "Review and approve the exact current enrollment plan.")
        result = apply_plan(plan, approved=args.approve, authorized=args.authorize_memory_write)
        report.update(status=result["status"], result=result)
