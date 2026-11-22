"""The CLI and packaged Skill share one explicit personal backend."""
from adp.cli import parser
from adp.personal_cli import run
from personal_fixtures import PersonalFixture
from test_config import snapshot


class PersonalCLITests(PersonalFixture):
    def arguments(self, prefix, action, extra=()):
        return parser().parse_args([*prefix, action, "--repo", str(self.a), "--remote", "forge", *extra])

    def test_managed_and_codex_personal_plan_are_the_same_protocol(self):
        before = snapshot(self.base)
        extra = ("--directory", str(self.directory), "--issue", "1", "--path", "product", "--feature-branch", "work/issue-1")
        direct, status = run(self.arguments(("personal",), "plan", extra), transport=self.transport, clock=lambda: self.now)
        self.assertEqual(status, 0)
        # Plan nonces intentionally differ; replay the exact approved token.
        args = self.arguments(("codex",), "apply", (*extra, "--personal", "--approve", direct["approval"]))
        declined, status = run(args, transport=self.transport, clock=lambda: self.now)
        self.assertEqual(declined["backend"], "PERSONAL")
        self.assertEqual(declined["plan"], direct["plan"])
        self.assertEqual(status, 4)
        self.assertEqual(snapshot(self.base), before)
        args.authorize_memory_write = True
        applied, status = run(args, transport=self.transport, clock=lambda: self.now)
        self.assertEqual((applied["status"], status), ("ENROLLED", 0))
        status_args = self.arguments(("codex",), "status", ("--personal", "--directory", str(self.directory)))
        before = snapshot(self.base)
        result, status = run(status_args, clock=lambda: self.now)
        self.assertEqual(result["result"]["status"], "ENROLLED")
        self.assertEqual(status, 0)
        self.assertEqual(snapshot(self.base), before)

    def test_signed_personal_mixing_and_missing_scope_refuse_read_only(self):
        before = snapshot(self.base)
        args = self.arguments(("codex",), "plan", ("--personal", "--operator-trust", str(self.base)))
        result, status = run(args, transport=self.transport, clock=lambda: self.now)
        self.assertEqual(status, 4)
        self.assertEqual(result["status"], "BLOCKED")
        args = self.arguments(("personal",), "plan")
        result, status = run(args, transport=self.transport, clock=lambda: self.now)
        self.assertEqual(result["status"], "INPUT_REQUIRED")
        self.assertEqual({q["id"] for q in result["questions"]}, {"issue", "paths"})
        self.assertEqual(snapshot(self.base), before)
