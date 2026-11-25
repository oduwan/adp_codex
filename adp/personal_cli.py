"""One explicit personal protocol shared by the managed CLI and Codex Skill.

Arguments are operator choices; no user-authored JSON or provider is loaded.
The default signed-provider paths remain separate and unchanged.
"""
from __future__ import annotations

from pathlib import Path
import re

from .discovery_schema import digest
from .enrollment import Blocked, local_checkout
from .enrollment_cli import discovery_token
from .errors import ADPError
from .personal_enrollment import PersonalChoices, apply_personal, plan_personal, selection
from .git import value
from .personal_github import PersonalGitHubRead
from .personal_runner import PersonalCoordinator
from .personal_storage import PersonalBlocked, approval, assert_public, load_state, read_private
from .project_validation_github import GitHubValidationHTTP
from .schema import require

ACTIONS = ("inspect", "plan", "apply", "status", "doctor", "preview", "reconnect", "run", "resume", "handoff")
PUBLICATION = ("publication-preview", "publish", "publication-status")
ARCHIVAL = ("archive-preview",)
from .personal_product_cli import PRODUCT
from .personal_track_cli import TRACK, WRITES
from .personal_recovery_cli import ACTIONS as RECOVERY, WRITES as RECOVERY_WRITES


def choices(parser):
    parser.add_argument("--personal", action="store_true", help="Explicit operator-managed local-draft mode; no signed provider")
    parser.add_argument("--path", action="append", default=[], help="Original-ticket source path, repeat for each admitted path")
    parser.add_argument("--feature-branch", help="Exact proposed feature branch, interpreted against existing governance")
    parser.add_argument("--feature-workspace", type=Path, help="Approved isolated local feature worktree")
    parser.add_argument("--commit-message", help="Actual selected commit subject, not a new repository rule")
    parser.add_argument("--commit-body", default="")
    parser.add_argument("--check", action="append", default=[], help="Existing project-prescribed native check name")
    parser.add_argument("--accept-native-job-records", action="store_true", help="Explicitly accept native job records as attempts, preserving unknown test counts")
    parser.add_argument("--seconds", type=int, default=1800, help="Original finite personal window, 60..3600 seconds")


def add_commands(commands):
    command = commands.add_parser("personal", help="Opt-in owned personal project setup and one finite local draft")
    stages = command.add_subparsers(dest="enroll_command", required=True)
    stages.add_parser("capabilities")
    for action in ACTIONS:
        parser = stages.add_parser(action)
        parser.add_argument("--repo", type=Path, required=True)
        parser.add_argument("--remote", required=True)
        parser.add_argument("--github-id")
        parser.add_argument("--issue", type=int)
        parser.add_argument("--directory", type=Path)
        parser.add_argument("--token-env", default="GH_TOKEN")
        parser.add_argument("--approve")
        parser.add_argument("--authorize-memory-write", action="store_true")
        parser.add_argument("--reviewed")
        parser.add_argument("--authorize-execution", action="store_true")
        parser.add_argument("--for-operation", choices=("run", "resume", "handoff"))
        parser.add_argument("--check-runtime", action="store_true")
        choices(parser)
    publication_commands(stages)


def publication_commands(stages, *, codex=False):
    from .personal_recovery_cli import commands as recovery_commands
    recovery_commands(stages, codex=codex)
    for action in ARCHIVAL:
        parser = stages.add_parser(action, help="Read-only expired NOTRUN archival proposal; no mutation authority")
        parser.add_argument("--repo", type=Path, required=True)
        parser.add_argument("--remote", required=True)
        parser.add_argument("--directory", type=Path, required=True)
        parser.add_argument("--github-id")
        parser.add_argument("--issue", type=int)
        parser.add_argument("--request", required=True)
        parser.add_argument("--checkpoint")
        parser.add_argument("--expected-proposal")
        if codex:
            parser.add_argument("--personal", action="store_true", required=True)
    from .personal_track_cli import commands as track_commands
    track_commands(stages, codex=codex)
    from .personal_product_cli import commands as product_commands
    product_commands(stages, codex=codex)
    for action in PUBLICATION:
        parser = stages.add_parser(action, help="Separately approved personal GitHub feature publication")
        parser.add_argument("--repo", type=Path, required=True)
        parser.add_argument("--remote", required=True)
        parser.add_argument("--directory", type=Path, required=True)
        parser.add_argument("--github-id")
        parser.add_argument("--issue", type=int)
        if codex:
            parser.add_argument("--personal", action="store_true", required=True)
        if action == "publish":
            parser.add_argument("--reviewed", required=True)
            parser.add_argument("--authorize-publication", action="store_true")
            parser.add_argument("--assume-administrative-quiescence", action="store_true")
            parser.add_argument("--confirm-project-publication-rules", action="store_true")
            parser.add_argument("--accept-plan-unavailable", action="store_true", help="Separately accept the exact proposal's private personal plan limitation; waive no project requirement")


