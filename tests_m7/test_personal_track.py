"""Focused M10-C native-chain composition. All workers/API are SYNTHETIC."""
from dataclasses import replace
import json
from unittest.mock import patch

from adp.discovery_github import Response
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.guard_types import data
from adp.personal_storage import PersonalBlocked, read_private
from adp.personal_track import PersonalTrack
from personal_track_fixtures import TrackFixture
from test_config import snapshot


class PersonalTrackTests(TrackFixture):
    def test_original_scope_packet_and_three_native_issue_completion_chain(self):
        self.enroll_track()
        original = self.personal.intent
        packet = self.scope_only()
        self.assertEqual(packet.original_issue_revision, original["original"]["revision"])
        self.assertEqual(packet.execution_authority, "UNKNOWN")
        initial = self.track.status(runtimes=self.runtime_by_identity)[0]
        self.assertEqual([row["status"] for row in initial["issues"]], ["READY", "BLOCKED_DEPENDENCY", "BLOCKED_DEPENDENCY"])
        accepted = []
        for number in (1, 2, 3):
            self.assertEqual(self.personal.plan["issue"], number)
            if number > 1:
                dependencies = self.personal.plan["native_prerequisites"]
                self.assertEqual(len(dependencies), 1)
                self.assertEqual(dependencies[0]["target"]["number"], number - 1)
            result = self.merged(loss_pr="after" if number == 1 else None, loss_merge="after" if number == 1 else None)
            accepted.append(result)
            self.assertEqual(self.personal.plan["issue"], number)
            self.assertEqual(result["ci"]["status"], "PASS")
            self.assertNotEqual(result["source"], result["merge"])
            status = self.c.track.status(transport=self.http)[0]
            self.assertEqual(status["next_issue"], number + 1 if number < 3 else None)
            if number < 3:
                self.synchronize(result["merge"])
                self.advance(number + 1)
                self.assertEqual(self.personal.plan["checkout"]["head"], result["merge"])
        self.assertEqual(status["status"], "COMPLETE")
        self.assertEqual(len(self.all_pulls), 3)
        self.assertEqual(len({r["checkpoint"] for r in accepted}), 3)
        self.assertEqual(len({r["setup"] for r in accepted}), 3)
        self.assertEqual(data(next(o.issue for o in self.track.originals.values() if o.issue.number == 1)), original["original"])

    def test_registration_scope_authority_and_missing_native_inventory_fail_closed(self):
        self.enroll()
        before = snapshot(self.base)
        _, token = PersonalTrack.registration(self.c, (1, 2, 3))
        self.assertEqual(snapshot(self.base), before)
        for authorized, reviewed in ((False, token), (True, "personal-track:" + "0" * 64)):
            with self.subTest(authorized=authorized), self.assertRaises(ADPError):
                PersonalTrack.register(self.c, (1, 2, 3), reviewed=reviewed, authorized=authorized)
        path = self.prefix + "/issues/2/dependencies/blocked_by?per_page=100&page=1"
        self.transport.api.responses[path] = Response(403, {})
        with self.assertRaises(ADPError):
            PersonalTrack.register(self.c, (1, 2, 3), reviewed=token, authorized=True)
        self.assertFalse((self.personal.state / "track-link.json").exists())

    def test_closed_green_or_local_only_never_unblocks_successor(self):
        self.enroll_track()
        before = snapshot(self.base)
        self.assertIsNone(self.track.status()[0]["next_issue"])
        self.assertEqual(snapshot(self.base), before)
        self.scope_only()
        self.local_and_publish()
        with self.assertRaises(ADPError):
            self.c.track.completion_preview(self.product)
        self.create_pr()
        self.execute_product("CI", accept_native=True)
        with self.assertRaises(ADPError):
            self.c.track.completion_preview(self.product)
        self.execute_product("REVIEW")
        with self.assertRaises(ADPError):
            self.c.track.completion_preview(self.product)
        self.assertIsNone(self.c.track.status(transport=self.http)[0]["next_issue"])

    def test_missing_exact_merged_base_blocks_before_next_owner_or_source_effect(self):
        self.enroll_track()
        result = self.merged()
        before = self.observation_snapshot()
        with self.assertRaises(PersonalBlocked) as error:
            self.c.track.next_preview(self.product, self.next_choices(2))
        self.assertEqual(error.exception.reason, "NEXT_BASE_UNAVAILABLE")
        self.assertEqual(self.observation_snapshot(), before)
        self.assertTrue(self.c.memory.inspect()["local_owner"])
        self.assertNotEqual(result["merge"], self.personal.plan["checkout"]["head"])

    def test_next_requires_new_scope_and_preserves_previous_counters_and_owner_release(self):
        self.enroll_track()
        result = self.merged()
        self.synchronize(result["merge"])
        choices = self.next_choices(2)
        proposal = self.c.track.next_preview(self.product, choices)
        before = self.c.memory.inspect()
        for authorized, reviewed in ((False, proposal["approval"]), (True, "personal-next:" + "0" * 64)):
            with self.subTest(authorized=authorized), self.assertRaises(ADPError):
                self.c.track.next(self.product, choices, reviewed=reviewed, setup_approval=proposal["setup_approval"], authorized=authorized)
        self.assertEqual(self.c.memory.inspect(), before)
        parent_memory = self.c.memory
        self.advance(2)
        after = parent_memory.inspect()
        self.assertIsNone(after["state"]["owner"])
        self.assertEqual(before["state"]["progress_guard"], after["state"]["progress_guard"])
        self.assertEqual(before["tasks"], after["tasks"])
        self.assertIsNone(self.c.record())

    def test_original_version_scope_native_edge_and_permission_drift_stop(self):
        self.enroll_track()
        base = self.prefix + "/issues/2"
        row = self.transport.api.responses[base].body
        for field, value in (("body", "Unapproved extra functionality"), ("updated_at", "2026-11-23T00:00:00Z")):
            old = row[field]
            row[field] = value
            with self.subTest(field=field), self.assertRaises(ADPError):
                self.track.current()
            row[field] = old
        path = base + "/dependencies/blocked_by?per_page=100&page=1"
        original = self.transport.api.responses[path]
        self.transport.api.responses[path] = Response(200, [])
        with self.assertRaises(ADPError):
            self.track.current()
        self.transport.api.responses[path] = original
        repo = self.transport.api.responses[self.prefix].body
        original = repo["permissions"]
        repo["permissions"] = {"pull": True, "push": False, "admin": True}
        with self.assertRaises(ADPError):
            self.track.current()
        repo["permissions"] = original
