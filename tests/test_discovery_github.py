"""GET-only adapter, pagination, permissions, identity and drift negatives."""
from __future__ import annotations

import copy
import io
import unittest
from dataclasses import replace
from unittest.mock import patch

from adp.discovery import DependencyPlanner
from adp.discovery_github import (API, FixtureTransport, GitHubDiscoveryAdapter,
    GitHubHTTPTransport, Response, _NoRedirect)
from adp.discovery_schema import digest, key, load_snapshot
from adp.discovery_types import Status
from adp.errors import ADPError
from adp.guard_types import data
from discovery_fixtures import Authority, assessed, discover, issue, pull, responses


class GitHubDiscoveryTests(unittest.TestCase):
    def test_malformed_timeline_entries_are_incomplete_without_losing_the_issue(self):
        path = "/repos/alpha/product/issues/1/timeline?per_page=100&page=1"
        for event in (None, {"event": "cross-referenced", "source": {"issue": None}}):
            snapshot, _ = discover(changed={path: Response(200, [event])})
            with self.subTest(event=event):
                self.assertEqual(len(snapshot.issues), 1)
                self.assertTrue(any(c.status != "COMPLETE" for c in snapshot.coverage))
                authority = Authority()
                track = DependencyPlanner(authority=authority, clock=lambda: 100).plan((snapshot,), reviews=assessed(snapshot, authority))
                self.assertEqual(track.candidates[0].status, Status.UNKNOWN)

    def test_overlapping_pr_pages_keep_partial_preview_without_duplicate_hydration(self):
        path = "/repos/alpha/product/pulls?state=all&sort=created&direction=asc&per_page=1&page=2"
        snapshot, transport = discover(prs=[pull(10), pull(11)], per_page=1, changed={path: Response(200, [pull(10)])})
        self.assertEqual([p.number for p in snapshot.pulls], [10])
        self.assertEqual(transport.calls.count("/repos/alpha/product/pulls/10"), 1)
        self.assertTrue(any(c.name == "pulls" and c.status == "PARTIAL" for c in snapshot.coverage))
    def test_native_duplicate_history_and_cross_reference_without_event_id(self):
        pr = pull()
        source = {**issue(10), "node_id": pr["node_id"], "pull_request": {"url": pr["url"]}}
        events = [{"event": "cross-referenced", "source": {"issue": source}},
                  {"event": "marked_as_duplicate", "id": 51}]
        path = "/repos/alpha/product/issues/1/timeline?per_page=100&page=1"
        snapshot, _ = discover(prs=[pr], changed={path: Response(200, events)})
        self.assertTrue(all(c.status == "COMPLETE" for c in snapshot.coverage))
        self.assertEqual(snapshot.issues[0].relations[0].kind, "PULL_REQUEST")
        self.assertIn("duplicate history", snapshot.issues[0].notices[0])

    def test_malformed_link_and_missing_author_never_qualify_readiness(self):
        path = "/repos/alpha/product/issues?state=all&sort=created&direction=asc&per_page=100&page=1"
        snapshot, _ = discover(changed={path: Response(200, [issue()], (("link", '<https://[invalid>; rel="next"'),))})
        self.assertTrue(any(c.status == "PARTIAL" for c in snapshot.coverage))
        snapshot, _ = discover([{**issue(), "user": None}])
        self.assertTrue(any(c.status == "UNKNOWN" for c in snapshot.coverage))
        self.assertEqual(DependencyPlanner(clock=lambda: 100).plan((snapshot,)).candidates[0].status, Status.UNKNOWN)

    def test_pr_detail_drift_from_inventory_is_not_a_stable_head(self):
        pr = pull()
        changed = {"/repos/alpha/product/pulls/10": Response(200, pull(sha="c" * 40))}
        snapshot, _ = discover(prs=[pr], changed=changed)
        self.assertTrue(any(c.name == "pull-stable:10" and c.status == "CHANGED" for c in snapshot.coverage))

    def test_pagination_and_pr_filter_keep_all_opaque_issues(self):
        rows = [issue(1), issue(2)]
        pr_issue = issue(10)
        pr_issue["pull_request"] = {"url": API + "/repos/alpha/product/pulls/10"}
        snapshot, transport = discover(rows + [pr_issue], [pull()], per_page=2)
        self.assertEqual([i.number for i in snapshot.issues], [1, 2])
        self.assertEqual(snapshot.pulls[0].head_sha, "a" * 40)
        self.assertTrue(all(c.status == "COMPLETE" for c in snapshot.coverage))
        self.assertTrue(any("page=2" in call for call in transport.calls))
        self.assertEqual(load_snapshot(data(snapshot)), snapshot)

    def test_authenticated_transport_has_fixed_origin_get_and_no_redirects(self):
        transport = GitHubHTTPTransport("synthetic-test-token")
        response = io.BytesIO(b'{"id":1}')
        response.code, response.headers = 200, {}
        with patch.object(transport._opener, "open", return_value=response) as opened:
            observed = transport.get("/repos/alpha/product")
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, API + "/repos/alpha/product")
        self.assertEqual(observed.status, 200)
        for route in ("https://evil.invalid/steal", "/repos/a/b/../../users", "/repos/a/b?token=secret%0a", "/graphql"):
            with self.subTest(route=route), self.assertRaises(ADPError):
                transport.get(route)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))

    def test_permission_failure_marks_unknown_without_retry_or_empty_inventory(self):
        path = "/repos/alpha/product/issues/1/dependencies/blocked_by?per_page=100&page=1"
        snapshot, transport = discover(changed={path: Response(403, {"message": "PRIVATE CONTENT"})})
        self.assertTrue(any(c.status == "FORBIDDEN" for c in snapshot.coverage))
        self.assertEqual(transport.calls.count(path), 1)
        self.assertEqual(DependencyPlanner(clock=lambda: 100).plan((snapshot,)).candidates[0].status, Status.UNKNOWN)
        self.assertNotIn("PRIVATE CONTENT", str(data(snapshot)))

    def test_rate_limit_preserves_partial_inventory_and_retry_delay(self):
        path = "/repos/alpha/product/issues?state=all&sort=created&direction=asc&per_page=1&page=2"
        snapshot, transport = discover([issue(1), issue(2)], per_page=1,
            changed={path: Response(429, None, (("retry-after", "30"), ("x-ratelimit-remaining", "0")))})
        self.assertTrue(any(c.status == "PARTIAL" and c.retry_after == 30 for c in snapshot.coverage))
        self.assertTrue(any(c.status == "NOTRUN" for c in snapshot.coverage))
        self.assertEqual(transport.calls[-1], path)
        self.assertNotIn("READY", str(data(DependencyPlanner(clock=lambda: 100).plan((snapshot,)))))

    def test_primary_rate_reset_and_success_exhaustion_stop_followup_requests(self):
        for response in (Response(403, None, (("x-ratelimit-remaining", "0"), ("x-ratelimit-reset", "140"))),
                         Response(200, [], (("x-ratelimit-remaining", "0"),))):
            path = "/repos/alpha/product/pulls?state=all&sort=created&direction=asc&per_page=100&page=1"
            snapshot, transport = discover(changed={path: response})
            self.assertEqual(transport.calls[-1], path)
            self.assertTrue(any(c.status == "NOTRUN" for c in snapshot.coverage))
            if response.status == 403:
                self.assertTrue(any(c.retry_after == 40 for c in snapshot.coverage))

    def test_partial_pagination_and_duplicate_pages_are_not_complete(self):
        route = "/repos/alpha/product/issues?state=all&sort=created&direction=asc&per_page=1&page=2"
        for changed in ({route: Response(500, None)}, {route: Response(200, [issue(1)])}):
            snapshot, _ = discover([issue(1), issue(2)], per_page=1, changed=changed)
            self.assertTrue(any(c.name == "issues" and c.status == "PARTIAL" for c in snapshot.coverage))
        snapshot, _ = discover([issue(1), issue(2)], per_page=1, max_pages=1)
        self.assertTrue(any(c.status == "PARTIAL" for c in snapshot.coverage))

    def test_adversarial_pagination_link_never_receives_credentials(self):
        path = "/repos/alpha/product/issues?state=all&sort=created&direction=asc&per_page=100&page=1"
        for link in ('<https://evil.invalid/repos/alpha/product/issues?page=2>; rel="next"',
                     '<https://api.github.com/repos/other/project/issues?page=2>; rel="next"', "not a link"):
            snapshot, transport = discover(changed={path: Response(200, [issue()], (("link", link),))})
            self.assertTrue(any(c.name == "issues" and c.status == "PARTIAL" for c in snapshot.coverage))
            self.assertTrue(all(call.startswith("/repos/alpha/product") for call in transport.calls))

    def test_unavailable_native_links_are_unknown_not_independence(self):
        for endpoint in ("dependencies/blocked_by", "sub_issues"):
            path = f"/repos/alpha/product/issues/1/{endpoint}?per_page=100&page=1"
            snapshot, _ = discover(changed={path: Response(404, None)})
            authority = Authority()
            result = DependencyPlanner(authority=authority, clock=lambda: 100).plan((snapshot,), reviews=assessed(snapshot, authority))
            self.assertEqual(result.candidates[0].status, Status.UNKNOWN)

    def test_native_blocking_and_subissue_semantics_are_separate(self):
        changed = {"/repos/alpha/product/issues/2/dependencies/blocked_by?per_page=100&page=1": Response(200, [issue(1)]),
                   "/repos/alpha/product/issues/1/sub_issues?per_page=100&page=1": Response(200, [issue(2)])}
        snapshot, _ = discover([issue(1), issue(2)], changed=changed)
        first, second = snapshot.issues
        self.assertEqual(first.relations[0].kind, "SUB_ISSUE")
        self.assertEqual(second.relations[0].kind, "BLOCKED_BY")
        self.assertTrue(all(r.confidence == "NATIVE" for i in snapshot.issues for r in i.relations))

    def test_issue_edits_and_inventory_changes_are_explicit(self):
        row = issue()
        edited = {**row, "body": "Changed accepted scope", "updated_at": "2026-11-09T09:00:00Z"}
        snapshot, _ = discover([row], changed={"/repos/alpha/product/issues/1": Response(200, edited)})
        self.assertTrue(any(c.status == "CHANGED" for c in snapshot.coverage))
        path = "/repos/alpha/product/issues?state=all&sort=created&direction=asc&per_page=100&page=1"
        snapshot, _ = discover([row], changed={path: (Response(200, [row]), Response(200, [row, issue(2)]))})
        self.assertTrue(any(c.name == "inventory-stable" and c.status == "CHANGED" for c in snapshot.coverage))

    def test_different_list_detail_fields_do_not_manufacture_issue_drift(self):
        snapshot, _ = discover(changed={"/repos/alpha/product/issues/1": Response(200, {**issue(), "extra_api_field": True})})
        self.assertTrue(all(c.status == "COMPLETE" for c in snapshot.coverage))

    def test_stable_repository_pin_and_foreign_objects_fail_closed(self):
        values = responses()
        with self.assertRaisesRegex(ADPError, "identity mismatch"):
            GitHubDiscoveryAdapter("alpha/product", FixtureTransport(values), expected_id="different").discover()
        snapshot, _ = discover([issue(name="other/product")])
        self.assertEqual(snapshot.issues, ())
        self.assertTrue(any(c.status == "PARTIAL" for c in snapshot.coverage))
        values["/repos/alpha/product"] = (values["/repos/alpha/product"], Response(200, {"id": "replacement", "full_name": "alpha/product"}))
        snapshot = GitHubDiscoveryAdapter("alpha/product", FixtureTransport(values), clock=lambda: 100).discover()
        self.assertTrue(any(c.name == "context-stable" and c.status == "CHANGED" for c in snapshot.coverage))

    def test_linked_pr_current_head_and_deleted_fork_are_preserved_honestly(self):
        pr = pull()
        source = issue(10)
        source["node_id"], source["pull_request"] = pr["node_id"], {"url": pr["url"]}
        event = {"id": "event-opaque", "event": "cross-referenced", "source": {"issue": source}}
        path = "/repos/alpha/product/issues/1/timeline?per_page=100&page=1"
        snapshot, _ = discover(prs=[pr], changed={path: Response(200, [event])})
        self.assertEqual(snapshot.issues[0].relations[0].kind, "PULL_REQUEST")
        self.assertEqual(snapshot.pulls[0].head_repository_id, "fork-opaque")
        missing_fork = copy.deepcopy(pr)
        missing_fork["head"]["repo"] = None
        snapshot, _ = discover(prs=[missing_fork])
        self.assertTrue(any(c.status == "UNKNOWN" for c in snapshot.coverage))

    def test_duplicate_identity_and_limits_refuse_without_inventing_task(self):
        rows = [issue(1), issue(2, iid="I-opaque-1")]
        with self.assertRaises(ADPError):
            discover(rows)
        snapshot, transport = discover(max_requests=1)
        self.assertTrue(any(c.status == "NOTRUN" for c in snapshot.coverage))
        self.assertEqual(len(transport.calls), 1)
