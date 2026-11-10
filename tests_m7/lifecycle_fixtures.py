"""Issue22-only disposable fixtures; no real worker or GitHub qualification claim."""
from dataclasses import replace
import json

from product_flow_fixtures import ProductFixture
from execution_fixtures import FixtureRuntime
from adp.autonomous_track import AutonomousTrack, PreparationInputs, TaskSpec, TrackWindow
from adp.discovery_schema import digest
from adp.execution_types import Role, RuntimeObservation, RuntimeStatus, WorkerResult
from adp.guard_types import Outcome, Classification, ForensicPlan, ForensicReport
from adp.policy_types import CandidateValidationRequest, Operation, Request
from adp.project_validation import ProjectValidation, ReportedEvidence, observation_subject, policy_subject
from adp.project_validation_types import (CandidateProjectObservation, CandidateProjectResult, EvidencePolicy,
    Phase, ProjectObservation, ProjectResult, RequiredCheck, ResultStatus)
from adp.ticket_preparation import original_scope_subject, preparation_subject
from adp.ticket_types import Clause, OriginalScope, Part, PreparationReview, Proposal


class LifecycleRuntime(FixtureRuntime):
    def dispatch(self, request):
        if request.role != Role.FORENSIC:
            return super().dispatch(request)
        if request.id in self.observations:
            return self.observations[request.id]
        self.requests[request.id] = request
        self.dispatch_count += 1
        req = json.loads(request.prompt.split("\n", 1)[1])["forensic"]
        plan = ForensicPlan("one bounded original-scope correction", "accepted check verified", "failure persists",
            "evidence incomplete", ("deadline", "authority", "no progress"), seconds=30, samples=20, payload_bytes=10000)
        result = WorkerResult(Outcome.PASS, False, (), "Synthetic finite independent reassessment",
            ForensicReport(req["id"], Classification.PRODUCT_DEFECT, ("fixture:forensic",), "bounded correction", plan))
        observed = RuntimeObservation(request.id, self.host, RuntimeStatus.COMPLETED, "fixture-context:" + request.id,
            result, "fixture:runtime-receipt:" + request.id, 0, digest(request))
        self.observations[request.id] = observed
        return observed


