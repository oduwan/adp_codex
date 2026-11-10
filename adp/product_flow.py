"""Finite PR/check/review/merge/report steps over the actual M5 Conductor.

There is no worker loop, enrollment, CI runner or second canonical journal here.
The trusted controller selects individual steps and supplies external authorities.
"""
from __future__ import annotations

from dataclasses import replace

from .discovery_schema import digest, typed
from .discovery_types import Status
from .execution_policy import ReservedSafety
from .execution_privacy import credential_shaped
from .execution_types import Role
from .github_product import DelegationProfile, GitHubProductForge, delegation_subject
from .git import value
from .guard_types import Attestation, Outcome, Permit, data
from .policy_schema import fresh
from .policy_types import Operation, ProjectCheck, ProjectQualifications, Qualifications, Request, Review
from .project_validation import ProjectValidation
from .project_validation_types import EvidenceGate, Phase, PullIdentity
from .schema import key, require
from .ticket_preparation import (TicketPreparer, _receipt, addition_subject, change_digest,
    original_scope_subject, preparation_subject, validate_proposal)
from .ticket_types import OriginalScope, PreparationReview, Proposal, ScopeAdditionApproval, ChangeKind


class PreparedScope:
    """Consume accepted #22 artifacts and reauthenticate original scope.

    This checks the existing preparer's proof; it does not interpret new prose,
    change acceptance or turn a preparation packet into execution permission.
    """
    def __init__(self, preparer, packet_reference):
        require(type(preparer) is TicketPreparer, "Use the accepted ticket preparer")
        self.preparer, self.packet_reference = preparer, packet_reference

    def verify(self, admission, candidate, revision, *, initial=False, completed=False):
        preparer = self.preparer
        packet = preparer.archive.packet(self.packet_reference)
        original = preparer.archive.original(packet.original_reference)
        proof = preparer.archive.preparation(packet.preparation_reference)
        scope, proposal, review = (typed(t, proof[n]) for t, n in
            ((OriginalScope, "scope"), (Proposal, "proposal"), (PreparationReview, "review")))
        from .discovery_types import Track
        track = typed(Track, proof["track"])
        clauses, paths, checks, dependencies = validate_proposal(original, scope, proposal)
        excluded = (*original.issue.authors, review.preparer)
        now = preparer.clock()
        require(_receipt(scope.evidence, preparer.authority, "ticket/original-scope", original_scope_subject(scope), excluded)
                and (not initial or fresh(review.observed_at, review.expires_at, now))
                and proof["subject"] == packet.preparation_digest == preparation_subject(original, scope, proposal, review, track)
                and _receipt(review.evidence, preparer.authority, "ticket/preparation", proof["subject"], excluded),
                "Original preparation authority is missing or stale")
        additions = {a.change_id: a for a in (typed(ScopeAdditionApproval, a) for a in proof["additions"])}
        for change in proposal.changes:
            if change.kind == ChangeKind.ADDITION:
                approval = additions.get(change.id)
                require(approval is not None and approval.original_reference == scope.original_reference
                    and approval.change_digest == change_digest(change)
                    and (not initial or fresh(approval.observed_at, approval.expires_at, now))
                    and _receipt(approval.evidence, preparer.authority, "ticket/scope-addition", addition_subject(approval)),
                    "Specific external scope-addition approval required")
        frozen = [c for c in track.candidates if c.identity == admission.identity]
        require(len(frozen) == 1 and packet.identity == admission.identity == original.issue.identity
                and packet.prepared_issue_revision == frozen[0].issue.revision
                and (not initial or candidate.issue.revision == packet.prepared_issue_revision)
                and (candidate.issue.title, candidate.issue.body) == (frozen[0].issue.title, frozen[0].issue.body)
                and candidate.status in ((Status.READY, Status.IN_PROGRESS, Status.DONE) if completed else (Status.READY, Status.IN_PROGRESS))
                and admission.product_goal == packet.goal == scope.goal and tuple(admission.allowed_paths) == tuple(paths) == packet.allowed_paths
                and tuple(admission.requirement.acceptance) == tuple(c.text for c in clauses if c.kind == "ACCEPTANCE")
                and packet.clauses == clauses and packet.checks == checks and packet.dependencies == dependencies,
                "Execution differs from the original admitted preparation scope")
        require(not initial or packet.base_sha == revision == admission.expected_revision,
                "Initial preparation source differs")
        return packet


