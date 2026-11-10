"""Explicit v3 wrapper for M1 checkpoints; guard and task schemas stay closed."""
from __future__ import annotations

from .discovery_schema import typed
from .execution_types import Role, ValidationResult, WorkerResult
from .guard_types import Permit, data
from .guard_types import Outcome
from .schema import JOB, KEY, encode, fields, integer, key, require, string
from .git import SHA
from .policy_types import Operation

MAX_EXECUTION_TASKS = 8
MAX_ACTIONS = 32


def fingerprint(value):
    require(type(value) is str and KEY.fullmatch(value), "Invalid execution fingerprint")


def sha(value):
    require(type(value) is str and SHA.fullmatch(value), "Invalid exact execution SHA")


def validation_result(raw):
    result = typed(ValidationResult, raw)
    integer(result.denominator, 1)
    integer(result.passed)
    integer(result.quarantined)
    sha(result.revision)
    require(len(result.counts) == len(Outcome) and {c.outcome for c in result.counts} == set(Outcome),
            "Complete unique validation accounting is required")
    for count in result.counts:
        integer(count.count)
    require(sum(c.count for c in result.counts) == result.denominator and result.quarantined <= result.denominator
            and result.passed == next(c.count for c in result.counts if c.outcome == Outcome.PASS),
            "Original validation inventory/accounting changed")
    require(result.outcome != Outcome.PASS or result.passed == result.denominator and result.quarantined == 0,
            "Partial validation cannot pass")
    return result


def job_schema(job):
    fields(job, "request_id role generation revision source_ref host context status permit result receipt checks validation_stop seconds deadline samples payload_bytes elapsed used_samples used_bytes started request_digest outside_digest admin_digest result_digest")
    fingerprint(job["request_id"])
    require(job["role"] in set(Role), "Invalid worker role")
    integer(job["generation"], 1)
    sha(job["revision"])
    string(job["source_ref"])
    string(job["host"], 128)
    if job["context"] is not None:
        string(job["context"], 128)
    require(job["status"] in {"PREPARED", "RUNNING", "OBSERVED", "DELIVERED", "COMPLETE", "CANCELLED", "UNKNOWN"}, "Invalid worker phase")
    if job["permit"] is not None:
        typed(Permit, job["permit"])
    if job["result"] is not None:
        worker_result(typed(WorkerResult, job["result"]))
    require(type(job["checks"]) is list and len(job["checks"]) <= 32, "Invalid durable validation receipts")
    require(job["validation_stop"] in ("NOT_STARTED", "RUNNING", "CONFIRMED", "UNKNOWN"), "Invalid validation liveness state")
    for check in job["checks"]:
        validation_result(check)
    string(job["receipt"], 512)
    require(type(job["seconds"]) is int and 1 <= job["seconds"] <= 300, "Invalid worker containment")
    integer(job["started"])
    for metric in ("samples", "payload_bytes", "elapsed", "used_samples", "used_bytes"):
        integer(job[metric])
    require(0 < job["samples"] <= 1000 and 0 < job["payload_bytes"] <= 1048576, "Invalid runtime IO containment")
    if job["deadline"] is not None:
        integer(job["deadline"], 1)
    fingerprint(job["request_digest"])
    fingerprint(job["outside_digest"])
    fingerprint(job["admin_digest"])
    if job["result_digest"] is not None:
        fingerprint(job["result_digest"])


def worker_result(result: WorkerResult):
    typed(WorkerResult, data(result))
    require(type(result.approved) is bool and len(result.criteria) <= 16
            and len(set(result.criteria)) == len(result.criteria), "Invalid worker result")
    for criterion in result.criteria:
        string(criterion, 128)
    require(type(result.summary) is str and len(result.summary) <= 1024, "Worker summary exceeds bounds")
    require(result.approved is False or result.outcome == "PASS", "A non-PASS worker cannot approve")


