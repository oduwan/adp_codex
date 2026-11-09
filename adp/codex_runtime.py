"""Supported codex exec adapter: fresh contexts, bounded IO and observed stops."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import selectors
import shutil
import signal
import sys
import subprocess
import threading
import tempfile
import time
from dataclasses import fields as dc_fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from .config import load_json, safe_path
from .discovery_schema import digest, typed
from .errors import ADPError
from .execution_schema import fingerprint, worker_result
from .execution_types import (Capabilities, Role, RuntimeObservation, RuntimeStatus,
    WorkerRequest, WorkerResult)
from .guard_types import Outcome, data
from .schema import decode, encode, require, string
from .storage import atomic, locked


def output_schema(cls):
    origin, args = get_origin(cls), get_args(cls)
    if origin is tuple:
        return {"type": "array", "items": output_schema(args[0])}
    if args:
        return {"anyOf": [output_schema(v) for v in args]}
    if cls is type(None):
        return {"type": "null"}
    if isinstance(cls, type) and issubclass(cls, Enum):
        return {"type": "string", "enum": [v.value for v in cls]}
    if is_dataclass(cls):
        hints = get_type_hints(cls)
        return {"type": "object", "properties": {f.name: output_schema(hints[f.name]) for f in dc_fields(cls)},
                "required": [f.name for f in dc_fields(cls)], "additionalProperties": False}
    return {"type": {str: "string", bool: "boolean", int: "integer"}[cls]}


def _start_time(pid):
    try:
        # comm can contain spaces and parentheses; fields after the last ')'
        # start at state (field 3). starttime is field 22.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _group_alive(group):
    """Observe live process-group members, including children after leader exit."""
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            parts = path.read_text().rsplit(")", 1)[1].split()
            if parts[0] != "Z" and int(parts[2]) == group:
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def frontend_environment():
    """Only model frontend authentication/settings, never mutation credentials."""
    names = {"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TZ", "TERM", "TMPDIR", "TEMP", "TMP",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "CODEX_HOME", "CODEX_CA_CERTIFICATE",
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID"}
    return {name: os.environ[name] for name in names if name in os.environ}


class CodexExecRuntime:
    """One foreground CLI process per request. No daemon or blind redispatch.

    Local launch/result receipts live outside worker roots. A STARTING receipt
    with no observed child identity is UNKNOWN after a crash. We never retry it.
    Auth/config administration and supported CLI sandbox enforcement are trusted.
    """
    def __init__(self, directory: Path, *, executable="codex", clock=None):
        self.directory = safe_path(directory)
        self.executable = shutil.which(executable) or executable
        self.clock = clock or time.monotonic
        self._live = {}
        self._mutex = threading.RLock()
        machine = Path("/etc/machine-id")
        identity = machine.read_bytes() if machine.exists() else platform.node().encode()
        try:
            namespace = os.readlink('/proc/self/ns/pid').encode()
        except OSError:
            namespace = b'unsupported'
        self.host = hashlib.sha256(identity + str(getattr(os, 'getuid', lambda: 'unsupported')()).encode() + namespace).hexdigest()
        self._capabilities = None
        self.supervisor = Path(__file__).with_name("execution_supervisor.py")

    def capabilities(self):
        if self._capabilities is not None:
            return self._capabilities
        supported, version, reason = False, "UNKNOWN", "Codex CLI capability probe unavailable"
        try:
            version = subprocess.check_output([self.executable, "--version"], stderr=subprocess.DEVNULL, timeout=10, env=frontend_environment()).decode().strip()
            help_text = subprocess.check_output([self.executable, "exec", "--help"], stderr=subprocess.DEVNULL, timeout=10, env=frontend_environment()).decode()
            supported = (os.name == "posix" and Path("/proc/self/stat").exists()
                and all(flag in help_text for flag in ("--json", "--output-schema", "--ephemeral", "--ignore-user-config", "--sandbox")))
            supported = supported and subprocess.check_output([sys.executable, str(self.supervisor), "--probe"],
                stderr=subprocess.DEVNULL, timeout=5, env=frontend_environment()).strip() == b"SUBREAPER_OK"
            reason = "" if supported else "UNSUPPORTED_RUNTIME: required CLI/sandbox/process-observation capabilities missing"
        except (OSError, subprocess.SubprocessError, UnicodeError):
            supported = False
            reason = "UNSUPPORTED_RUNTIME: Codex/supervisor capability probe failed"
        self._capabilities = Capabilities("codex-exec", self.host, version, supported, supported, supported, supported, 4 if supported else 0, reason)
        return self._capabilities

    def _path(self, request_id):
        fingerprint(request_id)
        return self.directory / (request_id + ".json")

    def _read(self, request_id):
        path = self._path(request_id)
        return load_json(path, 32768) if path.exists() else None

    def _save(self, request_id, record):
        atomic(self._path(request_id), encode(record, 32768))

    def _observation(self, request_id, record):
        if record is None:
            return RuntimeObservation(request_id, self.host, RuntimeStatus.NOT_STARTED, None, None, "runtime:not-started", 0)
        require(record["host"] == self.host, "Runtime receipt belongs to another host")
        result = typed(WorkerResult, record["result"]) if record["result"] is not None else None
        return RuntimeObservation(request_id, self.host, RuntimeStatus(record["status"]), record["context"], result,
                                  "runtime:" + request_id + ":" + digest(record), record["elapsed"], record["request_digest"],
                                  record.get("samples", 0), record.get("payload_bytes", 0), record.get("stopped"))

    def _stop_receipt(self, request_id, record):
        path = self.directory / (request_id + ".stop.json")
        if not path.exists():
            return None
        observed = load_json(path, 2048)
        from .schema import fields
        fields(observed, "request_digest pid status stopped cli_exit")
        require(observed["request_digest"] == record["request_digest"] and observed["pid"] == record["pid"]
                and type(observed["stopped"]) is bool, "Invalid supervisor stop binding")
        return observed

    def observe(self, request_id):
        record = self._read(request_id)
        if record is not None and record["status"] == RuntimeStatus.RUNNING:
            if _start_time(record["pid"]) != record["start_time"]:
                # A process exit without a durable terminal receipt proves no
                # worker result or successful cancellation.
                record = {**record, "status": RuntimeStatus.UNKNOWN}
        if record is not None and record["status"] == "STARTING":
            record = {**record, "status": RuntimeStatus.UNKNOWN}
        if record is not None and record["pid"] is not None:
            stop = self._stop_receipt(request_id, record)
            if stop and stop["stopped"]:
                record = {**record, "stopped": True}
        return self._observation(request_id, record)

    def dispatch(self, request: WorkerRequest):
        require(type(request) is WorkerRequest and 1 <= request.seconds <= 300, "Invalid bounded worker request")
        require(request.deadline is None or type(request.deadline) is int and request.deadline > time.time(),
                "Worker reservation deadline is absent or expired")
        require(request.role in (Role.RESEARCH, Role.DEVELOPER, Role.REVIEWER, Role.FORENSIC), "Coordination records are not worker contexts")
        require(type(request.samples) is int and 0 < request.samples <= 1000 and type(request.payload_bytes) is int
                and 0 < request.payload_bytes <= 1048576, "Invalid worker IO containment")
        fingerprint(request.id)
        string(request.task_id)
        require(type(request.prompt) is str and len(request.prompt.encode()) <= 32768, "Worker input exceeds bounds")
        workspace = safe_path(Path(request.workspace))
        require(workspace.is_dir() and not self.directory.is_relative_to(workspace), "Runtime controls must be outside the worker root")
        if not self.capabilities().independent_contexts:
            return RuntimeObservation(request.id, self.host, RuntimeStatus.UNSUPPORTED_RUNTIME, None, None,
                                      "runtime:unsupported", 0)
        with locked(self.directory):
            if self._path(request.id).exists():
                existing = self._read(request.id)
                require(existing["request_digest"] == digest(request), "Request ID reused with different input")
                return self.observe(request.id)
            require(len(list(self.directory.glob("*.json"))) < 256, "Runtime receipt capacity exhausted")
            schema_path = self.directory / "worker-schema.json"
            if not schema_path.exists():
                atomic(schema_path, encode(output_schema(WorkerResult)))
            record = {"host": self.host, "request_digest": digest(request), "status": "STARTING", "pid": None,
                "start_time": None, "context": None, "result": None, "elapsed": 0}
            self._save(request.id, record)  # Durable before spawning anything.
            command = [self.executable, "exec", "--ignore-user-config", "--ephemeral", "--json",
                "--sandbox", "workspace-write" if request.role == Role.DEVELOPER else "read-only",
                "-c", 'approval_policy="never"', "-c", "sandbox_workspace_write.network_access=false",
                "-c", 'shell_environment_policy.inherit="core"',
                "-c", 'shell_environment_policy.exclude=["*_TOKEN","*_SECRET","*_PASSWORD","*_KEY","ADP_*","GIT_*","GH_*","GITHUB_*","AWS_*","AZURE_*","GOOGLE_*","SSH_*","HTTP_PROXY","HTTPS_PROXY","ALL_PROXY"]',
                "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true", "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
                "--output-schema", str(schema_path), "-C", str(workspace), "-"]
            wrapper = [sys.executable, str(self.supervisor), "--receipt", str(self.directory / (request.id + ".stop.json")),
                "--request-digest", digest(request), "--seconds", str(request.seconds)]
            if request.deadline is not None:
                wrapper += ["--deadline", str(request.deadline)]
            try:
                # A regular bounded input file cannot block on an unread pipe.
                with tempfile.TemporaryFile(dir=self.directory) as source:
                    source.write(request.prompt.encode())
                    source.seek(0)
                    process = subprocess.Popen([*wrapper, "--", *command], stdin=source, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, start_new_session=True, env=frontend_environment())
            except OSError:
                record["status"] = RuntimeStatus.UNSUPPORTED_RUNTIME
                self._save(request.id, record)
                return self._observation(request.id, record)
            record.update(status=RuntimeStatus.RUNNING, pid=process.pid, start_time=_start_time(process.pid))
            with self._mutex:
                self._live[request.id] = (process, request, self.clock())
            try:
                self._save(request.id, record)
            except BaseException:
                # A failed receipt write cannot leave an unobserved live child.
                try:
                    os.kill(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                process.wait(timeout=8)
                process.stdout.close()
                with self._mutex:
                    self._live.pop(request.id, None)
                raise
            return self._observation(request.id, record)

    def wait(self, request_id):
        with self._mutex:
            live = self._live.get(request_id)
        if live is None:
            return self.observe(request_id)
        process, request, started = live
        record = self._read(request_id)
        output, last_message, complete, runtime_error = bytearray(), None, False, False
        timed_out = False
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = request.seconds - (self.clock() - started)
                if request.deadline is not None:
                    remaining = min(remaining, request.deadline - time.time())
                if remaining <= 0 or not selector.select(min(max(remaining, 0), 1)):
                    if remaining <= 0:
                        timed_out = True
                        self.cancel(request_id)
                        break
                    continue
                block = os.read(process.stdout.fileno(), 65536)
                if not block:
                    break
                output.extend(block)
                if len(output) > request.payload_bytes or output.count(b"\n") > request.samples:
                    runtime_error = True
                    self.cancel(request_id)
                    break
        for line in bytes(output).splitlines():
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue  # CLI diagnostics are not worker authority/evidence.
            if type(event) is not dict:
                continue
            if event.get("type") == "thread.started":
                context = event.get("thread_id")
                if type(context) is str and 0 < len(context) <= 128:
                    record["context"] = context
            if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message":
                last_message = event["item"].get("text")
            complete |= event.get("type") == "turn.completed"
            runtime_error |= event.get("type") in {"error", "turn.failed"}
        stopped = process.poll() is not None
        if not stopped:
            try:
                process.wait(timeout=5)
                stopped = True
            except subprocess.TimeoutExpired:
                self.cancel(request_id)
        stop = self._stop_receipt(request_id, record)
        if stop is None or not stop["stopped"]:
            self.cancel(request_id)
            stop = self._stop_receipt(request_id, record)
        stopped = process.poll() is not None and stop is not None and stop["stopped"]
        result = None
        status = RuntimeStatus.TIMEOUT if timed_out and stopped else RuntimeStatus.UNKNOWN
        if stopped and process.returncode == 0 and complete and not runtime_error and record["context"]:
            try:
                result = typed(WorkerResult, decode(last_message.encode(), 16384))
                worker_result(result)
                status = RuntimeStatus.COMPLETED
            except (ADPError, AttributeError, UnicodeError):
                pass
        if stopped and stop["status"] == "TIMEOUT":
            status = RuntimeStatus.TIMEOUT
        elif stopped and stop["status"] == "UNSUPPORTED_RUNTIME":
            status = RuntimeStatus.UNSUPPORTED_RUNTIME
        elif stopped and (runtime_error and not complete or process.returncode != 0 and record["context"] is None):
            status = RuntimeStatus.UNSUPPORTED_RUNTIME
        record.update(status=status, result=data(result) if result else None,
                      elapsed=min(301, int(self.clock() - started)), samples=output.count(b"\n"), payload_bytes=len(output), stopped=stopped)
        process.stdout.close()
        self._save(request_id, record)
        with self._mutex:
            self._live.pop(request_id, None)
        return self._observation(request_id, record)

    def cancel(self, request_id):
        record = self._read(request_id)
        if record is None:
            return self.observe(request_id)
        with self._mutex:
            live = self._live.get(request_id)
        stop = self._stop_receipt(request_id, record) if record["pid"] is not None else None
        if record["status"] != RuntimeStatus.RUNNING and not (stop and stop["stopped"]):
            return self.observe(request_id)
        if stop is None or not stop["stopped"]:
            if _start_time(record["pid"]) != record["start_time"]:
                return self._observation(request_id, {**record, "status": RuntimeStatus.UNKNOWN})
            try:
                # The supervisor handles this signal by killing/reaping its
                # entire adopted descendant forest. Never SIGKILL the reaper
                # and then mistake a missing process group for proof of stop.
                os.kill(record["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                stop = self._stop_receipt(request_id, record)
                if stop and stop["stopped"]:
                    break
                time.sleep(0.02)
        if stop and stop["stopped"]:
            if live:
                try:
                    live[0].wait(timeout=2)
                except subprocess.TimeoutExpired:
                    return self._observation(request_id, {**record, "status": RuntimeStatus.UNKNOWN})
                live[0].stdout.close()
            record.update(status=RuntimeStatus.CANCELLED, stopped=True)
            self._save(request_id, record)
            with self._mutex:
                self._live.pop(request_id, None)
        else:
            record = {**record, "status": RuntimeStatus.UNKNOWN}
        return self._observation(request_id, record)
