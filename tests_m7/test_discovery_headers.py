"""M8-F1: synthetic HTTP headers must not erase verified native dependencies."""
from __future__ import annotations

import io
import json
from email.message import Message
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from adp.discovery import complete_snapshot, DependencyPlanner
from adp.discovery_github import (API, MAX_RESPONSE, FixtureTransport,
    GitHubDiscoveryAdapter, GitHubHTTPTransport, Response, _NoRedirect)
from adp.discovery_types import Status
from adp.enrollment import inspect_project, local_checkout
from adp.errors import ADPError
from adp.guard_types import data
from adp.schema import string
from adp.runtime_limits import DEFAULTS
from discovery_fixtures import issue, responses
from test_config import GitFixture, run, snapshot as filesystem_snapshot


PREFIX = "/repos/alpha/product"
BLOCKED = PREFIX + "/issues/2/dependencies/blocked_by?per_page=100&page=1"
BENIGN = (("X-Empty", ""), ("X-Metadata", "first"), ("x-METADATA", "second"))
CONTROLS = ("link", "retry-after", "x-ratelimit-remaining", "x-ratelimit-reset")


def chain(headers=(), *, per_page=100):
    rows = [issue(n) for n in (1, 2, 3)]
    entries = responses(rows, per_page=per_page)
    for number in (2, 3):
        route = f"{PREFIX}/issues/{number}/dependencies/blocked_by?per_page={per_page}&page=1"
        entries[route] = Response(200, [rows[number - 2]])
        if per_page == 1:
            entries[route.replace("&page=1", "&page=2")] = Response(200, [])
    return {path: Response(row.status, row.body, headers) for path, row in entries.items()}


def observe(entries, **kwargs):
    transport = FixtureTransport(entries)
    result = GitHubDiscoveryAdapter("alpha/product", transport, clock=lambda: 100, **kwargs).discover()
    return result, transport


def get_response(transport):
    adapter = GitHubDiscoveryAdapter("alpha/product", transport)
    # The private request boundary normally receives these from discover().
    adapter._halt, adapter._requests = False, 0
    return adapter._get(PREFIX)


def native_edges(snapshot):
    return [(item.number, edge.kind, edge.target.number, edge.confidence)
            for item in snapshot.issues for edge in item.relations]


