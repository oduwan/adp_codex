"""Closed, bounded opt-in execution-v3 records, inside the M1 checkpoint."""
from __future__ import annotations

from .discovery_schema import digest, typed, validate_identity
from .discovery_types import Identity
from .execution_privacy import credential_shaped
from .guard_types import Permit
from .policy_schema import fingerprint, sha
from .policy_types import CandidateSource, TicketEditRequest
from .project_validation_types import CandidateEvidenceGate, EvidenceGate
from .schema import fields, integer, key, require, string

SLOT_STATES = {"PREPARING", "ACTIVE", "PENDING_VALIDATION", "WAITING_HUMAN_APPROVAL", "WAITING_TRACK",
               "COMPLETE", "BLOCKED", "BLOCKED_OPERATOR", "UNKNOWN", "UNSUPPORTED"}
LIFE_PHASES = {"DEVELOP", "CHECKING", "CHECKED", "COMMITTING", "COMMITTED_CHECKS", "REVIEW",
               "PENDING_VALIDATION", "REQUIRES_CORRECTION", "QUALIFIED"}


def track_schema(execution, repository_id):
    require(not credential_shaped({n: execution[n] for n in ("track", "lifecycles", "ticket_effects")}),
            "Sensitive track state refused")
    window = execution["track"]
    if window is not None:
        fields(window, "id config generation issued_at expires maximum_rounds used_rounds maximum_tasks maximum_parallel status slots")
        for name in ("id", "config"):
            fingerprint(window[name])
        integer(window["generation"], 1)
        integer(window["issued_at"])
        integer(window["expires"])
        require(0 < window["expires"] - window["issued_at"] <= 3600, "Track window lifetime exceeds bounds")
        require(type(window["maximum_rounds"]) is int and 1 <= window["maximum_rounds"] <= 32,
                "Invalid total finite track rounds")
        integer(window["used_rounds"])
        require(window["used_rounds"] <= window["maximum_rounds"], "Track round budget exhausted")
        require(type(window["maximum_tasks"]) is int and 1 <= window["maximum_tasks"] <= 8
                and type(window["maximum_parallel"]) is int and 1 <= window["maximum_parallel"] <= 4,
                "Track task/lane budget exceeds accepted bounds")
        require(window["status"] in SLOT_STATES | {"READY", "STOPPED", "EXHAUSTED"}, "Invalid track status")
        require(type(window["slots"]) is dict and len(window["slots"]) <= window["maximum_tasks"], "Track slot capacity exhausted")
        workspaces, task_ids = [], []
        for identity_key, slot in window["slots"].items():
            fields(slot, "identity task_id workspace_key packet status disposition")
            identity = typed(Identity, slot["identity"])
            validate_identity(identity)
            require(identity.repository_id == repository_id and identity_key == digest(identity), "Foreign track slot")
            string(slot["task_id"])
            string(slot["workspace_key"], 128)
            workspaces.append(slot["workspace_key"]); task_ids.append(slot["task_id"])
            if slot["packet"] is not None:
                string(slot["packet"], 128)
            require(slot["status"] in SLOT_STATES, "Invalid task disposition")
            if slot["disposition"] is not None:
                fingerprint(slot["disposition"])
            task = execution["tasks"].get(key(slot["task_id"]))
            if task is not None:
                require(task["identity"] == slot["identity"] and task["workspace_key"] == slot["workspace_key"],
                        "Track task identity differs from admitted execution")
            if slot["status"] == "COMPLETE":
                require(task is not None and task["stage"] == "COMPLETE" and slot["disposition"] is not None,
                        "Track completion requires product and independent refreshed disposition")
        require(len(workspaces) == len(set(workspaces)) and len(task_ids) == len(set(task_ids)),
                "Track slots require distinct task/workspace bindings")
    require(type(execution["lifecycles"]) is dict and len(execution["lifecycles"]) <= 8, "Lifecycle capacity exhausted")
    for task_key, life in execution["lifecycles"].items():
        require(task_key in execution["tasks"], "Lifecycle references an unadmitted task")
        fields(life, "packet mode phase job candidate gate expires policy feedback failure journal"
               + (" workspace" if "workspace" in life else ""))
        if life.get("workspace") is not None:
            fingerprint(life["workspace"])
        string(life["packet"], 128)
        require(life["mode"] in ("CANDIDATE", "COMMITTED", "POST_PR") and life["phase"] in LIFE_PHASES,
                "Invalid project development-check sequence")
        task = execution["tasks"][task_key]
        if life["job"] is not None:
            require(life["job"] in task["jobs"], "Lifecycle check lost its actual assignment")
        if life["candidate"] is not None:
            source = typed(CandidateSource, life["candidate"])
            for value in (source.content_digest, source.index_digest, source.worktree_digest):
                fingerprint(value)
        if life["gate"] is not None:
            gate = typed(CandidateEvidenceGate | EvidenceGate, life["gate"])
            require(gate.request.repository_id == repository_id and gate.request.task_id == task["task_id"],
                    "Foreign lifecycle check receipt")
            require(life["job"] is not None and gate.request.revision == task["jobs"][life["job"]]["revision"],
                    "Lifecycle check is not bound to its source assignment")
        integer(life["expires"])
        fingerprint(life["policy"])
        if life["journal"] is not None:
            fingerprint(life["journal"])
        string(life["feedback"], 1024)
        if life["failure"] is not None:
            fields(life["failure"], "reference source")
            string(life["failure"]["reference"], 512)
            fingerprint(life["failure"]["source"])
    effects = execution["ticket_effects"]
    require(type(effects) is dict and len(effects) + len(execution["actions"]) <= 32,
            "Combined external-effect capacity exhausted")
    for effect_id, effect in effects.items():
        fingerprint(effect_id)
        fields(effect, "task_id generation requirement permit request reference status observed_revision receipt assignment")
        string(effect["task_id"])
        integer(effect["generation"], 1)
        fingerprint(effect["requirement"])
        typed(Permit, effect["permit"])
        request = typed(TicketEditRequest, effect["request"])
        require(request.operation == "TICKET_EDIT", "Foreign ticket operation")
        string(effect["reference"], 128)
        string(effect["receipt"], 512)
        string(effect["assignment"], 128)
        require(effect["status"] in ("PREPARED", "SUBMITTED", "OBSERVED", "UNKNOWN"), "Invalid ticket effect state")
        if effect["observed_revision"] is not None:
            fingerprint(effect["observed_revision"])
