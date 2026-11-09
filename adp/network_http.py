"""Explicit trusted HTTP transport with fixed origin and enforced process deadline.

This is an operator-side transport, never a worker capability or authorization
provider. Only a caller's separately qualified exact operation may use it.
"""
from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Protocol
import uuid

from .errors import ADPError
from .execution_ports import UnconfirmedValidation, supervised_validation, validation_stopped
from .network_http_child import (MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES,
    UPDATE_REFS_MUTATION, validate_request)
from .schema import decode, fields, require


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


class HTTPTransport(Protocol):
    def request(self, method: str, path: str, body: dict | None, *, seconds: float) -> Response: ...


class NetworkTransportError(ADPError):
    """A transport failure is never proof that a submitted mutation was absent."""


def _environment() -> dict[str, str]:
    return {name: os.environ[name] for name in ("LANG", "LC_ALL") if name in os.environ}


def _supported() -> bool:
    if sys.platform != "linux" or not Path("/proc/self/stat").is_file():
        return False
    try:
        result = subprocess.run((sys.executable, "-I", "-B",
            str(Path(__file__).with_name("execution_supervisor.py")), "--probe"),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=_environment(), timeout=1, check=False)
        return result.returncode == 0 and result.stdout == b"SUBREAPER_OK\n"
    except (OSError, subprocess.TimeoutExpired):
        return False


def _child_argv() -> tuple[str, ...]:
    # Nonce binds the private receipt to this particular launch, not its token.
    return (sys.executable, "-I", "-B", str(Path(__file__).with_name("network_http_child.py")), uuid.uuid4().hex)


def _stop(process, path, subject):
    if process.poll() is None:
        try:
            process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            raise UnconfirmedValidation("validation:" + subject, str(path.parent)) from None
    return validation_stopped(path, subject, process.pid)


class GitHubHTTPTransport:
    """One bounded request to api.github.com:443 using private stdin credentials.

    The trusted credential getter itself is operator code, not a repository hook.
    DNS/TLS/response reads happen only in the supervised child. Runtime budget is
    at most five seconds plus bounded cancellation/reaping, with no retry. A lost
    stop receipt is UnconfirmedValidation and retains private forensic evidence.
    """
    def __init__(self, token_provider: Callable[[], str]):
        require(callable(token_provider), "Explicit trusted credential provider required")
        self._token_provider = token_provider

    def request(self, method: str, path: str, body: dict | None, *, seconds: float) -> Response:
        try:
            raw_body = validate_request(method, path, body, seconds)
        except (TypeError, ValueError, RecursionError, UnicodeError):
            raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: invalid bounded HTTP request") from None
        if not _supported():
            raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: bounded HTTPS supervisor unavailable")
        try:
            token = self._token_provider()
            require(type(token) is str and 0 < len(token) <= 4096
                    and all(33 <= ord(c) < 127 for c in token), "Invalid operator credential")
            # Clone input through JSON so a concurrent caller cannot change the
            # request after validation. No token enters argv, environment or log.
            payload = json.dumps({"method": method, "path": path, "body": json.loads(raw_body),
                "seconds": seconds, "token": token}, separators=(",", ":"), allow_nan=False).encode()
            require(len(payload) <= MAX_INPUT_BYTES, "Private request exceeds bound")
        except Exception:
            raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: operator credential unavailable") from None
        with supervised_validation(_child_argv(), max(1, math.ceil(seconds))) as (argv, stop_path, subject):
            try:
                process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, env=_environment(), start_new_session=True)
            except OSError:
                raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: HTTPS process unavailable") from None
            try:
                try:
                    output, _ = process.communicate(input=payload, timeout=seconds)
                except subprocess.TimeoutExpired:
                    _stop(process, stop_path, subject)
                    raise NetworkTransportError("UNKNOWN_NETWORK_OUTCOME: whole-request deadline reached") from None
                observed = validation_stopped(stop_path, subject, process.pid)
                require(observed["status"] == "EXITED" and observed["cli_exit"] == 0
                        and process.returncode == 0, "Trusted HTTP request did not return a confirmed result")
                require(len(output) <= MAX_OUTPUT_BYTES, "Trusted HTTP output exceeds bound")
                reply = decode(output, MAX_OUTPUT_BYTES)
                fields(reply, "status body_base64")
                require(type(reply["status"]) is int and 100 <= reply["status"] <= 599
                        and not 300 <= reply["status"] <= 399 and type(reply["body_base64"]) is str,
                        "Invalid trusted HTTP response")
                raw = base64.b64decode(reply["body_base64"], validate=True)
                require(len(raw) <= MAX_RESPONSE_BYTES, "HTTP response exceeds bound")
                return Response(reply["status"], raw)
            except UnconfirmedValidation:
                raise
            except NetworkTransportError:
                raise
            except (ADPError, ValueError, TypeError, OSError):
                raise NetworkTransportError("UNKNOWN_NETWORK_OUTCOME: trusted HTTP response unavailable") from None
            finally:
                if process.poll() is None:
                    _stop(process, stop_path, subject)