def retained(args, *, resolve=True):
    checkout = local_checkout(args.repo, args.remote)
    directory = args.directory
    if directory is None:
        require(args.github_id is not None and getattr(args, "issue", None) is not None,
                "Select --directory, or the original --github-id and --issue for reconnect")
        # Opaque issue identity comes only from the retained marker's enrollment,
        # never from a guessed issue-number-to-node-ID conversion.
        common = Path(value(args.repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        candidates = []
        if (common / "adp-personal").exists():
            paths = list((common / "adp-personal").glob("*.json"))
            require(len(paths) <= 32, "Personal marker inventory exceeds bounds")
            for path in paths:
                pointer = read_private(path)
                personal = load_state(Path(pointer["directory"]))
                if personal.repository_id == args.github_id and personal.plan["issue"] == args.issue:
                    candidates.append(personal.directory)
        require(len(candidates) == 1, "Select the original private enrollment directory")
        directory = candidates[0]
    personal = load_state(directory)
    p = personal.plan
    require(args.github_id in (None, personal.repository_id) and getattr(args, "issue", None) in (None, p["issue"])
            and checkout["repository"] == p["repository"]["name"] and checkout["remote"] == p["checkout"]["remote"]
            and str(args.repo.absolute()) in (p["checkout"]["path"], p["feature"]["workspace"]),
            "Reconnect only to the exact personal repository, issue and selected workspace")
    if resolve and args.enroll_command not in ARCHIVAL + RECOVERY:
        from .personal_episode import effective
        personal = effective(personal)
    return personal


def run(args, *, transport=None, ci_transport=None, runtime=None, clock=None, publication_transport=None):
    from .personal_history_track import READ_TRANSPORT, cli_port
    port = None
    # Existing ordinary commands already admit native project reads. Resolve
    # their historical read route before effective() can need it. Archival
    # observation must never initialize credentials or a network adapter.
    if args.enroll_command not in ARCHIVAL + RECOVERY + ("inspect", "plan", "apply", "capabilities"):
        try:
            port = cli_port(retained(args, resolve=False), publication_transport)
        except (ADPError, OSError, KeyError, TypeError, ValueError, AttributeError):
            pass  # The ordinary closed subject validation below reports it.
    binding = READ_TRANSPORT.set(port) if port is not None else None
    try:
        return _run(args, transport=transport, ci_transport=ci_transport, runtime=runtime, clock=clock,
            publication_transport=publication_transport)
    finally:
        if binding is not None:
            READ_TRANSPORT.reset(binding)


def _run(args, *, transport=None, ci_transport=None, runtime=None, clock=None, publication_transport=None):
    action = args.enroll_command
    report = {"schema_version": 1, "backend": "PERSONAL", "command": action,
        "mode": "MUTATING" if action in ("apply", "run", "resume", "handoff", "publish", "pr-create", "check-ci", "product-resume", "merge") + WRITES + RECOVERY_WRITES else "READ_ONLY",
        "status": "UNKNOWN", "questions": [], "plan": None, "approval": None, "result": None, "blockers": [],
        "runtime_qualification": "NOTRUN"}
    try:
        if action == "capabilities":
            report.update(status="AVAILABLE", result={"actions": list(ACTIONS + PUBLICATION + PRODUCT + TRACK + ARCHIVAL + RECOVERY), "scope": "LOCAL_DRAFT",
                "providers": "NOT_REQUIRED", "external_operations": "NOT_DELEGATED",
                "publication": {"status": "AVAILABLE_UNDER_SEPARATE_EXACT_APPROVAL", "credential_envelope": "OPERATOR_ADMINISTRATIVE_QUIESCENCE"}})
            assert_public(report)
            return report, 0
        require(action in ACTIONS + PUBLICATION + PRODUCT + TRACK + ARCHIVAL + RECOVERY, "Unsupported personal command")
        require(not any(getattr(args, name, None) for name in ("operator_trust", "operator_socket", "operator_profile")),
                "Choose personal mode or the unchanged signed-provider mode; never convert an enrollment")
        require(getattr(args, "rounds", 1) == 1 and getattr(args, "maximum_parallel", 1) == 1,
                "Personal mode admits exactly one issue, one task iteration and one concurrent worker")
        if action in ARCHIVAL:
            from .personal_archive import proposal
            c = PersonalCoordinator(retained(args), None, None, runtime=runtime, clock=clock)
            view = proposal(c, args.request, checkpoint=args.checkpoint, expected=args.expected_proposal)
            report.update(status=view["status"], result=view)
            assert_public(report)
            return report, 0
        if action in RECOVERY:
            from .personal_recovery_cli import dispatch
            if transport is None and action not in ("archive-observe", "archive-status", "archive-revoke", "continuation-status"):
                token = discovery_token("GH_TOKEN")
                transport, ci_transport = PersonalGitHubRead(token), GitHubValidationHTTP(token)
            result = dispatch(args, retained(args), transport=transport, ci_transport=ci_transport, runtime=runtime, clock=clock)
            report.update(result)
            assert_public(report)
            return report, 4 if report["status"].startswith("BLOCKED") else 0
        if action in TRACK:
            from .personal_track_cli import dispatch
            if transport is None and action in ("track-preview", "track-enroll", "track-status"):
                transport = PersonalGitHubRead(discovery_token(getattr(args, "token_env", "GH_TOKEN")))
            result = dispatch(args, retained(args), transport=transport, ci_transport=ci_transport,
                publication_transport=publication_transport, runtime=runtime, clock=clock)
            report.update(result)
            assert_public(report)
            return report, 0 if report["status"] in ("TRACK_PROPOSED", "TRACK_ENROLLED", "COMPLETE", "ACTIVE_ORIGINAL", "NEXT_SCOPE_REQUIRED",
                "COMPLETION_PROPOSED", "ACCEPTED_COMPLETION", "REPORT_PROPOSED", "REPORTED", "NOT_DELEGATED",
                "NEXT_PROPOSED", "NEXT_PROPOSED_RETAINED", "NEXT_ALREADY_ENROLLED", "NEXT_ENROLLED_SCOPE_REVIEW_REQUIRED") else 4
        if action in PRODUCT:
            from .personal_product_cli import dispatch
            result = dispatch(args, retained(args), runtime=runtime, clock=clock, transport=publication_transport)
            report.update(result)
            assert_public(report)
            return report, 0 if report["status"] in ("PR_PROPOSED", "PR_PRESENT", "CI_PROPOSED", "PASS", "NOT_REQUIRED", "REVIEW_PROPOSED", "CORRECT_PROPOSED", "PRODUCT_REVIEWED", "CORRECTED_REQUIRES_NEW_PUBLICATION", "MERGE_PROPOSED", "MERGED_DELEGATED_VERIFIED", "MERGED_EXTERNALLY_VERIFIED", "PR_DRAFT", "WAITING_HUMAN_APPROVAL") else 4
        if action in PUBLICATION:
            from .personal_publication import PersonalPublication
            personal = retained(args)
            coordinator = PersonalCoordinator(personal, None, None, runtime=runtime, clock=clock)
            publication = PersonalPublication(coordinator, transport=publication_transport)
            if (personal.state / "product.json").exists():
                from .personal_product import PersonalProduct
                from .personal_product_review import ProductCoordinator
                coordinator = ProductCoordinator(personal, None, None, runtime=runtime, clock=clock)
                product = PersonalProduct(coordinator, transport=publication_transport)
                publication = product.publication_backend(transport=publication_transport)
            if action == "publication-preview":
                proposed = publication.preview()
                report.update(status=proposed["status"], result=proposed["result"], approval=proposed["approval"])
            elif action == "publication-status":
                result = publication.status()
                report.update(status=result["status"], result=result)
            else:
                result = publication.publish(reviewed=args.reviewed, authorized=args.authorize_publication,
                    assume_quiescence=args.assume_administrative_quiescence,
                    confirm_project_rules=args.confirm_project_publication_rules,
                    accept_plan_unavailable=args.accept_plan_unavailable)
                report.update(status=result["status"], result=result)
            assert_public(report)
            return report, 0 if report["status"] in ("PUBLICATION_PROPOSED", "PUBLISHED_UNACCEPTED", "PUBLICATION_PRESENT", "NOT_DELEGATED") else 4
        if transport is None and (action in ("inspect", "plan", "apply", "preview", "run", "resume", "reconnect", "doctor")
                                  or (getattr(args, "for_operation", None) in ("run", "resume"))):
            token = discovery_token(getattr(args, "token_env", "GH_TOKEN"))
            transport, ci_transport = PersonalGitHubRead(token), GitHubValidationHTTP(token)
        if action in ("inspect", "plan", "apply"):
            observation, owner = selection(args.repo, args.remote, args.github_id, transport)
            if action == "inspect":
                report.update(status="OBSERVED", result={"facts": observation.facts, "owner": owner,
                    "execution_authority": "NOT_DELEGATED", "personal_setup": "AVAILABLE_WITH_EXACT_OPERATOR_APPROVAL"})
            else:
                if args.issue is None:
                    report["questions"].append({"id": "issue", "argument": "--issue", "action": "Choose one observed open original issue."})
                if not args.path:
                    report["questions"].append({"id": "paths", "argument": "--path", "action": "Select only the source paths needed for the original issue."})
                if report["questions"]:
                    report["status"] = "INPUT_REQUIRED"
                else:
                    directory = args.directory or Path.home() / ".local/state/adp-personal" / digest({
                        "repository": observation.repository["repository_id"], "issue": args.issue,
                        "common": str(args.repo.absolute())})
                    selected = PersonalChoices(args.issue, directory, tuple(args.path), branch=args.feature_branch,
                        workspace=args.feature_workspace, commit_message=args.commit_message, commit_body=args.commit_body,
                        checks=tuple(args.check), accept_native_job_records=args.accept_native_job_records, seconds=args.seconds)
                    p, original, docs = plan_personal(observation, owner, selected,
                        approved=getattr(args, "approve", None), ci_transport=ci_transport, clock=clock)
                    report.update(status="PROPOSED", plan=p, approval=approval(p))
                    if action == "apply":
                        personal = apply_personal(p, original, docs, approved=args.approve,
                            authorized=args.authorize_memory_write, transport=transport, ci_transport=ci_transport, clock=clock)
                        report.update(status="ENROLLED", result={"directory": str(personal.directory),
                            "feature_preparation": "DEFERRED_UNTIL_SEPARATE_RUN_AND_INDEPENDENT_POLICY_REVIEW", "execution": "NOT_STARTED"})
        else:
            personal = retained(args)
            c = PersonalCoordinator(personal, transport, ci_transport, runtime=runtime, clock=clock)
            if action in ("run", "resume", "handoff"):
                report["result"] = c.run(reviewed=args.reviewed, authorized=args.authorize_execution, operation=action)
                report["status"] = report["result"]["status"]
            elif action == "preview" or getattr(args, "for_operation", None):
                view, token = c.invocation(getattr(args, "for_operation", None) or "run")
                report.update(status="PREVIEW", result=view, approval=token)
            else:
                if action in ("reconnect", "doctor"):
                    c.fresh()
                report.update(status="RECONNECTED" if action == "reconnect" else "ENROLLED", result=c.status())
                if action == "doctor" and getattr(args, "check_runtime", False):
                    caps = c.runtime.capabilities()
                    version = caps.version if re.fullmatch(r"(?:codex-cli )?[0-9]+(?:\.[0-9]+)+(?:[-+][0-9A-Za-z.-]+)?", caps.version) else "UNKNOWN"
                    report["result"]["runtime"] = {"supported": caps.independent_contexts, "version": version,
                        "qualification": "NOTRUN"}
        assert_public(report)
    except (PersonalBlocked, Blocked) as exc:
        report.update(status=exc.status, blockers=[{"code": getattr(exc, "reason", getattr(exc, "code", "BLOCKED")), "action": str(exc)}])
    except (ADPError, OSError, ValueError, TypeError, KeyError):
        # Never disclose raw transport, policy, filesystem or worker exceptions.
        report.update(status="BLOCKED", blockers=[{"code": "PERSONAL_STATE_OR_AUTHORITY_UNVERIFIED",
            "action": "Reconcile the exact original plan, source, private state, permissions and retained receipts; do not reset or retry unknown effects."}])
    try:
        assert_public(report)
    except (ADPError, ValueError, TypeError):
        report.update(status="BLOCKED", plan=None, approval=None, result=None,
            blockers=[{"code": "PRIVATE_OR_OVERSIZED_OUTPUT", "action": "Inspect bounded private evidence locally; do not publish raw data."}])
    return report, 0 if report["status"] in ("OBSERVED", "PROPOSED", "ENROLLED", "RECONNECTED", "PREVIEW", "LOCAL_DRAFT_CODE_REVIEWED", "HANDED_OFF") else 4
