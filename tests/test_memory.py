"""Two independent clone proofs of memory, recovery and adversarial refusals."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from adp.errors import ADPError, AuthorityError, Conflict, GitError
from adp.memory import Memory
from adp.schema import MAX_RESULT, bundle, key
from test_config import GitFixture, run, snapshot


class MemoryFixture(GitFixture):
    def setUp(self) -> None:
        super().setUp()
        self.memory = Memory(self.config())
        self.other = Memory(self.config(self.b))
        self.sha = run(self.a, "rev-parse", "HEAD")

    def initialize(self) -> None:
        self.memory.initialize(authorized=True)
        self.memory.claim("conductor-a")

    def envelope(self, memory: Memory | None = None, identifier: str = "issue:alpha/../Ω") -> dict:
        memory = memory or self.memory
        memory.add_task(identifier, self.sha)
        return {"schema_version": 1, **memory.assign(identifier, "worker"),
                "result": {"outcome": "PASS", "summary": "bounded observation", "evidence": ["fixture:proof"]}}


class MemoryTests(MemoryFixture):
    def test_first_repeat_and_two_clone_handoff(self) -> None:
        before = snapshot(self.a)
        with self.assertRaises(AuthorityError):
            self.memory.initialize()
        self.assertEqual(snapshot(self.a), before)
        self.initialize()
        envelope = self.envelope()
        state_before = self.memory.inspect()["state"]
        self.memory.initialize(authorized=True)
        self.assertEqual(self.memory.inspect()["state"], state_before)
        self.memory.deliver(envelope)
        with self.assertRaisesRegex(Conflict, "inbox"):
            self.memory.handoff()
        self.memory.accept(envelope["assignment_id"])
        self.memory.handoff()
        self.other.initialize(authorized=True)
        self.other.claim("conductor-b")
        self.assertEqual(self.other.inspect()["state"]["generation"], 2)
        task = self.other.inspect()["tasks"][envelope["task_key"]]
        self.assertEqual(task["assignments"][envelope["assignment_id"]]["result"]["outcome"], "PASS")
        self.assertEqual((self.a / "product").read_text(), "unchanged\n")
        self.assertEqual(run(self.a, "rev-parse", "HEAD"), self.sha)
        self.assertEqual(run(self.b, "rev-parse", "HEAD"), self.sha)

    def test_missing_owner_and_confirmed_takeover(self) -> None:
        self.initialize()
        envelope = self.envelope()
        self.other.initialize(authorized=True)
        with self.assertRaises(Conflict):
            self.other.add_task("second")
        owner_id = self.other.inspect()["state"]["owner"]["id"]
        with self.assertRaises(Conflict):
            self.other.claim("b", takeover=True, confirmed_stopped_owner="wrong")
        self.other.claim("b", takeover=True, confirmed_stopped_owner=owner_id)
        with self.assertRaises(Conflict):
            self.memory.add_task("second")
        self.memory.recover()
        with self.assertRaises(Conflict):
            self.memory.add_task("second")
        with self.assertRaises(Conflict):
            self.memory.deliver(envelope)
        task = self.other.inspect()["tasks"][envelope["task_key"]]
        self.assertEqual(task["assignments"][envelope["assignment_id"]]["status"], "incomplete")
        (self.other.control / "owner.json").unlink()
        self.other.recover()
        with self.assertRaises(Conflict):
            self.other.claim("restart")

    def test_duplicate_stale_and_exact_revision_binding(self) -> None:
        self.initialize()
        envelope = self.envelope()
        for field, bad_value in (("generation", 0), ("source_revision", "b" * 40),
                                 ("worker", "another"), ("task_key", "a" * 64)):
            bad = copy.deepcopy(envelope)
            bad[field] = bad_value
            with self.assertRaises(ADPError):
                self.memory.deliver(bad)
        self.memory.deliver(envelope)
        with self.assertRaises(Conflict):
            self.memory.deliver(envelope)
        self.memory.accept(envelope["assignment_id"])
        with self.assertRaises(Conflict):
            self.memory.deliver(envelope)
        self.memory.set_revision("issue:alpha/../Ω", "f" * 40)
        accepted = self.memory.inspect()["tasks"][envelope["task_key"]]["assignments"][envelope["assignment_id"]]
        self.assertEqual(accepted["source_revision"], self.sha)
        self.assertEqual(accepted["status"], "accepted")

    def test_failed_push_and_recovery_do_not_rewrite_terminal_jobs(self) -> None:
        self.initialize()
        envelope = self.envelope()
        self.memory.deliver(envelope)
        with patch.object(self.memory, "_push", side_effect=GitError("synthetic push failure")):
            with self.assertRaises(GitError):
                self.memory.accept(envelope["assignment_id"])
        self.assertEqual(self.memory.inspect()["health"], "RECOVERY_REQUIRED")
        self.memory.recover()
        # Crash after push and before inbox cleanup: only exact accepted data can be removed.
        self.memory.cleanup_inbox()
        self.assertEqual(self.memory.inspect()["inbox_count"], 0)
        task = self.memory.inspect()["tasks"][envelope["task_key"]]
        self.assertEqual(task["assignments"][envelope["assignment_id"]]["status"], "accepted")

    def test_interrupted_commit_replays_journal_once(self) -> None:
        self.initialize()
        from adp.memory import git as real_git
        def interrupt(path, *args, **kwargs):
            if args[0] == "commit":
                raise GitError("synthetic interruption before commit")
            return real_git(path, *args, **kwargs)
        with patch("adp.memory.git", side_effect=interrupt):
            with self.assertRaises(GitError):
                self.memory.add_task("crash")
        self.assertEqual(self.memory.inspect()["health"], "RECOVERY_REQUIRED")
        self.memory.recover()
        revision = self.memory.inspect()["state"]["revision"]
        self.memory.recover()
        self.assertEqual(revision, self.memory.inspect()["state"]["revision"])
        self.assertIn(key("crash"), self.memory.inspect()["tasks"])

    def test_failed_initial_push_has_explicit_recovery(self) -> None:
        with patch.object(self.memory, "_push", side_effect=GitError("synthetic transport failure")):
            with self.assertRaises(GitError):
                self.memory.initialize(authorized=True)
        with self.assertRaises(Conflict):
            self.memory.claim("a")
        self.memory.recover()
        self.memory.claim("a")

    def test_remote_divergence_is_retained_honestly(self) -> None:
        self.initialize()
        self.other.initialize(authorized=True)
        owner = self.other.inspect()["state"]["owner"]["id"]
        with patch.object(self.memory, "_push", side_effect=GitError("synthetic push failure")):
            with self.assertRaises(GitError):
                self.memory.add_task("local-only")
        local_head = run(self.memory.path, "rev-parse", "HEAD")
        self.other.claim("b", takeover=True, confirmed_stopped_owner=owner)
        with self.assertRaises(Conflict):
            self.memory.recover()
        self.assertEqual(local_head, run(self.memory.path, "rev-parse", "HEAD"))
        self.assertTrue((self.memory.control / "pending.json").exists())
        self.assertNotIn(key("local-only"), self.other.inspect()["tasks"])

    def test_multi_issue_serialization_unique_assignments_and_cleanup(self) -> None:
        self.initialize()
        identifiers = ["a", "b", "opaque/../../issue"]
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda i: self.memory.add_task(i, self.sha), identifiers))
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = list(pool.map(lambda i: self.memory.assign(i, "worker"), identifiers))
        self.assertEqual(len({j["assignment_id"] for j in jobs}), 3)
        for identifier, job in zip(identifiers, jobs):
            envelope = {"schema_version": 1, **job,
                        "result": {"outcome": "ERROR", "summary": "fixture failure preserved", "evidence": []}}
            self.memory.deliver(envelope)
            self.memory.accept(job["assignment_id"])
            self.memory.retire(identifier, evidence="fixture:closed", confirmed=True)
        self.assertEqual(self.memory.inspect()["tasks"], {})
        self.assertEqual(list((self.memory.path / "tasks").iterdir()), [])
        self.memory.add_task("next", self.sha)
        self.assertTrue(self.memory.assign("next", "worker")["assignment_id"].endswith("-4"))

    def test_read_only_commands_do_not_change_any_local_or_remote_bytes(self) -> None:
        self.initialize()
        self.envelope()
        before = snapshot(self.base)
        for memory in (self.memory, self.other):
            memory.inspect()
            memory.config.remote_head()
        self.assertEqual(before, snapshot(self.base))

    def test_symlink_unexpected_files_and_oversized_delivery_refused(self) -> None:
        self.initialize()
        envelope = self.envelope()
        bad = copy.deepcopy(envelope)
        bad["result"]["summary"] = "x" * MAX_RESULT
        with self.assertRaises(ADPError):
            self.memory.deliver(bad)
        (self.memory.path / "inbox").symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ADPError):
            self.memory.deliver(envelope)
        (self.memory.path / "inbox").unlink()
        (self.memory.path / "product").write_text("unexpected")
        with self.assertRaises(ADPError):
            self.memory.add_task("blocked")

    def test_crafted_remote_tree_never_checked_out(self) -> None:
        self.memory.initialize(authorized=True)
        (self.memory.path / "escape").symlink_to(self.base)
        run(self.memory.path, "add", "escape")
        run(self.memory.path, "commit", "-m", "crafted")
        run(self.memory.path, "push", "upstream", "HEAD:refs/heads/coordination/current")
        with self.assertRaises(ADPError):
            self.other.initialize(authorized=True)
        self.assertFalse(self.other.path.exists())

    def test_process_death_during_atomic_replacement_and_inbox_delivery(self) -> None:
        self.initialize()
        import json
        import os
        import subprocess
        import sys
        envelope = self.envelope(identifier="atomic-delivery")
        program = r"""