class LifecycleFixture(ProductFixture):
    def setUp(self):
        super().setUp()
        self.runtime = LifecycleRuntime()
        self.authority.runtime = self.runtime
        self.conductor.runtime = self.runtime
        self.conductor.journal.upgrade_track(authorized=True)
        self.statuses = []
        self.queries = []
        self.action_count = 0
        self.action_id = None
        self.complete = True
        self.coverage = "COMPLETE"
        self.foreign = False
        self.window = TrackWindow("c" * 64, "d" * 64, self.now, self.now + 300, 8, 1)
        self.spec = TaskSpec(self.admission.identity, self.admission.task_id, "one", self.scope.preparer,
            self.assess, lambda packet: self.admission, self.validation, self.delegation,
            lambda: self.projects["one"].policy_factory(self.admission, None))
        self.track = AutonomousTrack(self.conductor, self.window, (self.spec,))

    def assess(self, original, track, inspection):
        reference = self.scope.preparer.archive.frozen_reference(original.issue.identity)
        scope = OriginalScope(reference, self.admission.product_goal,
            (Clause("goal", "OBJECTIVE", self.admission.product_goal), Clause("accept", "ACCEPTANCE", "criterion:answer")),
            self.admission.allowed_paths, ("unit",), ())
        scope = replace(scope, evidence=self.authority.grant(purpose="ticket/original-scope", subject=original_scope_subject(scope)))
        proposal = Proposal(reference, next(c.issue.revision for c in track.candidates if c.identity == original.issue.identity),
            inspection.digest, (Part("ticket", ("goal", "accept")),), instructions=("Use project-owned unit evidence",),
            exit_conditions=("Original acceptance or bounded stop",))
        review = PreparationReview("independent-fixture-preparer", self.now, self.now + 300)
        review = replace(review, evidence=self.authority.grant(purpose="ticket/preparation",
            subject=preparation_subject(original, scope, proposal, review, track)))
        return PreparationInputs(scope, proposal, review)

    def validation(self, provider, task, *, candidate=None, candidate_root=None):
        request = CandidateValidationRequest(Operation.VALIDATE, candidate=candidate) if candidate else Request(Operation.VALIDATE)
        plan = provider.plan(task, request)
        policy = EvidencePolicy(plan.policy_digest, tuple(RequiredCheck("unit", "project", "fixture:project", phase,
            self.denominator) for phase in self.phases), self.now, self.now + 300, action_id=self.action_id)
        policy = replace(policy, evidence=self.authority.grant(purpose="project-validation/candidate-policy" if candidate else "project-validation/policy", subject=policy_subject(plan, policy)))
        def observer(query):
            self.queries.append(query)
            status = self.statuses.pop(0) if self.statuses else self.check_status
            cls = CandidateProjectResult if candidate else ProjectResult
            extra = {"candidate_digest": "0" * 64 if self.foreign else digest(candidate)} if candidate else {}
            result = cls("unit", "project", "fixture:project", task.repository_id, task.revision,
                "run:" + str(len(self.queries)), "attempt:1", status, self.now, denominator=self.denominator,
                counts=self.counts, provider_status="synthetic-project", **extra)
            obs = (CandidateProjectObservation if candidate else ProjectObservation)(digest(query), self.now,
                self.complete, (result,), self.coverage, action_key=query.action_key)
            return replace(obs, evidence=self.authority.grant(purpose="project-validation/candidate-observation" if candidate else "project-validation/observation",
                subject=observation_subject(query, obs)))
        return ProjectValidation(provider, task, policy, ReportedEvidence(observer), directory=self.validation_dir,
            protected_roots=(self.root, self.memory.path), maximum_observations=32, clock=lambda: self.now,
            candidate=candidate, candidate_root=candidate_root)

    def attach(self, *, mode="CANDIDATE", action=None):
        self.spec = replace(self.spec, mode=mode, action=action)
        self.track = AutonomousTrack(self.conductor, self.window, (self.spec,))
        self.track._window(create=True)
        admission = self.track._prepare(self.spec, self.readiness.observe())
        if admission is None:
            raise AssertionError("Fixture original scope failed preparation")
        self.life = self.conductor.projects["one"].lifecycle
        self.life.bind(admission, self.generation)
        return self.life

    def dependent_track(self, *, dependent=True):
        """A real two-lane coordinator with an independently observed DONE edge."""
        from adp.discovery_types import Relation, Target
        from adp.guard_types import Attestation
        from adp.schema import key
        from adp.ticket_preparation import TicketArchive, TicketPreparer
        snapshot = self.discovery.snapshot
        first, second = snapshot.issues
        relation = Relation("BLOCKED_BY", Target("demo/project", 1, first.identity.issue_id), "NATIVE", "fixture:native")
        self.discovery.snapshot = replace(snapshot, issues=(first, replace(second, relations=(relation,) if dependent else ())))
        original_reviews = self.readiness.reviews
        def reviews(snapshots):
            result = list(original_reviews(snapshots))
            execution = self.conductor.journal.inspect()["state"]["execution"]
            current = execution["tasks"].get(key(self.admission.task_id))
            flow = execution["product_flows"].get(key(self.admission.task_id))
            if flow and flow["phase"] == "VALIDATED" and self.server.pulls:
                self.server.pulls[0]["draft"] = False  # separately authorized fixture project actor
            if current and current["stage"] == "COMPLETE" and self.server.pulls and self.server.pulls[0]["merged"] and self.server.comments:
                row = replace(result[0], completed=True, evidence=None)
                result[0] = self.readiness.planner.authority.sign(snapshots, row)
            return tuple(result)
        self.readiness.reviews = reviews
        grant = self.authority.grant
        def authority(*, purpose, subject, context=None):
            context = context or {}
            if purpose == "progress" and "review" in context:
                from adp.discovery_schema import typed
                from adp.discovery_types import ReadinessReview, Track
                review = typed(ReadinessReview, context["review"])
                track = typed(Track, context["track"])
                issue = next(c.issue for c in track.candidates if c.identity == review.identity)
                if review.completed and self.readiness.planner._verified(track.snapshots, issue, review, self.now):
                    receipt = Attestation(review.evidence.reviewer, "fixture:verified-prerequisite", subject)
                    self.authority.receipts.add((receipt, purpose))
                    return receipt
            return grant(purpose=purpose, subject=subject, context=context)
        self.authority.grant = authority
        second_admission = replace(self.admissions[1], requirement=replace(self.admissions[1].requirement,
            dependencies=("issue:" + digest(first.identity),) if dependent else ()))
        root = self.projects["two"].root
        class Lane:
            def discover(lane):
                return replace(self.discovery.snapshot, repository=replace(self.discovery.snapshot.repository,
                    checkout_ref="refs/heads/work/two", checkout_sha=second_admission.expected_revision))
        archive = TicketArchive(self.base / "scope-two", protected_roots=(root, self.memory.path))
        policy_factory = lambda: self.projects["two"].policy_factory(second_admission, None)
        preparer = TicketPreparer(adapters=(Lane(),), planner=self.readiness.planner, policy=policy_factory(),
            authority=self.authority, archive=archive, clock=lambda: self.now)
        def assess(original, track, inspection):
            reference = archive.frozen_reference(second.identity)
            scope = OriginalScope(reference, second_admission.product_goal,
                (Clause("goal", "OBJECTIVE", second_admission.product_goal), Clause("accept", "ACCEPTANCE", "criterion:answer")),
                second_admission.allowed_paths, ("unit",), (first.identity,) if dependent else ())
            scope = replace(scope, evidence=self.authority.grant(purpose="ticket/original-scope", subject=original_scope_subject(scope)))
            proposal = Proposal(reference, next(c.issue.revision for c in track.candidates if c.identity == second.identity),
                inspection.digest, (Part("ticket", ("goal", "accept")),), exit_conditions=("Original acceptance or bounded stop",))
            review = PreparationReview("independent-fixture-preparer", self.now, self.now + 300)
            review = replace(review, evidence=self.authority.grant(purpose="ticket/preparation",
                subject=preparation_subject(original, scope, proposal, review, track)))
            return PreparationInputs(scope, proposal, review)
        self.conductor.projects["two"] = replace(self.projects["two"], forge=self.forge)
        self.projects["two"] = self.conductor.projects["two"]
        spec = TaskSpec(second.identity, second_admission.task_id, "two", preparer, assess,
            lambda packet: second_admission, self.validation, self.delegation, policy_factory)
        request = self.server.request
        def routed(method, path, body=None, *, seconds):
            response = request(method, path, body, seconds=seconds)
            if method == "POST" and path.endswith("/pulls") and body["head"] == "work/two":
                from test_config import run
                self.server.pulls[-1]["head"]["sha"] = run(root, "rev-parse", "HEAD")
                return type(response)(response.status, json.dumps(self.server.pulls[-1]).encode())
            return response
        self.server.request = routed
        window = replace(self.window, maximum_tasks=2, maximum_parallel=2)
        return AutonomousTrack(self.conductor, window, (self.spec, spec)), second_admission


