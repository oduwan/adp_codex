"""R1/R2 typed stage operands, expiry/restart and default-verifier negatives."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.execution_types import Role
from adp.guard_types import data
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductAuthority
from adp.policy_types import Review
from adp.runtime_limits import RuntimeSettings, operation_scope
import test_lifecycle_reuse as lifecycle
from test_policy import PolicyFixture


class ResidualReuseTests(unittest.TestCase):
    def subject(self):
        helper = lifecycle.LifecycleReuseTests(); self.addCleanup(helper.doCleanups)
        workers, worker, current = helper.worker()
        from tempfile import TemporaryDirectory
        from pathlib import Path
        directory = TemporaryDirectory(); self.addCleanup(directory.cleanup)
        c = workers.c
        c.workers, c.task_id = workers, "task"
        c.personal = SimpleNamespace(state=Path(directory.name), intent={"approval": "operator"},
            plan={"window": {"expires_at": 300}})
        c.clock, c.revision = lambda: 100, lambda: worker["request"]["revision"]
        c.worker = Mock(side_effect=lambda *args: deepcopy(worker))
        c.require_development_protocol = Mock()
        c.live = Mock(side_effect=lambda **kw: deepcopy(current))
        latest = {"status": "NOT_REQUIRED", "observed_at": 95, "revision": c.revision(), "policy": "approved", "verified_absence": True}
        row = {"gates": [latest], "review": worker["request"]["id"]}
        flow = PersonalProduct.__new__(PersonalProduct)
        flow.c, flow.personal, flow.clock = c, c.personal, c.clock
        flow.active = {"view": {"issued_at": 90, "expires_at": 200}}
        flow.record = Mock(side_effect=lambda **kw: deepcopy(row))
        flow.qualified = Mock(side_effect=lambda: deepcopy(row["gates"][-1]) if row["gates"][-1]["status"] == "NOT_REQUIRED" else (_ for _ in ()).throw(ADPError("Current CI failed")))
        flow.verify_review = Mock(side_effect=lambda **kw: workers.actual(worker, approval=True, accounted=True))
        flow.review_principals = lambda: {"worker:" + worker["request"]["id"]}
        flow.ci_specification = SimpleNamespace(contract="ci", gate="actual")
        c.product = flow
        fixture = PolicyFixture(methodName="runTest"); fixture.setUp();self.addCleanup(fixture.doCleanups)
        plan = fixture.provider.determine_pr(fixture.task, "Original")
        review = Review("worker:" + worker["request"]["id"], c.revision(), True, 95, 200)
        subject = fixture.provider.review_subject(plan, review)
        return c, flow, row, worker, current, plan, review, subject

    def test_typed_operands_are_reused_but_not_across_operations_or_restart(self):
        c, flow, row, worker, current, plan, review, subject = self.subject()
        with operation_scope(RuntimeSettings()):
            authority = ProductAuthority(c, qualification=(digest(flow.active["view"]), deepcopy(row["gates"][-1]), deepcopy(worker)))
            evidence = authority._proof("policy/review", subject, "product-review", {"plan": data(plan), "value": data(review)}, review.reviewer)
            for _ in range(3):self.assertTrue(authority.verify(evidence, purpose="policy/review", subject=subject))
            flow.verify_review.assert_not_called();flow.qualified.assert_not_called()
            self.assertEqual(c.allowed.call_count, 8)  # current CI + assignment Guard per validation
            c.clock = lambda: 200
            self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))
            c.clock = lambda: 100
        self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))
        with operation_scope(RuntimeSettings()):
            self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))
            default = ProductAuthority(c)
            self.assertTrue(default.verify(evidence, purpose="policy/review", subject=subject))
            flow.verify_review.assert_called_once_with()
            c.runtime.observe.return_value = replace(c.runtime.observe.return_value, stopped=False)
            self.assertFalse(default.verify(evidence, purpose="policy/review", subject=subject))

    def test_same_sha_changed_ci_review_assignment_generation_or_revocation_refuse(self):
        for change in ("ci", "review", "assignment", "generation", "owner", "revoked", "view", "source"):
            c, flow, row, worker, current, plan, review, subject = self.subject()
            with self.subTest(change=change), operation_scope(RuntimeSettings()):
                authority = ProductAuthority(c, qualification=(digest(flow.active["view"]), deepcopy(row["gates"][-1]), deepcopy(worker)))
                evidence = authority._proof("policy/review", subject, "product-review", {"plan": data(plan), "value": data(review)}, review.reviewer)
                if change == "ci":row["gates"][-1]["status"] = "FAIL"
                if change == "review":row["review"] = "other"
                if change == "assignment":next(iter(current["tasks"].values()))["assignments"]["assignment"]["status"] = "pending"
                if change == "generation":current["state"]["generation"] += 1
                if change == "owner":current["local_owner"] = False
                if change == "revoked":c.allowed.side_effect = ADPError("Revoked")
                if change == "view":flow.active["view"]["expires_at"] += 1
                if change == "source":c.revision = lambda: "f"*40
                self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))

    def test_ci_qualification_projects_record_and_guard_from_one_actual_snapshot(self):
        c, flow, row, worker, current, plan, review, _ = self.subject()
        c.memory.inspect.reset_mock()
        self.assertEqual(PersonalProduct.qualified(flow), row["gates"][-1])
        c.memory.inspect.assert_called_once_with()
        c.allowed.assert_called_once()
        self.assertEqual(c.allowed.call_args.kwargs["_observed"], current)
        row["gates"][-1]["status"] = "FAIL"
        with self.assertRaises(ADPError):PersonalProduct.qualified(flow)
        row["gates"][-1]["status"] = "NOT_REQUIRED"
        row["gates"][-1]["verified_absence"] = False
        with self.assertRaises(ADPError):PersonalProduct.qualified(flow)

    def test_refreshed_native_principals_invalidate_removed_or_replaced_eligibility(self):
        c, flow, row, worker, current, plan, review, _ = self.subject()
        eligible = {"github-user:102"}
        flow.review_principals = lambda: eligible | {"worker:" + worker["request"]["id"]}
        native = replace(review, reviewer="github-user:102")
        from adp.policy import PolicyProvider
        subject = PolicyProvider(None).review_subject(plan, native)
        with operation_scope(RuntimeSettings()):
            authority = ProductAuthority(c, qualification=(digest(flow.active["view"]), deepcopy(row["gates"][-1]), deepcopy(worker)))
            evidence = authority._proof("policy/review", subject, "product-review", {"plan": data(plan), "value": data(native)}, native.reviewer)
            self.assertTrue(authority.verify(evidence, purpose="policy/review", subject=subject))
            eligible.clear()  # Final native reobservation lost approval/permission.
            self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))
            eligible.add("github-user:103")  # A new actor cannot satisfy the old proof.
            self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))

    def test_proof_writes_share_an_actual_subject_but_verification_observes_new_generation(self):
        c, flow, row, worker, current, plan, review, subject = self.subject()
        with operation_scope(RuntimeSettings()):
            actual = c.live();c.live.reset_mock()
            authority = ProductAuthority(c, qualification=(digest(flow.active["view"]), deepcopy(row["gates"][-1]), deepcopy(worker)))
            evidence = authority._proof("policy/review", subject, "product-review", {"plan": data(plan), "value": data(review)}, review.reviewer, _observed=actual)
            c.live.assert_not_called()
            current["state"]["generation"] += 1
            self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))
            c.live.assert_called_once_with()

    def test_default_verification_does_not_convert_old_same_sha_pass_to_allow(self):
        c, flow, row, worker, current, plan, review, subject = self.subject()
        authority = ProductAuthority(c)
        evidence = authority._proof("policy/review", subject, "product-review", {"plan": data(plan), "value": data(review)}, review.reviewer)
        row["gates"][-1]["status"] = "FAIL"
        flow.verify_review.side_effect = lambda **kw: flow.qualified()
        self.assertFalse(authority.verify(evidence, purpose="policy/review", subject=subject))


class ResidualDiagnosticsTests(unittest.TestCase):
    def test_response_and_proof_adapters_preserve_a_known_budget_refusal(self):
        from adp.github_product import _Responses
        from adp.runtime_limits import BudgetRefusal
        failure = BudgetRefusal("REQUEST_DEADLINE_EXHAUSTED", "bounded private cause")
        service = SimpleNamespace(runtime_settings=RuntimeSettings(), request=Mock(side_effect=failure))
        with self.assertRaises(BudgetRefusal) as caught:_Responses(service).request("GET", "/synthetic")
        self.assertIs(caught.exception, failure)
        from adp.personal_network import PersonalDiscoveryRead
        service.transport = SimpleNamespace(last_response=None)
        with self.assertRaises(BudgetRefusal) as caught:PersonalDiscoveryRead(service).get("/synthetic")
        self.assertIs(caught.exception, failure)
        from adp.discovery_github import GitHubDiscoveryAdapter
        adapter = GitHubDiscoveryAdapter("owned/project", SimpleNamespace(get=Mock(side_effect=failure)))
        adapter._halt, adapter._requests = False, 0
        with self.assertRaises(BudgetRefusal) as caught:adapter._get("/repos/owned/project")
        self.assertIs(caught.exception, failure)
        authority = ProductAuthority.__new__(ProductAuthority)
        authority.c = SimpleNamespace(episode=False, live=Mock(side_effect=failure))
        with self.assertRaises(BudgetRefusal) as caught:authority.verify(None, purpose="policy/review", subject="subject")
        self.assertIs(caught.exception, failure)

        from adp.personal_publication import PersonalPublication
        from adp.personal_storage import PersonalBlocked
        owner = {"push_access": True}
        repo = {"node_id": "R_owned", "default_branch": "trunk"}
        for origin in ("record", "inspect_ref"):
            publication = PersonalPublication.__new__(PersonalPublication)
            publication.personal = SimpleNamespace(plan={"owner": owner, "repository": {"default_branch": "trunk"}})
            publication.target = SimpleNamespace(node_id="R_owned", branch="work/issue-1")
            publication.record = Mock(side_effect=failure if origin == "record" else None, return_value=None)
            publication.service = SimpleNamespace(inspect_ref=Mock(side_effect=failure))
            with self.subTest(origin=origin):
                with self.assertRaises(BudgetRefusal) as caught:
                    publication.remote(_identity=(repo, owner))
                self.assertIs(caught.exception, failure)
                self.assertEqual(caught.exception.reason, "REQUEST_DEADLINE_EXHAUSTED")
        publication.service.inspect_ref.side_effect = ADPError("Private underlying policy error")
        with self.assertRaises(PersonalBlocked) as caught:publication.remote(_identity=(repo, owner))
        self.assertEqual(caught.exception.reason, "FEATURE_POLICY_UNVERIFIED")
        self.assertNotIn("Private underlying", str(caught.exception))

        from adp.enrollment import inspect_project, Blocked
        checkout = {"repository": "owned/project", "path": "/owned/disposable", "remote": "origin"}
        for owner, route in ((None, "adp.enrollment.GitHubDiscoveryAdapter"),
                ({"push_access": True}, "adp.personal_discovery.PersonalGitHubDiscoveryAdapter")):
            with self.subTest(adapter=route), patch("adp.enrollment.canonical", return_value={"name": "owned/project", "repository_id": "17"}), \
                    patch("adp.enrollment.Config.discover", return_value=object()), patch(route) as adapter:
                adapter.return_value.discover.side_effect = failure
                with self.assertRaises(BudgetRefusal) as caught:inspect_project(checkout, object(), "17", personal_owner=owner)
                self.assertIs(caught.exception, failure)
                adapter.return_value.discover.side_effect = ADPError("Private malformed discovery")
                with self.assertRaises(Blocked) as caught:inspect_project(checkout, object(), "17", personal_owner=owner)
                self.assertEqual(caught.exception.reason, "DISCOVERY_UNAVAILABLE")
                self.assertEqual(caught.exception.status, "UNKNOWN")
                self.assertNotIn("Private malformed", str(caught.exception))

    def test_effect_boundaries_are_retained_without_disclosing_unknown_labels(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import json
        from adp.personal_cli import _retain_measurements
        from adp.runtime_limits import reached
        from test_runtime_limits import service
        client = service()
        names = ("effect.prepared", "effect.submitted", "effect.dispatch_requested", "effect.acknowledged", "effect.observed", "effect.settled")
        with client.bounded(name="product.intent"):
            for name in names:reached(name)
            reached("PRIVATE_HOST_AND_CREDENTIAL")
        with TemporaryDirectory() as directory:
            root = Path(directory);root.chmod(0o700)
            result = _retain_measurements(SimpleNamespace(state=root), {"rows": client.measurements, "dropped": 0, "errors": 0}, 1)
            self.assertEqual(result["status"], "RETAINED")
            body = json.loads((root / "runtime-diagnostics.json").read_bytes())
            self.assertEqual(body["operations"][0]["boundaries"], {name: 1 for name in names})
            self.assertNotIn("PRIVATE_HOST", json.dumps(body))

    def test_pre_transport_deadline_keeps_exact_reason_and_confirms_no_process_started(self):
        from adp.runtime_limits import BudgetRefusal, current_budget
        from test_runtime_limits import service
        client = service()
        from adp.runtime_limits import Budget
        original = Budget.check_request
        with patch.object(Budget, "check_request", lambda budget, *a, **kw: original(budget, 0)), self.assertRaises(BudgetRefusal):
            client.request("GET", "/synthetic")
        self.assertEqual(client.transport.calls, [])
        self.assertEqual(client.unconfirmed_contexts(), ())
        self.assertEqual(client.measurements[-1]["transport_calls"], 0)
        self.assertEqual(client.measurements[-1]["final_refusal"], "REQUEST_DEADLINE_EXHAUSTED")


class ResidualValidationTests(unittest.TestCase):
    def fixture(self, personal=True):
        import test_project_validation as baseline
        f = baseline.ProjectValidationTests(methodName="runTest");f.setUp();self.addCleanup(f.doCleanups)
        if personal:
            # A narrow unit discriminator only: retain the established signed
            # fixture verifier; actual ProductAuthority/CI is exercised by the
            # stopped-receipt production stage fixture, not fabricated here.
            authority = ProductAuthority.__new__(ProductAuthority)
            authority.verify = f.authority.verify
            f.provider.authority = authority
        return f

    def test_one_actual_plan_per_personal_request_and_default_independent_decide_retained(self):
        from adp.project_validation_types import Phase
        for personal, expected in ((True, 1), (False, 2)):
            f = self.fixture(personal)
            auth = f.auth()
            with self.subTest(personal=personal), patch.object(f.provider, "plan", wraps=f.provider.plan) as plans, patch.object(f.provider, "decide", wraps=f.provider.decide) as decisions:
                f.validation.request(Phase.BEFORE_PR, authorization=auth)
                self.assertEqual(plans.call_count, expected)
                self.assertEqual(decisions.call_count, int(not personal))

    def test_late_owner_safety_is_not_reused_from_the_just_built_plan(self):
        from adp.project_validation_types import Phase
        f = self.fixture(); auth = f.auth(); actual = f.provider.plan
        def drift(*a, **kw):
            plan = actual(*a, **kw)
            f.safety.value = replace(f.safety.value, owns_memory=False)
            return plan
        with patch.object(f.provider, "plan", side_effect=drift), self.assertRaisesRegex(ADPError, "Current exact M3"):
            f.validation.request(Phase.BEFORE_PR, authorization=auth)

    def test_native_query_closing_request_remains_independent_and_changed_source_policy_refuse(self):
        from adp.project_validation_types import Phase
        for change in (None, "index", "policy", "owner"):
            f = self.fixture(); auth = f.auth(); original = f.source.observe
            def observe(query):
                result = original(query)
                if change == "index":f.adapter.snapshot = replace(f.adapter.snapshot, index_digest="f"*64)
                if change == "policy":f.adapter.snapshot = replace(f.adapter.snapshot, documents=())
                if change == "owner":f.safety.value = replace(f.safety.value, owns_memory=False)
                return result
            with self.subTest(change=change), patch.object(f.source, "observe", side_effect=observe), patch.object(f.provider, "plan", wraps=f.provider.plan) as plans:
                result = f.validation.observe(Phase.BEFORE_PR, authorization=auth)
                self.assertEqual(plans.call_count, 2)
                self.assertEqual(str(result.status), "PASS" if change is None else "UNKNOWN")

    def test_borrowed_factory_plan_is_initial_only_and_cannot_cross_operation_or_provider(self):
        from adp.project_validation_types import Phase
        from adp.runtime_limits import current_budget
        f = self.fixture(); auth = f.auth()
        with operation_scope(RuntimeSettings()):
            plan = f.provider.plan(f.task, __import__("adp.policy_types", fromlist=["Request"]).Request(__import__("adp.policy_types", fromlist=["Operation"]).Operation.VALIDATE))
            observed = (current_budget(), f.provider, plan)
            with patch.object(f.provider, "plan", wraps=f.provider.plan) as plans:
                result = f.validation.observe(Phase.BEFORE_PR, authorization=auth, _plan=observed)
                self.assertEqual(str(result.status), "PASS")
                self.assertEqual(plans.call_count, 1)  # The independent native-query closing observation.
            for bad in ((None, f.provider, plan), (current_budget(), object(), plan),
                        (current_budget(), f.provider, replace(plan, task=replace(plan.task, generation=2)))):
                with self.subTest(bad=str(type(bad[1]))), self.assertRaisesRegex(ADPError, "borrowed personal plan"):
                    f.validation.request(Phase.BEFORE_PR, authorization=auth, _plan=bad)
        with operation_scope(RuntimeSettings()), self.assertRaisesRegex(ADPError, "borrowed personal plan"):
            f.validation.request(Phase.BEFORE_PR, authorization=auth, _plan=observed)
        signed = self.fixture(False)
        with operation_scope(RuntimeSettings()), self.assertRaisesRegex(ADPError, "borrowed personal plan"):
            signed.validation.request(Phase.BEFORE_PR, authorization=signed.auth(), _plan=observed)


class ResidualHistoricalReadTests(unittest.TestCase):
    def test_selected_port_is_narrowed_without_default_credential_lookup(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from adp.personal_track import PersonalTrack
        from adp.personal_history_track import NativeReadOnly
        port = SimpleNamespace(request=Mock(return_value="read-result"))
        track = PersonalTrack.__new__(PersonalTrack)
        track.c = SimpleNamespace(transport=SimpleNamespace(service=SimpleNamespace(transport=port)))
        with TemporaryDirectory() as root:
            track.completion_path = lambda identity: Path(root)/"not-completed"
            with patch("adp.personal_history_track.NativeReadOnly", wraps=NativeReadOnly) as narrowed:
                self.assertIsNone(track.accepted("uncompleted"))
                narrowed.assert_called_once_with(port)
        read = NativeReadOnly(port)
        self.assertEqual(read.request("GET", "/selected", None, seconds=1), "read-result")
        port.request.reset_mock()
        with self.assertRaisesRegex(ADPError, "GET only"):read.request("POST", "/selected", {}, seconds=1)
        port.request.assert_not_called()


class ResidualNextTests(unittest.TestCase):
    def test_shared_admission_still_refuses_late_parent_drift_and_restart_reobserves(self):
        from contextlib import nullcontext
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from adp.discovery_types import Repository, Snapshot
        from adp.personal_enrollment import PersonalChoices
        from adp.personal_storage import read_private
        from adp.personal_track import PersonalTrack
        for changed in ("checkpoint", "generation", "retained-snapshot", "retained-completion"):
            with self.subTest(changed=changed), TemporaryDirectory() as directory:
                base = Path(directory)
                state = base / "state"; state.mkdir(mode=0o700)
                track = PersonalTrack.__new__(PersonalTrack)
                track.root, track.personal = base / "track", SimpleNamespace(state=state)
                snapshot = Snapshot(Repository("17", "owned/project", "https://github.com/owned/project"), (), (), (), 100)
                observation = SimpleNamespace(snapshot=snapshot)
                view = {"schema_version": 1, "completions": {}, "snapshot": data(snapshot),
                    "parent_generation": 1, "parent_checkpoint": "a"*40,
                    "plan": {"effects": {"directory": str(base / "child")}, "checkout": {"head": "b"*40}}}
                retained = {"view": view, "approval": "exact-next", "setup": "exact-setup"}
                fresh = not changed.startswith("retained-")
                parent = {"local_owner": True, "local_head": "f"*40 if changed == "checkpoint" else "a"*40,
                    "state": {"generation": 2 if changed == "generation" else 1}}
                track.c = SimpleNamespace(episode=False, transport=None, ci_transport=None,
                    memory=SimpleNamespace(inspect=Mock(return_value=parent)), invocation=Mock(), run=Mock())
                product = SimpleNamespace(transport=None, service=SimpleNamespace(bounded=lambda **kw: nullcontext()),
                    facts=Mock(return_value={"base_sha": "b"*40}))
                track.next_record = Mock(return_value=None if fresh else retained)
                track.successor = Mock(return_value=(None, False))
                result = {"next_issue": 2}
                def preview(product, choices, **kw):
                    kw["_observation"].append((result, observation, {}, None))
                    return {"result": view, "approval": "exact-next", "setup_approval": "exact-setup"}
                track.next_preview = Mock(side_effect=preview if fresh else AssertionError("Retained intent is not a fresh admission"))
                observed = SimpleNamespace(snapshot=replace(snapshot, repository=replace(snapshot.repository, name="other/project"))) if changed == "retained-snapshot" else observation
                completed = {"changed": {"source": "c"*40}} if changed == "retained-completion" else {}
                track.status = Mock(side_effect=AssertionError("Share actual same-stage admission") if fresh else None,
                    return_value=(result, observed, completed))
                choices = PersonalChoices(2, base / "child", ("product",))
                with patch("adp.personal_track.apply_personal", side_effect=AssertionError("Refuse before enrollment")) as apply:
                    with self.assertRaisesRegex(ADPError, "Previous window changed|Previous generation changed|Original next-intent observations changed"):
                        track.next(product, choices, reviewed="exact-next", setup_approval="exact-setup", authorized=True)
                apply.assert_not_called();track.c.invocation.assert_not_called();track.c.run.assert_not_called()
                if fresh:
                    track.status.assert_not_called()
                    self.assertEqual(read_private(state / "next-intent.json"), retained)
                    track.c.memory.inspect.assert_called_once_with()
                else:
                    track.status.assert_called_once()
                    track.c.memory.inspect.assert_not_called()