import json, os, sys
from pathlib import Path
from unittest.mock import patch
from adp.config import Config
from adp.memory import Memory
root, storage, target = sys.argv[1:]
memory = Memory(Config.discover(Path(root), branch="coordination/current", storage=Path(storage)))
operation = os.link if target == "inbox" else os.replace
def interrupted(src, dst):
    destination = Path(dst)
    if ((target == "tasks" and destination.parent.name == "tasks")
        or (target == "state" and destination.name == "state.json")
        or (target == "inbox" and destination.parent.name == "inbox")):
        os._exit(99)
    return operation(src, dst)
with patch("adp.storage.os." + ("link" if target == "inbox" else "replace"), side_effect=interrupted):
    if target == "inbox":
        memory.deliver(json.loads(sys.stdin.read()))
    else:
        memory.add_task("atomic-" + target)
"""
        root = str(__import__("pathlib").Path(__file__).resolve().parents[1])
        env = {**os.environ, "PYTHONPATH": root, "PYTHONDONTWRITEBYTECODE": "1"}
        for target in ("tasks", "state", "inbox"):
            child = subprocess.run([sys.executable, "-c", program, str(self.a),
                str(self.memory.path), target], env=env, input=json.dumps(envelope),
                capture_output=True, text=True, timeout=60)
            self.assertEqual(child.returncode, 99, child.stderr)
            self.memory.recover()
            self.assertEqual(self.memory.inspect()["health"], "SYNCED")
            self.assertEqual(list(self.memory.path.rglob(".adp-tmp-*")), [])
        job = self.memory.inspect()["tasks"][envelope["task_key"]]["assignments"][envelope["assignment_id"]]
        self.assertEqual(job["status"], "pending")
        self.assertIsNone(job["result"])
        self.memory.deliver(envelope)
        self.memory.accept(envelope["assignment_id"])

    def test_actual_remote_push_rejection_and_retry(self) -> None:
        self.initialize()
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o700)
        remote_before = self.config().remote_head()
        with self.assertRaises(GitError):
            self.memory.add_task("rejected")
        self.assertEqual(remote_before, self.config().remote_head())
        self.assertNotEqual(remote_before, run(self.memory.path, "rev-parse", "HEAD"))
        hook.unlink()
        self.memory.recover()
        self.assertEqual(self.memory.inspect()["health"], "SYNCED")

    def test_schema_rejects_duplicate_jobs_malformed_types_and_unknown_fields(self) -> None:
        self.initialize()
        self.envelope()
        self.memory.add_task("b", self.sha)
        inspected = self.memory.inspect()
        state = inspected["state"]
        tasks = inspected["tasks"]
        first, second = tasks.values()
        if not first["assignments"]:
            first, second = second, first
        second["assignments"] = copy.deepcopy(first["assignments"])
        with self.assertRaisesRegex(ADPError, "Duplicate"):
            bundle(state, tasks, self.config().identity)
        for payload in ('{"a":1,"a":2}', '{"a":NaN}', '[]', '{'):
            from adp.schema import decode
            with self.assertRaises(ADPError):
                decode(payload.encode())
        malformed = copy.deepcopy(state)
        malformed["generation"] = True
        with self.assertRaises(ADPError):
            bundle(malformed, inspected["tasks"], self.config().identity)


if __name__ == "__main__":
    import unittest
    unittest.main()
