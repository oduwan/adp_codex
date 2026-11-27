"""Known domain facts get fixed safe wording; missing historical causes stay unknown."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from adp.cli import parser
from adp.errors import ADPError
from adp.guard_types import Action, ActionKind
from adp.personal_cli import run
from adp.personal_runner import PersonalCoordinator
from adp.personal_storage import PersonalBlocked
import test_guard as fixtures
from test_config import snapshot


class RefusalDiagnosticsTests(fixtures.GuardFixture):
    def command(self, error):
        with TemporaryDirectory(prefix="adp-refusal-") as directory:
            root = Path(directory)
            args = parser().parse_args(["personal", "status", "--repo", str(root), "--remote", "forge", "--directory", str(root / "private")])
            before = snapshot(root)
            with patch("adp.personal_cli.retained", side_effect=error):
                report, code = run(args, transport=object())
            self.assertEqual(code, 4)
            self.assertEqual(report["mode"], "READ_ONLY")
            self.assertEqual(snapshot(root), before)
            public = json.dumps(report)
            self.assertNotIn("PRIVATE_HOST", public)
            self.assertNotIn("ghp_SECRET", public)
            self.assertNotIn(directory, public)
            return report["blockers"][0]

    def refusal(self):
        c = PersonalCoordinator.__new__(PersonalCoordinator)
        c.guard, c.task_id = self.guard, "task-A"
        with self.assertRaises(PersonalBlocked) as caught:c.allowed(self.identifier)
        return caught.exception

    def test_known_active_and_forensic_decisions_have_safe_operation_and_reason(self):
        permit = self.guard.begin("task-A", self.identifier, Action("author", ActionKind.CHECK, "one"))
        blocker = self.command(self.refusal())
        self.assertEqual(blocker["subreason"], "ACTIVE_RESERVATION")
        self.assertEqual(blocker["operation"], "status")
        self.guard.observe("task-A", self.identifier, permit, fixtures.Observation(fixtures.Outcome.FAIL, ("fixture:failed",), tuple(self.item()["unresolved"])))
        self.run_attempt(); self.run_attempt()
        blocker = self.command(self.refusal())
        self.assertEqual(blocker["code"], "PERSONAL_FORENSIC_RECOVERY_UNSUPPORTED")
        self.assertEqual(blocker["subreason"], "FORENSIC_REQUIRED")

    def test_expired_original_reservation_reports_safety_stop(self):
        permit = self.guard.begin("task-A", self.identifier, Action("author", ActionKind.CHECK, "one"))
        self.now += 301
        self.assertEqual(self.command(self.refusal())["subreason"], "EXPIRED_RESERVATION")
        self.guard.observe("task-A", self.identifier, permit,
            fixtures.Observation(fixtures.Outcome.UNKNOWN, ("fixture:overdue",), tuple(self.item()["unresolved"])))
        self.assertEqual(self.command(self.refusal())["subreason"], "STOP_UNSAFE")

    def test_known_historical_and_legacy_refusals_do_not_disclose_arbitrary_text(self):
        for reason, subreason in (("PERSONAL_HISTORY_GUARD_UNSETTLED", "UNSETTLED_GUARD"),
                ("LEGACY_DEVELOPMENT_OBSERVATION_ONLY", "LEGACY_PROTOCOL")):
            with self.subTest(subreason=subreason):
                blocker = self.command(PersonalBlocked(reason, "PRIVATE_HOST /private ghp_SECRET", subreason=subreason))
                self.assertEqual((blocker["code"], blocker["subreason"]), (reason, subreason))

    def test_unexpected_exceptions_keep_unknown_cause_and_generic_safe_action(self):
        for error in (ADPError("PRIVATE_HOST ghp_SECRET /private/receipt"), OSError("PRIVATE_HOST ghp_SECRET")):
            blocker = self.command(error)
            self.assertEqual(blocker["code"], "PERSONAL_STATE_OR_AUTHORITY_UNVERIFIED")
            self.assertEqual(blocker["subreason"], "UNKNOWN")
