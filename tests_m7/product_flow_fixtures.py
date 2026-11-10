"""Owned disposable product + actual M1–M5/#21/#22; synthetic GitHub only."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from execution_fixtures import ExecutionFixture
from test_config import run
from adp.config import Config
from adp.policy import PolicyProvider
from adp.policy_adapters import GitPolicyAdapter, MockRepositoryAdapter
from adp.policy_types import Protection
from discovery_fixtures import discover as discover_fixture, issue

from adp.discovery_schema import digest
from adp.execution_types import Role
from adp.github_product import DelegationProfile, GitHubProductForge, delegation_subject
from adp.guard_types import data
from adp.network_git import GitHubCAS, GitHubTarget
from adp.network_http import Response, NetworkTransportError
from adp.policy_types import Operation, Request, SourceClaim, SourceKind
from adp.product_flow import GitHubProductFlow, PreparedScope
from adp.project_validation import ProjectValidation, ReportedEvidence, observation_subject, policy_subject
from adp.project_validation_types import EvidencePolicy, Phase, ProjectObservation, ProjectResult, RequiredCheck, ResultStatus
from adp.ticket_preparation import TicketArchive, TicketPreparer, original_scope_subject, preparation_subject
from adp.ticket_types import Clause, OriginalScope, Part, PreparationReview, Proposal


class ProductServer:
    def __init__(self, fixture):
        self.f = fixture
        self.pulls, self.comments, self.calls = [], [], []
        self.review_rows = []
        self.failure, self.loss, self.before_write = None, None, None
        self.pages = None

    def bind_repository(self, node, database):
        if (node, database) != ("R_product", 17):
            raise ValueError("Wrong immutable repository")

    def request(self, method, path, body=None, *, seconds):
        self.calls.append((method, path, copy.deepcopy(body)))
        if self.failure is not None:
            return Response(self.failure, b'{}')
        base = "/repos/demo/project"
        if path == base:
            return Response(200, json.dumps({"id": 17, "node_id": "R_product", "full_name": "demo/project"}).encode())
        if self.before_write is not None and method != "GET":
            callback, self.before_write = self.before_write, None
            callback()
        if method in ("POST", "PUT") and self.loss == "before":
            self.loss = None
            raise NetworkTransportError("Synthetic stopped request before delivery")
        if method == "POST" and path == base + "/pulls":
            repository = {"id": 17, "node_id": "R_product", "full_name": "demo/project"}
            number = len(self.pulls) + 1
            item = {"number": number, "id": 100 + number, "html_url": f"https://github.com/demo/project/pull/{number}",
                "title": body["title"], "body": body["body"], "draft": body["draft"], "state": "open", "merged": False,
                "head": {"ref": body["head"], "sha": run(self.f.root, "rev-parse", "HEAD"), "repo": repository},
                "base": {"ref": body["base"], "sha": run(self.f.remote, "rev-parse", "refs/heads/trunk"), "repo": repository}}
            self.pulls.append(item)
            result = item
        elif method == "POST" and path.endswith("/comments"):
            result = {"body": body["body"], "html_url": "https://github.com/demo/project/issues/1#issuecomment-7"}
            self.comments.append(result)
        elif method == "PUT":
            item = self.pulls[0]
            if body["sha"] != item["head"]["sha"]:
                return Response(409, b'{}')
            args = ["commit-tree", run(self.f.root, "rev-parse", "HEAD^{tree}"), "-p", item["base"]["sha"]]
            if body["merge_method"] == "merge":
                args += ["-p", body["sha"]]
            args += ["-m", "Synthetic provider merge"]
            result_sha = run(self.f.remote, *args)
            run(self.f.remote, "update-ref", "refs/heads/trunk", result_sha, item["base"]["sha"])
            item.update(merged=True, state="closed", merge_commit_sha=result_sha)
            result = {"sha": result_sha, "merged": True}
        elif "/git/commits/" in path:
            revision = path.rsplit("/", 1)[1]
            result = {"sha": revision, "tree": {"sha": run(self.f.remote, "rev-parse", revision + "^{tree}")},
                "parents": [{"sha": p} for p in run(self.f.remote, "show", "-s", "--format=%P", revision).split()]}
        elif "/reviews?" in path:
            result = self.review_rows
        elif "/pulls/" in path:
            result = self.pulls[int(path.rsplit("/", 1)[1]) - 1]
        elif "/pulls?" in path:
            page = int(path.rsplit("page=", 1)[1])
            result = self.pages.get(page, []) if self.pages is not None else self.pulls
        elif "/comments?" in path:
            result = self.comments
        else:
            return Response(404, b'{}')
        if method in ("POST", "PUT") and self.loss == "after":
            self.loss = None
            raise NetworkTransportError("Synthetic stopped request after delivery")
        return Response(200, json.dumps(result).encode())


class ProductFixture(ExecutionFixture):
    def setUp(self):
        # #22's currently supported identity mapping is configured before init.
        # The accepted legacy fixture itself remains byte-for-byte unchanged.
        discover = Config.discover
        def configured(*args, **kwargs):
            kwargs.setdefault("repository_id", "repo-opaque-A")
            return discover(*args, **kwargs)
        with patch.object(Config, "discover", side_effect=configured):
            super().setUp()
        self.root = self.projects["one"].root
        run(self.remote, "config", "user.name", "Synthetic provider")
        run(self.remote, "config", "user.email", "fixture@example.invalid")
        self.rules["one"] = replace(self.rules["one"], merge_method="merge",
            permissions=tuple(replace(p, effect="ALLOW") if p.operation == Operation.MERGE else p for p in self.rules["one"].permissions))
        def factory(admission, safety):
            # A fresh trusted synthetic provider snapshot per operation; the
            # actual M3 decision and actual M1/M2 safety remain in use.
            snapshot = GitPolicyAdapter(self.projects["one"].git_port.config, governance=(), fingerprint_worktree=True).inspect()
            provider = PolicyProvider(MockRepositoryAdapter(snapshot), authority=self.authority, safety=safety, clock=lambda: self.now)
            source = SourceClaim(SourceKind.OPERATOR, "fixture:product-policy", "b" * 64, self.rules["one"], self.now, self.now + 300)
            provider.sources = (replace(source, evidence=self.authority.grant(purpose="policy/operator",
                subject=provider.source_subject(source, snapshot))),)
            protections = []
            for ref in (snapshot.source_ref, "refs/heads/trunk"):
                old = next((r.revision for r in snapshot.remote_refs if r.name == ref), None)
                p = Protection(ref, old, True, True, True, (), 1, ("merge", "squash", "ff_only"), (),
                    "fixture:product-protection", self.now, self.now + 300, mergeable_methods=("merge", "squash", "ff_only"))
                p = replace(p, evidence=self.authority.grant(purpose="policy/protection", subject=provider.protection_subject(p, snapshot)))
                protections.append(p)
            provider.protections = tuple(protections)
            return provider
        self.projects["one"] = replace(self.projects["one"], policy_factory=factory)
        self.conductor.journal.upgrade_product_flow(authorized=True)
        self.target = GitHubTarget(self.config.identity, "R_product", 17, "demo", "project", "work/one")
        self.server = ProductServer(self)
        self.service = GitHubCAS(self.target, self.server)
        self.forge = GitHubProductForge(self.service, self.conductor.journal, self.authority)
        self.admission = self.admissions[0]
        # Freeze/prepare the actual fixture issue at the initial code SHA.
        snapshot, _ = discover_fixture([issue(1, name="demo/project"), issue(2, name="demo/project")], name="demo/project")
        self.discovery.snapshot = replace(snapshot, repository=replace(snapshot.repository, memory_id=self.config.identity,
            checkout_ref="refs/heads/work/one", checkout_sha=self.initial))
        provider = factory(self.admission, None)
        archive = TicketArchive(self.base / "scope", protected_roots=(self.root, self.memory.path))
        original_ref = archive.freeze(self.discovery.snapshot, self.admission.identity)
        original = archive.original(original_ref)
        scope = OriginalScope(original_ref, self.admission.product_goal,
            (Clause("goal", "OBJECTIVE", self.admission.product_goal), Clause("accept", "ACCEPTANCE", "criterion:answer")),
            self.admission.allowed_paths, ("unit",), ())
        scope = replace(scope, evidence=self.authority.grant(purpose="ticket/original-scope", subject=original_scope_subject(scope)))
        proposal = Proposal(original_ref, original.issue.revision, provider.inspect_repository().digest,
            (Part("ticket", ("goal", "accept")),), exit_conditions=("Original acceptance or bounded explicit stop",))
        preparer = TicketPreparer(adapters=(self.discovery,), planner=self.readiness.planner, policy=provider,
            authority=self.authority, archive=archive, clock=lambda: self.now)
        reviews = self.readiness.reviews((self.discovery.snapshot,))
        track = preparer.observe(reviews=reviews)
        review = PreparationReview("synthetic-preparer", self.now, self.now + 300)
        review = replace(review, evidence=self.authority.grant(purpose="ticket/preparation",
            subject=preparation_subject(original, scope, proposal, review, track)))
        prepared = preparer.prepare(scope, proposal, review, readiness_reviews=reviews)
        if prepared.packet is None:
            raise AssertionError(prepared)
        self.scope = PreparedScope(preparer, prepared.packet_reference)
        self.phases = (Phase.BEFORE_PR,)
        self.check_status = ResultStatus.PASS
        self.counts, self.denominator = (), None
        self.merge_mode, self.envelope, self.methods = "DELEGATED", "HEAD_ATOMIC_BASE_OBSERVED", ("merge", "squash")
        self.validation_dir = self.base / "checks"
        self.flow = GitHubProductFlow(self.conductor, self.scope, self.validation, self.delegation)
        self.projects["one"] = replace(self.projects["one"], forge=self.forge, product_flow=self.flow)
        self.conductor.projects = self.projects
        self.generation = self.memory.inspect()["state"]["generation"]
        self.conductor._admit(self.admission, self.readiness.observe(), self.generation)

    def validation(self, provider, task):
        plan = provider.plan(task, Request(Operation.VALIDATE))
        checks = tuple(RequiredCheck("unit", "project", "fixture:project", phase, self.denominator) for phase in self.phases)
        policy = EvidencePolicy(plan.policy_digest, checks, self.now, self.now + 300)
        policy = replace(policy, evidence=self.authority.grant(purpose="project-validation/policy", subject=policy_subject(plan, policy)))
        def observer(query):
            result = ProjectResult("unit", "project", "fixture:project", task.repository_id, task.revision,
                "run:" + str(query.request.phase), "attempt:1", self.check_status, self.now,
                denominator=self.denominator, counts=self.counts, provider_status="synthetic-project")
            observation = ProjectObservation(digest(query), self.now, True, (result,))
            return replace(observation, evidence=self.authority.grant(purpose="project-validation/observation",
                subject=observation_subject(query, observation)))
        return ProjectValidation(provider, task, policy, ReportedEvidence(observer), directory=self.validation_dir,
            protected_roots=(self.root, self.memory.path), maximum_observations=32, clock=lambda: self.now)

    def delegation(self, admission, plan, scope):
        profile = DelegationProfile(admission.identity.repository_id, admission.identity.issue_id, admission.task_id,
            self.conductor._task(admission)["product_iteration"], plan.task.source_ref, "refs/heads/trunk", plan.task.revision,
            plan.policy_digest, scope, (Operation.PR, Operation.REPORT, Operation.MERGE), self.merge_mode, self.methods,
            self.envelope, self.now, self.now + 300)
        return replace(profile, evidence=self.authority.grant(purpose="github-product/delegation", subject=delegation_subject(profile)))

    def review(self):
        # Actual independent fixture runtime job, actual M2 acceptance, no local
        # per-test conversion of the target project's job-only CI.
        self.conductor._develop(self.admission, self.generation)
        self.conductor._review(self.admission, self.generation)
        self.assignment, self.job = self.conductor._job(self.admission, Role.COORDINATION, self.generation)
        return self.job

    def draft(self, *, ready=False):
        if not hasattr(self, "job"):
            self.review()
        pull = self.flow.draft(self.admission, self.job, self.generation)
        if ready and pull:
            self.server.pulls[0]["draft"] = False  # separately authorized external actor
        return pull
