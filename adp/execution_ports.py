"""Narrow observed Git/forge effects. No merge, release, deployment or force."""
from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .config import load_json, remote_identity, safe_path
from .discovery_schema import digest
from .errors import ADPError
from .execution_types import ExternalObservation, ValidationResult
from .git import author, git, value
from .guard_types import Outcome, data
from .policy_adapters import working_tree_digest
from .policy_types import Effect, Operation, OutcomeCount
from .schema import decode, encode, fields, integer, require
from .storage import atomic, locked


class UnconfirmedValidation(ADPError):
    def __init__(self, reference, artifact_path):
        super().__init__("Validation stop is unconfirmed; remaining inventory NOTRUN")
        self.reference, self.artifact_path = reference, artifact_path
        self.results = ()


@contextmanager
def supervised_validation(argv, seconds):
    temporary = tempfile.TemporaryDirectory(prefix="adp-validation-supervisor-")
    try:
        directory = temporary.name
        path = Path(directory) / "stop.json"
        subject = digest(argv)
        command = (sys.executable, str(Path(__file__).with_name("execution_supervisor.py")),
            "--receipt", str(path), "--request-digest", subject, "--seconds", str(seconds), "--", *argv)
        yield command, path, subject
    except UnconfirmedValidation:
        temporary._finalizer.detach()  # Private forensic evidence, never product output.
        raise
    finally:
        if temporary._finalizer.alive:
            temporary.cleanup()


def validation_stopped(path, subject, pid):
    try:
        observed = load_json(path, 2048) if path.exists() else {}
    except (ADPError, OSError):
        observed = {}
    if not (type(observed) is dict and observed.get("stopped") is True
            and observed.get("request_digest") == subject and observed.get("pid") == pid):
        raise UnconfirmedValidation("validation:" + subject, str(path.parent))
    return observed


def index_digest(root):
    return hashlib.sha256(git(root, "ls-files", "--stage", "-z")).hexdigest()


def tree_index_digest(root, revision):
    entries = []
    for entry in filter(None, git(root, "ls-tree", "-rz", revision).split(b"\0")):
        metadata, path = entry.split(b"\t", 1)
        mode, kind, sha = metadata.split()
        require(kind in (b"blob", b"commit"), "Unsupported tree entry")
        entries.append((path, mode + b" " + sha + b" 0\t" + path + b"\0"))
    return hashlib.sha256(b"".join(raw for _, raw in sorted(entries))).hexdigest()


