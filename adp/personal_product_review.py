"""Personal product authority verifies actual local receipts, never credentials."""
from __future__ import annotations

from dataclasses import replace

from .discovery_schema import digest, typed
from .discovery_types import Issue
from .github_product import DelegationProfile, delegation_subject
from .guard_types import Observation, Permit, ProgressKind, DecisionKind, data
from .execution_policy import ReservedSafety
from .execution_types import RuntimeObservation, RuntimeStatus
from .personal_git import administration
from .personal_enrollment import governance
from .personal_authority import PersonalAuthority
from .personal_runner import PersonalCoordinator
from .policy import PolicyProvider
from .policy_types import (Operation, Plan, ProjectCheck, ProjectQualifications, Protection,
    Qualifications, RepositorySnapshot, Review, SourceClaim, SourceKind, Task)
from .project_validation import observation_subject, policy_subject
from .project_validation_types import EvidencePolicy, ObservationQuery, ProjectObservation
from .schema import require, fields, key


def original_with_own_relation(original, observed, identity, repository):
    """Strip only new, exact native links to this already verified own PR.

    This does not normalize a timestamp, source version, scope or old relation.
    The caller must authenticate the PR from its durable observed intent.
    """
    baseline = typed(Issue, original)
    added = tuple(r for r in observed.relations if r not in baseline.relations)
    require(added and all(r.kind == "PULL_REQUEST" and r.confidence == "NATIVE"
        and r.target.repository == repository and r.target.number == identity["number"]
        and r.target.issue_id == identity["node_id"] for r in added), "Original ticket has unrelated or ambiguous changes")
    retained = replace(observed, relations=tuple(r for r in observed.relations if r not in added))
    require(digest(data(retained)) == digest(original), "Original version, scope or prior evidence changed")
    return [data(r) for r in added]


