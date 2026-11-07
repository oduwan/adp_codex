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
from .storage import atomic, locked, sync_directory

IGNORE = b"/inbox/\n"


class Memory:
    """All mutations affect only the selected memory branch and local controls.

    The caller must supply explicit operator authority for initialization and
    exceptional takeover. Git is an optimistic checkpoint transport, not a lease.
    """

    def __init__(self, config: Config):
        self.config = config
        self.branch, self.path = config.require_storage()
        common = Path(value(config.root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        self.control = safe_path(common / "adp" / key(self.branch))

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
        for name, sha in blobs.items():
            require(int(value(self.config.root, "cat-file", "-s", sha)) <= MAX_JSON, "Oversized memory blob")
            values[name] = git(self.config.root, "cat-file", "blob", sha, limit=MAX_JSON)
        require(values.pop(".gitignore") == IGNORE, "Unexpected memory ignore rules")
        state = decode(values.pop("state.json"))
        tasks = {name[6:-5]: decode(raw) for name, raw in values.items()}
        bundle(state, tasks, self.config.identity)
        return state, tasks

    def _registered(self) -> None:
        safe_path(self.path)
        require(self.path.is_dir(), "Memory worktree is absent; use authorized init --apply")
        actual = value(self.path, "rev-parse", "--show-toplevel")
        require(Path(actual) == self.path, "Storage is not the selected memory worktree")
        common = value(self.path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        require(Path(common) == self.control.parent.parent, "Memory belongs to another repository")
        require(value(self.path, "symbolic-ref", "HEAD") == "refs/heads/" + self.branch, "Memory branch mismatch")

    def _layout(self) -> None:
        self._registered()
        # os.scandir does not follow directory symlinks. Reject before recursion.
        for top in self.path.iterdir():
            require(not top.is_symlink(), "Symlinked memory entry")
            if top.name == ".git":
                require(top.is_file(), "Unexpected Git directory in linked memory")
            elif top.name in ("state.json", ".gitignore"):
                require(top.is_file() and top.stat().st_size <= MAX_JSON, "Invalid canonical file")
            elif top.name in ("tasks", "inbox"):
                require(top.is_dir(), "Invalid memory directory")
                count = 0
                for item in top.iterdir():
                    count += 1
                    require(count <= (MAX_TASKS if top.name == "tasks" else MAX_ASSIGNMENTS), "Memory file count exceeded")
                    require(not item.is_symlink() and item.is_file(), "Unsafe memory child")
                    require(item.name.endswith(".json") and KEY.fullmatch(item.name[:-5]), "Invalid memory child path")
                    limit = MAX_JSON if top.name == "tasks" else MAX_RESULT
                    require(item.stat().st_size <= limit, "Oversized local memory payload")
            else:
                raise ADPError("Storage contains unexpected files; refusing to modify it")

    def _local(self, *, dirty: bool = False) -> tuple[str, dict, dict[str, dict]]:
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

    def inspect(self) -> dict:
        """Observe only: no locks, fetch, token creation, index refresh or refs."""
        remote = self.config.remote_head()
        if not self.path.exists():
            return {"health": "REMOTE_AVAILABLE" if remote else "UNINITIALIZED",
                    "remote_head": remote, "owner": None}
        head, state, tasks = self._local(dirty=True)
        dirty = bool(value(self.path, "status", "--porcelain", "--untracked-files=all"))
        pending = (self.control / "pending.json").exists()
        return {"health": "RECOVERY_REQUIRED" if pending or dirty else
                "SYNCED" if head == remote else "REMOTE_MISMATCH",
                "local_head": head, "remote_head": remote, "state": state,
                "tasks": tasks, "local_owner": self._owns(state["owner"]),
                "inbox_count": len(self._inbox())}

    def initialize(self, *, authorized: bool = False) -> dict:
        if not authorized:
            raise AuthorityError("init --apply requires explicit --authorize-memory-write")
        author(self.config.root)
        with locked(self.control):
            remote = self.config.remote_head()
            if self.path.exists() and any(self.path.iterdir()):
                head, _, _ = self._local()
                if remote != head:
                    raise Conflict("Existing memory differs from remote; inspect recovery")
                return self.inspect()
            refs = value(self.config.root, "for-each-ref", "--format=%(refname)", "refs/heads/" + self.branch).splitlines()
            require("refs/heads/" + self.branch not in refs, "Memory branch already exists locally; select its worktree or recover explicitly")
            if remote:
                git(self.config.root, "fetch", "--no-tags", self.config.remote, "refs/heads/" + self.branch)
                require(value(self.config.root, "rev-parse", "FETCH_HEAD") == remote, "Remote changed during initialization; inspect and retry")
                self._read_ref(remote)  # Validate before any checkout of remote data.
                commit = remote
            else:
                state = {"schema_version": 1, "repository_id": self.config.identity,
                         "revision": 1, "generation": 0, "owner": None,
                         "task_keys": [], "assignment_sequence": 0}
                state_blob = git(
                    self.config.root, "hash-object", "-w", "--stdin", input=encode(state)).decode().strip()
                ignore_blob = git(self.config.root, "hash-object", "-w", "--stdin", input=IGNORE).decode().strip()
                tree = git(self.config.root, "mktree", input=(
                    f"100644 blob {ignore_blob}\t.gitignore\n100644 blob {state_blob}\tstate.json\n").encode()).decode().strip()
                commit = git(self.config.root, "commit-tree", tree, "-m", "Initialize coordination memory").decode().strip()
            git(self.config.root, "worktree", "add", "-b", self.branch, str(self.path), commit)
            if not remote:
                self._push(None)
            return self.inspect()

    def _push(self, expected: str | None) -> None:
        if self.config.remote_head() != expected:
            raise Conflict("Remote memory changed; local checkpoint retained, no automatic reconciliation")
        git(self.path, "push", "--no-verify", "--no-follow-tags", self.config.remote,
            "HEAD:refs/heads/" + self.branch)
        if self.config.remote_head() != value(self.path, "rev-parse", "HEAD"):
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
        author(self.config.root)
        if (self.control / "pending.json").exists():
            raise Conflict("An interrupted checkpoint requires explicit recover")
        head, state, tasks = self._local()
        if head != self.config.remote_head():
            raise Conflict("Remote memory differs; use explicit recovery, never auto-merge")
        if owned:
            self._owner(state)
        return head, copy.deepcopy(state), copy.deepcopy(tasks)

    def _write_files(self, state: dict, tasks: dict[str, dict]) -> None:
        self._layout()
        directory = self.path / "tasks"
        directory.mkdir(exist_ok=True)
        for task_key, task in tasks.items():
            atomic(directory / (task_key + ".json"), encode(task))
        for item in directory.iterdir():
            if item.stem not in tasks:
                item.unlink()
        sync_directory(directory)
        atomic(self.path / "state.json", encode(state))

    def _checkpoint(self, head: str, state: dict, tasks: dict[str, dict]) -> dict:
        state["revision"] += 1
        state["task_keys"] = sorted(tasks)
        bundle(state, tasks, self.config.identity)
        pending = {"base": head, "state": state, "tasks": tasks}
        atomic(self.control / "pending.json", encode(pending, MAX_JOURNAL))
        self._finish(pending)
        return self.inspect()

    def _finish(self, pending: dict) -> None:
        base, state, tasks = pending["base"], pending["state"], pending["tasks"]
        current = value(self.path, "rev-parse", "HEAD")
        if current == base:
            self._write_files(state, tasks)
            git(self.path, "add", "--all", "--", "state.json", "tasks")
            git(self.path, "commit", "-m", f"Checkpoint coordination revision {state['revision']}")
        else:
            require(value(self.path, "rev-parse", "HEAD^") == base, "Pending checkpoint parent mismatch")
            stored_state, stored_tasks = self._read_ref(current)
            require(stored_state == state and stored_tasks == tasks, "Pending checkpoint differs from local commit")
            require(not value(self.path, "status", "--porcelain", "--untracked-files=all"), "Pending committed checkpoint has dirty files")
        remote = self.config.remote_head()
        if remote != value(self.path, "rev-parse", "HEAD"):
            self._push(base)
        (self.control / "pending.json").unlink()
        sync_directory(self.control)

    def claim(self, label: str, *, takeover: bool = False,
              confirmed_stopped_owner: str | None = None) -> dict:
        string(label, 128)
        with locked(self.control):
            head, state, tasks = self._start(owned=False)
            if self._owns(state["owner"]):
                return self.inspect()
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
            if self._inbox():
                raise Conflict("Process local inbox results before voluntary handoff")
            self._invalidate(tasks)
            state["owner"] = None
            return self._checkpoint(head, state, tasks)

    def recover(self) -> dict:
        """Explicitly publish a validated pending transaction or fast-forward sync.

        A missing owner is never repaired by recovery. Released/foreign owners
        may sync; an owned local checkpoint requires its original credential.
        """
        author(self.config.root)
        with locked(self.control):
            self._layout()
            pending_path = self.control / "pending.json"
            if pending_path.exists():
                pending = load_json(pending_path, MAX_JOURNAL)
                fields(pending, "base state tasks")
                require(isinstance(pending["base"], str) and SHA.fullmatch(pending["base"]), "Invalid recovery base")
                bundle(pending["state"], pending["tasks"], self.config.identity)
                previous, _ = self._read_ref(pending["base"])
                require(pending["state"]["revision"] == previous["revision"] + 1, "Invalid pending revision")
                if not (self._owns(previous["owner"]) or self._owns(pending["state"]["owner"])):
                    raise Conflict("Recovery requires the original local owner credential")
                self._finish(pending)
            else:
                head, state, _ = self._local()
                remote = self.config.remote_head()
                if remote == head:
                    return self.inspect()
                if remote is None:
                    # Only a pristine, unowned initialization may republish an
                    # absent remote. A deleted owned branch is a conflict.
                    require(state["revision"] == 1 and state["owner"] is None,
                            "Remote memory is missing; explicit operator reconciliation required")
                    self._push(None)
                else:
                    git(self.config.root, "fetch", "--no-tags", self.config.remote, "refs/heads/" + self.branch)
                    require(value(self.config.root, "rev-parse", "FETCH_HEAD") == remote, "Remote changed while recovering")
                    self._read_ref(remote)
                    # --is-ancestor returns nonzero on divergence, surfaced as a
                    # controlled conflict rather than an automatic merge.
                    try:
                        git(self.path, "merge-base", "--is-ancestor", head, remote)
                    except GitError as exc:
                        raise Conflict("Divergent memory histories require operator reconciliation") from exc
                    if self._inbox():
                        raise Conflict("Local inbox would be stranded by synchronization")
                    git(self.path, "merge", "--ff-only", "--no-edit", remote)
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
            task = self._task(tasks, identifier)
            if task["source_revision"] is None:
                raise Conflict("Assignment requires an exact source revision")
            state["assignment_sequence"] += 1
            job_id = f"{state['generation']}-{state['assignment_sequence']}"
            task["assignments"][job_id] = {"generation": state["generation"],
                "worker": worker, "source_revision": task["source_revision"],
                "status": "pending", "result": None}
            self._checkpoint(head, state, tasks)
            return {"assignment_id": job_id, "generation": state["generation"],
                    "task_key": task["key"], "worker": worker,
                    "source_revision": task["source_revision"]}

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
        with locked(self.control):
            _, state, tasks = self._local()
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
            job = self._envelope(envelope, state, tasks)
            job["status"] = "accepted"
            job["result"] = envelope["result"]
            outcome = self._checkpoint(head, state, tasks)
            path.unlink()
            sync_directory(path.parent)
            return outcome

    def cleanup_inbox(self) -> dict:
        """Remove only deliveries already durably accepted with identical content."""
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
