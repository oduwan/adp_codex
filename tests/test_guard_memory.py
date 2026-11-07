"""M1 v1/v2 compatibility, fenced migration/recovery and two-clone guard state."""
from __future__ import annotations

import contextlib
import copy
import io
from unittest.mock import patch

from adp.cli import main
from adp.errors import ADPError, AuthorityError, Conflict, GitError
from adp.guard import GuardRefusal, ProgressGuard
from adp.guard_types import Action, ActionKind, DecisionKind, Observation, Outcome, Progress, ProgressKind, Requirement
from adp.memory import Memory
from adp.schema import bundle, key
from test_config import snapshot
from test_guard import SyntheticAuthority
from test_memory import MemoryFixture


class GuardMemoryTests(MemoryFixture):
    def test_explicit_upgrade_preserves_v1_tasks_ownership_and_read_only_modes(self):
        self.initialize()
        envelope = self.envelope()
        self.memory.deliver(envelope)
        self.memory.accept(envelope["assignment_id"])
        self.memory.assign("issue:alpha/../Ω", "pending-worker")
        original = self.memory.inspect()
        before = snapshot(self.base)
        with self.assertRaises(AuthorityError):
            self.memory.upgrade_guard()
        for command, extra in (("init", ("--dry-run",)), ("doctor", ()), ("status", ())):
            with contextlib.redirect_stdout(io.StringIO()):
                code = main([command, "--repo", str(self.a), "--memory-branch", self.memory.branch,
                             "--storage", str(self.memory.path), *extra])
            self.assertEqual(code, 0)
        self.assertEqual(before, snapshot(self.base))
        upgraded = self.memory.upgrade_guard(authorized=True)
        self.assertEqual(upgraded["state"]["schema_version"], 2)
        self.assertEqual(upgraded["tasks"], original["tasks"])
        for field in ("owner", "generation", "assignment_sequence", "task_keys", "repository_id"):
            self.assertEqual(upgraded["state"][field], original["state"][field])
        before = snapshot(self.base)
        self.memory.inspect()
        self.assertEqual(before, snapshot(self.base))
        self.memory.upgrade_guard(authorized=True)
        self.assertEqual(upgraded["state"], self.memory.inspect()["state"])
        self.assertEqual(upgraded["tasks"], self.memory.inspect()["tasks"])
        malformed = copy.deepcopy(upgraded["state"])
        malformed["schema_version"] = 1
        with self.assertRaises(ADPError):
            bundle(malformed, upgraded["tasks"], self.memory.config.identity)
        malformed["schema_version"] = 3
        with self.assertRaises(ADPError):
            bundle(malformed, upgraded["tasks"], self.memory.config.identity)

    def test_upgrade_push_failure_recovers_across_v1_v2_without_owner_invention(self):
        self.initialize()
        envelope = self.envelope()
        self.memory.deliver(envelope)
        self.memory.accept(envelope["assignment_id"])
        self.other.initialize(authorized=True)
        original = self.memory.inspect()
        with patch.object(self.memory, "_push", side_effect=GitError("synthetic migration push failure")):
            with self.assertRaises(GitError):
                self.memory.upgrade_guard(authorized=True)
        self.assertEqual(self.memory.inspect()["health"], "RECOVERY_REQUIRED")
        self.assertEqual(self.other.inspect()["state"]["schema_version"], 1)
        self.memory.recover()
        self.other.recover()
        self.assertEqual(self.other.inspect()["state"]["schema_version"], 2)
        self.assertEqual(self.other.inspect()["tasks"], original["tasks"])
        self.assertFalse(self.other.inspect()["local_owner"])
        with self.assertRaises(Conflict):
            self.other.upgrade_guard(authorized=True)

    def test_interrupted_upgrade_commit_replays_validated_v2_journal(self):
        self.initialize()
        self.envelope()
        original = self.memory.inspect()
        from adp.memory import git as real_git
        def interrupted(path, *args, **kwargs):
            if args[0] == "commit":
                raise GitError("synthetic migration interruption")
            return real_git(path, *args, **kwargs)
        with patch("adp.memory.git", side_effect=interrupted):
            with self.assertRaises(GitError):
                self.memory.upgrade_guard(authorized=True)
        self.memory.recover()
        current = self.memory.inspect()
        self.assertEqual(current["state"]["schema_version"], 2)
        self.assertEqual(current["tasks"], original["tasks"])
        self.assertEqual(current["state"]["owner"], original["state"]["owner"])
        self.assertEqual(current["state"]["generation"], original["state"]["generation"])

    def test_guard_counters_survive_clone_handoff_and_reinstantiation(self):
        self.initialize()
        self.memory.add_task("opaque:guarded", self.sha)
        authority = SyntheticAuthority()
        guard = ProgressGuard(self.memory, authority=authority, clock=lambda: 100)
        with self.assertRaises(AuthorityError):
            guard.inspect("opaque:guarded", "a" * 64)
        self.memory.upgrade_guard(authorized=True)
        spec = Requirement("contract:accepted", "gate:fixed", ("criterion-A",))
        subject = guard.admission_subject("opaque:guarded", spec)
        identifier = guard.register("opaque:guarded", spec, authority.attest(subject, "admission"))
        for _ in range(2):
            permit = guard.begin("opaque:guarded", identifier, Action("author-A", ActionKind.CHECK, "hypothesis"))
            guard.observe("opaque:guarded", identifier, permit,
                Observation(Outcome.FAIL, ("fixture:failure",), spec.acceptance))
        before = snapshot(self.base)
        guard.inspect("opaque:guarded", identifier)
        self.assertEqual(before, snapshot(self.base))
        self.memory.handoff()
        self.other.initialize(authorized=True)
        self.other.claim("conductor-b")
        restarted = ProgressGuard(Memory(self.config(self.b)), authority=authority, clock=lambda: 100)
        permit = restarted.begin("opaque:guarded", identifier, Action("author-B", ActionKind.CHECK, "cosmetic alias"))
        decision = restarted.observe("opaque:guarded", identifier, permit,
            Observation(Outcome.FAIL, ("fixture:same-failure",), spec.acceptance))
        self.assertEqual(decision.kind, DecisionKind.FORENSIC_REQUIRED)
        with self.assertRaises(GuardRefusal):
            restarted.begin("opaque:guarded", identifier, Action("author-C", ActionKind.CHECK, "another alias"))
        self.memory.recover()
        persisted = self.memory.inspect()["state"]["progress_guard"]["requirements"][identifier]
        self.assertEqual(persisted["counters"]["failures"], 3)
        self.assertEqual(persisted["last"]["context"]["generation"], 2)

    def test_crafted_guard_records_are_closed_and_fail_with_controlled_errors(self):
        self.initialize()
        self.memory.add_task("guarded", self.sha)
        self.memory.upgrade_guard(authorized=True)
        authority = SyntheticAuthority()
        guard = ProgressGuard(self.memory, authority=authority)
        spec = Requirement("contract:valid", "gate:fixed", ("criterion",))
        subject = guard.admission_subject("guarded", spec)
        identifier = guard.register("guarded", spec, authority.attest(subject, "admission"))
        original = self.memory.inspect()
        for path, value in ((("limits", "failures"), 4), (("counters", "failures"), True),
                            (("tasks",), ["../escape"]), (("mode",), []),
                            (("forensic_round",), 3), (("seen_facts",), [None]),
                            (("unexpected",), "override")):
            state = copy.deepcopy(original["state"])
            target = state["progress_guard"]["requirements"][identifier]
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ADPError):
                bundle(state, original["tasks"], self.memory.config.identity)

    def test_task_recreation_cannot_reuse_an_old_guard_attempt_or_approval(self):
        self.initialize()
        self.memory.add_task("recreated", self.sha)
        self.memory.upgrade_guard(authorized=True)
        authority = SyntheticAuthority()
        guard = ProgressGuard(self.memory, authority=authority, clock=lambda: 100)
        spec = Requirement("contract:stable", "gate:stable", ("criterion",))
        subject = guard.admission_subject("recreated", spec)
        identifier = guard.register("recreated", spec, authority.attest(subject, "admission"))
        permit = guard.begin("recreated", identifier, Action("author-A", ActionKind.CHECK, "original incarnation"))
        old_epoch = permit.decision.baseline.task_epoch
        self.memory.retire("recreated", evidence="fixture:durable-disposition", confirmed=True)
        self.memory.add_task("recreated", self.sha)
        self.assertNotEqual(guard.inspect("recreated", identifier).baseline.task_epoch, old_epoch)
        with self.assertRaises(Conflict):
            guard.observe("recreated", identifier, permit, Observation(Outcome.PASS, ("fixture:stale",), spec.acceptance))
        guard.abandon("recreated", identifier, evidence_reference="fixture:original-incarnation-incomplete")
        self.assertEqual(guard.inspect("recreated", identifier).kind, DecisionKind.ALLOW)
        self.assertEqual(self.memory.inspect()["state"]["progress_guard"]["requirements"][identifier]["counters"]["stalls"], 1)
        current = guard.begin("recreated", identifier, Action("author-A", ActionKind.CHECK, "current incarnation"))
        approved = Observation(Outcome.PASS, ("fixture:current-observation",), spec.acceptance,
            Progress(ProgressKind.CORRECTION_APPROVED, "current-fix", ("fixture:independent-review",)))
        subject = guard.progress_subject("recreated", identifier, current, approved)
        guard.observe("recreated", identifier, current, approved, evidence=authority.attest(subject, "progress"))
        guard.require_approval("recreated", identifier)
        self.memory.retire("recreated", evidence="fixture:second-disposition", confirmed=True)
        self.memory.add_task("recreated", self.sha)
        with self.assertRaises(GuardRefusal):
            guard.require_approval("recreated", identifier)
