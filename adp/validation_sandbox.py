"""Explicit, probed bubblewrap validation; no host-prefix or privilege fallback."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, is_dataclass
from contextlib import contextmanager

from .config import load_json, safe_path
from .discovery_schema import digest as canonical_digest
from .errors import ADPError
from .execution_containment import admin_seal, source_seal
from .execution_ports import UnconfirmedValidation, supervised_validation, validation_stopped
from .execution_privacy import credential_shaped
from .execution_types import CheckCommand, ValidationResult
from .git import value
from .guard_types import Outcome
from .policy_types import OutcomeCount
from .schema import decode, fields, integer, require
from .storage import atomic, sync_directory

_QUALIFICATIONS = {}
_UNCERTAIN_QUALIFICATIONS = set()
_QUALIFICATION_LOCK = threading.RLock()


def digest(value):
    def plain(item):
        if is_dataclass(item):
            return plain(asdict(item))
        if isinstance(item, Path):
            return str(item)
        if isinstance(item, dict):
            return {key: plain(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(val) for val in item]
        return item
    return canonical_digest(plain(value))


class UnsupportedValidation(ADPError):
    code = 7


class UnsafeValidation(ADPError):
    """Confirmed safety refusal; Conductor's existing exception path latches M2."""
    def __init__(self, results, reference):
        super().__init__('Validation containment stop; remaining inventory NOTRUN')
        self.results, self.reference = tuple(results), reference


def _reject_terminal_stop(stop, reference):
    # A parent observation deadline cannot erase a confirmed containment stop.
    if stop.get('cli_exit') in (-signal.SIGSYS, 128 + signal.SIGSYS) or stop.get('status') not in ('EXITED', 'TIMEOUT'):
        exception = UnsafeValidation((), 'sandbox:terminal-supervisor-stop')
        exception.validation_evidence = reference
        raise exception


@dataclass(frozen=True)
class SandboxPolicy:
    image: Path
    image_digest: str
    binary: Path
    binary_digest: str
    executable: str
    memory_bytes: int = 256 * 1024 * 1024
    cpu_seconds: int = 10
    descriptors: int = 64
    output_bytes: int = 65536


@dataclass(frozen=True)
class ValidationCapability:
    supported: bool
    backend: str
    version: str
    kernel: str
    policy_digest: str
    evidence: str
    reason: str = ''


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_digest(root: Path) -> str:
    """Credential-free operator runtime image, without special files or links."""
    rows, total = [], 0
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), 'Runtime image links/special files are unsupported')
        require(not stat.S_ISREG(info.st_mode) or info.st_nlink == 1, 'Runtime image hard links are unsupported')
        total += info.st_size
        require(len(rows) < 4096 and total <= 128 * 1024 * 1024, 'Runtime image exceeds fixed bounds')
        rows.append((path.relative_to(root).as_posix(), info.st_mode, file_digest(path) if path.is_file() else ''))
    return digest(rows)


def _private(root: Path) -> Path:
    root = safe_path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'Private validation receipts require owned mode0700 storage')
    return root


