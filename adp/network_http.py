"""Explicit trusted HTTP transport with fixed origin and enforced process deadline.

This is an operator-side transport, never a worker capability or authorization
provider. Only a caller's separately qualified exact operation may use it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol
import uuid

from .errors import ADPError
from .guard_types import Attestation
from .execution_ports import UnconfirmedValidation, supervised_validation, validation_stopped
from .network_http_child import (MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES,
    UPDATE_REFS_MUTATION, validate_request)
from .schema import decode, fields, require


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


class HTTPTransport(Protocol):
    def bind_repository(self, node_id: str, database_id: int) -> None: ...
    def request(self, method: str, path: str, body: dict | None, *, seconds: float) -> Response: ...


class NetworkTransportError(ADPError):
    """A transport failure is never proof that a submitted mutation was absent."""


SCOPE_PURPOSE = "github/installation-token-scope"
REQUIRED_PERMISSIONS = (("contents", "write"), ("metadata", "read"))


@dataclass(frozen=True)
class ScopedInstallationToken:
    """Private operator evidence, never portable state, a worker input or a grant.

    The authority must verify the actual authenticated token-issuance request and
    response, not these caller-supplied labels alone. A token scoped by immutable
    repository database ID prevents an owner/name reuse race from writing to a
    different repository. No PAT, broad installation token or refresh is accepted.
    """
    token: str = field(repr=False)
    installation_id: int
    repository_ids: tuple[int, ...]
    repository_node_id: str
    permissions: tuple[tuple[str, str], ...]
    issued_at: int
    expires_at: int
    issuance_request: str
    issuance_response: str
    kind: str = "installation"
    evidence: Attestation | None = field(default=None, repr=False)


class TokenScopeAuthority(Protocol):
    """Trusted external issuer verifier; no default or permissive implementation.

    A true verdict authenticates exact token bytes, installation, one-repository
    selection, returned permissions/expiry and both issuance provenance records.
    The private subject/proof must never enter argv, worker/runtime receipts,
    portable memory or product reports. This is independent from M3 permission.
    """
    def verify(self, evidence: Attestation, *, purpose: str, subject: str) -> bool: ...


def _scope_fields(value: ScopedInstallationToken, permissions=REQUIRED_PERMISSIONS) -> dict:
    require(type(value) is ScopedInstallationToken, "Unsupported credential type")
    require(type(value.kind) is str and value.kind == "installation"
            and type(value.token) is str and 0 < len(value.token) <= 4096
            and all(33 <= ord(c) < 127 for c in value.token), "Unsupported installation credential")
    require(type(value.installation_id) is int and 0 < value.installation_id < 10**18
            and type(value.repository_ids) is tuple and len(value.repository_ids) == 1
            and type(value.repository_ids[0]) is int and 0 < value.repository_ids[0] < 10**18,
            "One immutable installation repository is required")
    require(type(value.repository_node_id) is str and 0 < len(value.repository_node_id) <= 256
            and all(32 <= ord(c) != 127 for c in value.repository_node_id), "Pinned repository node is required")
    require(type(value.permissions) is tuple and value.permissions == permissions
            and all(type(p) is tuple for p in value.permissions), "Narrow installation permissions are required")
    require(type(value.issued_at) is int and type(value.expires_at) is int
            and 0 <= value.issued_at < value.expires_at < 10**18
            and value.expires_at - value.issued_at <= 3600, "Bounded installation lifetime is required")
    for reference in (value.issuance_request, value.issuance_response):
        require(type(reference) is str and 0 < len(reference) <= 256
                and all(32 <= ord(c) != 127 for c in reference), "Both issuance provenance records are required")
    return {"token_sha256": hashlib.sha256(value.token.encode()).hexdigest(),
            "installation_id": value.installation_id, "repository_ids": value.repository_ids,
            "repository_node_id": value.repository_node_id, "permissions": value.permissions,
            "issued_at": value.issued_at, "expires_at": value.expires_at,
            "issuance_request": value.issuance_request, "issuance_response": value.issuance_response,
            "kind": value.kind}


def installation_scope_subject(value: ScopedInstallationToken, *, permissions=REQUIRED_PERMISSIONS) -> str:
    """Private issuer-verification digest; not a portable evidence reference."""
    fields = _scope_fields(value, permissions)
    raw = json.dumps({"purpose": SCOPE_PURPOSE, "scope": fields}, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


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


def _child_argv(filename="network_http_child.py") -> tuple[str, ...]:
    # Nonce binds the private receipt to this particular launch, not its token.
    return (sys.executable, "-I", "-B", str(Path(__file__).with_name(filename)), uuid.uuid4().hex)


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

    The single pinned credential requires an independently verified GitHub App
    installation issuance restricted to exactly one immutable repository and
    narrow permissions. It cannot be replaced or refreshed in this instance.
    DNS/TLS/response reads happen only in the supervised child. Runtime budget is
    at most five seconds plus bounded cancellation/reaping, with no retry. A lost
    stop receipt is UnconfirmedValidation and retains private forensic evidence.
    """
    permissions = REQUIRED_PERMISSIONS
    validator = staticmethod(validate_request)
    child = "network_http_child.py"

    def __init__(self, token: ScopedInstallationToken, *, authority: TokenScopeAuthority,
                 clock: Callable[[], int] | None = None):
        self._credential = token
        self._authority = authority
        self._clock = clock or (lambda: int(time.time()))
        self._binding: tuple[str, int] | None = None
        self._scope_subject = None
        self._last_clock = None
        self._verified_scope()

    def _verified_scope(self) -> ScopedInstallationToken:
        try:
            value = self._credential
            subject = installation_scope_subject(value, permissions=self.permissions)
            require(self._scope_subject is None or subject == self._scope_subject,
                    "Pinned credential cannot be changed")
            now = self._clock()
            require(type(now) is int and value.issued_at <= now < value.expires_at
                    and (self._last_clock is None or now >= self._last_clock), "Installation credential is not current")
            evidence = value.evidence
            require(type(evidence) is Attestation and evidence.subject == subject
                    and self._authority is not None and callable(getattr(self._authority, "verify", None))
                    and self._authority.verify(evidence, purpose=SCOPE_PURPOSE, subject=subject) is True,
                    "Authenticated issuance scope is required")
            self._scope_subject = subject
            self._last_clock = now
            return value
        except Exception:
            # Never include token, private proof/subject, issuer response or a
            # verifier exception in an error. A credential proves no M3 rights.
            raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: verified single-repository installation credential required") from None

    def bind_repository(self, node_id: str, database_id: int) -> None:
        value = self._verified_scope()
        expected = (value.repository_node_id, value.repository_ids[0])
        require(type(node_id) is str and type(database_id) is int
                and (node_id, database_id) == expected and (self._binding is None or self._binding == expected),
                "HTTP repository identity does not match the pinned installation scope")
        self._binding = expected

    def request(self, method: str, path: str, body: dict | None, *, seconds: float) -> Response:
        try:
            raw_body = self.validator(method, path, body, seconds)
        except (TypeError, ValueError, RecursionError, UnicodeError):
            raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: invalid bounded HTTP request") from None
        if not _supported():
            raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: bounded HTTPS supervisor unavailable")
        value = self._verified_scope()
        require(self._binding == (value.repository_node_id, value.repository_ids[0]),
                "Bind the immutable installation repository before requests")
        try:
            checked_body = json.loads(raw_body)
            if path == "/graphql" and checked_body["query"] == UPDATE_REFS_MUTATION:
                require(checked_body["variables"]["input"]["repositoryId"] == value.repository_node_id,
                        "CAS repository differs from scoped installation identity")
            # Clone input through JSON so a concurrent caller cannot change the
            # request after validation. No token enters argv, environment or log.
            payload = json.dumps({"method": method, "path": path, "body": checked_body,
                "seconds": seconds, "token": value.token}, separators=(",", ":"), allow_nan=False).encode()
            require(len(payload) <= MAX_INPUT_BYTES, "Private request exceeds bound")
        except Exception:
            raise NetworkTransportError("UNSUPPORTED_ATOMIC_REF: operator credential unavailable") from None
        child = _child_argv() if self.child == "network_http_child.py" else _child_argv(self.child)
        with supervised_validation(child, max(1, math.ceil(seconds))) as (argv, stop_path, subject):
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