class DiscoveryHeaderTests(unittest.TestCase):
    def assert_chain(self, snapshot):
        self.assertTrue(complete_snapshot(snapshot), snapshot.coverage)
        self.assertEqual(native_edges(snapshot), [(2, "BLOCKED_BY", 1, "NATIVE"),
                                                (3, "BLOCKED_BY", 2, "NATIVE")])

    def get(self, headers=(), *, status=200, body=None):
        transport = FixtureTransport({PREFIX: Response(status, [] if body is None else body, headers)})
        return get_response(transport)

    def test_empty_repeated_and_combined_benign_headers_preserve_native_chain(self):
        for headers in (BENIGN[:1], BENIGN[1:], BENIGN):
            with self.subTest(headers=headers):
                self.assert_chain(observe(chain(headers))[0])
                self.assertEqual(self.get(headers).status, 200)

    def test_http_message_transport_preserves_status_body_and_native_chain(self):
        entries = chain()
        transport = GitHubHTTPTransport("synthetic-test-token")
        requests = []

        def opened(request, *, timeout):
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, DEFAULTS.request_timeout_seconds)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-test-token")
            self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
            self.assertEqual(request.get_header("X-github-api-version"), "2026-03-10")
            self.assertEqual(request.get_header("User-agent"), "adp-codex-read-only")
            self.assertTrue(request.full_url.startswith(API + PREFIX))
            requests.append(request.full_url)
            row = entries[request.full_url.removeprefix(API)]
            raw = io.BytesIO(json.dumps(row.body).encode())
            raw.code, raw.headers = row.status, Message()
            for name, value in BENIGN:
                raw.headers[name] = value
            return raw

        with patch.object(transport._opener, "open", side_effect=opened):
            response = transport.get(BLOCKED)
            self.assertEqual((response.status, response.body), (200, [issue(1)]))
            self.assertEqual(response.headers, tuple((n.lower(), v) for n, v in BENIGN))
            self.assert_chain(GitHubDiscoveryAdapter("alpha/product", transport, clock=lambda: 100).discover())
        self.assertTrue(requests)

    def test_malformed_names_values_and_pairs_fail_closed(self):
        for headers in ((("", "value"),), (("bad name", "value"),), (("bad:name", "value"),),
                        (("bad\nname", "value"),), (("x-name", "bad\r\nvalue"),),
                        (("x-name", "bad\x00value"),), (("x-name", "bad\x7fvalue"),),
                        (("x-name", 7),), ((7, "value"),), (("x-name",),), (None,), []):
            with self.subTest(headers=headers):
                self.assertEqual(self.get(headers).status, 0)

    def test_benign_header_count_name_and_value_bounds_are_unchanged(self):
        for headers in ((('x' * 128, 'v' * 4096),), (("x-repeat", ""),) * 128):
            with self.subTest(length=len(headers)):
                self.assertEqual(self.get(headers).status, 200)
        for headers in ((('x' * 129, 'v'),), (("x-name", "v" * 4097),),
                        (("x-repeat", ""),) * 129):
            with self.subTest(length=len(headers)):
                self.assertEqual(self.get(headers).status, 0)

    def test_control_headers_remain_unique_nonempty_and_case_insensitive(self):
        for name in CONTROLS:
            for values in (("1", "2"), ("1", "1")):
                with self.subTest(name=name, values=values):
                    self.assertEqual(self.get(BENIGN + ((name, values[0]), (name.upper(), values[1]))).status, 0)
            with self.subTest(name=name, value=""):
                self.assertEqual(self.get(BENIGN + ((name, ""),)).status, 0)

    def test_framing_representation_and_redirect_headers_are_not_benign_duplicates(self):
        for name in ("content-length", "transfer-encoding", "content-type", "content-encoding", "location"):
            with self.subTest(name=name):
                self.assertEqual(self.get(((name, "a"), (name.upper(), "b"))).status, 0)

    def test_ambiguous_native_endpoint_never_manufactures_complete_graph(self):
        for name in CONTROLS:
            entries = chain(BENIGN)
            entries[BLOCKED] = Response(200, [issue(1)], ((name, "1"), (name.upper(), "2")))
            with self.subTest(name=name):
                snapshot, _ = observe(entries)
                self.assertFalse(complete_snapshot(snapshot))
                self.assertNotIn((2, "BLOCKED_BY", 1, "NATIVE"), native_edges(snapshot))
                self.assertTrue(any(c.status == "UNKNOWN" for c in snapshot.coverage))
                self.assertTrue(all(c.status == Status.UNKNOWN for c in
                                    DependencyPlanner(clock=lambda: 100).plan((snapshot,)).candidates))

    def test_sequential_pagination_with_benign_headers_preserves_chain(self):
        entries = chain(BENIGN, per_page=1)
        first = PREFIX + "/issues?state=all&sort=created&direction=asc&per_page=1&page=1"
        second = first.replace("&page=1", "&page=2")
        row = entries[first]
        entries[first] = Response(200, row.body, BENIGN + (("Link", f'<{API}{second}>; rel="next"'),))
        snapshot, transport = observe(entries, per_page=1)
        self.assert_chain(snapshot)
        self.assertIn(second, transport.calls)

    def test_invalid_pagination_remains_partial_without_unsafe_followup(self):
        first = PREFIX + "/issues?state=all&sort=created&direction=asc&per_page=100&page=1"
        for link in ("invalid", '<https://evil.invalid/steal>; rel="next"',
                     f'<{API}/repos/other/product/issues?page=2>; rel="next"',
                     f'<{API}{first.replace("&page=1", "&page=3")}>; rel="next"'):
            entries = chain(BENIGN)
            entries[first] = Response(200, [issue(1)], BENIGN + (("link", link),))
            with self.subTest(link=link):
                snapshot, transport = observe(entries)
                self.assertFalse(complete_snapshot(snapshot))
                self.assertTrue(any(c.name == "issues" and c.status == "PARTIAL" for c in snapshot.coverage))
                self.assertTrue(all(p in entries for p in transport.calls))

    def test_permissions_rate_limits_and_unsupported_statuses_do_not_pass(self):
        for status, expected in ((401, "FORBIDDEN"), (403, "FORBIDDEN"), (429, "RATE_LIMITED"),
                                 (302, "UNKNOWN"), (404, "UNKNOWN"), (500, "UNKNOWN")):
            entries = chain(BENIGN)
            entries[BLOCKED] = Response(status, {"message": "private-error-payload"}, BENIGN)
            with self.subTest(status=status):
                snapshot, transport = observe(entries)
                self.assertFalse(complete_snapshot(snapshot))
                self.assertTrue(any(c.status == expected for c in snapshot.coverage))
                self.assertEqual(transport.calls.count(BLOCKED), 1)
                self.assertNotIn("private-error-payload", str(data(snapshot)))
                if status in (401, 403, 429):
                    self.assertEqual(transport.calls[-1], BLOCKED)

    def test_rate_limit_control_headers_still_halt_and_retain_retry_delay(self):
        path = PREFIX + "/pulls?state=all&sort=created&direction=asc&per_page=100&page=1"
        for status, controls, retry in ((200, (("X-RateLimit-Remaining", "0"),), None),
                                       (403, (("Retry-After", "30"),), 30),
                                       (429, (("Retry-After", "30"),), 30),
                                       (403, (("X-RateLimit-Remaining", "0"), ("X-RateLimit-Reset", "140")), 40)):
            entries = chain(BENIGN)
            entries[path] = Response(status, [], BENIGN + controls)
            with self.subTest(status=status, controls=controls):
                snapshot, transport = observe(entries)
                self.assertEqual(transport.calls[-1], path)
                self.assertFalse(complete_snapshot(snapshot))
                self.assertTrue(any(c.status == "NOTRUN" for c in snapshot.coverage))
                if retry is not None:
                    self.assertTrue(any(c.retry_after == retry for c in snapshot.coverage))

    def test_request_and_page_bounds_are_preserved(self):
        snapshot, transport = observe(chain(BENIGN), max_requests=2)
        self.assertFalse(complete_snapshot(snapshot))
        self.assertEqual(len(transport.calls), 2)
        snapshot, _ = observe(chain(BENIGN, per_page=1), per_page=1, max_pages=1)
        self.assertTrue(any(c.status == "PARTIAL" for c in snapshot.coverage))

    def test_transport_redirects_stay_non_success_without_following(self):
        transport = GitHubHTTPTransport("synthetic-test-token")
        for status in (301, 302, 307, 308):
            headers = Message()
            headers["Location"] = "https://evil.invalid/steal"
            response = urllib.error.HTTPError(API + PREFIX, status, "redirect", headers, io.BytesIO(b"private-redirect-body"))
            with self.subTest(status=status), patch.object(transport._opener, "open", side_effect=response) as opened:
                result = get_response(transport)
                self.assertEqual((result.status, result.body), (status, None))
                opened.assert_called_once()
            self.assertIsNone(_NoRedirect().redirect_request(None, None, status, "", headers, headers["Location"]))

    def test_transport_and_injected_json_size_and_shape_bounds_remain_strict(self):
        transport = GitHubHTTPTransport("synthetic-test-token")
        for payload in (b" " * (MAX_RESPONSE + 1), b'{"id":1,"id":2}', b"not-json"):
            raw = io.BytesIO(payload)
            raw.code, raw.headers = 200, Message()
            raw.headers["X-Empty"] = ""
            with self.subTest(size=len(payload)), patch.object(transport._opener, "open", return_value=raw):
                self.assertEqual(get_response(transport).status, 0)
        self.assertEqual(self.get(BENIGN, body="v" * (MAX_RESPONSE + 1)).status, 0)
        entries = chain(BENIGN)
        entries[BLOCKED] = Response(200, {"not": "an issue inventory"}, BENIGN)
        self.assertFalse(complete_snapshot(observe(entries)[0]))

    def test_headers_never_enter_portable_snapshot_and_shared_strings_stay_strict(self):
        headers = BENIGN + (("x-private-metadata", "private-header-payload"),)
        snapshot, _ = observe(chain(headers))
        self.assert_chain(snapshot)
        self.assertNotIn("private-header-payload", str(data(snapshot)))
        with self.assertRaises(ADPError):
            string("")


