"""Single-writer Git memory, explicit ownership and recoverable checkpoints."""
from __future__ import annotations

import copy
import hashlib
import os
import secrets
import uuid
from pathlib import Path

from .config import Config, load_json, safe_path
from .errors import ADPError, AuthorityError, Conflict, GitError
from .git import SHA, author, git, value
from .schema import (KEY, MAX_ASSIGNMENTS, MAX_JOURNAL, MAX_JSON, MAX_RESULT,
                     MAX_TASKS, bundle, decode, encode, fields, key, require,
                     result_schema, string)
from .storage import atomic, clear_slot, interrupted_slot, locked, sync_directory

IGNORE = b"/inbox/\n"
_UNREVIEWED_REMOTE = object()


class Memory:
    """All mutations affect only the selected memory branch and local controls.

    The caller must supply explicit operator authority for initialization and
    exceptional takeover. Git is an optimistic checkpoint transport, not a lease.
    """

    def __init__(self, config: Config, *, pinned_local_remote: Path | None = None):
        self.config = config
        self.pinned_local_remote = pinned_local_remote
        self._accounting_reads = False  # Private ephemeral optimization, never authority or persisted state.
        self.branch, self.path = config.require_storage()
        self.common = safe_path(Path(value(config.root, "rev-parse", "--path-format=absolute", "--git-common-dir")))
        self.control = safe_path(self.common / "adp" / key(self.branch))

    def _write_git(self, cwd: Path, *args: str, input: bytes | None = None) -> bytes:
        if self.pinned_local_remote is None:
            return git(cwd, *args, input=input)
        self.verify_pinned_remote()
        if cwd == self.config.root:
            directory = self.common
            prefix = ("--git-dir", str(directory))
        else:
            require(cwd == self.path, "Unexpected guided memory Git working directory")
            directory = self._registered()
            prefix = ("--git-dir", str(directory), "--work-tree", str(cwd))
        return git(cwd, *prefix, *args, input=input)

    def _remote_git(self, cwd: Path, args: tuple[str, ...], refspec: str) -> bytes:
        if self.pinned_local_remote is None:
            return git(cwd, *args, self.config.remote, refspec)
        endpoint = safe_path(self.pinned_local_remote).as_uri()
        # A private one-use alias prevents a selected remote name or an
        # existing URL rewrite from redirecting the approved local endpoint.
        alias = "adp-local-" + secrets.token_hex(16) + ":"
        return self._write_git(cwd, "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
                               "-c", f"url.{endpoint}.insteadOf={alias}", "-c", f"url.{endpoint}.pushInsteadOf={alias}",
                               *args, alias, refspec)

    def verify_pinned_remote(self) -> None:
        if self.pinned_local_remote is not None:
            path = safe_path(self.pinned_local_remote)
            require(safe_path(self.common) == self.common
                    and Path(value(self.config.root, "rev-parse", "--path-format=absolute", "--git-common-dir")) == self.common,
                    "The approved coordination Git directory changed")
            require(value(self.config.root, 'remote', 'get-url', '--all', self.config.remote) in (str(path), path.as_uri())
                    and value(self.config.root, 'remote', 'get-url', '--push', '--all', self.config.remote) in (str(path), path.as_uri()),
                    'The approved local coordination destination changed')

    def _remote_head(self) -> str | None:
        if self.pinned_local_remote is None:
            return self.config.remote_head()
        lines = self._remote_git(self.config.root, ("ls-remote", "--refs"),
                                 "refs/heads/" + self.branch).decode("ascii").splitlines()
        require(len(lines) <= 1, "Ambiguous pinned local memory ref")
        if not lines:
            return None
        revision, name = lines[0].split()
        require(SHA.fullmatch(revision) and name == "refs/heads/" + self.branch,
                "Invalid pinned local memory ref")
        return revision

    def _read_ref(self, ref: str) -> tuple[dict, dict[str, dict]]:
        entries = git(self.config.root, "ls-tree", "-rz", ref).split(b"\0")
        blobs: dict[str, str] = {}
        for entry in filter(None, entries):
            try:
                info, filename = entry.split(b"\t", 1)
                mode, kind, sha = info.decode().split()
                name = filename.decode("ascii")
            except (ValueError, UnicodeError) as exc:
                raise ADPError("Malformed memory tree") from exc
            require(mode == "100644" and kind == "blob", "Memory contains symlink/special files")
            require(name in ("state.json", ".gitignore") or name.startswith("tasks/")
                    and name.endswith(".json") and KEY.fullmatch(name[6:-5]), "Unexpected memory tree path")
            blobs[name] = sha
        require(len(blobs) <= MAX_TASKS + 2 and {"state.json", ".gitignore"} <= set(blobs), "Invalid memory tree size/layout")
        values: dict[str, bytes] = {}
        batched = self._accounting_reads is True and len(blobs) <= 4
        if batched:
            values = self._accounting_blobs(blobs)
        else:
            for name, sha in blobs.items():
                require(int(value(self.config.root, "cat-file", "-s", sha)) <= MAX_JSON, "Oversized memory blob")
                values[name] = git(self.config.root, "cat-file", "blob", sha, limit=MAX_JSON)
        require(values.pop(".gitignore") == IGNORE, "Unexpected memory ignore rules")
        state = decode(values.pop("state.json"))
        tasks = {name[6:-5]: decode(raw) for name, raw in values.items()}
        bundle(state, tasks, self.config.identity)
        return state, tasks

    def _accounting_blobs(self, blobs):
        """Read every actual blob byte now; retain no decoded fact or verdict."""
        require(2 <= len(blobs) <= 4 and all(SHA.fullmatch(oid) for oid in blobs.values()),
                "Unsupported accounting blob inventory")
        raw = git(self.config.root, "cat-file", "--batch", input=("\n".join(blobs.values()) + "\n").encode("ascii"),
                  limit=len(blobs) * (MAX_JSON + 256))
        cursor, values = 0, {}
        for name, oid in blobs.items():
            end = raw.find(b"\n", cursor)
            require(end >= cursor, "Truncated accounting blob header")
            header = raw[cursor:end].decode("ascii", "strict").split()
            require(len(header) == 3 and header[0] == oid and header[1] == "blob"
                    and header[2].isdigit() and 0 <= int(header[2]) <= MAX_JSON,
                    "Missing, malformed or oversized accounting blob")
            size = int(header[2]);cursor = end + 1
            body = raw[cursor:cursor + size]
            require(len(body) == size and raw[cursor + size:cursor + size + 1] == b"\n", "Truncated accounting blob body")
            digest = (hashlib.sha1 if len(oid) == 40 else hashlib.sha256)(b"blob " + str(size).encode() + b"\0" + body).hexdigest()
            require(digest == oid, "Accounting blob bytes differ from their immutable identity")
            values[name] = body;cursor += size + 1
        require(cursor == len(raw), "Unexpected accounting blob output")
        return values

    def _registered(self) -> Path | None:
        safe_path(self.path)
        require(self.path.is_dir(), "Memory worktree is absent; use authorized init --apply")
        gitfile = self.path / ".git"
        require(gitfile.is_file() and not gitfile.is_symlink(),
                "Storage is not a registered linked memory worktree; unexpected files are refused")
        directory, prefix = None, ()
        if self.pinned_local_remote is None:
            actual = value(self.path, "rev-parse", "--show-toplevel")
            require(Path(actual) == self.path, "Storage is not the selected memory worktree")
        else:
            directory = safe_path(Path(value(self.path, "rev-parse", "--absolute-git-dir")))
            require(directory.parent == self.common / "worktrees", "Guided memory worktree administration changed")
            backlink = safe_path(directory / "gitdir")
            require(backlink.is_file() and backlink.stat().st_size <= 4096
                    and safe_path(directory / backlink.read_text().removesuffix("\n")) == gitfile,
                    "Git administration does not belong to the selected memory worktree")
            prefix = ("--git-dir", str(directory), "--work-tree", str(self.path))
        common = value(self.path, *prefix, "rev-parse", "--path-format=absolute", "--git-common-dir")
        require(Path(common) == self.control.parent.parent, "Memory belongs to another repository")
        require(value(self.path, *prefix, "symbolic-ref", "HEAD") == "refs/heads/" + self.branch, "Memory branch mismatch")
        return directory

    def _accounting_registered(self, *, head=False):
        """One fresh native context query, only for selected observations."""
        if (not self._accounting_reads or self.pinned_local_remote is None
                or any(p != p.strip() or "\n" in p or "\r" in p for p in (str(self.path), str(self.common), self.branch))):
            return None  # Unsupported framing uses the unchanged native reader.
        safe_path(self.path)
        require(self.path.is_dir(), "Memory worktree is absent; use authorized init --apply")
        gitfile = self.path / ".git"
        require(gitfile.is_file() and not gitfile.is_symlink(),
                "Storage is not a registered linked memory worktree; unexpected files are refused")
        args = ("rev-parse", "--path-format=absolute", "--absolute-git-dir", "--git-common-dir",
                *(("HEAD",) if head else ()), "--symbolic-full-name", "HEAD")
        raw = git(self.path, *args, limit=32768)
        try:
            lines = raw.decode("utf-8").split("\n")
        except UnicodeError as exc:
            raise ADPError("Malformed accounting Git context") from exc
        require(len(lines) == (5 if head else 4) and lines[-1] == ""
                and all(line and line == line.strip() and "\r" not in line and "\0" not in line for line in lines[:-1]),
                "Malformed accounting Git context framing")
        directory = safe_path(Path(lines[0]))
        require(Path(lines[0]).is_absolute() and directory.parent == self.common / "worktrees",
                "Guided memory worktree administration changed")
        backlink = safe_path(directory / "gitdir")
        require(backlink.is_file() and backlink.stat().st_size <= 4096
                and safe_path(directory / backlink.read_text().removesuffix("\n")) == gitfile,
                "Git administration does not belong to the selected memory worktree")
        require(Path(lines[1]) == self.control.parent.parent, "Memory belongs to another repository")
        require(lines[-2] == "refs/heads/" + self.branch, "Memory branch mismatch")
        if head:
            require(SHA.fullmatch(lines[2]) is not None, "Malformed accounting HEAD")
        return directory, lines[2] if head else None

    def _layout(self, slots=(), *, _accounting_inspection=False) -> None:
        if not _accounting_inspection or self._accounting_registered() is None:
            self._registered()
        # os.scandir does not follow directory symlinks. Reject before recursion.
        for top in self.path.iterdir():
            require(not top.is_symlink(), "Symlinked memory entry")
            if top in slots:
                continue
            if top.name == ".git":
                require(top.is_file(), "Unexpected Git directory in linked memory")
            elif top.name in ("state.json", ".gitignore"):
                require(top.is_file() and top.stat().st_size <= MAX_JSON, "Invalid canonical file")
            elif top.name in ("tasks", "inbox"):
                require(top.is_dir(), "Invalid memory directory")
                count = 0
                for item in top.iterdir():
                    if item in slots and not item.is_symlink():
                        continue
                    count += 1
                    require(count <= (MAX_TASKS if top.name == "tasks" else MAX_ASSIGNMENTS), "Memory file count exceeded")
                    require(not item.is_symlink() and item.is_file(), "Unsafe memory child")
                    require(item.name.endswith(".json") and KEY.fullmatch(item.name[:-5]), "Invalid memory child path")
                    limit = MAX_JSON if top.name == "tasks" else MAX_RESULT
                    require(item.stat().st_size <= limit, "Oversized local memory payload")
            else:
                raise ADPError("Storage contains unexpected files; refusing to modify it")

    def _local(self, *, dirty: bool = False, _accounting_inspection=False) -> tuple[str, dict, dict[str, dict]]:
        if _accounting_inspection:
            self._layout(_accounting_inspection=True)
        else:
            self._layout()
        head = value(self.path, "rev-parse", "HEAD")
        state, tasks = self._read_ref(head)
        if not dirty:
            require(not value(self.path, "status", "--porcelain", "--untracked-files=all"), "Memory has uncommitted changes; inspect recovery")
            require(load_json(self.path / "state.json") == state, "Canonical state differs from commit")
            directory = self.path / "tasks"
            actual = {item.stem: load_json(item) for item in directory.iterdir()} if directory.exists() else {}
            require(actual == tasks, "Task files differ from commit")
            require((self.path / ".gitignore").read_bytes() == IGNORE, "Ignore rules differ from commit")
        return head, state, tasks

    def _recovery_document(self, *, protected=False) -> dict | None:
        path = safe_path(self.control / "pending.json")
        if not path.exists():
            return None
        pending = load_json(path, MAX_JOURNAL, protected=True) if protected else load_json(path, MAX_JOURNAL)
        if "schema_version" in pending:
            pending = load_json(path, MAX_JOURNAL, protected=True)
            fields(pending, "schema_version base state tasks policy_fence")
            require(type(pending["schema_version"]) is int and pending["schema_version"] == 2,
                    "Unsupported local recovery journal")
            self._journal_purpose(pending["policy_fence"])
        else:
            fields(pending, "base state tasks")
        require(isinstance(pending["base"], str) and SHA.fullmatch(pending["base"]), "Invalid recovery base")
        bundle(pending["state"], pending["tasks"], self.config.identity)
        return pending

    @staticmethod
    def _journal_purpose(purpose):
        fields(purpose, "policy stage subject")
        require(purpose["policy"] == "ACCOUNTING_EXPIRY_CONTINUATION" and purpose["stage"] in ("guard", "result", "episode")
                and type(purpose["subject"]) is str and KEY.fullmatch(purpose["subject"]), "Invalid exact-purpose recovery binding")

    @staticmethod
    def _journal_fence(pending, purpose, fence, before_effects=None, *, recovering=False):
        if "schema_version" in pending or "policy_fence" in pending:
            fields(pending, "schema_version base state tasks policy_fence")
            require(type(pending["schema_version"]) is int and pending["schema_version"] == 2, "Unsupported local recovery journal")
            Memory._journal_purpose(pending["policy_fence"])
            require(purpose == pending["policy_fence"] and callable(fence)
                    and (not recovering or callable(before_effects)),
                    "Use separately approved exact-purpose accounting reconciliation; ordinary recovery is refused")
        else:
            fields(pending, "base state tasks")

    def _recovery_slots(self, pending, tasks):
        if pending is not None:
            return [(self.path / "state.json", MAX_JSON),
                    *((self.path / "tasks" / (task_key + ".json"), MAX_JSON) for task_key in pending["tasks"])]
        return [(self.path / "inbox" / (key(assignment) + ".json"), MAX_RESULT)
                for task in tasks.values() for assignment in task["assignments"]]

    def inspect(self, *, recovery=False) -> dict:
        """Observe only: no locks, fetch, token creation, index refresh or refs."""
        remote = self._remote_head()
        if not self.path.exists():
            return {"health": "REMOTE_AVAILABLE" if remote else "UNINITIALIZED",
                    "remote_head": remote, "owner": None}
        slots = set()
        extra = {}
        if recovery:
            context = self._accounting_registered(head=True) if self._accounting_reads else None
            if context is None:
                self._registered()
                head = value(self.path, "rev-parse", "HEAD")
            else:
                _, head = context
            state, tasks = self._read_ref(head)
            pending = self._recovery_document(protected=True)
            slots = {slot for path, limit in self._recovery_slots(pending, tasks)
                     if (slot := interrupted_slot(path, limit)) is not None}
            if self._accounting_reads:
                self._layout(slots, _accounting_inspection=True)
            else:
                self._layout(slots)
            extra = {"recovery_slots": sorted(str(slot.relative_to(self.path)) for slot in slots),
                     "recovery_journal": hashlib.sha256(encode(pending, MAX_JOURNAL)).hexdigest() if pending is not None else None}
        else:
            if self._accounting_reads:
                head, state, tasks = self._local(dirty=True, _accounting_inspection=True)
            else:
                head, state, tasks = self._local(dirty=True)
        dirty = bool(value(self.path, "status", "--porcelain", "--untracked-files=all"))
        pending = (self.control / "pending.json").exists()
        return {"health": "RECOVERY_REQUIRED" if pending or dirty or slots else
                "SYNCED" if head == remote else "REMOTE_MISMATCH",
                "local_head": head, "remote_head": remote, "state": state,
                "tasks": tasks, "local_owner": self._owns(state["owner"]),
                "inbox_count": sum(item not in slots for item in self._inbox()), **extra}

    def initialize(self, *, authorized: bool = False, initial_only: bool = False) -> dict:
        from .personal_read_frame import forbid_writes
        forbid_writes()
        if not authorized:
            raise AuthorityError("init --apply requires explicit --authorize-memory-write")
        author(self.config.root)
        with locked(self.control):
            remote = self._remote_head()
            if initial_only:
                require(remote is None and not self.path.exists(),
                        "Guided enrollment cannot adopt an existing checkpoint or memory worktree")
            if self.path.exists() and any(self.path.iterdir()):
                head, _, _ = self._local()
                if remote != head:
                    raise Conflict("Existing memory differs from remote; inspect recovery")
                return self.inspect()
            refs = value(self.config.root, "for-each-ref", "--format=%(refname)", "refs/heads/" + self.branch).splitlines()
            require("refs/heads/" + self.branch not in refs, "Memory branch already exists locally; select its worktree or recover explicitly")
            if remote:
                self._remote_git(self.config.root, ("fetch", "--no-tags"), "refs/heads/" + self.branch)
                require(value(self.config.root, "rev-parse", "FETCH_HEAD") == remote, "Remote changed during initialization; inspect and retry")
                self._read_ref(remote)  # Validate before any checkout of remote data.
                commit = remote
            else:
                state = {"schema_version": 1, "repository_id": self.config.identity,
                         "revision": 1, "generation": 0, "owner": None,
                         "task_keys": [], "assignment_sequence": 0}
                state_blob = self._write_git(
                    self.config.root, "hash-object", "-w", "--stdin", input=encode(state)).decode().strip()
                ignore_blob = self._write_git(self.config.root, "hash-object", "-w", "--stdin", input=IGNORE).decode().strip()
                tree = self._write_git(self.config.root, "mktree", input=(
                    f"100644 blob {ignore_blob}\t.gitignore\n100644 blob {state_blob}\tstate.json\n").encode()).decode().strip()
                commit = self._write_git(self.config.root, "commit-tree", tree, "-m", "Initialize coordination memory").decode().strip()
            self._write_git(self.config.root, "worktree", "add", "-b", self.branch, str(self.path), commit)
            if not remote:
                self._push(None)
            return self.inspect()

    def _push(self, expected: str | None) -> None:
        if self._remote_head() != expected:
            raise Conflict("Remote memory changed; local checkpoint retained, no automatic reconciliation")
        self._remote_git(self.path, ("push", "--no-verify", "--no-follow-tags"), "HEAD:refs/heads/" + self.branch)
        if self._remote_head() != value(self.path, "rev-parse", "HEAD"):
            raise Conflict("Remote moved after push; publication is not confirmed")

    def _owns(self, owner: dict | None) -> bool:
        token = self.control / "owner.json"
        if owner is None or not token.exists():
            return False
        local = load_json(token, 1024)
        fields(local, "id secret")
        string(local["secret"], 128)
        return local["id"] == owner["id"] and hashlib.sha256(local["secret"].encode()).hexdigest() == owner["token_hash"]

    def _owner(self, state: dict) -> None:
        if not self._owns(state["owner"]):
            raise Conflict("Local owner credential missing or mismatched; no ownership inferred")

    def _start(self, *, owned: bool = True) -> tuple[str, dict, dict[str, dict]]:
        from .personal_read_frame import forbid_writes
        forbid_writes()
        author(self.config.root)
        if (self.control / "pending.json").exists():
            raise Conflict("An interrupted checkpoint requires explicit recover")
        head, state, tasks = self._local()
        if head != self._remote_head():
            raise Conflict("Remote memory differs; use explicit recovery, never auto-merge")
        if owned:
            self._owner(state)
        return head, copy.deepcopy(state), copy.deepcopy(tasks)

    def _write_files(self, state: dict, tasks: dict[str, dict], *, _fence=None) -> None:
        from .personal_read_frame import forbid_writes
        forbid_writes()
        self._layout()
        directory = self.path / "tasks"
        if _fence is not None:
            _fence()
        directory.mkdir(exist_ok=True)
        for task_key, task in tasks.items():
            if _fence is not None:
                _fence()
            atomic(directory / (task_key + ".json"), encode(task))
        for item in directory.iterdir():
            if item.stem not in tasks:
                if _fence is not None:
                    _fence()
                item.unlink()
        sync_directory(directory)
        if _fence is not None:
            _fence()
        atomic(self.path / "state.json", encode(state))

    def _checkpoint(self, head: str, state: dict, tasks: dict[str, dict], *, _fence=None, _purpose=None) -> dict:
        from .personal_read_frame import forbid_writes
        forbid_writes()
        if _fence is not None:
            _fence()
        previous, _ = self._read_ref(head)
        if previous.get("progress_guard", {}).get("schema_version") == 2:
            from .accounting_policy import entry
            old, new = entry(previous), entry(state)
            require(new is not None and {k: v for k, v in old.items() if k != "usage"} ==
                    {k: v for k, v in new.items() if k != "usage"}, "An accounting lineage cannot be replaced or renewed")
            before, after = old["usage"], new["usage"]
            require(all(after[n] >= before[n] for n in ("observations", "checks", "seconds", "samples", "payload_bytes"))
                    and all(after["requests"].get(k) == v for k, v in before["requests"].items())
                    and after["check_ids"][:len(before["check_ids"])] == before["check_ids"]
                    and previous["progress_guard"]["requirements"].keys() <= state["progress_guard"]["requirements"].keys(),
                    "Accounting consumption and admitted history are append-only")
            require(state["progress_guard"]["task_epochs"].get(old["parent_task"]) == previous["progress_guard"]["task_epochs"][old["parent_task"]]
                    and {k for k, v in state["progress_guard"]["requirements"].items() if old["parent_task"] in v["tasks"]} ==
                        {k for k, v in previous["progress_guard"]["requirements"].items() if old["parent_task"] in v["tasks"]}
                    and all(state["progress_guard"]["requirements"].get(k) == v for k, v in
                            previous["progress_guard"]["requirements"].items() if old["parent_task"] in v["tasks"]),
                    "All historical parent guard records and its epoch remain immutable")
        state["revision"] += 1
        state["task_keys"] = sorted(tasks)
        if state["schema_version"] in (2, 3):
            epochs = state["progress_guard"]["task_epochs"]
            state["progress_guard"]["task_epochs"] = {
                task_key: epochs.get(task_key, state["revision"]) for task_key in tasks}
        bundle(state, tasks, self.config.identity)
        pending = {"base": head, "state": state, "tasks": tasks}
        if _purpose is not None:
            self._journal_purpose(_purpose)
            require(callable(_fence), "Exact-purpose checkpoint requires live authority")
            pending.update(schema_version=2, policy_fence=copy.deepcopy(_purpose))
        if _fence is not None:
            _fence()
        atomic(self.control / "pending.json", encode(pending, MAX_JOURNAL))
        self._finish(pending, _fence=_fence, _purpose=_purpose)
        return self.inspect()

    def _finish(self, pending: dict, *, expected_remote=_UNREVIEWED_REMOTE, _fence=None, _purpose=None) -> None:
        from .personal_read_frame import forbid_writes
        forbid_writes()
        self._journal_fence(pending, _purpose, _fence)
        base, state, tasks = pending["base"], pending["state"], pending["tasks"]
        if expected_remote is not _UNREVIEWED_REMOTE:
            require(self._remote_head() == expected_remote, "Reviewed remote checkpoint changed before recovery")
        current = value(self.path, "rev-parse", "HEAD")
        if current == base:
            if _fence is not None:
                _fence()
            if _fence is None:
                self._write_files(state, tasks)
            else:
                self._write_files(state, tasks, _fence=_fence)
            if _fence is not None:
                _fence()
            self._write_git(self.path, "add", "--all", "--", "state.json", "tasks")
            if _fence is not None:
                _fence()
            self._write_git(self.path, "commit", "-m", f"Checkpoint coordination revision {state['revision']}")
        else:
            require(value(self.path, "rev-parse", "HEAD^") == base, "Pending checkpoint parent mismatch")
            stored_state, stored_tasks = self._read_ref(current)
            require(stored_state == state and stored_tasks == tasks, "Pending checkpoint differs from local commit")
            require(not value(self.path, "status", "--porcelain", "--untracked-files=all"), "Pending committed checkpoint has dirty files")
        remote = self._remote_head()
        require(expected_remote is _UNREVIEWED_REMOTE or remote == expected_remote,
                "Reviewed remote checkpoint changed during recovery")
        if remote != value(self.path, "rev-parse", "HEAD"):
            if _fence is not None:
                _fence()
            self._push(base)
        if _fence is not None:
            _fence()
        (self.control / "pending.json").unlink()
        sync_directory(self.control)

    def claim(self, label: str, *, takeover: bool = False,
              confirmed_stopped_owner: str | None = None, initial_only: bool = False) -> dict:
        string(label, 128)
        with locked(self.control):
            head, state, tasks = self._start(owned=False)
            if self._owns(state["owner"]):
                return self.inspect()
            require(state.get("progress_guard", {}).get("schema_version") != 2,
                    "An accounting episode cannot change its original owner generation")
            if initial_only:
                require(state["owner"] is None and state["generation"] == 0 and state["revision"] == 1
                        and state["schema_version"] == 1 and not tasks and not takeover,
                        "Guided enrollment cannot reclaim previously released ownership")
            if state["owner"] is not None:
                if not takeover or confirmed_stopped_owner != state["owner"]["id"]:
                    raise Conflict("Takeover requires --takeover and --confirm-stopped-owner matching the current owner ID")
            elif takeover:
                raise Conflict("There is no owner to take over")
            secret = secrets.token_hex(32)
            owner = {"id": uuid.uuid4().hex, "label": label,
                     "token_hash": hashlib.sha256(secret.encode()).hexdigest()}
            atomic(self.control / "owner.json", encode({"id": owner["id"], "secret": secret}, 1024))
            state["generation"] += 1
            state["owner"] = owner
            self._invalidate(tasks)
            return self._checkpoint(head, state, tasks)

    @staticmethod
    def _invalidate(tasks: dict[str, dict]) -> None:
        for task in tasks.values():
            for assignment in task["assignments"].values():
                if assignment["status"] == "pending":
                    assignment["status"] = "incomplete"

    def handoff(self) -> dict:
        with locked(self.control):
            head, state, tasks = self._start()
            if state["schema_version"] == 3:
                if state["execution"]["schema_version"] == 3:
                    require(all(effect["status"] == "OBSERVED" for effect in state["execution"]["ticket_effects"].values()),
                            "Reconcile all ticket effects before owner handoff")
                require(all(j["status"] in ("COMPLETE", "CANCELLED") and j["validation_stop"] not in ("RUNNING", "UNKNOWN") for t in state["execution"]["tasks"].values()
                            for j in t["jobs"].values()) and all(a["status"] == "OBSERVED" for a in state["execution"]["actions"].values()),
                        "Observe/cancel execution and reconcile external effects before handoff")
            if self._inbox():
                raise Conflict("Process local inbox results before voluntary handoff")
            self._invalidate(tasks)
            state["owner"] = None
            return self._checkpoint(head, state, tasks)

    def recover(self, *, before_effects=None, expected_remote=_UNREVIEWED_REMOTE, validate_states=None, _fence=None, _purpose=None) -> dict:
        """Explicitly publish a validated pending transaction or fast-forward sync.

        A missing owner is never repaired by recovery. Released/foreign owners
        may sync; an owned local checkpoint requires its original credential.
        """
        from .personal_read_frame import forbid_writes
        forbid_writes()
        author(self.config.root)
        with locked(self.control):
            initial_pending = self._recovery_document(protected=expected_remote is not _UNREVIEWED_REMOTE)
            if initial_pending is not None:
                self._journal_fence(initial_pending, _purpose, _fence, before_effects, recovering=True)
            if before_effects is not None:
                before_effects()
            self._registered()
            guarded = expected_remote is not _UNREVIEWED_REMOTE
            if guarded:
                require(self._remote_head() == expected_remote, "Reviewed remote checkpoint changed before recovery")
            pending = self._recovery_document(protected=guarded)
            require(pending == initial_pending, "Pending recovery purpose/subject changed")
            if pending is not None:
                previous, _ = self._read_ref(pending["base"])
                require(pending["state"]["revision"] == previous["revision"] + 1, "Invalid pending revision")
                if not (self._owns(previous["owner"]) or self._owns(pending["state"]["owner"])):
                    raise Conflict("Recovery requires the original local owner credential")
                if validate_states is not None:
                    validate_states(previous, pending["state"])
                # Only destinations named in this validated owned transaction
                # may have their private scratch slots removed.
                for path, limit in self._recovery_slots(pending, {}):
                    if _fence is not None:
                        _fence()
                    clear_slot(path, limit)
                if guarded:
                    self._finish(pending, expected_remote=expected_remote, _fence=_fence, _purpose=_purpose)
                else:
                    self._finish(pending, _fence=_fence, _purpose=_purpose)
            else:
                committed, committed_tasks = self._read_ref(value(self.path, "rev-parse", "HEAD"))
                if validate_states is not None:
                    validate_states(committed)
                for path, limit in self._recovery_slots(None, committed_tasks):
                    if _fence is not None:
                        _fence()
                    clear_slot(path, limit)
                head, state, _ = self._local()
                remote = self._remote_head()
                require(expected_remote is _UNREVIEWED_REMOTE or remote == expected_remote,
                        "Reviewed remote checkpoint changed before recovery")
                if remote == head:
                    return self.inspect()
                if remote is None:
                    # Only a pristine, unowned initialization may republish an
                    # absent remote. A deleted owned branch is a conflict.
                    require(state["revision"] == 1 and state["owner"] is None,
                            "Remote memory is missing; explicit operator reconciliation required")
                    self._push(None)
                else:
                    if guarded:
                        self._remote_git(self.config.root, ("fetch", "--no-tags", "--no-recurse-submodules",
                                         "--refmap=", "--no-prune", "--no-write-fetch-head", "--no-auto-maintenance"), remote)
                        require(self._remote_head() == remote, "Reviewed remote checkpoint changed while fetching")
                    else:
                        self._remote_git(self.config.root, ("fetch", "--no-tags"), "refs/heads/" + self.branch)
                        require(value(self.config.root, "rev-parse", "FETCH_HEAD") == remote, "Remote changed while recovering")
                    recovered, _ = self._read_ref(remote)
                    if validate_states is not None:
                        validate_states(recovered)
                    # --is-ancestor returns nonzero on divergence, surfaced as a
                    # controlled conflict rather than an automatic merge.
                    try:
                        git(self.path, "merge-base", "--is-ancestor", head, remote)
                    except GitError as exc:
                        raise Conflict("Divergent memory histories require operator reconciliation") from exc
                    if self._inbox():
                        raise Conflict("Local inbox would be stranded by synchronization")
                    self._write_git(self.path, "merge", "--ff-only", "--no-edit", remote)
            return self.inspect()

    def add_task(self, identifier: str, source_revision: str | None = None) -> dict:
        task_key = key(identifier)
        with locked(self.control):
            head, state, tasks = self._start()
            if task_key in tasks:
                raise Conflict("Task already exists")
            tasks[task_key] = {"schema_version": 1, "key": task_key, "id": identifier,
                "repository_id": self.config.identity, "iteration": 1, "phase": "active",
                "source_revision": source_revision, "assignments": {}, "blockers": [],
                "last_published_iteration": None}
            return self._checkpoint(head, state, tasks)

    def set_revision(self, identifier: str, revision: str) -> dict:
        with locked(self.control):
            head, state, tasks = self._start()
            task = self._task(tasks, identifier)
            if revision == task["source_revision"]:
                return self.inspect()
            self._invalidate({task["key"]: task})
            task["source_revision"] = revision
            task["iteration"] += 1
            return self._checkpoint(head, state, tasks)

    @staticmethod
    def _task(tasks: dict[str, dict], identifier: str) -> dict:
        try:
            return tasks[key(identifier)]
        except KeyError as exc:
            raise Conflict("Task is not active") from exc

    def assign(self, identifier: str, worker: str) -> dict:
        string(worker, 128)
        with locked(self.control):
            head, state, tasks = self._start()
            result = self._assign(state, tasks, identifier, worker)
            self._checkpoint(head, state, tasks)
            return result

    def _assign(self, state, tasks, identifier, worker):
        """Existing transition for callers already holding the canonical lock."""
        task = self._task(tasks, identifier)
        if task["source_revision"] is None:
            raise Conflict("Assignment requires an exact source revision")
        state["assignment_sequence"] += 1
        job_id = f"{state['generation']}-{state['assignment_sequence']}"
        task["assignments"][job_id] = {"generation": state["generation"], "worker": worker,
            "source_revision": task["source_revision"], "status": "pending", "result": None}
        return {"assignment_id": job_id, "generation": state["generation"], "task_key": task["key"],
                "worker": worker, "source_revision": task["source_revision"]}

    def _inbox(self) -> list[Path]:
        directory = safe_path(self.path / "inbox")
        return sorted(directory.iterdir()) if directory.exists() else []

    @staticmethod
    def _envelope(envelope: dict, state: dict, tasks: dict[str, dict]) -> dict:
        fields(envelope, "schema_version task_key assignment_id generation worker source_revision result")
        require(type(envelope["schema_version"]) is int and envelope["schema_version"] == 1, "Invalid result schema")
        require(isinstance(envelope["task_key"], str) and envelope["task_key"] in tasks, "Unknown result task")
        task = tasks[envelope["task_key"]]
        require(isinstance(envelope["assignment_id"], str), "Invalid result assignment")
        job = task["assignments"].get(envelope["assignment_id"])
        if (job is None or job["status"] != "pending"
                or type(envelope["generation"]) is not int
                or envelope["generation"] != state["generation"]
                or envelope["generation"] != job["generation"]
                or envelope["source_revision"] != job["source_revision"]
                or envelope["source_revision"] != task["source_revision"]
                or envelope["worker"] != job["worker"]):
            raise Conflict("Result is terminal, stale, or mismatches its exact assignment")
        result_schema(envelope["result"])
        encode(envelope, MAX_RESULT)
        return job

    def deliver(self, envelope: dict) -> Path:
        """Worker-only immutable local delivery; never writes canonical state."""
        from .personal_read_frame import forbid_writes
        forbid_writes()
        with locked(self.control):
            _, state, tasks = self._local()
            return self._deliver(envelope, state, tasks)

    def _deliver(self, envelope, state, tasks):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        self._envelope(envelope, state, tasks)
        inbox = self.path / "inbox"
        inbox.mkdir(exist_ok=True, mode=0o700)
        require(len(self._inbox()) < MAX_ASSIGNMENTS, "Local inbox capacity exceeded")
        path = inbox / (key(envelope["assignment_id"]) + ".json")
        try:
            atomic(path, encode(envelope, MAX_RESULT), replace=False)
        except FileExistsError as exc:
            raise Conflict("Duplicate immutable inbox delivery") from exc
        return path

    def accept(self, assignment_id: str) -> dict:
        with locked(self.control):
            head, state, tasks = self._start()
            path = self.path / "inbox" / (key(assignment_id) + ".json")
            envelope = load_json(path, MAX_RESULT)
            require(envelope.get("assignment_id") == assignment_id, "Inbox identity mismatch")
            self._accept_result(envelope, state, tasks)
            self._checkpoint(head, state, tasks)
            path.unlink()
            sync_directory(path.parent)
            return self.inspect()

    def _accept_result(self, envelope, state, tasks):
        job = self._envelope(envelope, state, tasks)
        job["status"] = "accepted"
        job["result"] = envelope["result"]

    def cleanup_inbox(self) -> dict:
        """Remove only deliveries already durably accepted with identical content."""
        from .personal_read_frame import forbid_writes
        forbid_writes()
        with locked(self.control):
            _, state, tasks = self._start()
            for path in self._inbox():
                envelope = load_json(path, MAX_RESULT)
                fields(envelope, "schema_version task_key assignment_id generation worker source_revision result")
                require(isinstance(envelope["task_key"], str) and isinstance(envelope["assignment_id"], str), "Invalid inbox identity")
                require(path.stem == key(envelope["assignment_id"]), "Inbox filename/identity mismatch")
                result_schema(envelope["result"])
                task = tasks.get(envelope["task_key"])
                job = task["assignments"].get(envelope["assignment_id"]) if task else None
                if (job is None or job["status"] != "accepted" or job["result"] != envelope["result"]
                        or job["generation"] != envelope["generation"] or job["worker"] != envelope["worker"]
                        or job["source_revision"] != envelope["source_revision"]):
                    raise Conflict("Unprocessed/stale inbox material requires explicit disposition")
                path.unlink()
            return self.inspect()

    def retire(self, identifier: str, *, evidence: str, confirmed: bool = False) -> dict:
        string(evidence, 512)
        if not confirmed:
            raise AuthorityError("Retirement requires confirmation of observed durable product disposition")
        with locked(self.control):
            head, state, tasks = self._start()
            task = self._task(tasks, identifier)
            if self._inbox() or any(j["status"] == "pending" for j in task["assignments"].values()):
                raise Conflict("Process inbox and finish or invalidate assignments before retirement")
            del tasks[task["key"]]
            return self._checkpoint(head, state, tasks)

    def discard_inbox(self, assignment_id: str, *, confirmed: bool = False) -> dict:
        """Explicitly acknowledge loss of local delivery, without accepting it."""
        from .personal_read_frame import forbid_writes
        forbid_writes()
        if not confirmed:
            raise AuthorityError("Discard requires --confirm-incomplete; no result will be accepted")
        with locked(self.control):
            self._local(dirty=True)
            path = self.path / "inbox" / (key(assignment_id) + ".json")
            # A crafted/malformed delivery can also be removed by exact opaque ID.
            require(path.is_file() and not path.is_symlink(), "Delivery does not exist")
            path.unlink()
            sync_directory(path.parent)
            return self.inspect()

    def upgrade_guard(self, *, authorized: bool = False) -> dict:
        """Explicit owner-only v1 -> v2 upgrade; M1 tasks are unchanged."""
        if not authorized:
            raise AuthorityError("Guard migration requires explicit memory-write authorization")
        with locked(self.control):
            head, state, tasks = self._start()
            if state["schema_version"] in (2, 3):
                return self.inspect()
            require(state["schema_version"] == 1, "Unsupported migration source")
            state["schema_version"] = 2
            state["progress_guard"] = {"schema_version": 1, "requirements": {},
                                       "task_epochs": {task_key: state["revision"] + 1 for task_key in tasks}}
            return self._checkpoint(head, state, tasks)
