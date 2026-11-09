"""Offline HTTP boundary proofs; no real GitHub request is performed."""
from __future__ import annotations

import base64
import errno
import json
import os
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from adp.errors import ADPError
from adp.execution_ports import UnconfirmedValidation
from adp.network_http import GitHubHTTPTransport, NetworkTransportError, Response, UPDATE_REFS_MUTATION
from adp.network_http_child import MAX_RESPONSE_BYTES, exchange, validate_request


TOKEN = "synthetic-only-http-credential"
QUERY = {"query": "query ADPRef($owner:String!) { repository(owner:$owner,name:\"unused\") { id } }", "variables": {"owner": "fixture"}}


def response_child(status=200, body=b'{"ok":true}'):
    reply = json.dumps({"status": status, "body_base64": base64.b64encode(body).decode()})
    return (sys.executable, "-I", "-B", "-c", "import sys;sys.stdin.buffer.read();sys.stdout.write(" + repr(reply) + ")")


class FakeResponse:
    def __init__(self, status=200, data=b'{"ok":true}'):
        self.status, self.data = status, data

    def read(self, maximum):
        return self.data[:maximum]


class FakeConnection:
    def __init__(self, response):
        self.response, self.requests, self.closed = response, [], False

    def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class NetworkHTTPTests(unittest.TestCase):
    def test_routes_force_delete_and_credential_urls_refuse_before_token_access(self):
        getter = []
        transport = GitHubHTTPTransport(lambda: getter.append(True) or TOKEN)
        cases = [("POST", "https://api.github.com/graphql", QUERY),
                 ("POST", "//evil.invalid/graphql", QUERY),
                 ("POST", "/graphql?token=synthetic", QUERY),
                 ("POST", "/graphql\r\nHost:evil.invalid", QUERY),
                 ("POST", "/repos/fixture/repo/git/refs", {}),
                 ("PATCH", "/repos/fixture/repo/git/refs/heads/target", {}),
                 ("POST", "/repos/fixture/../git/blobs", {}),
                 ("GET", "/repos/fixture/repo/rules/branches/%252Fescape", None),
                 ("GET", "/repos/fixture/repo/rules/branches/..%2Fescape", None),
                 ("GET", "/repos/fixture/repo/rules/branches/.git", None),
                 ("POST", "/graphql", {"query": "mutation { deleteRef(input:{refId:\"x\"}) { clientMutationId } }", "variables": {}})]
        mutation = {"query": UPDATE_REFS_MUTATION, "variables": {"input": {"repositoryId": "opaque-id",
            "clientMutationId": "fixture-id", "refUpdates": [{"name": "refs/heads/work/result", "beforeOid": "a" * 40,
            "afterOid": "b" * 40, "force": False}]}}}
        for changed in ({"force": True}, {"afterOid": "0" * 40}, {"name": "refs/tags/public-release"}, {"beforeOid": None}):
            copy = json.loads(json.dumps(mutation));copy["variables"]["input"]["refUpdates"][0].update(changed)
            cases.append(("POST", "/graphql", copy))
        for method, path, body in cases:
            with self.subTest(method=method, path=path), self.assertRaises(NetworkTransportError):
                transport.request(method, path, body, seconds=1)
        self.assertEqual(getter, [])
        for seconds in (0, -1, 6, float("inf"), float("nan"), True):
            with self.subTest(seconds=seconds), self.assertRaises(NetworkTransportError):
                transport.request("POST", "/graphql", QUERY, seconds=seconds)
        self.assertEqual(getter, [])

    def test_exact_cas_and_canonical_encoded_branch_routes_are_accepted(self):
        mutation = {"query": UPDATE_REFS_MUTATION, "variables": {"input": {"repositoryId": "opaque-id",
            "clientMutationId": "fixture-id", "refUpdates": [{"name": "refs/heads/work/result", "beforeOid": "0" * 40,
            "afterOid": "b" * 40, "force": False}]}}}
        self.assertEqual(json.loads(validate_request("POST", "/graphql", mutation, 1)), mutation)
        for path in ("/repos/fixture/repo/git/commits/" + "a" * 40,
                     "/repos/fixture/repo/rules/branches/work%2Fresult"):
            self.assertEqual(validate_request("GET", path, None, 1), b"null")

    def test_child_uses_only_verified_fixed_https_origin_and_private_authorization(self):
        connection = FakeConnection(FakeResponse(403, b'{"message":"denied"}'))
        with patch("adp.network_http_child.http.client.HTTPSConnection", return_value=connection) as constructor:
            reply = exchange({"method": "POST", "path": "/graphql", "body": QUERY, "seconds": 1, "token": TOKEN})
        args, kwargs = constructor.call_args
        self.assertEqual(args, ("api.github.com", 443))
        self.assertTrue(kwargs["context"].check_hostname)
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(len(connection.requests), 1)
        headers = connection.requests[0][2]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertNotIn(TOKEN, json.dumps(reply))
        self.assertEqual(reply["status"], 403)
        self.assertTrue(connection.closed)

    def test_redirect_and_oversize_response_do_not_retry_or_return_data(self):
        for response in (FakeResponse(302, b""), FakeResponse(200, b"x" * (MAX_RESPONSE_BYTES + 1))):
            with self.subTest(status=response.status):
                connection = FakeConnection(response)
                with patch("adp.network_http_child.http.client.HTTPSConnection", return_value=connection):
                    with self.assertRaises(ValueError):
                        exchange({"method": "POST", "path": "/graphql", "body": QUERY, "seconds": 1, "token": TOKEN})
                self.assertEqual(len(connection.requests), 1)
                self.assertTrue(connection.closed)

    def test_real_supervisor_response_and_secrets_never_enter_argv_environment_or_receipt(self):
        launches, receipts = [], []
        real_popen = subprocess.Popen
        from adp.execution_ports import validation_stopped as real_stopped
        def capture_popen(argv, **kwargs):
            launches.append((argv, kwargs.get("env")))
            return real_popen(argv, **kwargs)
        def capture_receipt(path, subject, pid):
            result = real_stopped(path, subject, pid)
            receipts.append(json.loads(path.read_text()))
            return result
        with (patch("adp.network_http._child_argv", return_value=response_child(201, b'{"sha":"intended"}')),
                patch("adp.network_http.subprocess.Popen", side_effect=capture_popen),
                patch("adp.network_http.validation_stopped", side_effect=capture_receipt),
                patch.dict(os.environ, {"GH_TOKEN": "synthetic-parent-forge-token", "HTTPS_PROXY": "http://untrusted.invalid"})):
            observed = GitHubHTTPTransport(lambda: TOKEN).request("POST", "/graphql", QUERY, seconds=2)
        self.assertEqual(observed, Response(201, b'{"sha":"intended"}'))
        self.assertTrue(receipts and all(r["stopped"] for r in receipts))
        public = json.dumps({"launches": launches, "receipts": receipts})
        for marker in (TOKEN, "synthetic-parent-forge-token", "untrusted.invalid"):
            self.assertNotIn(marker, public)

    def test_real_whole_request_deadline_reaps_detached_child(self):
        with tempfile.TemporaryDirectory(prefix="adp-network-http-timeout-") as directory:
            path = Path(directory) / "pid"
            program = ("import os,time; p=os.fork(); "
                "\nif p==0:\n os.setsid();open(" + repr(str(path)) + ", 'w').write(str(os.getpid()));time.sleep(60)"
                "\nelse: time.sleep(60)\n")
            argv = (sys.executable, "-I", "-B", "-c", program)
            start = time.monotonic()
            with patch("adp.network_http._child_argv", return_value=argv), self.assertRaises(NetworkTransportError) as error:
                GitHubHTTPTransport(lambda: TOKEN).request("POST", "/graphql", QUERY, seconds=0.5)
            self.assertIn("deadline", str(error.exception))
            self.assertLess(time.monotonic() - start, 4)
            self.assertTrue(path.is_file(), "Detached fixture must actually have started")
            with self.assertRaises(ProcessLookupError):os.kill(int(path.read_text()), 0)

    def test_unsupported_capability_and_unconfirmed_receipt_never_create_success(self):
        getter = []
        with patch("adp.network_http._supported", return_value=False), self.assertRaises(NetworkTransportError):
            GitHubHTTPTransport(lambda: getter.append(True) or TOKEN).request("POST", "/graphql", QUERY, seconds=1)
        self.assertEqual(getter, [])
        references = []
        def missing(path, subject, pid):
            references.append(path.parent)
            raise UnconfirmedValidation("validation:" + subject, str(path.parent))
        with (patch("adp.network_http._child_argv", return_value=response_child()),
                patch("adp.network_http.validation_stopped", side_effect=missing), self.assertRaises(UnconfirmedValidation)):
            GitHubHTTPTransport(lambda: TOKEN).request("POST", "/graphql", QUERY, seconds=2)
        self.assertTrue(references[0].is_dir(), "Missing stop evidence must be retained privately")
        import shutil
        shutil.rmtree(references[0])
        class Unstoppable:
            pid = 999999999
            def poll(self):return None
            def send_signal(self, sig):pass
            def communicate(self, *, timeout):raise subprocess.TimeoutExpired(('fixture',), timeout)
            def kill(self):pass
            def wait(self, *, timeout):raise subprocess.TimeoutExpired(('fixture',), timeout)
        from adp.network_http import _stop
        with self.assertRaises(UnconfirmedValidation):
            _stop(Unstoppable(), Path('/tmp/owned-fixture/stop.json'), 'fixture')

    def test_invalid_child_payload_and_sensitive_failures_remain_sanitized(self):
        sensitive = "synthetic-private-response-and-token"
        programs = ["import sys;sys.stdin.read();print('not-json')",
                    "import sys;sys.stdin.read();sys.stderr.write(" + repr(sensitive) + ");raise SystemExit(78)"]
        for program in programs:
            with self.subTest(program=program), patch("adp.network_http._child_argv",
                    return_value=(sys.executable, "-I", "-B", "-c", program)), self.assertRaises(NetworkTransportError) as error:
                GitHubHTTPTransport(lambda: sensitive).request("POST", "/graphql", QUERY, seconds=2)
            self.assertNotIn(sensitive, str(error.exception))


if __name__ == "__main__":
    unittest.main()
