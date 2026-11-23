"""Focused public-command routing; no worker, credential or forge execution."""
import contextlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.cli import main, parser
from adp.errors import ADPError
from adp.personal_cli import run


class PersonalPublicationCLITests(unittest.TestCase):
    def arguments(self, family, action, extra=()):
        return [family, action, "--repo", "/owned/product", "--remote", "origin",
                "--directory", "/owned/private-state", *extra]

    def test_publication_commands_are_explicitly_personal_and_separately_approved(self):
        for action in ("publication-preview", "publish", "publication-status"):
            extra = ("--reviewed", "publish1.synthetic") if action == "publish" else ()
            direct = parser().parse_args(self.arguments("personal", action, extra))
            codex = parser().parse_args(self.arguments("codex", action, (*extra, "--personal")))
            self.assertEqual(direct.enroll_command, codex.enroll_command)
            self.assertTrue(codex.personal)
            if action == "publish":
                for flag in ("authorize_publication", "assume_administrative_quiescence", "confirm_project_publication_rules"):
                    self.assertFalse(getattr(direct, flag))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser().parse_args(self.arguments("codex", action, extra))
        # No additional rights appear in the unchanged signed capability list.
        from adp.codex_cli import ACTIONS
        self.assertNotIn("publish", ACTIONS)
        capabilities, code = run(SimpleNamespace(enroll_command="capabilities"))
        self.assertEqual(code, 0)
        self.assertIn("publish", capabilities["result"]["actions"])
        self.assertEqual(capabilities["result"]["external_operations"], "NOT_DELEGATED")

    def test_both_cli_families_dispatch_to_the_same_existing_personal_port(self):
        for family, extra in (("personal", ()), ("codex", ("--personal",))):
            report = {"status": "PUBLICATION_PROPOSED", "runtime_qualification": "NOTRUN"}
            output = io.StringIO()
            with patch("adp.personal_cli.run", return_value=(report, 0)) as dispatch, contextlib.redirect_stdout(output):
                self.assertEqual(main(self.arguments(family, "publication-preview", extra)), 0)
            self.assertEqual(dispatch.call_args.args[0].enroll_command, "publication-preview")
            self.assertEqual(json.loads(output.getvalue()), report)

    def test_raw_credential_or_transport_errors_are_not_in_operator_output(self):
        args = parser().parse_args(self.arguments("personal", "publication-preview"))
        secret = "PRIVATE_CREDENTIAL_AND_HOST_FAILURE"
        with patch("adp.personal_cli.retained", return_value=object()), \
             patch("adp.personal_cli.PersonalCoordinator"), \
             patch("adp.personal_publication.PersonalPublication", side_effect=ADPError(secret)):
            report, code = run(args)
        self.assertEqual(code, 4)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertNotIn(secret, json.dumps(report))
        self.assertEqual(report["runtime_qualification"], "NOTRUN")
