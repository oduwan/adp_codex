"""Fixed operator verbs: observation, two archival grants, one episode, adoption."""
from pathlib import Path
import os
import sys

from .accounting_policy import entry
from .discovery_schema import digest
from .personal_recovery import Recovery
from .personal_storage import PersonalBlocked
from .schema import require

ACTIONS = ("archive-observe", "archive-guard-preview", "archive-guard", "archive-result-preview", "archive-result",
           "archive-status", "archive-reconcile-preview", "archive-reconcile", "archive-revoke", "continuation-preview",
           "continuation", "continuation-status", "adoption-preview", "adoption")
WRITES = ("archive-guard", "archive-result", "archive-reconcile", "archive-revoke", "continuation", "adoption")


def commands(stages, *, codex=False):
    for action in ACTIONS:
        p = stages.add_parser(action, help="Explicit finite accounting-expiry recovery; no automatic execution")
        p.add_argument("--repo", type=Path, required=True)
        p.add_argument("--remote", required=True)
        p.add_argument("--directory", type=Path, required=True)
        p.add_argument("--github-id")
        p.add_argument("--issue", type=int)
        if codex:
            p.add_argument("--personal", action="store_true", required=True)
        if action in ("archive-observe", "archive-guard-preview", "archive-guard"):
            p.add_argument("--request", required=True)
        if action in ("archive-guard-preview", "archive-guard"):
            p.add_argument("--feature-branch", required=True)
            p.add_argument("--feature-workspace", type=Path, required=True)
            p.add_argument("--path", action="append", required=True)
            p.add_argument("--check", action="append", required=True)
            p.add_argument("--commit-message", required=True)
            p.add_argument("--commit-body", default="")
            p.add_argument("--seconds", type=int, default=1800)
            p.add_argument("--developers", type=int, default=0)
            p.add_argument("--candidate-reviewers", type=int, default=1)
            p.add_argument("--code-reviewers", type=int, default=2)
            p.add_argument("--maximum-check-observations", type=int, default=3)
            p.add_argument("--worker-seconds", type=int, default=300)
        if action in ("archive-reconcile-preview", "archive-reconcile"):
            p.add_argument("--stage", choices=("guard", "result", "episode"), required=True)
        if action in WRITES:
            p.add_argument("--reviewed", required=True)
            p.add_argument("--authorize-memory-write", action="store_true")
        if action in ("archive-guard", "archive-result"):
            p.add_argument("--acknowledge-overdue-accounting", action="store_true")
        if action == "adoption":
            p.add_argument("--authorize-candidate-copy", action="store_true")


def observe(c, request):
    """Same-host, read-only native route; never calls capabilities/dispatch."""
    try:
        if not (os.name == "posix" and sys.platform.startswith("linux") and Path("/proc/self/ns/pid").is_symlink()):
            raise PersonalBlocked("BLOCKED_RUNTIME_HOST_CONTEXT", "The original trusted Linux UID/machine/PID namespace is required; the native route is unavailable here.")
        row = c.worker(request)
        if row["host"] != c.runtime.host:
            raise PersonalBlocked("BLOCKED_RUNTIME_HOST_CONTEXT", "Use an explicitly approved native host-execution tool in the original trusted UID/machine/PID namespace; do not change identities or copy receipts.")
        from .personal_archive import proposal
        from .personal_storage import read_private
        from .personal_history_git import storage_context
        storage_context(c.memory)
        master = read_private(c.personal.state / "accounting-recovery" / "intent.json", optional=True)
        if master is None:
            view = proposal(c, request)
            stage, reference = view["stage"], view["reference"]
        else:
            require(master["request"] == request, "Wrong original request")
            if entry(c.memory.inspect(recovery=True)["state"]) is not None:
                from .personal_history import archived
                m, _, _ = archived(c.personal, memory=c.memory, runtime=c.runtime)
                stage, reference = "ARCHIVED_WITH_EXPLICIT_SUCCESSOR", "accounting-recovery:" + digest(m)
            else:
                view = Recovery(c).status()
                stage, reference = view["status"], view["binding"]
        return {"status": "ARCHIVAL_OBSERVATION_VERIFIED", "result": {"stage": stage, "reference": reference,
            "runtime_context": "ORIGINAL_MATCH", "timeliness": "UNKNOWN", "worker_outcome": "NOTRUN",
            "product_acceptance": "NOT_ACCEPTED", "effects": "NONE", "apply_authority": "NOT_DELEGATED"}}
    except PermissionError as exc:
        raise PersonalBlocked("BLOCKED_ARCHIVAL_OBSERVATION_ACCESS", "Original evidence is inaccessible in this execution context; request supported native host observation without changing filesystem protections.") from exc


def dispatch(args, personal, *, transport=None, ci_transport=None, runtime=None, clock=None):
    from .personal_runner import PersonalCoordinator
    from .personal_episode import Continuation
    c = PersonalCoordinator(personal, transport, ci_transport, runtime=runtime, clock=clock)
    action = args.enroll_command
    if action == "archive-observe":
        return observe(c, args.request)
    if action.startswith("adoption"):
        from .personal_adoption import Adoption
        adoption = Adoption(c)
        if action == "adoption-preview":
            return adoption.preview()[0]
        result = adoption.apply(reviewed=args.reviewed,
            authorized=args.authorize_memory_write and args.authorize_candidate_copy)
        return {"status": result["status"], "result": result}
    r = Recovery(c)
    if action in ("continuation-preview", "continuation", "continuation-status"):
        continuation = Continuation(c)
        if action == "continuation-preview":
            return continuation.preview()[0]
        result = continuation.apply(reviewed=args.reviewed, authorized=args.authorize_memory_write) if action == "continuation" else continuation.status()
        return {"status": result["status"], "result": result}
    if action.startswith("archive-reconcile"):
        target = Continuation(c) if args.stage == "episode" else r
        if action == "archive-reconcile-preview":
            return target.reconcile_preview()[0] if args.stage == "episode" else target.reconcile_preview(args.stage)[0]
        result = target.reconcile(reviewed=args.reviewed, authorized=args.authorize_memory_write) if args.stage == "episode" else target.reconcile(
            args.stage, reviewed=args.reviewed, authorized=args.authorize_memory_write)
        return {"status": result["status"], "result": result}
    if action == "archive-revoke":
        result = r.revoke(args.reviewed, authorized=args.authorize_memory_write)
    elif action == "archive-status":
        if entry(c.memory.inspect(recovery=True)["state"]) is not None:
            from .personal_history import archived
            archived(personal, memory=c.memory, runtime=c.runtime)
            result = {"status": "ARCHIVED_WITH_EXPLICIT_SUCCESSOR", "historical_terminal": "PERMANENT_STOP_UNSAFE", "product_acceptance": "NOT_ACCEPTED"}
        else:
            result = r.status()
    else:
        stage = "guard" if action.startswith("archive-guard") else "result"
        choices = None
        if stage == "guard":
            choices = {"branch": args.feature_branch, "workspace": str(args.feature_workspace), "paths": args.path,
                "checks": args.check, "commit_message": args.commit_message, "commit_body": args.commit_body,
                **{n: getattr(args, n) for n in ("seconds", "developers", "candidate_reviewers", "code_reviewers", "maximum_check_observations", "worker_seconds")}}
        if action.endswith("preview"):
            return r.preview(stage, request=getattr(args, "request", None), choices=choices)[0]
        result = r.apply(stage, reviewed=args.reviewed, authorized=args.authorize_memory_write,
            acknowledge=args.acknowledge_overdue_accounting, request=getattr(args, "request", None), choices=choices)
    return {"status": result["status"], "result": result}
