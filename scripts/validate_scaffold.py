#!/usr/bin/env python3
"""Validate the portable ADP planning plugin and Markdown links.

No network access, Git credentials, target checkout, or runtime engine required.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "plugin.json",
    "skills/adp-codex/SKILL.md",
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/ARCHITECTURE.md",
    "docs/PROGRESS_GUARD.md",
    "docs/POLICY_PROVIDER.md",
    "docs/ISSUE_DISCOVERY.md",
    "docs/STATE_CONTRACT.md",
    "docs/ROADMAP.md",
    ".github/workflows/scaffold.yml",
)
MARKDOWN_LINK = re.compile(r"(?<!\\)\[[^]]+\]\(([^)]+)\)")
SKILL_HEADER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
VERSION = re.compile(r"\A\d+\.\d+\.\d+\Z")


def validate(root: Path = ROOT) -> list[str]:
    """Return all observable scaffold violations; never modify the filesystem."""
    errors: list[str] = []

    for relative in REQUIRED:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"Required file absent or symlinked: {relative}")

    manifest = root / "plugin.json"
    if manifest.is_file() and not manifest.is_symlink():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("manifest is not a JSON object")
        except (ValueError, UnicodeError) as exc:
            errors.append(f"Invalid plugin.json: {exc}")
        else:
            if data.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
                errors.append("plugin.json requires the portable Agent Plugins schema")
            if data.get("name") != "adp-codex":
                errors.append("plugin.json name must be adp-codex")
            if not isinstance(data.get("version"), str) or not VERSION.fullmatch(data["version"]):
                errors.append("plugin.json requires a semantic x.y.z version")
            if not isinstance(data.get("description"), str) or not data["description"].strip():
                errors.append("plugin.json requires a nonempty description")

    skill = root / "skills/adp-codex/SKILL.md"
    if skill.is_file() and not skill.is_symlink():
        try:
            body = skill.read_text(encoding="utf-8")
        except UnicodeError as exc:
            errors.append(f"Invalid SKILL.md encoding: {exc}")
        else:
            match = SKILL_HEADER.match(body)
            if not match:
                errors.append("SKILL.md requires YAML frontmatter delimited by ---")
            else:
                header = match.group(1)
                if not re.search(r"(?m)^name:\s*adp-codex\s*$", header):
                    errors.append("SKILL.md requires name: adp-codex")
                if not re.search(r"(?m)^description:\s*\S", header):
                    errors.append("SKILL.md requires a nonempty description")
            if "read-only" not in body.lower() or "does not grant execution authority" not in body.lower():
                errors.append("Planning skill must explicitly remain read-only and grant no execution authority")

    for path in sorted(root.rglob("*.md")):
        if any(p in (".git", ".venv") for p in path.parts):
            continue
        if path.is_symlink():
            errors.append(f"Symlinked Markdown not permitted: {path.relative_to(root)}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            errors.append(f"Invalid Markdown encoding {path.relative_to(root)}: {exc}")
            continue
        for target in MARKDOWN_LINK.findall(content):
            # No network fetch; URLs are not validated by this local check.
            if "://" in target or target.startswith(("mailto:", "#", "/")):
                continue
            dest = target.split("#", 1)[0].strip()
            if not dest:
                continue
            resolved = (path.parent / dest).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
                errors.append(f"Broken relative link: {path.relative_to(root)} -> {target}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for problem in errors:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print("PASS: ADP Codex portable skill scaffold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
