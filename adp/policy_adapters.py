"""Observational Git and M2 adapters; no mutation or execution adapter ships."""
from __future__ import annotations

import hashlib
import stat
from pathlib import PurePosixPath

from .config import Config, remote_identity
from .errors import AuthorityError, GitError
from .git import git, value
from .guard import GuardRefusal, ProgressGuard
from .policy_schema import parse_profile, sha as exact_sha, validate_snapshot
from .policy_types import Document, Ref, RepositorySnapshot, Safety, SourceKind, Task
from .schema import require, string


def working_tree_digest(root) -> str | None:
    """Opt-in bounded stage precondition; never follows untracked symlinks."""
    diff = git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", limit=1048576)
    paths = git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    paths = [p for p in paths if p]
    if len(paths) > 32:
        return None
    result = hashlib.sha256(diff)
    total = len(diff)
    for raw in sorted(paths):
        path = root / raw.decode("utf-8", "strict")
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1048576:
            return None
        content = path.read_bytes()
        total += len(content)
        if total > 1048576:
            return None
        result.update(raw + b"\0" + str(metadata.st_mode).encode() + b"\0" + content)
    return result.hexdigest()


class MockRepositoryAdapter:
    """Explicit offline snapshot adapter; it grants no verification or rights."""
    def __init__(self, snapshot: RepositorySnapshot):
        validate_snapshot(snapshot)
        self.snapshot = snapshot

    def inspect(self) -> RepositorySnapshot:
        validate_snapshot(self.snapshot)
        return self.snapshot


