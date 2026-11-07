"""Explicit or unambiguous configuration discovery, with no writes."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .errors import ADPError, ConfigurationError
from .git import git, value


def safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ADPError("Symlinked paths are not permitted for ADP storage/configuration")
    return path


def load_json(path: Path, limit: int = 65536) -> dict:
    safe_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ADPError("JSON must be a regular bounded file")
        raw = os.read(descriptor, limit + 1)
        if len(raw) > limit:
            raise ADPError("JSON payload exceeds size limit")
    finally:
        os.close(descriptor)
    def pairs(items: list[tuple[str, object]]) -> dict:
        data: dict = {}
        for key, item in items:
            if key in data:
                raise ValueError("duplicate key")
            data[key] = item
        return data
    try:
        data = json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ADPError("Malformed JSON (duplicate keys and non-finite numbers forbidden)") from exc
    if not isinstance(data, dict):
        raise ADPError("JSON root must be an object")
    return data


def remote_identity(url: str, root: Path) -> str:
    if (any(ord(c) < 32 for c in url) or url.startswith("-")
            or url.partition(":")[2].startswith(":")):
        raise ConfigurationError("Unsafe remote transport")
    if "://" in url:
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            parsed.port  # validate malformed/non-numeric ports observationally
        except ValueError as exc:
            raise ConfigurationError("Malformed remote URL") from exc
        if parsed.scheme not in ("https", "ssh", "file", "git"):
            raise ConfigurationError("Unsupported remote transport")
        if parsed.password or (parsed.username and parsed.scheme != "ssh") or parsed.query or parsed.fragment:
            raise ConfigurationError("Remote URLs must not contain credentials/query/fragment")
        if parsed.scheme == "file":
            if parsed.netloc not in ("", "localhost"):
                raise ConfigurationError("Non-local file remote")
            return "file:" + str(Path(unquote(parsed.path)).resolve())
        if not hostname:
            raise ConfigurationError("Remote URL requires a hostname")
        return f"{parsed.scheme}://{parsed.netloc.lower()}/{parsed.path.strip('/').removesuffix('.git')}"
    if ":" in url and not url.startswith("/"):
        host, path = url.split(":", 1)
        if not host or not path or host.startswith("-"):
            raise ConfigurationError("Ambiguous remote URL")
        return f"ssh://{host.lower()}/{path.strip('/').removesuffix('.git')}"
    return "file:" + str((root / url).resolve())


@dataclass(frozen=True)
class Config:
    root: Path
    remote: str
    identity: str
    branch: str | None
    storage: Path | None

    @classmethod
    def discover(cls, repo: Path, *, remote: str | None = None,
                 repository_id: str | None = None, branch: str | None = None,
                 storage: Path | None = None, config: Path | None = None) -> Config:
        root = Path(value(repo, "rev-parse", "--show-toplevel"))
        config_path = config if config is not None else root / ".adp.json"
        data = load_json(config_path) if config_path.exists() or config_path.is_symlink() else {}
        if config is not None and not config_path.exists():
            raise ConfigurationError("Explicit configuration file does not exist")
        if set(data) - {"schema_version", "remote", "repository_id", "memory_branch", "storage"}:
            raise ConfigurationError("Unknown configuration key")
        if data and (type(data.get("schema_version")) is not int or data["schema_version"] != 1):
            raise ConfigurationError("Configuration requires schema_version 1")
        if any(not isinstance(v, str) or not v for k, v in data.items() if k != "schema_version"):
            raise ConfigurationError("Configuration values must be nonempty strings")
        remotes = value(root, "remote").splitlines()
        selected = remote or data.get("remote")
        if selected is None:
            if len(remotes) != 1:
                raise ConfigurationError("Select --remote explicitly: repository has zero or multiple remotes")
            selected = remotes[0]
        if selected not in remotes or selected.startswith("-"):
            raise ConfigurationError("Selected remote does not exist or is unsafe")
        urls = value(root, "remote", "get-url", "--all", selected).splitlines()
        pushes = value(root, "remote", "get-url", "--push", "--all", selected).splitlines()
        if len(urls) != 1 or pushes != urls:
            raise ConfigurationError("Select a remote with exactly one identical fetch/push endpoint")
        normalized = remote_identity(urls[0], root)
        identity = repository_id or data.get("repository_id") or "repo:" + hashlib.sha256(normalized.encode()).hexdigest()
        if len(identity) > 256 or not identity.strip() or any(ord(c) < 32 for c in identity):
            raise ConfigurationError("Repository identity must be a compact opaque identifier")
        selected_branch = branch or data.get("memory_branch")
        if selected_branch:
            try:
                git(root, "check-ref-format", "refs/heads/" + selected_branch)
            except ADPError as exc:
                raise ConfigurationError("Invalid memory branch") from exc
        location = storage if storage is not None else data.get("storage")
        target = safe_path(root / location) if location is not None else None
        if target:
            worktrees = value(root, "worktree", "list", "--porcelain").splitlines()
            for line in worktrees:
                if line.startswith("worktree "):
                    other = Path(line[9:])
                    if other != target and (target.is_relative_to(other) or other.is_relative_to(target)):
                        raise ConfigurationError("Memory storage must be outside every product worktree")
                    if other == target and other == root:
                        raise ConfigurationError("Memory storage cannot be the product worktree")
            common = Path(value(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
            if target.is_relative_to(common) or common.is_relative_to(target):
                raise ConfigurationError("Memory storage cannot overlap Git administrative data")
        return cls(root, selected, identity, selected_branch, target)

    def require_storage(self) -> tuple[str, Path]:
        if not self.branch or self.storage is None:
            raise ConfigurationError("Select --memory-branch and --storage explicitly (suggestion: adp/state)")
        return self.branch, self.storage

    def remote_head(self) -> str | None:
        branch, _ = self.require_storage()
        lines = value(self.root, "ls-remote", "--refs", self.remote, "refs/heads/" + branch).splitlines()
        if len(lines) > 1:
            raise ADPError("Ambiguous memory ref")
        return lines[0].split()[0] if lines else None
