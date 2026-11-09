"""Accepted discovery/policy integration, including exact reserved guard safety."""
from __future__ import annotations

from .discovery import DependencyPlanner
from .guard_types import Attestation, Decision, DecisionKind
from .policy import PolicyProvider
from .policy_types import Safety, Task
from .schema import require


class M4ReadinessService:
    def __init__(self, adapters, planner: DependencyPlanner, reviews):
        self.adapters, self.planner, self.reviews = adapters, planner, reviews

    def observe(self):
        snapshots = tuple(adapter.discover() for adapter in self.adapters)
        return self.planner.plan(snapshots, reviews=self.reviews(snapshots))


class ReservedSafety:
    """An ALLOW for one already-reserved M2 action, never a new attempt.

    Generic guard.inspect remains blocked while a reservation is outstanding.
    This adapter reuses the actual M2 token/context/deadline validators so M3
    can authorize bounded suboperations after durable checkpointing. No guard
    threshold, counter, observation or stored approval is changed here.
    """
    def __init__(self, guard, permit=None, *, forensic_request=None):
        self.guard, self.permit, self.forensic_request = guard, permit, forensic_request

    def observe(self, task: Task):
        state, memory_task, item = self.guard._snapshot(task.task_id, task.requirement_id)
        baseline = self.guard._baseline(task.requirement_id, state, memory_task, item)
        if self.forensic_request is not None:
            require(item["mode"] == "forensic" and item["request"] is not None
                    and item["request"]["id"] == self.forensic_request
                    and item["request"]["context"] == self.guard._context(state, memory_task), "Stale forensic-only admission")
        else:
            require(self.permit is not None, "An exact M2 reservation is required")
            active = self.guard._active(state, memory_task, item, self.permit.token)
            require(item["mode"] in ("normal", "running") and active["started"] <= self.guard._now() <= active["deadline"],
                    "Reserved attempt is stopped or outside containment")
        approval = None
        stored = item["approval"]
        if stored is not None and stored["context"] == self.guard._context(state, memory_task):
            self.guard._verify(Attestation(stored["reviewer"], stored["reference"], stored["subject"]),
                               "progress", stored["subject"], authors=item["authors"])
            approval = baseline
        memory = self.guard.memory.inspect()
        require(memory["health"] == "SYNCED", "Memory changed during reserved safety inspection")
        return Safety(Decision(DecisionKind.ALLOW, "Only this existing bounded reservation", baseline),
                      memory["local_owner"], tuple(item["authors"]), memory["local_head"], approval)


def policy_task(memory, admission, requirement_id, source_ref):
    observed = memory.inspect()
    require(observed["health"] == "SYNCED" and observed["local_owner"], "Current M1 ownership is required")
    task = memory._task(observed["tasks"], admission.task_id)
    state = observed["state"]
    authors = tuple(state["progress_guard"]["requirements"][requirement_id]["authors"])
    return Task(memory.config.identity, admission.task_id, admission.branch_slug, task["source_revision"], source_ref,
                requirement_id, state["generation"], state["progress_guard"]["task_epochs"][task["key"]],
                task["iteration"], authors or ("conductor:admitted-source",))