class BubblewrapValidation:
    """Single-process, zero-scratch Linux x86_64 profile selected by an operator.

    The image is a dedicated runtime filesystem, not /usr or a host root. No
    authentication, controller, memory or unrelated worktree belongs in it.
    Every invocation probes the OS boundary before executing any product check.
    """
    def __init__(self, commands: tuple[CheckCommand, ...], *, policy: SandboxPolicy,
                 protected_roots: tuple[Path, ...], receipts: Path):
        require(type(policy) is SandboxPolicy and type(commands) is tuple and 0 < len(commands) <= 32,
                'Explicit typed sandbox policy and finite validation matrix required')
        self.commands, self.policy = commands, policy
        self.protected_roots = tuple(safe_path(p) for p in protected_roots)
        require(bool(self.protected_roots), 'Explicit memory/controller/authentication protection roots required')
        self.receipts = _private(receipts)
        self._launcher_digest = file_digest(Path(__file__).with_name('validation_launcher.py'))
        self._validate_policy()

    def policy_digest(self):
        return digest({'configuration': self.policy, 'protected_roots': self.protected_roots,
                       'launcher_sha256': self._launcher_digest, 'profile_version': 1})

    def _host_key(self):
        status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
        return digest({'policy': self.policy_digest(), 'port_sha256': file_digest(Path(__file__)),
            'kernel': platform.release(), 'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'pid': os.getpid(), 'uid': os.getresuid(), 'gid': os.getresgid(), 'groups': sorted(os.getgroups()),
            'namespaces': {name: os.readlink('/proc/self/ns/' + name) for name in ('user', 'mnt', 'net', 'pid')},
            'controls': {name: status.get(name, '').strip() for name in ('NoNewPrivs', 'Seccomp', 'Seccomp_filters', 'CapEff', 'CapBnd')}})

    def _assert_idle(self):
        descriptor = os.open(self.receipts / 'execution.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a+b') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UnconfirmedValidation('sandbox:execution-already-running', str(self.receipts))
            if (self.receipts / 'active.json').exists() or (self.receipts / 'active.json').is_symlink():
                raise UnconfirmedValidation('sandbox:prior-launch-stop-unknown', str(self.receipts))

    def _validate_policy(self):
        p = self.policy
        require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'UNSUPPORTED_VALIDATION_RUNTIME: Linux x86_64 required')
        image, binary = safe_path(p.image), safe_path(p.binary)
        require(file_digest(Path(__file__).with_name('validation_launcher.py')) == self._launcher_digest, 'Trusted validation launcher changed')
        require(image.is_dir() and binary.is_file() and binary.stat().st_mode & 0o111
                and not binary.stat().st_mode & (stat.S_ISUID | stat.S_ISGID), 'A non-setuid explicit bubblewrap runtime is required')
        require(file_digest(binary) == p.binary_digest and image_digest(image) == p.image_digest, 'Pinned validation runtime changed')
        for field, low, high in ((p.memory_bytes, 64 * 1024 * 1024, 1024 * 1024 * 1024),
                                 (p.cpu_seconds, 1, 300), (p.descriptors, 32, 128), (p.output_bytes, 1024, 65536)):
            require(type(field) is int and low <= field <= high, 'Invalid fixed sandbox resource limit')
        for name in ('work', 'proc', 'dev', 'tmp'):
            require((image / name).is_dir() and not any((image / name).iterdir()), 'Runtime image mount/scratch slots must be empty')
        protected = (*self.protected_roots, Path(__file__).resolve().parent)
        require(all(not q.is_relative_to(image) and not image.is_relative_to(q) for q in protected), 'Runtime image overlaps protected host data')
        require(not self.receipts.is_relative_to(image) and not image.is_relative_to(self.receipts), 'Runtime image overlaps private receipts')
        for command in self.commands:
            require(type(command) is CheckCommand and type(command.argv) is tuple and command.argv and command.argv[0] == p.executable
                    and type(command.name) is str and 0 < len(command.name) <= 128
                    and type(command.seconds) is int and 1 <= command.seconds <= 300
                    and type(command.denominator) is int and command.denominator > 0, 'Invalid registered executable/argv or original denominator')
            require(all(type(v) is str and 0 < len(v) <= 32768 and '\0' not in v for v in command.argv)
                    and sum(len(v) for v in command.argv) <= 65536, 'Registered argv exceeds bounds')
        require(len({c.name for c in self.commands}) == len(self.commands), 'Validation check names must be unique')
        guest = PurePosixPath(p.executable)
        require(guest.is_absolute() and '..' not in guest.parts, 'Executable must name an absolute image path')
        executable = image.joinpath(*guest.parts[1:])
        require(executable.is_file() and executable.stat().st_mode & 0o111, 'Registered executable is absent from the pinned image')

    def _source(self, root: Path, revision: str):
        root = safe_path(root)
        require(root.is_dir() and (root / '.git').is_dir() and not (root / '.git').is_symlink(),
                'UNSUPPORTED_VALIDATION_RUNTIME: standalone Git checkout required')
        require(all(not root.is_relative_to(q) and not q.is_relative_to(root) for q in
                    (*self.protected_roots, self.receipts, self.policy.image)), 'Product overlaps protected validation data')
        total = 0
        for index, path in enumerate(root.rglob('*')):
            info = path.lstat()
            total += info.st_size
            require(index < 8192 and total <= 64 * 1024 * 1024, 'Source inventory exceeds fixed validation bounds')
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode), 'Special source files are unsupported')
            require(not stat.S_ISREG(info.st_mode) or info.st_nlink == 1, 'Source hard links cannot expose outside data')
            if stat.S_ISLNK(info.st_mode):
                require(path.resolve().is_relative_to(root), 'Outside source symlink is refused')
        config_path = safe_path(root / '.git/config')
        require(config_path.stat().st_size <= 65536, 'Product Git configuration exceeds validation bounds')
        config = config_path.read_text()
        import re
        require(not credential_shaped(config) and not re.search(
                r'(?im)^\s*\[(?:credential|include|includeif)\b|^\s*(?:extraheader|worktree|hookspath|fsmonitor|sshcommand)\s*=', config),
                'External or credential-bearing product Git configuration is unsupported')
        require(not (root / '.git/objects/info/alternates').exists(), 'External Git object alternates are unsupported')
        require(value(root, 'rev-parse', 'HEAD') == revision, 'Validation source revision drifted')
        return source_seal(root), admin_seal(root)

    def _argv(self, root, argv, seconds):
        p = self.policy
        limits = json.dumps({'memory_bytes': p.memory_bytes, 'cpu_seconds': min(seconds, p.cpu_seconds), 'descriptors': p.descriptors}, separators=(',', ':'))
        return (sys.executable, '-I', str(Path(__file__).with_name('validation_launcher.py')),
                '--binary', str(p.binary), '--image', str(p.image), '--source', str(root),
                '--limits', limits, '--', *argv)

    @contextmanager
    def _flight(self, argv):
        descriptor = os.open(self.receipts / 'execution.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a+b') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UnconfirmedValidation('sandbox:execution-already-running', str(self.receipts))
            active = self.receipts / 'active.json'
            if active.exists() or active.is_symlink():
                raise UnconfirmedValidation('sandbox:prior-launch-stop-unknown', str(self.receipts))
            atomic(active, json.dumps({'status': 'PREPARED', 'command_digest': digest(argv),
                                       'policy_digest': self.policy_digest()}).encode())
            yield active

    def _record(self, active, argv, raw, errors, stop):
        descriptor, receipt = tempfile.mkstemp(prefix='receipt-', suffix='.json', dir=self.receipts)
        payload = json.dumps({'stop': stop, 'command_digest': digest(argv), 'policy_digest': self.policy_digest(),
                              'output_hex': bytes(raw).hex(), 'stderr_hex': bytes(errors).hex()}, sort_keys=True).encode()
        with os.fdopen(descriptor, 'wb') as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        active.unlink()
        sync_directory(self.receipts)
        return 'sandbox-stop:' + hashlib.sha256(payload).hexdigest()

    def _execute(self, root, argv, seconds):
        self._validate_policy()
        require(sum(1 for _ in self.receipts.glob('receipt-*.json')) < 256, 'Private receipt inventory exhausted')
        raw, errors = bytearray(), bytearray()
        with self._flight(argv) as active, supervised_validation(self._argv(root, argv, seconds), seconds) as (launch, stop_path, subject):
            atomic(active, json.dumps({'status': 'RUNNING', 'command_digest': digest(argv),
                                       'policy_digest': self.policy_digest(), 'stop_path': str(stop_path),
                                       'request_digest': subject}).encode())
            try:
                process = subprocess.Popen(launch, cwd='/', stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, env={'PATH': '/usr/bin:/bin'}, start_new_session=True)
            except OSError:
                raise UnconfirmedValidation('sandbox:launch-stop-unknown', str(stop_path.parent))
            try:
                end = time.monotonic() + seconds
                try:
                    with selectors.DefaultSelector() as selector:
                        selector.register(process.stdout, selectors.EVENT_READ, raw)
                        selector.register(process.stderr, selectors.EVENT_READ, errors)
                        while selector.get_map():
                            left = end - time.monotonic()
                            ready = selector.select(max(0, left))
                            if left <= 0 or not ready:
                                raise subprocess.TimeoutExpired(argv, seconds)
                            for event, _ in ready:
                                block = os.read(event.fd, 65536)
                                if not block:
                                    selector.unregister(event.fileobj)
                                else:
                                    event.data.extend(block)
                                    if len(raw) + len(errors) > self.policy.output_bytes:
                                        raise UnsafeValidation((), 'sandbox:output-limit')
                    process.wait(timeout=max(0.01, end - time.monotonic()))
                except BaseException as exc:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=8)  # Fixed M5 stop/reap observation budget, not added check time.
                    except subprocess.TimeoutExpired:
                        process.kill()
                        try:
                            process.wait(timeout=1)
                        finally:
                            raise UnconfirmedValidation('sandbox:supervisor-stop-unknown', str(stop_path.parent))
                    stop = validation_stopped(stop_path, subject, process.pid)
                    exc.validation_evidence = self._record(active, argv, raw, errors, stop)
                    _reject_terminal_stop(stop, exc.validation_evidence)
                    raise
                stop = validation_stopped(stop_path, subject, process.pid)
                reference = self._record(active, argv, raw, errors, stop)
                # Trusted negative probes expect a normal SIGSYS receipt;
                # product run below always treats that receipt as terminal.
                if stop.get('status') not in ('EXITED', 'TIMEOUT'):
                    _reject_terminal_stop(stop, reference)
                return bytes(raw), stop, reference
            finally:
                process.stdout.close()
                process.stderr.close()

    def capabilities(self, *, seconds=12, fresh=False) -> ValidationCapability:
        require(type(seconds) is int and seconds > 0 and type(fresh) is bool, 'Invalid capability observation budget')
        deadline = time.monotonic() + min(seconds, 12)
        self._validate_policy()  # Actual bytes are rechecked, never just a flag.
        self._assert_idle()  # A cache cannot hide an in-flight or uncertain launch.
        key = self._host_key()
        if not _QUALIFICATION_LOCK.acquire(timeout=max(0.01, deadline - time.monotonic())):
            return ValidationCapability(False, 'bubblewrap-seccomp-single-process', '', platform.release(),
                self.policy_digest(), 'sandbox:probe-lock-budget', 'UNSUPPORTED_VALIDATION_RUNTIME: concurrent probe budget')
        try:
            self._assert_idle()
            if key in _UNCERTAIN_QUALIFICATIONS:
                raise UnconfirmedValidation('sandbox:prior-qualification-stop-unknown', str(self.receipts))
            known = _QUALIFICATIONS.get(key)
            if not fresh and known is not None and known[0] > time.monotonic():
                return known[1]
            try:
                remaining = int(deadline - time.monotonic())
                if remaining <= 0:
                    return ValidationCapability(False, 'bubblewrap-seccomp-single-process', '', platform.release(),
                        self.policy_digest(), 'sandbox:probe-budget', 'UNSUPPORTED_VALIDATION_RUNTIME: capability budget exhausted')
                observed = self._probe(seconds=remaining)
            except UnconfirmedValidation:
                _QUALIFICATIONS.pop(key, None)
                _UNCERTAIN_QUALIFICATIONS.add(key)
                raise
            if observed.supported:
                if len(_QUALIFICATIONS) >= 32:
                    del _QUALIFICATIONS[next(iter(_QUALIFICATIONS))]
                _QUALIFICATIONS[key] = (time.monotonic() + 300, observed)
            else:
                _QUALIFICATIONS.pop(key, None)
            return observed
        finally:
            _QUALIFICATION_LOCK.release()

    def _probe(self, *, seconds=12) -> ValidationCapability:
        p = self.policy
        evidence, version = 'sandbox:unqualified', ''
        stage = 'policy'
        try:
            deadline = time.monotonic() + seconds
            self._validate_policy()
            stage = 'runtime-version'
            version = subprocess.check_output((str(p.binary), '--version'), stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            with tempfile.TemporaryDirectory(prefix='adp-sandbox-probe-') as temporary:
                root = Path(temporary)
                # Trusted probe code, never a target-project command.
                probes = (('benign', "print('ADP_SANDBOX_READY')", False),
                          ('write', "open('/work/forbidden','w').write('unsafe')", True),
                          ('network', "import socket;socket.create_connection(('127.0.0.1',9),1)", True),
                          ('fork', "import os;os.fork()", True))
                rows = []
                for name, source, killed in probes:
                    stage = 'probe-' + name
                    left = min(3, int(deadline - time.monotonic()))
                    require(left > 0, 'Capability probe budget exhausted')
                    raw, stop, reference = self._execute(root, (p.executable, '-I', '-B', '-c', source), left)
                    require(stop['stopped'] is True and stop['status'] == 'EXITED'
                            and (stop['cli_exit'] in (-signal.SIGSYS, 128 + signal.SIGSYS) if killed
                                 else stop['cli_exit'] == 0 and raw.strip() == b'ADP_SANDBOX_READY'),
                            'Required OS enforcement probe failed: status=' + str(stop.get('status'))
                            + '; exit=' + str(stop.get('cli_exit')))
                    rows.append((name, stop['cli_exit'], hashlib.sha256(raw).hexdigest(), reference))
                evidence = 'sandbox:' + digest({'policy': self.policy_digest(), 'rows': rows, 'version': version, 'kernel': platform.release()})
            return ValidationCapability(True, 'bubblewrap-seccomp-single-process', version, platform.release(), self.policy_digest(), evidence)
        except UnconfirmedValidation:
            raise  # Uncertain liveness is not an unsupported platform or safe retry.
        except (ADPError, OSError, ValueError, subprocess.SubprocessError) as exc:
            return ValidationCapability(False, 'bubblewrap-seccomp-single-process', version, platform.release(), self.policy_digest(), evidence,
                                        'UNSUPPORTED_VALIDATION_RUNTIME: ' + stage + ': ' + type(exc).__name__
                                        + (': ' + str(exc) if isinstance(exc, ADPError) else ''))

    def _result(self, command, revision, outcome, counts=None, quarantined=0, receipt=None):
        counts = counts or {name: command.denominator if name == outcome else 0 for name in Outcome}
        measured = tuple(OutcomeCount(name, counts[name]) for name in sorted(Outcome))
        return ValidationResult(command.name, revision, outcome, command.denominator, counts[Outcome.PASS],
                                'sandbox-validation:' + digest({'policy': self.policy_digest(), 'command': command, 'revision': revision,
                                                               'counts': counts, 'stop_receipt': receipt}), measured, quarantined)

    def run(self, root: Path, revision: str, required: tuple[str, ...], *, seconds: int) -> tuple[ValidationResult, ...]:
        require(type(seconds) is int and 1 <= seconds <= 300 and type(required) is tuple
                and len(set(required)) == len(required) and set(required) == {c.name for c in self.commands},
                'Exact required validation matrix and bounded invocation required')
        deadline = time.monotonic() + seconds
        self._validate_policy()
        before = self._source(root, revision)
        lock_path = self.receipts / (digest(str(root)) + '.lock')
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a+b') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UnconfirmedValidation('sandbox:already-running', str(self.receipts))
            state_path = self.receipts / (digest(str(root)) + '.json')
            state = load_json(state_path) if state_path.exists() else {}
            if state.get('status') == 'RUNNING':
                raise UnconfirmedValidation('sandbox:interrupted-stop-unknown', str(self.receipts))
            capability = self.capabilities(seconds=max(1, int(deadline - time.monotonic())))
            if not capability.supported:
                raise UnsupportedValidation(capability.reason)
            subject = digest({'root': str(root), 'revision': revision, 'source': before, 'policy': self.policy_digest(), 'commands': self.commands})
            results = []
            atomic(state_path, json.dumps({'status': 'RUNNING', 'subject': subject}).encode())
            try:
                for index, command in enumerate(self.commands):
                    left = int(deadline - time.monotonic())
                    if left <= 0:
                        results.append(self._result(command, revision, Outcome.NOTRUN))
                        continue
                    if self._source(root, revision) != before:
                        raise UnsafeValidation([*results, *(self._result(c, revision, Outcome.NOTRUN)
                            for c in self.commands[index:])], 'sandbox:source-changed-before-check')
                    reference = None
                    try:
                        raw, stop, reference = self._execute(root, command.argv, min(left, command.seconds))
                        _reject_terminal_stop(stop, reference)
                        if stop['status'] == 'TIMEOUT':
                            results.append(self._result(command, revision, Outcome.TIMEOUT, receipt=reference))
                            continue
                        payload = decode(raw)
                        fields(payload, 'denominator counts quarantined')
                        require(type(payload['denominator']) is int and payload['denominator'] == command.denominator,
                                'Original validation denominator changed')
                        require(type(payload['counts']) is dict and set(payload['counts']) == set(Outcome), 'All validation outcomes required')
                        for count in payload['counts'].values():
                            integer(count)
                        integer(payload['quarantined'])
                        require(sum(payload['counts'].values()) == command.denominator and payload['quarantined'] <= command.denominator,
                                'Incomplete validation accounting')
                        outcome = Outcome.PASS if stop['cli_exit'] == 0 and payload['counts']['PASS'] == command.denominator and payload['quarantined'] == 0 else Outcome.FAIL
                        results.append(self._result(command, revision, outcome, payload['counts'], payload['quarantined'], receipt=reference))
                    except subprocess.TimeoutExpired as exc:
                        results.append(self._result(command, revision, Outcome.TIMEOUT, receipt=getattr(exc, 'validation_evidence', None)))
                    except (UnconfirmedValidation, UnsafeValidation) as exc:
                        if isinstance(exc, UnconfirmedValidation):
                            with _QUALIFICATION_LOCK:
                                cache_key = self._host_key()
                                _QUALIFICATIONS.pop(cache_key, None)
                                _UNCERTAIN_QUALIFICATIONS.add(cache_key)
                        measured = [*results, self._result(command, revision, Outcome.UNKNOWN,
                            receipt=getattr(exc, 'validation_evidence', None))]
                        measured.extend(self._result(c, revision, Outcome.NOTRUN) for c in self.commands[index + 1:])
                        exc.results = tuple(measured)
                        raise
                    except (ADPError, OSError):
                        results.append(self._result(command, revision, Outcome.UNKNOWN, receipt=reference))
                    if self._source(root, revision) != before:
                        raise UnsafeValidation([*results[:-1], self._result(command, revision, Outcome.UNKNOWN, receipt=reference),
                            *(self._result(c, revision, Outcome.NOTRUN) for c in self.commands[index + 1:])],
                            'sandbox:source-changed-after-check')
                atomic(state_path, json.dumps({'status': 'STOPPED', 'subject': subject, 'results': [r.evidence for r in results]}).encode())
                return tuple(results)
            except BaseException:
                # Durable RUNNING is deliberately not cleared without a complete
                # stop/accounting proof. Restart never blindly starts another run.
                raise
