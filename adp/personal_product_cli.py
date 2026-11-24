"""Operator operands for the existing personal single-issue product flow."""
from .personal_product import PersonalProduct
from .personal_product_review import ProductCoordinator

PRODUCT = ("pr-preview", "pr-create", "ci-preview", "check-ci", "product-preview", "product-resume", "merge-preview", "merge", "product-status")


def commands(stages, *, codex=False):
    from pathlib import Path
    for action in PRODUCT:
        p = stages.add_parser(action, help="One separately approved personal PR/check/review/merge operation")
        p.add_argument("--repo", type=Path, required=True)
        p.add_argument("--remote", required=True)
        p.add_argument("--directory", type=Path, required=True)
        p.add_argument("--github-id")
        p.add_argument("--issue", type=int)
        if codex:
            p.add_argument("--personal", action="store_true", required=True)
        if action in ("pr-preview", "pr-create"):
            p.add_argument("--title", required=True)
            p.add_argument("--body", required=True, help="Exact product PR text, without closing directives")
        if action in ("pr-create", "merge"):
            p.add_argument("--authorize-pr" if action == "pr-create" else "--authorize-merge", action="store_true")
            p.add_argument("--authorize-memory-write", action="store_true", help="Explicit accepted product-flow migration/intent writes")
            p.add_argument("--assume-administrative-quiescence", action="store_true")
            p.add_argument("--confirm-project-rules", action="store_true")
            p.add_argument("--accept-plan-unavailable", action="store_true", help="Separately accept the exact private personal plan limitation in this PR/merge proposal")
        if action in ("ci-preview", "check-ci"):
            p.add_argument("--accept-native-job-records", action="store_true")
            p.add_argument("--confirm-no-required-checks", action="store_true", help="Explicit current governance interpretation; never waives a requirement")
        if action in ("product-preview", "product-resume"):
            p.add_argument("--for-operation", choices=("review", "correct"), required=True)
        if action in ("check-ci", "product-resume"):
            p.add_argument("--authorize-execution", action="store_true")
        if action in ("merge-preview", "merge", "product-status"):
            p.add_argument("--merge-method", choices=("merge", "squash"), default="merge")
        if action in ("merge-preview", "merge"):
            p.add_argument("--delegate-merge", action="store_true", help="Separate proposed delegation; default is manual")
        if action == "merge":
            p.add_argument("--accept-head-atomic-base-observed", action="store_true")
        if action in ("pr-create", "check-ci", "product-resume", "merge"):
            p.add_argument("--reviewed", required=True)


def dispatch(args, personal, *, runtime=None, clock=None, transport=None):
    c = ProductCoordinator(personal, None, None, runtime=runtime, clock=clock)
    f = PersonalProduct(c, transport=transport)
    action = args.enroll_command
    if action in ("pr-preview", "merge-preview"):
        proposed = f.proposed("PR" if action == "pr-preview" else "MERGE", title=getattr(args, "title", None),
            body=getattr(args, "body", None), method=getattr(args, "merge_method", None), delegate=getattr(args, "delegate_merge", False))
        proposed.pop("binding", None)
        return proposed
    if action in ("pr-create", "merge"):
        result = f.intent("PR" if action == "pr-create" else "MERGE", reviewed=args.reviewed,
            authorized=args.authorize_pr if action == "pr-create" else args.authorize_merge,
            authorize_memory=args.authorize_memory_write, assume_quiescence=args.assume_administrative_quiescence,
            confirm_rules=args.confirm_project_rules, title=getattr(args, "title", None), body=getattr(args, "body", None),
            method=getattr(args, "merge_method", None), delegate=getattr(args, "delegate_merge", False),
            accept_envelope=getattr(args, "accept_head_atomic_base_observed", False),
            accept_plan_unavailable=getattr(args, "accept_plan_unavailable", False))
        return {"status": result["status"], "result": result}
    if action == "product-status":
        result = f.status(manual_method=args.merge_method)
        return {"status": result["status"], "result": result}
    operation = "CI" if action in ("ci-preview", "check-ci") else args.for_operation.upper()
    options = {"accept_native": getattr(args, "accept_native_job_records", False),
               "confirm_no_checks": getattr(args, "confirm_no_required_checks", False)}
    if action in ("ci-preview", "product-preview"):
        proposed = f.execution_preview(operation, **options)
        proposed.pop("binding", None)
        return proposed
    result = f.execute(operation, reviewed=args.reviewed, authorized=args.authorize_execution, **options)
    return {"status": result["status"], "result": result}