class GitPolicyAdapter:
    """Inspect selected repository/remote and committed policy bytes only.

    Local Git configuration/authentication is trusted as in M1. Free text is
    hashed, never interpreted or executed. Profiles require external verification
    even after parsing. Pre-fetched external documents may be supplied explicitly.
    """
    def __init__(self, config: Config, *, profiles: tuple[str, ...] = (),
                 governance: tuple[str, ...] = ("AGENTS.md", "CONTRIBUTING.md"),
                 contracts: tuple[str, ...] = (), injected: tuple[Document, ...] = (),
                 fingerprint_worktree: bool = False):
        self.config = config
        self.paths = tuple((p, kind) for paths, kind in (
            (governance, SourceKind.GOVERNANCE), (profiles, SourceKind.PROFILE),
            (contracts, SourceKind.CONTRACT)) for p in paths)
        require(len(self.paths) + len(injected) <= 16, "Too many selected policy sources")
        for path, _ in self.paths:
            string(path)
            parsed = PurePosixPath(path)
            require(not parsed.is_absolute() and str(parsed) == path and not any(
                part in ("..", ".git", ".") for part in parsed.parts)
                and "\\" not in path and not path.startswith(":") and ":" not in path,
                "Unsafe policy source path")
        require(len({p for p, _ in self.paths}) == len(self.paths), "Duplicate policy path")
        self.injected = injected
        self.fingerprint_worktree = fingerprint_worktree

    def _remote_refs(self, config):
        return tuple(Ref(name, sha) for sha, name in (line.split() for line in
            value(config.root, "ls-remote", "--refs", config.remote, "refs/heads/*", "refs/tags/*").splitlines()))

    def inspect(self) -> RepositorySnapshot:
        # Revalidate even a Config constructed directly instead of discovered.
        cfg = Config.discover(self.config.root, remote=self.config.remote,
                              repository_id=self.config.identity)
        root = cfg.root
        head = value(root, "rev-parse", "HEAD")
        source_ref = value(root, "symbolic-ref", "--quiet", "HEAD")
        endpoint = value(root, "remote", "get-url", cfg.remote)
        fingerprint = hashlib.sha256(remote_identity(endpoint, root).encode()).hexdigest()
        index = hashlib.sha256(git(root, "ls-files", "--stage", "-z")).hexdigest()
        unstaged = git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z")
        untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
        local_refs = tuple(Ref(*line.split(" ", 1)) for line in value(root, "for-each-ref",
            "--format=%(refname) %(objectname)", "refs/heads/", "refs/tags/").splitlines())
        diagnostics = ()
        try:
            remote_refs = self._remote_refs(cfg)
            known = True
        except GitError:
            remote_refs, known = (), False
            diagnostics = ("Remote refs inaccessible; no absent-ref or write authority inferred",)
        old = next((r.revision for r in remote_refs if r.name == source_ref), None)
        relation = "UNKNOWN"
        if known and old is None:
            relation = "CREATE"
        elif old == head:
            relation = "SAME"
        elif old is not None:
            exact_sha(old)
            try:
                common = value(root, "merge-base", old, head)
                relation = "FAST_FORWARD" if common == old else "DIVERGED"
            except GitError:
                pass  # No fetch: inaccessible ancestry remains UNKNOWN.
        selected = dict(self.paths)
        documents = list(self.injected)
        found = set()
        # Read Git objects rather than following uncommitted paths/symlinks.
        for entry in filter(None, git(root, "ls-tree", "-rz", head).split(b"\0")):
            metadata, path_raw = entry.split(b"\t", 1)
            path = path_raw.decode("utf-8", "surrogateescape")
            if path not in selected:
                continue
            mode, kind, sha = metadata.decode().split()
            require(mode == "100644" and kind == "blob", "Policy sources must be regular committed files")
            require(int(value(root, "cat-file", "-s", sha)) <= 65536, "Oversized policy source")
            raw = git(root, "cat-file", "blob", sha, limit=65536)
            source_kind = selected[path]
            found.add(path)
            profile = parse_profile(raw) if source_kind == SourceKind.PROFILE else None
            documents.append(Document(path, source_kind, hashlib.sha256(raw).hexdigest(), profile))
        missing = [path for path, kind in self.paths if kind in (SourceKind.PROFILE, SourceKind.CONTRACT)
                   and path not in found]
        require(not missing, "Missing explicitly selected profile/contract sources: " + ", ".join(missing))
        result = RepositorySnapshot(cfg.identity, cfg.remote, fingerprint, source_ref, head,
            index, not unstaged and not untracked, tuple(sorted(local_refs, key=lambda r: r.name)),
            tuple(sorted(remote_refs, key=lambda r: r.name)), tuple(sorted(documents, key=lambda d: d.reference)),
            known, diagnostics, relation, working_tree_digest(root) if self.fingerprint_worktree else None)
        validate_snapshot(result)
        # Reject a racing read instead of returning an internally mixed HEAD/index.
        require(value(root, "rev-parse", "HEAD") == head
                and value(root, "symbolic-ref", "--quiet", "HEAD") == source_ref
                and hashlib.sha256(git(root, "ls-files", "--stage", "-z")).hexdigest() == index,
                "Repository changed during policy inspection; inspect again")
        return result


class M2SafetyAdapter:
    """Fresh read-only M1 ownership + M2 decision. It never reserves an action."""
    def __init__(self, guard: ProgressGuard):
        self.guard = guard

    def observe(self, task: Task) -> Safety:
        decision = self.guard.inspect(task.task_id, task.requirement_id)
        memory = self.guard.memory.inspect()
        require(memory["health"] == "SYNCED", "Memory checkpoint is not synchronized")
        item = memory["state"]["progress_guard"]["requirements"][task.requirement_id]
        # Detect a guard-state race between the two observational reads.
        current = self.guard.inspect(task.task_id, task.requirement_id)
        require(current == decision, "Guard changed during safety inspection")
        try:
            approval = self.guard.require_approval(task.task_id, task.requirement_id)
        except (GuardRefusal, AuthorityError):
            approval = None
        require(self.guard.inspect(task.task_id, task.requirement_id) == current, "Guard changed during approval inspection")
        return Safety(decision, memory["local_owner"], tuple(item["authors"]), memory["local_head"], approval)
