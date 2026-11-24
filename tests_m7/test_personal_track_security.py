"""Focused semantic authority, evidence retention and terminal-stop controls."""
from dataclasses import replace
from pathlib import Path
import shutil
from unittest.mock import patch

from adp.discovery_types import ReadinessReview
from adp.errors import ADPError
from adp.guard_types import Action, ActionKind, Observation, Outcome, data
from adp.personal_track import PersonalTrack
from adp.personal_track_preparation import ContextAuthority, prepare, semantic_bundle, unsigned_policy
from adp.policy import PolicyProvider
from adp.schema import encode
from adp.storage import atomic
from personal_track_fixtures import TrackFixture
from test_config import snapshot


class PersonalTrackSecurityTests(TrackFixture):
    def test_only_exact_typed_semantic_projection_can_receive_review_authority(self):
        self.enroll_track()
        packet = self.scope_only()
        bundle, worker = semantic_bundle(self.track), self.c.original_approval()
        adapter, source, claims = unsigned_policy(self.c)
        policy = PolicyProvider(adapter, authority=self.c.authority, clock=self.c.clock)
        policy.sources = tuple(self.c.authority.source(policy, claim, source) for claim in claims)
        authority = ContextAuthority(self.track, worker, bundle, policy)
        from adp.discovery_schema import typed
        from adp.ticket_types import OriginalScope
        scope = typed(OriginalScope, bundle["scope"])
        for purpose, body in (("arbitrary/domain", scope), ("ticket/original-scope", replace(scope, allowed_paths=("extra",))),
                ("ticket/preparation", "0" * 64), ("discovery/readiness", ReadinessReview(packet.identity, scope.goal,
                    (self.personal.plan["criterion"],), (), specification="KNOWN", policy="KNOWN", completed=True))):
            with self.subTest(purpose=purpose), self.assertRaises(ADPError):
                authority.evidence(purpose, body)
        self.assertTrue(authority.verify(authority.evidence("ticket/original-scope", scope),
            purpose="ticket/original-scope", subject=__import__("adp.ticket_preparation", fromlist=["original_scope_subject"]).original_scope_subject(scope)))
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.personal.feature.exists())

    def test_foreign_same_issue_packet_is_not_a_retained_admission(self):
        self.enroll_track()
        packet = self.scope_only()
        foreign = self.track.archive.save_packet(replace(packet, allowed_paths=("unapproved",)))
        from adp.personal_storage import read_private
        path = self.personal.state / "prepared-track.json"
        row = read_private(path)
        row["packet"] = foreign
        atomic(path, encode(row))
        before = self.c.memory.inspect()
        with self.assertRaises(ADPError):
            prepare(self.track)
        self.assertEqual(self.c.memory.inspect(), before)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse(self.personal.feature.exists())

    def test_missing_or_symlinked_archive_is_unknown_without_read_side_creation(self):
        self.enroll_track()
        archive = self.track.root / "archive"
        retained = self.track.root / "retained-archive"
        archive.rename(retained)
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            PersonalTrack(self.c)
        self.assertEqual(snapshot(self.base), before)
        archive.symlink_to(retained, target_is_directory=True)
        with self.assertRaises(ADPError):
            PersonalTrack(self.c)
        self.assertTrue(archive.is_symlink())

    def test_current_terminal_guard_and_changed_post_review_native_context_block(self):
        self.enroll_track()
        self.scope_only()
        repo = self.transport.api.responses[self.prefix].body
        repo["allow_merge_commit"] = False
        # The original independent snapshot is never silently rebound.
        from adp.personal_storage import read_private
        saved = read_private(self.personal.state / "prepared-track.json")
        from adp.discovery_schema import digest
        old = self.c.original_approval()["context"]["track_preparation"]
        self.assertNotEqual(old["snapshot"], data(self.track.current().snapshot))
        repo["allow_merge_commit"] = True
        rid = self.c.requirement("develop")
        for n in range(3):
            permit = self.c.guard.begin(self.c.task_id, rid, Action("personal:coordinator", ActionKind.CHECK, "negative:" + str(n), "Bounded negative"))
            self.c.guard.observe(self.c.task_id, rid, permit, Observation(Outcome.FAIL, ("fixture:failed",), (self.personal.plan["criterion"],)))
        state = self.c.memory.inspect()
        with self.assertRaises(ADPError):
            self.track.status()
        self.assertEqual(self.c.memory.inspect(), state)
        self.assertEqual(read_private(self.personal.state / "prepared-track.json"), saved)
