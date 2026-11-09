"""Bounded Linux child-subreaper for one documented Codex CLI invocation.

This is an OS lifecycle wrapper, not a Codex protocol. It never exits normally
until every descendant has been killed/reaped, including double-fork/setsid
children adopted by PR_SET_CHILD_SUBREAPER. Missing stop receipt proves nothing.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def enable_subreaper():
    try:
        library = ctypes.CDLL(None, use_errno=True)
        return library.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    except (OSError, AttributeError):
        return False


def descendants():
    parents = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            parts = path.read_text().rsplit(')', 1)[1].split()
            parents[int(path.parent.name)] = int(parts[1])
        except (OSError, ValueError, IndexError):
            continue
    found, previous = {os.getpid()}, set()
    while found != previous:
        previous = set(found)
        found.update(pid for pid, parent in parents.items() if parent in found)
    return found - {os.getpid()}


def terminate_and_reap():
    end = time.monotonic() + 5
    while time.monotonic() < end:
        # Freeze the current forest before killing. The subreaper preserves
        # ancestry when a parent exits, so detached children remain observable.
        children = descendants()
        for sig in (signal.SIGSTOP, signal.SIGKILL):
            for pid in children:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return not descendants()  # ECHILD plus empty observed forest.
            except InterruptedError:
                continue
            if pid == 0:
                break
        time.sleep(0.02)
    return False


def receipt(path, payload):
    descriptor, temporary = tempfile.mkstemp(prefix='.supervisor-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as output:
            json.dump(payload, output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--request-digest')
    parser.add_argument('--seconds', type=int)
    parser.add_argument('--deadline', type=float)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    supported = enable_subreaper()
    if args.probe:
        print('SUBREAPER_OK' if supported else 'UNSUPPORTED')
        return 0 if supported else 78
    stopping = []
    def cancelled(number, frame):
        stopping.append(number)
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    end = time.monotonic() + args.seconds
    if args.deadline is not None:
        end = min(end, time.monotonic() + args.deadline - time.time())
    process, code, status = None, None, 'UNSUPPORTED_RUNTIME'
    try:
        if supported:
            if end <= time.monotonic():
                status = 'TIMEOUT'
            else:
                command = args.command[1:] if args.command[:1] == ['--'] else args.command
                process = subprocess.Popen(command)  # Inherit bounded regular stdin and CLI stdout.
                status = 'UNKNOWN'
                while True:
                    code = process.poll()
                    if code is not None:
                        status = 'EXITED'
                        break
                    if stopping:
                        status = 'CANCELLED'
                        break
                    if time.monotonic() >= end or len(descendants()) > 128:
                        status = 'TIMEOUT'
                        break
                    time.sleep(0.02)
    except OSError:
        status = 'UNSUPPORTED_RUNTIME' if process is None else 'UNKNOWN'
    finally:
        stopped = terminate_and_reap()
        if process is not None and process.returncode is None:
            # waitpid in terminate_and_reap already consumed its status.
            process.returncode = -signal.SIGKILL
        receipt(args.receipt, {'request_digest':args.request_digest, 'pid':os.getpid(),
            'status':status if stopped else 'UNKNOWN', 'stopped':stopped, 'cli_exit':code})
    return (code if status == 'EXITED' and code is not None else 124 if status == 'TIMEOUT' else 78 if status == 'UNSUPPORTED_RUNTIME' else 125)


if __name__ == '__main__':
    raise SystemExit(main())
