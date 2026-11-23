"""Personal-only public operands, without workers or network."""
import contextlib
import io
import unittest
from adp.cli import parser
from adp.codex_cli import ACTIONS


class PersonalProductCLITests(unittest.TestCase):
    def arguments(self, action):
        return [action, "--repo", "/owned/project", "--remote", "origin", "--directory", "/owned/private"]

    def test_both_operator_families_have_separate_pr_and_merge_approvals(self):
        extra = ["--title", "Outcome", "--body", "Refs #1", "--reviewed", "token"]
        a = parser().parse_args(["personal", *self.arguments("pr-create"), *extra])
        b = parser().parse_args(["codex", *self.arguments("pr-create"), *extra, "--personal"])
        self.assertEqual(a.enroll_command, b.enroll_command)
        self.assertFalse(a.authorize_pr)
        m = parser().parse_args(["personal", *self.arguments("merge"), "--reviewed", "other-token"])
        self.assertFalse(m.delegate_merge)
        self.assertFalse(m.authorize_merge)
        self.assertFalse(m.accept_head_atomic_base_observed)
        self.assertNotIn("merge", ACTIONS)

    def test_codex_product_verbs_cannot_select_signed_mode_implicitly(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(["codex", *self.arguments("merge-preview")])
        a = parser().parse_args(["personal", *self.arguments("ci-preview")])
        self.assertFalse(a.accept_native_job_records)
        self.assertFalse(a.confirm_no_required_checks)