class GitHubProductFlow:
    """Individually invocable transitions; every effect uses M5's actual journal."""
    def __init__(self, conductor, scope, validation_factory, delegation_factory):
        from .conductor import Conductor
        require(type(conductor) is Conductor and type(scope) is PreparedScope, "Actual Conductor and prepared scope required")
        self.conductor, self.scope = conductor, scope
        self.validation_factory, self.delegation_factory = validation_factory, delegation_factory

    def authorize_scope(self, admission, candidate, revision, *, initial=False, completed=False):
        packet = self.scope.verify(admission, candidate, revision, initial=initial, completed=completed)
        # Immutable preparation proves the admitted original. A fresh external
        # authority assesses the current observed context, including harmless PR
        # link/comment changes, without treating that historical proof as a grant.
        self.conductor._grant("github-product/scope", digest({"original": packet.original_reference,
            "preparation": packet.preparation_reference, "current_issue": data(candidate.issue), "revision": revision,
            "goal": admission.product_goal, "acceptance": admission.requirement.acceptance,
            "paths": admission.allowed_paths, "checks": packet.checks}),
            context={"packet": data(packet), "current_issue": data(candidate.issue)})
        return packet

    def reobserve_completed(self, admission):
        """Validate current disposition without replaying historical creation."""
        c = self.conductor
        task, project, flow = c._task(admission), c._project(admission), self._flow(admission)
        if task["kind"] == "INTERNAL":
            require(task["review"] is not None and task["review"]["revision"] == task["revision"], "Internal acceptance is missing")
            return
        require(flow["pull"] is not None and task["review"] is not None and task["review"]["revision"] == task["revision"],
                "Completed product lacks current exact review/PR")
        actions = c.journal.inspect()["state"]["execution"]["actions"]
        creation = next(a for a in actions.values() if a["task_key"] == key(admission.task_id) and a["operation"] == Operation.PR)
        require(project.forge.pull(flow["pull"], revision=task["revision"], source_ref=task["source_ref"],
            base_ref=creation["payload"]["base_ref"]) is not None, "Completed current PR head/ref/identity changed")
        if flow["merge_result"] is not None:
            merge_id, merge = next((k, a) for k, a in actions.items() if a["task_key"] == key(admission.task_id) and a["operation"] == Operation.MERGE)
            observed = c._observe_action(project, merge_id, merge)
            require(observed.status == "PRESENT" and observed.revision == flow["merge_result"], "Completed merge result is unproven")
        else:
            require(project.git_port.remote_revision(task["source_ref"]) == task["revision"], "Current published source changed")
        for action_id, action in actions.items():
            if action["task_key"] == key(admission.task_id) and action["operation"] == Operation.REPORT:
                observed = c._observe_action(project, action_id, action)
                require(observed.status == "PRESENT" and observed.revision == task["revision"], "Completed product report changed")

    def _context(self, admission, job, generation, *, reserved=True):
        c = self.conductor
        c._ownership(generation)
        candidate = c._refresh_issue(admission)
        task = c._task(admission)
        project = c._project(admission)
        require(type(project.forge) is GitHubProductForge, "Select the journal-backed qualified product forge")
        project.forge.service._check_stop()
        packet = self.authorize_scope(admission, candidate, task["revision"])
        require(packet.repository.name.lower() == project.forge.repository.lower()
                and packet.repository.url.lower() == project.forge.service.target.endpoint.lower(),
                "Prepared project differs from pinned forge target")
        require(value(project.root, "rev-parse", "HEAD") == task["revision"]
                and value(project.root, "symbolic-ref", "HEAD") == task["source_ref"]
                and not value(project.root, "status", "--porcelain", "--untracked-files=all"), "Product source changed")
        permit = typed(Permit, job["permit"])
        canonical = [j for j in task["jobs"].values() if j["request_id"] == job["request_id"]]
        require(len(canonical) == 1 and canonical[0]["generation"] == generation
                and canonical[0]["permit"] == job["permit"] and job["revision"] == task["revision"]
                and job["source_ref"] == task["source_ref"], "Current actual M1/M2 product job required")
        provider, context = c._policy(admission, permit)
        if reserved:
            ReservedSafety(c.guard, permit).observe(context)  # actual reservation, owner and deadline
        state = c.journal.inspect()["state"]["execution"]
        require(state["schema_version"] == 2, "Explicit product-flow upgrade required")
        return task, project, packet, provider, context, permit

    def _flow(self, admission):
        return self.conductor.journal.inspect()["state"]["execution"]["product_flows"][key(admission.task_id)]

    def _save(self, admission, **changes):
        self.conductor.journal.change(lambda execution, state, tasks:
            execution["product_flows"][key(admission.task_id)].update(changes))

    def bind(self, admission, job, generation):
        task, project, packet, provider, context, permit = self._context(admission, job, generation)
        subject = digest({"original": packet.original_reference, "preparation": packet.preparation_reference,
                          "goal": packet.goal, "clauses": [data(clause) for clause in packet.clauses],
                          "paths": packet.allowed_paths, "checks": packet.checks})
        old = self.conductor.journal.inspect()["state"]["execution"]["product_flows"].get(key(admission.task_id))
        if old is not None:
            require(old["scope"] == subject and old["original"] == packet.original_reference, "Frozen product scope changed")
            if old["revision"] != task["revision"]:
                self._save(admission, revision=task["revision"], gates=[], review_job=None, phase="PREPARED", merge_result=None, acceptance=None)
            return self._flow(admission)
        record = {"original": packet.original_reference, "preparation": packet.preparation_reference,
            "scope": subject, "revision": task["revision"], "phase": "PREPARED", "pull": None,
            "gates": [], "review_job": None, "delegation": "0" * 64, "merge_result": None, "acceptance": None}
        self.conductor.journal.change(lambda execution, state, tasks: execution["product_flows"].update({key(admission.task_id): record}))
        return self._flow(admission)

    def _delegation(self, admission, job, generation, operation, provider, plan):
        flow = self._flow(admission)
        profile = self.delegation_factory(admission, plan, flow["scope"])
        if profile is None and operation == Operation.MERGE:
            return None
        subject = delegation_subject(profile)
        c = self.conductor
        require(type(profile.evidence) is Attestation and profile.evidence.subject == subject
                and c.authority.verify(profile.evidence, purpose="github-product/delegation", subject=subject) is True
                and fresh(profile.observed_at, profile.expires_at, c.clock())
                and (profile.repository_id, profile.issue_id, profile.task_id, profile.iteration, profile.source_ref,
                     profile.revision, profile.policy_digest, profile.scope_digest) ==
                    (admission.identity.repository_id, admission.identity.issue_id, admission.task_id,
                     c._task(admission)["product_iteration"], plan.task.source_ref, plan.task.revision, plan.policy_digest, flow["scope"]),
                "Unverified or foreign project delegation")
        require(operation == Operation.REPORT or profile.base_ref == getattr(plan.payload, "base_ref", profile.base_ref), "Delegated base differs")
        if operation == Operation.MERGE and (profile.merge_mode == "MANUAL" or operation not in profile.operations):
            return None
        require(operation in profile.operations, "Project did not delegate this effect")
        return profile

    def authorize_effect(self, admission, job, generation, provider, plan):
        """Reauthenticate immediately after SUBMITTED and before forge dispatch."""
        profile = self._delegation(admission, job, generation, plan.request.operation, provider, plan)
        require(profile is not None, "Project merge authority is manual or absent")
        if plan.request.operation == Operation.MERGE:
            require(profile.merge_envelope == "HEAD_ATOMIC_BASE_OBSERVED"
                    and plan.payload.method in profile.methods, "Native merge envelope changed")
        return profile

    def checks(self, admission, job, generation, phase):
        self.bind(admission, job, generation)
        task, project, packet, provider, context, permit = self._context(admission, job, generation)
        provider, plan, authorization = self.conductor._authorize_policy(admission, permit, Request(Operation.VALIDATE))
        validation = self.validation_factory(provider, plan.task)
        require(type(validation) is ProjectValidation and validation.provider is provider and validation.task == plan.task,
                "Use actual #21 evidence integration bound to current M3")
        require(set(packet.checks) == set(plan.required_checks), "Original prescribed checks changed")
        if not any(check.phase == phase for check in validation.policy.checks):
            return None  # The project does not prescribe this phase.
        pull = self._flow(admission)["pull"]
        if phase == Phase.AFTER_PR:
            require(pull is not None, "Post-PR checks need the existing exact PR")
            identity = PullIdentity(pull["id"], pull["number"], pull["repository_id"])
        else:
            identity = None
        _, _, reserved = self.conductor.guard._snapshot(admission.task_id, self.conductor._requirement(admission))
        remaining = reserved["active"]["deadline"] - self.conductor.clock()
        require(remaining > 0, "Project observation exceeded actual M2 deadline")
        gate = validation.observe(phase, authorization=authorization, pull=identity, budget_ms=min(300000, remaining * 1000))
        phases = [g for g in self._flow(admission)["gates"] if g["request"]["phase"] != phase]
        phases.append(data(gate))
        status = "VALIDATED" if gate.qualified else "REQUIRES_CORRECTION" if gate.reason == "ACTIONABLE_PROJECT_FAILURE" else "PENDING_VALIDATION"
        def save(execution, state, tasks):
            current = execution["product_flows"][key(admission.task_id)]
            require(current["acceptance"] is None, "Reconcile pending acceptance before a new check observation")
            current.update(gates=phases, phase=status)
            if not gate.qualified:
                execution["tasks"][key(admission.task_id)]["review"] = None
        self.conductor.journal.change(save)
        return gate

    def qualifications(self, admission, provider, plan, *, allow_code_review=False):
        c = self.conductor
        flow, task = self._flow(admission), c._task(admission)
        validation_provider, context = provider, plan.task
        validation_plan = validation_provider.plan(context, Request(Operation.VALIDATE))
        validation = self.validation_factory(validation_provider, context)
        # Authenticate complete project phase inventory without running CI.
        from .project_validation import policy_subject
        validation._verify(validation.policy.evidence, "policy", policy_subject(validation_plan, validation.policy))
        require(set(validation_plan.required_checks) == set(plan.required_checks)
                == {check.name for check in validation.policy.checks}, "Project phase inventory differs from final M3 checks")
        required = tuple(sorted((check.name, str(check.phase)) for check in validation.policy.checks))
        checks = []
        now = c.clock()
        for raw in flow["gates"]:
            gate = typed(EvidenceGate, raw)
            require(gate.qualified and gate.request.revision == task["revision"]
                    and gate.request.generation == context.generation and gate.request.task_epoch == context.task_epoch
                    and gate.request.iteration == context.iteration, "Current complete project evidence required")
            state = validation._state(gate.request)
            require(state["last_digest"] == gate.evidence.split(":", 1)[1]
                    and fresh(state["last_observed"], state["last_observed"] + validation.policy.maximum_age, now),
                    "Project observation is stale or lacks its actual #21 receipt")
            # The signer must authenticate the actual #21 observation and policy,
            # not merely these caller-presented fields. No permissive signer exists.
            for result in gate.results:
                rule = next((r for r in validation.policy.checks if (r.name, r.phase) == (result.name, gate.request.phase)), None)
                require(rule is not None and (rule.provider, rule.origin) == (result.provider, result.origin)
                        and (rule.denominator is None or rule.denominator == result.denominator)
                        and (result.attempt_id is not None or rule.native_record_is_attempt), "Project check policy changed")
                check = ProjectCheck(result.name, result.revision, str(gate.request.phase), digest(gate.request),
                    gate.evidence.split(":", 1)[1], result.provider, result.origin, result.run_id, result.attempt_id,
                    str(result.status), result.denominator, result.counts, result.quarantined,
                    state["last_observed"], state["last_observed"] + validation.policy.maximum_age)
                evidence = c._grant("policy/project-check", provider.project_check_subject(plan, check),
                    context={"gate": raw, "policy": data(validation.policy), "check": data(check)})
                checks.append(replace(check, evidence=evidence))
        require({(r.name, r.phase) for r in checks} == set(required), "Every prescribed project phase must qualify")
        review = task["review"]
        if review is None and allow_code_review:
            job = task["jobs"][flow["review_job"]]
            require(job["role"] == Role.REVIEWER and job["status"] == "COMPLETE" and job["result"]["approved"], "Actual code review required")
            review = {"revision": job["revision"], "context": job["context"], "reviewer": "worker:" + job["request_id"],
                "receipt": job["receipt"], "criteria": job["result"]["criteria"], "checks": []}
        require(review is not None and review["revision"] == task["revision"], "Actual independent final exact-SHA review required")
        approved = Review(review["reviewer"], review["revision"], True, now, now + 300)
        evidence = c._grant("policy/review", provider.review_subject(plan, approved), context=review, principal=review["reviewer"])
        approved = replace(approved, evidence=evidence)
        result = ProjectQualifications(tuple(checks), (approved,), required)
        evidence = c._grant("policy/project-validation", provider.project_policy_subject(plan, result),
            context={"policy": data(validation.policy), "gates": flow["gates"]})
        return replace(result, policy_evidence=evidence)

    def draft(self, admission, job, generation):
        self.bind(admission, job, generation)
        c = self.conductor
        task, project, packet, provider, context, permit = self._context(admission, job, generation)
        if task["kind"] == "INTERNAL":
            return None
        # Only prescribed BEFORE_PR checks gate the creation stage.
        gate = self.checks(admission, job, generation, Phase.BEFORE_PR)
        if gate is not None and not gate.qualified:
            return None
        c._action(admission, job, Request(Operation.PUSH), generation,
            qualifications=lambda p, plan: self.qualifications(admission, p, plan) if plan.gated else Qualifications())
        task, project, packet, provider, context, permit = self._context(admission, job, generation)
        plan = provider.plan(context, Request(Operation.PR, summary=admission.summary))
        profile = self._delegation(admission, job, generation, Operation.PR, provider, plan)
        require(plan.payload is not None and plan.payload.draft is True, "UNSUPPORTED: product flow creates Draft PRs only")
        flow = self._flow(admission)
        if flow["pull"] is not None:
            require(project.forge.pull(flow["pull"], revision=task["revision"], source_ref=task["source_ref"],
                base_ref=profile.base_ref) is not None, "Existing PR head/base changed")
            return flow["pull"]
        observed = c._action(admission, job, plan.request, generation,
            payload_extra={"revision": task["revision"], "body": packet.goal},
            qualifications=lambda p, current: self.qualifications(admission, p, current) if current.gated else Qualifications())
        number = int(observed.reference.rsplit("/", 1)[1])
        reply = project.forge.transport.request("GET", f"/repos/{project.forge.repository}/pulls/{number}")
        require(reply.status == 200 and type(reply.body) is dict and reply.body.get("id") is not None, "Exact PR identity unavailable")
        pull = {"id": str(reply.body["id"]), "number": number, "repository_id": context.repository_id, "url": observed.reference}
        require(project.forge.pull(pull, revision=task["revision"], source_ref=task["source_ref"], base_ref=profile.base_ref) is not None,
                "Created PR identity differs")
        self._save(admission, pull=pull, phase="PENDING_VALIDATION")
        return pull

    def qualify_review(self, admission, job, generation):
        """Resume the same durable acceptance and exact M2 criterion actions."""
        c = self.conductor
        flow = self._flow(admission)
        pending = flow["acceptance"]
        if pending is None:
            self.bind(admission, job, generation)
            for phase in Phase:
                gate = self.checks(admission, job, generation, phase)
                if gate is not None and not gate.qualified:
                    return False
            task, project, packet, provider, context, permit = self._context(admission, job, generation)
            flow = self._flow(admission)
            assignment_id = next(k for k, j in task["jobs"].items() if j["request_id"] == job["request_id"])
            pending = {"job": assignment_id, "review_job": flow["review_job"], "gates": digest(flow["gates"]),
                "generation": generation, "revision": task["revision"], "receipt": "pending"}
            pending["receipt"] = "product-acceptance:" + digest(pending)
            from .execution_types import WorkerResult
            def prepared(execution, state, tasks):
                execution["product_flows"][key(admission.task_id)]["acceptance"] = pending
                current = execution["tasks"][key(admission.task_id)]["jobs"][assignment_id]
                current.update(status="OBSERVED", receipt=pending["receipt"],
                    result=data(WorkerResult(Outcome.PASS, False, (), "Qualified project evidence awaiting durable acceptance")))
            c.journal.change(prepared)
        task, project, packet, provider, context, permit = self._context(admission, job, generation, reserved=False)
        flow = self._flow(admission)
        require(pending["generation"] == generation and pending["revision"] == task["revision"]
                and pending["gates"] == digest(flow["gates"])
                and task["jobs"][pending["job"]]["request_id"] == job["request_id"], "Pending acceptance context changed")
        reviewed = task["jobs"].get(pending["review_job"])
        require(reviewed is not None and reviewed["revision"] == task["revision"] and reviewed["generation"] == generation
                and reviewed["status"] == "COMPLETE" and reviewed["role"] == Role.REVIEWER
                and reviewed["result"]["approved"] and reviewed["result"]["outcome"] == Outcome.PASS
                and set(admission.requirement.acceptance) <= set(reviewed["result"]["criteria"]),
                "Actual independent current code-review acceptance required")
        from .guard_types import Action, ActionKind, Observation, Progress, ProgressKind
        from .policy import PolicyProvider
        from .policy_adapters import M2SafetyAdapter
        principal, receipt = "worker:" + reviewed["request_id"], pending["receipt"]
        state, memory_task, item = c.guard._snapshot(admission.task_id, c._requirement(admission))
        active = item["active"]
        if active is None:
            require(item["last"] is not None and receipt in item["last"]["observation"]["evidence"]
                    and item["last"]["context"] == c.guard._context(state, memory_task),
                    "Original acceptance consumption is not authoritatively proven")
            # This is observational policy/evidence reconstruction, not an ALLOW
            # execution capability. Actual accepted M2 inspection supplies safety.
            provider = PolicyProvider(provider.adapter, sources=provider.sources, protections=provider.protections,
                authority=provider.authority, safety=M2SafetyAdapter(c.guard), clock=provider.clock)
        elif active["id"] != permit.token:
            require(active["action"]["actor"] == "conductor:criterion-observation"
                    and active["action"]["hypothesis"].startswith("criterion:")
                    and active["context"] == c.guard._context(state, memory_task), "Conflicting acceptance reservation")
            current = Permit(active["id"], c.guard._decision(c._requirement(admission), state, memory_task, item))
            provider, context = c._policy(admission, current)
        # Reauthenticate all actual retained #21 proof, its original counts,
        # current phase policy and exact independent review before local recovery.
        self.qualifications(admission, provider, provider.plan(context, Request(Operation.VALIDATE)), allow_code_review=True)
        if active is not None and active["id"] == permit.token:
            proof = None if item["approval"] is not None else Progress(ProgressKind.CORRECTION_APPROVED,
                "exact-source-reviewed", (reviewed["receipt"],))
            observation = Observation(Outcome.PASS, (reviewed["receipt"], receipt), tuple(item["unresolved"]), progress=proof)
            evidence = c._grant("progress", c.guard.progress_subject(admission.task_id, c._requirement(admission), permit, observation),
                context={"receipt": reviewed["receipt"], "principal": principal, "gates": flow["gates"]}, principal=principal) if proof else None
            c.guard.observe(admission.task_id, c._requirement(admission), permit, observation, evidence=evidence)
        for criterion in admission.requirement.acceptance:
            state, memory_task, item = c.guard._snapshot(admission.task_id, c._requirement(admission))
            if criterion not in item["unresolved"]:
                continue
            if item["active"] is not None:
                require(item["active"]["action"]["actor"] == "conductor:criterion-observation"
                        and item["active"]["action"]["hypothesis"] == "criterion:" + criterion,
                        "Interrupted criterion differs")
                reserved = Permit(item["active"]["id"], c.guard._decision(c._requirement(admission), state, memory_task, item))
            else:
                reserved = c.guard.begin(admission.task_id, c._requirement(admission), Action("conductor:criterion-observation", ActionKind.CHECK,
                    "criterion:" + criterion, "Actual project gates plus independent exact-SHA review"))
            measured = Observation(Outcome.PASS, (reviewed["receipt"], receipt), tuple(x for x in item["unresolved"] if x != criterion),
                progress=Progress(ProgressKind.REQUIREMENT_VERIFIED, criterion, (reviewed["receipt"],)))
            evidence = c._grant("progress", c.guard.progress_subject(admission.task_id, c._requirement(admission), reserved, measured),
                context={"receipt": reviewed["receipt"], "principal": principal, "gates": flow["gates"]}, principal=principal)
            c.guard.observe(admission.task_id, c._requirement(admission), reserved, measured, evidence=evidence)
        job = task["jobs"][pending["job"]]
        c._deliver(admission, pending["job"], job, Outcome.PASS)
        def accepted(execution, state, tasks):
            current = execution["tasks"][key(admission.task_id)]
            current["jobs"][pending["job"]]["status"] = "COMPLETE"
            current["review"] = {"revision": reviewed["revision"], "context": reviewed["context"], "reviewer": principal,
                "receipt": reviewed["receipt"], "criteria": reviewed["result"]["criteria"], "checks": []}
            execution["product_flows"][key(admission.task_id)].update(phase="VALIDATED", acceptance=None)
        c.journal.change(accepted)
        return True

    def merge(self, admission, job, generation):
        c = self.conductor
        self.bind(admission, job, generation)
        task, project, packet, provider, context, permit = self._context(admission, job, generation)
        if task["kind"] == "INTERNAL":
            return "INTERNAL"
        existing = [a for a in c.journal.inspect()["state"]["execution"]["actions"].values()
                    if a["task_key"] == key(admission.task_id) and a["operation"] == Operation.MERGE]
        if existing:
            observed = c._action(admission, job, Request(Operation.MERGE), generation)
            self._save(admission, phase="MERGED", merge_result=observed.revision)
            return "MERGED"
        plan = provider.plan(context, Request(Operation.MERGE))
        profile = self._delegation(admission, job, generation, Operation.MERGE, provider, plan)
        if profile is None:
            self._save(admission, phase="WAITING_HUMAN_APPROVAL")
            return "WAITING_HUMAN_APPROVAL"
        method = getattr(plan.payload, "method", None)
        if method not in ("merge", "squash") or method not in profile.methods or profile.merge_envelope != "HEAD_ATOMIC_BASE_OBSERVED":
            self._save(admission, phase="UNSUPPORTED")
            return "UNSUPPORTED"
        pull = self._flow(admission)["pull"]
        require(pull is not None, "Existing PR required")
        item = project.forge.pull(pull, revision=task["revision"], source_ref=task["source_ref"],
            base_ref=plan.payload.base_ref, expected_base=plan.payload.expected_base)
        require(item is not None, "Exact PR head/base differs from review")
        if item["draft"]:
            self._save(admission, phase="WAITING_HUMAN_APPROVAL")
            return "WAITING_HUMAN_APPROVAL"
        require(item["state"] == "open" or item["merged"], "PR is closed without merge")
        reviews = project.forge.reviews(pull, task["revision"])
        require(reviews is not None, "Project review inventory incomplete")
        # External review requirements and canonical authorship are assessed by
        # the same independent authority, over the actual provider inventory.
        c._grant("github-product/reviews", digest({"plan": data(plan), "pull": pull, "reviews": reviews,
            "independent": task["review"]}), context={"reviews": reviews, "independent": task["review"]})
        require(not any(r["commit_id"] == task["revision"] and r["state"] == "CHANGES_REQUESTED" for r in reviews),
                "Current project review requests changes")
        # Freshly observe every required phase immediately before acceptance.
        for phase in Phase:
            gate = self.checks(admission, job, generation, phase)
            if gate is not None and not gate.qualified:
                return self._flow(admission)["phase"]
        review = task["review"]
        require(review is not None, "Actual independent review required")
        review_job = next(k for k, j in task["jobs"].items() if j["role"] == Role.REVIEWER
            and j["status"] == "COMPLETE" and j["receipt"] == review["receipt"] and j["revision"] == task["revision"])
        self._save(admission, review_job=review_job)
        # A diverged base is refused; native merge needs the reviewed source tree.
        require(value(project.root, "merge-base", plan.payload.expected_base, task["revision"]) == plan.payload.expected_base,
                "Base diverged from reviewed source")
        observed = c._action(admission, job, Request(Operation.MERGE), generation,
            payload_extra={"pull": pull, "source_tree": value(project.root, "rev-parse", "HEAD^{tree}"),
                "envelope": profile.merge_envelope}, qualifications=lambda p, current: self.qualifications(admission, p, current))
        self._save(admission, phase="MERGED", merge_result=observed.revision)
        return "MERGED"

    def report(self, admission, job, generation):
        c = self.conductor
        self.bind(admission, job, generation)
        task, project, packet, provider, context, permit = self._context(admission, job, generation)
        if task["kind"] == "INTERNAL":
            return None
        flow = self._flow(admission)
        require(flow["pull"] is not None and flow["phase"] in ("MERGED", "WAITING_HUMAN_APPROVAL", "COMPLETE"),
                "No completed substantive product disposition")
        body = f"Implemented {admission.summary}\n\nProject checks and independent review qualified {task['revision']}.\n{flow['pull']['url']}"
        body += (f"\nMerged as {flow['merge_result']}." if flow["merge_result"] else "\nMerge awaits project human approval.")
        require(not credential_shaped(body), "Sensitive product summary refused")
        target = c._refresh_issue(admission, report=True).issue.url
        request = Request(Operation.REPORT, report_target=target, report_body=body)
        plan = provider.plan(context, request)
        self._delegation(admission, job, generation, Operation.REPORT, provider, plan)
        # Reporting also needs fresh complete evidence, even for manual merge.
        if flow["merge_result"] is not None:
            # A closed merged PR no longer has the pre-merge #21 query context.
            # Retain its qualified, still-fresh provenance and reobserve the
            # immutable resulting commit/parents/tree instead of inventing CI.
            actions = c.journal.inspect()["state"]["execution"]["actions"]
            merge_id, merge_action = next((k, a) for k, a in actions.items()
                if a["task_key"] == key(admission.task_id) and a["operation"] == Operation.MERGE)
            observed_merge = c._observe_action(project, merge_id, merge_action)
            require(observed_merge.status == "PRESENT" and observed_merge.revision == flow["merge_result"],
                    "Merged result is not currently proven")
        else:
            for phase in Phase:
                gate = self.checks(admission, job, generation, phase)
                require(gate is None or gate.qualified, "Product checks are not qualified for a report")
        result = c._action(admission, job, request, generation, payload_extra={"revision": task["revision"]},
            qualifications=lambda p, current: self.qualifications(admission, p, current))
        publication = digest({"repository": c.memory.config.identity, "task": admission.task_id, "iteration": task["product_iteration"]})
        action_id = next(k for k, a in c.journal.inspect()["state"]["execution"]["actions"].items()
            if a["operation"] == Operation.REPORT and a["task_key"] == key(admission.task_id))
        c.journal.change(lambda execution, state, tasks: execution["publications"].update({publication:
            {"action": action_id, "body_digest": digest(body), "reference": result.reference}}))
        self._save(admission, phase="COMPLETE" if flow["merge_result"] else "WAITING_HUMAN_APPROVAL")
        return result

    def advance(self, admission, generation):
        """One finite publication step; external waiting never launches a loop."""
        c = self.conductor
        assignment, job = c._job(admission, Role.COORDINATION, generation)
        task = c._task(admission)
        flow = c.journal.inspect()["state"]["execution"]["product_flows"].get(key(admission.task_id))
        if flow is not None and flow["acceptance"] is not None:
            self.qualify_review(admission, job, generation)
            return "VALIDATED"
        outcome = Outcome.UNKNOWN
        if task["kind"] == "INTERNAL":
            self.bind(admission, job, generation)
            if task["review"] is None:
                _, _, _, provider, context, _ = self._context(admission, job, generation)
                validation = self.validation_factory(provider, context)
                if any(check.phase == Phase.AFTER_PR for check in validation.policy.checks):
                    self._save(admission, phase="UNSUPPORTED")
                    phase = "UNSUPPORTED"  # INTERNAL cannot create a PR to obtain these checks.
                elif self.qualify_review(admission, job, generation):
                    return "VALIDATED"
                else:
                    phase = self._flow(admission)["phase"]
            else:
                phase = "COMPLETE"
        else:
            pull = self.draft(admission, job, generation)
            phase = self._flow(admission)["phase"]
            if pull is not None:
                gate = self.checks(admission, job, generation, Phase.AFTER_PR)
                if gate is None or gate.qualified:
                    if c._task(admission)["review"] is None:
                        if self.qualify_review(admission, job, generation):
                            return "VALIDATED"  # This reservation was consumed by acceptance.
                        phase = self._flow(admission)["phase"]
                    else:
                        phase = self.merge(admission, job, generation)
                        if phase in ("MERGED", "WAITING_HUMAN_APPROVAL"):
                            self.report(admission, job, generation)
                            phase = self._flow(admission)["phase"]
        outcome = Outcome.PASS if phase == "COMPLETE" else Outcome.FAIL if phase == "REQUIRES_CORRECTION" else Outcome.UNKNOWN
        job["receipt"] = "product-step:" + job["request_id"]
        from .execution_types import WorkerResult
        job["result"] = data(WorkerResult(outcome, False, (), "Observed finite product step"))
        c._deliver(admission, assignment, job, outcome)
        c._measured(admission, job, outcome)
        def finish(execution, state, tasks):
            current = execution["tasks"][key(admission.task_id)]
            current["jobs"][assignment].update(status="COMPLETE", receipt=job["receipt"], result=job["result"])
            if phase == "COMPLETE":
                current["stage"] = "COMPLETE"
            elif phase == "REQUIRES_CORRECTION":
                current.update(stage="DEVELOP", review=None)
        c.journal.change(finish)
        return phase
