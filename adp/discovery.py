"""Deterministic dependency proposals and non-destructive refresh reconciliation."""
from __future__ import annotations

import json
import time
from dataclasses import replace

from .guard_types import data
from .schema import bundle, integer, require
from .discovery_schema import (MAX_ITEMS, digest, json_value, key, validate_identity,
    validate_progress, validate_review, validate_snapshot, validate_track)
from .discovery_types import (Candidate, Identity, MemoryBinding, ProgressRecord,
    ReadinessAuthority, ReadinessReview, Snapshot, Status, Track)


class MemoryProgressAdapter:
    """Observe accepted M1 records through explicit provider-to-memory bindings.

    No checkpoint, lock, recovery, reservation or upgrade. M1 accepted results
    stay observations; PASS does not prove accepted external disposition.
    """
    def __init__(self, memory, bindings: tuple[MemoryBinding, ...]):
        require(type(bindings) is tuple and len(bindings) <= 64
                and all(type(b) is MemoryBinding for b in bindings), "Invalid memory bindings")
        require(len({b.task_id for b in bindings}) == len(bindings)
                and len({b.identity for b in bindings}) == len(bindings), "Ambiguous memory/task mapping")
        self.memory, self.bindings = memory, bindings

    def observe(self) -> tuple[ProgressRecord, ...]:
        observation = self.memory.inspect()
        require(observation["health"] == "SYNCED", "Current memory progress unavailable or unsynchronized")
        state, tasks = observation["state"], observation["tasks"]
        bundle(state, tasks, self.memory.config.identity)
        records = []
        for binding in self.bindings:
            validate_identity(binding.identity)
            from .schema import key as memory_key
            task = tasks.get(memory_key(binding.task_id))
            require(task is not None and task["id"] == binding.task_id, "Mapped memory task is absent")
            records.append(ProgressRecord(binding.identity, state["repository_id"], observation["local_head"],
                state["generation"], json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=True)))
        return tuple(sorted(records, key=lambda p: p.identity))


def review_subject(snapshots: tuple[Snapshot, ...], review: ReadinessReview) -> str:
    validate_review(review)
    for snapshot in snapshots:
        validate_snapshot(snapshot)
    payload = data(review)
    payload.pop("evidence")
    return digest({"domain": "discovery/readiness", "snapshots": [data(s) for s in sorted(snapshots, key=lambda s: s.repository.id)],
                   "review": payload})


