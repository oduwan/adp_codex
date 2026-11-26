"""One personal issue composed with the actual M7 forge, M3 and #21 ports.

Private operator receipts are local trust, not external signatures. Nothing in
this module reports/closes issues, marks a Draft ready or admits another task.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
import secrets

from .personal_read_frame import qualified as historical_operation
from .config import Config
from .discovery_schema import digest, typed
from .errors import ADPError
from .execution_memory import ExecutionJournal, invocation_lock
from .execution_policy import ReservedSafety
from .execution_types import ExternalObservation
from .github_product import DelegationProfile, GitHubProductForge, delegation_subject
from .guard import ProgressGuard
from .guard_schema import requirement_id
from .guard_types import Action, ActionKind, DecisionKind, Observation, Outcome, Permit, Requirement, data
from .network_git import GitHubCAS, GitHubPolicyAdapter
from .personal_ci import native_inventory, prescribed_checks
from .personal_enrollment import governance
from .personal_git import administration
from .personal_github import owned_repository
from .personal_product_http import PersonalProductTransport, PersonalProjectRead
from .personal_product_policy import closing_directive, observe_policy, product_text
from .github_rules import PLAN_ASSENT
from .personal_publication import PersonalPublication, WARRANT
from .personal_storage import LIMIT, PersonalBlocked, create_private, read_private
from .policy import PolicyProvider
from .policy_schema import sha, fingerprint
from .policy_types import (Authorization, Effect, Operation, Permission, ProjectCheck, ProjectQualifications,
    Protection, Qualifications, Request, Review, Rules, SourceClaim, SourceKind, Task)
from .project_validation import ProjectValidation, policy_subject, observation_subject
from .project_validation_github import GitHubEvidenceSource
from .project_validation_types import EvidenceGate, EvidencePolicy, Phase, PullIdentity, RequiredCheck
from .schema import encode, fields, key, require, string
from .storage import atomic
from .runtime_limits import bind_consent, consent_limits, consent_scope, current_budget, measured, network_operation

TOKEN = re.compile(r"product[12]\.([0-9]{1,12})\.([0-9]{1,12})\.([0-9a-f]{32})\.([0-9a-f]{64})\Z")
ASSENT = "I reviewed the current supplied project governance and approve this exact operation without waiving any project requirement."
ENVELOPE = "HEAD_ATOMIC_BASE_OBSERVED"


class PersonalProduct:
    def __init__(self, coordinator, *, transport=None):
        self.c, self.personal, self.clock = coordinator, coordinator.personal, coordinator.clock
        self.publication = PersonalPublication(coordinator, transport=transport) if transport is not None else PersonalPublication(coordinator)
        self.target = self.publication.target
        self.journal = ExecutionJournal(self.c.memory)
        self.path = self.personal.state / "product.json"
        self._writing = None
        self.active = None
        self.transport = transport or PersonalProductTransport(self.target,
            protected_roots=(self.personal.feature, Path(self.personal.plan["checkout"]["path"]),
                self.personal.directory, Path(__file__).resolve().parents[1]), authorize_write=self.write_authorized)
        self.service = GitHubCAS(self.target, self.transport)
        self.service.bind_control(self.c.memory.control)
        self.read = PersonalProjectRead(self.service)
        self.c.transport = self.read
        self.c.product = self
        from .personal_product_review import ProductAuthority
        self.c.authority = ProductAuthority(self.c)
        self.c.guard = ProgressGuard(self.c.memory, authority=self.c.authority, clock=self.clock)
        self.guard = ProgressGuard(self.c.memory, authority=self.c.authority, clock=self.clock)
        self.forge = GitHubProductForge(self.service, self.journal, self.c.authority)
        self.cfg = Config.discover(self.personal.feature, remote=self.personal.plan["checkout"]["remote"], repository_id=self.personal.repository_id)
        self.port = self.publication.port
        self.specification = Requirement(self.c.task_id, "personal-product-effects", ("exact-effects-observed",))
        self.ci_specification = Requirement(self.c.task_id, "personal-post-pr-validation", ("prescribed-ci-qualified",))

    def record(self):
        row = read_private(self.path, optional=True)
        if row is None:
            require(not any(a["operation"] in (Operation.PR, Operation.MERGE) and a["task_key"] == key(self.c.task_id)
                for a in self.journal.inspect()["state"]["execution"]["actions"].values()),
                "Missing product intent history cannot authorize replacement effects")
            return None
        fields(row, "schema_version setup generation intents pull gates review execution correction publications")
        require(type(row["schema_version"]) is int and row["schema_version"] in ((1, 2) if self.c.episode else (1,))
                and row["setup"] == self.personal.intent["approval"]
                and row["generation"] == self.c.memory.inspect()["state"]["generation"]
                and type(row["intents"]) is list and len(row["intents"]) <= 4
                and type(row["execution"]) is list and len(row["execution"]) <= 8
                and type(row["gates"]) is list and len(row["gates"]) <= self.personal.plan["window"]["maximum_check_observations"]
                and type(row["publications"]) is list and len(row["publications"]) <= 2,
                "Product identity, generation or finite history differs")
        for intent in row["intents"]:
            fields(intent, "view approval binding action requirement reservation observation")
            require(intent["view"]["operation"] in ("PR", "MERGE")
                    and intent["approval"] == self.token(intent["view"], intent["binding"])
                    and intent["action"] == digest({"personal-product": intent["view"]}), "Product consent changed")
            require("availability" not in intent["view"]["facts"]["policy"]
                    or intent["view"].get("plan_disabled_rules_assent") == PLAN_ASSENT,
                    "Exact product plan-disabled rules warrant is missing")
        for execution in row["execution"]:
            fields(execution, "view approval binding phase checks result reservation")
            require(execution["view"]["operation"] in ("CI", "REVIEW", "CORRECT")
                    and execution["approval"] == self.token(execution["view"], execution["binding"])
                    and execution["phase"] in ("PREPARED", "SUBMITTED", "COMPLETE")
                    and type(execution["checks"]) is list and len(execution["checks"]) <= 32, "Malformed retained execution")
            for check in execution["checks"]:
                typed(RequiredCheck, check)
        for publication in row["publications"]:
            fields(publication, "revision action legacy")
            sha(publication["revision"]); fingerprint(publication["action"])
            require(type(publication["legacy"]) is bool, "Malformed publication history")
        return row

    def save(self, row):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        create_private(self.personal.state)
        atomic(self.path, encode(row, LIMIT))

    def initialize(self):
        row = self.record()
        if row is None:
            row = {"schema_version": 2 if self.c.episode else 1, "setup": self.personal.intent["approval"],
                "generation": self.c.memory.inspect()["state"]["generation"], "intents": [], "pull": None,
                "gates": [], "review": None, "execution": [], "correction": None, "publications": []}
            self.save(row)
        require(not self.c.episode or row["schema_version"] == 2, "Legacy Product history is observation-only")
        return row

    @staticmethod
    def token(view, binding):
        names = ("historical_basis", "historical_engine", "reader_engine")
        present = [name in view for name in names]
        require(not any(present) or all(present), "Incomplete accounting writer binding")
        return ".".join(("product2" if all(present) else "product1", str(view["issued_at"]), str(view["expires_at"]), view["nonce"], digest({"view": view, "credential": binding})))

    def local(self, *, genuine=True, _history_capture=None):
        self.c.live(_history_capture=_history_capture) if _history_capture is not None else self.c.live()
        self.c.workers.fence()
        require(self.c.record()["phase"] == "LOCAL_DRAFT_CODE_REVIEWED", "Finish the exact reviewed local draft first")
        if genuine:
            self.c.fresh(_history_capture=_history_capture) if _history_capture is not None else self.c.fresh()
            self.c.original_approval()
            self.c.verify_local_review()
        require(self.port._value("rev-parse", "HEAD") == self.c.revision()
                and not self.port._value("status", "--porcelain", "--untracked-files=all")
                and digest(governance(self.personal.feature)) == self.personal.plan["governance_digest"],
                "Current product source/governance changed")
        return self.review_seal()

    def history_binding(self, *, capture=None, view=None):
        if not getattr(self.c, "episode", False):
            return {}
        from .personal_history import _reader_binding
        if capture is None:
            capture = {}
            self.c.live(_history_capture=capture)
        binding = _reader_binding(capture)
        if view is not None:
            row = self.record()
            require(row is None or row["schema_version"] == 2, "Legacy Product history is observation-only")
            require(all(view.get(k) == v for k, v in binding.items()), "Legacy or changed accounting writer; observe only")
        return binding

    def review_seal(self, *, review_worker=None):
        state = self.c.memory.inspect()
        task, run = state["tasks"][key(self.c.task_id)], self.c.record()
        reviews = []
        for name in ("original_review", "code_review"):
            worker = self.c.worker(run[name])
            assignment = task["assignments"].get(worker["assignment"]["assignment_id"])
            require(assignment is not None and assignment["status"] == "accepted"
                    and assignment["result"] == self.c.workers.result(worker)
                    and assignment["generation"] == state["state"]["generation"], "Canonical review assignment changed")
            s, t, guard = self.c.guard._snapshot(self.c.task_id, worker["requirement"])
            if guard["active"] is None:
                self.c.allowed(worker["requirement"])
            else:
                coordination = run["coordination"]
                if coordination is None and review_worker is not None:
                    require(review_worker["purpose"] == "product" and review_worker["phase"] in ("SUBMITTED", "STOPPED")
                            and review_worker["requirement"] == worker["requirement"]
                            and review_worker["permit"]["token"] == guard["active"]["id"]
                            and guard["active"]["action"]["kind"] == "REVIEW"
                            and guard["active"]["action"]["hypothesis"] == "worker:" + review_worker["request"]["id"],
                            "Only this exact stopped product review may inspect its prior approval seal")
                else:
                    require(coordination is not None and coordination["permit"]["token"] == guard["active"]["id"], "Unrelated active guard")
                self.c.guard._active(s, t, guard, guard["active"]["id"])
                require(self.clock() < guard["active"]["deadline"] and guard["mode"] in ("normal", "running"), "Guard deadline/stop")
            reviews.append({"request": worker["request"], "assignment": assignment, "observation": worker["observation"], "approval": guard["approval"]})
        return digest({"reviews": reviews, "source": task["source_revision"], "generation": state["state"]["generation"],
            "epoch": state["state"]["progress_guard"]["task_epochs"][key(self.c.task_id)]})

    def facts(self, *, merge=False):
        p = self.personal.plan
        owner = owned_repository(self.read, p["repository"]["name"], self.personal.repository_id)
        repo_response = self.read.get(self.target.api)
        repo = repo_response.body
        require(repo_response.status == 200 and type(repo) is dict and owner == p["owner"] and owner["push_access"]
                and repo.get("node_id") == self.target.node_id and repo.get("default_branch") == p["repository"]["default_branch"],
                "Repository, account, permissions or default branch changed")
        refs = {r.name: r.revision for r in self.service.refs()}
        base_ref = "refs/heads/" + p["repository"]["default_branch"]
        require(refs.get(self.target.ref) == self.c.revision() and base_ref in refs,
                "Exact published HEAD and current base required")
        policy = observe_policy(self.read, self.target, base_ref, personal=(p["repository"], p["owner"]),
            expected_sha=refs[base_ref], service=self.service, expected_head=self.c.revision())
        names = sorted(set(p["required_check_names"]) | set(policy["checks"]))
        require(len(names) <= 32, "Project checks exceed accepted capacity")
        methods = []
        if merge:
            require(all(type(repo.get(k)) is bool for k in ("allow_merge_commit", "allow_squash_merge")),
                    "Current repository merge methods unknown")
            methods = [m for m, k in (("merge", "allow_merge_commit"), ("squash", "allow_squash_merge"))
                if repo[k] and m in policy["methods"]]
        return {"base_ref": base_ref, "base_sha": refs[base_ref], "policy": policy, "checks": names, "methods": methods}

    def pull(self, *, expected_base=None, allow_merged=False, published_revision=None):
        row = self.record()
        require(row is not None and row["pull"] is not None, "Existing exact PR identity required")
        identity = row["pull"]
        item = self.forge.pull({k: identity[k] for k in ("id", "number", "repository_id", "url")},
            revision=published_revision or self.c.revision(), source_ref=self.target.ref,
            base_ref="refs/heads/" + self.personal.plan["repository"]["default_branch"], expected_base=expected_base)
        require(item is not None and item.get("node_id") == identity["node_id"]
                and (item["state"] == "open" and not item["merged"] or allow_merged and item["merged"]),
                "PR identity, source, base or disposition changed")
        original = next(i for i in row["intents"] if i["view"]["operation"] == "PR")
        require(item.get("title") == original["view"]["title"]
                and item.get("body") == original["view"]["body"] + "\n\n" + self.forge.marker(original["action"]),
                "Current PR text differs from exact publication consent")
        inventory = self.forge.inventory(Operation.PR, {"body": original["view"]["body"]})
        require(inventory is not None and all(type(p.get("head")) is dict for p in inventory), "Ambiguous PR inventory")
        matches = [p for p in inventory if p["head"].get("ref") == self.target.branch]
        require(len(matches) == 1 and type(matches[0].get("id")) is int
                and str(matches[0]["id"]) == identity["id"], "Alternate or duplicate source PR")
        return item

    @network_operation("product.proposed")
    @historical_operation
    def proposed(self, operation, *, approved=None, title=None, body=None, method=None, delegate=False):
        require(operation in ("PR", "MERGE"), "Unsupported product operation")
        now = self.clock()
        if approved is None:
            issued, expires, nonce = now, min(now + 300, self.personal.plan["window"]["expires_at"]), secrets.token_hex(16)
        else:
            match = TOKEN.fullmatch(approved or "")
            require(match is not None, "Use the exact separate product proposal")
            issued, expires, nonce = int(match[1]), int(match[2]), match[3]
        require(0 <= issued <= now < expires and 0 < expires - issued <= 300
                and expires <= self.personal.plan["window"]["expires_at"], "Original product window expired")
        bind_consent({"runtime_limits": self.service.limits.values(), "expires_at": expires}, now)
        with self.service.bounded():
            capture = {} if self.c.episode else None
            seal = self.local(_history_capture=capture)
            facts = self.facts(merge=operation == "MERGE")
            original = self.publication.current_original()
            if operation == "PR":
                product_text(title, body)
                require(self.record() is None or self.record()["pull"] is None, "One original PR only")
                payload = {"body": body}
                inventory = self.forge.inventory(Operation.PR, payload)
                require(inventory is not None and not any(type(r.get("head")) is not dict
                    or r["head"].get("ref") == self.target.branch for r in inventory),
                    "Alternate/ambiguous PR for the admitted feature; do not POST a replacement")
            else:
                require(type(delegate) is bool and method in ("merge", "squash"), "Explicit supported merge method required")
                item = self.pull(expected_base=facts["base_sha"])
                self.qualified()
                self.verify_review()
                require(not closing_directive(self.port._value("log", "--format=%B", facts["base_sha"] + "..HEAD")),
                        "Merge would cause undelegated issue closure")
                self.native_reviews(item, facts)
                require(method in facts["methods"], "Current project forbids this merge method")
                require(self.port._value("merge-base", facts["base_sha"], self.c.revision()) == facts["base_sha"],
                        "Native merge requires observed base ancestry; no fetch or rewrite")
                if item["draft"] or item.get("mergeable") is not True or item.get("mergeable_state") != "clean":
                    return {"status": "WAITING_HUMAN_APPROVAL", "reason": "PR_READINESS_OR_NATIVE_MERGEABILITY", "approval": None}
            view = {"operation": operation, "runtime_limits": self.service.limits.values(),
                "setup": self.personal.intent["approval"], "repository": self.personal.plan["repository"],
                "issue_id": self.personal.plan["issue_id"], "original_digest": self.personal.plan["original_digest"],
                "original_observation": original, "revision": self.c.revision(), "source_ref": self.target.ref,
                "source_tree": self.port._value("rev-parse", "HEAD^{tree}"), "review_binding": seal,
                "administration": digest(administration(self.personal.feature)), "facts": facts,
                "title": title if operation == "PR" else None, "body": body if operation == "PR" else None,
                "method": method if operation == "MERGE" else None, "merge_mode": "DELEGATED" if delegate else "MANUAL",
                "pull": self.record()["pull"] if self.record() is not None else None,
                "validation": self.validation_binding() if operation == "MERGE" else None,
                "product_review": self.record()["review"] if operation == "MERGE" else None,
                "policy_assent": ASSENT, "administrative_quiescence_warrant": WARRANT,
                "merge_envelope": ENVELOPE}
            # Observe after all preceding callbacks, at the original first-read
            # position. Generation and checkpoint belong to this same snapshot.
            observed = self.c.memory.inspect()
            view.update(generation=observed["state"]["generation"], checkpoint=observed["local_head"],
                issued_at=issued, expires_at=expires, nonce=nonce)
            if "availability" in facts["policy"]:
                view["plan_disabled_rules_assent"] = PLAN_ASSENT
            if capture is not None:
                from .personal_episode import same_observation
                same_observation(capture["subject"], observed)
                view.update(self.history_binding(capture=capture))
            binding = self.transport.credential_binding
            require(self.clock() < expires, "Proposal expired during observation")
        return {"status": "WAITING_HUMAN_APPROVAL" if operation == "MERGE" and not delegate else operation + "_PROPOSED",
            "result": view, "approval": self.token(view, binding), "binding": binding}

    @measured("product.live")
    @historical_operation
    def live(self, *, genuine=False):
        if self.c.episode and not genuine:
            from .personal_read_frame import product_live
            return product_live(self)
        from .personal_read_frame import forbid_writes
        forbid_writes()
        return self._live_current(genuine=genuine)

    def _live_current(self, *, genuine=False):
        require(self.active is not None, "Exact operation consent required")
        view = self.active["view"]
        bind_consent(view, self.clock())
        capture = {} if self.c.episode else None
        self.local(genuine=genuine, _history_capture=capture)
        self.history_binding(capture=capture, view=view)
        require(view["issued_at"] <= self.clock() < view["expires_at"]
                and view["generation"] == self.c.memory.inspect()["state"]["generation"]
                and view["revision"] == self.c.revision() and view["source_tree"] == self.port._value("rev-parse", "HEAD^{tree}")
                and view["review_binding"] == self.review_seal()
                and view["administration"] == digest(administration(self.personal.feature))
                and self.transport.credential_binding == self.active["binding"], "Exact operation owner/source/review/credential/consent changed")
        return view

    def write_authorized(self):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        if self.c.episode:
            from .personal_read_frame import _CURRENT
            require(_CURRENT.get() is not None and _CURRENT.get()["c"] is self.c, "No active historical invocation")
        view = self._live_current()
        from .personal_read_frame import current_source
        source_admin = current_source(self, self.active, product=True)
        require(type(self._writing) is tuple and len(self._writing) == 4
                and self._writing[0] == self.active["action"], "Fresh one-use product dispatch required")
        identifier, expected, expected_admin, subject = self._writing
        require(source_admin == expected_admin, "Current effect source administration changed")
        original = (self.report_record() if view["operation"] == "REPORT" else
            next((i for i in self.record()["intents"] if i["action"] == identifier), None))
        require(original == self.active, "Current product intent changed")
        observed = self.c.memory.inspect()
        from .personal_episode import same_observation
        same_observation(subject, observed)
        state, task = observed["state"], observed["tasks"][key(self.c.task_id)]
        row = state["execution"]["actions"].get(identifier)
        require(observed["health"] == "SYNCED" and observed["local_owner"]
                and state["generation"] == view["generation"] and task["source_revision"] == view["revision"]
                and row == expected and row["status"] == "SUBMITTED" and row["operation"] == view["operation"],
                "Current canonical submitted effect/owner/source differs")
        claim = {"intent": identifier, "generation": row["generation"], "payload": digest(row["payload"]),
                 "operation": row["operation"], "repository": self.forge.repository_id}
        require(read_private(self.forge._claim_path(identifier)) == claim, "Original forge dispatch claim changed")
        permit = typed(Permit, self.active["reservation"])
        item = self.guard._get(state, task, self.active["requirement"])
        active = self.guard._active(state, task, item, permit.token)
        require(self.transport.credential_binding == self.active["binding"], "Current effect credential changed")
        if self.c.episode:
            self.c.episode_fence()
        now = self.clock()
        require(active["started"] <= now < active["deadline"] and item["mode"] in ("normal", "running")
                and view["issued_at"] <= now < view["expires_at"], "Effect M2 or consent interval/stop changed")
        budget = self.service._budget.get()
        require(budget is not None and budget is current_budget(), "Original effect operation budget required")
        budget.check()
        return True

    def rules(self):
        v = self.active["view"]
        return Rules(permissions=tuple(Permission(op, Effect.ALLOW) for op in sorted({Operation(v["operation"]), Operation.VALIDATE})),
            base_branch=v["facts"]["base_ref"].removeprefix("refs/heads/"), branch_template=self.c.rules().branch_template,
            pr_title_template="{summary}", pr_draft=True, merge_method=v["method"],
            checks=tuple(v["facts"]["checks"]), reviews=1)

    def proof(self, purpose, subject, kind, payload, *, principal="personal:operator"):
        return self.c.authority._proof(purpose, subject, "product-" + kind, payload, principal)

    def provider(self, permit):
        v = self.live()
        adapter = GitHubPolicyAdapter(self.cfg, self.service, governance=tuple(d["path"] for d in self.personal.intent["governance"]))
        provider = PolicyProvider(adapter, authority=self.c.authority, safety=ReservedSafety(self.c.guard, permit), clock=self.clock)
        snapshot = adapter.inspect()
        claims = [SourceClaim(SourceKind.OPERATOR, "personal:exact-product-policy", digest(v), self.rules(), v["issued_at"], v["expires_at"])]
        claims += [SourceClaim(d.kind, d.reference, d.digest, self.rules(), v["issued_at"], v["expires_at"]) for d in snapshot.documents]
        provider.sources = tuple(replace(s, evidence=self.proof("policy/" + s.kind.lower(), provider.source_subject(s, snapshot), "source",
            {"source": data(s), "snapshot": data(snapshot)})) for s in claims)
        f = v["facts"]
        protection = Protection(f["base_ref"], f["base_sha"], True, False, True, tuple(f["checks"]),
            max(1, f["policy"]["native_reviews"]), tuple(f["methods"]), (),
            "personal:operator-plan-disabled-base-policy" if "availability" in f["policy"] else "personal:actual-native-base-policy",
            v["issued_at"], v["expires_at"], mergeable_methods=tuple(f["methods"]))
        provider.protections = (replace(protection, evidence=self.proof("policy/protection", provider.protection_subject(protection, snapshot),
            "protection", {"protection": data(protection), "snapshot": data(snapshot)})),)
        state = self.c.memory.inspect()
        task = Task(self.personal.repository_id, self.c.task_id, self.target.branch.split("/")[-1], self.c.revision(), self.target.ref,
            permit.decision.baseline.requirement_id, state["state"]["generation"], state["state"]["progress_guard"]["task_epochs"][key(self.c.task_id)],
            state["tasks"][key(self.c.task_id)]["iteration"], self.c.source_authors())
        return provider, task

    def authorize(self, provider, plan, qualifications=Qualifications()):
        return Authorization(self.proof("policy/operation", provider.authorization_subject(plan, qualifications), "operation",
            {"plan": data(plan), "qualifications": data(qualifications)}), qualifications)

    def final_boundary(self):
        v = self.live(genuine=True)
        require(self.publication.current_original() == v["original_observation"]
                and self.facts(merge=v["operation"] == "MERGE") == v["facts"], "Current original ticket/project policy/head/base changed")
        if v["operation"] == "MERGE":
            item = self.pull(expected_base=v["facts"]["base_sha"])
            require(not item["draft"] and item.get("mergeable") is True and item.get("mergeable_state") == "clean", "PR readiness changed")
            self.qualified(); self.verify_review(); self.native_reviews(item, v["facts"])
        else:
            inventory = self.forge.inventory(Operation.PR, {"body": v["body"]})
            require(inventory is not None and not any(type(r.get("head")) is not dict
                    or r["head"].get("ref") == self.target.branch for r in inventory), "Concurrent alternate PR; observe only")
        require(callable(getattr(self, "_policy_final", None)) and self._policy_final() is True,
                "Current exact M3 final authorization required")

    @network_operation("product.intent")
    @historical_operation
    def intent(self, operation, *, reviewed, authorized, authorize_memory, assume_quiescence, confirm_rules,
               title=None, body=None, method=None, delegate=False, accept_envelope=False, accept_plan_unavailable=False):
        require(authorized is True and authorize_memory is True and assume_quiescence is True and confirm_rules is True,
                "Separate exact operator effect, memory migration, project rules and quiescence approvals required")
        require(operation != "MERGE" or delegate is True and accept_envelope is True,
                "Merge defaults MANUAL; separately delegate the observed-base envelope")
        with invocation_lock(self.c.memory.control):
            row = self.record()
            require(not self.c.episode or row is None or row["schema_version"] == 2, "Legacy Product effects are observation-only")
            old = next((r for r in row["intents"] if r["approval"] == reviewed), None) if row else None
            previous = [r for r in row["intents"] if r["view"]["operation"] == operation] if row else []
            if old is None and previous:
                require(operation == "MERGE" and all(r["action"] not in self.journal.inspect()["state"]["execution"]["actions"] for r in previous)
                        and self.c.record()["coordination"] is None, "Observe original effect only; no replacement authorization")
            if old is None:
                proposed = self.proposed(operation, approved=reviewed, title=title, body=body, method=method, delegate=delegate)
                require(proposed["approval"] == reviewed and proposed.get("result") is not None, "Product proposal changed")
                require("plan_disabled_rules_assent" not in proposed["result"] or accept_plan_unavailable is True,
                        "PLAN_UNAVAILABLE: separately accept this exact operation's plan-disabled rules warrant")
                row = self.initialize()
                old = {"view": proposed["result"], "approval": reviewed, "binding": proposed["binding"],
                    "action": digest({"personal-product": proposed["result"]}), "requirement": None, "reservation": None, "observation": None}
                row["intents"].append(old); self.save(row)
            else:
                require(old["approval"] == reviewed, "Only observation of the original intent is supported")
            require(old["view"]["operation"] == operation and title in (None, old["view"]["title"])
                    and body in (None, old["view"]["body"]) and method in (None, old["view"]["method"]),
                    "Resume cannot change approved effect operands")
            self.active = old
            bind_consent(old["view"])
            with self.service.bounded():
                self.local(); self.facts(merge=operation == "MERGE")
                self.live(genuine=True)
            self.journal.upgrade_product_flow(authorized=True)
            if old["requirement"] is None:
                if operation == "PR":
                    admission = self.proof("admission", self.guard.admission_subject(self.c.task_id, self.specification), "admission", data(self.specification))
                    old["requirement"] = self.guard.register(self.c.task_id, self.specification, admission)
                else:
                    old["requirement"] = self.c.requirement("develop")
                self.save_intent(old)
            action = self.journal.inspect()["state"]["execution"]["actions"].get(old["action"])
            if action is not None:
                with self.service.bounded():
                    return self.settle(self.forge.observe(old["action"], operation, action["payload"], attempted=True))
            if old["reservation"] is None:
                if operation == "MERGE":
                    permit = self.c.reserve("personal-merge:" + old["action"])
                else:
                    state, task, item = self.guard._snapshot(self.c.task_id, old["requirement"])
                    if item["active"] is not None:
                        require(item["active"]["action"]["hypothesis"] == old["action"], "Unrelated effect reservation")
                        permit = Permit(item["active"]["id"], self.guard.inspect(self.c.task_id, old["requirement"]))
                    else:
                        permit = self.guard.begin(self.c.task_id, old["requirement"], Action("personal:coordinator", ActionKind.CHECK,
                            old["action"], "One authenticated exact product effect", seconds=min(consent_limits(old["view"]).operation_timeout_seconds, old["view"]["expires_at"] - self.clock())))
                old["reservation"] = data(permit); self.save_intent(old)
            permit = typed(Permit, old["reservation"])
            if operation == "MERGE":
                self.refresh_merge_ci(permit)
                with self.service.bounded():
                    self.native_reviews(self.pull(expected_base=old["view"]["facts"]["base_sha"]), old["view"]["facts"])
            with self.service.bounded():
                provider, task = self.provider(permit)
                plan = provider.plan(task, Request(Operation(operation), summary=old["view"]["title"] or ""))
                qualifications = self.qualifications(provider, plan) if operation == "MERGE" else Qualifications()
                authorization = self.authorize(provider, plan, qualifications)
                require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Actual M3 refused product operation")
                payload = data(plan.payload)
                if operation == "PR":
                    payload.update(body=old["view"]["body"], revision=task.revision)
                else:
                    profile = self.delegation(plan)
                    require(self.c.authority.verify(profile.evidence, purpose="github-product/delegation", subject=delegation_subject(profile)), "Unverified exact merge delegation")
                    payload.update(pull={k: old["view"]["pull"][k] for k in ("id", "number", "repository_id", "url")},
                        source_tree=old["view"]["source_tree"], envelope=ENVELOPE)
                action = {"task_key": key(self.c.task_id), "generation": task.generation, "operation": operation,
                    "revision": task.revision, "source_ref": task.source_ref, "target": plan.target_ref,
                    "expected_target": plan.expected_target, "payload": payload, "status": "PREPARED", "observation": None, "plan_digest": digest(plan)}
                self.journal.change(lambda e, s, t: e["actions"].update({old["action"]: action}))
                dispatch = self.forge.prepare_dispatch(old["action"], action)
                self.journal.change(lambda e, s, t: e["actions"][old["action"]].update(status="SUBMITTED"))
                current = provider.plan(task, plan.request)
                require(replace(current, safety=plan.safety) == plan, "Product plan changed after durable checkpoint")
                plan = current
                authorization = self.authorize(provider, plan, qualifications)
                require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Fresh checkpoint-bound M3 refused effect")
                effect = self.proof("execution/effect", digest({"id": old["action"], "plan": digest(plan), "payload": payload}),
                    "effect", {"id": old["action"], "plan": digest(plan), "payload": payload})
                self._policy_final = lambda: provider.decide(plan, authorization).effect == Effect.ALLOW
            from .personal_read_frame import current_source
            self._writing = (old["action"], {**action, "status": "SUBMITTED"},
                             current_source(self, old, product=True), self.c.memory.inspect())
            try:
                # Accepted forge owns its unchanged dispatch bound.
                observation = self.forge.submit(old["action"], Operation(operation), payload, authorization=effect,
                    plan_digest=digest(plan), dispatch=dispatch, validate=self.final_boundary)
            except (ADPError, OSError):
                observation = None
            finally:
                self._writing = None
            with self.service.bounded():
                if observation is None:
                    observation = self.forge.observe(old["action"], operation, payload, attempted=True)
                return self.settle(observation)

    def save_intent(self, intent):
        row = self.record()
        row["intents"] = [intent if i["action"] == intent["action"] else i for i in row["intents"]]
        self.save(row)
        self.active = intent

    def settle(self, observation):
        require(self._writing is None, "Observation carries no write authority")
        intent, v = self.active, self.active["view"]
        require(observation.status == "PRESENT" and not self.service.unconfirmed_contexts(),
                "UNKNOWN_PRODUCT_EFFECT: observe only; never retry the write")
        if v["operation"] == "PR":
            require(self.facts() == v["facts"], "Base/policy changed after PR creation")
            match = re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/([1-9][0-9]*)", observation.reference or "")
            require(match is not None, "Invalid observed PR URL")
            item = self.service.request("GET", self.target.api + "/pulls/" + match[1])
            require(type(item.get("id")) is int and item["id"] > 0 and type(item.get("node_id")) is str and 0 < len(item["node_id"]) <= 256, "Both actual PR identities required")
            identity = {"id": str(item["id"]), "node_id": item["node_id"], "number": int(match[1]),
                "repository_id": self.personal.repository_id, "url": observation.reference}
            row = self.record()
            require(row["pull"] in (None, identity), "Original PR identity changed")
            row["pull"] = identity; self.save(row)
            self.pull(expected_base=v["facts"]["base_sha"])
        self.journal.change(lambda e, s, t: e["actions"][intent["action"]].update(status="OBSERVED", observation=data(observation)))
        permit = typed(Permit, intent["reservation"])
        if v["operation"] == "MERGE":
            if self.c.record()["coordination"] is not None:
                self.c.conclude(permit, "personal:merge:" + observation.revision)
        else:
            _, _, item = self.guard._snapshot(self.c.task_id, intent["requirement"])
            measured = Observation(Outcome.PASS, ("personal:pr:" + intent["action"],), tuple(item["unresolved"]))
            if item["active"] is not None:
                self.guard.observe(self.c.task_id, intent["requirement"], permit, measured)
            else:
                require(item["last"] is not None and item["last"]["observation"] == data(measured), "Original PR accounting missing")
        intent["observation"] = data(observation); self.save_intent(intent)
        disposition = self.guard.inspect(self.c.task_id, intent["requirement"]).kind
        return {"status": ("PR_PRESENT" if disposition == DecisionKind.ALLOW else "PR_PRESENT_GUARD_STOPPED") if v["operation"] == "PR" else "MERGED_DELEGATED_VERIFIED",
            "progress_guard": disposition,
            "pull": self.record()["pull"], "revision": observation.revision, "next_issue": "NOT_AUTHORIZED", "runtime_qualification": "NOTRUN"}

    def ci_identity(self):
        pull = self.record()["pull"]
        return PullIdentity(pull["node_id"], pull["number"], pull["repository_id"])

    def checks(self):
        row = self.record()
        execution = next((r for r in reversed(row["execution"]) if r["view"]["operation"] == "CI"), None)
        return tuple(typed(RequiredCheck, c) for c in execution["checks"]) if execution is not None else ()

    @network_operation("product.execution_preview")
    @historical_operation
    def execution_preview(self, operation, *, approved=None, accept_native=False, confirm_no_checks=False):
        require(operation in ("CI", "REVIEW", "CORRECT"), "Unsupported one-issue execution")
        now = self.clock()
        if approved:
            m = TOKEN.fullmatch(approved)
            require(m is not None, "Exact execution proposal required")
            issued, expires, nonce = int(m[1]), int(m[2]), m[3]
        else:
            issued, expires, nonce = now, min(now + 300, self.personal.plan["window"]["expires_at"]), secrets.token_hex(16)
        require(0 <= issued <= now < expires and 0 < expires - issued <= 300
                and expires <= self.personal.plan["window"]["expires_at"], "Original execution window expired")
        bind_consent({"runtime_limits": self.service.limits.values(), "expires_at": expires}, now)
        with self.service.bounded():
            capture = {} if self.c.episode else None
            seal = self.local(_history_capture=capture)
            facts = self.facts()
            self.pull(expected_base=facts["base_sha"])
            if operation == "REVIEW":
                self.qualified()
            if operation == "CORRECT":
                require(self.correction_feedback() is not None, "Only actual in-scope failure/rejection permits correction")
            observed = self.c.memory.inspect()
            view = {"operation": operation, "runtime_limits": self.service.limits.values(),
                "setup": self.personal.intent["approval"], "revision": self.c.revision(),
                "source_tree": self.port._value("rev-parse", "HEAD^{tree}"), "source_ref": self.target.ref,
                "facts": facts, "review_binding": seal, "generation": observed["state"]["generation"],
                "administration": digest(administration(self.personal.feature)), "pull": self.record()["pull"],
                "journal": digest(self.record()), "workers": digest(self.c.workers.records()),
                "checkpoint": observed["local_head"], "accept_native_records": accept_native,
                "confirm_no_required_checks": confirm_no_checks,
                "validation": self.validation_binding() if operation == "REVIEW" else None,
                "original_relation_delta": getattr(self.c, "original_relation_delta", []),
                "issued_at": issued, "expires_at": expires, "nonce": nonce}
            if capture is not None:
                from .personal_episode import same_observation
                same_observation(capture["subject"], observed)
                view.update(self.history_binding(capture=capture))
            binding = self.transport.credential_binding
        return {"status": operation + "_PROPOSED", "result": view, "binding": binding, "approval": self.token(view, binding)}

    @network_operation("product.execute_ci", enabled=lambda self, operation, **k: operation == "CI")
    @historical_operation
    def execute(self, operation, *, reviewed, authorized, accept_native=False, confirm_no_checks=False):
        require(authorized is True, "Separately authorize this finite personal execution")
        with invocation_lock(self.c.memory.control):
            row = self.record()
            require(row is not None and row["pull"] is not None, "Original PR required")
            entry = next((r for r in row["execution"] if r["approval"] == reviewed), None)
            if entry is None:
                require(not self.c.episode or row["schema_version"] == 2, "Legacy execution is observation-only")
                proposal = self.execution_preview(operation, approved=reviewed, accept_native=accept_native, confirm_no_checks=confirm_no_checks)
                require(proposal["approval"] == reviewed, "Execution proposal changed")
                require(all(e["phase"] == "COMPLETE" for e in row["execution"]), "Reconcile the original local execution first")
                require(len(row["execution"]) < 8, "Finite execution history exhausted")
                entry = {"view": proposal["result"], "approval": reviewed, "binding": proposal["binding"],
                    "phase": "PREPARED", "checks": [], "result": None, "reservation": None}
                row["execution"].append(entry); self.save(row)
            require(entry["view"]["operation"] == operation and entry["approval"] == self.token(entry["view"], entry["binding"]), "Execution identity changed")
            if entry["phase"] == "COMPLETE":
                return {"status": "RETAINED_OBSERVATION", "observation": entry["result"],
                    "freshness": "NOT_REOBSERVED", "observed_revision": entry["view"]["revision"],
                    "execution": "NOT_REPEATED"}
            self.history_binding(view=entry["view"])
            require(entry["view"]["issued_at"] <= self.clock() < entry["view"]["expires_at"], "Original execution consent expired")
            with consent_scope(entry["view"]):
                return self._execute_selected(operation, entry, reviewed)

    def _execute_selected(self, operation, entry, reviewed):
        if operation == "CI":
            require(entry["view"]["revision"] == self.c.revision(), "Original CI consent source changed")
            result = self.observe_ci(entry)
        else:
            try:
                if operation == "REVIEW":
                    require(entry["view"]["revision"] == self.c.revision(), "Original review consent source changed")
                    with self.service.bounded():
                        require(self.facts() == entry["view"]["facts"], "Current product policy or base changed")
                        self.pull(expected_base=entry["view"]["facts"]["base_sha"])
                    require(self.validation_binding() == entry["view"]["validation"], "Approved CI binding changed")
                    worker = self.c.resume_product_review(entry)
                    if worker is None:
                        self.local()
                        context = self.review_context()
                        worker = self.c.workers.execute("product", context, self.personal.feature)
                    self.local()  # Normal approval must hold after accounting.
                    observed = self.c.workers.actual(worker, accounted=True)
                    row = self.record()
                    row["review"] = worker["request"]["id"]; self.save(row)
                    result = {"status": "PRODUCT_REVIEWED" if observed.result.approved else "REQUIRES_CORRECTION", "revision": self.c.revision()}
                else:
                    result = self.correct(entry)
            finally:
                self.c.stop_workers()
        row = self.record()
        retained = next(r for r in row["execution"] if r["approval"] == reviewed)
        retained.update(phase="COMPLETE", result=result); self.save(row)
        return result

    def validation_context(self, entry, permit):
        # A local observation receives no forge mutation capability. Reuse M3
        # against the exact newly approved current published source and policy.
        v = entry["view"]
        bind_consent(v, self.clock())
        view = {**v, "operation": "VALIDATE", "method": None}
        self.active = {"view": view, "binding": entry["binding"], "action": None}
        provider, task = self.provider(permit)
        plan = provider.plan(task, Request(Operation.VALIDATE))
        auth = self.authorize(provider, plan)
        rules = self.checks()
        policy = EvidencePolicy(plan.policy_digest, rules, v["issued_at"], v["expires_at"], result_maximum_age=300)
        policy = replace(policy, evidence=self.proof("project-validation/policy", policy_subject(plan, policy), "check-policy",
            {"plan": data(plan), "policy": data(policy)}))
        def attest(query, observed):
            return self.proof("project-validation/observation", observation_subject(query, observed), "native",
                {"query": data(query), "observation": data(observed)}, principal="personal:native-github")
        source = GitHubEvidenceSource(self.personal.plan["repository"]["name"], self.personal.repository_id,
            str(self.target.database_id), rules, self.read, attest=attest, clock=self.clock)
        validation = ProjectValidation(provider, task, policy, source, directory=self.personal.state / "product-checks",
            protected_roots=(self.personal.feature,), maximum_observations=self.personal.plan["window"]["maximum_check_observations"],
            clock=self.clock, retain_requests=True)
        return validation, auth

    def reserve_ci(self, entry):
        proof = self.proof("admission", self.guard.admission_subject(self.c.task_id, self.ci_specification), "admission", data(self.ci_specification))
        requirement = self.guard.register(self.c.task_id, self.ci_specification, proof)
        state, task, item = self.guard._snapshot(self.c.task_id, requirement)
        if entry["reservation"] is None:
            entry["reservation"] = {"requirement": requirement, "context": self.guard._context(state, task), "sequence": item["sequence"], "permit": None, "observation": None}
            self.save_execution(entry)
        reservation = entry["reservation"]
        require(reservation["requirement"] == requirement and reservation["context"] == self.guard._context(state, task), "Original CI reservation context changed")
        if reservation["permit"] is None:
            if item["active"] is not None:
                require(item["active"]["action"]["hypothesis"] == digest(entry["view"]), "Unrelated CI reservation")
                permit = Permit(item["active"]["id"], self.guard.inspect(self.c.task_id, requirement))
            else:
                require(item["sequence"] == reservation["sequence"], "CI guard history changed")
                permit = self.guard.begin(self.c.task_id, requirement, Action("personal:coordinator", ActionKind.CHECK,
                    digest(entry["view"]), "One actual project CI disposition", seconds=min(consent_limits(entry["view"]).operation_timeout_seconds, entry["view"]["expires_at"] - self.clock())))
            reservation["permit"] = data(permit); self.save_execution(entry)
        permit = typed(Permit, reservation["permit"])
        state, task, current = self.guard._snapshot(self.c.task_id, requirement)
        if current["active"] is None:
            require(entry["phase"] == "SUBMITTED" and reservation["observation"] is not None
                    and current["last"] is not None and current["last"]["context"] == reservation["context"]
                    and current["last"]["observation"] == reservation["observation"], "Original CI accounting missing")
        else:
            active = self.guard._active(state, task, current, permit.token)
            require(current["mode"] in ("normal", "running") and active["started"] <= self.clock() < active["deadline"]
                    and active["action"]["hypothesis"] == digest(entry["view"]), "Original CI permit expired or changed")
        return permit

    def charge_ci(self, entry):
        if getattr(self.c, "episode", False):
            self.c.charge_check("post-pr:" + digest(entry["view"]))
        run = self.c.record()
        reservation = entry["reservation"]
        if "observation_before" not in reservation:
            reservation["observation_before"] = run["observations"]
            self.save_execution(entry)  # Recover the same charge across either file checkpoint.
        before = reservation["observation_before"]
        require(type(before) is int and 0 <= before < self.personal.plan["window"]["maximum_check_observations"]
                and run["observations"] in (before, before + 1), "Original check-observation charge differs")
        if run["observations"] == before:
            run["observations"] += 1
            self.c.save(run)
        entry["phase"] = "SUBMITTED"
        self.save_execution(entry)  # Before the first identity read; no replay after lost delivery.

    def conclude_ci(self, entry, result):
        reservation = entry["reservation"]
        _, _, item = self.guard._snapshot(self.c.task_id, reservation["requirement"])
        if reservation["observation"] is None:
            outcome = Outcome.FAIL if result["status"] in ("FAIL", "ERROR", "TIMEOUT", "CANCELLED") else Outcome.PASS if result["status"] in ("PASS", "NOT_REQUIRED") else Outcome.UNKNOWN
            reservation["observation"] = data(Observation(outcome, ("personal:post-pr-ci:" + digest(result),), tuple(item["unresolved"])))
            self.save_execution(entry)
        if item["active"] is not None:
            self.guard.observe(self.c.task_id, reservation["requirement"], typed(Permit, reservation["permit"]), typed(Observation, reservation["observation"]))
        else:
            require(item["last"] is not None and item["last"]["observation"] == reservation["observation"], "Original CI accounting missing")
        self.c.allowed(reservation["requirement"])

    def observe_ci(self, entry):
        v = entry["view"]
        bind_consent(v)
        permit = self.reserve_ci(entry)
        if entry["phase"] == "SUBMITTED":
            # A consumed observation is never restarted, even when its caller
            # result was lost. Already-accounted results may reconcile locally.
            result = entry["result"] or {"status": "UNKNOWN", "qualified": False, "reason": "LOST_CHECK_DELIVERY",
                "revision": self.c.revision(), "observed_at": self.clock()}
            self.retain_ci(entry, result)
            self.conclude_ci(entry, result)
            return result
        with self.service.bounded():
            facts = self.facts()
            require(facts["policy"] == v["facts"]["policy"] and facts["base_sha"] == v["facts"]["base_sha"], "CI project policy/base changed")
            self.pull(expected_base=v["facts"]["base_sha"])
            if not v["facts"]["checks"]:
                require(not self.personal.plan["required_check_names"], "Unknown original check requirements")
                if self.personal.plan["check_requirements"] != "VERIFIED_ABSENT" and v.get("confirm_no_required_checks") is not True:
                    result = {"status": "UNKNOWN", "qualified": False, "reason": "PROJECT_CHECK_REQUIREMENTS_UNVERIFIED",
                        "revision": self.c.revision(), "policy": v["facts"]["policy"]["digest"], "observed_at": self.clock()}
                else:
                    result = {"status": "NOT_REQUIRED", "qualified": False, "verified_absence": True,
                        "revision": self.c.revision(), "policy": v["facts"]["policy"]["digest"], "observed_at": self.clock(),
                        "interpretation": "VERIFIED_ABSENT" if self.personal.plan["check_requirements"] == "VERIFIED_ABSENT" else "EXACT_OPERATOR_INTERPRETATION_PENDING_INDEPENDENT_PRODUCT_REVIEW"}
                entry["phase"] = "SUBMITTED"
                self.retain_ci(entry, result)
                self.conclude_ci(entry, result)
                return result
            self.charge_ci(entry)
            try:
                inventory = native_inventory(self.personal.plan["repository"]["name"], self.personal.repository_id,
                    self.target.ref, self.c.revision(), self.read)
                checks = prescribed_checks(v["facts"]["checks"], inventory,
                    accept_native_job_records=v["accept_native_records"])
                for check in checks:
                    required_origin = v["facts"]["policy"]["origins"].get(check.name)
                    require(required_origin is None or check.origin == "github-app:" + str(required_origin), "Native required check origin differs")
            except (ADPError, OSError):
                self.service._check_stop()  # Unknown process stop is a hard fence, not availability feedback.
                result = {"status": "UNKNOWN", "qualified": False, "reason": "NATIVE_CHECK_IDENTITY_UNAVAILABLE",
                    "revision": self.c.revision(), "observed_at": self.clock(), "policy": v["facts"]["policy"]["digest"]}
                self.retain_ci(entry, result)
                self.conclude_ci(entry, result)
                return result
            entry["checks"] = [data(replace(check, phase=Phase.AFTER_PR)) for check in checks]
            self.save_execution(entry)
        with self.service.bounded():
            validation, authorization = self.validation_context(entry, permit)
            gate = validation.observe(Phase.AFTER_PR, authorization=authorization, pull=self.ci_identity(), budget_ms=5000)
        result = {"status": str(gate.status), "qualified": gate.qualified, "gate": data(gate), "observed_at": self.clock(), "policy": v["facts"]["policy"]["digest"]}
        self.retain_ci(entry, result)
        self.conclude_ci(entry, result)
        return result

    def retain_ci(self, entry, result):
        entry["result"] = result
        self.save_execution(entry)  # Preserve disposition before concluding its permit.
        row = self.record()
        if not row["gates"] or row["gates"][-1] != result:
            require(len(row["gates"]) < self.personal.plan["window"]["maximum_check_observations"], "Original CI disposition history exhausted")
            row["gates"].append(result)
        if result["status"] != "PASS":
            row["review"] = None
        self.save(row)

    def save_execution(self, entry):
        row = self.record()
        row["execution"] = [entry if e["approval"] == entry["approval"] else e for e in row["execution"]]
        self.save(row)

    def qualified(self):
        row = self.record()
        require(row is not None and row["gates"], "Actual current post-PR evidence missing")
        latest = row["gates"][-1]
        self.c.allowed(requirement_id(self.ci_specification.contract, self.ci_specification.gate))
        require(0 <= self.clock() - latest.get("observed_at", -1000) <= 300, "Project evidence is stale")
        if latest["status"] == "NOT_REQUIRED":
            require(latest["verified_absence"] is True and latest["revision"] == self.c.revision(), "No-check policy is not verified")
            return latest
        require(latest["status"] == "PASS" and latest.get("qualified") is True, "Current exact PR CI is not qualified")
        gate = typed(EvidenceGate, latest["gate"])
        require(gate.qualified and gate.request.revision == self.c.revision() and gate.request.pull == self.ci_identity()
                and gate.request.repository_id == self.personal.repository_id, "Current exact PR CI is not qualified")
        state = read_private(self.personal.state / "product-checks" / (digest(gate.request) + ".json"))
        require(state["inflight"] is False and state["last_digest"] == gate.evidence.split(":", 1)[1]
                and state["request"] == digest(gate.request) and state["original_request"] == data(gate.request), "Actual #21 evidence receipt differs")
        return latest

    def validation_binding(self):
        latest = self.qualified()
        if latest["status"] == "NOT_REQUIRED":
            return digest({"status": "NOT_REQUIRED", "policy": latest["policy"], "revision": latest["revision"]})
        gate = typed(EvidenceGate, latest["gate"])
        return digest({"policy": latest["policy"], "revision": gate.request.revision, "pull": data(gate.request.pull),
            "results": [data(result) for result in gate.results], "checks": [data(c) for c in self.checks()]})

    def review_context(self):
        self.qualified()
        context = self.c.context("code")
        return {**context, "purpose": "product", "criterion": self.personal.plan["criterion"],
            "pull": self.record()["pull"], "validation_binding": self.validation_binding(),
            "actual_post_pr_evidence": self.record()["gates"][-1],
            "original_relation_delta": getattr(self.c, "original_relation_delta", [])}

    def verify_review(self):
        row = self.record()
        require(row is not None and row["review"] is not None, "Independent current product review missing")
        worker = self.c.worker(row["review"])
        current = self.review_context()
        # A reobservation may have a new query nonce but must prove identical
        # native result identities/provenance/outcomes and current policy.
        require(worker["purpose"] == "product" and worker["request"]["revision"] == self.c.revision()
                and {k: v for k, v in worker["context"].items() if k != "actual_post_pr_evidence"}
                == {k: v for k, v in current.items() if k != "actual_post_pr_evidence"}, "Changed SHA/checks invalidate independent review")
        self.c.workers.actual(worker, approval=True, accounted=True)

    def native_reviews(self, item, facts):
        rows = self.forge.reviews(self.record()["pull"], self.c.revision())
        require(rows is not None and not any(r["state"] in ("CHANGES_REQUESTED", "PENDING") for r in rows), "Incomplete or rejected native review")
        require(type(item.get("user")) is dict, "Actual PR author unknown")
        author = item["user"].get("id")
        require(type(author) is int and author > 0, "Actual PR author unknown")
        candidates = [r for r in rows if r["state"] == "APPROVED" and r.get("commit_id") == self.c.revision()
                    and r["user"]["id"] not in (author, self.personal.plan["owner"]["account_id"])]
        eligible = []
        require(len(candidates) <= 16, "Native eligible review inventory exceeds bounds")
        if facts["policy"]["native_reviews"]:
            for row in candidates:
                login = row["user"].get("login")
                require(type(login) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login), "Native reviewer login unavailable")
                response = self.read.get(self.target.api + "/collaborators/" + login + "/permission")
                permission = response.body
                require(response.status == 200 and type(permission) is dict
                        and type(permission.get("user")) is dict and type(permission["user"].get("id")) is int
                        and permission["user"]["id"] > 0 and permission["user"]["id"] == row["user"]["id"], "Native reviewer eligibility unknown")
                if permission.get("permission") in ("write", "maintain", "admin"):
                    eligible.append(row)
        require(len(eligible) >= facts["policy"]["native_reviews"], "Required independent native approvals missing")
        self._native = eligible
        return eligible

    def review_principals(self):
        row = self.record()
        return {"worker:" + row["review"]} | {"github-user:" + str(r["user"]["id"]) for r in getattr(self, "_native", [])}

    def check_matches(self, check):
        latest = self.qualified()
        if latest["status"] == "NOT_REQUIRED":
            return False
        gate = typed(EvidenceGate, latest["gate"])
        return any(check.name == r.name and check.revision == r.revision and check.provider == r.provider
            and check.origin == r.origin and check.run_id == r.run_id and check.attempt_id == r.attempt_id
            and check.status == str(r.status) and check.denominator == r.denominator and check.counts == r.counts
            and check.quarantined == r.quarantined and check.request_digest == digest(gate.request)
            and check.observation_digest == gate.evidence.split(":", 1)[1] for r in gate.results)

    def qualifications(self, provider, plan):
        self.verify_review()
        latest = self.qualified()
        now = self.clock()
        reviews = []
        for principal in sorted(self.review_principals()):
            r = Review(principal, self.c.revision(), True, now, min(now + 300, self.personal.plan["window"]["expires_at"]))
            reviews.append(replace(r, evidence=self.proof("policy/review", provider.review_subject(plan, r), "review",
                {"plan": data(plan), "value": data(r)}, principal=principal)))
        if latest["status"] == "NOT_REQUIRED":
            return Qualifications(reviews=tuple(reviews))
        gate = typed(EvidenceGate, latest["gate"])
        results = []
        for r in gate.results:
            c = ProjectCheck(r.name, r.revision, str(gate.request.phase), digest(gate.request), gate.evidence.split(":", 1)[1],
                r.provider, r.origin, r.run_id, r.attempt_id, str(r.status), r.denominator, r.counts, r.quarantined,
                latest["observed_at"], min(latest["observed_at"] + 300, self.personal.plan["window"]["expires_at"]))
            results.append(replace(c, evidence=self.proof("policy/project-check", provider.project_check_subject(plan, c), "project-check", {"plan": data(plan), "value": data(c)})))
        q = ProjectQualifications(tuple(results), tuple(reviews), tuple((c.name, str(c.phase)) for c in self.checks()))
        return replace(q, policy_evidence=self.proof("policy/project-validation", provider.project_policy_subject(plan, q), "project-policy", {"plan": data(plan), "value": data(q)}))

    def delegation(self, plan):
        v = self.active["view"]
        p = DelegationProfile(self.personal.repository_id, self.personal.plan["issue_id"], self.c.task_id, plan.task.iteration,
            self.target.ref, v["facts"]["base_ref"], self.c.revision(), plan.policy_digest, self.personal.plan["original_digest"],
            ("MERGE",), "DELEGATED", (v["method"],), ENVELOPE, v["issued_at"], v["expires_at"])
        return replace(p, evidence=self.proof("github-product/delegation", delegation_subject(p), "delegation", data(p)))

    def correction_feedback(self):
        row = self.record()
        if row["gates"] and row["gates"][-1]["status"] in ("FAIL", "ERROR", "TIMEOUT", "CANCELLED"):
            return row["gates"][-1]
        if row["review"] is not None:
            worker = self.c.worker(row["review"])
            if worker["observation"]["result"]["approved"] is False:
                return worker["observation"]["result"]
        return None

    def correct(self, entry):
        row = self.record()
        if row["correction"] is None:
            feedback = self.correction_feedback()
            require(feedback is not None and self.c.record()["coordination"] is None
                    and all(a["status"] == "OBSERVED" for a in self.journal.inspect()["state"]["execution"]["actions"].values()
                        if a["task_key"] == key(self.c.task_id)), "Reconcile uncertain effects before correction")
            require(sum(r["purpose"] == "develop" for r in self.c.workers.records()) < self.personal.plan["window"]["developers"], "Original Developer budget exhausted")
            require(sum(r["purpose"] in ("code", "product") for r in self.c.workers.records())
                    < self.personal.plan["window"]["code_reviewers"], "Original independent role budget exhausted before correction")
            row["correction"] = {"from": self.c.revision(), "feedback": feedback, "approval": entry["approval"]}
            original = read_private(self.personal.state / "publication.json")
            require(original["view"]["revision"] == self.c.revision(), "Original publication receipt differs")
            row["publications"] = [{"revision": self.c.revision(), "action": original["action_id"], "legacy": True}]
            row["review"] = None; self.save(row)
        require(row["correction"]["approval"] == entry["approval"], "Retain the original correction intent")
        run = self.c.record()
        if run["phase"] == "LOCAL_DRAFT_CODE_REVIEWED" and run["revision"] == row["correction"]["from"]:
            run["feedback"].append(row["correction"]["feedback"])
            run.update(phase="DEVELOP", code_review=None)
            self.c.save(run)
        result = self.c._run()
        return {"status": "CORRECTED_REQUIRES_NEW_PUBLICATION" if self.c.revision() != row["correction"]["from"] else result["status"],
            "revision": self.c.revision(), "old_review_and_ci": "HISTORICAL", "next_issue": "NOT_AUTHORIZED"}

    def publication_backend(self, *, transport=None):
        original = read_private(self.personal.state / "publication.json")
        if original["view"]["revision"] == self.c.revision():
            return PersonalPublication(self.c, transport=transport)
        from .personal_republication import RevisionPublication
        return RevisionPublication(self, transport=transport)

    def refresh_merge_ci(self, permit):
        """Exactly one fresh #21 observation, charged to the original budget."""
        original_active = self.active
        v = original_active["view"]
        row = self.record()
        if not v["facts"]["checks"]:
            self.qualified()
            return
        previous = next(e for e in reversed(row["execution"]) if e["view"]["operation"] == "CI")
        view = {**v, "operation": "CI", "accept_native_records": previous["view"]["accept_native_records"]}
        approval = self.token(view, original_active["binding"])
        entry = next((e for e in row["execution"] if e["approval"] == approval), None)
        if entry is None:
            require(len(row["execution"]) < 8, "Finite execution history exhausted")
            entry = {"view": view, "approval": approval, "binding": original_active["binding"],
                "phase": "PREPARED", "checks": [], "result": None, "reservation": None}
            row["execution"].append(entry); self.save(row)
        try:
            require(entry["phase"] == "PREPARED", "A cached merge CI result cannot authorize a later dispatch")
            result = self.observe_ci(entry)
            entry.update(phase="COMPLETE", result=result); self.save_execution(entry)
        finally:
            self.active = original_active
        if result["status"] != "PASS":
            self.c.conclude(permit, "personal:merge-ci:" + digest(result), Outcome.FAIL if result["status"] in ("FAIL", "ERROR", "TIMEOUT", "CANCELLED") else Outcome.UNKNOWN)
            raise PersonalBlocked("CURRENT_CI_NOT_QUALIFIED", "Use the actual current project result as same-ticket feedback while original budgets remain; no merge was submitted.", status="REQUIRES_CORRECTION" if result["status"] in ("FAIL", "ERROR") else "PENDING_VALIDATION")
        require(self.validation_binding() == v["validation"], "Changed current CI invalidates product review and merge approval")

    @network_operation("product.status")
    @historical_operation
    def status(self, *, manual_method="merge"):
        row = self.record()
        if row is None:
            return {"status": "NOT_DELEGATED", "merge": "MANUAL", "runtime_qualification": "NOTRUN"}
        # Resource caps only, before choosing a current native observation.
        # Do not reinterpret expired historical facts as fresh authorization.
        for intent in row["intents"]:
            bind_consent(intent["view"])
        with self.service.bounded():
            self.c.check_administration(self.c.record())
            self.service._check_stop()
            require({r.name: r.revision for r in self.service.refs()}.get(self.target.ref) == self.c.revision(), "Published current ref unavailable")
            if row["pull"] is None:
                return {"status": "PRODUCT_EFFECT_UNCERTAIN", "mutation_retry": "NOT_AUTHORIZED"}
            item = self.pull(allow_merged=True)
            if item["merged"]:
                require(manual_method in ("merge", "squash"), "Supported manual merge method required")
                actions = self.journal.inspect()["state"]["execution"]["actions"]
                intent = next((r for r in reversed(row["intents"]) if r["view"]["operation"] == "MERGE" and r["action"] in actions), None)
                original = next(r for r in row["intents"] if r["view"]["operation"] == "PR")
                v = intent["view"] if intent else original["view"]
                payload = {"pull": {k: row["pull"][k] for k in ("id", "number", "repository_id", "url")},
                    "revision": self.c.revision(), "head_ref": self.target.ref, "base_ref": v["facts"]["base_ref"],
                    "expected_base": v["facts"]["base_sha"], "source_tree": self.port._value("rev-parse", "HEAD^{tree}"),
                    "method": v["method"] if intent else manual_method, "envelope": ENVELOPE}
                observed = self.forge.observe(intent["action"] if intent else original["action"], Operation.MERGE, payload, attempted=True)
                require(type(item.get("merged_by")) is dict, "External merge actor unknown")
                actor = item["merged_by"].get("id")
                require(observed.status == "PRESENT" and type(actor) is int and actor > 0, "External merge result/actor is UNKNOWN")
                unresolved = intent is not None and (intent["observation"] is None or actions[intent["action"]]["status"] != "OBSERVED")
                qualified = intent is not None
                if intent is None:
                    try:
                        self.qualified(); self.verify_review()
                        qualified = True
                    except (ADPError, OSError, KeyError, TypeError, ValueError):
                        qualified = False
                return {"status": "MERGED_WITH_UNRESOLVED_DELEGATED_INTENT" if unresolved else "MERGED_DELEGATED_VERIFIED" if intent else "MERGED_EXTERNALLY_VERIFIED" if qualified else "EXTERNAL_MERGE_OBSERVED_UNQUALIFIED",
                    "qualification": "CURRENT_BOUND_RECEIPTS" if qualified else "UNKNOWN",
                    "attribution": "UNKNOWN" if unresolved else "RECORDED_DELEGATED_EFFECT" if intent else "EXTERNAL_EFFECT",
                    "actor": "github-user:" + str(actor), "physical_human_identity": "NOT_ASSERTED", "revision": observed.revision,
                    "pull": row["pull"], "next_issue": "NOT_AUTHORIZED", "runtime_qualification": "NOTRUN"}
            state = "PR_DRAFT" if item["draft"] else "WAITING_HUMAN_APPROVAL"
            return {"status": state, "pull": row["pull"], "revision": self.c.revision(),
                "ci": row["gates"][-1]["status"] if row["gates"] else "NOTRUN", "merge": "MANUAL",
                "mutation_retry": "NOT_AUTHORIZED", "runtime_qualification": "NOTRUN"}
