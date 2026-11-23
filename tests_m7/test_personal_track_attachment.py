"""Focused regressions for independently demonstrated review blockers."""
from pathlib import Path
from unittest.mock import patch

from adp.errors import ADPError
from adp.personal_storage import load_state
from adp.personal_track import immutable
from adp.personal_track_preparation import prepare
from personal_track_fixtures import TrackFixture
from test_config import run


class PersonalTrackAttachmentTests(TrackFixture):
    def test_retained_packet_allows_only_actual_own_feature_and_commit_refs(self):
        self.enroll_track()
        packet = self.scope_only()
        self.c.prepare_feature()
        original = self.c.memory.inspect()
        self.assertEqual(prepare(self.c.track), packet)
        self.assertEqual(self.c.memory.inspect(), original)
        self.assertEqual(len(self.requests), 1)
        _, token = self.c.invocation()
        result = self.c.run(reviewed=token, authorized=True)
        self.assertEqual(result["status"], "LOCAL_DRAFT_CODE_REVIEWED")
        current = self.c.memory.inspect()
        contexts = len(self.requests)
        self.assertEqual(prepare(self.c.track), packet)
        self.assertEqual(self.c.memory.inspect(), current)
        self.assertEqual(len(self.requests), contexts)
        run(self.a, "branch", "unapproved", "HEAD")
        with self.assertRaises(ADPError):
            prepare(self.c.track)
        self.assertEqual(self.c.memory.inspect(), current)

    def test_partial_personal_setup_keeps_same_next_tokens_and_window(self):
        self.enroll_track()
        accepted = self.merged()
        self.synchronize(accepted["merge"])
        choices = self.next_choices(2)
        proposed = self.c.track.next_preview(self.product, choices)
        with patch("adp.personal_enrollment.complete_setup", side_effect=OSError("Synthetic interrupted bootstrap")):
            with self.assertRaises(OSError):
                self.c.track.next(self.product, choices, reviewed=proposed["approval"],
                    setup_approval=proposed["setup_approval"], authorized=True)
        self.assertEqual(load_state(choices.directory).intent["phase"], "PREPARED")
        held = self.c.track.next_preview(self.product, choices)
        self.assertEqual(held["status"], "NEXT_PROPOSED_RETAINED")
        self.assertEqual((held["approval"], held["setup_approval"]), (proposed["approval"], proposed["setup_approval"]))
        result = self.c.track.next(self.product, choices, reviewed=held["approval"], setup_approval=held["setup_approval"], authorized=True)
        self.assertEqual(result["status"], "NEXT_ENROLLED_SCOPE_REVIEW_REQUIRED")
        child = load_state(choices.directory)
        self.assertEqual(child.plan, proposed["result"]["plan"])
        self.assertEqual(child.memory().inspect()["state"]["generation"], 1)

    def test_enrolled_child_without_shared_attachment_needs_original_next_recovery(self):
        self.enroll_track()
        accepted = self.merged()
        self.synchronize(accepted["merge"])
        choices = self.next_choices(2)
        proposed = self.c.track.next_preview(self.product, choices)
        def fail_shared(path, body):
            if path.parent == self.c.track.root / "links":
                raise OSError("Synthetic crash before shared attachment")
            return immutable(path, body)
        with patch("adp.personal_track.immutable", side_effect=fail_shared):
            with self.assertRaises(OSError):
                self.c.track.next(self.product, choices, reviewed=proposed["approval"],
                    setup_approval=proposed["setup_approval"], authorized=True)
        child = load_state(choices.directory)
        state = child.memory().inspect()
        self.assertEqual(child.intent["phase"], "ENROLLED")
        from adp.personal_runner import PersonalCoordinator
        incomplete = PersonalCoordinator(child, self.c.transport, None, clock=lambda: self.now)
        with self.assertRaises(ADPError):
            incomplete.live()
        held = self.c.track.next_preview(self.product, choices)
        self.assertEqual(held["status"], "NEXT_PROPOSED_RETAINED")
        self.assertEqual(held["approval"], proposed["approval"])
        self.c.track.next(self.product, choices, reviewed=held["approval"], setup_approval=held["setup_approval"], authorized=True)
        self.assertEqual(child.memory().inspect(), state)
        complete = self.c.track.next_preview(self.product, choices)
        self.assertEqual(complete["status"], "NEXT_ALREADY_ENROLLED")
        self.assertIsNone(complete["approval"])
