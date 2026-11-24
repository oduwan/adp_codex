"""Finite operator choices for native progression; no handwritten controllers."""
from pathlib import Path

from .discovery_schema import digest, typed
from .discovery_types import Identity
from .personal_enrollment import PersonalChoices
from .personal_product import PersonalProduct
from .personal_product_review import ProductCoordinator
from .personal_report import PersonalReport
from .personal_runner import PersonalCoordinator
from .personal_track import PersonalTrack
from .schema import require

TRACK = ("track-preview", "track-enroll", "track-status", "completion-preview", "complete",
    "report-preview", "report", "report-status", "next-preview", "next")
WRITES = ("track-enroll", "complete", "report", "next")


def commands(stages, *, codex=False):
    for action in TRACK:
        p = stages.add_parser(action, help="One explicit finite personal native-track operation")
        p.add_argument("--repo", type=Path, required=True)
        p.add_argument("--remote", required=True)
        p.add_argument("--directory", type=Path, required=True)
        p.add_argument("--github-id")
        p.add_argument("--issue", type=int)
        if codex:
            p.add_argument("--personal", action="store_true", required=True)
        if action in ("track-preview", "track-enroll"):
            p.add_argument("--track-issue", type=int, action="append", required=True)
        if action in WRITES:
            p.add_argument("--reviewed", required=True)
            p.add_argument("--authorize-memory-write", action="store_true")
        if action == "complete":
            p.add_argument("--confirm-project-acceptance", action="store_true")
        if action == "report":
            p.add_argument("--authorize-report", action="store_true")
            p.add_argument("--assume-administrative-quiescence", action="store_true")
            p.add_argument("--confirm-project-rules", action="store_true")
        if action in ("next-preview", "next"):
            p.add_argument("--next-issue", type=int, required=True)
            p.add_argument("--path", action="append", required=True)
            p.add_argument("--feature-branch")
            p.add_argument("--feature-workspace", type=Path)
            p.add_argument("--commit-message")
            p.add_argument("--commit-body", default="")
            p.add_argument("--check", action="append", default=[])
            p.add_argument("--accept-native-job-records", action="store_true")
            p.add_argument("--seconds", type=int, default=1800)
            if action == "next":
                p.add_argument("--setup-approved", required=True)


def dispatch(args, personal, *, transport=None, ci_transport=None, publication_transport=None, runtime=None, clock=None):
    action = args.enroll_command
    if action in ("track-preview", "track-enroll", "track-status"):
        c = PersonalCoordinator(personal, transport, ci_transport, runtime=runtime, clock=clock)
        if action == "track-preview":
            view, approval = PersonalTrack.registration(c, tuple(args.track_issue))
            return {"status": "TRACK_PROPOSED", "approval": approval, "result": {"repository": view["repository"],
                "numbers": view["numbers"], "native_snapshot": digest(view["snapshot"]),
                "effects": "Freeze unchanged originals only; no worker, new window or GitHub mutation."}}
        if action == "track-enroll":
            track = PersonalTrack.register(c, tuple(args.track_issue), reviewed=args.reviewed, authorized=args.authorize_memory_write)
            return {"status": "TRACK_ENROLLED", "result": {"original_issues": sorted(o.issue.number for o in track.originals.values()),
                "execution": "NOT_STARTED", "next_admission": "NOT_AUTHORIZED"}}
        require(c.track is not None, "Select the immutable original track first")
        result = c.track.status(transport=publication_transport)[0]
        return {"status": result["status"], "result": result}
    c = ProductCoordinator(personal, transport, ci_transport, runtime=runtime, clock=clock)
    require(c.track is not None, "Select the immutable original track first")
    f = PersonalReport(c, transport=publication_transport) if action.startswith("report") else PersonalProduct(c, transport=publication_transport)
    if action == "completion-preview":
        return c.track.completion_preview(f)
    if action == "complete":
        result = c.track.complete(f, reviewed=args.reviewed, authorized=args.authorize_memory_write,
            confirm_acceptance=args.confirm_project_acceptance)
        return {"status": "ACCEPTED_COMPLETION", "result": {"identity": result["identity"], "source": result["source"],
            "merge": result["merge"], "actor": "github-user:" + str(result["actor"]), "evidence": digest(result)}}
    if action == "report-preview":
        proposed = f.report_preview(); proposed.pop("binding", None)
        return proposed
    if action == "report":
        result = f.report(reviewed=args.reviewed, authorized=args.authorize_report, authorize_memory=args.authorize_memory_write,
            assume_quiescence=args.assume_administrative_quiescence, confirm_rules=args.confirm_project_rules)
        return {"status": result["status"], "result": result}
    if action == "report-status":
        row = f.report_record()
        if row is None:
            return {"status": "NOT_DELEGATED", "result": {"report": "NOT_DELEGATED"}}
        with f.service.bounded():
            observed, _ = f.observed_report(row)
        return {"status": "REPORTED" if row["after"] is not None else "REPORT_OBSERVED_UNACCOUNTED",
            "result": {"reference": observed.reference, "revision": observed.revision, "retry": "NOT_AUTHORIZED"}}
    require(action in ("next-preview", "next"), "Unsupported track command")
    selected = [i for i, o in c.track.originals.items() if o.issue.number == args.next_issue]
    require(len(selected) == 1, "Next Issue must be in the frozen original inventory")
    directory = c.track.root / "windows" / digest(selected[0])
    choices = PersonalChoices(args.next_issue, directory, tuple(args.path), branch=args.feature_branch,
        workspace=args.feature_workspace, commit_message=args.commit_message, commit_body=args.commit_body,
        checks=tuple(args.check), accept_native_job_records=args.accept_native_job_records, seconds=args.seconds)
    c.ci_transport = ci_transport or f.read
    if action == "next-preview":
        proposed = c.track.next_preview(f, choices)
        view = proposed["result"]
        proposed["result"] = {"plan": view["plan"], "original": digest(view["original"]),
            "current_native_snapshot": digest(view["snapshot"]), "accepted_dependencies": view["completions"],
            "effects": ("No new writes or authority; reconnect to the original next directory/window."
                if proposed["status"] == "NEXT_ALREADY_ENROLLED" else
                "Release the completed old owner, set up this distinct new scope/window. No worker or GitHub mutation."),
            "source_sync": "Exact current native base must already be local; ADP does not fetch."}
        return proposed
    result = c.track.next(f, choices, reviewed=args.reviewed, setup_approval=args.setup_approved,
        authorized=args.authorize_memory_write)
    return {"status": result["status"], "result": result}