def _cycles(graph):
    """Tarjan over the bounded inventory, retaining every observed edge."""
    counter, stack, on_stack, indexes, low, result = 0, [], set(), {}, {}, []
    def visit(node):
        nonlocal counter
        indexes[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for neighbor in sorted(graph[node]):
            if neighbor not in indexes:
                visit(neighbor)
                low[node] = min(low[node], low[neighbor])
            elif neighbor in on_stack:
                low[node] = min(low[node], indexes[neighbor])
        if low[node] == indexes[node]:
            component = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1 or node in graph[node]:
                result.append(tuple(sorted(component)))
    for node in sorted(graph):
        if node not in indexes:
            visit(node)
    return tuple(sorted(result))


def _retain(old, current, limit):
    records = {digest(v): v for v in old}
    records.update({digest(v): v for v in current})
    require(len(records) <= limit, "Retained evidence capacity exhausted; explicit disposition required")
    return tuple(records[k] for k in sorted(records))


def complete_snapshot(snapshot):
    required = {"repository", "repository-refresh", "issues", "pulls", "issues-refresh", "pulls-refresh",
                "inventory-stable", "context-stable"}
    for issue in snapshot.issues:
        prefix = "issue:" + key(issue.identity)
        required.update(prefix + ":" + name for name in ("comments", "timeline", "blocked_by", "sub_issues", "current", "stable"))
    return required <= {c.name for c in snapshot.coverage} and all(c.status == "COMPLETE" for c in snapshot.coverage)


class DependencyPlanner:
    """Readiness is a proposal. Even READY never grants operation authority."""
    def __init__(self, *, authority: ReadinessAuthority | None = None, clock=None):
        self.authority = authority
        self.clock = clock or (lambda: int(time.time()))

    def _verified(self, snapshots, issue, review, now):
        validate_review(review)
        if review.identity != issue.identity or review.evidence is None or self.authority is None:
            return False
        if review.evidence.reviewer in issue.authors or not (review.observed_at <= now <= review.expires_at
                and 0 < review.expires_at - review.observed_at <= 3600):
            return False
        subject = review_subject(snapshots, review)
        return review.evidence.subject == subject and self.authority.verify(
            review.evidence, purpose="discovery/readiness", subject=subject) is True

    def plan(self, snapshots: tuple[Snapshot, ...], *, previous: Track | None = None,
             reviews: tuple[ReadinessReview, ...] = (), memory: tuple[MemoryProgressAdapter, ...] = ()) -> Track:
        require(type(snapshots) is tuple and 0 < len(snapshots) <= 16, "Select bounded repository snapshots")
        now = self.clock()
        integer(now)
        for snapshot in snapshots:
            validate_snapshot(snapshot)
            require(snapshot.observed_at <= now and now - snapshot.observed_at <= 3600, "Discovery snapshot is stale or from the future")
        require(len({s.repository.id for s in snapshots}) == len(snapshots)
                and len({s.repository.name.lower() for s in snapshots}) == len(snapshots), "Ambiguous repository identity/name mapping")
        require(type(reviews) is tuple and len(reviews) <= MAX_ITEMS, "Too many readiness reviews")
        require(len({r.identity for r in reviews}) == len(reviews), "Conflicting current readiness reviews")
        review_map = {r.identity: r for r in reviews}
        for review in reviews:
            validate_review(review)
        old = {}
        if previous is not None:
            validate_track(previous)
            old = {c.identity: c for c in previous.candidates}
        observations, repositories, numbers, prs, snapshot_map = {}, {}, {}, {}, {}
        for snapshot in snapshots:
            repo = snapshot.repository
            repositories[repo.id] = repo
            for issue in snapshot.issues:
                observations[issue.identity] = issue
                numbers[(repo.name.lower(), issue.number)] = issue.identity
                snapshot_map[issue.identity] = snapshot
            for pr in snapshot.pulls:
                prs[(repo.name.lower(), pr.number)] = pr
        require(len(observations.keys() | old.keys()) <= MAX_ITEMS, "Track inventory exceeds bounds")
        for identity, candidate in old.items():
            if identity not in observations:
                observations[identity] = candidate.issue
        live_progress = {}
        require(type(memory) is tuple and len(memory) <= 16, "Invalid memory observation ports")
        for port in memory:
            require(type(port) is MemoryProgressAdapter, "Current progress requires the observational M1 adapter")
            for record in port.observe():
                validate_progress(record)
                require(record.identity in snapshot_map, "Memory binding points outside observed issues")
                repo = repositories[record.identity.repository_id]
                require(repo.memory_id == record.memory_repository_id, "Memory and provider repository mapping differs")
                require(record.identity not in live_progress, "Duplicate memory binding")
                live_progress[record.identity] = record
        graph = {identity: set() for identity in observations}
        missing, tentative, heads, linked, assessments, diagnostics = {}, {}, {}, {}, {}, []
        for identity, issue in observations.items():
            missing[identity], tentative[identity], heads[identity], linked[identity] = [], [], [], []
            review = review_map.get(identity)
            if review is None and identity in old:
                verified = [r for r in old[identity].reviews if self._verified(snapshots, issue, r, now)]
                if len(verified) == 1:
                    review = verified[0]
            assessments[identity] = review if review is not None and self._verified(snapshots, issue, review, now) else None
            for relation in issue.relations:
                target = numbers.get((relation.target.repository.lower(), relation.target.number))
                if target is not None and relation.target.issue_id is not None and target.issue_id != relation.target.issue_id:
                    target = None
                if relation.kind == "PULL_REQUEST":
                    pr = prs.get((relation.target.repository.lower(), relation.target.number))
                    if pr is None or relation.target.issue_id is not None and pr.identity.issue_id != relation.target.issue_id:
                        missing[identity].append("Linked PR metadata is absent or identity changed")
                    else:
                        heads[identity].append((key(pr.identity), pr.head_sha))
                        linked[identity].append(pr)
                    continue
                if relation.confidence == "NATIVE" and relation.kind == "BLOCKED_BY":
                    if target is None:
                        missing[identity].append("Explicit prerequisite is missing: " + relation.target.repository + "#" + str(relation.target.number))
                    else:
                        graph[identity].add(target)
                elif relation.kind in {"BLOCKED_BY", "DUPLICATE_OF", "SUPERSEDED_BY"}:
                    accepted = assessments[identity]
                    if accepted is None or (digest(relation) not in accepted.dismissed_inferences
                            and not (target is not None and (target in accepted.confirmed_dependencies or target == accepted.duplicate_of))):
                        tentative[identity].append("Tentative " + relation.kind + " requires independent confirmation: " + relation.source)
                elif relation.kind == "SUB_ISSUE" and assessments[identity] is None:
                    tentative[identity].append("Native sub-issue hierarchy needs bounded parent/child scope assessment")
            accepted = assessments[identity]
            if accepted is not None:
                for target in (*accepted.confirmed_dependencies, *((accepted.duplicate_of,) if accepted.duplicate_of else ())):
                    if target not in observations or target not in snapshot_map:
                        missing[identity].append("Confirmed prerequisite/canonical task is outside the observed inventory")
                    else:
                        graph[identity].add(target)
        cycles = _cycles(graph)
        cyclic = {i for component in cycles for i in component}
        statuses, reasons = {}, {}
        for identity, issue in observations.items():
            previous_item, snapshot, review = old.get(identity), snapshot_map.get(identity), assessments[identity]
            why = []
            status = Status.READY
            if snapshot is None:
                status, why = Status.UNKNOWN, ["Issue absent from refresh; prior observation/evidence retained"]
            elif not complete_snapshot(snapshot):
                status, why = Status.UNKNOWN, ["Discovery inventory or required metadata is incomplete"]
            elif missing[identity]:
                status, why = Status.BLOCKED_DEPENDENCY, missing[identity]
            elif identity in cyclic:
                status, why = Status.BLOCKED_DEPENDENCY, ["Dependency cycle retained; no edge was dropped"]
            elif previous_item and previous_item.pull_heads != tuple(sorted(set(heads[identity]))):
                status, why = Status.UNKNOWN, ["Linked PR HEADs/links changed; prior evidence is historical and requires reassessment"]
            elif review is None:
                status, why = Status.NEEDS_SPEC, ["Independent current scope/acceptance assessment is missing or unverified", *issue.notices]
            elif review.conflicts or review.specification != "KNOWN" or not review.scope.strip() or not review.acceptance or tentative[identity]:
                status, why = Status.NEEDS_SPEC, list(review.conflicts) + tentative[identity] + ["Scope/acceptance or inferred relationships require clarification"]
            elif review.completed:
                status, why = Status.DONE, ["Independently verified current product disposition; forge closure alone was insufficient"]
            elif review.duplicate_of is not None:
                status, why = Status.BLOCKED_DEPENDENCY, ["Confirmed duplicate/superseded task; canonical work is retained separately"]
            elif review.policy != "KNOWN" or not review.policy_references:
                status, why = Status.BLOCKED_OPERATOR, ["Required external policy knowledge/decision missing; Git permissions remain UNKNOWN"]
            elif issue.state == "closed":
                status, why = Status.UNKNOWN, ["Closed issue has no verified accepted disposition"]
            elif review.active_prs:
                current = {p.identity for p in linked[identity] if p.state == "open" and p.head_sha is not None}
                if set(review.active_prs) <= current:
                    status, why = Status.IN_PROGRESS, ["Independently confirmed linked open PR at observed HEAD; no new task proposed"]
                else:
                    status, why = Status.UNKNOWN, ["Assessed active PR is absent, closed or lacks its exact HEAD"]
            if identity in live_progress:
                record = live_progress[identity]
                task = json_value(record.task_json.encode(), 65536)
                pending = [j for j in task["assignments"].values() if j["status"] == "pending"]
                current_heads = {sha for _, sha in heads[identity]}
                if snapshot is not None:
                    current_heads.add(snapshot.repository.checkout_sha)
                if pending:
                    if status == Status.DONE:
                        status, why = Status.UNKNOWN, ["Disposition conflicts with a retained live assignment"]
                    elif status == Status.READY and all(j["source_revision"] in current_heads for j in pending):
                        status, why = Status.IN_PROGRESS, ["Current M1 assignment retained at exact observed revision; no duplicate task"]
                    elif status != Status.IN_PROGRESS:
                        status, why = Status.UNKNOWN, why + ["Live assignment preserved pending current-context reconciliation"]
            elif previous_item and any(j.get("status") == "pending" for record in previous_item.progress
                    for j in json_value(record.task_json.encode(), 65536).get("assignments", {}).values()):
                status, why = Status.UNKNOWN, ["Previously live assignment retained; current M1 observation is required before proposing new work"]
            if status == Status.READY:
                why = ["Verified bounded scope, known external policies and observed prerequisites; proposal only"]
            statuses[identity], reasons[identity] = status, why
        # Resolve readiness to a fixed point. DONE is the only accepted
        # prerequisite disposition; no FAIL/SKIP/UNKNOWN or open PR is a PASS.
        for _ in range(len(graph)):
            changed = False
            for identity in sorted(graph):
                if statuses[identity] in {Status.READY, Status.IN_PROGRESS, Status.DONE} and any(statuses[d] != Status.DONE for d in graph[identity]):
                    statuses[identity] = Status.BLOCKED_DEPENDENCY
                    reasons[identity] = ["Explicit prerequisite has no verified DONE disposition"]
                    changed = True
            if not changed:
                break
        # Topological order includes only nodes whose internal prerequisites can
        # be ordered. Cycles and their dependants remain explicitly unordered.
        remaining, order = {i: set(d) for i, d in graph.items()}, []
        while remaining:
            available = sorted(i for i, deps in remaining.items() if not deps)
            if not available:
                break
            order.extend(available)
            for identity in available:
                del remaining[identity]
            for deps in remaining.values():
                deps.difference_update(available)
        candidates = []
        for identity in sorted(observations):
            prior = old.get(identity)
            progress = _retain(prior.progress if prior else (), (live_progress[identity],) if identity in live_progress else (), 8)
            retained_reviews = _retain(prior.reviews if prior else (), (review_map[identity],) if identity in review_map else (), 8)
            head_history = tuple(sorted(set((prior.head_history + prior.pull_heads if prior else ()) + tuple(heads[identity])), key=lambda p: (p[0], p[1] or "")))
            history = tuple(sorted(set((prior.observation_history if prior else ()) + (digest(observations[identity]),))))
            require(len(head_history) <= 64 and len(history) <= 8, "Observation evidence capacity exhausted; explicit disposition required")
            repo = snapshot_map[identity].repository if identity in snapshot_map else prior.repository
            candidates.append(Candidate(identity, observations[identity], repo, statuses[identity], tuple(reasons[identity]),
                tuple(sorted(graph[identity])), tuple(sorted(set(heads[identity]))), progress, retained_reviews, identity in snapshot_map,
                head_history, history))
        if cycles:
            diagnostics.append("Cycles retained; track is not a complete DAG")
        if remaining:
            diagnostics.append("Cyclic tasks and their dependants are not in the proposed order")
        if any(not complete_snapshot(s) for s in snapshots):
            diagnostics.append("Selected repository inventory/metadata is incomplete; no readiness is assumed")
        titles = {}
        for identity, issue in observations.items():
            titles.setdefault(issue.title.strip().casefold(), []).append(identity)
        if any(len(ids) > 1 for title, ids in titles.items() if title):
            diagnostics.append("Identical titles observed; independent scope assessments must distinguish duplicates from separate tasks")
        result = Track(tuple(sorted(snapshots, key=lambda s: s.repository.id)), tuple(candidates), tuple(order), cycles,
                       tuple(diagnostics), digest(previous) if previous else None)
        validate_track(result)
        return result