class ProductCoordinator(PersonalCoordinator):
    def original_matches(self, issue):
        if super().original_matches(issue):
            self.original_relation_delta = []
            return True
        product = getattr(self, "product", None)
        require(product is not None and product.record() is not None and product.record()["pull"] is not None,
                "Only an observed own PR may explain a native relation delta")
        row = product.record()
        delta = original_with_own_relation(self.personal.intent["original"], issue, row["pull"], self.personal.plan["repository"]["name"])
        with product.service.bounded():
            remote = {r.name: r.revision for r in product.service.refs()}.get(product.target.ref)
            actions = product.journal.inspect()["state"]["execution"]["actions"].values()
            require(any(a["task_key"] == key(self.task_id) and a["operation"] == Operation.PUSH
                        and a["status"] == "OBSERVED" and a["revision"] == remote for a in actions),
                    "Native own-PR link has no confirmed source publication")
            product.pull(published_revision=remote)
        self.original_relation_delta = delta
        return True

    def verify_local_review(self):
        requirement = self.requirement("develop")
        state, task, item = self.guard._snapshot(self.task_id, requirement)
        if item["active"] is None:
            return super().verify_local_review()
        run = self.record()
        coordination = run["coordination"]
        if coordination is not None and coordination["label"].startswith("personal-report:"):
            require(callable(getattr(self.product, "report_record", None)), "Exact REPORT composition required")
            intent = self.product.report_record()
            require(intent is not None and coordination["label"] == "personal-report:" + intent["action"]
                    and intent["reservation"] == coordination["permit"] and intent["view"]["operation"] == "REPORT",
                    "Unrelated report reservation cannot reuse an approval")
            return self.reserved_code_review(typed(Permit, coordination["permit"]))
        require(coordination is not None and coordination["label"].startswith("personal-merge:")
                and coordination["requirement"] == requirement, "Only the exact active MERGE may use reserved approval")
        effect_id = coordination["label"].removeprefix("personal-merge:")
        intent = next((i for i in self.product.record()["intents"] if i["action"] == effect_id), None)
        require(intent is not None and intent["view"]["operation"] == "MERGE" and intent["view"]["merge_mode"] == "DELEGATED"
                and intent["reservation"] == coordination["permit"] and intent["requirement"] == requirement,
                "Current exact delegated MERGE reservation required")
        permit = typed(Permit, coordination["permit"])
        active = self.guard._active(state, task, item, permit.token)
        require(active["action"]["hypothesis"] == "personal:personal-merge:" + effect_id, "Unrelated original action")
        return self.reserved_code_review(permit)

    def reserved_code_review(self, permit, *, recovering=False):
        run = self.record()
        requirement = self.requirement("develop")
        state, task, item = self.guard._snapshot(self.task_id, requirement)
        self.guard._active(state, task, item, permit.token)
        self.check_administration(run)
        review = self.worker(run["code_review"])
        port = self.product.port
        require(review["purpose"] == "code" and review["request"]["revision"] == run["revision"] == task["source_revision"]
                and port._value("rev-parse", "HEAD") == run["revision"]
                and port._value("symbolic-ref", "HEAD") == "refs/heads/" + self.personal.plan["feature"]["branch"]
                and not port._value("status", "--porcelain", "--untracked-files=all"), "Exact current clean code review required")
        self.workers.actual(review, approval=True, accounted=not recovering)
        if recovering:
            assignment = task["assignments"].get(review["assignment"]["assignment_id"])
            require(review["phase"] == "ACCOUNTED" and assignment is not None
                    and assignment["status"] == "accepted" and assignment["result"] == self.workers.result(review),
                    "Prior genuine code delivery is not canonically accounted")
        current = Task(self.personal.repository_id, self.task_id, self.personal.plan["feature"]["branch"].split("/")[-1],
            task["source_revision"], "refs/heads/" + self.personal.plan["feature"]["branch"], requirement,
            state["generation"], state["progress_guard"]["task_epochs"][key(self.task_id)], task["iteration"], tuple(item["authors"]))
        safety = ReservedSafety(self.guard, permit).observe(current)
        require(safety.owns_memory is True and safety.guard.kind == DecisionKind.ALLOW
                and safety.approval == safety.guard.baseline == self.guard._baseline(requirement, state, task, item),
                "Current original M1/M2 canonical approval required")

    def resume_product_review(self, entry):
        requirement = self.requirement("product")
        state, task, item = self.guard._snapshot(self.task_id, requirement)
        if item["active"] is None:
            return None
        self.live()
        self.workers.fence()  # Every existing process must already be stopped.
        self.fresh()
        self.original_approval()
        view = entry["view"]
        require(entry["phase"] != "COMPLETE" and view["operation"] == "REVIEW"
                and self.record()["coordination"] is None
                and view["revision"] == self.revision() == task["source_revision"]
                and view["administration"] == digest(administration(self.personal.feature))
                and view["source_tree"] == self.product.port._value("rev-parse", "HEAD^{tree}")
                and digest(governance(self.personal.feature)) == self.personal.plan["governance_digest"],
                "Only this original incomplete exact-source review can recover")
        context = self.product.review_context()
        matches = [r for r in self.workers.records() if r["purpose"] == "product" and r["context"] == context]
        require(len(matches) == 1, "Original product review request/context missing or ambiguous")
        worker = matches[0]
        require(worker["phase"] in ("SUBMITTED", "STOPPED") and worker["requirement"] == requirement
                and worker["request"]["revision"] == view["revision"]
                and worker["request"]["generation"] == state["generation"]
                and worker["guard_context"] == item["active"]["context"]
                and item["active"]["action"]["hypothesis"] == "worker:" + worker["request"]["id"]
                and item["active"]["action"]["kind"] == "REVIEW"
                and self.clock() < worker["request"]["deadline"], "Unrelated or expired review reservation")
        permit = typed(Permit, worker["permit"])
        self.guard._active(state, task, item, permit.token)
        observed = self.runtime.observe(worker["request"]["id"])
        require(type(observed) is RuntimeObservation and observed.status == RuntimeStatus.COMPLETED
                and observed.stopped is True and observed.request_id == worker["request"]["id"]
                and observed.request_digest == digest(worker["request"])
                and observed.host == worker["host"] == self.runtime.host, "Existing stopped genuine review result unavailable")
        require(view["generation"] == state["generation"]
                and view["review_binding"] == self.product.review_seal(review_worker=worker),
                "Original operator-approved code/ownership seal changed")
        self.reserved_code_review(permit, recovering=True)
        # Existing execute reconciles the same immutable request and M1/M2
        # delivery; a SUBMITTED request may never be dispatched again.
        return self.workers.execute("product", context, self.personal.feature)

    def context(self, purpose):
        context = super().context(purpose)
        product = getattr(self, "product", None)
        if purpose == "develop" and product is not None and product.record() is not None and product.record()["correction"] is not None:
            context["compound_correction"] = "One Developer result, scoped staging and one local commit under the original deadline; conclude before source transition."
        return context

    @staticmethod
    def compound(row):
        return row["purpose"] == "develop" and "compound_correction" in row["context"]

    def worker_action(self, row, action):
        if self.compound(row):
            require(row["context"] == self.context("develop"), "Original prospective correction scope changed")
            return replace(action, exit_criteria=row["context"]["compound_correction"])
        return action

    def authorize_worker(self, row):
        if row["purpose"] == "product":
            require(row["context"] == self.product.review_context(), "Product review context/CI changed before dispatch")
        super().authorize_worker(row)
        if self.compound(row):
            current = self.record()
            state, task, item = self.guard._snapshot(self.task_id, row["requirement"])
            active = self.guard._active(state, task, item, row["permit"]["token"])
            require(active["action"]["exit_criteria"] == row["context"]["compound_correction"], "Compound scope was not reserved before dispatch")
            coordination = {"label": "commit:" + row["request"]["id"], "requirement": row["requirement"],
                "permit": row["permit"], "action": active["action"], "context": row["guard_context"], "sequence": item["sequence"],
                "observation": None, "next_phase": None, "check_state": None}
            require(current["coordination"] in (None, coordination), "Another original operation is reserved")
            current["coordination"] = coordination
            self.save(current)  # Before SUBMITTED/dispatch, not retroactive coalescing.

    def defer_developer_guard(self, row, observed):
        if not self.compound(row) or observed.result.outcome != "PASS":
            return False
        coordination = self.record()["coordination"]
        require(coordination is not None and coordination["permit"] == row["permit"]
                and coordination["label"] == "commit:" + row["request"]["id"], "Durable original compound accounting missing")
        state, task, item = self.guard._snapshot(self.task_id, row["requirement"])
        active = self.guard._active(state, task, item, row["permit"]["token"])
        require(self.clock() < active["deadline"] and active["action"]["exit_criteria"] == row["context"]["compound_correction"], "Compound deadline/definition changed")
        return True

    def worker_accounted(self, row):
        if self.compound(row) and row["observation"]["result"]["outcome"] != "PASS":
            current = self.record()
            require(current["coordination"] is not None and current["coordination"]["permit"] == row["permit"], "Original failed correction missing")
            current["coordination"] = None
            self.save(current)

    def _run(self):
        current = self.record()
        if current is not None and current["phase"] == "DEVELOP" and current["coordination"] is not None:
            worker = self.worker(current["coordination"]["label"].removeprefix("commit:"))
            require(self.compound(worker), "Only the exact retained compound correction can resume")
            worker = self.workers.execute("develop", worker["context"], self.personal.feature)
            current = self.record()
            current.update(developer=worker["request"]["id"], phase="STAGE" if worker["observation"]["result"]["outcome"] == "PASS" else "DEVELOP")
            self.save(current)
        return super()._run()

    def conclude(self, permit, reference, outcome="PASS", *, next_phase=None):
        current = self.record()
        coordination = current["coordination"]
        if coordination is not None and coordination["label"].startswith("commit:") and coordination["observation"] is None:
            worker = self.worker(coordination["label"].removeprefix("commit:"))
            if self.compound(worker):
                actual = self.workers.actual(worker, accounted=True)
                state, task, item = self.guard._snapshot(self.task_id, worker["requirement"])
                active = self.guard._active(state, task, item, permit.token)
                elapsed = max(actual.elapsed_seconds, self.clock() - active["started"])
                coordination["observation"] = data(Observation(outcome, (reference,), tuple(item["unresolved"]),
                    elapsed_seconds=elapsed, samples=actual.samples, payload_bytes=actual.payload_bytes))
                coordination["next_phase"] = next_phase
                self.save(current)
        return super().conclude(permit, reference, outcome, next_phase=next_phase)

    def check_stage(self):
        product = getattr(self, "product", None)
        if product is not None and product.record() is not None and product.record()["correction"] is not None:
            # #41 explicitly admits AFTER_PR evidence for unpublished commits.
            # The original scope Reviewer already refuses unsupported mandatory
            # precommit checks. Do not consume another native observation on an
            # unpublished SHA or copy the old gate to that new SHA.
            row = self.record()
            require(row["phase"] == "CHECKS" and row["coordination"] is None,
                    "Reconcile original correction checks first")
            row["phase"] = "LOCAL_DRAFT_CODE_REVIEWED"
            self.save(row)
            return
        super().check_stage()


