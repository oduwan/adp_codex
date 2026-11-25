"""One explicitly approved local personal draft, no forge or network Git writes.

The existing signed Conductor backend is unchanged. This small coordinator is
the single M1 writer and composes the real guard, policy, Git CAS, runtime and
project-evidence ports directly. Code review never implies product acceptance.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import time

from .codex_runtime import CodexExecRuntime
from .config import Config
from .discovery_schema import digest, typed
from .discovery_types import Identity
from .enrollment import local_checkout
from .errors import ADPError, GitError
from .execution_memory import invocation_lock
from .execution_policy import ReservedSafety
from .execution_ports import GitExecutionPort, index_digest
from .execution_types import RuntimeStatus
from .execution_containment import admin_seal, source_seal
from .git import author, git, value
from .guard import ProgressGuard
from .guard_types import Action, ActionKind, DecisionKind, Observation, Outcome, Permit, Requirement, data
from .personal_authority import PersonalAuthority
from .personal_enrollment import governance, selection
from .personal_git import administration
from .personal_storage import INTENT, LIMIT, PersonalBlocked, create_private, read_private
from .personal_workers import PersonalWorkers
from .policy import PolicyProvider
from .policy_adapters import GitPolicyAdapter
from .policy_types import Authorization, Effect, Operation, Permission, RepositorySnapshot, Request, Rules, SourceClaim, SourceKind, Task
from .project_validation import ProjectValidation
from .project_validation_github import GitHubEvidenceSource
from .project_validation_types import EvidencePolicy, Phase, RequiredCheck
from .schema import encode, fields, key, require
from .storage import atomic


class LocalPolicyAdapter(GitPolicyAdapter):
    """Inspect actual local Git state; remote refs stay honestly UNKNOWN."""
    def _remote_refs(self, config):
        raise GitError("Personal local-draft mode does not contact a Git remote")


class PersonalCoordinator:
    def __init__(self, personal, transport, ci_transport, *, runtime=None, clock=None):
        self.personal, self.transport, self.ci_transport = personal, transport, ci_transport
        self.clock = clock or (lambda: int(time.time()))
        self.memory = personal.memory()
        self.runtime = runtime or CodexExecRuntime(personal.state / "runtime")
        self.task_id = "personal:" + digest({"repository": personal.repository_id, "issue": personal.plan["issue_id"]})
        self.episode = personal.intent["kind"] == "ACCOUNTING_EPISODE"
        if self.episode:
            self.task_id = personal.task_id
        self.authority = PersonalAuthority(self)
        self.guard = ProgressGuard(self.memory, authority=self.authority, clock=self.clock)
        self.workers = PersonalWorkers(self)
        self.path = personal.state / "run.json"
        self.track = None
        if (personal.state / "track-link.json").exists():
            from .personal_track import PersonalTrack
            self.track = PersonalTrack(self)

    def live(self):
        # Recheck immutable retained consent and the actual owner. Do not rerun
        # Git configuration discovery for every nested evidence verification.
        p = self.personal.plan
        if self.track is not None:
            self.track.require_attachment()
        if self.episode:
            _, _, subject = self.personal._active_view(memory=self.memory, allow_expired=False, now=self.clock())
        else:
            require(read_private(self.personal.directory / INTENT) == self.personal.intent
                    and read_private(Path(p["effects"]["marker"])) == {"schema_version": 1,
                        "directory": str(self.personal.directory), "approval": self.personal.intent["approval"]}
                    and p["window"]["issued_at"] <= self.clock() < p["window"]["expires_at"], "Personal consent changed or expired")
        observed = self.memory.inspect()
        require(observed["health"] == "SYNCED" and observed["local_owner"], "The original synchronized M1 owner is required")
        if self.episode:
            from .personal_episode import same_observation
            same_observation(subject, observed)
        row = self.record()
        require(row is None or row["generation"] == observed["state"]["generation"], "Personal execution generation changed")
        self.check_administration(row)
        require(self.personal.intent["phase"] == "ENROLLED", "Complete the original personal setup first")
        if self.episode:
            self.episode_fence()
        return observed

    def episode_fence(self):
        """Final nonblocking consent/owner check after full evidence validation."""
        from .accounting_policy import entry
        window = self.personal.plan["window"]
        require(window["issued_at"] <= self.clock() < window["expires_at"]
                and not (self.personal.root.state / "accounting-recovery" / "revoked" /
                         (digest(self.personal.intent["approval"]) + ".json")).exists(), "Episode consent expired or revoked")

    def seconds_left(self):
        self.live()
        return self.personal.plan["window"]["expires_at"] - self.clock()

    def record(self):
        row = read_private(self.path, optional=True)
        if row is not None:
            fields(row, "schema_version approval generation phase revision original_review developer candidate code_review actions coordination gates feedback observations feature_administration")
            require(row["schema_version"] == 1 and type(row["schema_version"]) is int
                    and row["approval"] == self.personal.intent["approval"]
                    and type(row["generation"]) is int and row["generation"] > 0,
                    "Personal execution journal or generation changed")
            require(row["phase"] in ("SCOPE", "FEATURE", "FEATURE_TRANSITION", "DEVELOP", "STAGE", "CANDIDATE", "COMMIT",
                    "SOURCE_TRANSITION", "CODE", "CHECKS", "CHECKS_TRANSITION", "CANDIDATE_REJECTED", "LOCAL_DRAFT_CODE_REVIEWED")
                    and type(row["observations"]) is int and 0 <= row["observations"] <= self.personal.plan["window"]["maximum_check_observations"]
                    and type(row["feedback"]) is list and len(row["feedback"]) <= 8
                    and type(row["gates"]) is list and len(row["gates"]) <= 3, "Malformed personal phase or finite accounting")
        return row

    def check_administration(self, row=None, *, _reader=None):
        reader = _reader or administration
        if self.episode and _reader is None:
            from .personal_history_product_git import administration as reader
        require(reader(Path(self.personal.plan["checkout"]["path"])) == self.personal.plan["administration"],
                "Original product Git administration changed")
        if row is not None and row["feature_administration"] is not None:
            require(reader(self.personal.feature) == row["feature_administration"], "Feature Git administration changed")

    def save(self, row):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        self.live()
        create_private(self.personal.state)
        atomic(self.path, encode(row, LIMIT))

    def revision(self):
        row = self.record()
        return row["revision"] if row else self.personal.plan["checkout"]["head"]

    def source_origin(self, *, historical=False):
        row = self.record()
        if row is not None and row["developer"] is not None:
            worker = self.worker(row["developer"])
            require(worker["purpose"] == "develop" and worker["observation"]["result"]["outcome"] == "PASS",
                    "Source origin must be its actual successful unapproved Developer")
            if historical:
                from .personal_history import retained
                retained(self.runtime, worker)
                current = self.memory.inspect()
                job = current["tasks"][key(self.task_id)]["assignments"].get(worker["assignment"]["assignment_id"])
                require(worker["phase"] == "ACCOUNTED" and worker["observation"]["result"]["approved"] is False
                        and worker["observation"]["result"]["criteria"] == [] and job is not None
                        and job["status"] == "accepted" and job["result"] == self.workers.result(worker)
                        and job["worker"] == "worker:" + row["developer"]
                        and job["generation"] == worker["request"]["generation"] == current["state"]["generation"]
                        and job["source_revision"] == worker["request"]["revision"], "Historical source author evidence differs")
            else:
                self.workers.actual(worker, accounted=True)
            return {"kind": "DEVELOPER", "label": row["developer"], "authors": ["worker:" + row["developer"]],
                    "source": worker["result_source"]}
        require(self.episode, "An actual Developer or qualified retained candidate origin is required")
        from .personal_adoption import adopted
        return adopted(self, historical=historical)

    def source_authors(self):
        if not self.episode:
            # Existing M7 proves the exact current code Reviewer separately.
            # Its Developer author was at the precommit SHA, not the active
            # MERGE reservation's committed SHA. Preserve that author contract.
            identifier = self.record()["developer"]
            require(type(identifier) is str, "Actual source author is missing")
            return ("worker:" + identifier,)
        return tuple(self.source_origin(historical=True)["authors"])

    def assign_worker(self, row):
        if not self.episode:
            return self.memory.assign(self.task_id, "worker:" + row["request"]["id"])
        from .accounting_policy import consume_request
        from .storage import locked
        with locked(self.memory.control):
            self.live()
            head, state, tasks = self.memory._start()
            consume_request(state, key(self.task_id), row["request"]["id"], row["purpose"])
            result = self.memory._assign(state, tasks, self.task_id, "worker:" + row["request"]["id"])
            self.memory._checkpoint(head, state, tasks, _fence=self.episode_fence)
            return result

    def charge_check(self, identifier):
        if not self.episode:
            return
        from .accounting_policy import entry
        from .storage import locked
        with locked(self.memory.control):
            self.live()
            head, state, tasks = self.memory._start()
            usage = entry(state)["usage"]
            hashed = digest(identifier)
            if hashed not in usage["check_ids"]:
                usage["check_ids"].append(hashed)
                usage["checks"] += 1
                self.memory._checkpoint(head, state, tasks, _fence=self.episode_fence)

    def specification(self, purpose):
        if purpose == "feature":
            return Requirement(self.task_id, "local-feature", ("feature-prepared",))
        semantic = purpose in ("original", "candidate")
        return Requirement(self.task_id, "semantic-" + purpose if semantic else "product",
                           (purpose,) if semantic else (self.personal.plan["criterion"],))

    def requirement(self, purpose):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        spec = self.specification(purpose)
        proof = self.authority.operator_evidence("admission", self.guard.admission_subject(self.task_id, spec),
            {"task_id": self.task_id, "requirement": data(spec)})
        return self.guard.register(self.task_id, spec, proof)

    def review_requirement(self):
        """Verification cannot admit/repair a missing episode baseline."""
        if not self.episode:
            return self.requirement("develop")
        from .guard_schema import requirement_id
        spec = self.specification("develop")
        identifier = requirement_id(spec.contract, spec.gate)
        _, task, item = self.guard._snapshot(self.task_id, identifier)
        expected = data(spec)
        require(task["key"] in item["tasks"] and all(item[n] == expected[n]
                for n in ("contract", "gate", "acceptance", "dependencies", "limits")),
                "The existing exact episode review baseline is required")
        return identifier

    def allowed(self, requirement):
        decision = self.guard.inspect(self.task_id, requirement)
        if decision.kind != DecisionKind.ALLOW:
            code = "PERSONAL_FORENSIC_RECOVERY_UNSUPPORTED" if decision.kind == DecisionKind.FORENSIC_REQUIRED else "PROGRESS_GUARD_STOPPED"
            raise PersonalBlocked(code, "Follow the retained M2 disposition; this minimal backend cannot bypass or automatically replace its forensic/terminal recovery boundary.")

    def fresh(self):
        self.live()
        plan = self.personal.plan
        observation, owner = selection(Path(plan["checkout"]["path"]), plan["checkout"]["remote"], self.personal.repository_id, self.transport)
        original = [i for i in observation.snapshot.issues if i.identity.issue_id == plan["issue_id"]]
        expected_checkout = dict(plan["checkout"])
        if not plan["feature"]["prepare"] and self.record() is not None:
            expected_checkout["head"] = self.revision()
            current = self.record()["actions"].get("commit:" + (self.record()["developer"] or ""))
            if current is not None and observation.checkout["head"] != expected_checkout["head"]:
                observed = GitExecutionPort(Config.discover(Path(expected_checkout["path"]), remote=plan["checkout"]["remote"],
                    repository_id=self.personal.repository_id), bound_git_directory=Path(plan["administration"]["directory"]["path"])).observe(current)
                require(observed.status == "PRESENT" and observed.revision == observation.checkout["head"],
                        "Source advanced without the exact current bound commit")
                expected_checkout["head"] = observed.revision
        require(observation.checkout == expected_checkout and owner == plan["owner"] and len(original) == 1
                and self.original_matches(original[0])
                and digest(governance(Path(plan["checkout"]["path"]))) == plan["governance_digest"],
                "The original source, issue, native prerequisites, ownership or governance changed")
        if self.track is not None:
            self.track.prerequisites(observation)
            if self.record() is None or self.record()["phase"] in ("SCOPE", "FEATURE", "FEATURE_TRANSITION"):
                self.track.native_base(self)
        else:
            require(not plan["native_prerequisites"], "Native prerequisites need independent acceptance before this task can be READY")
        if self.record() is None or self.record()["phase"] in ("SCOPE", "FEATURE", "FEATURE_TRANSITION"):
            require(not value(Path(plan["checkout"]["path"]), "status", "--porcelain", "--untracked-files=all"),
                    "Original checkout changed before scope admission or feature preparation")
        # Protections and declared requirements may tighten; never discard them.
        current_rules = observation.facts["branch_rules"]
        require(current_rules == plan["branch_rules"], "Branch requirements changed; preserve this enrollment and obtain an operator disposition")
        self.live()
        return observation

    def original_matches(self, issue):
        return digest(data(issue)) == self.personal.plan["original_digest"]

    def accounting_material(self):
        return read_private(self.personal.root.state / "accounting-recovery" / "intent.json")["blueprint"]["material"]

    def context(self, purpose):
        plan, row = self.personal.plan, self.record()
        context = {"purpose": purpose, "repository_id": self.personal.repository_id,
            "original": self.personal.intent["original"], "governance": self.personal.intent["governance"],
            "paths": plan["paths"], "feature_branch": plan["feature"]["branch"],
            "commit_message": plan["commit_message"], "commit_body": plan["commit_body"],
            "prescribed_checks": plan["required_check_names"], "check_knowledge": plan["check_requirements"],
            "branch_rules": plan["branch_rules"], "scope_limit": "Only the complete original ticket; no added features, tests or infrastructure.",
            "supported_operations": "Read-only original review; then local feature preparation, edits, staging and commit. Manual merge; no push, PR, issue edits or reporting.",
            "evidence_limit": "Native GitHub checks only; any required precommit check unsupported by this port MUST block COMMIT. Never waive a governance requirement. Missing/pending/403 are not PASS or absence.",
            "revision": self.revision()}
        if purpose != "original":
            context["feedback"] = row["feedback"]
            context["project_gates"] = row["gates"]
        if purpose in ("candidate", "code"):
            context["developer"] = row["developer"]
            if self.episode:
                context["source_origin"] = self.source_origin()
            root = self.personal.feature
            context["diff"] = git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary",
                *( ("--cached",) if purpose == "candidate" else (self.personal.plan["checkout"]["head"], "HEAD")), limit=16384).decode("utf-8", "strict")
            context["index_digest"] = index_digest(root)
        if purpose == "original" and self.track is not None:
            from .personal_track_preparation import semantic_bundle
            context["track_preparation"] = semantic_bundle(self.track)
        if self.episode:
            from .personal_recovery import candidate_diff
            context["accounting_episode"] = {"policy": "ACCOUNTING_EXPIRY_CONTINUATION", "episode": self.personal.descriptor["episode"],
                "historical_terminal": "PERMANENT_STOP_UNSAFE_OVERDUE_ACCOUNTING", "worker_timeliness": "UNKNOWN",
                "candidate_material": self.personal.descriptor["base"]["choices"]["paths"],
                "adoption_scope": self.accounting_material(),
                "source_acceptance": "UNACCEPTED; new staged-diff and committed-SHA review and actual project CI required"}
            if purpose == "original":
                context["accounting_episode"]["candidate_source"] = candidate_diff(self.personal.root)
        return context

    def worker(self, request_id):
        matches = [row for row in self.workers.records() if row["request"]["id"] == request_id]
        require(len(matches) == 1, "The genuine purpose-bound worker record is missing")
        return matches[0]

    def original_approval(self):
        row = self.record()
        require(row is not None and row["original_review"] is not None, "Independent original-scope/policy admission is required")
        review = self.worker(row["original_review"])
        require(review["purpose"] == "original" and review["context"] == {**self.context("original"), "revision": self.personal.plan["checkout"]["head"]},
                "Original scope/policy approval context differs")
        self.workers.actual(review, approval=True, accounted=True)
        return review

    def rules(self):
        p = self.personal.plan
        # Exact task choices, NOT invented repository-wide conventions.
        return Rules(permissions=tuple(Permission(Operation(op), Effect.ALLOW) for op in p["operations"]),
            branch_template=(p["feature"]["branch"].rpartition("/")[0] + "/" if "/" in p["feature"]["branch"] else "") + "{slug}",
            subject_template="{summary}",
            body_template=p["commit_body"].replace("{", "{{").replace("}", "}}"), subject_limit=256,
            checks=tuple(p["required_check_names"]), reviews=1)

    def source_subject(self, claim, *, typed_snapshot):
        return PolicyProvider(None).source_subject(claim, typed(RepositorySnapshot, typed_snapshot))

    def provider(self, root, permit, purpose="develop"):
        cfg = Config.discover(root, remote=self.personal.plan["checkout"]["remote"], repository_id=self.personal.repository_id)
        documents = self.personal.intent["governance"]
        require(len(documents) <= 15, "The supported bounded personal policy inventory is exceeded")
        require(digest(governance(root)) == self.personal.plan["governance_digest"], "Project governance changed")
        adapter = LocalPolicyAdapter(cfg, governance=tuple(d["path"] for d in documents), fingerprint_worktree=True)
        provider = PolicyProvider(adapter, authority=self.authority, safety=ReservedSafety(self.guard, permit), clock=self.clock)
        snapshot = adapter.inspect()
        expires, issued = (self.personal.plan["window"][n] for n in ("expires_at", "issued_at"))
        claims = [SourceClaim(SourceKind.OPERATOR, "personal:exact-local-choices", digest(self.personal.plan), self.rules(), issued, expires)]
        claims += [SourceClaim(d.kind, d.reference, d.digest, self.rules(), issued, expires) for d in snapshot.documents]
        provider.sources = tuple(self.authority.source(provider, claim, snapshot) for claim in claims)
        observed = self.memory.inspect()
        memory_task = observed["tasks"][key(self.task_id)]
        requirement = permit.decision.baseline.requirement_id
        item = self.guard._snapshot(self.task_id, requirement)[2]
        task = Task(self.personal.repository_id, self.task_id, self.personal.plan["feature"]["branch"].split("/")[-1], memory_task["source_revision"],
            value(root, "symbolic-ref", "HEAD"), requirement, observed["state"]["generation"],
            observed["state"]["progress_guard"]["task_epochs"][key(self.task_id)], memory_task["iteration"],
            tuple(item["authors"]) or ("personal:coordinator",))
        return provider, task

    def validate_operation(self, plan):
        self.live()
        self.original_approval()
        p = self.personal.plan
        require(plan.policy_effect == Effect.ALLOW and plan.task.repository_id == self.personal.repository_id
                and plan.task.task_id == self.task_id and plan.task.generation == self.memory.inspect()["state"]["generation"]
                and plan.request.operation in p["operations"], "Personal operation is not delegated")
        op, payload = plan.request.operation, plan.payload
        root = Path(p["checkout"]["path"]) if op == Operation.BRANCH else self.personal.feature
        require(value(root, "rev-parse", "HEAD") == plan.task.revision and author(root) == tuple(p["author"]),
                "Operation source or Git author differs")
        if op == Operation.BRANCH:
            require(p["feature"]["prepare"] and plan.target_ref == "refs/heads/" + p["feature"]["branch"]
                    and payload.start_revision == p["checkout"]["head"], "Feature operation differs from the exact approval")
        else:
            require(plan.task.source_ref == "refs/heads/" + p["feature"]["branch"], "Personal operation targets another branch")
        if op in (Operation.EDIT, Operation.STAGE, Operation.INSPECT):
            require(all(any(path == allowed or path.startswith(allowed + "/") for allowed in p["paths"]) for path in plan.request.paths),
                    "Operation exceeds the original admitted paths")
        if op == Operation.COMMIT:
            require(payload.subject == p["commit_message"] and payload.body == p["commit_body"], "Commit message differs from the approved local choice")
            candidate = self.worker(self.record()["candidate"])
            require(candidate["purpose"] == "candidate" and candidate["context"] == self.context("candidate"), "Staged scope review is stale")
            self.workers.actual(candidate, approval=True, accounted=True)

    def authorize_worker(self, row):
        self.fresh()
        self.workers.fence()
        request = row["request"]
        if self.track is not None:
            require(not self.track.completion_path(typed(Identity, self.track.link["identity"])).exists(),
                    "An accepted original cannot restart development")
        require(self.clock() < request["deadline"] and request["revision"] == self.revision(), "Worker source/deadline differs")
        if row["purpose"] == "original":
            require(Path(request["workspace"]) == Path(self.personal.plan["checkout"]["path"]), "Original review workspace differs")
            return  # Explicitly approved read-only inspection, before interpretation.
        if row["purpose"] == "develop":
            prior = self.record()["developer"]
            if prior is None:
                if self.episode and (self.personal.state / "adoption.json").exists():
                    require(source_seal(self.personal.feature) == self.source_origin()["source"], "Adopted candidate source changed")
                else:
                    require(not value(self.personal.feature, "status", "--porcelain", "--untracked-files=all"),
                            "First Developer needs the approved pristine feature checkout")
            else:
                require(source_seal(self.personal.feature) == self.worker(prior)["result_source"],
                        "Source changed outside the retained previous Developer result")
        provider, task = self.provider(self.personal.feature, typed(Permit, row["permit"]), row["purpose"])
        operation = Request(Operation.EDIT if row["purpose"] == "develop" else Operation.INSPECT,
                            summary=request["id"], paths=tuple(self.personal.plan["paths"]))
        plan = provider.plan(task, operation)
        require(provider.decide(plan, self.authority.authorize(plan)).effect == Effect.ALLOW, "M3 refused the exact worker operation")

    def effect(self, name, root, permit, request):
        self.fresh()
        row = self.record()
        cfg = Config.discover(root, remote=self.personal.plan["checkout"]["remote"], repository_id=self.personal.repository_id)
        port = GitExecutionPort(cfg, bound_git_directory=Path(administration(root)["directory"]["path"]))
        existing = row["actions"].get(name)
        if existing is not None:
            observation = port.observe(existing)
            require(observation.status in ("PRESENT", "ABSENT"), "Git effect is uncertain; never blindly retry")
            if observation.status == "PRESENT":
                existing.update(status="OBSERVED", observation=data(observation))
                self.save(row)
                return observation
        provider, task = self.provider(root, permit)
        plan = provider.plan(task, request)
        authorization = self.authority.authorize(plan)
        require(provider.decide(plan, authorization).effect == Effect.ALLOW, "M3 refused the exact local Git effect")
        action = {"operation": request.operation, "revision": plan.task.revision, "source_ref": plan.task.source_ref,
            "target": plan.target_ref, "expected_target": plan.expected_target, "payload": data(plan.payload),
            "status": "PREPARED", "observation": None}
        require(existing is None or all(existing[k] == action[k] for k in ("operation", "revision", "source_ref", "target", "expected_target", "payload")),
                "Reserved local effect operands changed")
        row["actions"][name] = action
        self.save(row)
        self.live()
        try:
            observation = port.submit(action, provider, plan, authorization)
        except OSError:
            observation = port.observe(action)
        require(observation.status == "PRESENT", "Local Git effect is not confirmed; retain its intent")
        action.update(status="OBSERVED", observation=data(observation))
        self.save(row)
        return observation

    def checks(self):
        return tuple(typed(RequiredCheck, row) for row in self.personal.plan["checks"])

    def observe_checks(self, permit):
        p, row = self.personal.plan, self.record()
        if not p["required_check_names"]:
            return {"status": "VERIFIED_ABSENT" if p["check_requirements"] == "VERIFIED_ABSENT" else "UNKNOWN", "qualified": False}
        if p["unresolved_check_names"] or self.ci_transport is None:
            return {"status": "UNKNOWN", "qualified": False, "missing": p["required_check_names"]}
        require(row["observations"] < p["window"]["maximum_check_observations"], "Personal check observation budget is exhausted")
        # Episode usage is canonical M1 state. Charge before creating the
        # exact M3 plan: a later checkpoint would invalidate its authorization.
        # Legacy personal mode keeps the same no-op charge behavior.
        self.charge_check("local:" + permit.token)
        provider, task = self.provider(self.personal.feature, permit)
        plan = provider.plan(task, Request(Operation.VALIDATE))
        authorization = self.authority.authorize(plan)
        policy = self.authority.check_policy(plan, EvidencePolicy(plan.policy_digest, self.checks(),
            p["window"]["issued_at"], p["window"]["expires_at"]))
        source = GitHubEvidenceSource(p["repository"]["name"], self.personal.repository_id, self.personal.repository_id,
            self.checks(), self.ci_transport, attest=self.authority.native_observation, clock=self.clock)
        validation = ProjectValidation(provider, task, policy, source, directory=self.personal.state / "checks",
            protected_roots=(self.personal.feature,), maximum_observations=p["window"]["maximum_check_observations"], clock=self.clock,
            retain_requests=True)
        row["observations"] += 1  # Consume before observation; lost results stay consumed.
        self.save(row)
        _, _, reserved = self.guard._snapshot(self.task_id, permit.decision.baseline.requirement_id)
        remaining = min(self.seconds_left(), reserved["active"]["deadline"] - self.clock())
        require(remaining > 0, "Check observation exhausted its M2 deadline")
        gate = validation.observe(Phase.BEFORE_PR, authorization=authorization, budget_ms=min(5000, remaining * 1000))
        return {"status": gate.status, "qualified": gate.qualified, "gate": data(gate)}

    def initialize_run(self):
        row = self.record()
        if row is None:
            require(key(self.task_id) not in self.memory.inspect()["tasks"], "Lost private execution journal cannot reset existing M1 work")
            row = {"schema_version": 1, "approval": self.personal.intent["approval"],
                "generation": self.memory.inspect()["state"]["generation"], "phase": "SCOPE", "revision": self.revision(),
                "original_review": None, "developer": None, "candidate": None, "code_review": None,
                "actions": {}, "coordination": None, "gates": [], "feedback": [], "observations": 0,
                "feature_administration": None if self.personal.plan["feature"]["prepare"] else self.personal.plan["administration"]}
            self.save(row)
        if key(self.task_id) not in self.memory.inspect()["tasks"]:
            self.memory.add_task(self.task_id, row["revision"])
        return row

    def reserve(self, label):
        row = self.record()
        requirement = self.requirement("feature" if label == "feature" or label.startswith("adoption:") else "develop")
        state, task, item = self.guard._snapshot(self.task_id, requirement)
        if row["coordination"] is None:
            action = Action("personal:coordinator", ActionKind.CHECK, "personal:" + label,
                "One observed local operation and project-check disposition", seconds=min(300, self.seconds_left()))
            row["coordination"] = {"label": label, "requirement": requirement, "permit": None,
                "action": data(action), "context": self.guard._context(state, task), "sequence": item["sequence"],
                "observation": None, "next_phase": None, "check_state": None}
            self.save(row)  # Intent exists before canonical guard allocation.
        coordination = row["coordination"]
        require(coordination["label"] == label and coordination["requirement"] == requirement,
                "Another finite local operation needs reconciliation")
        if coordination["permit"] is not None:
            return typed(Permit, coordination["permit"])
        state, task, item = self.guard._snapshot(self.task_id, requirement)
        require(coordination["context"] == self.guard._context(state, task), "Original coordinator context changed")
        if item["active"] is not None:
            require(item["active"]["action"] == coordination["action"] and item["active"]["context"] == coordination["context"],
                    "An unrelated active reservation cannot be adopted")
            permit = Permit(item["active"]["id"], self.guard.inspect(self.task_id, requirement))
        else:
            require(item["sequence"] == coordination["sequence"], "Coordinator guard history advanced without a recoverable permit")
            permit = self.guard.begin(self.task_id, requirement, typed(Action, coordination["action"]))
        row["coordination"]["permit"] = data(permit)
        self.save(row)
        return permit

    def conclude(self, permit, reference, outcome=Outcome.PASS, *, next_phase=None):
        requirement = permit.decision.baseline.requirement_id
        _, _, item = self.guard._snapshot(self.task_id, requirement)
        row = self.record()
        coordination = row["coordination"]
        require(coordination is not None and coordination["permit"]["token"] == permit.token,
                "Original coordinator permit is unavailable")
        if coordination["observation"] is None:
            require(item["active"] is not None and item["active"]["id"] == permit.token,
                    "Coordinator result has no live original reservation")
            coordination["observation"] = data(Observation(outcome, (reference,), tuple(item["unresolved"])))
            coordination["next_phase"] = next_phase
            self.save(row)  # Preserve the exact intended accounting before M2.
        measured = typed(Observation, coordination["observation"])
        require(measured.evidence == (reference,) and measured.outcome == outcome and coordination["next_phase"] == next_phase,
                "Retained coordinator result differs")
        if item["active"] is not None:
            self.guard.observe(self.task_id, requirement, permit, measured)
        else:
            require(item["last"] is not None and item["last"]["observation"] == coordination["observation"]
                    and item["last"]["context"] == coordination["context"], "Local operation guard observation is missing")
        row["coordination"] = None
        if next_phase is not None:
            row["phase"] = next_phase
        self.save(row)
        self.allowed(requirement)

    def finish_transition(self):
        row = self.record()
        coordination = row["coordination"]
        require(row["phase"] in ("CANDIDATE_REJECTED", "CHECKS_TRANSITION") and coordination is not None,
                "No retained result transition to reconcile")
        if coordination["observation"] is None:
            gate = row["gates"][-1] if row["phase"] == "CHECKS_TRANSITION" else row["feedback"][-1]
            reference = "personal:checks:" + digest(gate) if row["phase"] == "CHECKS_TRANSITION" else "personal:candidate-rejected:" + row["candidate"]
            failed = row["phase"] == "CANDIDATE_REJECTED" or gate["status"] in ("FAIL", "ERROR", "TIMEOUT", "CANCELLED")
            outcome = Outcome.FAIL if failed else Outcome.UNKNOWN
            phase = "DEVELOP" if failed else "LOCAL_DRAFT_CODE_REVIEWED"
        else:
            reference, outcome, phase = coordination["observation"]["evidence"][0], coordination["observation"]["outcome"], coordination["next_phase"]
        self.conclude(typed(Permit, coordination["permit"]), reference, outcome, next_phase=phase)

    def prepare_feature(self):
        p, row = self.personal.plan, self.record()
        if p["feature"]["prepare"] and row["phase"] == "FEATURE":
            permit = self.reserve("feature")
            self.effect("feature", Path(p["checkout"]["path"]), permit, Request(Operation.BRANCH))
            # A write-ahead exact branch reservation precedes worktree creation.
            root = self.personal.feature
            if root.exists():
                require(self.record()["actions"]["feature"].get("worktree") == {"path": str(root), "status": "SUBMITTED"},
                        "An unreserved feature worktree cannot be adopted")
                actual = local_checkout(root, p["checkout"]["remote"])
                common = lambda path: value(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
                require(actual["head"] == p["checkout"]["head"] and actual["ref"] == "refs/heads/" + p["feature"]["branch"]
                        and common(root) == common(Path(p["checkout"]["path"]))
                        and not value(root, "status", "--porcelain", "--untracked-files=all"), "Feature worktree is uncertain; do not overwrite it")
            else:
                require(self.record()["actions"]["feature"].get("worktree") is None,
                        "A submitted worktree effect has no complete result; do not launch it again")
                self.fresh()
                # Worktree creation is a distinct local mutation under the
                # original bounded feature reservation, not just an outer lease.
                provider, task = self.provider(Path(p["checkout"]["path"]), permit)
                plan = provider.plan(task, Request(Operation.BRANCH))
                require(provider.decide(plan, self.authority.authorize(plan)).effect == Effect.ALLOW,
                        "Feature preparation lost current M3/M2 authority")
                from .config import safe_path
                require(safe_path(root) == root and not root.exists(), "Feature destination changed")
                row = self.record()
                row["actions"]["feature"]["worktree"] = {"path": str(root), "status": "SUBMITTED"}
                self.save(row)
                port = GitExecutionPort(provider.adapter.config,
                    bound_git_directory=Path(p["administration"]["directory"]["path"]))
                port._git("worktree", "add", "--", str(root), p["feature"]["branch"])
            row = self.record()
            bound = administration(root)
            require(bound["common"] == p["administration"]["common"], "Prepared feature belongs to different Git administration")
            row["feature_administration"] = bound
            row["actions"]["feature"]["worktree"]["status"] = "OBSERVED"
            row["phase"] = "FEATURE_TRANSITION"
            self.save(row)
        row = self.record()
        if row["phase"] == "FEATURE_TRANSITION" and row["coordination"] is not None:
            self.conclude(typed(Permit, row["coordination"]["permit"]), "personal:feature-prepared", next_phase="DEVELOP")
        row = self.record()
        row["phase"] = "DEVELOP"
        self.save(row)

    def _run(self):
        self.fresh()
        self.workers.fence()
        caps = self.runtime.capabilities()
        require(type(self.runtime) is CodexExecRuntime, "Personal execution requires the actual Codex runtime")
        if not all((caps.independent_contexts, caps.workspace_write, caps.observe, caps.cancel)):
            raise PersonalBlocked("UNSUPPORTED_RUNTIME", "Use the supported genuine independent Codex CLI.", status="UNSUPPORTED_RUNTIME")
        row = self.initialize_run()
        if row["phase"] == "SCOPE":
            review = self.workers.execute("original", self.context("original"), Path(self.personal.plan["checkout"]["path"]))
            self.workers.actual(review, approval=True, accounted=True)
            row = self.record()
            row.update(original_review=review["request"]["id"], phase="FEATURE")
            self.save(row)
        self.original_approval()
        if self.track is not None:
            from .personal_track_preparation import prepare
            prepare(self.track)
        if self.record()["phase"] in ("CHECKS_TRANSITION", "CANDIDATE_REJECTED"):
            self.finish_transition()
        if self.record()["phase"] in ("FEATURE", "FEATURE_TRANSITION"):
            self.prepare_feature()
        if self.episode and self.record()["phase"] == "DEVELOP" and self.record()["developer"] is None:
            if not (self.personal.state / "adoption.json").exists():
                return {**self.status(), "status": "CANDIDATE_ADOPTION_REQUIRED", "execution": "STOPPED"}
        # One task iteration; ordinary correction remains in the same M1/M2
        # requirement and original role/time budgets, never a new campaign.
        for _ in range(max(1, self.personal.plan["window"]["developers"])):
            row = self.record()
            if row["phase"] == "DEVELOP":
                self.allowed(self.requirement("develop"))
                developer = self.workers.execute("develop", self.context("develop"), self.personal.feature)
                row = self.record()
                row["developer"] = developer["request"]["id"]
                row["phase"] = "STAGE" if developer["observation"]["result"]["outcome"] == Outcome.PASS else "DEVELOP"
                if row["phase"] == "DEVELOP":
                    row["feedback"].append(developer["observation"]["result"])
                self.save(row)
                if row["phase"] == "DEVELOP":
                    continue
            if self.record()["phase"] in ("STAGE", "CANDIDATE", "COMMIT", "SOURCE_TRANSITION"):
                self.commit_and_checks()
            row = self.record()
            if row["phase"] == "CODE":
                reviewer = self.workers.execute("code", self.context("code"), self.personal.feature)
                result = reviewer["observation"]["result"]
                row = self.record()
                if result["approved"] and result["outcome"] == Outcome.PASS:
                    self.workers.actual(reviewer, approval=True, accounted=True)
                    row.update(code_review=reviewer["request"]["id"], phase="CHECKS")
                else:
                    row.update(code_review=None, phase="DEVELOP")
                    row["feedback"].append(result)
                self.save(row)
                if row["phase"] == "DEVELOP":
                    continue
            if self.record()["phase"] == "CHECKS":
                self.check_stage()
                if self.record()["phase"] == "DEVELOP":
                    continue
            if self.record()["phase"] == "LOCAL_DRAFT_CODE_REVIEWED":
                self.verify_draft()
                return self.status()
        return self.status()

    def commit_and_checks(self):
        row = self.record()
        origin = self.source_origin()
        attempt = origin["label"]
        if row["phase"] == "SOURCE_TRANSITION":
            return self.source_transition()
        permit = self.reserve("commit:" + attempt)
        row = self.record()
        if row["phase"] == "STAGE":
            require(source_seal(self.personal.feature) == origin["source"], "Authenticated source origin changed before staging")
            changed = git(self.personal.feature, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "HEAD", "-z")
            changed += git(self.personal.feature, "ls-files", "--others", "--exclude-standard", "-z")
            paths = tuple(sorted({p.decode("utf-8", "strict") for p in changed.split(b"\0") if p}))
            require(paths, "Developer reported success without a committable in-scope change")
            self.effect("stage:" + attempt, self.personal.feature, permit, Request(Operation.STAGE, paths=paths))
            row = self.record()
            row.update(phase="CANDIDATE", candidate=None)
            self.save(row)
        if self.record()["phase"] == "CANDIDATE":
            _, _, item = self.guard._snapshot(self.task_id, self.requirement("develop"))
            candidate = self.workers.execute("candidate", self.context("candidate"), self.personal.feature,
                                             deadline=item["active"]["deadline"])
            actual = self.workers.actual(candidate, accounted=True)
            if actual.result.approved is not True or actual.result.outcome != Outcome.PASS:
                row = self.record()
                row.update(phase="CANDIDATE_REJECTED", candidate=candidate["request"]["id"])
                row["feedback"].append(data(actual.result))
                self.save(row)
                self.finish_transition()
                return
            self.workers.actual(candidate, approval=True, accounted=True)
            row = self.record()
            row.update(candidate=candidate["request"]["id"], phase="COMMIT")
            self.save(row)
        if self.record()["phase"] == "COMMIT":
            observed = self.effect("commit:" + attempt, self.personal.feature, permit,
                Request(Operation.COMMIT, summary=self.personal.plan["commit_message"]))
            row = self.record()
            row.update(revision=observed.revision, phase="SOURCE_TRANSITION", code_review=None)
            self.save(row)
            self.source_transition()

    def source_transition(self):
        row = self.record()
        require(row["phase"] == "SOURCE_TRANSITION", "No original source transition to recover")
        if row["coordination"] is not None:
            self.conclude(typed(Permit, row["coordination"]["permit"]), "personal:commit:" + row["revision"])
        require(any(a["operation"] == Operation.COMMIT and a["status"] == "OBSERVED"
                    and a["observation"]["revision"] == row["revision"] for a in row["actions"].values()),
                "Canonical source transition requires its observed original Git CAS")
        if self.memory.inspect()["tasks"][key(self.task_id)]["source_revision"] != row["revision"]:
            self.memory.set_revision(self.task_id, row["revision"])
        row = self.record()
        row["phase"] = "CODE"
        self.save(row)

    def check_stage(self):
        row = self.record()
        # Legacy lost-delivery accounting uses its original durable label,
        # without introducing a new Worker observation or approval requirement.
        attempt = self.source_origin(historical=True)["label"] if self.episode else row["developer"]
        if row["phase"] == "CHECKS":
            # Check observation uses a new guarded action at the actual new SHA.
            # It can remain pending without accepting the original requirement.
            if self.memory.inspect()["tasks"][key(self.task_id)]["source_revision"] != row["revision"]:
                self.memory.set_revision(self.task_id, row["revision"])
            permit = self.reserve("checks:" + attempt)
            row = self.record()
            if row["coordination"]["check_state"] is None:
                row["coordination"]["check_state"] = "SUBMITTED"
                self.save(row)
                gate = self.observe_checks(permit)
            else:
                require(row["coordination"]["check_state"] == "SUBMITTED", "Unexpected retained check delivery")
                # The original #21 evidence remains private. A missing caller
                # delivery is UNKNOWN, never a cached PASS or a new observation.
                gate = {"status": "UNKNOWN", "qualified": False, "reason": "LOST_CHECK_DELIVERY",
                        "missing": self.personal.plan["required_check_names"]}
            row = self.record()
            row["coordination"]["check_state"] = "RETURNED"
            row["gates"].append(gate)
            # Preserve observed failures as corrective feedback. UNKNOWN and
            # pending checks permit code-only review, never project acceptance.
            failed = gate["status"] in ("FAIL", "ERROR", "TIMEOUT", "CANCELLED")
            row["phase"] = "CHECKS_TRANSITION"
            if failed:
                row["feedback"].append(gate)
            self.save(row)
            self.finish_transition()

    def verify_draft(self):
        self.fresh()
        self.verify_local_review()

    def verify_local_review(self):
        self.check_administration(self.record())
        row = self.record()
        review = self.worker(row["code_review"])
        require(review["purpose"] == "code" and review["request"]["revision"] == row["revision"]
                and value(self.personal.feature, "rev-parse", "HEAD") == row["revision"]
                and value(self.personal.feature, "symbolic-ref", "HEAD") == "refs/heads/" + self.personal.plan["feature"]["branch"]
                and not value(self.personal.feature, "status", "--porcelain", "--untracked-files=all"),
                "Local draft or exact-SHA review is stale")
        self.workers.actual(review, approval=True, accounted=True)
        self.guard.require_approval(self.task_id, self.review_requirement())

    def invocation(self, operation="run"):
        require(operation in ("run", "resume", "handoff"), "Unsupported personal invocation")
        if operation == "handoff":
            # Expiry revokes execution, not a safe explicit owner release.
            observed = self.memory.inspect()
            require(observed["health"] == "SYNCED" and observed["local_owner"], "Original M1 owner is required for handoff")
        else:
            self.fresh()
        row = self.record()
        state = self.memory.inspect()
        root = self.personal.feature if self.personal.feature.exists() else Path(self.personal.plan["checkout"]["path"])
        view = {"mode": "PERSONAL", "operation": operation, "approval": self.personal.intent["approval"],
            "checkpoint": state["local_head"], "generation": state["state"]["generation"],
            "journal": digest(row), "worker_inventory": digest(self.workers.records()),
            "workspace": str(self.personal.feature), "revision": self.revision(),
            "maximum_tasks": 1, "maximum_rounds": 1, "maximum_parallel": 1,
            "actual_checkout": {"ref": value(root, "symbolic-ref", "HEAD"), "sha": value(root, "rev-parse", "HEAD"),
                "source_digest": source_seal(root), "admin_digest": admin_seal(root),
                "clean": not bool(value(root, "status", "--porcelain", "--untracked-files=all"))},
            "expires_at": self.personal.plan["window"]["expires_at"]}
        return view, "personal-run:" + digest(view)

    def run(self, *, reviewed, authorized, operation="run"):
        require(authorized, "Separately approve the exact finite personal invocation")
        _, initial_token = self.invocation(operation)
        require(reviewed == initial_token, "Personal invocation changed; review it again without renewing the enrollment")
        with invocation_lock(self.memory.control):
            _, token = self.invocation(operation)
            require(reviewed == token, "Personal invocation changed; review it again without renewing the enrollment")
            try:
                if operation == "handoff":
                    self.workers.fence()
                    execution = self.memory.inspect()["state"]["execution"]
                    external = [a for a in execution["actions"].values() if a["task_key"] == key(self.task_id)]
                    require(all(a["status"] == "OBSERVED" for a in external)
                            and not list(self.memory.control.glob("network-stop-*.json")),
                            "Reconcile canonical external effects and confirmed transport stops before handoff")
                    if (self.personal.state / "product.json").exists():
                        from .personal_product import PersonalProduct
                        product = getattr(self, "product", None) or PersonalProduct(self)
                        current = product.status()
                        require(current["status"] in ("PR_DRAFT", "WAITING_HUMAN_APPROVAL", "MERGED_DELEGATED_VERIFIED", "MERGED_EXTERNALLY_VERIFIED")
                                and not product.service.unconfirmed_contexts(), "Reobserve exact product effects before ownership release")
                    elif (self.personal.state / "publication.json").exists() or external:
                        from .personal_publication import PersonalPublication
                        current = PersonalPublication(self).status()
                        require(current["status"] in ("PUBLICATION_PRESENT", "PUBLICATION_PRESENT_GUARD_STOPPED") and current["canonical_status"] == "OBSERVED"
                                and not current["unconfirmed_transport"], "Reobserve exact publication before ownership release")
                    require(all(r["phase"] == "ACCOUNTED" for r in self.workers.records())
                            and (self.record() is None or self.record()["coordination"] is None)
                            and (self.record() is None or all(a["status"] == "OBSERVED"
                                and ("worktree" not in a or a["worktree"]["status"] == "OBSERVED") for a in self.record()["actions"].values()))
                            and all(item["active"] is None for item in self.memory.inspect()["state"]["progress_guard"]["requirements"].values()),
                            "Reconcile worker/operation intents before handoff")
                    self.memory.handoff()
                    return {"status": "HANDED_OFF", "execution": "STOPPED", "authority": "REVOKED"}
                return self._run()
            finally:
                self.stop_workers()

    def stop_workers(self):
        # A foreground exit must not leave an invented background job.
        for row in self.workers.records():
            if row["phase"] == "SUBMITTED":
                observation = self.runtime.observe(row["request"]["id"])
                if observation.status == RuntimeStatus.RUNNING:
                    observation = self.runtime.cancel(row["request"]["id"])
                if observation.stopped is not True:
                    raise PersonalBlocked("WORKER_STOP_UNCONFIRMED", "Retain the original runtime evidence and reconcile its stop before any later work.")

    def status(self):
        observed = self.memory.inspect()
        row = self.record()
        require(row is None or row["generation"] == observed["state"]["generation"], "Retained generation differs; preserve historical receipts")
        phase = row["phase"] if row else "ENROLLED"
        decisions = []
        task = observed["tasks"].get(key(self.task_id))
        if task is not None:
            decisions = [self.guard._decision(identifier, observed["state"], task, item).kind
                for identifier, item in observed["state"]["progress_guard"]["requirements"].items() if key(self.task_id) in item["tasks"]]
        status = ("OWNER_NOT_ACTIVE" if not observed["local_owner"] else "BLOCKED_PROGRESS_GUARD"
                  if any(d != DecisionKind.ALLOW for d in decisions) else phase)
        code_review = "NOT_RECORDED"
        if phase == "LOCAL_DRAFT_CODE_REVIEWED":
            try:
                self.verify_local_review()
                code_review = "CURRENT_LOCAL_SOURCE"
            except (ADPError, OSError, ValueError, TypeError, KeyError):
                code_review = "UNVERIFIED_OR_HISTORICAL"
                if status == phase:
                    status = "BLOCKED_CODE_REVIEW"
        return {"mode": "PERSONAL", "status": status, "phase": phase, "progress_guard": decisions,
            "code_review": code_review, "remote_scope": "NOT_REOBSERVED_BY_STATUS",
            "repository_id": self.personal.repository_id, "issue": self.personal.plan["issue"],
            "local_owner": observed["local_owner"], "generation": observed["state"]["generation"],
            "memory_health": observed["health"], "revision": self.revision(),
            "workers": [{"role": r["purpose"], "phase": r["phase"], "request_id": r["request"]["id"],
                "stopped": self.runtime.observe(r["request"]["id"]).stopped} for r in self.workers.records()],
            "check_results": row["gates"] if row else [], "product_acceptance": "NOT_ACCEPTED",
            "external_operations": "NOT_DELEGATED", "merge": "MANUAL",
            "expires_at": self.personal.plan["window"]["expires_at"], "runtime_qualification": "NOTRUN"}
