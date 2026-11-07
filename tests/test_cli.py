"""CLI boundary and actual installed-command semantics in disposable targets."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from unittest.mock import patch

from adp.cli import main
from adp.errors import AuthorityError, Conflict
from test_memory import MemoryFixture
from test_config import GitFixture, run, snapshot


class CLITests(GitFixture):
    def invoke(self, command: str, *extra: str) -> tuple[int, str, str]:
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main([command, "--repo", str(self.a), "--memory-branch", "coordination/current",
                         "--storage", str(self.base / "a-memory"), *extra])
        return code, output.getvalue(), errors.getvalue()

    def test_fresh_read_only_and_authorized_initialization(self) -> None:
        before = snapshot(self.base)
        for command, extra, expected in (("init", ("--dry-run",), 0),
                                         ("doctor", (), 4), ("status", (), 4)):
            code, output, errors = self.invoke(command, *extra)
            self.assertEqual(code, expected, errors)
            self.assertIn("READ_ONLY" if command == "init" else "UNINITIALIZED", output)
        self.assertEqual(before, snapshot(self.base))
        self.assertEqual(self.invoke("init", "--apply")[0], 6)
        self.assertEqual(before, snapshot(self.base))
        self.assertEqual(self.invoke("init", "--apply", "--authorize-memory-write")[0], 0)
        self.assertEqual(self.invoke("claim", "--owner", "a")[0], 0)
        before = snapshot(self.base)
        observed: list[str] = []
        real_popen = subprocess.Popen
        def observational(args, **kwargs):
            operation = args[args.index("-C") + 2]
            observed.append(operation)
            self.assertIn(operation, {"rev-parse", "config", "remote", "check-ref-format",
                "worktree", "ls-remote", "status", "symbolic-ref", "ls-tree", "cat-file"})
            return real_popen(args, **kwargs)
        with patch("adp.git.subprocess.Popen", side_effect=observational):
            for command, extra in (("init", ("--dry-run",)), ("doctor", ()), ("status", ())):
                code, output, errors = self.invoke(command, *extra)
                self.assertEqual(code, 0, errors)
        self.assertIn("ls-remote", observed)
        self.assertEqual(before, snapshot(self.base))

    def test_dirty_product_doctor_and_unsafe_storage_fail_without_changes(self) -> None:
        (self.a / "product").write_text("dirty")
        before = snapshot(self.base)
        self.assertEqual(self.invoke("doctor")[0], 4)
        self.assertEqual(before, snapshot(self.base))
        self.assertEqual(self.invoke("init", "--dry-run")[0], 4)

    def test_module_entrypoint_and_missing_configuration(self) -> None:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        root = str(__import__("pathlib").Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = root
        before = snapshot(self.base)
        result = subprocess.run([sys.executable, "-m", "adp", "init", "--dry-run", "--repo", str(self.a)],
                                cwd=self.base, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decision_required", result.stdout)
        self.assertEqual(before, snapshot(self.base))

    def test_exit_codes_and_handoff_cycle(self) -> None:
        self.assertEqual(self.invoke("init", "--apply", "--authorize-memory-write")[0], 0)
        self.assertEqual(self.invoke("task-add", "opaque")[0], 4)
        self.assertEqual(self.invoke("claim", "--owner", "a")[0], 0)
        revision = run(self.a, "rev-parse", "HEAD")
        self.assertEqual(self.invoke("task-add", "opaque", "--revision", revision)[0], 0)
        code, output, _ = self.invoke("assign", "opaque", "--worker", "worker")
        self.assertEqual(code, 0)
        job = json.loads(output)
        self.assertEqual(self.invoke("task-retire", "opaque", "--evidence", "fixture:closed")[0], 6)
        self.assertEqual(self.invoke("handoff")[0], 0)
        self.assertEqual(self.invoke("claim", "--owner", "a-again")[0], 0)
        self.assertEqual(self.invoke("task-retire", "opaque", "--evidence", "fixture:closed", "--confirm-disposition")[0], 0)
        self.assertEqual(self.invoke("release")[0], 0)


class ProcessMemoryTests(MemoryFixture):
    def test_process_writers_serialize_and_stale_inbox_discard(self) -> None:
        self.initialize()
        import os
        import subprocess
        import sys
        root = str(__import__("pathlib").Path(__file__).resolve().parents[1])
        env = {**os.environ, "PYTHONPATH": root, "PYTHONDONTWRITEBYTECODE": "1"}
        processes = [subprocess.Popen([sys.executable, "-m", "adp", "task-add",
            "--repo", str(self.a), "--memory-branch", self.memory.branch,
            "--storage", str(self.memory.path), identifier, "--revision", self.sha],
            cwd=self.base, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for identifier in ("process-a", "process-b")]
        for process in processes:
            _, errors = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, errors)
        self.assertEqual(len(self.memory.inspect()["tasks"]), 2)
        envelope = self.envelope()
        self.memory.deliver(envelope)
        self.other.initialize(authorized=True)
        self.other.claim("b", takeover=True,
            confirmed_stopped_owner=self.other.inspect()["state"]["owner"]["id"])
        with self.assertRaises(Conflict):
            self.memory.recover()
        with self.assertRaises(AuthorityError):
            self.memory.discard_inbox(envelope["assignment_id"])
        self.memory.discard_inbox(envelope["assignment_id"], confirmed=True)
        self.memory.recover()
        self.assertEqual(self.memory.inspect()["health"], "SYNCED")