class ProductAuthority(PersonalAuthority):
    def _validate(self, body):
        fields(body, "schema_version purpose subject kind payload principal approval generation expires_at")
        require(type(body["schema_version"]) is int and body["schema_version"] == 1, "Unsupported personal authority")
        kind = body.get("kind", "")
        if kind == "progress" and self.c.worker(body["payload"]["request_id"])["purpose"] == "product":
            row = self.c.worker(body["payload"]["request_id"])
            self.c.live()
            self.c.workers.actual(row, approval=True)
            require(row["context"] == self.c.product.review_context(), "Product acceptance review/CI is stale")
            measured = typed(Observation, body["payload"]["observation"])
            state, task, item = self.c.guard._snapshot(self.c.task_id, row["requirement"])
            require(body["approval"] == self.c.personal.intent["approval"] and body["generation"] == state["generation"]
                    and self.c.clock() < body["expires_at"] == self.c.personal.plan["window"]["expires_at"]
                    and body["purpose"] == "progress" and body["principal"] == "worker:" + row["request"]["id"]
                    and measured.progress is not None and measured.progress.kind == ProgressKind.REQUIREMENT_VERIFIED
                    and measured.progress.fact == self.c.personal.plan["criterion"]
                    and measured.progress.evidence == measured.evidence == (row["observation"]["receipt"],)
                    and measured.unresolved == (), "Actual product acceptance proof differs")
            if item["active"] is not None and item["active"]["id"] == row["permit"]["token"]:
                require(body["subject"] == self.c.guard.progress_subject(self.c.task_id, row["requirement"], typed(Permit, row["permit"]), measured), "Product progress subject differs")
            else:
                require(item["approval"] is not None and item["approval"]["context"] == row["guard_context"]
                        and item["approval"]["subject"] == body["subject"], "Current canonical product approval missing")
            return
        if not kind.startswith("product-"):
            return super()._validate(body)
        self.c.live()
        flow = self.c.product
        require(body["approval"] == self.c.personal.intent["approval"]
                and body["generation"] == self.c.memory.inspect()["state"]["generation"]
                and self.c.clock() < body["expires_at"] == self.c.personal.plan["window"]["expires_at"], "Expired product authority")
        purpose, subject, p = (body[k] for k in ("purpose", "subject", "payload"))
        kind = kind.removeprefix("product-")
        if kind == "admission":
            spec = flow.specification if p == data(flow.specification) else flow.ci_specification
            require(purpose == "admission" and p == data(spec)
                    and subject == flow.guard.admission_subject(self.c.task_id, spec), "Unapproved effect requirement")
        elif kind == "source":
            s, snapshot = typed(SourceClaim, p["source"]), typed(RepositorySnapshot, p["snapshot"])
            require(s.rules == flow.rules() and s.evidence is None and purpose == "policy/" + s.kind.lower()
                    and subject == PolicyProvider(None).source_subject(s, snapshot)
                    and (s.kind == SourceKind.OPERATOR and s.reference == "personal:exact-product-policy" and s.document_digest == digest(flow.active["view"])
                         or s.kind == SourceKind.GOVERNANCE and any(d.reference == s.reference and d.digest == s.document_digest for d in snapshot.documents)), "Unverified project governance interpretation")
        elif kind == "protection":
            protection, snapshot = typed(Protection, p["protection"]), typed(RepositorySnapshot, p["snapshot"])
            v, f = flow.active["view"], flow.active["view"]["facts"]
            expected = Protection(f["base_ref"], f["base_sha"], True, False, True, tuple(f["checks"]),
                max(1, f["policy"]["native_reviews"]), tuple(f["methods"]), (), "personal:actual-native-base-policy",
                v["issued_at"], v["expires_at"], mergeable_methods=tuple(f["methods"]))
            require(protection == expected and purpose == "policy/protection"
                    and subject == PolicyProvider(None).protection_subject(protection, snapshot), "Native protection proof differs")
        elif kind == "operation":
            plan = typed(Plan, p["plan"])
            qualifications = typed(ProjectQualifications if "required" in p["qualifications"] else Qualifications, p["qualifications"])
            flow.live()
            require(plan.policy_effect == "ALLOW" and plan.task.repository_id == self.c.personal.repository_id
                    and plan.task.task_id == self.c.task_id and plan.task.revision == self.c.revision()
                    and plan.task.source_ref == flow.target.ref and plan.request.operation in (flow.active["view"]["operation"], Operation.VALIDATE)
                    and purpose == "policy/operation" and subject == PolicyProvider.authorization_subject(plan, qualifications), "Operation outside exact product delegation")
            if plan.request.operation == Operation.MERGE:
                require(flow.active["view"]["merge_mode"] == "DELEGATED" and plan.payload.method == flow.active["view"]["method"]
                        and plan.payload.expected_base == flow.active["view"]["facts"]["base_sha"], "Separate exact merge authority missing")
            elif plan.request.operation == Operation.PR:
                v = flow.active["view"]
                require(plan.payload.title == v["title"] and plan.payload.draft is True
                        and plan.payload.head_ref == v["source_ref"] and plan.payload.base_ref == v["facts"]["base_ref"]
                        and plan.expected_target == v["facts"]["base_sha"], "PR operands differ from immutable consent")
            elif plan.request.operation == Operation.REPORT:
                v = flow.active["view"]
                require(callable(getattr(flow, "report_record", None)) and flow.report_record() == flow.active
                        and plan.payload.target == v["target"] == self.c.personal.intent["original"]["url"]
                        and plan.payload.body == v["body"], "Separate exact target/body REPORT authority required")
        elif kind == "effect":
            flow.live()
            row = flow.journal.inspect()["state"]["execution"]["actions"].get(p["id"])
            require(purpose == "execution/effect" and p["id"] == flow.active["action"] and row is not None
                    and row["status"] == "SUBMITTED" and row["payload"] == p["payload"]
                    and row["operation"] == flow.active["view"]["operation"] and subject == digest(p), "Exact submitted effect authority missing")
        elif kind == "check-policy":
            plan, policy = typed(Plan, p["plan"]), typed(EvidencePolicy, p["policy"])
            require(purpose == "project-validation/policy" and policy.evidence is None
                    and policy.checks == flow.checks() and subject == policy_subject(plan, policy), "Actual prescribed check policy differs")
        elif kind == "native":
            query, observed = typed(ObservationQuery, p["query"]), typed(ProjectObservation, p["observation"])
            require(purpose == "project-validation/observation" and observed.evidence is None
                    and query.request.repository_id == self.c.personal.repository_id and query.request.revision == self.c.revision()
                    and query.request.pull == flow.ci_identity() and subject == observation_subject(query, observed)
                    and 0 <= self.c.clock() - observed.observed_at <= 300, "Native CI observation identity/freshness differs")
        elif kind in ("project-check", "project-policy", "review"):
            plan = typed(Plan, p["plan"])
            if kind == "project-check":
                value = typed(ProjectCheck, p["value"])
                require(purpose == "policy/project-check" and subject == PolicyProvider(None).project_check_subject(plan, value)
                        and flow.check_matches(value), "Project check lacks actual current #21 provenance")
            elif kind == "project-policy":
                value = typed(ProjectQualifications, p["value"])
                flow.qualified()
                require(purpose == "policy/project-validation" and subject == PolicyProvider(None).project_policy_subject(plan, value)
                        and value.required == tuple((c.name, str(c.phase)) for c in flow.checks()), "Project phase policy differs")
            else:
                value = typed(Review, p["value"])
                flow.verify_review()
                reviewers = flow.review_principals()
                require(purpose == "policy/review" and value.reviewer in reviewers and value.approved is True
                        and value.revision == self.c.revision() and value.observed_at <= self.c.clock() < value.expires_at
                        and body["principal"] == value.reviewer and subject == PolicyProvider(None).review_subject(plan, value), "Independent exact-SHA review differs")
        elif kind == "report-delegation":
            value, plan = typed(DelegationProfile, p["profile"]), typed(Plan, p["plan"])
            v = flow.live()
            require(plan.request.operation == Operation.REPORT and v["operation"] == "REPORT"
                    and plan.task.repository_id == self.c.personal.repository_id and plan.task.task_id == self.c.task_id
                    and plan.task.revision == self.c.revision() and plan.task.source_ref == flow.target.ref
                    and plan.payload.target == v["target"] and plan.payload.body == v["body"], "Unbound REPORT delegation plan")
            expected = DelegationProfile(self.c.personal.repository_id, self.c.personal.plan["issue_id"], self.c.task_id,
                plan.task.iteration, flow.target.ref, v["facts"]["base_ref"], self.c.revision(), plan.policy_digest,
                self.c.personal.plan["original_digest"], ("REPORT",), "MANUAL", (), "UNKNOWN", v["issued_at"], v["expires_at"])
            require(value == expected and purpose == "github-product/delegation" and subject == delegation_subject(value),
                    "REPORT delegation cannot grant merge or another original scope")
        elif kind == "delegation":
            value = typed(DelegationProfile, p)
            v = flow.active["view"]
            require(purpose == "github-product/delegation" and subject == delegation_subject(value) and value.evidence is None
                    and value.repository_id == self.c.personal.repository_id and value.issue_id == self.c.personal.plan["issue_id"]
                    and value.task_id == self.c.task_id and value.revision == self.c.revision() and value.scope_digest == self.c.personal.plan["original_digest"]
                    and v["merge_mode"] == value.merge_mode == "DELEGATED" and value.operations == ("MERGE",)
                    and value.methods == (v["method"],) and value.merge_envelope == v["merge_envelope"], "Explicit current merge delegation missing")
        else:
            raise ValueError("Unsupported personal product proof")
        if kind != "review":
            require(body["principal"] == ("personal:native-github" if kind == "native" else "personal:operator"), "Unqualified product principal")
