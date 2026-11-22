"""Physical Git binding regressions, disposable repositories and no workers."""
import shutil
from pathlib import Path
from unittest.mock import patch

from adp.config import Config
from adp.execution_ports import GitExecutionPort
from adp.git import git, value
from adp.personal_git import administration
from personal_fixtures import PersonalFixture
from test_config import run


class PersonalGitTests(PersonalFixture):
    def test_bound_local_cas_cannot_follow_a_redirect_at_the_write_boundary(self):
        checkout = self.base / "linked-source"
        run(self.a, "worktree", "add", "-b", "linked", str(checkout))
        original = administration(checkout)
        copied = self.base / "copied-administration"
        shutil.copytree(self.a / ".git", copied)
        suffix = Path(original["directory"]["path"]).relative_to(self.a / ".git")
        foreign = copied / suffix
        cfg = Config.discover(checkout, remote="forge", repository_id="17")
        port = GitExecutionPort(cfg, bound_git_directory=Path(original["directory"]["path"]))
        sha = value(checkout, "rev-parse", "HEAD")
        def redirected(root, *args, **kwargs):
            if "update-ref" in args:
                (checkout / ".git").write_text("gitdir: " + str(foreign) + "\n")
            return git(root, *args, **kwargs)
        # Simulate redirect AFTER the final identity check, immediately before
        # exec. Explicit --git-dir keeps the actual CAS in the original admin.
        with patch("adp.execution_ports.git", side_effect=redirected):
            port._git("update-ref", "refs/heads/bound-only", sha, "0" * len(sha))
        self.assertEqual(value(self.a, "rev-parse", "refs/heads/bound-only"), sha)
        self.assertEqual(value(copied, "for-each-ref", "--format=%(objectname)", "refs/heads/bound-only"), "")

