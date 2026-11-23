"""Current PR native evidence negatives using the actual #21 adapter/evaluator."""
from dataclasses import replace
from types import SimpleNamespace
import unittest

from adp.discovery_github import Response
from adp.discovery_schema import digest
from adp.guard_types import Attestation
from adp.project_validation import ProjectValidation
from adp.project_validation_github import GitHubEvidenceSource
from adp.project_validation_types import (EvidenceRequest, EvidencePolicy, Phase, RequiredCheck, PullIdentity, ObservationQuery)
from adp.personal_product import PersonalProduct
from adp.errors import ADPError


class PersonalProductCITests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.identity = PullIdentity("PR_actual_node", 10, "17")
        self.request = EvidenceRequest("17", "refs/heads/work/task", self.sha, "f" * 64, Phase.AFTER_PR, "one-task", 1, 1, 1, self.identity)
        self.run = {"id": 71, "name": "unit", "head_sha": self.sha, "app": {"id": 9},
            "url": "https://api.github.com/repos/owned/project/check-runs/71", "status": "completed", "conclusion": "success",
            "started_at": "1970-01-01T00:16:30Z", "completed_at": "1970-01-01T00:16:35Z"}
        self.rows, self.forbidden, self.pr_node, self.repository_id = [self.run], False, self.identity.id, 17
        self.rule = RequiredCheck("unit", "github-check", "github-app:9", Phase.AFTER_PR, native_record_is_attempt=True)

    def get(self, path, *, seconds):
        prefix = "/repos/owned/project"
        if self.forbidden:
            return Response(403, None)
        if path == prefix:
            return Response(200, {"id": self.repository_id, "full_name": "owned/project"})
        if "/git/ref/heads/" in path:
            return Response(200, {"ref": self.request.source_ref, "object": {"sha": self.sha}})
        if "/pulls/" in path:
            return Response(200, {"id": 2010, "node_id": self.pr_node, "number": 10, "state": "open",
                "head": {"ref": "work/task", "sha": self.sha, "repo": {"id": 17}}, "base": {"repo": {"id": 17}}})
        if "/check-suites?" in path:
            return Response(200, {"total_count": 1, "check_suites": [{"id": 70}]})
        return Response(200, {"total_count": len(self.rows), "check_runs": self.rows})

    def evaluate(self):
        receipts = set()
        def attest(query, observed):
            from adp.project_validation import observation_subject
            subject = observation_subject(query, observed)
            proof = Attestation("synthetic:native", "fixture:" + subject, subject)
            receipts.add(proof)
            return proof
        source = GitHubEvidenceSource("owned/project", "17", "17", (self.rule,), self, attest=attest, clock=lambda: 1000)
        query = ObservationQuery(self.request, "e" * 64, 1000)
        observed = source.observe(query)
        validation = ProjectValidation.__new__(ProjectValidation)
        validation.clock = lambda: 1000
        validation.policy = EvidencePolicy("f" * 64, (self.rule,), 900, 1100, result_maximum_age=300)
        validation.provider = SimpleNamespace(authority=SimpleNamespace(verify=lambda evidence, **kwargs: evidence in receipts and evidence.subject == kwargs["subject"]))
        return validation._evaluate(query, observed)

    def test_actual_opaque_pr_identity_and_unknown_counts_qualify(self):
        gate = self.evaluate()
        self.assertTrue(gate.qualified)
        self.assertIsNone(gate.results[0].denominator)
        self.assertIsNone(gate.results[0].attempt_id)
        self.assertEqual(gate.results[0].counts, ())

    def test_all_native_nonpass_outcomes_remain_nonpass(self):
        for state, conclusion, expected in (("in_progress", None, "PENDING"), ("completed", "failure", "FAIL"),
            ("completed", "action_required", "ERROR"), ("completed", "timed_out", "TIMEOUT"),
            ("completed", "skipped", "SKIP"), ("completed", "cancelled", "CANCELLED"), ("completed", "stale", "UNKNOWN")):
            with self.subTest(conclusion=conclusion):
                self.run.update(status=state, conclusion=conclusion)
                gate = self.evaluate()
                self.assertEqual(gate.status, expected)
                self.assertFalse(gate.qualified)

    def test_missing_and_duplicate_checks_cannot_be_pass(self):
        for rows in ([], [self.run, {**self.run, "id": 72, "url": self.run["url"].removesuffix("71") + "72"}]):
            self.rows = rows
            self.assertFalse(self.evaluate().qualified)

    def test_previous_sha_and_foreign_app_cannot_be_pass(self):
        self.run["head_sha"] = "b" * 40
        self.assertFalse(self.evaluate().qualified)
        self.run["head_sha"] = self.sha
        self.run["app"] = {"id": 999}
        self.assertFalse(self.evaluate().qualified)

    def test_foreign_repository_and_rest_id_as_node_id_refuse(self):
        self.repository_id = 18
        self.assertFalse(self.evaluate().qualified)
        self.repository_id = 17
        self.pr_node = "2010"
        self.assertFalse(self.evaluate().qualified)

    def test_permission_failure_and_stale_native_record_remain_unknown(self):
        self.forbidden = True
        self.assertFalse(self.evaluate().qualified)
        self.forbidden = False
        self.run["completed_at"] = "1970-01-01T00:00:00Z"
        self.assertFalse(self.evaluate().qualified)

    def test_missing_attempt_is_not_manufactured_without_project_assent(self):
        self.rule = replace(self.rule, native_record_is_attempt=False)
        self.assertFalse(self.evaluate().qualified)

    def test_readonly_outsider_approval_does_not_satisfy_native_review(self):
        f = PersonalProduct.__new__(PersonalProduct)
        f.record = lambda: {"pull": {"number": 10}}
        f.c = SimpleNamespace(revision=lambda: self.sha)
        f.target = SimpleNamespace(api="/repos/owned/project")
        f.personal = SimpleNamespace(plan={"owner": {"account_id": 91}})
        row = {"id": 1, "state": "APPROVED", "commit_id": self.sha, "user": {"id": 102, "login": "outsider"}}
        f.forge = SimpleNamespace(reviews=lambda *args: [row])
        f.read = SimpleNamespace(get=lambda path: Response(200, {"user": {"id": 102}, "permission": "read"}))
        with self.assertRaisesRegex(ADPError, "approvals missing"):
            f.native_reviews({"user": {"id": 91}}, {"policy": {"native_reviews": 1}})
        f.read = SimpleNamespace(get=lambda path: Response(403, None))
        with self.assertRaisesRegex(ADPError, "eligibility unknown"):
            f.native_reviews({"user": {"id": 91}}, {"policy": {"native_reviews": 1}})
