"""Focused Free-private compatibility proofs; synthetic transports only."""
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.discovery_github import Response, GitHubHTTPTransport
from adp.discovery_schema import digest
from adp.enrollment import branch_rules
from adp.errors import ADPError
from adp.github_rules import MESSAGE, RULES_DOC, PROTECTION_DOC, PLAN_ASSENT, plan_error, retained_error
from adp.network_git import GitHubCAS, GitHubTarget, GitHubGitExecutionPort, _Budget
from adp.network_http import Response as NativeResponse
from adp.personal_github import PersonalGitHubRead
from adp.personal_network import PersonalDiscoveryRead
from adp.personal_rules import PERSONAL_REF_QUERY, enrollment_rules
from adp.personal_publication import PersonalPublication
from adp.personal_product import PersonalProduct
from adp.personal_product_policy import observe_policy
from personal_fixtures import PersonalFixture

HEAD = "a" * 40
BASE = "b" * 40
HEADERS = (("content-type", "application/json; charset=utf-8"),)


def denied(*, classic=False, headers=HEADERS, **changes):
    return Response(403, {"message": MESSAGE, "documentation_url": PROTECTION_DOC if classic else RULES_DOC,
        "status": "403", **changes}, headers)


class Native:
    """Fresh native response semantics, no network or worker launch."""
    def __init__(self):
        self.target = GitHubTarget("17", "R_personal", 17, "owned", "project", "work/task")
        self.repository = {"repository_id": "17", "database_id": 17, "node_id": "R_personal", "name": "owned/project", "default_branch": "trunk"}
        self.owner = {"account_id": 91, "repository_id": "17", "read_access": True, "push_access": True, "admin_access": True}
        self.repo = {"id": 17, "node_id": "R_personal", "full_name": "owned/project", "default_branch": "trunk", "private": True,
            "owner": {"id": 91, "type": "User"}, "permissions": {"pull": True, "push": True, "admin": True}}
        self.prefix = self.target.api
        self.entries = {"/user": Response(200, {"id": 91}), self.prefix: Response(200, self.repo)}
        for name, sha in (("trunk", BASE), ("work%2Ftask", HEAD)):
            self.entries[self.prefix + "/branches/" + name] = Response(200, {"name": name.replace("%2F", "/"), "protected": False, "commit": {"sha": sha}})
            self.entries[self.prefix + "/rules/branches/" + name] = denied()
            self.entries[self.prefix + "/rules/branches/" + name + "?per_page=100&page=1"] = denied()
            self.entries[self.prefix + "/branches/" + name + "/protection"] = denied(classic=True)
        self.current, self.permission, self.graph_error, self.account = HEAD, "ADMIN", None, 91
        self.calls, self.last_response = [], None
        self.before = None
        self.service = GitHubCAS(self.target, self, personal=True)
        self.service.personal_context = (self.repository, self.owner)

    def bind_repository(self, *identity):
        assert identity == ("R_personal", 17)

    def get(self, path):
        self.calls.append(("GET", path))
        if self.before:
            self.before(path)
        if path == "/user":
            return Response(200, {"id": self.account})
        return self.entries.get(path, Response(404, None))

    def request(self, method, path, body, *, seconds):
        assert 0 < seconds <= 5
        if path == "/graphql":
            self.calls.append((method, path))
            item = None if self.current is None else {"name": "work/task", "prefix": "refs/heads/",
                "target": {"oid": self.current, "__typename": "Commit"}, "branchProtectionRule": None}
            repo = {"id": "R_personal", "databaseId": 17, "nameWithOwner": "owned/project", "viewerPermission": self.permission,
                "defaultBranchRef": {"name": "trunk", "prefix": "refs/heads/", "target": {"oid": BASE, "__typename": "Commit"}},
                "ref": item, "branchProtectionRules": {"totalCount": 0, "nodes": [], "pageInfo": {"hasNextPage": False}}}
            result = Response(200, {"data": {"node": repo}, **({"errors": self.graph_error} if self.graph_error else {})})
        else:
            assert method == "GET", "No external mutation admitted by this fixture"
            result = self.get(path)
        raw = json.dumps(result.body).encode()
        self.last_response = result.status, raw, result.headers
        return NativeResponse(result.status, raw)


