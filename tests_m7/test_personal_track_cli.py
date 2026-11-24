"""Operator protocol is explicit in both supported CLI spellings."""
import argparse
import contextlib
import io
import unittest

from adp.cli import parser
from adp.personal_cli import run as personal_run
from personal_track_fixtures import TrackFixture
from test_config import snapshot


class PersonalTrackCLIContractTests(unittest.TestCase):
    def test_capabilities_and_both_cli_spellings_do_not_delegate_effects(self):
        args = parser().parse_args(["personal", "capabilities"])
        report, code = personal_run(args)
        self.assertEqual(code, 0)
        self.assertEqual(report["mode"], "READ_ONLY")
        self.assertEqual(report["result"]["external_operations"], "NOT_DELEGATED")
        for action in ("track-preview", "track-status", "completion-preview", "report-preview", "report-status", "next-preview"):
            self.assertIn(action, report["result"]["actions"])
        for root, extra in (("personal", []), ("codex", ["--personal"])):
            args = parser().parse_args([root, "next-preview", *extra, "--repo", "/owned/source", "--remote", "origin",
                "--directory", "/owned/private", "--next-issue", "2", "--path", "product"])
            self.assertEqual(args.enroll_command, "next-preview")
            self.assertEqual(args.next_issue, 2)
            self.assertFalse(getattr(args, "authorize_memory_write", False))

    def test_next_and_report_require_separate_review_tokens_and_next_setup_token(self):
        common = ["--repo", "/owned/source", "--remote", "origin", "--directory", "/owned/private"]
        with contextlib.redirect_stderr(io.StringIO()):
            for words in (["personal", "report", *common, "--authorize-report"],
                    ["personal", "next", *common, "--next-issue", "2", "--path", "product", "--reviewed", "some-token"],
                    ["codex", "next-preview", *common, "--next-issue", "2", "--path", "product"]):
                with self.subTest(command=words[1]), self.assertRaises(SystemExit):
                    parser().parse_args(words)


class PersonalTrackCLIFixtureTests(TrackFixture):
    def test_cli_track_preview_and_declined_enrollment_preserve_source_and_memory(self):
        self.enroll()
        common = ["--repo", str(self.a), "--remote", "forge", "--directory", str(self.personal.directory),
            "--track-issue", "1", "--track-issue", "2", "--track-issue", "3"]
        before = snapshot(self.base)
        proposed, code = personal_run(parser().parse_args(["personal", "track-preview", *common]),
            transport=self.transport, runtime=self.runtime, clock=lambda: self.now)
        self.assertEqual(code, 0)
        self.assertEqual(proposed["status"], "TRACK_PROPOSED")
        self.assertNotIn("snapshot", proposed["result"])
        self.assertEqual(snapshot(self.base), before)
        declined, code = personal_run(parser().parse_args(["personal", "track-enroll", *common,
            "--reviewed", proposed["approval"]]), transport=self.transport, runtime=self.runtime, clock=lambda: self.now)
        self.assertEqual(code, 4)
        self.assertEqual(declined["status"], "BLOCKED")
        self.assertEqual(snapshot(self.base), before)
        self.assertEqual(self.requests, [])
