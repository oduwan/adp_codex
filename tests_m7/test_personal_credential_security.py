"""Deterministic credential-source security controls; no real gh process."""
import io
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp import personal_network_child as child


class PersonalCredentialSecurityTests(unittest.TestCase):
    def test_unsafe_ancestry_refuses_and_safe_directory_identities_are_pinned(self):
        safe = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=1001, st_dev=5, st_ino=19)
        with patch.object(child.os, "getuid", return_value=1001), patch.object(Path, "lstat", return_value=safe):
            observed = child.trusted_ancestry(Path("/owned/config/gh"), directory=True)
        self.assertEqual([row["path"] for row in observed], ["/owned/config/gh", "/owned/config", "/owned", "/"])
        self.assertTrue(all(row["device"] == 5 and row["inode"] == 19 for row in observed))
        for mode, uid in ((stat.S_IFDIR | 0o777, 1001), (stat.S_IFDIR | 0o1777, 0),
                          (stat.S_IFDIR | 0o755, 1002), (stat.S_IFLNK | 0o755, 1001)):
            unsafe = SimpleNamespace(st_mode=mode, st_uid=uid, st_dev=5, st_ino=20)
            with self.subTest(mode=mode, uid=uid), patch.object(child.os, "getuid", return_value=1001), \
                 patch.object(Path, "lstat", side_effect=(safe, unsafe)), self.assertRaises(ValueError):
                child.trusted_ancestry(Path("/owned/config/gh"))

    def test_unsupported_no_refresh_cli_never_falls_back_or_uses_partial_token(self):
        actor = {"gh": "/trusted/gh", "config": "/owned/config"}
        failed = SimpleNamespace(stdout=io.BytesIO(b"PRIVATE_PARTIAL_TOKEN\n"), wait=lambda: 1)
        with patch.object(child, "context", return_value=actor), \
             patch.object(child.pwd, "getpwuid", return_value=SimpleNamespace(pw_dir="/owned")), \
             patch.object(child.subprocess, "Popen", return_value=failed) as launch, self.assertRaises(ValueError):
            child.credential({"kind": "credential", "context": actor})
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0], ("/trusted/gh", "auth", "token", "--hostname", "github.com", "--no-refresh"))
