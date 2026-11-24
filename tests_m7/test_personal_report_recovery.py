"""Uncertain comment delivery cannot mint another write or next window."""
from adp.errors import ADPError
from adp.personal_report import PersonalReport
from personal_track_fixtures import TrackFixture


class PersonalReportRecoveryTests(TrackFixture):
    def test_lost_before_delivery_stays_unknown_and_blocks_next_without_blind_post(self):
        self.enroll_track()
        self.merged()
        report = PersonalReport(self.c, transport=self.http)
        self.http.authorize_write = report.write_authorized
        proposed = report.report_preview()
        self.http.report_loss = "before"
        with self.assertRaises(ADPError):
            report.report(reviewed=proposed["approval"], authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True)
        pending = self.c.memory.inspect()
        self.assertEqual(len(self.all_comments), 0)
        with self.assertRaises(ADPError):
            report.report(reviewed=proposed["approval"], authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True)
        self.assertEqual(self.c.memory.inspect(), pending)
        self.assertEqual(len([r for r in self.http.effects if r[1].endswith("/comments")]), 1)
        with self.assertRaises(ADPError):
            self.c.track.status(transport=self.http)
        _, token = self.c.invocation("handoff")
        with self.assertRaises(ADPError):
            self.c.run(reviewed=token, authorized=True, operation="handoff")
        self.assertTrue(self.c.memory.inspect()["local_owner"])