class GitExecutionPort:
    """Real local Git effects. Network push requires another strict-CAS port.

    Local push destinations must be explicitly allowlisted bare repositories.
    Immutable object transfer is followed by update-ref's exact old-SHA CAS.
    No force/lease option or unadvertised temporary ref is used.
    """
    def __init__(self, config, *, local_remotes=()):
        self.config = config
        self.root = config.root
        self.local_remotes = tuple(safe_path(Path(p)) for p in local_remotes)

    def _remote(self):
        endpoint = value(self.root, "remote", "get-url", self.config.remote)
        identity = remote_identity(endpoint, self.root)
        require(identity.startswith("file:"), "UNSUPPORTED_ATOMIC_REF: network push needs an exact-CAS backend")
        path = safe_path(Path(identity[5:]))
        require(path in self.local_remotes and value(path, "rev-parse", "--is-bare-repository") == "true",
                "Local remote is not explicitly authorized")
        return path

    def observe(self, action):
        root, operation, payload = self.root, action["operation"], action["payload"]
        head = value(root, "rev-parse", "HEAD")
        source = value(root, "symbolic-ref", "HEAD")
        if source != action["source_ref"]:
            return ExternalObservation("UNKNOWN")
        if operation == Operation.STAGE:
            unstaged = git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "--", *payload["paths"])
            new = git(root, "ls-files", "--others", "--exclude-standard", "--", *payload["paths"])
            if not unstaged and not new and head == action["revision"]:
                return ExternalObservation("PRESENT", "index:" + index_digest(root), head)
            if head == action["revision"] and index_digest(root) == payload["index_digest"] and working_tree_digest(root) == payload["worktree_digest"]:
                return ExternalObservation("ABSENT")
            return ExternalObservation("UNKNOWN")
        if operation == Operation.COMMIT:
            if head == action["revision"]:
                return ExternalObservation("ABSENT")
            parent = value(root, "rev-parse", "HEAD^")
            message = payload["subject"] + ("\n\n" + payload["body"] if payload["body"] else "")
            if (parent == action["revision"] and tree_index_digest(root, head) == payload["index_digest"]
                    and value(root, "log", "-1", "--format=%B") == message.strip()):
                return ExternalObservation("PRESENT", "commit:" + head, head)
            return ExternalObservation("UNKNOWN")
        if operation == Operation.BRANCH:
            refs = value(root, "for-each-ref", "--format=%(objectname)", action["target"]).splitlines()
            if refs == [payload["start_revision"]]:
                return ExternalObservation("PRESENT", action["target"], refs[0])
            return ExternalObservation("ABSENT" if not refs else "UNKNOWN")
        if operation == Operation.PUSH:
            remote = self._remote()
            refs = value(remote, "for-each-ref", "--format=%(objectname)", action["target"]).splitlines()
            old = refs[0] if len(refs) == 1 else None
            if old == action["revision"]:
                return ExternalObservation("PRESENT", action["target"], old)
            return ExternalObservation("ABSENT" if old == action["expected_target"] else "UNKNOWN")
        raise ADPError("Unsupported Git execution operation")

    def submit(self, action, provider, plan, authorization):
        require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Fresh exact-operation M3 authorization is required")
        require(plan.request.operation == action["operation"] and plan.task.revision == action["revision"], "Execution plan changed")
        require(plan.task.repository_id == self.config.identity and provider.adapter.config.root == self.root
                and plan.task.source_ref == action["source_ref"] and plan.target_ref == action["target"]
                and plan.expected_target == action["expected_target"] and data(plan.payload) == action["payload"],
                "Execution effect differs from the exact authorized plan")
        require(value(self.root, "rev-parse", "HEAD") == action["revision"]
                and value(self.root, "symbolic-ref", "HEAD") == action["source_ref"], "Source drift before Git mutation")
        payload, operation = action["payload"], action["operation"]
        if operation == Operation.STAGE:
            require(index_digest(self.root) == payload["index_digest"]
                    and working_tree_digest(self.root) == payload["worktree_digest"], "Staging content/index changed")
            require(all(not (self.root / p).is_dir() for p in payload["paths"]), "Stage explicit files, not an unbounded directory")
            git(self.root, "add", "--", *payload["paths"])
        elif operation == Operation.COMMIT:
            author(self.root)
            require(index_digest(self.root) == payload["index_digest"], "Commit index changed")
            tree = value(self.root, "write-tree")
            if tree == value(self.root, "rev-parse", "HEAD^{tree}"):
                return ExternalObservation("PRESENT", "commit:" + action["revision"], action["revision"])
            message = payload["subject"] + ("\n\n" + payload["body"] if payload["body"] else "")
            commit = git(self.root, "commit-tree", tree, "-p", action["revision"], "-F", "-", input=message.encode()).decode().strip()
            git(self.root, "update-ref", action["source_ref"], commit, action["revision"])
        elif operation == Operation.BRANCH:
            require(not payload["reuse"], "Existing branch requires observation, not overwrite")
            git(self.root, "update-ref", action["target"], payload["start_revision"], "0" * len(action["revision"]))
        elif operation == Operation.PUSH:
            remote = self._remote()
            # Copy immutable objects only; create no FETCH_HEAD or tracking ref.
            git(remote, "fetch", "--no-tags", "--no-write-fetch-head", "--no-auto-maintenance", str(self.root), action["revision"])
            git(remote, "update-ref", action["target"], action["revision"], action["expected_target"] or "0" * len(action["revision"]))
        else:
            raise ADPError("No merge, release, deployment or force execution port exists")
        return self.observe(action)


class LocalForgeBackend:
    """Disposable durable forge with atomic idempotency; never contacts GitHub."""
    def __init__(self, directory: Path):
        self.directory = safe_path(directory)
        self.lose_response = False

    def _read(self):
        path = self.directory / "forge.json"
        return load_json(path, 1048576) if path.exists() else {"items": {}}

    def observe(self, key, operation, payload, *, attempted=False):
        item = self._read()["items"].get(key)
        if item is None:
            return ExternalObservation("ABSENT")  # Atomic ledger, not eventual search.
        if item["operation"] != operation or item["digest"] != digest(payload):
            return ExternalObservation("UNKNOWN")
        return ExternalObservation("PRESENT", item["reference"], item["revision"], item["body_digest"])

    def submit(self, key, operation, payload, *, authorization=None, plan_digest=None):
        require(operation in (Operation.PR, Operation.REPORT), "Only PR/product-report effects are supported")
        with locked(self.directory):
            state = self._read()
            if key not in state["items"]:
                require(len(state["items"]) < 32, "Synthetic forge capacity exhausted")
                state["items"][key] = {"operation": operation, "digest": digest(payload),
                    "reference": "fixture:forge/" + str(len(state["items"]) + 1),
                    "revision": payload["revision"], "body_digest": digest(payload.get("body", ""))}
                atomic(self.directory / "forge.json", encode(state, 1048576))
        if self.lose_response:
            self.lose_response = False
            raise OSError("Synthetic lost response after durable external creation")
        return self.observe(key, operation, payload, attempted=True)


