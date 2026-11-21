"""Focused M9-A installer checks, separate from frozen qualification inventories."""
from pathlib import Path
import argparse
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import install_adp as installer


REVISION = "1" * 40
DIGEST = "2" * 64
OLD = "adp-managed-" + "1" * 32
NEW = "adp-managed-" + "2" * 32
PROJECT = b"""
[project]
name = "adp-codex"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
[project.scripts]
adp = "adp.cli:main"
"""
MANIFEST = {"name": "adp-codex", "version": "0.1.0",
            "repository": "https://github.com/oduwan/adp_codex"}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.codex = Mock(home=self.home / ".codex", cwd=self.home)
        self.codex.observe.return_value = (False, False, False)
        self.install = installer.Installation(self.home / "managed", self.codex)
        self.archive = self.home / "source.tar"
        self.receipt = self.source().receipt

    def source(self, *, manifest=MANIFEST, revision=REVISION, extra=None):
        contents = {"pyproject.toml": PROJECT, "plugin.json": json.dumps(manifest).encode(),
                    "adp/__init__.py": b"", "adp/cli.py": b"# source",
                    installer.SKILL: b"# ADP", "docs/ARCHITECTURE.md": b"# Architecture"}
        contents.update(extra or {})
        with tarfile.open(self.archive, "w", format=tarfile.PAX_FORMAT,
                          pax_headers={"comment": revision}) as tar:
            for name, body in contents.items():
                info = tarfile.TarInfo(name)
                info.size = len(body)
                tar.addfile(info, io.BytesIO(body))
        return installer.Source.read(self.archive, REVISION, installer.digest(self.archive.read_bytes()))

    def test_source_binds_commit_digest_and_package_identity(self):
        with self.assertRaisesRegex(installer.Refusal, "SHA-256 mismatch"):
            installer.Source.read(self.archive, REVISION, DIGEST)
        with self.assertRaisesRegex(installer.Refusal, "Git commit"):
            self.source(revision="3" * 40)
        with self.assertRaisesRegex(installer.Refusal, "package version"):
            self.source(manifest=dict(MANIFEST, version="0.2.0"))

    def test_missing_archive_and_traversal_refused(self):
        with self.assertRaisesRegex(installer.Refusal, "Cannot read the local archive"):
            installer.Source.read(self.home / "missing.tar", REVISION, DIGEST)
        with self.assertRaisesRegex(installer.Refusal, "unsupported or duplicate path"):
            self.source(extra={"../outside": b"unexpected"})
        self.assertFalse((self.home.parent / "outside").exists())

    def test_unsupported_python_and_host(self):
        args = argparse.Namespace(action="verify")
        with patch.object(sys, "version_info", (3, 10)):
            with self.assertRaisesRegex(installer.Refusal, "Python 3.11"):
                installer.run(args)
        with patch.object(sys, "platform", "darwin"):
            with self.assertRaisesRegex(installer.Refusal, "Linux and WSL2"):
                installer.run(args)

    def test_unwritable_and_symlink_directories_are_refused(self):
        with patch.object(os, "access", return_value=False):
            with self.assertRaisesRegex(installer.Refusal, "not writable"):
                installer.safe_directory(self.home / "absent", os.getuid())
        link = self.home / "link"
        link.symlink_to(self.home)
        with self.assertRaisesRegex(installer.Refusal, "symbolic links"):
            installer.safe_directory(link / "absent", os.getuid())

    def test_missing_or_changed_codex_command_surface(self):
        codex = installer.Codex("/bin/false", self.codex.home, self.home)
        with self.assertRaisesRegex(installer.Refusal, "capability probe"):
            codex.probe()
        with patch.object(installer, "command", return_value=b"Changed command --json"):
            with self.assertRaisesRegex(installer.Refusal, "Unsupported Codex"):
                codex.probe()

    def test_missing_github_auth_blocks_before_installer_mutation(self):
        args = argparse.Namespace(action="install", source=self.archive, revision=REVISION,
                                  sha256=self.receipt["sha256"], dry_run=False, yes=True)

        def command(argv, cwd, label, **kwargs):
            if "api" in argv:
                raise installer.Refusal(label)
            return b""

        with (patch.dict(os.environ, {"HOME": str(self.home), "CODEX_HOME": str(self.codex.home)}),
              patch.object(os, "getuid", return_value=1234),
              patch.object(os, "geteuid", return_value=1234),
              patch.object(os, "umask"),
              patch.object(installer, "safe_directory"),
              patch.object(installer.shutil, "which", return_value="/bin/false"),
              patch.object(installer, "Codex", return_value=self.codex),
              patch.object(installer, "command", side_effect=command)):
            self.codex.cli.return_value = {"installed": []}
            with self.assertRaisesRegex(installer.Refusal, "GitHub authentication"):
                installer.run(args)
        self.assertFalse((self.home / installer.MANAGED).exists())
        self.codex.skills.assert_not_called()

    def active(self):
        self.install.root.mkdir(mode=0o700)
        (self.install.root / OLD).mkdir(mode=0o700)
        self.install.save({OLD: self.receipt})
        self.install.link.symlink_to(OLD)
        return self.install.load()

    def test_matching_verified_install_is_idempotent(self):
        records, current = self.active()
        with (patch.object(self.install, "report", return_value=True),
              patch.object(self.install, "stage") as stage):
            self.install.apply("install", records, current, self.source())
        self.assertEqual(self.install.load(), ({OLD: self.receipt}, OLD))
        stage.assert_not_called()

    def test_failed_build_download_keeps_existing_installation(self):
        records, current = self.active()
        # Keep an independently managed sentinel outside the installer-owned generation.
        protected = self.home / "operator-config"
        protected.write_text("existing operator state")
        failure = installer.Refusal("Build dependency download failed")
        with (patch.object(self.install, "stage", side_effect=failure),
              patch.object(self.install, "report", return_value=False),
              patch.object(installer.uuid, "uuid4", return_value=Mock(hex="2" * 32))):
            with self.assertRaisesRegex(installer.Refusal, "download failed"):
                self.install.apply("upgrade", records, current, self.source())
        self.assertEqual(self.install.load(), ({OLD: self.receipt}, OLD))
        self.assertEqual(protected.read_text(), "existing operator state")

    def test_failed_plugin_downstream_cleanup_retains_receipt_for_retry(self):
        records, current = self.active()
        self.install.link.unlink()
        self.install.save({OLD: self.receipt, NEW: self.receipt})
        (self.install.root / NEW).mkdir(mode=0o700)
        records, current = self.install.load()
        self.codex.observe.return_value = (True, True, True)
        self.codex.cli.side_effect = installer.Refusal("Codex temporarily unavailable")
        with self.assertRaisesRegex(installer.Refusal, "temporarily unavailable"):
            self.install.apply("uninstall", records, current, None)
        self.assertEqual(set(self.install.load()[0]), {OLD, NEW})
        self.codex.observe.return_value = (False, False, False)
        self.codex.cli.side_effect = None
        self.install.apply("uninstall", *self.install.load(), None)
        self.assertEqual(self.install.load(), ({}, None))

    def test_uninstall_refuses_repointed_marketplace(self):
        records, current = self.active()
        codex = installer.Codex("/unused", self.codex.home, self.home)
        with patch.object(codex, "cli", return_value={"marketplaces": [
                {"name": OLD, "root": str(self.home / "someone-elses-marketplace")}]}):
            with self.assertRaisesRegex(installer.Refusal, "points elsewhere"):
                codex.observe(OLD, self.install.catalog(OLD), records[current]["version"])
        self.assertTrue((self.install.root / OLD).is_dir())

    def test_verify_requires_receipt_to_own_launcher(self):
        self.install.root.mkdir(mode=0o700)
        self.install.link.symlink_to(self.home / "outside")
        with self.assertRaisesRegex(installer.Refusal, "Missing ADP ownership receipt"):
            self.install.load()


if __name__ == "__main__":
    unittest.main()
