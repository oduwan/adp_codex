"""Actual M1/M2/M3/M5 plus fake authenticated provider and real Git atomic CAS."""
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from adp.config import Config
from adp.discovery_schema import digest, typed
from adp.errors import ADPError
from adp.execution_ports import UnconfirmedValidation
from adp.execution_types import Role
from adp.guard_types import Permit, data
from adp.network_git import GitHubCAS, GitHubGitExecutionPort, GitHubPolicyAdapter, GitHubTarget
from adp.network_http import Response
from adp.policy import PolicyProvider
from adp.policy_types import Operation, Protection, Request, SourceClaim, SourceKind
from execution_fixtures import ExecutionFixture
from network_fixtures import ObjectServer, git_bytes, gv


class NetworkExecutionQualification(ExecutionFixture):
    def setUp(self):
        super().setUp()
        self.root = self.projects["one"].root
        self.target = GitHubTarget(self.config.identity, "R_opaque-network", 717, "owned-disposable", "fixture", "work/one")
        gv(self.root, "remote", "set-url", "team", self.target.endpoint + ".git")
        self.cfg = Config.discover(self.root, remote="team", repository_id=self.config.identity)
        self.product_remote = self.base / "network-product.git"; self.product_remote.mkdir()
        gv(self.product_remote, "init", "--bare", "--initial-branch=trunk")
        gv(self.product_remote, "fetch", "--no-tags", "--no-write-fetch-head", "--no-auto-maintenance", str(self.remote), self.initial)
        for ref in ("refs/heads/trunk", "refs/heads/work/one", "refs/heads/work/two"):
            gv(self.product_remote, "update-ref", ref, self.initial)
        self.server = ObjectServer(self.product_remote, self.target)
        self.service = GitHubCAS(self.target, self.server)
        self.port = GitHubGitExecutionPort(self.cfg, self.service, self.conductor.journal)
        def factory(admission, safety):
            adapter = GitHubPolicyAdapter(self.cfg, self.service, governance=(), fingerprint_worktree=True)
            provider = PolicyProvider(adapter, authority=self.authority, safety=safety, clock=lambda: self.now)
            source = SourceClaim(SourceKind.OPERATOR, "fixture:network-project-policy", "b" * 64,
                                 self.rules["one"], self.now, self.now + 300)
            provider.sources = (replace(source, evidence=self.authority.grant(purpose="policy/operator",
                subject=provider.source_subject(source))),)
            snapshot = adapter.inspect()
            protections = []
            for ref in (snapshot.source_ref, "refs/heads/trunk"):
                old = next((r.revision for r in snapshot.remote_refs if r.name == ref), None)
                p = Protection(ref, old, True, True, False, (), 1, (), (), "fixture:network-protection", self.now, self.now + 300)
                protections.append(replace(p, evidence=self.authority.grant(purpose="policy/protection", subject=provider.protection_subject(p))))
            provider.protections = tuple(protections)
            return provider
        self.projects["one"] = replace(self.projects["one"], git_port=self.port, policy_factory=factory)

    def prepare(self, *, absent=False, intermediate=False):
        (self.root / "product.py").write_text("def answer():\n    return 42\n")
        gv(self.root, "add", "product.py"); gv(self.root, "commit", "-m", "Independent canonical product commit")
        self.new = gv(self.root, "rev-parse", "HEAD")
        if intermediate:
            self.middle = self.new
            (self.root / "product.py").write_text("def answer():\n    return 42\n# exact later revision\n")
            gv(self.root, "add", "product.py"); gv(self.root, "commit", "-m", "Later exact product revision")
            self.new = gv(self.root, "rev-parse", "HEAD")
        admission = replace(self.admissions[0], expected_revision=self.new)
        self.discovery.snapshot = replace(self.discovery.snapshot, repository=replace(self.discovery.snapshot.repository, checkout_sha=self.new))
        if absent:
            gv(self.product_remote, "update-ref", "-d", self.target.ref, self.initial)  # Fixture setup only.
        generation = self.memory.inspect()["state"]["generation"]
        self.conductor._admit(admission, self.readiness.observe(), generation)
        _, job = self.conductor._job(admission, Role.COORDINATION, generation)
        self.admission, self.permit = admission, typed(Permit, job["permit"])
        provider, plan, auth = self.policy()
        self.action = {"task_key": __import__('adp.schema', fromlist=['key']).key(admission.task_id), "generation": generation,
            "operation": Operation.PUSH, "revision": plan.task.revision, "source_ref": plan.task.source_ref,
            "target": plan.target_ref, "expected_target": plan.expected_target, "payload": data(plan.payload),
            "status": "PREPARED", "observation": None, "plan_digest": digest(plan)}
        self.action_id = digest({"fixture": "one-durable-network-intent", "revision": self.new})
        self.conductor.journal.change(lambda execution, state, tasks: execution["actions"].update({self.action_id: self.action}))

    def policy(self):
        return self.conductor._authorize_policy(self.admission, self.permit, Request(Operation.PUSH))

    def submit(self, *, port=None, ticket=None):
        port = port or self.port
        if ticket is None:
            ticket = port.prepare_dispatch(self.action_id, self.action)
        self.conductor.journal.change(lambda execution, state, tasks: execution["actions"][self.action_id].update(status="SUBMITTED"))
        provider, plan, auth = self.policy()
        return port.submit(self.action, provider, plan, auth, dispatch=ticket)

    def test_existing_and_verified_absent_refs_preserve_exact_oid(self):
        self.prepare()
        before = self.server.refs()
        result = self.submit()
        self.assertEqual((result.status, result.revision), ("PRESENT", self.new))
        after = self.server.refs()
        self.assertEqual({k: v for k, v in before.items() if k != self.target.ref}, {k: v for k, v in after.items() if k != self.target.ref})
        self.assertEqual(after[self.target.ref], self.new)
        self.assertEqual(sum(kind == "ref" for kind, _ in self.server.mutations), 1)
        self.assertEqual(self.port.observe(self.action).status, "PRESENT")
        with self.assertRaises(ADPError): self.port.prepare_dispatch(self.action_id, self.action)

    def test_verified_absence_creation_has_zero_old_comparison(self):
        self.prepare(absent=True)
        before = self.server.refs()
        result = self.submit()
        self.assertEqual(result.status, "PRESENT")
        update = next(row for kind, row in self.server.mutations if kind == "ref")
        self.assertEqual(update["beforeOid"], "0" * 40)
        self.assertEqual(self.server.refs(), {**before, self.target.ref: self.new})

    def test_atomic_race_rejects_even_when_fast_forward_would_succeed(self):
        self.prepare(intermediate=True)
        # Install an intermediate ancestor at the atomic boundary. A normal
        # fast-forward would accept new, but expected-old must reject it.
        before = self.server.refs()
        self.server.before_cas = lambda: gv(self.product_remote, "update-ref", self.target.ref, self.middle, self.initial)
        self.assertEqual(self.submit().status, "UNKNOWN")
        self.assertEqual(self.server.refs(), {**before, self.target.ref: self.middle})
        self.assertEqual(gv(self.product_remote, "merge-base", self.middle, self.new), self.middle)
        self.assertFalse(any(kind == "ref" for kind, _ in self.server.mutations))

    def test_lost_acknowledgement_reobserves_once_and_restart_never_resubmits(self):
        self.prepare()
        self.server.lose_ack = True
        self.assertEqual(self.submit().status, "PRESENT")
        restarted = GitHubGitExecutionPort(self.cfg, self.service, self.conductor.journal)
        self.assertEqual(restarted.observe(self.action).status, "PRESENT")
        with self.assertRaises(ADPError): self.submit(port=restarted)
        self.assertEqual(sum(kind == "ref" for kind, _ in self.server.mutations), 1)

    def test_submitted_old_absent_changed_or_missing_claim_never_retries(self):
        self.prepare()
        ticket = self.port.prepare_dispatch(self.action_id, self.action)
        self.conductor.journal.change(lambda execution, state, tasks: execution["actions"][self.action_id].update(status="SUBMITTED"))
        self.port._claim_path(self.action_id).unlink()  # Simulated lost private runtime state.
        restarted = GitHubGitExecutionPort(self.cfg, self.service, self.conductor.journal)
        self.assertEqual(restarted.observe(self.action).status, "UNKNOWN")
        with self.assertRaises(ADPError): restarted.prepare_dispatch(self.action_id, self.action)
        provider, plan, auth = self.policy()
        with self.assertRaises(ADPError): restarted.submit(self.action, provider, plan, auth)
        with self.assertRaises(OSError): self.port.submit(self.action, provider, plan, auth, dispatch=ticket)
        self.assertFalse(self.server.mutations)
        gv(self.product_remote, "update-ref", "-d", self.target.ref, self.initial)
        self.assertEqual(restarted.observe(self.action).status, "UNKNOWN")

    def reject_mutation(self, change):
        self.prepare()
        before = self.server.refs()
        ticket = self.port.prepare_dispatch(self.action_id, self.action)
        self.conductor.journal.change(lambda execution, state, tasks: execution["actions"][self.action_id].update(status="SUBMITTED"))
        provider, plan, auth = self.policy()
        self.assertIn(ticket, self.port._dispatches)
        with self.assertRaises(ADPError):
            self.port.submit({**self.action, **change}, provider, plan, auth, dispatch=ticket)
        self.assertEqual(self.server.refs(), before)
        self.assertFalse(self.server.mutations)

    def test_binding_and_authorization_negatives_cannot_mutate(self):
        self.reject_mutation({"target": "refs/heads/other"})

    def test_mutated_revision_has_a_fresh_dispatch_and_cannot_mutate(self):
        self.reject_mutation({"revision": "d" * 40})

    def test_mutated_expected_old_has_a_fresh_dispatch_and_cannot_mutate(self):
        self.reject_mutation({"expected_target": "e" * 40})

    def test_mutated_source_has_a_fresh_dispatch_and_cannot_mutate(self):
        self.reject_mutation({"source_ref": "refs/heads/trunk"})

    def test_mutated_generation_has_a_fresh_dispatch_and_cannot_mutate(self):
        self.reject_mutation({"generation": 999999})

    def test_rules_permissions_upload_failures_and_uncertainty_refuse(self):
        self.prepare()
        before = self.server.refs()
        for key, value in (("permission", "READ"), ("protected", True), ("rules", [{"type": "required_signatures"}])):
            setattr(self.server, key, value)
            with self.subTest(key=key), self.assertRaises(ADPError): self.service.inspect_ref(writable=True)
            setattr(self.server, key, "WRITE" if key == "permission" else False if key == "protected" else [])
        self.server.failure = (lambda method, path, body: method == "POST" and "/git/" in path,
                               Response(403, b"do not publish credential-bearing response"))
        with self.assertRaises(OSError): self.submit()
        self.assertEqual(self.server.refs(), before)
        self.assertEqual(self.port.observe(self.action).status, "UNKNOWN")
        self.assertFalse(self.server.mutations)

    def test_absent_ref_legacy_protection_is_not_inferred_from_404(self):
        self.prepare(absent=True)
        self.server.legacy = 1
        with self.assertRaises(ADPError): self.submit()
        self.assertNotIn(self.target.ref, self.server.refs())
        self.assertFalse(self.server.mutations)

    def test_source_drift_during_upload_prevents_cas(self):
        self.prepare()
        before = self.server.refs()
        self.server.after_upload = lambda: gv(self.root, "update-ref", self.target.ref, self.initial, self.new)
        with self.assertRaises(ADPError): self.submit()
        self.assertEqual(self.server.refs(), before)
        self.assertFalse(any(kind == "ref" for kind, _ in self.server.mutations))
        self.assertEqual(self.port.observe(self.action).status, "UNKNOWN")

    def test_unknown_http_stop_is_durable_and_never_reconciles_present(self):
        self.prepare()
        original = self.server.request
        def lost_stop(*args, **kwargs):
            raise UnconfirmedValidation("validation:synthetic-network-stop", str(self.base / "private-stop"))
        with patch.object(self.server, "request", side_effect=lost_stop), self.assertRaises(ADPError):
            self.service.inspect_ref()
        self.assertTrue(self.port.unconfirmed_contexts())
        # Even exact desired remote state cannot hide a possibly live process.
        from adp.network_objects import closure
        other_service = GitHubCAS(self.target, self.server)
        other_service.upload(closure(self.root, self.new, other_service.known_commit))
        gv(self.product_remote, "update-ref", self.target.ref, self.new, self.initial)
        restarted_service = GitHubCAS(self.target, self.server)
        restarted = GitHubGitExecutionPort(self.cfg, restarted_service, self.conductor.journal)
        self.assertEqual(restarted.observe(self.action).status, "UNKNOWN")
        with self.assertRaises(ADPError): restarted.remote_revision(self.target.ref)
        self.assertTrue(self.conductor._quiesce((self.admission,)))
        with self.assertRaises(ADPError): self.conductor.handoff(authorized=True)

    def test_conductor_runs_and_reobserves_real_journal_without_helpers(self):
        def no_network_git(root, *args):
            self.assertNotIn("ls-remote", args)
            return gv(root, *args)
        self.server.lose_ack = True
        with patch("adp.policy_adapters.value", side_effect=no_network_git):
            result = self.conductor.run((self.admissions[0],), maximum_parallel=1, authorized=True)
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertEqual(sum(kind == "ref" for kind, _ in self.server.mutations), 1)
        self.assertEqual(len(self.forge._read()["items"]), 2)
        again = self.conductor.resume((self.admissions[0],), maximum_parallel=1, authorized=True)
        self.assertEqual(again["status"], "COMPLETE", again)
        self.assertEqual(sum(kind == "ref" for kind, _ in self.server.mutations), 1)
        self.assertEqual(self.conductor.handoff(authorized=True)["health"], "SYNCED")
