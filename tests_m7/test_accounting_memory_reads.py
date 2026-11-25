"""Fresh canonical reads on owned disposable repositories, with no workers."""
from pathlib import Path
import hashlib
import time
import unittest
from unittest.mock import patch

from adp.errors import ADPError
from adp.git import git, value
from adp.memory import Memory
from adp.personal_episode import EpisodeState
from adp.schema import MAX_JSON
from adp.storage import atomic
from personal_fixtures import GitFixture


class AccountingMemoryReadTests(GitFixture):
    def setUp(self):
        super().setUp()
        self.native = Memory(self.config(), pinned_local_remote=self.remote)
        self.native.initialize(authorized=True)
        self.native.claim("synthetic-original-owner")
        self.revision = value(self.a, "rev-parse", "HEAD")
        for identifier in ("original", "episode"):
            self.native.add_task(identifier, self.revision)
        self.fast = Memory(self.config(), pinned_local_remote=self.remote)
        self.fast._accounting_reads = True

    def preserved(self):
        return {str(p.relative_to(self.base)): (p.lstat().st_mode, p.lstat().st_mtime_ns,
                    hashlib.sha256(p.read_bytes()).hexdigest()) for p in self.base.rglob("*") if p.is_file()}

    def test_actual_inspection_parity_fewer_commands_and_readonly_preservation(self):
        before = self.preserved()
        calls = []
        def counted(*args, **kwargs):
            calls.append(args[1:]);return git(*args, **kwargs)
        with patch("adp.memory.git", side_effect=counted), patch("adp.git.git", side_effect=counted):
            start = time.monotonic();expected = self.native.inspect();native_seconds = time.monotonic() - start
            native_calls = len(calls);native_blobs = sum(c[0] == "cat-file" for c in calls);calls.clear()
            start = time.monotonic();actual = self.fast.inspect();batch_seconds = time.monotonic() - start
            batch_calls = len(calls)
        self.assertEqual(actual, expected)
        self.assertLess(batch_calls, native_calls)
        self.assertEqual(native_blobs - sum(c[0] == "cat-file" for c in calls), 7)  # Four size/body pairs become one exact batch.
        self.assertEqual(native_calls - batch_calls, 9)  # Plus three registration queries becoming one.
        self.assertEqual(self.preserved(), before)
        self.assertIs(type(self.fast), Memory)
        print("SYNTHETIC_CURRENT_MEMORY_COMMANDS native=" + str(native_calls) + " batch=" + str(batch_calls)
              + " native_seconds=" + str(round(native_seconds, 6)) + " batch_seconds=" + str(round(batch_seconds, 6)), flush=True)

    def test_context_query_parity_recovery_freshness_and_late_dirty_observation(self):
        before = self.preserved()
        directory = self.native._registered()
        self.assertEqual(self.fast._accounting_registered(), (directory, None))
        self.assertEqual(self.fast._accounting_registered(head=True), (directory, value(self.native.path, "rev-parse", "HEAD")))
        expected = self.native.inspect(recovery=True)
        calls = []
        def counted(*args, **kwargs):
            calls.append(args[1:]);return git(*args, **kwargs)
        with patch("adp.memory.git", side_effect=counted), patch("adp.git.git", side_effect=counted):
            self.assertEqual(self.fast.inspect(recovery=True), expected)
        self.assertEqual(len(calls), 9)
        context = [c for c in calls if "--symbolic-full-name" in c]
        self.assertEqual(len(context), 2)  # Recovery re-registers the actual context after reading blobs.
        self.assertEqual((context[0].count("HEAD"), context[1].count("HEAD")), (2, 1))
        self.assertEqual(self.preserved(), before)
        with patch.object(self.fast, "_accounting_registered", side_effect=AssertionError("Default writer read keeps native registration")):
            self.assertEqual(self.fast._local(dirty=True), self.native._local(dirty=True))
        state = self.fast.path / "state.json";raw = state.read_bytes()
        native_read = self.fast._read_ref
        def drift(ref):
            result = native_read(ref)
            atomic(state, b"{}\n")
            return result
        try:
            with patch.object(self.fast, "_read_ref", side_effect=drift):
                self.assertEqual(self.fast.inspect()["health"], "RECOVERY_REQUIRED")
        finally:atomic(state, raw)
        for kind in ("insteadOf", "pushInsteadOf"):
            name = "url." + str(self.base / "unapproved.git") + "." + kind
            git(self.a, "config", name, str(self.remote))
            try:
                for memory in (self.native, self.fast):
                    with self.assertRaises(ADPError):memory.inspect()
            finally:git(self.a, "config", "--unset-all", name)
        self.assertEqual(self.fast.inspect(), self.native.inspect())

    def test_context_framing_branch_common_backlink_and_unsupported_paths_refuse(self):
        for head in (False, True):
            for fault in ("missing", "extra", "nul", "cr", "branch", "common", "head"):
                if fault == "head" and not head:continue
                def malformed(root, *args, **kwargs):
                    raw = git(root, *args, **kwargs)
                    if "--symbolic-full-name" not in args:return raw
                    lines = raw.split(b"\n")
                    if fault == "missing":return b"\n".join(lines[:-2]) + b"\n"
                    if fault == "extra":return raw + b"extra\n"
                    if fault == "nul":return raw.replace(b"\n", b"\0\n", 1)
                    if fault == "cr":return raw.replace(b"\n", b"\r\n", 1)
                    if fault == "branch":lines[-2] = b"HEAD"
                    if fault == "common":lines[1] = str(self.base / "foreign.git").encode()
                    if fault == "head":lines[2] = b"not-a-sha"
                    return b"\n".join(lines)
                with self.subTest(head=head, fault=fault), patch("adp.memory.git", side_effect=malformed):
                    with self.assertRaises(ADPError):self.fast._accounting_registered(head=head)
        directory = self.native._registered();backlink = directory / "gitdir";raw = backlink.read_bytes()
        backlink.write_text(str(self.base / "foreign" / ".git") + "\n")
        try:
            for memory in (self.native, self.fast):
                with self.assertRaises(ADPError):memory.inspect()
        finally:backlink.write_bytes(raw)
        path = self.fast.path
        self.fast.path = Path(str(path) + "\nunsupported")
        try:
            with patch("adp.memory.git", side_effect=AssertionError("Unsupported framing uses original path")):
                self.assertIsNone(self.fast._accounting_registered())
        finally:self.fast.path = path
        with patch.object(self.fast, "_accounting_registered", return_value=None), patch.object(self.fast, "_registered", wraps=self.fast._registered) as original:
            self.assertEqual(self.fast.inspect(), self.native.inspect())
            original.assert_called_once()

    def test_owner_inbox_pending_dirty_remote_and_path_changes_are_always_observed(self):
        def same():self.assertEqual(self.fast.inspect(), self.native.inspect())
        same()
        owner = self.native.control / "owner.json";raw = owner.read_bytes();owner.unlink()
        try:
            same();self.assertFalse(self.fast.inspect()["local_owner"])
        finally:atomic(owner, raw)
        pending = self.native.control / "pending.json";atomic(pending, b"{}\n")
        try:
            same();self.assertEqual(self.fast.inspect()["health"], "RECOVERY_REQUIRED")
            for memory in (self.native, self.fast):
                with self.assertRaises(ADPError):memory.inspect(recovery=True)
        finally:pending.unlink()
        job = self.native.assign("episode", "synthetic-worker-label")
        self.native.deliver({"schema_version": 1, **job, "result": {"outcome": "UNKNOWN", "summary": "Unaccepted synthetic result", "evidence": []}})
        same();self.assertEqual(self.fast.inspect()["inbox_count"], 1)
        self.native.accept(job["assignment_id"])
        same();self.assertEqual(self.fast.inspect()["inbox_count"], 0)
        state = self.native.path / "state.json";raw = state.read_bytes()
        atomic(state, b"{}\n")
        try:
            same();self.assertEqual(self.fast.inspect()["health"], "RECOVERY_REQUIRED")
        finally:atomic(state, raw)
        retained = self.base / "retained-state"
        state.rename(retained);state.symlink_to(retained)
        try:
            for memory in (self.native, self.fast):
                with self.assertRaises(ADPError):memory.inspect()
        finally:state.unlink();retained.rename(state)
        git(self.a, "remote", "set-url", "upstream", str(self.base / "unapproved.git"))
        try:
            for memory in (self.native, self.fast):
                with self.assertRaises(ADPError):memory.inspect()
        finally:git(self.a, "remote", "set-url", "upstream", str(self.remote))
        other = Memory(self.config(self.b), pinned_local_remote=self.remote)
        other.initialize(authorized=True)
        owner_id = other.inspect()["state"]["owner"]["id"]
        other.claim("synthetic-second-owner", takeover=True, confirmed_stopped_owner=owner_id)
        same();self.assertEqual(self.fast.inspect()["health"], "REMOTE_MISMATCH")

    def test_missing_corrupt_and_malformed_blobs_refuse_without_forgiving_fallback(self):
        self.assertEqual(self.fast.inspect(), self.native.inspect())
        head = value(self.native.path, "rev-parse", "HEAD")
        oid = value(self.a, "rev-parse", head + ":state.json")
        path = self.a / ".git" / "objects" / oid[:2] / oid[2:]
        saved = self.base / "retained-object";raw = path.read_bytes();mode = path.stat().st_mode & 0o777
        path.rename(saved)
        try:
            for memory in (self.native, self.fast):
                with self.assertRaises(ADPError):memory.inspect()
        finally:saved.rename(path)
        path.chmod(0o600);path.write_bytes(b"Corrupt owned fixture object")
        try:
            for memory in (self.native, self.fast):
                with self.assertRaises(ADPError):memory.inspect()
        finally:path.write_bytes(raw);path.chmod(mode)
        def header_change(raw, kind):
            end = raw.index(b"\n");parts = raw[:end].split()
            if kind == "oid":parts[0] = b"0" * len(parts[0])
            if kind == "type":parts[1] = b"tree"
            if kind == "size":parts[2] = str(MAX_JSON + 1).encode()
            if kind == "missing":return parts[0] + b" missing\n"
            if kind == "body":return raw[:end + 1] + b"!" + raw[end + 2:]
            if kind == "trailing":return raw + b"unexpected"
            if kind == "truncated":return raw[:-1]
            return b" ".join(parts) + raw[end:]
        for fault in ("oid", "type", "size", "missing", "body", "trailing", "truncated"):
            def malformed(root, *args, **kwargs):
                self.assertNotEqual(args[:2], ("cat-file", "-s"), "Malformed batch must never fall back")
                actual = git(root, *args, **kwargs)
                return header_change(actual, fault) if args == ("cat-file", "--batch") else actual
            with self.subTest(fault=fault), patch("adp.memory.git", side_effect=malformed), patch("adp.git.git", side_effect=malformed):
                with self.assertRaises(ADPError):self.fast.inspect()
        self.assertEqual(self.fast.inspect(), self.native.inspect())

    def test_larger_valid_inventory_keeps_native_loop_and_exact_memory_trust_type(self):
        self.native.add_task("larger-inventory", self.revision)
        with patch.object(self.fast, "_accounting_blobs", side_effect=AssertionError("Use unchanged larger reader")):
            self.assertEqual(self.fast.inspect(), self.native.inspect())
        original = Memory(self.config(), pinned_local_remote=self.remote)
        self.assertFalse(original._accounting_reads)
        from types import SimpleNamespace
        selected = EpisodeState.memory(SimpleNamespace(root=SimpleNamespace(memory=lambda: original)))
        self.assertIs(selected, original)
        self.assertIs(type(selected), Memory)  # Preserve ProjectValidation's exact trusted-type gate.
        self.assertTrue(selected._accounting_reads)
        self.assertFalse(Memory(self.config(), pinned_local_remote=self.remote)._accounting_reads)
        ignore = self.native.path / ".gitignore"
        ignore.write_bytes(b"Unapproved ignore policy\n")
        git(self.native.path, "add", ".gitignore");git(self.native.path, "commit", "-m", "Malformed disposable ignore")
        for memory in (self.native, self.fast):
            with self.assertRaises(ADPError):memory.inspect()
