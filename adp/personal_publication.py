"""One separately approved personal feature publication through accepted M7.

This does not create PRs, accept products, merge, report or admit another issue.
It uses real canonical M5 actions, M1 ownership, M2 and the original GitHub CAS.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
import secrets

from .config import Config
from .discovery_github import GitHubDiscoveryAdapter
from .discovery_schema import digest, typed
from .errors import ADPError
from .enrollment import branch_rules, local_checkout
from .execution_memory import ExecutionJournal, invocation_lock
from .execution_policy import ReservedSafety
from .guard import ProgressGuard
from .guard_types import Action, ActionKind, Attestation, DecisionKind, Observation, Outcome, Permit, Requirement, data
from .network_git import GitHubCAS, GitHubGitExecutionPort, GitHubPolicyAdapter, GitHubTarget
from .personal_git import administration
from .personal_enrollment import governance
from .personal_github import owned_repository
from .personal_network import PersonalDiscoveryRead, PersonalGitHubTransport
from .personal_storage import LIMIT, PersonalBlocked, create_private, read_private
from .policy import PolicyProvider
from .policy_types import Authorization, Effect, Operation, Permission, Plan, Protection, Qualifications, RepositorySnapshot, Request, Rules, SourceClaim, SourceKind, Task
from .schema import encode, fields, key, require
from .storage import atomic

WARRANT = "No repository rename, transfer, name reuse or credential-scope changes during this finite publication window."
POLICY_ASSENT = "I reviewed the supplied current project governance: this exact feature publication is permitted and has no unmet or unrepresented prepublication condition."
TOKEN = re.compile(r"publish1\.([0-9]{1,12})\.([0-9]{1,12})\.([0-9a-f]{32})\.([0-9a-f]{64})\Z")


class OriginalRead:
    """Transparent receipt digests of the actual selected M4 observations.

    The full successful preflight validates these same responses, not a later
    unrelated baseline. Targeted reobservation still uses M4's complete paging
    and control-header checks. Raw issue/comment bodies are never retained here.
    """
    SUFFIXES = ("comments", "timeline", "dependencies/blocked_by", "sub_issues")

    def __init__(self, transport, base, *, additional=()):
        self.transport, self.base, self.observed = transport, base, {}
        self.bases = (base, *additional)
        require(type(additional) is tuple and 1 <= len(self.bases) <= 8
                and len(set(self.bases)) == len(self.bases), "Bounded unique original observations required")

    def get(self, path):
        response = self.transport.get(path)
        if any(path == base or any(path.startswith(base + "/" + suffix + "?") for suffix in self.SUFFIXES)
               for base in self.bases):
            require(response.status == 200, "Complete current original-ticket evidence required")
            observed = digest({"body": response.body,
                "pagination": [(k.lower(), v) for k, v in response.headers if k.lower() == "link"]})
            require(path not in self.observed or self.observed[path] == observed, "Original-ticket evidence changed during observation")
            self.observed[path] = observed
            require(len(self.observed) <= 81, "Original-ticket evidence exceeds accepted paging bounds")
        return response


class PersonalPublication:
    def __init__(self, coordinator, *, transport=None):
        self.c, self.personal = coordinator, coordinator.personal
        self.clock = coordinator.clock
        p = self.personal.plan
        self.target = GitHubTarget(self.personal.repository_id, p["repository"]["node_id"],
            p["repository"]["database_id"], *p["repository"]["name"].split("/"), p["feature"]["branch"])
        self.journal = ExecutionJournal(self.c.memory)
        self.path = self.personal.state / "publication.json"
        self.evidence = self.personal.state / "publication-evidence"
        self._dispatching = False
        self.c.check_administration(self.c.record())
        self.transport = transport or PersonalGitHubTransport(self.target,
            protected_roots=(self.personal.feature, Path(p["checkout"]["path"]), self.personal.directory, Path(__file__).resolve().parents[1]),
            authorize_write=self.write_authorized)
        self.service = GitHubCAS(self.target, self.transport)
        self.service.bind_control(self.c.memory.control)
        self.read = PersonalDiscoveryRead(self.service)
        self.c.transport = self.read
        self.guard = ProgressGuard(self.c.memory, authority=self, clock=self.clock)
        self.specification = Requirement(self.c.task_id, "personal-publication", ("published",))
        self.cfg = Config.discover(self.personal.feature, remote=p["checkout"]["remote"], repository_id=self.personal.repository_id)
        self.port = GitHubGitExecutionPort(self.cfg, self.service, self.journal,
            bound_git_directory=Path(administration(self.personal.feature)["directory"]["path"]))

    def record(self, *, _observed=None):
        row = read_private(self.path, optional=True)
        if row is None:
            require(not any(a["task_key"] == key(self.c.task_id) and a["operation"] == Operation.PUSH
                for a in self.journal.inspect()["state"]["execution"]["actions"].values()),
                "Missing personal publication history cannot authorize a replacement effect")
            return None
        fields(row, "schema_version view approval credential_binding action_id requirement reservation pending_observation")
        require(type(row["schema_version"]) is int and row["schema_version"] == 1
                and row["action_id"] == digest({"personal-publication": row["view"]})
                and row["view"]["setup_approval"] == self.personal.intent["approval"]
                and row["view"]["generation"] == (_observed if _observed is not None else self.c.memory.inspect())["state"]["generation"],
                "Publication identity, consent or ownership changed")
        view = row["view"]
        require(view["administrative_quiescence_warrant"] == WARRANT and view["project_policy_assent"] == POLICY_ASSENT
                and view["operation"] == "PUSH" and view["force"] is False
                and row["approval"] == ".".join(("publish1", str(view["issued_at"]), str(view["expires_at"]), view["nonce"],
                    digest({"view": view, "private_credential": row["credential_binding"]}))),
                "Retained publication consent was altered")
        return row

    def save(self, row):
        create_private(self.personal.state)
        atomic(self.path, encode(row, LIMIT))

    def admit_task(self, execution, task_key, task):
        existing = execution["tasks"].get(task_key)
        require(existing is None or existing == task, "Canonical publication task differs")
        execution["tasks"][task_key] = task

    def local(self):
        bases = self.original_bases()
        capture = OriginalRead(self.read, bases[0], additional=bases[1:])
        self.c.transport = capture
        try:
            self.c.fresh()
        finally:
            self.c.transport = self.read
        self.c.workers.fence()
        require(self.c.record()["phase"] == "LOCAL_DRAFT_CODE_REVIEWED" and self.c.record()["coordination"] is None,
                "Finish the actual reviewed local draft and reconcile its original guard work")
        review_binding = self.review_binding()
        self.c.original_approval()
        self.c.verify_local_review()
        require(self.review_binding() == review_binding, "Canonical review evidence changed during genuine verification")
        require(all(base in capture.observed and all(base + "/" + suffix + "?per_page=100&page=1" in capture.observed
            for suffix in capture.SUFFIXES) for base in bases), "Full preflight did not validate all original-ticket observations")
        return capture.observed, review_binding

    def review_binding(self, *, _observed=None):
        """Current canonical evidence sealed by full genuine batch review.

        Recompare per object; this is not a new approval or a substitute for
        runtime verification before and after the whole immutable batch.
        """
        observed = _observed if _observed is not None else self.c.memory.inspect()
        require(observed["health"] == "SYNCED" and observed["local_owner"], "Current review owner is required")
        state, task = observed["state"], observed["tasks"][key(self.c.task_id)]
        row, reviews = self.c.record(), {}
        require(task["source_revision"] == row["revision"], "Canonical reviewed source changed")
        for name, purpose in (("original_review", "original"), ("code_review", "code")):
            worker = self.c.worker(row[name])
            assignment = task["assignments"].get(worker["assignment"]["assignment_id"])
            require(worker["purpose"] == purpose and worker["phase"] == "ACCOUNTED" and assignment is not None
                    and assignment["status"] == "accepted" and assignment["worker"] == "worker:" + row[name]
                    and assignment["generation"] == worker["request"]["generation"] == state["generation"]
                    and assignment["source_revision"] == worker["request"]["revision"]
                    and assignment["result"] == self.c.workers.result(worker), "Canonical independent review assignment changed")
            item = state["progress_guard"]["requirements"][worker["requirement"]]
            require(self.c.guard._decision(worker["requirement"], state, task, item).kind == DecisionKind.ALLOW,
                    "Original or code review guard is no longer allowed")
            if purpose == "code":
                require(item["approval"] is not None and item["approval"]["context"] == self.c.guard._context(state, task),
                        "Current canonical code approval is missing")
            reviews[purpose] = {"assignment": assignment, "guard": item}
        return digest({"reviews": reviews, "revision": task["source_revision"], "iteration": task["iteration"],
            "generation": state["generation"], "epoch": state["progress_guard"]["task_epochs"][task["key"]]})

    def original_bases(self):
        primary = self.target.api + "/issues/" + str(self.personal.plan["issue"])
        # The accepted metadata-only helper needs no execution coordinator.
        # A constructed coordinator still must explicitly expose its track.
        if not hasattr(self, "c") or self.c.track is None:
            return (primary,)
        return (primary, *(self.target.api + "/issues/" + str(number)
            for number in sorted(o.issue.number for o in self.c.track.originals.values())
            if number != self.personal.plan["issue"]))

    def current_original(self):
        bases = self.original_bases()
        capture = OriginalRead(self.read, bases[0], additional=bases[1:])
        observer = GitHubDiscoveryAdapter(self.personal.plan["repository"]["name"], capture, max_requests=128, clock=self.clock)
        observer._halt, observer._requests, observer._coverage_items, observer._now = False, 0, [], self.clock()
        for index, base in enumerate(bases):
            observer._one(base, "original-before:" + str(index))
            for suffix in capture.SUFFIXES:
                observer._pages(base + "/" + suffix, "original-" + str(index) + ":" + suffix)
            observer._one(base, "original-after:" + str(index))
        require(all(item.status == "COMPLETE" for item in observer._coverage_items),
                "Original-ticket pagination, permissions or stability is unverified")
        return capture.observed

    def remote(self):
        p = self.personal.plan
        owner = owned_repository(self.read, p["repository"]["name"], self.personal.repository_id)
        observer = GitHubDiscoveryAdapter(p["repository"]["name"], self.read, max_requests=1)
        observer._halt, observer._requests = False, 0
        response = observer._get(self.target.api)
        require(response.status == 200 and type(response.body) is dict, "Current repository metadata unavailable")
        repo = response.body
        require(owner == p["owner"] and owner["push_access"] is True
                and repo.get("node_id") == self.target.node_id
                and repo.get("default_branch") == p["repository"]["default_branch"]
                and self.target.branch != repo["default_branch"], "Current owner, permission, identity or default branch differs")
        try:
            return self.service.inspect_ref(writable=True)
        except (ADPError, OSError):
            raise PersonalBlocked("FEATURE_POLICY_UNVERIFIED",
                "Restore current GitHub feature-ref, permission and branch-rule metadata access; constrained or protected refs are unsupported. Never assume missing rules or retry an uncertain write.") from None

    def proposed(self, approved=None):
        now = self.clock()
        if approved is None:
            issued, expires, nonce = now, min(now + 300, self.personal.plan["window"]["expires_at"]), secrets.token_hex(16)
        else:
            match = TOKEN.fullmatch(approved or "")
            require(match is not None, "Use the separate exact publication approval")
            issued, expires, nonce = int(match[1]), int(match[2]), match[3]
        require(0 <= issued <= now < expires and 0 < expires - issued <= 300
                and expires <= self.personal.plan["window"]["expires_at"], "Original publication window is expired or invalid")
        with self.service.bounded():
            original_observation, review_binding = self.local()
            old = self.remote()
            if old is not None:
                require(self.port._value("--no-replace-objects", "merge-base", old, self.c.revision()) == old,
                        "Unknown or non-fast-forward feature ancestry; no fetch/force fallback")
            state = self.c.memory.inspect()
            row = self.c.record()
            review = self.c.worker(row["code_review"])
            view = {"mode": "PERSONAL_PUBLICATION", "repository": self.personal.plan["repository"],
                "account_id": self.personal.plan["owner"]["account_id"], "issue": self.personal.plan["issue"],
                "issue_id": self.personal.plan["issue_id"], "original_digest": self.personal.plan["original_digest"],
                "original_observation": original_observation,
                "canonical_review_binding": review_binding,
                "setup_approval": self.personal.intent["approval"], "checkpoint": state["local_head"],
                "generation": state["state"]["generation"], "source_ref": self.target.ref,
                "revision": self.c.revision(), "tree": self.port._value("rev-parse", "HEAD^{tree}"),
                "expected_old": old, "absence": "VERIFIED" if old is None else "NOT_APPLICABLE",
                "review_request": row["code_review"], "review_receipt_digest": digest(review["observation"]["receipt"]),
                "worker_inventory": digest(self.c.workers.records()), "administration": digest(administration(self.personal.feature)),
                "governance": self.personal.plan["governance"], "governance_digest": self.personal.plan["governance_digest"],
                "project_check_dispositions": row["gates"], "project_policy_assent": POLICY_ASSENT,
                "credential_source": "STORED_GH_GITHUB_COM_NORMAL_OPERATOR", "credential_confinement": "OPERATOR_QUIESCENCE_ASSUMPTION",
                "credential_provenance": self.transport.credential_provenance,
                "administrative_quiescence_warrant": WARRANT, "operation": "PUSH", "force": False,
                "dispatch_seconds": 45, "maximum_requests": 128, "issued_at": issued, "expires_at": expires,
                "nonce": nonce, "product_acceptance": "NOT_ACCEPTED", "other_external_rights": "NOT_DELEGATED"}
            binding = self.transport.credential_binding
            token = ".".join(("publish1", str(issued), str(expires), nonce, digest({"view": view, "private_credential": binding})))
            require(self.clock() < expires, "Publication window expired during observations")
            return view, token, binding

    def preview(self):
        if self.record() is not None:
            return {"status": "PUBLICATION_INTENT_EXISTS", "result": self.status(), "approval": None}
        view, token, _ = self.proposed()
        return {"status": "PUBLICATION_PROPOSED", "result": view, "approval": token}

    def live(self, *, review=True):
        # One actual fresh observation per call, never retained across objects
        # or callbacks. c.live performs its full current M1/consent checks;
        # generation and review seals refer to that same observed checkpoint.
        observed = self.c.live()
        row = self.record(_observed=observed)
        require(row is not None, "Exact publication consent is missing")
        view = row["view"]
        require(view["issued_at"] <= self.clock() < view["expires_at"]
                and self.port._value("rev-parse", "HEAD") == view["revision"]
                and self.port._value("--no-replace-objects", "rev-parse", "HEAD^{tree}") == view["tree"]
                and self.port._value("symbolic-ref", "HEAD") == view["source_ref"]
                and not self.port._value("status", "--porcelain", "--untracked-files=all")
                and digest(administration(self.personal.feature)) == view["administration"]
                and digest(self.c.workers.records()) == view["worker_inventory"]
                and self.review_binding(_observed=observed) == view["canonical_review_binding"]
                and self.transport.credential_binding == row["credential_binding"], "Publication source, review, credential or finite consent changed")
        if review:
            self.c.verify_local_review()
        return row

    def write_authorized(self):
        # Full genuine review is performed at both batch boundaries. Recheck
        # its sealed canonical assignments/approvals and every current source,
        # owner, credential and guard binding for each exact immutable object.
        row = self.live(review=False)
        require(self._dispatching and row["requirement"] is not None and row["reservation"] is not None,
                "Only the fresh one-use publication dispatch can mutate")
        _, _, item = self.guard._snapshot(self.c.task_id, row["requirement"])
        action = self.journal.inspect()["state"]["execution"]["actions"].get(row["action_id"])
        require(item["active"] is not None and item["active"]["id"] == row["reservation"]["permit"]["token"]
                and self.clock() < item["active"]["deadline"] and action is not None and action["status"] == "SUBMITTED",
                "Current M2 reservation and canonical SUBMITTED intent required")
        return True

    def validate_dispatch(self):
        self.live()
        self.c.workers.fence()
        self.c.original_approval()
        p = self.personal.plan
        expected_checkout = dict(p["checkout"])
        if not p["feature"]["prepare"]:
            expected_checkout["head"] = self.c.revision()
        require(local_checkout(Path(p["checkout"]["path"]), p["checkout"]["remote"]) == expected_checkout
                and digest(governance(Path(p["checkout"]["path"]))) == p["governance_digest"]
                and digest(governance(self.personal.feature)) == p["governance_digest"],
                "Original source or governance changed")
        if self.c.track is None:
            require(not p["native_prerequisites"], "Native prerequisites need independent acceptance before publication")
        else:
            # Full current M4 admission/preflight is bound into the approved raw
            # maps for EVERY selected original. Reobserve those exact maps below
            # and the actual prerequisite receipts here, without another whole
            # repository inventory inside the unchanged CAS request budget.
            self.c.track.publication_prerequisites()
        require(self.current_original() == self.record()["view"]["original_observation"], "Original-ticket scope or native evidence changed")
        require([branch_rules(self.read, p["repository"]["name"], item["ref"].removeprefix("refs/heads/"))
                for item in p["branch_rules"]] == p["branch_rules"], "Original branch requirements changed")
        require(self.remote() == self.record()["view"]["expected_old"], "Remote authority or exact ref changed before CAS")

    def rules(self):
        return Rules(permissions=(Permission(Operation.PUSH, Effect.ALLOW),), reviews=1,
                     branch_template=self.c.rules().branch_template,
                     checks=tuple(self.personal.plan["required_check_names"]))

    def proof(self, purpose, subject, kind, payload):
        row = self.live()
        body = {"purpose": purpose, "subject": subject, "kind": kind, "payload": payload,
            "principal": "personal:operator", "approval": row["approval"], "generation": row["view"]["generation"]}
        self.validate_proof(body)
        create_private(self.evidence)
        identity = digest(body)
        path = self.evidence / (identity + ".json")
        if path.exists():
            require(read_private(path) == body, "Publication proof conflicts")
        else:
            require(len(list(self.evidence.glob("*.json"))) < 256, "Publication evidence bound exhausted")
            atomic(path, encode(body, LIMIT), replace=False)
        return Attestation("personal:operator", "personal-publication:" + identity, subject)

    def verify(self, evidence, *, purpose, subject):
        try:
            self.live()
            require(type(evidence) is Attestation and evidence.reference.startswith("personal-publication:"), "Unqualified publication proof")
            identity = evidence.reference.removeprefix("personal-publication:")
            require(re.fullmatch("[0-9a-f]{64}", identity) is not None, "Unsafe proof reference")
            body = read_private(self.evidence / (identity + ".json"))
            require(digest(body) == identity and body["purpose"] == purpose and body["subject"] == subject
                    and evidence == Attestation(body["principal"], "personal-publication:" + identity, subject), "Publication proof identity differs")
            self.validate_proof(body)
            return True
        except (ADPError, OSError, KeyError, ValueError, TypeError):
            return False

    def validate_proof(self, body):
        fields(body, "purpose subject kind payload principal approval generation")
        row = self.record()
        require(body["approval"] == row["approval"] and body["generation"] == row["view"]["generation"], "Publication proof belongs to another consent")
        purpose, subject, payload = body["purpose"], body["subject"], body["payload"]
        kind = body["kind"]
        if kind == "admission":
            require(purpose == "admission" and payload == data(self.specification)
                    and subject == self.guard.admission_subject(self.c.task_id, self.specification), "Unapproved publication requirement")
        elif kind == "source":
            source = typed(SourceClaim, payload["source"])
            snapshot = typed(RepositorySnapshot, payload["snapshot"])
            require(source.evidence is None and source.rules == self.rules()
                    and purpose == "policy/" + source.kind.lower()
                    and subject == PolicyProvider(None).source_subject(source, snapshot)
                    and (source.kind == SourceKind.OPERATOR and source.reference == "personal:exact-publication-policy"
                         and source.document_digest == digest(row["view"])
                         or source.kind == SourceKind.GOVERNANCE and any(d.reference == source.reference and d.digest == source.document_digest for d in snapshot.documents)),
                    "Publication policy does not match actual governance and exact operator assent")
        elif kind == "protection":
            protection = typed(Protection, payload["protection"])
            snapshot = typed(RepositorySnapshot, payload["snapshot"])
            require(purpose == "policy/protection" and protection.evidence is None
                    and protection.ref == self.target.ref and protection.revision == row["view"]["expected_old"]
                    and protection.known and protection.push_allowed and not protection.merge_allowed
                    and not protection.checks and not protection.unsupported
                    and subject == PolicyProvider(None).protection_subject(protection, snapshot), "Unqualified native feature protection")
        elif kind == "operation":
            plan = typed(Plan, payload)
            require(purpose == "policy/operation" and subject == PolicyProvider.authorization_subject(plan, Qualifications())
                    and plan.policy_effect == Effect.ALLOW and plan.request.operation == Operation.PUSH
                    and plan.task.repository_id == self.personal.repository_id and plan.task.task_id == self.c.task_id
                    and plan.task.revision == row["view"]["revision"] and plan.task.source_ref == self.target.ref
                    and plan.target_ref == self.target.ref and plan.expected_target == row["view"]["expected_old"], "Publication operation differs from exact consent")
        else:
            raise ADPError("Unsupported publication proof")
        require(body["principal"] == "personal:operator", "Unqualified publication principal")

    def initialize(self):
        row = self.live()
        task_key = key(self.c.task_id)
        state = self.c.memory.inspect()
        task = {"task_id": self.c.task_id, "identity": {"repository_id": self.personal.repository_id,
            "issue_id": self.personal.plan["issue_id"], "forge": "github"}, "workspace_key": digest(row["view"]["administration"]),
            "admission": digest({"original": self.personal.plan["original_digest"], "scope_review": self.c.record()["original_review"]}),
            "issue_digest": self.personal.plan["original_digest"], "revision": row["view"]["revision"], "source_ref": self.target.ref,
            "product_iteration": state["tasks"][task_key]["iteration"], "kind": "PRODUCT", "stage": "PUBLISH", "jobs": {}, "review": None}
        # Genuine personal worker evidence stays in its original ledger/M1
        # assignments. Never synthesize canonical M5 Reviewer/check jobs.
        def admit(execution, state, tasks):
            self.admit_task(execution, task_key, task)
        self.journal.change(admit)
        proof = self.proof("admission", self.guard.admission_subject(self.c.task_id, self.specification), "admission", data(self.specification))
        requirement = self.guard.register(self.c.task_id, self.specification, proof)
        row = self.record()
        require(row["requirement"] in (None, requirement), "Publication guard requirement changed")
        row["requirement"] = requirement
        self.save(row)
        state, task, item = self.guard._snapshot(self.c.task_id, requirement)
        if row["reservation"] is None:
            action = Action("personal:coordinator", ActionKind.CHECK, "Publish the exact independently reviewed feature", "Exact authenticated ref observed", seconds=min(45, row["view"]["expires_at"] - self.clock()))
            row["reservation"] = {"context": self.guard._context(state, task), "sequence": item["sequence"], "action": data(action), "permit": None}
            self.save(row)
        reservation = row["reservation"]
        if reservation["permit"] is None:
            if item["active"] is not None:
                require(item["active"]["context"] == reservation["context"] and item["active"]["action"] == reservation["action"], "Unrelated publication guard reservation")
                permit = Permit(item["active"]["id"], self.guard.inspect(self.c.task_id, requirement))
            else:
                require(item["sequence"] == reservation["sequence"], "Publication guard history advanced")
                permit = self.guard.begin(self.c.task_id, requirement, typed(Action, reservation["action"]))
            row["reservation"]["permit"] = data(permit)
            self.save(row)
        return typed(Permit, self.record()["reservation"]["permit"])

    def provider(self, permit):
        row = self.live()
        old = self.remote()
        require(old == row["view"]["expected_old"], "Expected feature ref changed")
        adapter = GitHubPolicyAdapter(self.cfg, self.service, governance=tuple(d["path"] for d in self.personal.intent["governance"]))
        provider = PolicyProvider(adapter, authority=self, safety=ReservedSafety(self.guard, permit), clock=self.clock)
        snapshot = adapter.inspect()
        issued, expires = row["view"]["issued_at"], row["view"]["expires_at"]
        claims = [SourceClaim(SourceKind.OPERATOR, "personal:exact-publication-policy", digest(row["view"]), self.rules(), issued, expires)]
        claims += [SourceClaim(d.kind, d.reference, d.digest, self.rules(), issued, expires) for d in snapshot.documents]
        provider.sources = tuple(replace(source, evidence=self.proof("policy/" + source.kind.lower(), provider.source_subject(source, snapshot),
            "source", {"source": data(source), "snapshot": data(snapshot)})) for source in claims)
        protection = Protection(self.target.ref, old, True, True, False, (), 1, (), (), "personal:native-feature-policy", self.clock(), expires)
        provider.protections = (replace(protection, evidence=self.proof("policy/protection", provider.protection_subject(protection, snapshot),
            "protection", {"protection": data(protection), "snapshot": data(snapshot)})),)
        state = self.c.memory.inspect()["state"]
        task = Task(self.personal.repository_id, self.c.task_id, self.target.branch.split("/")[-1], row["view"]["revision"], self.target.ref,
            row["requirement"], state["generation"], state["progress_guard"]["task_epochs"][key(self.c.task_id)],
            self.c.memory.inspect()["tasks"][key(self.c.task_id)]["iteration"], ("worker:" + self.c.record()["developer"],))
        plan = provider.plan(task, Request(Operation.PUSH))
        authorization = Authorization(self.proof("policy/operation", PolicyProvider.authorization_subject(plan), "operation", data(plan)))
        require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Actual M3 refused publication")
        return provider, plan, authorization

    def reauthorize(self, provider, plan):
        current = provider.plan(plan.task, plan.request)
        require(replace(current, safety=plan.safety) == plan, "Publication policy, repository, source or exact payload changed after reservation")
        authorization = Authorization(self.proof("policy/operation", PolicyProvider.authorization_subject(current), "operation", data(current)))
        require(provider.decide(current, authorization).effect == Effect.ALLOW, "Current checkpoint-bound M3 refused publication")
        return current, authorization

    def settle(self, observation):
        require(not self._dispatching, "Settlement cannot carry a mutation capability")
        row = self.live()
        require(self.remote() == row["view"]["revision"], "Current repository or branch role changed after publication")
        require(observation.status == "PRESENT" and observation.revision == row["view"]["revision"] and not self.service.unconfirmed_contexts(),
                "Publication outcome is uncertain; never retry the write")
        self.journal.change(lambda execution, state, tasks: execution["actions"][row["action_id"]].update(status="OBSERVED", observation=data(observation)))
        permit = typed(Permit, row["reservation"]["permit"])
        _, _, item = self.guard._snapshot(self.c.task_id, row["requirement"])
        if row["pending_observation"] is None:
            reference = "personal:published:" + row["action_id"]
            # Native ref presence is an observed effect, not a new independent
            # review of that effect. Keep every M2 criterion unresolved.
            measured = Observation(Outcome.PASS, (reference,), tuple(item["unresolved"]))
            row["pending_observation"] = data(measured)
            self.save(row)
        measured = typed(Observation, row["pending_observation"])
        if item["active"] is not None:
            decision = self.guard.observe(self.c.task_id, row["requirement"], permit, measured)
        else:
            require(item["last"] is not None and item["last"]["observation"] == row["pending_observation"], "Original publication accounting missing")
            decision = self.guard.inspect(self.c.task_id, row["requirement"])
        return {"status": "PUBLISHED_UNACCEPTED" if decision.kind == DecisionKind.ALLOW else "PUBLISHED_GUARD_STOPPED",
            "progress_guard": decision.kind, "independent_publication_progress": "NOT_CLAIMED", "repository_id": self.personal.repository_id,
            "ref": self.target.ref, "revision": observation.revision, "product_acceptance": "NOT_ACCEPTED", "other_external_rights": "NOT_DELEGATED"}

    def publish(self, *, reviewed, authorized, assume_quiescence, confirm_project_rules):
        require(authorized is True and assume_quiescence is True and confirm_project_rules is True,
                "Separately confirm the exact publication, project rules and finite quiescence warrant")
        existing = self.record()
        if existing is None:
            view, token, binding = self.proposed(reviewed)
            require(reviewed == token, "Publication proposal changed; no mutation authorized")
        else:
            require(reviewed == existing["approval"], "Use the original publication intent; do not renew it")
        with invocation_lock(self.c.memory.control):
            existing = self.record()
            if existing is None:
                current, token, current_binding = self.proposed(reviewed)
                require(current == view and token == reviewed and current_binding == binding, "Publication changed under invocation lock")
                self.save({"schema_version": 1, "view": view, "approval": reviewed, "credential_binding": binding,
                    "action_id": digest({"personal-publication": view}), "requirement": None, "reservation": None, "pending_observation": None})
            else:
                with self.service.bounded():
                    self.local()
                    self.remote()  # Observe current credentials without granting replay.
                self.live()
            permit = self.initialize()
            row = self.record()
            action = self.journal.inspect()["state"]["execution"]["actions"].get(row["action_id"])
            if action is not None:
                # Recovery is observation only, even PREPARED without a claim.
                with self.service.bounded():
                    return self.settle(self.port.observe(action))
            with self.service.bounded():
                provider, plan, authorization = self.provider(permit)
                action = {"task_key": key(self.c.task_id), "generation": row["view"]["generation"], "operation": Operation.PUSH,
                    "revision": plan.task.revision, "source_ref": plan.task.source_ref, "target": plan.target_ref,
                    "expected_target": plan.expected_target, "payload": data(plan.payload), "status": "PREPARED", "observation": None,
                    "plan_digest": digest(plan)}
                self.journal.change(lambda execution, state, tasks: execution["actions"].update({row["action_id"]: action}))
                dispatch = self.port.prepare_dispatch(row["action_id"], action)
                self.journal.change(lambda execution, state, tasks: execution["actions"][row["action_id"]].update(status="SUBMITTED"))
                plan, authorization = self.reauthorize(provider, plan)
            # The accepted port owns its unchanged 45s/128-call dispatch. Do
            # not nest it inside a preflight budget which would be restored
            # already expired afterward. Never renew the original M2 permit.
            self._dispatching = True
            try:
                result = self.port.submit(action, provider, plan, authorization, dispatch=dispatch, validate=self.validate_dispatch)
            except OSError:
                result = None  # Observe only after clearing mutation authority.
            finally:
                self._dispatching = False
            with self.service.bounded():
                if result is None:
                    result = self.port.observe(action)
                return self.settle(result)

    def status(self):
        row = self.record()
        if row is None:
            return {"status": "NOT_DELEGATED", "product_acceptance": "NOT_ACCEPTED"}
        action = self.journal.inspect()["state"]["execution"]["actions"].get(row["action_id"])
        with self.service.bounded():
            self.c.check_administration(self.c.record())
            self.c.verify_local_review()
            self.remote()
            observation = self.port.observe(action) if action is not None else None
        guard = self.guard.inspect(self.c.task_id, row["requirement"]).kind if row["requirement"] is not None else None
        present = observation is not None and observation.status == "PRESENT"
        return {"status": ("PUBLICATION_PRESENT" if guard == DecisionKind.ALLOW else "PUBLICATION_PRESENT_GUARD_STOPPED") if present else "UNKNOWN_PUBLICATION",
            "canonical_status": action["status"] if action is not None else "NOT_SUBMITTED", "ref": self.target.ref,
            "revision": row["view"]["revision"], "product_acceptance": "NOT_ACCEPTED", "mutation_retry": "NOT_AUTHORIZED",
            "progress_guard": guard, "unconfirmed_transport": bool(self.service.unconfirmed_contexts()), "expires_at": row["view"]["expires_at"]}