def execution_schema(value, repository_id):
    version = value.get("schema_version") if type(value) is dict else None
    fields(value, "schema_version repository_id tasks actions publications" + (" product_flows" if version == 2 else ""))
    require(type(version) is int and version in (1, 2)
            and value["repository_id"] == repository_id, "Unsupported execution schema/repository")
    require(type(value["tasks"]) is dict and len(value["tasks"]) <= MAX_EXECUTION_TASKS, "Execution task capacity exhausted")
    all_contexts = []
    for task_key, task in value["tasks"].items():
        fields(task, "task_id identity workspace_key admission issue_digest revision source_ref product_iteration kind stage jobs review")
        require(task_key == key(task["task_id"]), "Execution task identity mismatch")
        fields(task["identity"], "repository_id issue_id forge")
        from .discovery_schema import validate_identity
        from .discovery_types import Identity
        validate_identity(typed(Identity, task["identity"]))
        fingerprint(task["admission"])
        string(task["workspace_key"], 128)
        fingerprint(task["issue_digest"])
        sha(task["revision"])
        string(task["source_ref"])
        integer(task["product_iteration"], 1)
        require(task["kind"] in {"PRODUCT", "INTERNAL"}, "Unknown iteration purpose")
        require(task["stage"] in {"DEVELOP", "REVIEW", "PUBLISH", "COMPLETE", "BLOCKED", "CANCELLED"}, "Invalid Conductor phase")
        require(type(task["jobs"]) is dict and len(task["jobs"]) <= 8, "Worker evidence capacity exhausted")
        contexts = []
        for job_id, job in task["jobs"].items():
            require(type(job_id) is str and JOB.fullmatch(job_id), "Invalid M1 assignment ID")
            job_schema(job)
            if job["context"] is not None:
                contexts.append(job["context"])
        require(len(contexts) == len(set(contexts)), "Worker contexts must be independent")
        all_contexts.extend(contexts)
        if task["review"] is not None:
            fields(task["review"], "revision context reviewer receipt criteria checks")
            sha(task["review"]["revision"])
            string(task["review"]["context"], 128)
            string(task["review"]["reviewer"], 128)
            string(task["review"]["receipt"], 512)
            require(type(task["review"]["criteria"]) is list and len(task["review"]["criteria"]) <= 16, "Invalid reviewed criteria")
            require(len(set(task["review"]["criteria"])) == len(task["review"]["criteria"]), "Duplicate reviewed criteria")
            for criterion in task["review"]["criteria"]:
                string(criterion, 128)
            require(type(task["review"]["checks"]) is list and len(task["review"]["checks"]) <= 32, "Invalid reviewed checks")
            for check in task["review"]["checks"]:
                measured = validation_result(check)
                require(measured.revision == task["review"]["revision"] and measured.outcome == "PASS"
                        and measured.denominator > 0 and measured.passed == measured.denominator
                        and measured.quarantined == 0 and sum(c.count for c in measured.counts) == measured.denominator
                        and all(c.count >= 0 and (c.outcome == "PASS" or c.count == 0) for c in measured.counts),
                        "Unqualified exact-source review check")
            require(any(j["role"] == Role.REVIEWER and j["status"] == "COMPLETE" and j["result"] is not None
                        and j["result"]["approved"] and j["context"] == task["review"]["context"]
                        and "worker:" + j["request_id"] == task["review"]["reviewer"]
                        and j["receipt"] == task["review"]["receipt"] and j["revision"] == task["review"]["revision"]
                        and (j["validation_stop"] == "CONFIRMED" or version == 2 and j["validation_stop"] == "NOT_STARTED"
                             and not j["checks"] and value["product_flows"].get(task_key, {}).get("review_job") == aid
                             and value["product_flows"][task_key]["gates"]
                             and all(typed(__import__("adp.project_validation_types", fromlist=["EvidenceGate"]).EvidenceGate, g).qualified
                                     for g in value["product_flows"][task_key]["gates"]))
                        and j["checks"] == task["review"]["checks"]
                        for aid, j in task["jobs"].items()), "Review must reference an actual completed independent Reviewer job")
    require(len(all_contexts) == len(set(all_contexts)), "Context reuse across tasks/roles is forbidden")
    require(type(value["actions"]) is dict and len(value["actions"]) <= MAX_ACTIONS, "External action capacity exhausted")
    for action_id, action in value["actions"].items():
        fingerprint(action_id)
        fields(action, "task_key generation operation revision source_ref target expected_target payload status observation plan_digest")
        fingerprint(action["task_key"])
        require(action["task_key"] in value["tasks"], "Action references an unknown admitted task")
        integer(action["generation"], 1)
        sha(action["revision"])
        string(action["source_ref"])
        require(action["operation"] in (Operation.STAGE, Operation.COMMIT, Operation.BRANCH, Operation.PUSH, Operation.PR, Operation.REPORT)
                or version == 2 and action["operation"] == Operation.MERGE,
                "Unsupported external execution operation")
        string(action["target"], 512)
        if action["expected_target"] is not None:
            sha(action["expected_target"])
        require(type(action["payload"]) is dict, "Invalid action payload")
        require(action["status"] in {"PREPARED", "SUBMITTED", "OBSERVED", "UNKNOWN"}, "Invalid external action state")
        fingerprint(action["plan_digest"])
        if action["observation"] is not None:
            from .execution_types import ExternalObservation
            typed(ExternalObservation, action["observation"])
        encode(action, 8192)
    require(type(value["publications"]) is dict and len(value["publications"]) <= 8, "Publication capacity exhausted")
    for pub_id, publication in value["publications"].items():
        fingerprint(pub_id)
        fields(publication, "action body_digest reference")
        fingerprint(publication["action"])
        require(publication["action"] in value["actions"] and value["actions"][publication["action"]]["operation"] == Operation.REPORT
                and value["actions"][publication["action"]]["status"] == "OBSERVED", "Publication must reference an observed product report")
        fingerprint(publication["body_digest"])
        string(publication["reference"], 512)
    if version == 2:
        require(type(value["product_flows"]) is dict and len(value["product_flows"]) <= MAX_EXECUTION_TASKS,
                "Product-flow capacity exhausted")
        for task_key, flow in value["product_flows"].items():
            require(task_key in value["tasks"], "Product flow references unknown task")
            fields(flow, "original preparation scope revision phase pull gates review_job delegation merge_result")
            for name in ("original", "preparation"):
                string(flow[name], 128)
            fingerprint(flow["scope"])
            sha(flow["revision"])
            fingerprint(flow["delegation"])
            require(flow["phase"] in {"PREPARED", "PENDING_VALIDATION", "REQUIRES_CORRECTION", "WAITING_HUMAN_APPROVAL",
                "VALIDATED", "MERGED", "COMPLETE", "UNKNOWN", "UNSUPPORTED"}, "Invalid product-flow stage")
            if flow["pull"] is not None:
                fields(flow["pull"], "id number repository_id url")
                integer(flow["pull"]["number"], 1)
                for name in ("id", "repository_id", "url"):
                    string(flow["pull"][name], 512)
            require(type(flow["gates"]) is list and len(flow["gates"]) <= 2, "Invalid project gates")
            from .project_validation_types import EvidenceGate
            phases = []
            for raw in flow["gates"]:
                gate = typed(EvidenceGate, raw)
                require(gate.request.revision == flow["revision"] and gate.request.task_id == value["tasks"][task_key]["task_id"]
                        and gate.request.repository_id == repository_id, "Foreign project gate")
                phases.append(gate.request.phase)
            require(len(set(phases)) == len(phases), "Duplicate project phases")
            if flow["review_job"] is not None:
                job = value["tasks"][task_key]["jobs"].get(flow["review_job"])
                require(job is not None and job["role"] == Role.REVIEWER and job["status"] == "COMPLETE"
                        and job["revision"] == flow["revision"] and job["result"] is not None
                        and job["result"]["approved"] and job["context"] is not None,
                        "Product review must reference an actual completed independent Reviewer")
            if flow["merge_result"] is not None:
                sha(flow["merge_result"])
    encode(value)