class DiscoveryHeaderInspectionTests(GitFixture):
    def test_read_only_inspection_keeps_native_chain_and_unknown_branch_rules(self):
        run(self.a, "remote", "add", "forge", "https://github.com/alpha/product.git")
        entries = chain(BENIGN)
        entries[PREFIX] = Response(200, {"id": 123, "node_id": "R-opaque", "full_name": "alpha/product",
                                         "default_branch": "trunk"}, BENIGN)
        entries[PREFIX + "/branches/trunk"] = Response(200, {"name": "trunk", "protected": True}, BENIGN)
        entries[PREFIX + "/rules/branches/trunk"] = Response(403, None, BENIGN)
        before = filesystem_snapshot(self.base)
        observation = inspect_project(local_checkout(self.a, "forge"), FixtureTransport(entries), "123")
        self.assertEqual(observation.facts["discovery"], "COMPLETE")
        self.assertEqual([[(edge["kind"], edge["number"]) for edge in row["native_dependencies"]]
                          for row in observation.facts["issues"]], [[], [("BLOCKED_BY", 1)], [("BLOCKED_BY", 2)]])
        self.assertEqual(observation.facts["branch_rules"][0]["rules"], "UNKNOWN")
        self.assertEqual(filesystem_snapshot(self.base), before)
