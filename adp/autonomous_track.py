"""Explicit finite GitHub-track controller, composed from the accepted ports.

An operator supplies interpretations, independent evidence services and isolated
project workspaces. Issue prose never constructs those services or permissions.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .conductor import Conductor
from .discovery import complete_snapshot
from .discovery_schema import digest, validate_identity, validate_track
from .discovery_types import Status
from .errors import AuthorityError, Conflict
from .execution_memory import invocation_lock
from .execution_types import Admission
from .guard_types import data
from .lifecycle import TaskLifecycle
from .product_flow import GitHubProductFlow, PreparedScope
from .schema import integer, key, require, string
from .ticket_preparation import TicketPreparer
from .ticket_types import OriginalScope, Proposal, PreparationReview, ScopeAdditionApproval, DependencyEdit


@dataclass(frozen=True)
class PreparationInputs:
    scope: OriginalScope
    proposal: Proposal
    review: PreparationReview
    additions: tuple[ScopeAdditionApproval, ...] = ()
    dependency_edits: tuple[DependencyEdit, ...] = ()


@dataclass(frozen=True)
class TaskSpec:
    identity: object
    task_id: str
    workspace_key: str
    preparer: TicketPreparer
    assess: object
    admission_factory: object
    validation_factory: object
    delegation_factory: object
    policy_factory: object
    mode: str = "CANDIDATE"
    action: object = None
    ticket_publisher: object = None


@dataclass(frozen=True)
class TrackWindow:
    id: str
    configuration: str
    issued_at: int
    expires_at: int
    maximum_rounds: int
    maximum_tasks: int
    maximum_parallel: int = 1


class _Snapshot:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def discover(self):
        return self.snapshot


class AutonomousTrack:
    """One repository, at most eight tasks, no timer/daemon or renewed budget.

    assess(original, scope_track, policy_inspection) returns authenticated
    PreparationInputs. admission_factory(packet) provides the project's branch,
    commit summary and original M2 contract. Neither callback runs in a worker.
    """
    def __init__(self, conductor: Conductor, window: TrackWindow, tasks: tuple[TaskSpec, ...]):
        require(type(conductor) is Conductor and type(window) is TrackWindow, "Actual Conductor and explicit track window required")
        from .policy_schema import fingerprint
        fingerprint(window.id); fingerprint(window.configuration)
        integer(window.issued_at); integer(window.expires_at)
        require(0 < window.expires_at - window.issued_at <= 3600
                and type(window.maximum_rounds) is int and 1 <= window.maximum_rounds <= 32
                and type(window.maximum_tasks) is int and 1 <= window.maximum_tasks <= 8
                and type(window.maximum_parallel) is int and 1 <= window.maximum_parallel <= 4,
                "Finite track bounds required")
        require(type(tasks) is tuple and 1 <= len(tasks) <= window.maximum_tasks
                and all(type(t) is TaskSpec and type(t.preparer) is TicketPreparer for t in tasks), "Bounded explicit task specifications required")
        for task in tasks:
            validate_identity(task.identity)
            require(task.identity.repository_id == conductor.memory.config.identity, "Track cannot mix repository identities")
            string(task.task_id); string(task.workspace_key, 128)
            require(task.workspace_key in conductor.projects and task.mode in ("CANDIDATE", "COMMITTED", "POST_PR"), "Unknown project/check sequence")
            if task.ticket_publisher is not None:
                from .ticket_publication import TicketPublisher
                publisher = task.ticket_publisher
                require(type(publisher) is TicketPublisher and publisher.c is conductor
                        and publisher.admission.identity == task.identity and publisher.admission.task_id == task.task_id
                        and publisher.admission.workspace_key == task.workspace_key, "Publisher must bind the actual immutable task/workspace")
        for values in ([t.identity for t in tasks], [t.task_id for t in tasks], [t.workspace_key for t in tasks]):
            require(len(values) == len(set(values)), "Distinct task identity and workspace bindings required")
        roots = [conductor.projects[t.workspace_key].root.resolve() for t in tasks]
        require(all(not a.is_relative_to(b) for i, a in enumerate(roots) for j, b in enumerate(roots) if i != j), "Track workspaces must be isolated")
        self.c, self.window, self.tasks = conductor, window, tasks
        self.configuration = digest({"window": data(window), "tasks": [{"identity": data(t.identity), "task": t.task_id,
            "workspace": t.workspace_key, "root": str(conductor.projects[t.workspace_key].root.resolve()), "mode": t.mode,
            "archive": str(t.preparer.archive.directory), "ticket_target": t.ticket_publisher.service.target.fingerprint if t.ticket_publisher else None,
            "ticket_envelope": t.ticket_publisher.envelope if t.ticket_publisher else None} for t in tasks]})

    def status(self):
        # Inspect only; no discovery, claims, migration or runtime dispatch.
        observed = self.c.journal.inspect()
        return {"mode": "READ_ONLY", "generation": observed["state"]["generation"],
                "track": observed["state"]["execution"].get("track"), "background_work": "UNKNOWN"}

    def _ticket_stops(self):
        unconfirmed = set()
        for spec in self.tasks:
            if spec.ticket_publisher is not None:
                try:
                    unconfirmed.update(spec.ticket_publisher.service.unconfirmed_contexts())
                except Exception:
                    unconfirmed.add("ticket:" + digest(spec.identity))
        return unconfirmed

    def _window(self, *, create=False):
        c, w = self.c, self.window
        observed = c.journal.inspect()
        require(observed["local_owner"], "Actual M1 ownership required")
        require(w.issued_at <= c.clock() < w.expires_at, "Track window not current")
        require(observed["state"]["execution"]["schema_version"] == 3, "Explicit execution-track upgrade required")
        row = observed["state"]["execution"]["track"]
        generation = observed["state"]["generation"]
        if row is None:
            require(create, "No admitted track window")
            row = {"id": w.id, "config": self.configuration, "generation": generation,
                "issued_at": w.issued_at, "expires": w.expires_at, "maximum_rounds": w.maximum_rounds,
                "used_rounds": 0, "maximum_tasks": w.maximum_tasks, "maximum_parallel": w.maximum_parallel,
                "status": "READY", "slots": {}}
            c._grant("track/window", digest({"repository": c.memory.config.identity, "generation": generation, "window": row}))
            c.journal.change(lambda execution, state, tasks: execution.update(track=row))
        require(row["id"] == w.id and row["config"] == self.configuration and row["generation"] == generation,
                "Track configuration/generation changed; no implicit budget renewal")
        return row

    def _slot(self, spec, **changes):
        identity = digest(spec.identity)
        def update(execution, state, tasks):
            slots = execution["track"]["slots"]
            if identity not in slots:
                require(len(slots) < self.window.maximum_tasks, "Track task capacity exhausted")
                slots[identity] = {"identity": data(spec.identity), "task_id": spec.task_id, "workspace_key": spec.workspace_key,
                    "packet": None, "status": "PREPARING", "disposition": None}
            slots[identity].update(changes)
        self.c.journal.change(update)

    def _attach(self, spec, packet_reference):
        packet = spec.preparer.archive.packet(packet_reference)
        admission = spec.admission_factory(packet)
        require(type(admission) is Admission and admission.identity == spec.identity and admission.task_id == spec.task_id
                and admission.workspace_key == spec.workspace_key and admission.expected_revision == packet.base_sha
                and admission.product_goal == packet.goal and admission.allowed_paths == packet.allowed_paths
                and admission.requirement.acceptance == tuple(c.text for c in packet.clauses if c.kind == "ACCEPTANCE"),
                "Project admission must conserve the immutable prepared packet")
        expected_dependencies = tuple("issue:" + digest(identity) for identity in packet.dependencies)
        require(admission.requirement.dependencies == expected_dependencies, "M2 prerequisites differ from original packet")
        scope = PreparedScope(spec.preparer, packet_reference)
        flow = GitHubProductFlow(self.c, scope, spec.validation_factory, spec.delegation_factory)
        life = TaskLifecycle(self.c, scope, spec.validation_factory, mode=spec.mode, action=spec.action)
        self.c.projects[spec.workspace_key] = replace(self.c.projects[spec.workspace_key], product_flow=flow, lifecycle=life)
        return admission

    def _prepare(self, spec, track):
        candidates = [c for c in track.candidates if c.identity == spec.identity]
        if len(candidates) != 1 or not candidates[0].observed or candidates[0].status == Status.DONE:
            return None
        candidate = candidates[0]
        repository = next(s for s in track.snapshots if s.repository.id == spec.identity.repository_id)
        archive = spec.preparer.archive
        reference = archive.frozen_reference(spec.identity) or archive.freeze(repository, spec.identity)
        if spec.ticket_publisher is not None and not spec.ticket_publisher.recover(preparer=spec.preparer):
            self._slot(spec, status="UNKNOWN")
            return None
        original = archive.original(reference)
        # Reobserve the project-local checkout binding for each lane. The same
        # GitHub issue must agree with the track observation; local branches are
        # independent and are never invented from issue prose.
        snapshots = tuple(adapter.discover() for adapter in spec.preparer.adapters)
        local_reviews = self.c.readiness.reviews(snapshots)
        local_track = spec.preparer.planner.plan(snapshots, reviews=local_reviews)
        local = next((v for v in local_track.candidates if v.identity == spec.identity), None)
        require(local is not None and local.issue == candidate.issue
                and all(complete_snapshot(s) for s in snapshots), "Task-local and current GitHub observations disagree")
        track = local_track
        candidate = local
        # Keep exactly the observed snapshots while the independent preparation
        # service assesses them. Execution reobserves actual M4 afterward.
        policy = spec.policy_factory()
        preparer = TicketPreparer(adapters=tuple(_Snapshot(s) for s in track.snapshots), planner=spec.preparer.planner,
            policy=policy, authority=spec.preparer.authority, archive=archive, clock=self.c.clock)
        inputs = spec.assess(original, track, policy.inspect_repository())
        require(type(inputs) is PreparationInputs and inputs.scope.original_reference == reference,
                "Authenticated original-ticket assessment required")
        changed = (candidate.issue.title, candidate.issue.body) != (original.issue.title, original.issue.body)
        edits = (any(change.field in ("TITLE", "BODY") for change in inputs.proposal.changes) and not changed) or bool(inputs.dependency_edits)
        if edits:
            if spec.ticket_publisher is None:
                self._slot(spec, status="BLOCKED_OPERATOR")
                return None
            result = spec.ticket_publisher.publish(inputs, track=track, preparer=preparer, dependency_edits=inputs.dependency_edits)
            self._slot(spec, status=result)
            # An edit bundle, even observed complete, never authorizes code from
            # the old DAG. A later fresh independent assessment is mandatory.
            return None
        reviews = tuple(r for candidate in track.candidates for r in candidate.reviews)
        result = preparer.prepare(inputs.scope, inputs.proposal, inputs.review,
            readiness_reviews=reviews, additions=inputs.additions)
        if result.status != Status.READY:
            self._slot(spec, status=str(result.status) if str(result.status) in
                {"BLOCKED_OPERATOR", "UNKNOWN", "UNSUPPORTED"} else "BLOCKED")
            return None
        self._slot(spec, packet=result.packet_reference, status="ACTIVE")
        return self._attach(spec, result.packet_reference)

    def run(self, *, rounds=1, maximum_parallel=None, authorized=False, recover=False):
        if not authorized:
            raise AuthorityError("Autonomous track requires explicit finite execution authority")
        parallel = self.window.maximum_parallel if maximum_parallel is None else maximum_parallel
        require(type(rounds) is int and 1 <= rounds <= 4 and type(parallel) is int
                and 1 <= parallel <= self.window.maximum_parallel, "Invocation exceeds finite track limits")
        c, admissions = self.c, []
        with invocation_lock(c.memory.control):
            if recover:
                c.memory.recover()
            c._privacy_preflight()
            self._window(create=True)
            try:
                if self._ticket_stops():
                    stops = sorted(self._ticket_stops() | set(c._quiesce(None)))
                    c.journal.change(lambda execution, state, tasks: execution["track"].update(status="UNKNOWN"))
                    return {"status": "UNKNOWN", "background_work": "UNKNOWN", "unconfirmed_contexts": stops,
                            "tasks": {}, "track": self.status()["track"]}
                results, waited, unconfirmed = {}, set(), []
                runtime_status = None
                for _ in range(rounds):
                    row = self._window()
                    if row["used_rounds"] >= row["maximum_rounds"]:
                        break
                    track = c.readiness.observe()
                    validate_track(track)
                    require(all(complete_snapshot(s) for s in track.snapshots), "Incomplete track cannot authorize execution")
                    c._grant("track/refresh", digest({"window": row["id"], "generation": row["generation"],
                        "round": row["used_rounds"], "track": digest(track)}))
                    c.journal.change(lambda execution, state, tasks: execution["track"].update(
                        used_rounds=execution["track"]["used_rounds"] + 1))
                    selected = []
                    by_identity = {s.identity: s for s in self.tasks}
                    order = list(track.order) + [s.identity for s in self.tasks if s.identity not in track.order]
                    for identity in order:
                        spec = by_identity.get(identity)
                        if spec is None or spec.task_id in waited:
                            continue
                        slot = self._window()["slots"].get(digest(identity))
                        if slot is not None and slot["status"] == "COMPLETE":
                            continue
                        if slot is not None and slot["packet"] is not None:
                            admission = self._attach(spec, slot["packet"])
                            existing = c.journal.inspect()["state"]["execution"]["tasks"].get(key(spec.task_id))
                            if existing is not None and existing["stage"] == "COMPLETE":
                                c._project(admission).product_flow.reobserve_completed(admission)
                                match = next((candidate for candidate in track.candidates if candidate.identity == identity), None)
                                done = match is not None and match.status == Status.DONE
                                self._slot(spec, status="COMPLETE" if done else "WAITING_TRACK",
                                    disposition=digest(match) if done else None)
                                continue
                        else:
                            admission = self._prepare(spec, track)
                        if admission is not None:
                            selected.append(admission)
                    if not selected:
                        break
                    admissions = selected
                    result = c._run(tuple(selected), maximum_parallel=parallel, rounds=1)
                    unconfirmed = result.get("unconfirmed_contexts", [])
                    runtime_status = result["status"]
                    results.update(result.get("tasks", {}))
                    for admission in selected:
                        observed = result.get("tasks", {}).get(admission.task_id, {})
                        status = observed.get("status", "UNKNOWN")
                        spec = by_identity[admission.identity]
                        if status in {"PENDING_VALIDATION", "WAITING_HUMAN_APPROVAL", "UNSUPPORTED", "UNKNOWN", "BLOCKED"}:
                            self._slot(spec, status=status)
                            waited.add(admission.task_id)
                    if result["status"] in {"UNKNOWN", "UNSUPPORTED_RUNTIME"} or any(
                        v.get("status") == "BLOCKED" for v in result.get("tasks", {}).values()):
                        break
                # One final observation is essential: local merge/report receipts
                # do not certify that another task is independently READY.
                final_track = c.readiness.observe()
                validate_track(final_track)
                require(all(complete_snapshot(s) for s in final_track.snapshots), "Final track observation incomplete")
                for spec in self.tasks:
                    slot = self._window()["slots"].get(digest(spec.identity))
                    task = c.journal.inspect()["state"]["execution"]["tasks"].get(key(spec.task_id))
                    if slot and slot["packet"] and task and task["stage"] == "COMPLETE":
                        candidate = next((v for v in final_track.candidates if v.identity == spec.identity), None)
                        done = candidate is not None and candidate.status == Status.DONE
                        self._slot(spec, status="COMPLETE" if done else "WAITING_TRACK", disposition=digest(candidate) if done else None)
                row = self._window()
                unconfirmed = sorted(set(unconfirmed) | self._ticket_stops() | set(c._quiesce(None)))
                status = "COMPLETE" if len(row["slots"]) == len(self.tasks) and all(
                    v["status"] == "COMPLETE" for v in row["slots"].values()) else "EXHAUSTED" if row["used_rounds"] >= row["maximum_rounds"] else "STOPPED"
                if unconfirmed or runtime_status == "UNKNOWN":
                    status = "UNKNOWN"
                elif runtime_status == "UNSUPPORTED_RUNTIME":
                    status = "UNSUPPORTED"
                c.journal.change(lambda execution, state, tasks: execution["track"].update(status=status))
                return {"status": status, "tasks": results, "track": self.status()["track"],
                    "background_work": "UNKNOWN" if unconfirmed or runtime_status == "UNKNOWN" else False,
                    "unconfirmed_contexts": unconfirmed}
            except BaseException:
                if c._quiesce(None) or self._ticket_stops():
                    raise Conflict("Track has unconfirmed external stops; reconciliation required")
                raise

    def resume(self, **kwargs):
        return self.run(recover=True, **kwargs)

    def adopt_generation(self, *, authorized=False):
        """Explicit safe handoff adoption; no changed window or renewed budgets."""
        if not authorized:
            raise AuthorityError("Track generation adoption requires explicit authority")
        c = self.c
        with invocation_lock(c.memory.control):
            observed = c.journal.inspect()
            row = observed["state"]["execution"].get("track")
            require(observed["local_owner"] and row is not None and row["id"] == self.window.id
                    and row["config"] == self.configuration and self.window.issued_at <= c.clock() < self.window.expires_at,
                    "Same current finite window and actual new owner required")
            require(not c._quiesce(None) and not self._ticket_stops() and not any(e["status"] != "OBSERVED" for e in
                observed["state"]["execution"]["ticket_effects"].values()), "Unknown ticket/runtime effects refuse adoption")
            require(all(a["status"] == "OBSERVED" for a in observed["state"]["execution"]["actions"].values())
                    and all(j["status"] in ("COMPLETE", "CANCELLED") for t in observed["state"]["execution"]["tasks"].values()
                            for j in t["jobs"].values()), "Reconcile every prior assignment/effect before adoption")
            for spec in self.tasks:
                slot = row["slots"].get(digest(spec.identity))
                if slot and slot["packet"]:
                    admission = self._attach(spec, slot["packet"])
                    life = c._project(admission).lifecycle
                    life._admission = admission
                    life.before_handoff()
            generation = observed["state"]["generation"]
            require(generation > row["generation"], "Only a newly claimed M1 generation may adopt a window")
            c._grant("track/adopt-generation", digest({"window": row, "generation": generation}),
                     context={"configuration": self.configuration, "prior_state": observed["state"]["execution"]})
            c._ownership(generation)
            def adopt(execution, state, tasks):
                execution["track"]["generation"] = generation
                for task_key, life in execution["lifecycles"].items():
                    task = execution["tasks"][task_key]
                    if task["stage"] == "COMPLETE":
                        continue
                    require(life["phase"] != "CHECKING", "Unobserved project action refuses adoption")
                    life.update(gate=None, candidate=None, expires=0, journal=None, job=None,
                                phase="COMMITTED_CHECKS" if task["stage"] in ("REVIEW", "PUBLISH") else "DEVELOP")
                    if task["stage"] == "PUBLISH":
                        task.update(stage="REVIEW", review=None)
                    flow = execution["product_flows"].get(task_key)
                    if flow is not None:
                        flow.update(gates=[], review_job=None, acceptance=None, phase="PREPARED")
            c.journal.change(adopt)
            return self.status()

    def handoff(self, *, authorized=False):
        # A new generation cannot inherit this window's execution grants or
        # counters by silently changing configuration. Retain it as evidence.
        row = self._window()
        require(not self._ticket_stops(), "Unconfirmed ticket transport stop refuses handoff")
        for spec in self.tasks:
            slot = row["slots"].get(digest(spec.identity))
            if slot is not None and slot["packet"] is not None:
                admission = self._attach(spec, slot["packet"])
                life = self.c._project(admission).lifecycle
                life._admission = admission
        return self.c.handoff(authorized=authorized)