class PersonalRulesTests(unittest.TestCase):
    def test_exact_plan_error_is_distinct_from_empty_or_unknown(self):
        path = "/repos/owned/project/rules/branches/work%2Ftask"
        self.assertEqual(plan_error(denied(), path)["status"], "PLAN_UNAVAILABLE")
        self.assertIsNone(plan_error(Response(200, []), path))
        for status in (0, 200, 401, 404, 429, 500):
            self.assertIsNone(plan_error(Response(status, denied().body, HEADERS), path))
        self.assertNotEqual(digest(plan_error(denied(), path)), digest([]))

    def test_wrong_missing_extra_and_ambiguous_error_bodies_refuse(self):
        path = "/repos/owned/project/rules/branches/trunk"
        for body in (None, [], {}, {**denied().body, "message": "Access Denied"},
                {**denied().body, "documentation_url": RULES_DOC + "/"}, {**denied().body, "status": 403},
                {**denied().body, "private": "SECRET_PAYLOAD"}, {"message": MESSAGE}):
            with self.subTest(body=body):
                self.assertIsNone(plan_error(Response(403, body, HEADERS), path))
        for raw in (b'{"message":"x","message":"y"}', b'null', b'not-json', b' ' * 4097):
            self.assertIsNone(retained_error(403, raw, HEADERS, path))
        self.assertIsNone(retained_error(403, json.dumps(denied().body).encode(), HEADERS, "/repos/owned/project/issues/1"))

    def test_missing_conflicting_rate_redirect_and_pagination_headers_refuse(self):
        path = "/repos/owned/project/rules/branches/trunk"
        for headers in ((), (("content-type", "text/html"),), HEADERS + HEADERS,
                HEADERS + (("x-ratelimit-remaining", "0"),), HEADERS + (("retry-after", "1"),),
                HEADERS + (("x-ratelimit-remaining", "unknown"),), HEADERS + (("location", "https://evil.invalid"),),
                HEADERS + (("link", "unverified"),), HEADERS + (("content-type", ""),)):
            with self.subTest(headers=headers):
                self.assertIsNone(plan_error(denied(headers=headers), path))
        self.assertIsNotNone(plan_error(denied(headers=HEADERS + (("x-benign", ""), ("x-benign", "ok"))), path))

    def test_personal_reads_retain_only_exact_safe_error_and_signed_reads_drop_it(self):
        path = "/repos/owned/project/rules/branches/trunk"
        class Reply(io.BytesIO):
            code = 403
            headers = dict(HEADERS)
        raw = json.dumps(denied().body).encode()
        for cls, expected in ((PersonalGitHubRead, denied().body), (GitHubHTTPTransport, None)):
            t = cls("SYNTHETIC_TOKEN")
            t._opener = SimpleNamespace(open=lambda *a, **kw: Reply(raw))
            self.assertEqual(t.get(path).body, expected)
        f = Native()
        self.assertEqual(PersonalDiscoveryRead(f.service).get(path).body, denied().body)
        f.entries[path] = denied(extra="SECRET_PAYLOAD")
        self.assertIsNone(PersonalDiscoveryRead(f.service).get(path).body)
        f.service._live_unknown = True
        self.assertEqual(PersonalDiscoveryRead(f.service).get(path).status, 0)

    def test_personal_enrollment_classifies_without_rewriting_signed_observation(self):
        f = Native()
        result = enrollment_rules(f, f.repository, f.owner, "trunk")
        self.assertEqual(result["rules"], "PLAN_UNAVAILABLE")
        self.assertEqual(result["required_check_contexts"], [])
        self.assertIn("separately accept", result["rules_action"])
        self.assertEqual(branch_rules(f, "owned/project", "trunk")["rules"], "UNKNOWN")
        self.assertTrue(all(method == "GET" for method, _ in f.calls))

    def test_public_foreign_org_permission_and_third_read_drift_refuse(self):
        for mutation in (lambda f: f.repo.update(private=False), lambda f: f.repo.update(id=18),
                lambda f: f.repo.update(node_id="R_other"), lambda f: f.repo["owner"].update(type="Organization"),
                lambda f: f.repo["owner"].update(id=92), lambda f: f.repo["permissions"].update(admin=False),
                lambda f: f.repo["permissions"].update(push=None), lambda f: setattr(f, "account", 92)):
            f = Native(); mutation(f)
            with self.subTest(mutation=mutation), self.assertRaises(ADPError):
                f.service.inspect_ref(writable=True)
        f = Native()
        def third(path):
            if sum(p == f.prefix for _, p in f.calls) == 2:
                f.repo["owner"]["id"] = 92
        f.before = third
        with self.assertRaises(ADPError):
            f.service.inspect_ref(writable=True)

    def test_existing_and_absent_feature_use_real_ref_and_supported_branch(self):
        f = Native()
        self.assertEqual(f.service.inspect_ref(writable=True), HEAD)
        evidence = deepcopy(f.service.personal_policy)
        self.assertEqual(evidence["protection_absence"], "NOT_INDEPENDENTLY_OBSERVED")
        self.assertEqual(evidence["rules"]["status"], "PLAN_UNAVAILABLE")
        f.current = None
        f.entries[f.prefix + "/branches/work%2Ftask/protection"] = Response(404, None)
        f.calls.clear()
        self.assertIsNone(f.service.inspect_ref(writable=True))
        self.assertNotIn(("GET", f.prefix + "/branches/work%2Ftask/protection"), f.calls)
        self.assertEqual(f.service.personal_policy, evidence)
        f.service.personal = False  # Default signed service never uses fallback.
        with self.assertRaises(OSError):
            f.service.inspect_ref(writable=True)

    def test_protected_unknown_inconsistent_feature_and_unrelated_graphql_refuse(self):
        for protected in (True, None, 0):
            f = Native()
            f.entries[f.prefix + "/branches/work%2Ftask"].body["protected"] = protected
            with self.subTest(protected=protected), self.assertRaises(ADPError):
                f.service.inspect_ref(writable=True)
        for protected in (True, None, 0):
            for current in (HEAD, None):
                f = Native(); f.current = current
                f.entries[f.prefix + "/branches/trunk"].body["protected"] = protected
                with self.subTest(default_protected=protected, current=current), self.assertRaises(ADPError):
                    f.service.inspect_ref(writable=True)
        f = Native(); f.current = BASE
        with self.assertRaises(ADPError):
            f.service.inspect_ref(writable=True)
        for permission, errors in (("WRITE", None), ("ADMIN", [{"message": MESSAGE}])):
            f = Native(); f.permission, f.graph_error = permission, errors
            with self.assertRaises(ADPError):
                f.service.inspect_ref(writable=True)

    def test_classic_permission_failure_or_changed_entitlement_never_falls_back(self):
        for response in (Response(403, None), denied(classic=True, message="Resource not accessible"),
                denied(), Response(200, {}), Response(404, None)):
            for current, name in ((HEAD, "work%2Ftask"), (None, "trunk")):
                f = Native(); f.current = current
                f.entries[f.prefix + "/branches/" + name + "/protection"] = response
                with self.subTest(response=response, current=current), self.assertRaises(ADPError):
                    f.service.inspect_ref(writable=True)

    def test_both_entitlement_transitions_invalidate_approved_policy(self):
        f = Native(); f.service.inspect_ref(writable=True)
        f.service.personal_policy_binding = (deepcopy(f.service.personal_policy),)
        f.entries[f.prefix + "/rules/branches/work%2Ftask"] = Response(200, [])
        with self.assertRaises(ADPError):
            f.service.inspect_ref(writable=True)
        f = Native(); f.service.personal_policy_binding = (None,)
        with self.assertRaises(ADPError):
            f.service.inspect_ref(writable=True)

    def test_positive_rules_remain_enforced_on_feature_and_default_branch(self):
        f = Native()
        rule = {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "tests", "integration_id": 7}],
            "strict_required_status_checks_policy": True}}
        f.entries[f.prefix + "/rules/branches/work%2Ftask"] = Response(200, [rule])
        with self.assertRaises(ADPError):
            f.service.inspect_ref(writable=True)
        f.entries[f.prefix + "/rules/branches/trunk?per_page=100&page=1"] = Response(200, [rule])
        policy = observe_policy(f, f.target, "refs/heads/trunk")
        self.assertEqual(policy["checks"], ["tests"])
        self.assertEqual(policy["origins"], {"tests": 7})
        self.assertNotIn("availability", policy)
        f.entries[f.prefix + "/rules/branches/work%2Ftask"] = Response(200, [])
        self.assertEqual(f.service.inspect_ref(writable=True), HEAD)

    def test_default_policy_requires_exact_base_owner_and_classic_plan_evidence(self):
        f = Native()
        def observe():
            return observe_policy(f, f.target, "refs/heads/trunk", personal=(f.repository, f.owner), expected_sha=BASE,
                service=f.service, expected_head=HEAD)
        policy = observe()
        with self.assertRaises(ADPError):
            observe_policy(f, f.target, "refs/heads/trunk", personal=(f.repository, f.owner))
        self.assertEqual(policy["availability"]["rules"]["status"], "PLAN_UNAVAILABLE")
        self.assertNotIn("PASS", str(policy))
        for permission, errors in (("READ", None), (None, None), ("ADMIN", [{"message": "Permission denied"}])):
            f.permission, f.graph_error = permission, errors
            with self.subTest(permission=permission, errors=errors), self.assertRaises(ADPError):
                observe()
        f.permission, f.graph_error = "ADMIN", None
        f.current = BASE
        with self.assertRaises(ADPError):
            observe()
        f.current = HEAD
        f.entries[f.prefix + "/branches/trunk"].body["commit"]["sha"] = HEAD
        with self.assertRaises(ADPError):
            observe()
        f.entries[f.prefix + "/branches/trunk"].body["commit"]["sha"] = BASE
        f.entries[f.prefix + "/branches/trunk/protection"] = Response(403, None)
        with self.assertRaises(ADPError):
            observe()
        f.entries[f.prefix + "/branches/trunk/protection"] = denied(classic=True)
        f.entries[f.prefix + "/branches/trunk"].body["protected"] = True
        with self.assertRaises(ADPError):
            observe()

    def test_missing_feature_plan_context_or_foreign_default_identity_refuses(self):
        f = Native(); f.service.personal_context = None
        with self.assertRaises(ADPError):
            f.service.inspect_ref(writable=True)
        f = Native(); f.repository["node_id"] = "foreign"
        with self.assertRaises(ADPError):
            observe_policy(f, f.target, "refs/heads/trunk", personal=(f.repository, f.owner), expected_sha=BASE)

    def test_separate_publication_and_product_assent_precedes_durable_intent(self):
        pub = PersonalPublication.__new__(PersonalPublication)
        pub.record = lambda: None
        pub.proposed = lambda _: ({"plan_disabled_rules_assent": PLAN_ASSENT}, "exact", "binding")
        pub.save = Mock()
        with TemporaryDirectory() as directory:
            pub.c = SimpleNamespace(memory=SimpleNamespace(control=Path(directory)))
            pub.service = Native().service
            with self.assertRaisesRegex(ADPError, "PLAN_UNAVAILABLE"):
                pub.publish(reviewed="exact", authorized=True, assume_quiescence=True, confirm_project_rules=True)
        pub.save.assert_not_called()
        with TemporaryDirectory() as directory:
            for operation in ("PR", "MERGE"):
                f = PersonalProduct.__new__(PersonalProduct)
                f.c = SimpleNamespace(memory=SimpleNamespace(control=Path(directory)))
                f.service = Native().service
                f.record = lambda: None
                f.proposed = lambda *a, **kw: {"approval": "exact", "result": {"plan_disabled_rules_assent": PLAN_ASSENT}}
                f.initialize = Mock()
                with self.subTest(operation=operation), self.assertRaisesRegex(ADPError, "PLAN_UNAVAILABLE"):
                    f.intent(operation, reviewed="exact", authorized=True, authorize_memory=True, assume_quiescence=True,
                        confirm_rules=True, delegate=True, accept_envelope=True)
                f.initialize.assert_not_called()

    def test_both_real_cas_boundaries_reject_plan_or_permission_drift_without_cas(self):
        # Actual accepted submit sequencing; isolated authority/journal boundary
        # fixtures are not proof of genuine M1/Codex/GitHub execution.
        for boundary in (1, 2):
            f = Native(); f.service.inspect_ref(writable=True)
            f.service.personal_policy_binding = (deepcopy(f.service.personal_policy),)
            port = GitHubGitExecutionPort.__new__(GitHubGitExecutionPort)
            ticket, action = object(), {"operation": "PUSH", "expected_target": HEAD, "revision": "c" * 40}
            port.service = f.service
            port._dispatches = {ticket: ("intent", {})}
            port._claim = lambda *a: {}
            port._authorize = lambda *a: "intent"
            port.bound_git_directory, port.root = None, Path("/unused-disposable-fixture")
            port._git = None
            f.service.upload, f.service.cas = Mock(), Mock()
            calls = []
            def validate():
                calls.append(1)
                if len(calls) == boundary:
                    f.repo["permissions"]["admin"] = False
            with TemporaryDirectory() as directory:
                claim = Path(directory) / "claim.json"; claim.write_text("{}")
                port._claim_path = lambda _: claim
                with patch("adp.network_git.closure", return_value=()), self.subTest(boundary=boundary), self.assertRaises(ADPError):
                    port.submit(action, None, None, None, dispatch=ticket, validate=validate)
            self.assertEqual(len(calls), boundary)
            self.assertEqual(f.service.upload.call_count, boundary - 1)
            f.service.cas.assert_not_called()
            self.assertNotIn(ticket, port._dispatches)

    def test_unchanged_finite_network_budget_and_personal_query_route_bounds(self):
        import time
        from adp.personal_network_child import validate_personal
        from adp.personal_product_child import validate_product
        self.assertNotIn("branchProtection", PERSONAL_REF_QUERY)
        for validator in (validate_personal, validate_product):
            validator("POST", "/graphql", {"query": PERSONAL_REF_QUERY, "variables": {"id": "R_personal", "ref": "refs/heads/work/task"}}, 5)
            validator("GET", "/repos/owned/project/branches/work%2Ftask/protection", None, 5)
            with self.assertRaises((ValueError, ADPError)):
                validator("GET", "/repos/owned/project/branches/work%2ftask/protection", None, 5)
            with self.assertRaises(ValueError):
                validator("GET", "/repos/owned/project/branches/work%2Ftask/protection", None, 6)
        f = Native()
        for budget in (_Budget(time.monotonic() - 1), _Budget(time.monotonic() + 45, 128)):
            token = f.service._budget.set(budget)
            try:
                before = len(f.calls)
                with self.assertRaises(ADPError):
                    f.service.inspect_ref(writable=True)
                self.assertEqual(len(f.calls), before)
            finally:
                f.service._budget.reset(token)

    def test_cli_assent_is_separate_and_off_by_default_in_both_families(self):
        from adp.cli import parser
        for family in ("personal", "codex"):
            for action in ("publish", "pr-create", "merge"):
                args = [family, action, "--repo", "/owned/project", "--remote", "origin", "--directory", "/owned/private", "--reviewed", "exact"]
                if family == "codex":
                    args += ["--personal"]
                if action == "pr-create":
                    args += ["--title", "Outcome", "--body", "Refs #1"]
                self.assertFalse(parser().parse_args(args).accept_plan_unavailable)
                self.assertTrue(parser().parse_args(args + ["--accept-plan-unavailable"]).accept_plan_unavailable)

    def test_latest_raw_second_rules_response_controls_cannot_be_discarded(self):
        import base64
        from adp.personal_network import PersonalGitHubTransport
        for bad in (HEADERS + (("link", '<https://api.github.com/foreign/project/rules/branches/x?page=2>; rel="next"'),),
                HEADERS + (("content-type", "application/json"),),
                HEADERS + (("x-ratelimit-remaining", "0"),), (("content-type", ""),)):
            f = Native()
            f.entries[f.prefix + "/rules/branches/work%2Ftask"] = Response(200, [])
            transport = PersonalGitHubTransport(f.target)
            actor = {"uid": 1001, "synthetic": True}
            transport._context = actor
            rule_calls = []
            def exchange(payload, seconds, *, child):
                request = json.loads(payload)
                response = f.request(request["method"], request["path"], request["body"], seconds=seconds)
                headers = f.last_response[2]
                if "/rules/branches/" in request["path"]:
                    rule_calls.append(1)
                    headers = HEADERS if len(rule_calls) == 1 else bad
                return json.dumps({"status": response.status, "body_base64": base64.b64encode(response.body).decode(), "headers": headers}).encode()
            service = GitHubCAS(f.target, transport, personal=True)
            service.personal_context = f.repository, f.owner
            with patch.object(transport, "_actor", return_value=actor), patch.object(transport, "_credential", return_value="SYNTHETIC_TOKEN"), \
                    patch("adp.personal_network._supported", return_value=True), patch("adp.personal_network.supervised_output", side_effect=exchange):
                with self.subTest(headers=bad), self.assertRaises((ADPError, OSError)):
                    service.inspect_ref(writable=True)
            self.assertEqual(len(rule_calls), 2)
            self.assertIsNone(transport.last_response)


