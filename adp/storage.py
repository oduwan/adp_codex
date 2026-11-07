"""Local atomic files and one process-wide/interprocess mutation queue."""
from __future__ import annotations

import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import safe_path
from .errors import ADPError

_MUTEX = threading.RLock()


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path: Path, raw: bytes, *, replace: bool = True) -> None:
    safe_path(path)
    safe_path(path.parent)
    fd, name = tempfile.mkstemp(prefix=".adp-tmp-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Atomic no-replace delivery: a duplicate never changes the first file.
            os.link(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(directory: Path) -> Iterator[None]:
    # Fail closed where advisory file locking is unavailable; never guess a stale
    # PID or remove another process's lock. The OS releases flock after a crash.
    try:
        import fcntl
    except ImportError as exc:
        raise ADPError("This platform requires POSIX flock for serialized memory writes") from exc
    with _MUTEX:
        safe_path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = safe_path(directory / "lock")
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
