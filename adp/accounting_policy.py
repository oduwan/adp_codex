"""One opt-in accounting-expiry lineage; never resets a terminal requirement.

Only the personal recovery transaction installs this closed policy. Legacy
registry v1 and all ordinary terminal decisions retain their original meaning.
"""
from __future__ import annotations

from copy import deepcopy

from .discovery_schema import digest
from .guard_schema import COUNTERS, requirement_id
from .schema import fields, integer, key, require, string

POLICY = "ACCOUNTING_EXPIRY_CONTINUATION"
REASON = "An interrupted attempt exceeded containment; operator disposition required"
ROLES = ("scope_reviewers", "developers", "candidate_reviewers", "code_reviewers", "forensic_reviewers",
         "maximum_check_observations", "worker_seconds", "maximum_parallel", "maximum_tasks", "maximum_rounds")
CAPS = dict(zip(ROLES, (1, 2, 2, 2, 2, 3, 300, 1, 1, 1)))
PURPOSES = {"original": "scope_reviewers", "develop": "developers", "candidate": "candidate_reviewers",
            "code": "code_reviewers", "product": "code_reviewers"}


def fingerprint(value):
    require(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value), "Invalid policy digest")


def entry(state):
    registry = state["progress_guard"]
    return registry.get("accounting_continuation") if registry["schema_version"] == 2 else None


def child_id(parent, episode):
    fingerprint(episode)
    return parent + ":accounting:" + episode


def validate(registry, repository_id):
    """Closed canonical relation; opaque private hashes are not proof by themselves."""
    item = registry["accounting_continuation"]
    fields(item, "schema_version policy episode repository_id issue_id issue_revision parent_id child_id parent_task child_task "
        "parent_requirement child_requirement checkpoints parent_guard parent_task_digest archive blueprint plan grant host generation "
        "window allocations usage")
    require(item["schema_version"] == 1 and type(item["schema_version"]) is int and item["policy"] == POLICY
            and item["repository_id"] == repository_id, "Unsupported accounting continuation")
    for name in ("episode", "parent_task", "child_task", "parent_requirement", "child_requirement", "parent_guard",
                 "parent_task_digest", "archive", "blueprint", "plan", "grant", "host", "issue_revision"):
        fingerprint(item[name])
    string(item["issue_id"]); string(item["parent_id"]); string(item["child_id"])
    require(item["parent_id"].startswith("personal:") and item["child_id"] == child_id(item["parent_id"], item["episode"])
            and key(item["parent_id"]) == item["parent_task"] and key(item["child_id"]) == item["child_task"],
            "Accounting episode identity is not its explicit parent-child relation")
    require(item["parent_requirement"] == requirement_id(item["parent_id"], "product")
            and item["child_requirement"] == requirement_id(item["child_id"], "product")
            and item["parent_task"] in registry["task_epochs"] and item["child_task"] in registry["task_epochs"],
            "Retain both canonical task incarnations")
    fields(item["checkpoints"], "initial guard result")
    for sha in item["checkpoints"].values():
        require(type(sha) is str and len(sha) == 40 and all(c in "0123456789abcdef" for c in sha), "Invalid archival checkpoint")
    integer(item["generation"], 1)
    fields(item["window"], "issued_at expires_at")
    for n in item["window"].values(): integer(n)
    require(60 <= item["window"]["expires_at"] - item["window"]["issued_at"] <= 3600, "Continuation window cannot expand")
    fields(item["allocations"], "previous previous_used current")
    for label, limits in item["allocations"].items():
        fields(limits, " ".join(ROLES))
        for name, value in limits.items():
            integer(value)
            maximum = CAPS[name] * (2 if label == "previous_used" and name == "worker_seconds" else 1)
            require(value <= maximum, "Continuation role/resource cap exceeded")
    require(item["allocations"]["current"]["scope_reviewers"] == 1
            and item["allocations"]["previous_used"]["scope_reviewers"] == 1
            and item["allocations"]["previous_used"]["developers"] == 1
            and item["allocations"]["current"]["forensic_reviewers"] == 0
            and all(item["allocations"]["current"][n] == 1 for n in ("maximum_parallel", "maximum_tasks", "maximum_rounds")),
            "Only one additive scope revalidation; no fresh forensic or parallel grant")
    requirements = registry["requirements"]
    old, new = requirements.get(item["parent_requirement"]), requirements.get(item["child_requirement"])
    require(old is not None and new is not None and digest(old) == item["parent_guard"]
            and old["mode"] == "unsafe" and old["reason"] == REASON and old["active"] is None
            and old["last_event"] == "attempt" and old["last"]["observation"]["outcome"] == "UNKNOWN"
            and old["last"]["observation"]["progress"] is None and old["last"]["observation"]["risk"] is None,
            "Only the exact immutable accounting-expiry parent qualifies")
    require(old["tasks"] == [item["parent_task"]] and new["tasks"] == [item["child_task"]]
            and new["acceptance"] == old["acceptance"] == ["original-ticket:" + item["issue_revision"]]
            and new["dependencies"] == old["dependencies"] and new["limits"] == old["limits"],
            "Successor must satisfy the same original criterion and unchanged thresholds")
    for identifier, guard in requirements.items():
        if item["child_task"] in guard["tasks"]:
            allowed = {"product": ["original-ticket:" + item["issue_revision"]],
                       "semantic-original": ["original"], "semantic-candidate": ["candidate"],
                       "local-feature": ["feature-prepared"], "personal-publication": ["published"],
                       "personal-product-effects": ["exact-effects-observed"],
                       "personal-post-pr-validation": ["prescribed-ci-qualified"]}
            require(guard["contract"] == item["child_id"] and guard["tasks"] == [item["child_task"]]
                    and guard["gate"] in allowed and guard["acceptance"] == allowed[guard["gate"]]
                    and guard["limits"] == old["limits"] and guard["forensic_round"] == old["forensic_round"],
                    "An episode cannot create another gate, relax limits or replenish forensic allowance")
    fields(item["usage"], "requests observations checks check_ids seconds samples payload_bytes")
    usage = item["usage"]
    for name in ("observations", "checks", "seconds", "samples", "payload_bytes"): integer(usage[name])
    require(usage["checks"] <= item["allocations"]["current"]["maximum_check_observations"], "Child check quota exhausted")
    require(type(usage["check_ids"]) is list and len(set(usage["check_ids"])) == len(usage["check_ids"]) == usage["checks"], "Exact lifetime check charges required")
    for identifier in usage["check_ids"]: fingerprint(identifier)
    require(type(usage["requests"]) is dict and len(usage["requests"]) <= 7, "Bounded child request census required")
    for identifier, row in usage["requests"].items():
        fingerprint(identifier); fields(row, "purpose")
        require(row["purpose"] in PURPOSES, "Unapproved child role")
    for role in set(PURPOSES.values()):
        require(sum(PURPOSES[r["purpose"]] == role for r in usage["requests"].values())
                <= item["allocations"]["current"][role], "Child role allocation exhausted")


