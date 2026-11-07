"""Argument-only Git calls with observational defaults and bounded outputs."""
from __future__ import annotations

import os
import re
import selectors
import subprocess
import time
from pathlib import Path

from .errors import ConfigurationError, GitError

SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def git(path: Path, *args: str, input: bytes | None = None,
        limit: int = 8 * 1024 * 1024) -> bytes:
    env = os.environ.copy()
    # Do not inherit an unrelated caller's index, worktree, or repository.
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_NOSYSTEM="1")
    try:
        with subprocess.Popen(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
             "-c", "protocol.ext.allow=never", "-c", "core.attributesFile=/dev/null",
             "-c", "commit.gpgsign=false", "-C", str(path), *args],
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env) as process:
            try:
                if input is not None:
                    process.stdin.write(input)
                    process.stdin.close()
                output = bytearray()
                deadline = time.monotonic() + 60
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            raise GitError(f"Git {args[0]} timed out")
                        block = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(output)))
                        if not block:
                            break
                        output.extend(block)
                        if len(output) > limit:
                            raise GitError(f"Git {args[0]} output exceeds the permitted size")
                if process.wait(timeout=max(0.1, deadline - time.monotonic())):
                    raise GitError(f"Git {args[0]} failed; inspect transport/auth or repository health")
                return bytes(output)
            except BaseException:
                process.kill()
                process.wait()
                raise
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"Git {args[0]} unavailable or timed out") from exc


def value(path: Path, *args: str) -> str:
    return git(path, *args).decode("utf-8", "strict").strip()


def optional_config(path: Path, name: str) -> str | None:
    # --get-regexp exits 1 for absence; --list permits an observational lookup.
    entries = value(path, "config", "--null", "--list").split("\0")
    matches = [entry.split("\n", 1)[1] for entry in entries
               if entry.startswith(name.lower() + "\n")]
    return matches[-1] if matches else None


def author(path: Path) -> tuple[str, str]:
    name = optional_config(path, "user.name") or ""
    email = optional_config(path, "user.email") or ""
    if (not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name)
            or "<" in name or ">" in name or "/" in name or "\\" in name
            or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email)
            or email.endswith((".local", ".localhost", ".internal"))):
        raise ConfigurationError("Configure an explicit public/project-safe Git user.name and user.email")
    return name, email
