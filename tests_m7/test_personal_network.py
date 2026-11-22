"""Synthetic personal credential/HTTP controls; no real gh login or API call."""
import base64
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.discovery_github import GitHubDiscoveryAdapter
from adp.execution_ports import UnconfirmedValidation
from adp.network_git import GitHubCAS, GitHubTarget, UPDATE_REFS_MUTATION
from adp.network_http import NetworkTransportError
from adp.personal_network import PersonalDiscoveryRead, PersonalGitHubTransport
from adp import personal_network_child as child


class PersonalNetworkTests(unittest.TestCase):
    def setUp(self):
        self.target = GitHubTarget("17", "R_personal", 17, "personal", "project", "work/issue-1")
        self.actor = {"uid": 1001, "gh": "/trusted/gh", "config": "/owned/gh", "files": {}}
        self.token = "synthetic-private-gh-credential"
        self.headers = []
        self.body = {"id": 91}
        self.status = 200
        self.calls = []
        self.addCleanup(patch.stopall)
        patch("adp.personal_network._supported", return_value=True).start()
        patch.object(PersonalGitHubTransport, "_actor", side_effect=lambda: self.actor).start()
        self.exchange = patch("adp.personal_network.supervised_output", side_effect=self.reply).start()
        self.http = PersonalGitHubTransport(self.target)
        self.http.bind_repository(self.target.node_id, self.target.database_id)

    def reply(self, raw, seconds, *, child, environment=None):
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, 5)
        self.assertEqual(child, "personal_network_child.py")
        value = json.loads(raw)
        self.calls.append(value)
        if value["kind"] == "credential":
            self.assertLessEqual(set(environment or {}), {"LANG", "LC_ALL", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR"})
            return json.dumps({"context": self.actor, "token": self.token, "version": "2.105.0"}).encode()
        self.assertEqual(value["token"], self.token)
        return json.dumps({"status": self.status, "body_base64": base64.b64encode(json.dumps(self.body).encode()).decode(),
                           "headers": self.headers}).encode()

    def test_private_gh_credential_is_pinned_without_an_app_issuance_record(self):
        with patch.dict("adp.personal_network.os.environ", {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/owned/bus", "XDG_RUNTIME_DIR": "/run/user/1001"}):
            result = self.http.request("GET", "/user", None, seconds=5)
        self.assertEqual(self.exchange.call_args_list[0].kwargs["environment"]["DBUS_SESSION_BUS_ADDRESS"], "unix:path=/owned/bus")
        self.assertEqual(result.status, 200)
        self.assertEqual([c["kind"] for c in self.calls], ["credential", "http"])
        self.assertEqual(set(self.calls[0]), {"kind", "context"})
        first = self.http.credential_binding
        self.http.request("GET", "/user", None, seconds=5)
        self.assertEqual(sum(c["kind"] == "credential" for c in self.calls), 1)
        self.assertEqual(self.http.credential_binding, first)
        self.assertNotIn(self.token, str(result))

    def test_foreign_routes_force_and_unapproved_writes_refuse_before_credential(self):
        cas = {"query": UPDATE_REFS_MUTATION, "variables": {"input": {"repositoryId": self.target.node_id,
            "refUpdates": [{"name": self.target.ref, "beforeOid": "0" * 40, "afterOid": "1" * 40, "force": True}],
            "clientMutationId": "proof"}}}
        for method, path, body in [("GET", "/repos/other/project", None), ("POST", self.target.api + "/issues", {}),
            ("DELETE", self.target.api + "/git/refs/x", None), ("POST", "/graphql", cas),
            ("POST", self.target.api + "/git/blobs", {"encoding": "base64", "content": "YQ=="})]:
            with self.subTest(path=path), self.assertRaises(NetworkTransportError):
                self.http.request(method, path, body, seconds=5)
        self.exchange.assert_not_called()

    def test_exact_mutation_needs_the_live_personal_warrant(self):
        permit = Mock(return_value=True)
        self.http.authorize_write = permit
        self.body = {"sha": "1" * 40}
        self.http.request("POST", self.target.api + "/git/blobs", {"encoding": "base64", "content": "YQ=="}, seconds=5)
        permit.assert_called_once_with()
        permit.return_value = False
        before = len(self.calls)
        with self.assertRaises(NetworkTransportError):
            self.http.request("POST", self.target.api + "/git/blobs", {}, seconds=5)
        self.assertEqual(len(self.calls), before)

    def test_native_headers_keep_empty_repeated_benign_and_conflicting_control_semantics(self):
        service = GitHubCAS(self.target, self.http)
        read = PersonalDiscoveryRead(service)
        def observe():
            adapter = GitHubDiscoveryAdapter("personal/project", read, max_requests=1)
            adapter._halt, adapter._requests = False, 0
            return adapter._get("/user"), adapter
        self.headers = [["x-benign", ""], ["x-benign", "a"], ["x-benign", "b"]]
        self.assertEqual(observe()[0].status, 200)
        self.headers = [["x-ratelimit-remaining", "1"], ["X-RateLimit-Remaining", "2"]]
        self.assertEqual(observe()[0].status, 0)
        self.headers = [["x-ratelimit-remaining", "0"]]
        response, adapter = observe()
        self.assertEqual(response.status, 200)  # The final available response remains valid.
        before = len(self.calls)
        self.assertTrue(adapter._halt)
        self.assertEqual(adapter._get("/user").status, -1)
        self.assertEqual(len(self.calls), before)  # Exhaustion blocks every later request.

    def test_unconfirmed_credential_stop_stays_durably_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            service = GitHubCAS(self.target, self.http)
            service.bind_control(Path(directory))
            self.exchange.side_effect = UnconfirmedValidation("validation:synthetic", directory)
            with self.assertRaises(Exception):
                service.request("GET", "/user")
            self.assertTrue(service.unconfirmed_contexts())
            before = self.exchange.call_count
            with self.assertRaises(Exception):
                service.request("GET", "/user")
            self.assertEqual(self.exchange.call_count, before)

    def test_changed_gh_context_and_malformed_replies_never_reuse_authority(self):
        self.http.request("GET", "/user", None, seconds=5)
        self.actor = {**self.actor, "uid": 1002}
        with self.assertRaises(NetworkTransportError):
            self.http.request("GET", "/user", None, seconds=5)
        self.actor = {**self.actor, "uid": 1001}
        for output in (b"not-json", b'{"status":302,"body_base64":"","headers":[]}',
                       b'{"status":200,"body_base64":"!!!!","headers":[]}'):
            self.exchange.side_effect = None
            self.exchange.return_value = output
            with self.subTest(output=output), self.assertRaises(NetworkTransportError):
                self.http.request("GET", "/user", None, seconds=5)

    def test_credential_child_uses_only_fixed_normal_user_stored_login(self):
        actor = self.actor
        process = SimpleNamespace(stdout=io.BytesIO((self.token + "\n").encode()), wait=lambda: 0)
        version = SimpleNamespace(stdout=io.BytesIO(b"gh version 2.105.0 (SYNTHETIC)\n"), wait=lambda: 0)
        with patch.object(child, "context", return_value=actor), patch.object(child.pwd, "getpwuid", return_value=SimpleNamespace(pw_dir="/owned")), \
             patch.object(child.subprocess, "Popen", side_effect=(process, version)) as launch, \
             patch.dict(child.os.environ, {"GH_TOKEN": "private-override", "GITHUB_TOKEN": "private-other", "GH_HOST": "evil.invalid", "GH_REPO": "other/repo"}):
            result = child.credential({"kind": "credential", "context": actor})
        self.assertEqual(result["token"], self.token)
        self.assertEqual(launch.call_args_list[0].args[0], ("/trusted/gh", "auth", "token", "--hostname", "github.com", "--no-refresh"))
        self.assertEqual(launch.call_args_list[1].args[0], ("/trusted/gh", "--version"))
        self.assertFalse(any(k in launch.call_args.kwargs["env"] for k in ("GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "GH_REPO")))
        self.assertNotIn(self.token, str(launch.call_args))
        with patch.object(child.os, "getuid", return_value=0), self.assertRaises(ValueError):
            child.context("/unavailable/gh", "/unavailable/config")

    def test_http_child_has_fixed_tls_origin_no_redirect_and_bounded_headers(self):
        response = SimpleNamespace(status=200, getheaders=lambda: [("x-benign", "")], read=lambda maximum: b"{}")
        connection = Mock()
        connection.getresponse.return_value = response
        request = {"kind": "http", "method": "GET", "path": "/user", "body": None, "seconds": 1, "token": self.token}
        with patch.object(child.http.client, "HTTPSConnection", return_value=connection) as connect:
            self.assertEqual(child.exchange_http(request)["headers"], [("x-benign", "")])
            self.assertEqual(connect.call_args.args, ("api.github.com", 443))
            self.assertIsNotNone(connect.call_args.kwargs["context"])
            self.assertEqual(connection.request.call_args.kwargs["headers"]["Authorization"], "Bearer " + self.token)
            response.status = 302
            with self.assertRaises(ValueError):
                child.exchange_http(request)
            response.status = 200
            response.getheaders = lambda: [("x", "a")] * 129
            with self.assertRaises(ValueError):
                child.exchange_http(request)
