"""Independent-review regressions: normal-user executable and honest M2 stop."""
import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adp.guard_types import DecisionKind
from adp.personal_network_child import executable_identity
from personal_publication_fixtures import PublicationFixture


class PersonalExecutableSecurityTests(unittest.TestCase):
    def test_privilege_changing_gh_modes_and_file_capabilities_are_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gh"
            path.write_bytes(b"synthetic executable identity; never executed")
            for mode in (0o4755, 0o2755, 0o6755):
                path.chmod(mode)
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    executable_identity(path)
            path.chmod(0o755)
            with patch("adp.personal_network_child.os.getxattr", return_value=b"file-capabilities"), self.assertRaises(ValueError):
                executable_identity(path)
            with patch("adp.personal_network_child.os.getxattr", side_effect=OSError(errno.EOPNOTSUPP, "unsupported")), self.assertRaises(ValueError):
                executable_identity(path)
            with patch("adp.personal_network_child.os.getxattr", side_effect=OSError(errno.ENODATA, "absent")):
                self.assertEqual(executable_identity(path)["mode"], 0o755)


class PersonalGuardSettlementSecurityTests(PublicationFixture):
    def test_present_ref_preserves_and_reports_terminal_guard_accounting(self):
        pub = self.ready()
        proposal = pub.preview()
        submit = pub.port.submit
        def expired_after_actual_cas(*args, **kwargs):
            result = submit(*args, **kwargs)
            self.assertEqual(result.status, "PRESENT")
            row = pub.record()
            active = pub.guard._snapshot(self.c.task_id, row["requirement"])[2]["active"]
            self.now = active["deadline"] + 1
            return result
        with patch.object(pub.port, "submit", side_effect=expired_after_actual_cas):
            result = self.publish(proposal["approval"])
        self.assertEqual(result["status"], "PUBLISHED_GUARD_STOPPED")
        self.assertEqual(result["progress_guard"], DecisionKind.STOP_UNSAFE)
        row = pub.record()
        guard = pub.guard._snapshot(self.c.task_id, row["requirement"])[2]
        self.assertEqual(guard["mode"], "unsafe")
        self.assertIsNone(guard["last"]["observation"]["progress"])
        self.assertEqual(guard["unresolved"], ["published"])
        self.assertEqual(pub.journal.inspect()["state"]["execution"]["actions"][row["action_id"]]["status"], "OBSERVED")
        self.assertEqual(pub.status()["status"], "PUBLICATION_PRESENT_GUARD_STOPPED")
        self.assertEqual(sum(kind == "ref" for kind, _ in self.http.server.mutations), 1)
