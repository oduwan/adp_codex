"""Configuration and observational Git regression tests, using local remotes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from adp.config import Config
from adp.errors import ADPError, ConfigurationError
from adp.git import author


def run(path: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.org",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.org")
    return subprocess.check_output(["git", "-C", str(path), *args], env=env,
                                   stderr=subprocess.PIPE).decode().strip()


def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for path in root.rglob("*"):
        info = path.lstat()
        if path.is_symlink():
            content = "link:" + os.readlink(path)
        elif path.is_file():
            content = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            content = "directory"
        result[str(path.relative_to(root))] = f"{info.st_mode}:{info.st_mtime_ns}:{content}"
    return result


class GitFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="adp-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / "remote.git"
        self.remote.mkdir()
        run(self.remote, "init", "--bare", "--initial-branch=trunk")
        self.a = self.base / "a"
        self.a.mkdir()
        run(self.a, "init", "--initial-branch=trunk")
        run(self.a, "config", "user.name", "Fixture")
        run(self.a, "config", "user.email", "fixture@example.org")
        (self.a / "product").write_text("unchanged\n")
        run(self.a, "add", "product")
        run(self.a, "commit", "-m", "fixture")
        run(self.a, "remote", "add", "upstream", str(self.remote))
        run(self.a, "push", "upstream", "trunk")
        self.b = self.base / "b"
        run(self.base, "clone", "--origin", "mirror", str(self.remote), str(self.b))
        run(self.b, "config", "user.name", "Fixture")
        run(self.b, "config", "user.email", "fixture@example.org")

    def config(self, root: Path | None = None, **kw: object) -> Config:
        root = root or self.a
        return Config.discover(root, branch="coordination/current",
                               storage=self.base / (root.name + "-memory"), **kw)


class ConfigurationTests(GitFixture):
    def test_identity_and_explicit_selection(self) -> None:
        self.assertEqual(self.config().identity, self.config(self.b).identity)
        self.assertEqual(self.config().remote, "upstream")
        run(self.a, "remote", "add", "second", str(self.remote))
        with self.assertRaisesRegex(ConfigurationError, "Select --remote"):
            self.config()
        self.assertEqual(self.config(remote="second").remote, "second")

    def test_discovery_and_remote_inspection_do_not_write(self) -> None:
        before = snapshot(self.base)
        self.assertIsNone(self.config().remote_head())
        self.assertEqual(before, snapshot(self.base))

    def test_config_discovery_and_override(self) -> None:
        (self.a / ".adp.json").write_text(json.dumps({"schema_version": 1,
            "remote": "upstream", "repository_id": "forge:project/opaque",
            "memory_branch": "custom/memory", "storage": "../memory"}))
        config = Config.discover(self.a)
        self.assertEqual(config.identity, "forge:project/opaque")
        self.assertEqual(config.storage, self.base / "memory")
        self.assertEqual(Config.discover(self.a, branch="another").branch, "another")

    def test_malformed_config_and_unsafe_paths(self) -> None:
        path = self.a / ".adp.json"
        for payload in ('{"schema_version":1,"schema_version":1}', '[]',
                        '{"schema_version":true}', '{"unknown":1}', '{"remote":NaN}'):
            path.write_text(payload)
            with self.assertRaises(ADPError):
                self.config()
        path.unlink()
        (self.base / "link").symlink_to(self.base, target_is_directory=True)
        for storage in (self.a, self.a / "local", self.base / "link" / "mem", self.base):
            with self.assertRaises(ADPError):
                Config.discover(self.a, branch="memory", storage=storage)

    def test_unsafe_identity_and_remote(self) -> None:
        run(self.a, "config", "user.email", "root@host.local")
        with self.assertRaises(ConfigurationError):
            author(self.a)
        run(self.a, "remote", "set-url", "upstream", "https://secret:token@example.org/repo")
        with self.assertRaises(ConfigurationError):
            self.config()


if __name__ == "__main__":
    unittest.main()