class SubprocessValidation:
    """Explicit project-owned argv only; no shell or issue-text commands."""
    def __init__(self, commands, *, trusted_disposable=False, sandbox_prefix=()):
        self.commands = commands
        self.trusted_disposable = trusted_disposable
        self.sandbox_prefix = sandbox_prefix

    def run(self, root, revision, required, *, seconds):
        require(self.trusted_disposable or self.sandbox_prefix,
                "UNSUPPORTED_VALIDATION_RUNTIME: explicitly select a qualified sandbox or trusted disposable project")
        require(set(required) == {c.name for c in self.commands}, "Validation matrix must match every required project check")
        results = []
        deadline = time.monotonic() + seconds
        for index, command in enumerate(self.commands):
            require(command.argv and command.denominator > 0 and 0 < command.seconds <= 300, "Invalid explicit validation budget")
            if time.monotonic() >= deadline:
                counts = tuple(OutcomeCount(name, command.denominator if name == Outcome.NOTRUN else 0) for name in Outcome)
                results.append(ValidationResult(command.name, revision, Outcome.NOTRUN, command.denominator, 0,
                    "validation:budget-exhausted", counts, 0))
                continue
            counts, quarantined, passed = (), 0, 0
            try:
                # No forge/ADP credentials or arbitrary parent variables in test code.
                environment = {name: os.environ[name] for name in ("PATH", "LANG", "LC_ALL", "TMPDIR") if name in os.environ}
                with supervised_validation((*self.sandbox_prefix, *command.argv), command.seconds) as (argv, stop_path, subject), subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, env=environment,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True) as process:
                    raw = bytearray()
                    end = min(deadline, time.monotonic() + command.seconds)
                    try:
                        with selectors.DefaultSelector() as selector:
                            selector.register(process.stdout, selectors.EVENT_READ)
                            while True:
                                left = end - time.monotonic()
                                if left <= 0 or not selector.select(left):
                                    raise subprocess.TimeoutExpired(command.argv, command.seconds)
                                block = os.read(process.stdout.fileno(), 65536)
                                if not block:
                                    break
                                raw.extend(block)
                                require(len(raw) <= 65536, "Validation receipt exceeds bounds")
                        code = process.wait(timeout=max(0.01, end - time.monotonic()))
                        stop = validation_stopped(stop_path, subject, process.pid)
                        if stop["status"] == "TIMEOUT":
                            raise subprocess.TimeoutExpired(command.argv, command.seconds)
                    except BaseException:
                        import signal
                        try:
                            if process.poll() is None:
                                os.kill(process.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=8)
                        validation_stopped(stop_path, subject, process.pid)
                        raise
                payload = decode(bytes(raw))
                fields(payload, "denominator counts quarantined")
                require(type(payload["denominator"]) is int and payload["denominator"] == command.denominator,
                        "Original check denominator changed")
                require(type(payload["counts"]) is dict and set(payload["counts"]) == set(Outcome), "Complete outcome accounting is required")
                for count in payload["counts"].values():
                    integer(count)
                integer(payload["quarantined"])
                require(sum(payload["counts"].values()) == command.denominator
                        and payload["quarantined"] <= command.denominator, "Incomplete validation coverage")
                counts = tuple(OutcomeCount(name, payload["counts"][name]) for name in sorted(payload["counts"]))
                quarantined = payload["quarantined"]
                passed = payload["counts"]["PASS"]
                outcome = Outcome.PASS if code == 0 and passed == command.denominator and quarantined == 0 else Outcome.FAIL
            except UnconfirmedValidation as exc:
                counts = tuple(OutcomeCount(name, command.denominator if name == Outcome.UNKNOWN else 0) for name in Outcome)
                results.append(ValidationResult(command.name, revision, Outcome.UNKNOWN, command.denominator, 0, exc.reference, counts, 0))
                for later in self.commands[index + 1:]:
                    counts = tuple(OutcomeCount(name, later.denominator if name == Outcome.NOTRUN else 0) for name in Outcome)
                    results.append(ValidationResult(later.name, revision, Outcome.NOTRUN, later.denominator, 0,
                        "validation:unconfirmed-prior-stop", counts, 0))
                exc.results = tuple(results)
                raise
            except subprocess.TimeoutExpired:
                outcome = Outcome.TIMEOUT
            except OSError:
                outcome = Outcome.ERROR
            except ADPError:
                outcome = Outcome.UNKNOWN
            if not counts:
                counts = tuple(OutcomeCount(name, command.denominator if name == outcome else 0) for name in Outcome)
            require(value(root, "rev-parse", "HEAD") == revision, "Validation changed source HEAD")
            results.append(ValidationResult(command.name, revision, outcome, command.denominator,
                passed, "validation:" + digest({"argv": command.argv, "revision": revision, "counts": [c.__dict__ for c in counts]}), counts, quarantined))
        return tuple(results)