class PersonalPlanRulesTests(PersonalFixture):
    def free_private(self):
        from adp.git import value
        repo = self.transport.api.responses[self.prefix].body
        repo["private"] = True
        self.transport.api.responses[self.prefix + "/branches/trunk"].body["commit"] = {"sha": value(self.a, "rev-parse", "HEAD")}
        self.transport.api.responses[self.prefix + "/rules/branches/trunk"] = denied()

    def test_real_personal_plan_retains_native_edges_and_unknown_check_requirements(self):
        from dataclasses import replace
        from test_config import snapshot
        self.free_private()
        before = snapshot(self.base)
        plan, original, _ = self.plan()
        self.assertEqual(plan["branch_rules"][0]["rules"], "PLAN_UNAVAILABLE")
        self.assertEqual(plan["check_requirements"], "UNKNOWN")
        self.assertEqual(plan["merge_mode"], "MANUAL")
        self.assertEqual(plan["publication"], "NOT_DELEGATED")
        observation, _ = self.observe()
        for number in (2, 3):
            row = next(i for i in observation.snapshot.issues if i.number == number)
            self.assertTrue(any(r.kind == "BLOCKED_BY" and r.confidence == "NATIVE" and r.target.number == number - 1 for r in row.relations))
        selected, _, _ = self.plan(choices=replace(self.choices, checks=("tests",)))
        self.assertEqual(selected["required_check_names"], ["tests"])
        self.assertEqual(selected["unresolved_check_names"], ["tests"])
        self.assertEqual(selected["checks"], [])
        self.assertEqual(selected["check_requirements"], "PRESENT")
        self.assertEqual(snapshot(self.base), before)

    def test_enrollment_plan_or_owner_drift_cannot_reapprove_or_write_state(self):
        from adp.personal_enrollment import apply_personal
        from adp.personal_storage import approval
        from test_config import snapshot
        self.free_private()
        plan, original, docs = self.plan()
        self.transport.api.responses[self.prefix + "/rules/branches/trunk"] = Response(200, [])
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=approval(plan), authorized=True, transport=self.transport, clock=lambda: self.now)
        self.assertFalse(self.directory.exists())
        self.assertEqual(snapshot(self.base), before)


if __name__ == "__main__":
    unittest.main()
