"""Version-observed, separately authorized, non-retrying existing ticket edits.

GitHub issue edits have no native compare-and-swap. An independently approved
OBSERVED_VERSION envelope is mandatory; ATOMIC_VERSION is unsupported.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import os

from .discovery import complete_snapshot
from .discovery_schema import digest, typed
from .discovery_types import Identity
from .execution_policy import ReservedSafety, policy_task
from .execution_privacy import credential_shaped
from .errors import Conflict
from .guard_schema import requirement_id
from .guard_types import Action, ActionKind, Observation, Outcome, Permit, Requirement, data
from .network_git import GitHubCAS
from .network_http import GitHubHTTPTransport
from .policy_types import Effect, Operation, Qualifications, TicketEditRequest
from .schema import encode, key, require
from .storage import locked, sync_directory
from .ticket_http_child import validate_request
from .ticket_preparation import (_receipt, _fresh, addition_subject, change_digest, original_scope_subject,
    preparation_subject, validate_proposal)
from .ticket_types import ChangeKind, DependencyEdit


class GitHubTicketHTTPTransport(GitHubHTTPTransport):
    permissions = (("issues", "write"), ("metadata", "read"))
    validator = staticmethod(validate_request)
    child = "ticket_http_child.py"


class TicketPublisher:
    """Uses actual M1/M2/M3; raw reviewed diffs stay in the private archive.

    The external authority must authenticate ticket/edit and separately
    ticket/observed-version (not a broad issues-write or merge delegation).
    Each effect is irreversible once delivery becomes uncertain. A fresh M4
    observation may reconcile it; an absent write is never resubmitted.
    """
    def __init__(self, conductor, admission, service, *, envelope="OBSERVED_VERSION"):
        from .conductor import Conductor
        require(type(conductor) is Conductor and type(service) is GitHubCAS
                and service.target.memory_id == conductor.memory.config.identity
                and admission.identity.repository_id == service.target.memory_id, "Actual pinned ticket execution ports required")
        self.c, self.admission, self.service, self.envelope = conductor, admission, service, envelope
        self.service.bind_control(conductor.memory.control)

    def _current(self, preparer):
        # The preparer may hold the frozen snapshots used by an independently
        # reviewed subject. Effect observations must use the live M4 service.
        track = self.c.readiness.observe()
        require(all(complete_snapshot(s) for s in track.snapshots), "Complete native dependency inventory required")
        rows = [candidate for candidate in track.candidates if candidate.identity == self.admission.identity]
        require(len(rows) == 1, "Ticket missing or ambiguous")
        return track, rows[0]

    def _policy(self, permit, request):
        c, admission = self.c, self.admission
        safety = ReservedSafety(c.guard, permit)
        project = c._project(admission)
        provider = project.policy_factory(admission, safety)
        provider.safety = safety
        from .git import value
        task = policy_task(c.memory, admission, permit.decision.baseline.requirement_id,
                           value(project.root, "symbolic-ref", "HEAD"))
        plan = provider.plan(task, request)
        authorization = project.policy_authorizer.authorize(plan, Qualifications())
        require(provider.decide(plan, authorization).effect == Effect.ALLOW, "M3 ticket edit refused")
        return provider, plan, authorization

    def _authorize(self, inputs, track, preparer):
        original = preparer.archive.original(inputs.scope.original_reference)
        require(original.repository.name.lower() == (self.service.target.owner + "/" + self.service.target.name).lower()
                and original.repository.url.lower() == self.service.target.endpoint.lower(), "Frozen repository differs from pinned native ticket target")
        validate_proposal(original, inputs.scope, inputs.proposal)
        now = self.c.clock()
        excluded = (*original.issue.authors, inputs.review.preparer)
        require(original.issue.identity == self.admission.identity and inputs.proposal.original_reference == inputs.scope.original_reference
                and _receipt(inputs.scope.evidence, preparer.authority, "ticket/original-scope", original_scope_subject(inputs.scope), excluded)
                and _fresh(inputs.review.observed_at, inputs.review.expires_at, now)
                and _receipt(inputs.review.evidence, preparer.authority, "ticket/preparation",
                    preparation_subject(original, inputs.scope, inputs.proposal, inputs.review, track), excluded),
                "Independent original scope and exact ticket diff review required")
        require(all(change.kind != ChangeKind.UNKNOWN for change in inputs.proposal.changes), "Unclassified ticket change refused")
        for change in inputs.proposal.changes:
            if change.kind == ChangeKind.ADDITION:
                approval = next((a for a in inputs.additions if a.change_id == change.id), None)
                require(approval is not None and approval.original_reference == inputs.scope.original_reference
                        and approval.change_digest == change_digest(change) and _fresh(approval.observed_at, approval.expires_at, now)
                        and _receipt(approval.evidence, preparer.authority, "ticket/scope-addition", addition_subject(approval)),
                        "Specific external scope-addition approval required")
        require(self.envelope == "OBSERVED_VERSION", "UNSUPPORTED: native ticket API has no atomic version condition")
        return original

    def publish(self, inputs, *, track, preparer, dependency_edits=()):
        c, admission = self.c, self.admission
        observed = c.journal.inspect()
        require(observed["local_owner"] and observed["state"]["execution"]["schema_version"] == 3,
                "Current explicitly upgraded M1 owner required")
        generation = observed["state"]["generation"]
        original = self._authorize(inputs, track, preparer)
        _, _, _, approved_dependencies = validate_proposal(original, inputs.scope, inputs.proposal)
        require(preparer.policy.inspect_repository().digest == inputs.proposal.policy_digest,
                "Ticket proposal project policy changed")
        require(type(dependency_edits) is tuple and len(dependency_edits) <= 16
                and all(type(edge) is DependencyEdit and type(edge.database_id) is int and edge.database_id > 0
                        and type(edge.add) is bool and edge.dependency.repository_id == admission.identity.repository_id
                        and edge.dependency != admission.identity for edge in dependency_edits), "Bounded existing native edges required")
        require(len({edge.dependency for edge in dependency_edits}) == len(dependency_edits), "Duplicate dependency edit")
        require(all((edge.dependency in approved_dependencies) == edge.add for edge in dependency_edits),
                "Native edge update changes approved dependency meaning")
        diff = {change.field.lower(): change.after for change in inputs.proposal.changes if change.field in {"TITLE", "BODY"}}
        base = f"/repos/{self.service.target.owner}/{self.service.target.name}"
        candidate = next((v for v in track.candidates if v.identity == admission.identity), None)
        require(candidate is not None and candidate.issue.revision == inputs.proposal.expected_issue_revision,
                "Ticket version changed before preparation effect")
        number = candidate.issue.number
        operations = [("PATCH", base + f"/issues/{number}", diff, {"fields": diff})] if diff else []
        for edge in dependency_edits:
            operations.append(("POST" if edge.add else "DELETE", base + f"/issues/{number}/dependencies/blocked_by"
                + ("" if edge.add else "/" + str(edge.database_id)), {"issue_id": edge.database_id} if edge.add else None,
                {"edge": data(edge)}))
        require(operations and len(operations) <= 16 and not credential_shaped(data(inputs)), "Bounded non-sensitive exact ticket proposal required")
        bundle = {"original": inputs.scope.original_reference, "inputs": data(inputs), "edges": [data(edge) for edge in dependency_edits],
                  "operations": operations, "envelope": self.envelope, "track": data(track)}
        with locked(preparer.archive.directory):
            reference = "ticket-effect:" + preparer.archive._put("effect-", bundle)
        subject = digest({"repository": admission.identity.repository_id, "issue": data(admission.identity), "bundle": bundle})
        c._grant("ticket/edit", subject, context=bundle)
        c._grant("ticket/observed-version", subject, context={"bundle": bundle, "limitation": "GET/compare/write is not atomic"})
        if dependency_edits:
            c._grant("ticket/dependency-conservation", subject, context={"original": data(original), "bundle": bundle,
                "approved_dependencies": [data(identity) for identity in approved_dependencies], "track": data(track)})
        requirement = Requirement("ticket-preparation", digest(admission.identity), ("ticket-effect-observed",))
        rid = requirement_id(requirement.contract, requirement.gate)
        if key(admission.task_id) not in c.memory.inspect()["tasks"]:
            c.memory.add_task(admission.task_id, admission.expected_revision)
        if rid not in c.journal.inspect()["state"]["progress_guard"]["requirements"]:
            receipt = c._grant("admission", c.guard.admission_subject(admission.task_id, requirement))
            c.guard.register(admission.task_id, requirement, receipt)
        expected = inputs.proposal.expected_issue_revision
        for index, (method, path, body, effect) in enumerate(operations):
            effect_id = digest({"bundle": digest(bundle), "index": index, "repository": admission.identity.repository_id})
            row = c.journal.inspect()["state"]["execution"]["ticket_effects"].get(effect_id)
            current_track, current = self._current(preparer)
            if row is not None and row["status"] == "OBSERVED":
                require(row["generation"] == generation, "Stale observed ticket generation")
                self._retained_observation(preparer.archive, effect_id, row)
                if not self._finish(row, typed(Permit, row["permit"]), rid, row["receipt"]):
                    return "BLOCKED"
                expected = row["observed_revision"]
                continue
            if row is None:
                require(current.issue.revision == expected, "Ticket version changed before effect")
                _, _, item = c.guard._snapshot(admission.task_id, rid)
                if item["active"] is not None:
                    require(item["active"]["action"]["actor"] == "conductor:ticket-effect"
                            and item["active"]["action"]["hypothesis"] == effect_id, "Unreconciled ticket reservation")
                    permit = Permit(item["active"]["id"], c.guard._decision(rid, *c.guard._snapshot(admission.task_id, rid)))
                else:
                    permit = c.guard.begin(admission.task_id, rid, Action("conductor:ticket-effect", ActionKind.CHECK,
                        effect_id, "Observe this exact authorized existing-ticket change", seconds=min(300, admission.seconds)))
                pending = [dict(a, assignment_id=aid) for aid, a in c.memory.inspect()["tasks"][key(admission.task_id)]["assignments"].items()
                           if a["status"] == "pending" and a["worker"] == "ticket:" + effect_id]
                require(len(pending) <= 1, "Duplicate ticket assignments")
                assignment = pending[0] if pending else c.memory.assign(admission.task_id, "ticket:" + effect_id)
                request = TicketEditRequest(Operation.TICKET_EDIT, issue_id=admission.identity.issue_id, number=number,
                    issue_revision=expected, edit_reference=reference, edit_digest=digest(effect), envelope=self.envelope)
                row = {"task_id": admission.task_id, "generation": generation, "requirement": rid, "permit": data(permit),
                    "request": data(request), "reference": reference, "status": "PREPARED", "observed_revision": None,
                    "receipt": "ticket:pending", "assignment": assignment["assignment_id"]}
                c.journal.change(lambda execution, state, tasks: execution["ticket_effects"].update({effect_id: row}))
            require(row["generation"] == generation and row["reference"] == reference, "Stale ticket effect generation")
            permit, request = typed(Permit, row["permit"]), typed(TicketEditRequest, row["request"])
            if row["status"] == "PREPARED":
                require(current.issue.revision == expected, "Ticket changed at dispatch")
                self._policy(permit, request)
                identity = self.service.request("GET", base)
                live = self.service.request("GET", base + f"/issues/{number}")
                require(identity.get("node_id") == self.service.target.node_id and identity.get("id") == self.service.target.database_id
                        and live.get("node_id") == admission.identity.issue_id and live.get("number") == number,
                        "Immutable GitHub repository/issue identity changed")
                if method != "PATCH":
                    edge = dependency_edits[index - (1 if diff else 0)]
                    dependency = next((v.issue for v in current_track.candidates if v.identity == edge.dependency), None)
                    require(dependency is not None, "Dependency identity missing from complete inventory")
                    live_dependency = self.service.request("GET", base + f"/issues/{dependency.number}")
                    require(live_dependency.get("node_id") == edge.dependency.issue_id
                            and live_dependency.get("id") == edge.database_id,
                            "Native dependency database/node identity differs")
                # Recheck actual complete M4 version after independent transport
                # reads. This remains observed-version, never a CAS guarantee.
                _, checked = self._current(preparer)
                require(checked.issue.revision == expected, "Ticket changed after authorization reads")
                self._authorize(inputs, track, preparer)
                c._ownership(generation)
                provider, plan, authorization = self._policy(permit, request)
                require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Fresh ticket policy refused")
                c._grant("ticket/edit", subject, context=bundle)
                c._grant("ticket/observed-version", subject, context=bundle)
                claim = c.memory.control / ("ticket-intent-" + effect_id + ".json")
                try:
                    fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                except OSError:
                    raise Conflict("UNKNOWN: consumed ticket intent; observation required") from None
                with os.fdopen(fd, "wb") as stream:
                    stream.write(encode({"effect": effect_id, "generation": generation, "request": digest(request)}))
                    stream.flush(); os.fsync(stream.fileno())
                sync_directory(c.memory.control)
                c.journal.change(lambda execution, state, tasks: execution["ticket_effects"][effect_id].update(status="SUBMITTED"))
                try:
                    c._ownership(generation)
                    self._authorize(inputs, track, preparer)
                    c._grant("ticket/edit", subject, context=bundle)
                    c._grant("ticket/observed-version", subject, context=bundle)
                    _, checked = self._current(preparer)
                    require(checked.issue.revision == expected, "Ticket changed at final effect boundary")
                    self._policy(permit, request)
                    self.service.request(method, path, body)
                except Exception:
                    # Includes DELETE's native 204: only the following full M4
                    # observation may establish the actual state, not this error.
                    pass
            fresh_track, fresh = self._current(preparer)
            if method == "PATCH":
                present = all(getattr(fresh.issue, name) == value for name, value in body.items())
            else:
                edge = dependency_edits[index - (1 if diff else 0)]
                native = [relation for relation in fresh.issue.relations
                          if relation.kind == "BLOCKED_BY" and relation.confidence == "NATIVE"]
                present = any(relation.target.issue_id == edge.dependency.issue_id for relation in native) == edge.add
            status = "OBSERVED" if present and not self.service.unconfirmed_contexts() else "UNKNOWN"
            receipt = self._observation(preparer.archive, effect_id, fresh_track)
            c.journal.change(lambda execution, state, tasks: execution["ticket_effects"][effect_id].update(
                status=status, observed_revision=fresh.issue.revision if present else None, receipt=receipt))
            if status != "OBSERVED":
                return "UNKNOWN"
            # Retained canonical result makes a stopped reply/restart idempotent.
            if not self._finish(row, permit, rid, receipt):
                return "BLOCKED"
            expected = fresh.issue.revision
        return "PREPARING"  # fresh complete DAG + independently reviewed packet required

    def _finish(self, row, permit, rid, receipt):
        c, task_id = self.c, self.admission.task_id
        state, task, item = c.guard._snapshot(task_id, rid)
        if item["active"] is not None:
            c.guard.observe(task_id, rid, permit, Observation(Outcome.PASS, (receipt,), tuple(item["unresolved"])))
        assignment = c.memory.inspect()["tasks"][key(task_id)]["assignments"][row["assignment"]]
        envelope = {"schema_version": 1, "task_key": key(task_id), "assignment_id": row["assignment"],
                "generation": row["generation"], "worker": assignment["worker"], "source_revision": assignment["source_revision"],
                "result": {"outcome": "PASS", "summary": "Observed the authorized ticket effect", "evidence": [receipt]}}
        from .config import load_json
        inbox = c.memory.path / "inbox" / (key(row["assignment"]) + ".json")
        if inbox.exists():
            require(load_json(inbox) == envelope, "Conflicting immutable ticket delivery")
        if assignment["status"] == "pending":
            if not inbox.exists():
                c.memory.deliver(envelope)
            c.memory.accept(row["assignment"])
        else:
            require(assignment["result"] == envelope["result"], "Conflicting accepted ticket result")
            if inbox.exists():
                with locked(c.memory.control):
                    c.memory._start()
                    require(load_json(inbox) == envelope, "Ticket inbox changed")
                    inbox.unlink(); sync_directory(inbox.parent)
        from .guard_types import DecisionKind
        return c.guard.inspect(task_id, rid).kind == DecisionKind.ALLOW

    def _observation(self, archive, effect_id, track):
        with locked(archive.directory):
            return "ticket-observation:" + archive._put("effect-observation-", {"effect": effect_id,
                "track": data(track), "transport_stopped": not self.service.unconfirmed_contexts()})

    def _retained_observation(self, archive, effect_id, row):
        from .discovery_schema import json_value, validate_track
        from .discovery_types import Track
        from .policy_schema import fingerprint
        require(row["reference"].startswith("ticket-effect:"), "Missing retained exact ticket proposal")
        bundle_id = row["reference"].split(":", 1)[1]
        fingerprint(bundle_id)
        bundle = json_value(archive._read(archive.directory / ("effect-" + bundle_id + ".json")), 1048576)
        require(digest(bundle) == bundle_id, "Retained ticket proposal differs")
        require(row["receipt"].startswith("ticket-observation:"), "Missing actual retained ticket observation")
        identity = row["receipt"].split(":", 1)[1]
        fingerprint(identity)
        observed = json_value(archive._read(archive.directory / ("effect-observation-" + identity + ".json")), 1048576)
        require(digest(observed) == identity and observed["effect"] == effect_id and observed["transport_stopped"] is True,
                "Ticket observation/confirmed stop differs")
        track = typed(Track, observed["track"])
        validate_track(track)
        require(all(complete_snapshot(s) for s in track.snapshots) and any(c.identity == self.admission.identity
                and c.issue.revision == row["observed_revision"] for c in track.candidates), "Observed ticket version evidence missing")

    def recover(self, *, preparer):
        """Reconcile retained canonical effects before rebuilding any packet.

        No new proposal/version can hide an older uncertain write. Reads do not
        require reviving expired edit authority; a PREPARED effect without a
        consumed claim can use its original, still-authorized publication path.
        """
        from .autonomous_track import PreparationInputs
        from .discovery_types import Track
        from .discovery_schema import json_value
        c = self.c
        observed = c.journal.inspect()
        require(observed["local_owner"], "Current M1 owner required for ticket recovery")
        rows = observed["state"]["execution"]["ticket_effects"]
        for effect_id, row in rows.items():
            if row["task_id"] != self.admission.task_id and row["request"]["issue_id"] != self.admission.identity.issue_id:
                continue
            require(row["task_id"] == self.admission.task_id, "Ticket identity already has a different canonical task binding")
            if row["generation"] != observed["state"]["generation"]:
                assignment = c.memory.inspect()["tasks"][key(self.admission.task_id)]["assignments"].get(row["assignment"])
                require(row["status"] == "OBSERVED" and assignment is not None and assignment["status"] == "accepted"
                        and assignment["result"]["evidence"] == [row["receipt"]], "Reconcile unfinished ticket effects before generation adoption")
                from .guard_types import DecisionKind
                require(c.guard.inspect(self.admission.task_id, row["requirement"]).kind == DecisionKind.ALLOW,
                        "Historical preparation guard stop remains binding")
                self._retained_observation(preparer.archive, effect_id, row)
                continue
            reference = row["reference"]
            require(reference.startswith("ticket-effect:"), "Invalid private ticket effect reference")
            fingerprint = reference.split(":", 1)[1]
            from .policy_schema import fingerprint as validate_fingerprint
            validate_fingerprint(fingerprint)
            bundle = json_value(preparer.archive._read(preparer.archive.directory / ("effect-" + fingerprint + ".json")), 1048576)
            require(digest(bundle) == fingerprint, "Ticket effect evidence hash differs")
            index = next((i for i in range(len(bundle["operations"])) if digest({"bundle": digest(bundle),
                "index": i, "repository": self.admission.identity.repository_id}) == effect_id), None)
            require(index is not None, "Canonical ticket effect missing from retained proposal")
            if row["status"] == "OBSERVED":
                self._retained_observation(preparer.archive, effect_id, row)
                if not self._finish(row, typed(Permit, row["permit"]), row["requirement"], row["receipt"]):
                    return False
                continue
            claim = c.memory.control / ("ticket-intent-" + effect_id + ".json")
            if row["status"] == "PREPARED" and not claim.exists():
                inputs = typed(PreparationInputs, bundle["inputs"])
                result = self.publish(inputs, track=typed(Track, bundle["track"]), preparer=preparer,
                    dependency_edits=tuple(typed(DependencyEdit, edge) for edge in bundle["edges"]))
                return result == "PREPARING"
            track, current = self._current(preparer)
            method, path, body, effect = bundle["operations"][index]
            if method == "PATCH":
                present = all(getattr(current.issue, name) == value for name, value in body.items())
            else:
                edge = typed(DependencyEdit, effect["edge"])
                present = any(r.kind == "BLOCKED_BY" and r.confidence == "NATIVE" and r.target.issue_id == edge.dependency.issue_id
                    for r in current.issue.relations) == edge.add
            if not present or self.service.unconfirmed_contexts():
                return False
            receipt = self._observation(preparer.archive, effect_id, track)
            c.journal.change(lambda execution, state, tasks: execution["ticket_effects"][effect_id].update(
                status="OBSERVED", observed_revision=current.issue.revision, receipt=receipt))
            if not self._finish(row, typed(Permit, row["permit"]), row["requirement"], receipt):
                return False
        return True
