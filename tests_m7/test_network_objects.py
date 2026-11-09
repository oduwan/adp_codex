import tempfile
import unittest
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from adp.errors import ADPError
from adp.network_git import GitHubCAS, GitHubTarget
from adp.network_objects import closure, commit_payload, object_oid, oid, tree_payload
from network_fixtures import ObjectServer, git_bytes, gv


class ObjectQualification(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="adp-network-objects-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.source = self.base / "source"; self.source.mkdir()
        self.remote = self.base / "remote"; self.remote.mkdir()
        gv(self.source, "init", "--initial-branch=topic")
        gv(self.remote, "init", "--bare", "--initial-branch=topic")
        (self.source / "nested").mkdir()
        (self.source / "nested/binary").write_bytes(b"\0\xffarbitrary\r\n")
        (self.source / "executable").write_text("#!/bin/false\n")
        (self.source / "executable").chmod(0o755)
        gv(self.source, "add", "."); gv(self.source, "commit", "-m", "Original unicode: λ")
        self.first = gv(self.source, "rev-parse", "HEAD")
        (self.source / "next").write_text("next\n")
        gv(self.source, "add", "."); gv(self.source, "commit", "-m", "Parented exact commit")
        self.head = gv(self.source, "rev-parse", "HEAD")
        self.target = GitHubTarget("opaque-memory", "R_opaque", 717, "owned-disposable", "fixture", "topic")
        self.server = ObjectServer(self.remote, self.target)
        self.client = GitHubCAS(self.target, self.server)

    def test_actual_objects_preserve_oids_without_any_refs(self):
        before = self.server.refs()
        objects = closure(self.source, self.head, self.client.known_commit)
        self.assertGreaterEqual(len(objects), 7)
        self.client.upload(objects)
        for item in objects:
            self.assertEqual(git_bytes(self.source, "cat-file", item.kind, item.oid),
                             git_bytes(self.remote, "cat-file", item.kind, item.oid))
        self.assertEqual(self.server.refs(), before)
        self.assertEqual(gv(self.source, "rev-parse", "HEAD"), self.head)

    def test_unrepresentable_commit_headers_dates_and_encoding_refuse(self):
        raw = git_bytes(self.source, "cat-file", "commit", self.head)
        cases = [raw.replace(b" +0000", b" +0200"), raw.replace(b"\n\n", b"\nencoding ISO-8859-1\n\n", 1),
                 raw.replace(b"\n\n", b"\ngpgsig fake\n\n", 1), raw.replace(b"\n\n", b"\nextra header\n\n", 1),
                 raw[:-1], raw.replace(b"Parented", b"\xffarented")]
        for case in cases:
            with self.subTest(case=case[:16]), self.assertRaises(ADPError): commit_payload(case)
        self.assertFalse(self.server.mutations)

    def test_unsafe_tree_forms_refuse(self):
        for invalid in ("0" * 40, "a" * 39, "A" * 40, None, True):
            with self.subTest(invalid=invalid), self.assertRaises(ADPError): oid(invalid)
        sha = bytes.fromhex(self.first)
        for raw in (b"160000 submodule\0" + sha, b"100644 ../escape\0" + sha, b"100644 .git\0" + sha,
                    b"100644 duplicate\0" + sha + b"100644 duplicate\0" + sha,
                    b"100644 z\0" + sha + b"100644 a\0" + sha, b"100644 truncated\0"):
            with self.subTest(raw=raw[:20]), self.assertRaises(ADPError): tree_payload(raw)

    def test_closure_preflight_bounds_before_any_mutation(self):
        for name, maximum in (("MAX_OBJECTS", 1), ("MAX_OBJECT_BYTES", 1), ("MAX_TOTAL_BYTES", 1),
                              ("MAX_COMMITS", 1), ("MAX_DEPTH", 0)):
            with self.subTest(name=name), patch("adp.network_objects." + name, maximum), self.assertRaises(ADPError):
                closure(self.source, self.head, self.client.known_commit)
            self.assertFalse(self.server.mutations)

    def test_entire_closure_is_checked_before_upload(self):
        raw = git_bytes(self.source, "cat-file", "commit", self.first).replace(b" +0000", b" +0300")
        wrong = git_bytes(self.source, "hash-object", "-w", "-t", "commit", "--stdin", raw=raw).decode().strip()
        new = git_bytes(self.source, "cat-file", "commit", self.head).replace(self.first.encode(), wrong.encode())
        head = git_bytes(self.source, "hash-object", "-w", "-t", "commit", "--stdin", raw=new).decode().strip()
        with self.assertRaises(ADPError): closure(self.source, head, self.client.known_commit)
        self.assertFalse(self.server.mutations)

    def test_upload_mismatches_and_failures_preserve_all_refs(self):
        objects = closure(self.source, self.head, self.client.known_commit)
        self.server.mismatch = True
        with self.assertRaises(ADPError): self.client.upload(objects)
        self.assertEqual(self.server.refs(), {})
        self.assertEqual(len(self.server.mutations), 1)

    def test_http_error_and_malformed_replies_remain_unknown(self):
        from adp.network_http import Response
        for code in (401, 403, 409, 422, 429):
            with self.subTest(code=code):
                self.server.failure = (lambda *args: True, Response(code, b"private response"))
                with self.assertRaises(OSError): self.client.known_commit(self.head)
        for body in (b"{", b'{"data":1,"data":2}', b"x" * (1048576 + 1)):
            self.server.failure = (lambda *args: True, Response(200, body))
            with self.assertRaises((ADPError, OSError)): self.client.known_commit(self.head)
        self.assertFalse(self.server.mutations)

    def test_ref_inventory_requires_complete_identity_and_pagination(self):
        self.client.upload(closure(self.source, self.head, self.client.known_commit))
        gv(self.remote, "update-ref", "refs/heads/one", self.first)
        gv(self.remote, "update-ref", "refs/heads/two", self.head)
        self.server.page_size = 1
        self.assertEqual(len(self.client.refs()), 2)
        self.server.wrong_identity = True
        with self.assertRaises(ADPError): self.client.refs()
        self.server.wrong_identity = False
        original = self.server.request
        def boolean_database(*args, **kwargs):
            reply = original(*args, **kwargs)
            value = json.loads(reply.body)
            value["data"]["node"]["databaseId"] = True
            return self.server.response(value)
        aliased = GitHubCAS(replace(self.target, database_id=1), self.server)
        with patch.object(self.server, "request", side_effect=boolean_database), self.assertRaises(ADPError):
            aliased.refs()

    def test_interrupted_transport_is_write_ahead_fenced_across_restart(self):
        control = self.base / "private-control"; control.mkdir(mode=0o700)
        self.client.bind_control(control)
        with patch.object(self.server, "request", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.client.inspect_ref()
        restarted = GitHubCAS(self.target, self.server); restarted.bind_control(control)
        before = len(self.server.calls)
        with self.assertRaises(ADPError): restarted.inspect_ref()
        self.assertEqual(len(self.server.calls), before)
        self.assertTrue(restarted.unconfirmed_contexts())

    def test_failed_stop_boundary_persistence_never_launches_transport(self):
        control = self.base / "private-control"; control.mkdir(mode=0o700)
        self.client.bind_control(control)
        with patch("adp.network_git.os.open", side_effect=OSError("synthetic storage failure")), self.assertRaises(ADPError):
            self.client.inspect_ref()
        self.assertFalse(self.server.calls)
        self.assertTrue(self.client.unconfirmed_contexts())
