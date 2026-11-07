"""Synthetic, offline tests for the architecture-stage skill package."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_scaffold", ROOT / "scripts/validate_scaffold.py")
assert spec is not None and spec.loader is not None
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ScaffoldTests(unittest.TestCase):
    def test_repo_scaffold_is_valid(self) -> None:
        self.assertEqual(validator.validate(ROOT), [])

    def test_portable_manifest_and_skill(self) -> None:
        payload = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], "adp-codex")
        self.assertIn("agent-plugins.org", payload["$schema"])
        skill = (ROOT / "skills/adp-codex/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        self.assertIn("read-only", skill.lower())
        self.assertIn("not implemented", skill.lower())

    def test_progress_guard_cannot_be_silently_skipped(self) -> None:
        policy = (ROOT / "docs/PROGRESS_GUARD.md").read_text(encoding="utf-8")
        for invariant in ("TEST_CORRUPTED", "UNCLASSIFIED", "Full diagnostic campaign",
                          "review", "operator", "without a new"):
            self.assertIn(invariant.lower(), policy.lower())

    def test_missing_required_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adp-scaffold-test-") as directory:
            copy = Path(directory)
            shutil.copytree(ROOT / "skills", copy / "skills")
            shutil.copytree(ROOT / "docs", copy / "docs")
            shutil.copytree(ROOT / ".github", copy / ".github")
            for filename in ("plugin.json", "README.md", "AGENTS.md", "CONTRIBUTING.md",
                             "SECURITY.md", "CHANGELOG.md"):
                shutil.copy2(ROOT / filename, copy / filename)
            self.assertEqual(validator.validate(copy), [])
            (copy / "plugin.json").unlink()
            self.assertTrue(any("plugin.json" in e for e in validator.validate(copy)))

    def test_broken_relative_link_is_detected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adp-link-test-") as directory:
            copy = Path(directory)
            shutil.copytree(ROOT / "skills", copy / "skills")
            shutil.copytree(ROOT / "docs", copy / "docs")
            shutil.copytree(ROOT / ".github", copy / ".github")
            for filename in ("plugin.json", "README.md", "AGENTS.md", "CONTRIBUTING.md",
                             "SECURITY.md", "CHANGELOG.md"):
                shutil.copy2(ROOT / filename, copy / filename)
            readme = copy / "README.md"
            readme.write_text(readme.read_text(encoding="utf-8") +
                              "\n[not there](docs/MISSING_FILE.md)\n", encoding="utf-8")
            self.assertTrue(any("Broken relative link" in e for e in validator.validate(copy)))


if __name__ == "__main__":
    unittest.main()
