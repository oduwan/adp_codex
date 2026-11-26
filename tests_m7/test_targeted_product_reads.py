"""Exact targeted GitHub evidence; deterministic, no network or Workers."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.discovery_github import Response
from adp.errors import ADPError
from adp.execution_github import GitHubForgeBackend
from adp.forge_http_child import validate_request
from adp.personal_product_child import validate_product
from adp.personal_publication import PersonalPublication
from adp.personal_rules import product_refs
from adp.policy_types import Operation
from test_personal_rules import Native, HEAD, BASE


class TargetedProductReadTests(unittest.TestCase):
    def backend(self, pages):
        calls = []
        def request(method, path, body=None):
            calls.append((method, path))
            if path == "/repos/owned/project":
                return Response(200, {"id": 17, "full_name": "owned/project"})
            return pages[int(path.rsplit("=", 1)[1]) - 1]
        return GitHubForgeBackend("owned/project", "17", SimpleNamespace(request=request), None,
            head_ref="refs/heads/work/task"), calls

    def row(self, identity=1):
        return {"id": identity, "body": "ordinary product", "head": {"ref": "work/task", "sha": HEAD,
            "repo": {"id": 17, "full_name": "owned/project"}}}

    def test_filtered_inventory_is_complete_and_fresh_not_a_cached_absence(self):
        pages = [Response(200, [])]
        b, calls = self.backend(pages)
        self.assertEqual(b.inventory(Operation.PR, {}), ())
        pages[0] = Response(200, [self.row()])
        self.assertEqual(len(b.inventory(Operation.PR, {})), 1)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(path.endswith("state=all&head=owned%3Awork%2Ftask&per_page=100&page=1")
            for _, path in calls if "?" in path))

    def test_filtered_inventory_refuses_ignored_filter_fork_and_duplicate(self):
        for field, value in (("ref", "unrelated"), ("repo", {"id": 18, "full_name": "owned/project"}),
                             ("repo", {"id": 17, "full_name": "foreign/project"}), ("repo", None)):
            row = self.row();row["head"][field] = value
            b, _ = self.backend([Response(200, [row])])
            with self.subTest(field=field, value=value):self.assertIsNone(b.inventory(Operation.PR, {}))
        b, _ = self.backend([Response(200, [self.row(), self.row()])])
        self.assertIsNone(b.inventory(Operation.PR, {}))

    def test_filtered_inventory_pages_and_refuses_partial_or_oversized(self):
        full = [self.row(i + 1) for i in range(100)]
        for second, count in ((Response(200, [self.row(101)]), 101), (Response(403, None), None),
                              (Response(200, [self.row()]), None)):
            b, calls = self.backend([Response(200, full), second])
            rows = b.inventory(Operation.PR, {})
            self.assertEqual(None if rows is None else len(rows), count)
            self.assertEqual(len(calls), 3)
        b, _ = self.backend([Response(200, full)] * 3)
        self.assertIsNone(b.inventory(Operation.PR, {}))

    def test_lost_response_empty_inventory_remains_unknown(self):
        b, _ = self.backend([Response(200, [])])
        payload = {"body": "original", "revision": HEAD}
        self.assertEqual(b.observe("a"*64, Operation.PR, payload).status, "ABSENT")
        self.assertEqual(b.observe("a"*64, Operation.PR, payload, attempted=True).status, "UNKNOWN")

    def test_only_canonical_head_query_is_admitted_by_both_child_routes(self):
        path = "/repos/owned/project/pulls?state=all&head=owned%3Awork%2Ftask&per_page=100&page=1"
        for validator in (validate_request, validate_product):
            validator("GET", path, None, 10)
            for changed in (path.replace("owned%3A", "foreign%3A"), path.replace("%2F", "/"),
                            path.replace("state=all", "state=open"), path + "&extra=1",
                            path.replace("page=1", "page=21"), path.replace("work%2Ftask", "..%2Fsecret")):
                with self.subTest(validator=validator.__name__, path=changed), self.assertRaises(ValueError):
                    validator("GET", changed, None, 10)

    def test_known_refs_are_one_pinned_query_and_validate_all_semantic_fields(self):
        f = Native()
        self.assertEqual(product_refs(f.service, "refs/heads/trunk"), {f.target.ref: HEAD, "refs/heads/trunk": BASE})
        self.assertEqual(f.calls, [("POST", "/graphql")])
        for permission in ("READ", None):
            f.permission = permission
            with self.assertRaises(ADPError):product_refs(f.service, "refs/heads/trunk")
        f.permission = "WRITE"
        for base in ("refs/heads/changed", "refs/tags/trunk"):
            with self.assertRaises(ADPError):product_refs(f.service, base)
        f.current = None
        with self.assertRaises(ADPError):product_refs(f.service, "refs/heads/trunk")
        f.current, f.graph_error = HEAD, [{"message": "partial"}]
        with self.assertRaises(ADPError):product_refs(f.service, "refs/heads/trunk")

    def test_known_refs_refuse_repository_oid_and_object_type_drift(self):
        for field, value in (("name", "wrong"), ("prefix", "refs/tags/"),
                             ("target", {"oid": HEAD, "__typename": "Tag"}), ("target", {"oid": "bad", "__typename": "Commit"})):
            f = Native();original = f.service._repository
            def changed(*a):
                row = original(*a);row["ref"][field] = value;return row
            with patch.object(f.service, "_repository", side_effect=changed), self.subTest(field=field), self.assertRaises(ADPError):
                product_refs(f.service, "refs/heads/trunk")
    def test_selected_closure_excludes_unrelated_successor_but_requires_accepted_predecessor(self):
        p = PersonalPublication.__new__(PersonalPublication)
        p.target = SimpleNamespace(api="/repos/owned/project")
        p.personal = SimpleNamespace(plan={"issue": 2})
        track = SimpleNamespace(originals={"first": SimpleNamespace(issue=SimpleNamespace(number=1)),
            "third": SimpleNamespace(issue=SimpleNamespace(number=3))}, publication_prerequisites=Mock(return_value=("first",)))
        p.c = SimpleNamespace(track=track)
        self.assertEqual(p.original_bases(prerequisites=track.publication_prerequisites()),
            ("/repos/owned/project/issues/2", "/repos/owned/project/issues/1"))
        self.assertEqual(len(p.original_bases()), 3)  # Publication keeps its retained full-preflight map.
        track.publication_prerequisites.side_effect = ADPError("No accepted native predecessor")
        with self.assertRaisesRegex(ADPError, "accepted native"):
            p.original_bases(prerequisites=track.publication_prerequisites())

    def test_scoped_policy_refs_do_not_replace_signed_global_inventory(self):
        from adp.network_git import GitHubPolicyAdapter
        f = Native()
        f.service.refs = Mock(return_value=("unchanged-full-inventory",))
        with patch("adp.network_git._endpoint"):
            default = GitHubPolicyAdapter(SimpleNamespace(), f.service)
            self.assertEqual(default._remote_refs(None), ("unchanged-full-inventory",))
            scoped = GitHubPolicyAdapter(SimpleNamespace(), f.service, product_base="refs/heads/trunk")
            self.assertEqual({r.name: r.revision for r in scoped._remote_refs(None)},
                {f.target.ref: HEAD, "refs/heads/trunk": BASE})
        f.service.refs.assert_called_once_with()

    def test_product_rules_never_grant_unrelated_ref_operations(self):
        from adp.personal_product import PersonalProduct
        p = PersonalProduct.__new__(PersonalProduct)
        p.active = {"view": {"operation": "PR", "method": None,
            "facts": {"base_ref": "refs/heads/trunk", "checks": []}}}
        p.c = SimpleNamespace(rules=lambda: SimpleNamespace(branch_template="work/{slug}"))
        rules = p.rules()
        self.assertEqual({p.operation for p in rules.permissions}, {Operation.PR, Operation.VALIDATE})

    def test_legacy_submitted_receipt_map_is_observed_never_upgraded_or_redispatched(self):
        from contextlib import nullcontext
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from adp.personal_product import PersonalProduct
        from adp.runtime_limits import DEFAULTS
        with TemporaryDirectory() as directory:
            p = PersonalProduct.__new__(PersonalProduct)
            p.c = SimpleNamespace(episode=False, memory=SimpleNamespace(control=Path(directory)))
            p.clock = lambda: 100
            view = {"operation": "PR", "title": "original", "body": "Refs #1", "method": None,
                "original_observation": {"old-wide-map": "unchanged"}, "runtime_limits": DEFAULTS.values(),
                "issued_at": 90, "expires_at": 190}
            old = {"approval": "retained", "view": view, "action": "id", "requirement": "existing"}
            p.record = lambda: {"intents": [old]}
            p.service = SimpleNamespace(bounded=lambda **kw: nullcontext())
            p.live, p.local = Mock(), Mock()
            p.original = Mock(side_effect=AssertionError("No migration into new targeted write authority"))
            p.journal = SimpleNamespace(upgrade_product_flow=Mock(), inspect=lambda: {
                "state": {"execution": {"actions": {"id": {"status": "SUBMITTED", "payload": {"original": True}}}}}})
            p.forge = SimpleNamespace(observe=Mock(return_value="actual-observation"), submit=Mock())
            p.settle = Mock(return_value="settled-original")
            self.assertEqual(p.intent("PR", reviewed="retained", authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True), "settled-original")
            p.forge.observe.assert_called_once_with("id", "PR", {"original": True}, attempted=True)
            p.forge.submit.assert_not_called()
            p.original.assert_not_called()