class SecondProfileFixture(LifecycleFixture):
    """Unrelated owned Git origin, opaque provider identity and project policy."""
    def setUp(self):
        from unittest.mock import patch
        import execution_fixtures as execution
        import product_flow_fixtures as product
        from adp.config import Config
        from adp.network_git import GitHubTarget
        from adp.network_http import Response
        from adp.policy_types import Permission, Effect, Protection
        from adp.schema import key
        from test_config import run
        configured = Config.discover
        def config(*args, **kwargs):
            kwargs["repository_id"] = "repo-opaque-B"
            return configured(*args, **kwargs)
        discover_execution, discover_product = execution.discover, product.discover_fixture
        def inventory(*args, **kwargs):
            kwargs["rid"] = "repo-opaque-B"
            return discover_execution(*args, **kwargs)
        def project_inventory(rows, **kwargs):
            kwargs.update(rid="repo-opaque-B", name="beta/firmware")
            return discover_product([product.issue(row["number"], name="beta/firmware") for row in rows], **kwargs)
        class Server(product.ProductServer):
            def bind_repository(server, node, database):
                if (node, database) != ("R_second", 18):
                    raise ValueError("Foreign second repository")
            def request(server, method, path, body=None, *, seconds):
                response = super().request(method, path.replace("/repos/beta/firmware", "/repos/demo/project"), body, seconds=seconds)
                raw = response.body.replace(b'R_product', b'R_second').replace(b'demo/project', b'beta/firmware')
                value = json.loads(raw)
                def ids(obj):
                    if type(obj) is dict:
                        if obj.get("node_id") == "R_second":
                            obj["id"] = 18
                        for item in obj.values(): ids(item)
                    elif type(obj) is list:
                        for item in obj: ids(item)
                ids(value)
                return Response(response.status, json.dumps(value).encode())
        def target(memory, node, database, owner, name, branch):
            return GitHubTarget(memory, "R_second", 18, "beta", "firmware", branch)
        with patch.object(Config, "discover", side_effect=config), patch.object(execution, "discover", side_effect=inventory), \
                patch.object(product, "discover_fixture", side_effect=project_inventory), patch.object(product, "ProductServer", Server), \
                patch.object(product, "GitHubTarget", side_effect=target):
            super().setUp()
        # Re-provision the fixture's not-started task before exercising #22.
        # No worker, effect, attempt or counter is erased or reset.
        assert not self.conductor._task(self.admission)["jobs"]
        self.conductor.journal.change(lambda execution, state, tasks: execution["tasks"].pop(key(self.admission.task_id)))
        run(self.root, "branch", "-m", "change/one")
        run(self.root, "push", "team", "change/one")
        run(self.remote, "update-ref", "refs/heads/stable", self.initial)
        self.rules["one"] = replace(self.rules["one"], base_branch="stable", branch_template="change/{slug}",
            subject_template="repair: {summary}", merge_method="squash", permissions=tuple(replace(p, effect=Effect.DENY) if p.operation == Operation.MERGE else p
                for p in self.rules["one"].permissions))
        factory = self.projects["one"].policy_factory
        def policy(admission, safety):
            provider = factory(admission, safety)
            snapshot = provider.adapter.inspect()
            protection = Protection("refs/heads/stable", self.initial, True, True, True, (), 1, ("squash",), (),
                "fixture:second-protection", self.now, self.now + 300, mergeable_methods=("squash",))
            protection = replace(protection, evidence=self.authority.grant(purpose="policy/protection",
                subject=provider.protection_subject(protection, snapshot)))
            provider.protections = (*provider.protections, protection)
            return provider
        self.projects["one"] = replace(self.projects["one"], policy_factory=policy)
        self.conductor.projects["one"] = self.projects["one"]
        self.discovery.snapshot = replace(self.discovery.snapshot, repository=replace(self.discovery.snapshot.repository,
            checkout_ref="refs/heads/change/one"))
        self.merge_mode, self.methods = "MANUAL", ("squash",)
        self.phases = (Phase.AFTER_PR,)
        self.spec = replace(self.spec, mode="POST_PR")
        self.window = replace(self.window, id="e" * 64, configuration="f" * 64)
        self.track = AutonomousTrack(self.conductor, self.window, (self.spec,))

    def delegation(self, admission, plan, scope):
        from adp.github_product import delegation_subject
        profile = replace(super().delegation(admission, plan, scope), base_ref="refs/heads/stable", evidence=None)
        return replace(profile, evidence=self.authority.grant(purpose="github-product/delegation", subject=delegation_subject(profile)))
