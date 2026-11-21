"""Focused M9-A installer checks, separate from frozen qualification inventories."""
from pathlib import Path
import argparse
import io
import json
import os
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
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
        self.codex.observe.return_value = installer.PluginState(False, False, False, False)
        self.install = installer.Installation(self.home / "managed", self.codex)
        self.archive = self.home / "source.tar"
        self.receipt = self.source().receipt

    def source(self, *, manifest=MANIFEST, revision=REVISION, extra=None):
        contents = {"pyproject.toml": PROJECT, "plugin.json": json.dumps(manifest).encode(),
                    "adp/__init__.py": b"", "adp/__main__.py": b"from .cli import main", "adp/cli.py": b"# source",
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
            self.codex.independent_plugins.return_value = []
            with self.assertRaisesRegex(installer.Refusal, "GitHub authentication"):
                installer.run(args)
        self.assertFalse((self.home / installer.MANAGED).exists())
        self.codex.probe_lifecycle.assert_not_called()

    def test_concurrent_conflicting_plugin_is_detected_after_confirmation(self):
        args = argparse.Namespace(action="install", source=self.archive, revision=REVISION,
                                  sha256=self.receipt["sha256"], dry_run=False, yes=True)
        with (patch.dict(os.environ, {"HOME": str(self.home), "CODEX_HOME": str(self.codex.home)}),
              patch.object(os, "getuid", return_value=1234),
              patch.object(os, "geteuid", return_value=1234),
              patch.object(os, "umask"),
              patch.object(installer, "safe_directory"),
              patch.object(installer.shutil, "which", return_value="/bin/false"),
              patch.object(installer, "Codex", return_value=self.codex),
              patch.object(installer, "command", return_value=b"managed_enterprise\n"),
              patch.object(installer.Installation, "apply") as apply):
            self.codex.independent_plugins.side_effect = [[], [{"enabled": True}]]
            with self.assertRaisesRegex(installer.Refusal, "became enabled"):
                installer.run(args)
        self.codex.probe_lifecycle.assert_called_once_with()
        self.codex.cli.assert_not_called()
        apply.assert_not_called()

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
        self.codex.observe.return_value = installer.PluginState(True, True, True, True)
        self.codex.remove.side_effect = installer.Refusal("Codex temporarily unavailable")
        with self.assertRaisesRegex(installer.Refusal, "temporarily unavailable"):
            self.install.apply("uninstall", records, current, None)
        self.assertEqual(set(self.install.load()[0]), {OLD, NEW})
        self.codex.observe.return_value = installer.PluginState(False, False, False, False)
        self.codex.remove.side_effect = None
        self.install.apply("uninstall", *self.install.load(), None)
        self.assertEqual(self.install.load(), ({}, None))

    def test_uninstall_refuses_repointed_marketplace(self):
        records, current = self.active()
        codex = installer.Codex("/unused", self.codex.home, self.home)
        with patch.object(codex, "config", return_value={"marketplaces": {
                OLD: {"source_type": "local", "source": str(self.home / "foreign")}}}):
            with self.assertRaisesRegex(installer.Refusal, "points elsewhere"):
                codex.observe(OLD, self.install.catalog(OLD))
        self.assertTrue((self.install.root / OLD).is_dir())

    def test_disabled_plugins_refuse_install_capability(self):
        codex = installer.Codex("/unused", self.codex.home, self.home)
        with patch.object(installer, "command", return_value=b"plugins stable false\n"):
            with self.assertRaisesRegex(installer.Refusal, "plugins are disabled"):
                codex.require_plugins_enabled()

    def test_cleanup_reconciles_half_installed_plugins_with_missing_catalog(self):
        for configured, cached in ((False, True), (True, False)):
            with self.subTest(configured=configured, cached=cached):
                self.install.root.mkdir(mode=0o700, exist_ok=True)
                records = {OLD: self.receipt}
                self.install.save(records)
                catalog = self.install.catalog(OLD)
                codex = installer.Codex("/unused", self.codex.home, self.home)
                self.install.codex = codex
                plugin_dir = codex.home / "plugins/cache" / OLD / installer.NAME
                if cached:
                    plugin_dir.mkdir(parents=True)
                selector = f"{installer.NAME}@{OLD}"
                config = {"marketplaces": {OLD: {"source_type": "local", "source": str(catalog)}},
                          "plugins": {selector: {"enabled": True}} if configured else {}}

                def remove(*args):
                    if args == ("remove", selector):
                        config["plugins"].pop(selector, None)
                        if cached:
                            plugin_dir.rmdir()
                        return {"pluginId": selector}
                    elif args == ("marketplace", "remove", OLD):
                        del config["marketplaces"][OLD]
                        return {"marketplaceName": OLD}
                    else:
                        self.fail(f"Unexpected Codex command {args}")

                with (patch.object(codex, "config", return_value=config),
                      patch.object(codex, "cli", side_effect=remove) as cli):
                    self.install.cleanup(records, OLD)
                self.assertEqual(cli.call_count, 2)
                self.assertEqual(self.install.load(), ({}, None))

    def test_unexecutable_launcher_fails_verify_and_is_repairable(self):
        records, current = self.active()
        engine = self.install.root / OLD / "venv"
        sites = engine / "lib/python3.11/site-packages"
        source = self.source()
        for name in self.receipt["engine"]:
            path = sites / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.files[name])
        metadata = sites / "adp_codex-0.1.0.dist-info/METADATA"
        metadata.parent.mkdir()
        metadata.write_text("Name: adp-codex\nVersion: 0.1.0\n")
        launcher = engine.parent / "bin/adp"
        launcher.parent.mkdir()
        launcher.write_text(installer.launcher_script(engine))
        alias = engine.parent / installer.LAUNCHER_ALIAS
        alias.parent.mkdir(parents=True)
        alias.symlink_to(installer.LAUNCHER_LINK)
        receipt = dict(self.receipt, launcher_sha256=installer.digest(launcher.read_bytes()))
        records[OLD] = receipt
        self.install.save(records)
        command = installer.command

        def run(argv, *args, **kwargs):
            if "-c" in argv:
                return json.dumps([str(engine), str(sites / "adp/__init__.py")]).encode()
            return command(argv, *args, **kwargs)

        with (patch.object(installer, "command", side_effect=run),
              patch.object(self.install, "stage", side_effect=installer.Refusal("Repair reached staging"))):
            with self.assertRaisesRegex(installer.Refusal, "Repair reached staging"):
                self.install.apply("install", records, current, source)
        self.assertEqual(self.install.load(), ({OLD: receipt}, OLD))

        launcher.write_text("#!/bin/sh\nexit 0\n")
        launcher.chmod(0o700)
        with patch.object(installer, "command") as command:
            self.assertFalse(self.install.report(current, receipt))
        command.assert_not_called()

    def test_documented_launcher_ignores_other_adp_on_pythonpath(self):
        import venv

        generation = self.home / "generation with spaces"
        engine = generation / "venv"
        venv.EnvBuilder(with_pip=False).create(engine)
        candidates = list(engine.glob("lib/python*/site-packages"))
        managed = candidates[0] / "adp"
        foreign = self.home / "other-checkout/adp"
        for path, message in ((managed, "managed ADP"), (foreign, "foreign ADP")):
            path.mkdir(parents=True)
            (path / "__init__.py").touch()
            (path / "__main__.py").write_text(f"print({message!r})\n")
        installer.write_launcher(generation)
        current = self.home / "current"
        current.symlink_to(self.home / "old-generation")
        replacement = self.home / "activate"
        replacement.symlink_to(generation)
        replacement.replace(current)
        for relative in ("bin/adp", installer.LAUNCHER_ALIAS):
            with self.subTest(launcher=relative):
                result = installer.command([str(current / relative), "--help"], foreign.parent,
                                           "Managed launcher", env=dict(os.environ, PYTHONPATH=str(foreign.parent)))
                self.assertEqual(result, b"managed ADP\n")

    def test_verify_reuses_healthy_isolated_launcher_from_earlier_layout(self):
        records, current = self.active()
        source = self.source()
        generation = self.install.root / current
        engine = generation / "engine"
        sites = engine / "lib/python3.11/site-packages"
        catalog = self.install.catalog(current)
        cache = self.codex.home / "plugins/cache" / current / installer.NAME / self.receipt["version"]
        for parent, section in ((sites, "engine"), (catalog / installer.CATALOG_PLUGIN, "plugin"), (cache, "plugin")):
            for name in self.receipt[section]:
                path = parent / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.files[name])
        manifest = catalog / ".agents/plugins/marketplace.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps(installer.marketplace_payload(current)))
        metadata = sites / "adp_codex-0.1.0.dist-info/METADATA"
        metadata.parent.mkdir()
        metadata.write_text("Name: adp-codex\nVersion: 0.1.0\n")
        launcher = generation / "bin/adp"
        launcher.parent.mkdir()
        launcher.write_text(installer.launcher_script(engine))
        receipt = records[current] | {"launcher_sha256": installer.digest(launcher.read_bytes())}
        self.codex.observe.return_value = installer.PluginState(True, True, True, True)
        self.codex.discovered.return_value = True
        with patch.object(installer, "command", side_effect=[
                json.dumps([str(engine), str(sites / "adp/__init__.py")]).encode(), b"help"]):
            self.assertTrue(self.install.report(current, receipt))

    def test_subprocess_output_is_bounded(self):
        with patch.object(installer, "MAX_RESPONSE", 1024):
            with self.assertRaisesRegex(installer.Refusal, "exceeded the output limit"):
                installer.command([sys.executable, "-c", "while True: print('x' * 1024)"],
                                  self.home, "Test overflow")

    def test_changed_codex_response_retains_candidate_ownership(self):
        self.install.root.mkdir(mode=0o700)
        with patch.object(self.install, "stage", side_effect=installer.UnknownCodexState("changed")):
            with self.assertRaisesRegex(installer.UnknownCodexState, "changed"):
                self.install.apply("install", {}, None, self.source())
        records, current = self.install.load()
        self.assertIsNone(current)
        name, = records
        self.assertTrue(records[name]["codex_format_unknown"])
        with self.assertRaisesRegex(installer.Refusal, "PARTIAL"):
            self.install.cleanup(records, name)
        self.codex.remove.assert_not_called()

    def test_pending_build_keeps_files_for_the_guarded_worker(self):
        self.install.root.mkdir(mode=0o700)
        source = self.source()
        with patch.object(installer, "command", side_effect=installer.PendingMutation("build is settling")):
            with self.assertRaisesRegex(installer.PendingMutation, "build is settling"):
                self.install.apply("install", {}, None, source)
        records, current = self.install.load()
        self.assertIsNone(current)
        name, = records
        staged = self.install.root / name / "build/source/pyproject.toml"
        self.assertEqual(staged.read_bytes(), source.files["pyproject.toml"])
        self.codex.remove.assert_not_called()

    def test_pending_probe_keeps_private_scratch(self):
        scratch = self.home / "probe-scratch"
        scratch.mkdir()
        with patch.object(installer.tempfile, "mkdtemp", return_value=str(scratch)):
            with self.assertRaises(installer.PendingMutation):
                with installer.installer_scratch() as path:
                    (path / "pending-probe").touch()
                    raise installer.PendingMutation("probe is settling")
        self.assertTrue((scratch / "pending-probe").is_file())

    def test_disposable_probe_refuses_changed_skill_identity_fields(self):
        codex = installer.Codex("/unused", self.codex.home, self.home)
        expected = self.home / "probe-codex-home/plugins/cache/adp-managed-probe/adp-codex/0.0.1" / installer.SKILL
        changed = [{"skillName": installer.NAME, "path": str(expected), "enabled": True}]
        with (patch.object(installer.Codex, "add"),
              patch.object(installer.Codex, "skills", return_value=changed)):
            with self.assertRaisesRegex(installer.Refusal, "skill response"):
                codex.probe_lifecycle()
        self.assertFalse(codex.home.exists())

    def test_interrupted_mutation_fences_detached_writer_until_exit(self):
        import fcntl

        program = """import fcntl, os, signal, subprocess, sys, time
from pathlib import Path
from scripts import install_adp
root, ready, released, changed, spawn_return = map(Path, sys.argv[1:6])
if sys.argv[6] == "during":
    popen = subprocess.Popen
    def delayed_popen(*args, **kwargs):
        process = popen(*args, **kwargs)
        deadline = time.monotonic() + 8
        while not spawn_return.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        return process
    subprocess.Popen = delayed_popen
signal.signal(signal.SIGTERM, install_adp.interrupt_on_term)
fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
fcntl.flock(fd, fcntl.LOCK_EX)
child = '''
from pathlib import Path
import sys, time
ready, released, changed = map(Path, sys.argv[1:])
ready.touch()
deadline = time.monotonic() + 8
while not released.exists() and time.monotonic() < deadline:
    time.sleep(.01)
if released.exists():
    changed.touch()
'''
shim = 'import subprocess,sys; subprocess.Popen(sys.argv[1:], start_new_session=True)'
try:
    install_adp.command([sys.executable, '-c', shim, sys.executable, '-c', child,
                         str(ready), str(released), str(changed)], root, 'mutation', mutation_lock=fd)
except install_adp.PendingMutation:
    sys.exit(2)
"""
        for interruption, phase in ((signal.SIGTERM, "after"), (signal.SIGTERM, "during"), (signal.SIGKILL, "after")):
            with self.subTest(signal=interruption, phase=phase):
                ready = self.home / f"ready-{interruption}-{phase}"
                released = self.home / f"released-{interruption}-{phase}"
                changed = self.home / f"changed-{interruption}-{phase}"
                spawn_return = self.home / f"spawn-return-{interruption}-{phase}"
                with subprocess.Popen([sys.executable, "-c", program, str(self.home), str(ready),
                                       str(released), str(changed), str(spawn_return), phase],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
                    try:
                        deadline = time.monotonic() + 10
                        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.01)
                        self.assertTrue(ready.exists())
                        process.send_signal(interruption)
                        spawn_return.touch()
                        process.wait(timeout=5)
                        expected = 2 if interruption == signal.SIGTERM else -signal.SIGKILL
                        self.assertEqual(process.returncode, expected)
                        fd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            with self.assertRaises(BlockingIOError):
                                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            released.touch()
                            deadline = time.monotonic() + 5
                            while True:
                                try:
                                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                    break
                                except BlockingIOError:
                                    if time.monotonic() >= deadline:
                                        self.fail("Mutation guard failed to release its lock")
                                    time.sleep(0.01)
                            self.assertTrue(changed.exists())
                        finally:
                            os.close(fd)
                    finally:
                        if process.poll() is None:
                            process.kill()

    def test_verify_requires_receipt_to_own_launcher(self):
        self.install.root.mkdir(mode=0o700)
        self.install.link.symlink_to(self.home / "outside")
        with self.assertRaisesRegex(installer.Refusal, "Missing ADP ownership receipt"):
            self.install.load()


if __name__ == "__main__":
    unittest.main()
