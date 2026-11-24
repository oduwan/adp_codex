"""Restart the SAME approved next intent; never replace a consumed window."""
from unittest.mock import patch

from adp.errors import ADPError
from adp.personal_storage import read_private
from personal_track_fixtures import TrackFixture
from network_fixtures import gv


class PersonalTrackRecoveryTests(TrackFixture):
    def test_next_recovers_interrupted_setup_after_handoff_without_fork_or_budget_reset(self):
        self.enroll_track()
        accepted = self.merged()
        self.synchronize(accepted["merge"])
        choices = self.next_choices(2)
        proposed = self.c.track.next_preview(self.product, choices)
        old = self.c.memory.inspect()
        with patch("adp.personal_track.apply_personal", side_effect=OSError("Synthetic interrupted approved setup")):
            with self.assertRaises(OSError):
                self.c.track.next(self.product, choices, reviewed=proposed["approval"],
                    setup_approval=proposed["setup_approval"], authorized=True)
        after = self.c.memory.inspect()
        self.assertIsNone(after["state"]["owner"])
        self.assertEqual(old["state"]["progress_guard"], after["state"]["progress_guard"])
        retained = read_private(self.personal.state / "next-intent.json")
        preview = self.c.track.next_preview(self.product, choices)
        self.assertEqual(preview["status"], "NEXT_PROPOSED_RETAINED")
        self.assertEqual(preview["approval"], proposed["approval"])
        result = self.c.track.next(self.product, choices, reviewed=proposed["approval"],
            setup_approval=proposed["setup_approval"], authorized=True)
        self.assertEqual(result["status"], "NEXT_ENROLLED_SCOPE_REVIEW_REQUIRED")
        from adp.personal_storage import load_state
        child = load_state(choices.directory)
        child_state = child.memory().inspect()
        self.assertEqual(child.plan, retained["view"]["plan"])
        again = self.c.track.next(self.product, choices, reviewed=proposed["approval"],
            setup_approval=proposed["setup_approval"], authorized=True)
        self.assertEqual(again["directory"], result["directory"])
        self.assertEqual(child.memory().inspect(), child_state)
        self.assertEqual(read_private(self.personal.state / "next-intent.json"), retained)
        self.assertEqual(len(self.c.track.links()), 2)

    def test_changed_base_original_and_expiry_refuse_new_scope_before_owner_release(self):
        self.enroll_track()
        accepted = self.merged()
        self.synchronize(accepted["merge"])
        choices = self.next_choices(2)
        proposed = self.c.track.next_preview(self.product, choices)
        before = self.c.memory.inspect()
        changed = gv(self.store, "commit-tree", gv(self.store, "rev-parse", accepted["merge"] + "^{tree}"),
            "-p", accepted["merge"], "-m", "Synthetic native base drift")
        gv(self.store, "update-ref", "refs/heads/trunk", changed, accepted["merge"])
        with self.assertRaises(ADPError):
            self.c.track.next(self.product, choices, reviewed=proposed["approval"],
                setup_approval=proposed["setup_approval"], authorized=True)
        gv(self.store, "update-ref", "refs/heads/trunk", accepted["merge"], changed)
        original = self.transport.api.responses[self.prefix + "/issues/2"].body
        body = original["body"]
        original["body"] = "Unauthorized expanded scope"
        with self.assertRaises(ADPError):
            self.c.track.next(self.product, choices, reviewed=proposed["approval"],
                setup_approval=proposed["setup_approval"], authorized=True)
        original["body"] = body
        self.now = proposed["result"]["plan"]["window"]["expires_at"]
        with self.assertRaises(ADPError):
            self.c.track.next(self.product, choices, reviewed=proposed["approval"],
                setup_approval=proposed["setup_approval"], authorized=True)
        self.assertEqual(self.c.memory.inspect(), before)
        self.assertFalse((self.personal.state / "next-intent.json").exists())
        self.assertFalse(choices.directory.exists())
        self.assertEqual(len(self.c.track.links()), 1)