def install(state, tasks, relation):
    """Lock-held, already authenticated personal transaction primitive only."""
    require(state["schema_version"] == 3 and state["progress_guard"]["schema_version"] == 1,
            "Explicit policy installation requires original execution v3/guard v1")
    require(key(relation["child_id"]) not in tasks, "Only one new explicit episode can be installed")
    parent = tasks[relation["parent_task"]]
    require(digest(parent) == relation["parent_task_digest"] and state["generation"] == relation["generation"], "Original task/generation changed")
    old = state["progress_guard"]["requirements"][relation["parent_requirement"]]
    require(digest(old) == relation["parent_guard"], "Original terminal guard changed")
    new = deepcopy(old)
    new.update(contract=relation["child_id"], tasks=[relation["child_task"]], sequence=0, mode="normal",
        last=None, last_event=None, active=None, request=None, plan=None, approval=None, campaign=None,
        reason="Explicit accounting-expiry continuation; original terminal parent retained")
    tasks[relation["child_task"]] = {"schema_version": 1, "key": relation["child_task"], "id": relation["child_id"],
        "repository_id": state["repository_id"], "iteration": 1, "phase": "active", "source_revision": parent["source_revision"],
        "assignments": {}, "blockers": [], "last_published_iteration": None}
    registry = state["progress_guard"]
    registry["task_epochs"][relation["child_task"]] = state["revision"] + 1
    registry["requirements"][relation["child_requirement"]] = new
    registry.update(schema_version=2, accounting_continuation=deepcopy(relation))


def consume_request(state, task_key, request_id, purpose):
    item = entry(state)
    require(item is not None and item["child_task"] == task_key and purpose in PURPOSES, "Unqualified episode request")
    old = item["usage"]["requests"].get(request_id)
    require(old is None or old == {"purpose": purpose}, "Request replay changed role")
    item["usage"]["requests"][request_id] = {"purpose": purpose}


def observe(state, task, before, after):
    item = entry(state)
    if item is None or item["child_task"] != task["key"]:
        return
    if before["active"] is not None and after["active"] is None and after["last"] != before["last"]:
        usage, measured = item["usage"], after["last"]["observation"]
        usage["observations"] += 1
        for target, source in (("seconds", "elapsed_seconds"), ("samples", "samples"), ("payload_bytes", "payload_bytes")):
            usage[target] += measured[source]
