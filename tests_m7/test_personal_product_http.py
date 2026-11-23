"""Existing grammar/supervisor selection, exercised without live HTTP."""
from contextvars import ContextVar
import unittest
from unittest.mock import patch
from adp.errors import ADPError

from adp.discovery_github import Response
from adp.network_git import GitHubCAS, GitHubTarget, REF_QUERY, UPDATE_REFS_MUTATION
from adp.personal_product_child import validate_product
from adp.personal_product_http import PersonalProjectRead


class PersonalProductHTTPTests(unittest.TestCase):
    def test_only_draft_pr_and_exact_head_merge_mutations_are_selected(self):
        validate_product("POST", "/repos/owned/project/pulls", {"head": "work/task", "base": "trunk", "title": "Task", "body": "Refs #1", "draft": True}, 5)
        validate_product("PUT", "/repos/owned/project/pulls/10/merge", {"sha": "a" * 40, "merge_method": "merge"}, 5)
        for method in ("PATCH", "DELETE"):
            with self.assertRaises(ValueError):
                validate_product(method, "/repos/owned/project/pulls/10", {}, 5)

    def test_product_consent_cannot_upload_git_objects_or_update_refs(self):
        for path in ("/repos/owned/project/git/blobs", "/repos/owned/project/git/trees", "/repos/owned/project/git/commits", "/repos/owned/project/git/refs"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_product("POST", path, {}, 5)
        with self.assertRaises(ValueError):
            validate_product("POST", "/graphql", {"query": UPDATE_REFS_MUTATION, "variables": {}}, 5)

    def test_reports_issue_edits_readiness_and_unsupported_merges_refuse(self):
        for method, path, payload in (("POST", "/repos/owned/project/issues/1/comments", {"body": "spam"}),
            ("PUT", "/repos/owned/project/pulls/10/merge", {"sha": "a" * 40, "merge_method": "rebase"}),
            ("POST", "/graphql", {"query": "mutation { markPullRequestReadyForReview }", "variables": {}})):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_product(method, path, payload, 5)

    def test_actual_ci_native_protection_and_review_reads_are_supported(self):
        for suffix in ("/pulls/10/reviews?per_page=100&page=1", "/branches/trunk/protection",
            "/rules/branches/trunk?per_page=100&page=1", "/collaborators/reviewer/permission",
            "/commits/" + "a" * 40 + "/check-runs?filter=all&per_page=100&page=1"):
            validate_product("GET", "/repos/owned/project" + suffix, None, 5)

    def test_request_bounds_and_canonical_encoded_refs_are_unchanged(self):
        for path in ("/repos/owned/project/branches/%2fescape/protection", "/repos/owned/project/rules/branches/trunk?per_page=100&page=21", "https://evil.invalid/pulls"):
            with self.subTest(path=path), self.assertRaises((ValueError, ADPError)):
                validate_product("GET", path, None, 5)
        with self.assertRaises(ValueError):
            validate_product("GET", "/repos/owned/project", None, 6)

    def test_tighter_ci_deadline_reaches_shared_http_and_consumes_outer_budget(self):
        from adp.network_git import _Budget
        from types import SimpleNamespace
        import time
        observed = []
        class Transport:
            last_response = None
            def bind_repository(self, *args):
                pass
            def request(self, method, path, body, *, seconds):
                from adp.network_http import Response as NativeResponse
                observed.append(seconds)
                self.last_response = (200, b'{}', ())
                return NativeResponse(200, b'{}')
        service = GitHubCAS(GitHubTarget("17", "R_personal", 17, "owned", "project", "work/task"), Transport())
        outer = _Budget(time.monotonic() + 45)
        token = service._budget.set(outer)
        try:
            self.assertEqual(PersonalProjectRead(service).get("/repos/owned/project", seconds=.1).status, 200)
            self.assertGreater(observed[0], 0)
            self.assertLessEqual(observed[0], .1)
            self.assertEqual(outer.calls, 1)
            self.assertIs(service._budget.get(), outer)
        finally:
            service._budget.reset(token)
