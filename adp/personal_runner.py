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
        self.authority = PersonalAuthority(self)
        self.guard = ProgressGuard(self.memory, authority=self.authority, clock=self.clock)
        self.workers = PersonalWorkers(self)
        self.path = personal.state / "run.json"

    def live(self):
        # Recheck immutable retained consent and the actual owner. Do not rerun
        # Git configuration discovery for every nested evidence verification.
        p = self.personal.plan
        require(read_private(self.personal.directory / INTENT) == self.personal.intent
                and read_private(Path(p["effects"]["marker"])) == {"schema_version": 1,
                    "directory": str(self.personal.directory), "approval": self.personal.intent["approval"]}
                and p["window"]["issued_at"] <= self.clock() < p["window"]["expires_at"], "Personal consent changed or expired")
        observed = self.memory.inspect()
        require(observed["health"] == "SYNCED" and observed["local_owner"], "The original synchronized M1 owner is required")
        row = self.record()
        require(row is None or row["generation"] == observed["state"]["generation"], "Personal execution generation changed")
        require(self.personal.intent["phase"] == "ENROLLED", "Complete the original personal setup first")

    def seconds_left(self):
        self.live()
        return self.personal.plan["window"]["expires_at"] - self.clock()

    def record(self):
        row = read_private(self.path, optional=True)
        if row is not None:
            fields(row, "schema_version approval generation phase revision original_review developer candidate code_review actions coordination gates feedback observations")
            require(row["schema_version"] == 1 and type(row["schema_version"]) is int
                    and row["approval"] == self.personal.intent["approval"]
                    and type(row["generation"]) is int and row["generation"] > 0,
                    "Personal execution journal or generation changed")
            require(row["phase"] in ("SCOPE", "FEATURE", "FEATURE_TRANSITION", "DEVELOP", "STAGE", "CANDIDATE", "COMMIT",
                    "SOURCE_TRANSITION", "CODE", "CHECKS", "LOCAL_DRAFT_CODE_REVIEWED")
                    and type(row["observations"]) is int and 0 <= row["observations"] <= self.personal.plan["window"]["maximum_check_observations"]
                    and type(row["feedback"]) is list and len(row["feedback"]) <= 8
                    and type(row["gates"]) is list and len(row["gates"]) <= 3, "Malformed personal phase or finite accounting")
        return row

    def save(self, row):
        self.live()
        create_private(self.personal.state)
        atomic(self.path, encode(row, LIMIT))

    def revision(self):
        row = self.record()
        return row["revision"] if row else self.personal.plan["checkout"]["head"]

    def specification(self, purpose):
        if purpose == "feature":
            return Requirement(self.task_id, "local-feature", ("feature-prepared",))
        semantic = purpose in ("original", "candidate")
        return Requirement(self.task_id, "semantic-" + purpose if semantic else "product",
                           (purpose,) if semantic else (self.personal.plan["criterion"],))

    def requirement(self, purpose):
        spec = self.specification(purpose)
        proof = self.authority.operator_evidence("admission", self.guard.admission_subject(self.task_id, spec),
            {"task_id": self.task_id, "requirement": data(spec)})
        return self.guard.register(self.task_id, spec, proof)

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
            pending = self.record()["actions"].values()
            commits = [a for a in pending if a["operation"] == Operation.COMMIT]
            if commits and observation.checkout["head"] != expected_checkout["head"]:
                observed = GitExecutionPort(Config.discover(Path(expected_checkout["path"]), remote=plan["checkout"]["remote"],
                    repository_id=self.personal.repository_id)).observe(commits[-1])
                require(observed.status == "PRESENT", "Source advanced without a bound observed commit")
                expected_checkout["head"] = observed.revision
        require(observation.checkout == expected_checkout and owner == plan["owner"] and len(original) == 1
                and digest(data(original[0])) == plan["original_digest"]
                and digest(governance(Path(plan["checkout"]["path"]))) == plan["governance_digest"],
                "The original source, issue, native prerequisites, ownership or governance changed")
        require(not plan["native_prerequisites"], "Native prerequisites need independent acceptance before this task can be READY")
        if self.record() is None or self.record()["phase"] in ("SCOPE", "FEATURE", "FEATURE_TRANSITION"):
            require(not value(Path(plan["checkout"]["path"]), "status", "--porcelain", "--untracked-files=all"),
                    "Original checkout changed before scope admission or feature preparation")
        # Protections and declared requirements may tighten; never discard them.
        current_rules = observation.facts["branch_rules"]
        require(current_rules == plan["branch_rules"], "Branch requirements changed; preserve this enrollment and obtain an operator disposition")
        self.live()
        return observation

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
            root = self.personal.feature
            context["diff"] = git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary",
                *( ("--cached",) if purpose == "candidate" else (self.personal.plan["checkout"]["head"], "HEAD")), limit=16384).decode("utf-8", "strict")
            context["index_digest"] = index_digest(root)
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
        require(self.clock() < request["deadline"] and request["revision"] == self.revision(), "Worker source/deadline differs")
        if row["purpose"] == "original":
            require(Path(request["workspace"]) == Path(self.personal.plan["checkout"]["path"]), "Original review workspace differs")
            return  # Explicitly approved read-only inspection, before interpretation.
        if row["purpose"] == "develop":
            prior = self.record()["developer"]
            if prior is None:
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
        port = GitExecutionPort(cfg)
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
                "actions": {}, "coordination": None, "gates": [], "feedback": [], "observations": 0}
            self.save(row)
        if key(self.task_id) not in self.memory.inspect()["tasks"]:
            self.memory.add_task(self.task_id, row["revision"])
        return row

    def reserve(self, label):
        row = self.record()
        if row["coordination"] is not None:
            require(row["coordination"]["label"] == label, "Another finite local operation needs reconciliation")
            return typed(Permit, row["coordination"]["permit"])
        requirement = self.requirement("feature" if label == "feature" else "develop")
        permit = self.guard.begin(self.task_id, requirement, Action("personal:coordinator", ActionKind.CHECK,
            "personal:" + label, "One observed local operation and project-check disposition", seconds=min(300, self.seconds_left())))
        row["coordination"] = {"label": label, "permit": data(permit)}
        self.save(row)
        return permit

    def conclude(self, permit, reference, outcome=Outcome.PASS):
        requirement = permit.decision.baseline.requirement_id
        _, _, item = self.guard._snapshot(self.task_id, requirement)
        if item["active"] is not None:
            self.guard.observe(self.task_id, requirement, permit, Observation(outcome, (reference,), tuple(item["unresolved"])))
        else:
            require(item["last"] is not None and reference in item["last"]["observation"]["evidence"], "Local operation guard observation is missing")
        row = self.record()
        row["coordination"] = None
        self.save(row)
        self.allowed(requirement)

    def prepare_feature(self):
        p, row = self.personal.plan, self.record()
        if p["feature"]["prepare"] and row["phase"] == "FEATURE":
            permit = self.reserve("feature")
            self.effect("feature", Path(p["checkout"]["path"]), permit, Request(Operation.BRANCH))
            # A write-ahead exact branch reservation precedes worktree creation.
            root = self.personal.feature
            if root.exists():
                actual = local_checkout(root, p["checkout"]["remote"])
                common = lambda path: value(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
                require(actual["head"] == p["checkout"]["head"] and actual["ref"] == "refs/heads/" + p["feature"]["branch"]
                        and common(root) == common(Path(p["checkout"]["path"]))
                        and not value(root, "status", "--porcelain", "--untracked-files=all"), "Feature worktree is uncertain; do not overwrite it")
            else:
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
                git(Path(p["checkout"]["path"]), "worktree", "add", "--", str(root), p["feature"]["branch"])
            row = self.record()
            row["phase"] = "FEATURE_TRANSITION"
            self.save(row)
        row = self.record()
        if row["phase"] == "FEATURE_TRANSITION" and row["coordination"] is not None:
            self.conclude(typed(Permit, row["coordination"]["permit"]), "personal:feature-prepared")
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
        if self.record()["phase"] in ("FEATURE", "FEATURE_TRANSITION"):
            self.prepare_feature()
        # One task iteration; ordinary correction remains in the same M1/M2
        # requirement and original role/time budgets, never a new campaign.
        for _ in range(self.personal.plan["window"]["developers"]):
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
        attempt = row["developer"]
        if row["phase"] == "SOURCE_TRANSITION":
            return self.source_transition()
        permit = self.reserve("commit:" + attempt)
        row = self.record()
        if row["phase"] == "STAGE":
            developer = self.worker(attempt)
            self.workers.actual(developer, accounted=True)
            require(source_seal(self.personal.feature) == developer["result_source"], "Developer content changed before staging")
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
                row.update(phase="DEVELOP", candidate=None)
                row["feedback"].append(data(actual.result))
                self.save(row)
                self.conclude(permit, "personal:candidate-rejected:" + candidate["request"]["id"], Outcome.FAIL)
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
        attempt = row["developer"]
        if row["phase"] == "CHECKS":
            # Check observation uses a new guarded action at the actual new SHA.
            # It can remain pending without accepting the original requirement.
            if self.memory.inspect()["tasks"][key(self.task_id)]["source_revision"] != row["revision"]:
                self.memory.set_revision(self.task_id, row["revision"])
            if row["coordination"] is None:
                permit = self.reserve("checks:" + attempt)
            else:
                permit = typed(Permit, row["coordination"]["permit"])
            gate = self.observe_checks(permit)
            row = self.record()
            row["gates"].append(gate)
            # Preserve observed failures as corrective feedback. UNKNOWN and
            # pending checks permit code-only review, never project acceptance.
            failed = gate["status"] in ("FAIL", "ERROR", "TIMEOUT", "CANCELLED")
            row["phase"] = "DEVELOP" if failed else "LOCAL_DRAFT_CODE_REVIEWED"
            if failed:
                row["feedback"].append(gate)
            self.save(row)
            self.conclude(permit, "personal:checks:" + digest(gate), Outcome.FAIL if failed else Outcome.UNKNOWN)

    def verify_draft(self):
        self.fresh()
        row = self.record()
        review = self.worker(row["code_review"])
        require(review["purpose"] == "code" and review["request"]["revision"] == row["revision"]
                and value(self.personal.feature, "rev-parse", "HEAD") == row["revision"]
                and value(self.personal.feature, "symbolic-ref", "HEAD") == "refs/heads/" + self.personal.plan["feature"]["branch"]
                and not value(self.personal.feature, "status", "--porcelain", "--untracked-files=all"),
                "Local draft or exact-SHA review is stale")
        self.workers.actual(review, approval=True, accounted=True)
        self.guard.require_approval(self.task_id, self.requirement("develop"))

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
                    require(all(r["phase"] == "ACCOUNTED" for r in self.workers.records())
                            and (self.record() is None or self.record()["coordination"] is None)
                            and (self.record() is None or all(a["status"] == "OBSERVED" for a in self.record()["actions"].values()))
                            and all(item["active"] is None for item in self.memory.inspect()["state"]["progress_guard"]["requirements"].values()),
                            "Reconcile worker/operation intents before handoff")
                    self.memory.handoff()
                    return {"status": "HANDED_OFF", "execution": "STOPPED", "authority": "REVOKED"}
                return self._run()
            finally:
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
        return {"mode": "PERSONAL", "status": row["phase"] if row else "ENROLLED",
            "repository_id": self.personal.repository_id, "issue": self.personal.plan["issue"],
            "local_owner": observed["local_owner"], "generation": observed["state"]["generation"],
            "memory_health": observed["health"], "revision": self.revision(),
            "workers": [{"role": r["purpose"], "phase": r["phase"], "request_id": r["request"]["id"],
                "stopped": self.runtime.observe(r["request"]["id"]).stopped} for r in self.workers.records()],
            "check_results": row["gates"] if row else [], "product_acceptance": "NOT_ACCEPTED",
            "external_operations": "NOT_DELEGATED", "merge": "MANUAL",
            "expires_at": self.personal.plan["window"]["expires_at"], "runtime_qualification": "NOTRUN"}
