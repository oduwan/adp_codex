"""Issue37 boundary evidence, NOT a provider-free enrollment implementation.

Characterize reusable accepted ports and their current missing representations.
All authority receipts and GitHub observations below are explicit fixtures.
"""
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from adp.errors import ADPError
from adp.policy import PolicyProvider
from adp.policy_adapters import GitPolicyAdapter
from adp.policy_types import Effect, Operation, Request, SourceKind
from adp.project_validation import policy_subject
from adp.project_validation_github import GitHubEvidenceSource
from adp.project_validation_types import (EvidencePolicy, EvidenceRequest,
    ObservationQuery, Phase, RequiredCheck, ResultStatus)
from test_config import GitFixture, snapshot as filesystem_snapshot
from test_policy import PolicyFixture
from test_project_validation import FakeGitHub


class PersonalContractPolicyEvidence(PolicyFixture):
    def test_exact_operator_commit_choice_needs_no_project_policy_file(self):
        self.adapter.snapshot = replace(self.snapshot, documents=())
        provider = self.make_provider(kind=SourceKind.OPERATOR, reference="operator:exact-fixture-choice")
        inspection = provider.inspect_repository()
        self.assertEqual(inspection.snapshot.documents, ())
        self.assertEqual(inspection.conflicts, ())
        plan = provider.plan(self.task, Request(Operation.COMMIT, summary="Chosen fixture change"))
        self.assertEqual(plan.policy_effect, Effect.ALLOW)
        self.assertEqual(provider.decide(plan).effect, Effect.UNKNOWN)
        self.assertEqual(self.authorize(plan, provider=provider).effect, Effect.ALLOW)
        # This is an explicit synthetic operation instruction, not an invented
        # project rule or proof that a gh login grants commit authority.
        self.assertEqual(plan.payload.subject, "change(ABC-opaque): Chosen fixture change")

    def test_authenticated_empty_check_inventory_has_no_accepted_absence_gate(self):
        rules = replace(self.rules, checks=())
        self.adapter.snapshot = replace(self.snapshot, documents=(replace(self.document, profile=rules),))
        provider = self.make_provider(rules=rules)
        inspection = provider.inspect_repository()
        self.assertEqual(inspection.conflicts, ())
        self.assertEqual(len(inspection.sources), 1)
        self.assertEqual(inspection.sources[0].rules.checks, ())
        plan = provider.plan(self.task, Request(Operation.VALIDATE))
        self.assertEqual(plan.policy_effect, Effect.UNKNOWN)
        self.assertIn("No external validation/check matrix was specified", plan.reasons)
        with self.assertRaisesRegex(ADPError, "Invalid project check inventory"):
            policy_subject(plan, EvidencePolicy(plan.policy_digest, (), 90, 200))

    def test_native_pre_pr_observation_reuses_real_port_without_a_pull_or_issuer(self):
        checks = (RequiredCheck("build", "github-check", "github-app:9", Phase.BEFORE_PR),)
        server = FakeGitHub(self.task)
        source = GitHubEvidenceSource("disposable/two", self.task.repository_id, "777", checks,
                                      server, clock=lambda: self.now)
        request = EvidenceRequest(self.task.repository_id, self.task.source_ref, self.task.revision,
                                  "a" * 64, Phase.BEFORE_PR, self.task.task_id, 1, 7, 1)
        query = ObservationQuery(request, "fixture-observation", budget_ms=1000)
        observed = source.observe(query)
        self.assertTrue(observed.complete)
        self.assertEqual(observed.coverage, "COMPLETE")
        self.assertEqual(len(observed.results), 1)
        result = observed.results[0]
        self.assertEqual((result.repository_id, result.revision, result.run_id),
                         (self.task.repository_id, self.task.revision, "71"))
        self.assertEqual(result.status, ResultStatus.PASS)
        self.assertIsNone(result.denominator)
        self.assertEqual(result.counts, ())
        self.assertIsNone(result.attempt_id)
        self.assertIsNone(observed.evidence)  # Observation alone is not a gate.
        self.assertFalse(any("/pulls/" in call for call in server.calls))
        server.runs = [server.run(status="queued", conclusion=None, started_at=None, completed_at=None)]
        pending = source.observe(query)
        self.assertEqual(pending.results[0].status, ResultStatus.PENDING)
        server.task = replace(self.task, revision="f" * 40)
        stale = source.observe(query)
        self.assertFalse(stale.complete)
        self.assertNotEqual(stale.coverage, "COMPLETE")


class PersonalContractReadOnlyEvidence(GitFixture):
    def test_no_governance_documents_are_observed_without_inventing_rules(self):
        before = filesystem_snapshot(self.base)
        adapter = GitPolicyAdapter(self.config(), fingerprint_worktree=True)
        inspected = PolicyProvider(adapter).inspect_repository()
        self.assertEqual(inspected.snapshot.documents, ())
        self.assertEqual(inspected.sources, ())
        self.assertEqual(filesystem_snapshot(self.base), before)
