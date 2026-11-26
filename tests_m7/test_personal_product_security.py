"""Focused independent-review counterexamples; isolated boundaries, synthetic data."""
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.discovery_github import Response
from adp.errors import ADPError
from adp.execution_types import ExternalObservation
from adp.network_git import GitHubTarget
from adp.network_http import Response as NativeResponse, NetworkTransportError
from adp.personal_network import PersonalGitHubTransport
from adp.personal_product import PersonalProduct
from adp.personal_product_http import PersonalProductTransport
from adp.personal_product_policy import constraints
from adp.policy_types import Ref


class PersonalProductSecurityTests(unittest.TestCase):
    def test_required_native_review_booleans_missing_or_numeric_are_unknown(self):
        parameters = {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False, "require_last_push_approval": False, "required_review_thread_resolution": False}
        constraints({"protected": False}, [{"type": "pull_request", "parameters": parameters}])
        for name in parameters.keys() - {"required_approving_review_count"}:
            for invalid in (None, 0, 0.0):
                changed = dict(parameters)
                if invalid is None:
                    del changed[name]
                else:
                    changed[name] = invalid
                with self.subTest(name=name, invalid=invalid), self.assertRaises(ADPError):
                    constraints({"protected": False}, [{"type": "pull_request", "parameters": changed}])

    def test_native_permission_identity_rejects_numeric_alias_and_wrong_shape(self):
        f = PersonalProduct.__new__(PersonalProduct)
        f.record = lambda: {"pull": {"number": 10}}
        f.c = SimpleNamespace(revision=lambda: "a" * 40)
        f.target = SimpleNamespace(api="/repos/owned/project")
        f.personal = SimpleNamespace(plan={"owner": {"account_id": 91}})
        f.forge = SimpleNamespace(reviews=lambda *args: [{"id": 1, "state": "APPROVED", "commit_id": "a" * 40,
            "user": {"id": 102, "login": "reviewer"}}])
        for user in ({"id": 102.0}, None, [], {"id": -1}):
            f.read = SimpleNamespace(get=lambda path: Response(200, {"permission": "write", "user": user}))
            with self.subTest(user=user), self.assertRaises(ADPError):
                f.native_reviews({"user": {"id": 91}}, {"policy": {"native_reviews": 1}})

    def test_completed_execution_returns_retained_evidence_not_current_pass(self):
        with TemporaryDirectory(prefix="adp-synthetic-retained-") as directory:
            f = PersonalProduct.__new__(PersonalProduct)
            f.c = SimpleNamespace(memory=SimpleNamespace(control=Path(directory)), revision=lambda: "b" * 40)
            f.service = SimpleNamespace(bounded=lambda **kw: nullcontext())
            f.clock = lambda: 2000
            view = {"operation": "CI", "issued_at": 1000, "expires_at": 1300, "nonce": "a" * 32, "revision": "a" * 40}
            token = f.token(view, "c" * 64)
            entry = {"view": view, "approval": token, "binding": "c" * 64, "phase": "COMPLETE", "checks": [],
                "result": {"status": "PASS", "qualified": True}, "reservation": None}
            f.record = lambda: {"pull": {"number": 10}, "execution": [entry]}
            result = f.execute("CI", reviewed=token, authorized=True)
            self.assertEqual(result["status"], "RETAINED_OBSERVATION")
            self.assertEqual(result["observation"]["status"], "PASS")
            self.assertEqual(result["freshness"], "NOT_REOBSERVED")

    def test_unobserved_own_merge_is_never_credited_as_manual_proof(self):
        f = PersonalProduct.__new__(PersonalProduct)
        source = "a" * 40
        v = {"operation": "PR", "facts": {"base_ref": "refs/heads/trunk", "base_sha": "b" * 40}, "method": None}
        merge = {"view": {**v, "operation": "MERGE", "method": "merge", "revision": source}, "action": "d" * 64, "observation": None}
        row = {"pull": {"id": "2010", "node_id": "PR_actual", "number": 10, "repository_id": "17", "url": "https://github.com/owned/project/pull/10"},
            "intents": [{"view": v, "action": "c" * 64, "observation": {}}, merge]}
        f.record = lambda: row
        f.c = SimpleNamespace(record=lambda: {}, check_administration=lambda row: None, revision=lambda: source)
        f.target = SimpleNamespace(ref="refs/heads/work/task")
        f.service = SimpleNamespace(bounded=lambda **kw: nullcontext(), _check_stop=lambda: None, refs=lambda: (Ref(f.target.ref, source),))
        f.pull = lambda **kwargs: {"merged": True, "merged_by": {"id": 91}}
        f.port = SimpleNamespace(_value=lambda *args: "e" * 40)
        f.forge = SimpleNamespace(observe=lambda *args, **kwargs: ExternalObservation("PRESENT", "https://github.com/owned/project/pull/10", "f" * 40))
        f.journal = SimpleNamespace(inspect=lambda: {"state": {"execution": {"actions": {merge["action"]: {"status": "SUBMITTED"}}}}})
        result = f.status()
        self.assertEqual(result["status"], "MERGED_WITH_UNRESOLVED_DELEGATED_INTENT")
        self.assertEqual(result["attribution"], "UNKNOWN")

    def test_native_control_headers_fail_closed_benign_repetitions_survive(self):
        t = PersonalProductTransport(GitHubTarget("17", "R_owned", 17, "owned", "project", "work/task"))
        native = NativeResponse(200, b'{}')
        t.last_response = (200, b'{}', (("x-benign", ""), ("x-benign", "ok")))
        with patch.object(PersonalGitHubTransport, "request", return_value=native):
            self.assertEqual(t.request("GET", "/repos/owned/project", None, seconds=5), native)
            for headers in ((("link", "one"), ("Link", "two")), (("content-type", ""),), (("x-ratelimit-remaining", "0"),)):
                t.last_response = (200, b'{}', headers)
                with self.subTest(headers=headers), self.assertRaises(NetworkTransportError):
                    t.request("GET", "/repos/owned/project", None, seconds=5)

        # Forge consumers intentionally discard headers; qualify controls before
        # that boundary so an omitted next page cannot appear complete.
        import json
        for route in ("/pulls?state=all&per_page=100&page=1", "/pulls/10/reviews?per_page=100&page=1"):
            path = "/repos/owned/project" + route
            # replace only the page parameter, not per_page=100.
            next_url = "https://api.github.com" + path.removesuffix("page=1") + "page=2"
            for link in ("malformed", ",", ",,", f'<{next_url}>; rel="next",',
                f'<{next_url}>; rel="next"', f'<{next_url}>; rel="next", <{next_url}>; rel="next"',
                f'<{next_url.replace("api.github.com", "foreign.example")}>; rel="next"'):
                t.last_response = (200, b"[]", (("link", link),))
                with patch.object(PersonalGitHubTransport, "request", return_value=NativeResponse(200, b"[]")):
                    with self.subTest(route=route, link=link), self.assertRaises(NetworkTransportError):
                        t.request("GET", path, None, seconds=5)
            full = json.dumps([{"body": str(i)} for i in range(100)]).encode()
            t.last_response = (200, full, (("link", f'<{next_url}>; rel="next"'),))
            with patch.object(PersonalGitHubTransport, "request", return_value=NativeResponse(200, full)):
                self.assertEqual(t.request("GET", path, None, seconds=5).body, full)

        # Actual accepted inventory and review reducers must consume the second
        # page: an alternate PR and a rejected review cannot be hidden there.
        from adp.execution_github import GitHubForgeBackend
        from adp.github_product import GitHubProductForge
        from adp.policy_types import Operation
        calls = []
        def raw(method, path, body, *, seconds):
            calls.append(path)
            if path == "/repos/owned/project":
                value, headers = {"id": 17, "full_name": "owned/project"}, ()
            else:
                page = int(path.rsplit("=", 1)[1])
                if "/reviews?" in path:
                    value = [{"id": i + 1, "state": "APPROVED", "user": {"id": i + 10}} for i in range(100)] if page == 1 else [
                        {"id": 101, "state": "CHANGES_REQUESTED", "user": {"id": 900}}]
                else:
                    value = [{"id": i + 1, "body": str(i), "head": {"ref": "unrelated"}} for i in range(100)] if page == 1 else [
                        {"id": 101, "body": "Alternate", "head": {"ref": "work/task"}}]
                headers = (("link", '<https://api.github.com' + path.removesuffix("page=1") + 'page=2>; rel="next"'),) if page == 1 else ()
            payload = json.dumps(value).encode()
            t.last_response = (200, payload, headers)
            return NativeResponse(200, payload)
        class Reads:
            def request(_, method, path, body=None):
                reply = t.request(method, path, body, seconds=5)
                return Response(reply.status, json.loads(reply.body))
        with patch.object(PersonalGitHubTransport, "request", side_effect=raw):
            backend = GitHubForgeBackend("owned/project", "17", Reads(), None)
            rows = backend.inventory(Operation.PR, {"body": "Approved"})
            self.assertEqual(len(rows), 101)
            self.assertEqual(rows[-1]["head"]["ref"], "work/task")
            forge = GitHubProductForge.__new__(GitHubProductForge)
            forge.repository, forge.transport = "owned/project", Reads()
            forge.service = SimpleNamespace(bounded=lambda **kw: nullcontext())
            rows = forge.reviews({"number": 10}, "a" * 40)
            self.assertTrue(any(r["state"] == "CHANGES_REQUESTED" for r in rows))
        self.assertTrue(any(path.endswith("page=2") for path in calls))
