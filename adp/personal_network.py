"""Separate gh-auth transport under an explicitly warranted personal envelope.

Unlike signed App mode, repository confinement during object uploads depends on
the operator's finite administrative-quiescence guarantee. No App scope or
independent issuer proof is fabricated. The original signed transport is intact.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import time
from types import SimpleNamespace

from .discovery_github import ENROLLMENT_PATH, PATH, Response as ReadResponse
from .errors import ADPError
from .network_git import GitHubTarget, REF_QUERY, REFS_QUERY, UPDATE_REFS_MUTATION
from .network_http import NetworkTransportError, Response, _supported, supervised_output
from .execution_ports import UnconfirmedValidation
from .personal_network_child import context, validate_personal
from .schema import decode, fields, require
from .github_rules import checked, retained_error
from .runtime_limits import request_allowance, settings_for
from .personal_rules import PERSONAL_REF_QUERY


class PersonalGitHubTransport:
    validator = staticmethod(validate_personal)
    http_child = "personal_network_child.py"
    def __init__(self, target: GitHubTarget, *, protected_roots=(), authorize_write=None, runtime_settings=None):
        require(type(target) is GitHubTarget, "Pin the exact personal target")
        self.target, self.protected_roots = target, tuple(Path(p).resolve() for p in protected_roots)
        self.runtime_settings = settings_for(settings=runtime_settings)
        self.authorize_write = authorize_write
        self._binding = None
        self._context = None
        self._token = None
        self._version = None
        self.last_response = None

    def bind_repository(self, node_id, database_id):
        # This pins the chosen recipient, NOT a server-side token scope.
        expected = (self.target.node_id, self.target.database_id)
        require(type(database_id) is int and (node_id, database_id) == expected
                and self._binding in (None, expected), "Personal HTTP recipient changed")
        self._binding = expected

    def _actor(self):
        require(os.getuid() != 0 and os.getuid() == os.geteuid() and os.getgid() == os.getegid(),
                "Use the normal nonprivileged gh operator account")
        path = shutil.which("gh")
        require(path is not None, "Supported gh auth token command is required")
        binary = Path(path).resolve()
        config = Path(os.environ.get("GH_CONFIG_DIR") or
            str(Path(os.environ.get("XDG_CONFIG_HOME") or str(Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config")) / "gh")).absolute()
        require(all(not binary.is_relative_to(root) and not config.resolve().is_relative_to(root) for root in self.protected_roots),
                "Keep gh credentials and executable outside all product and coordination roots")
        return context(str(binary), str(config))

    def _credential(self, seconds):
        deadline = time.monotonic() + seconds
        actor = self._actor()
        require(self._context in (None, actor), "Selected gh account/configuration/executable changed")
        if self._token is None:
            payload = json.dumps({"kind": "credential", "context": actor}, separators=(",", ":")).encode()
            environment = {name: os.environ[name] for name in ("LANG", "LC_ALL", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR") if name in os.environ}
            remaining = deadline - time.monotonic()
            require(remaining > 0, "Credential context exhausted request budget")
            reply = decode(supervised_output(payload, remaining, child="personal_network_child.py", environment=environment), 16384)
            fields(reply, "context token version")
            token = reply["token"]
            require(reply["context"] == actor and type(token) is str and 0 < len(token) <= 4096
                    and all(33 <= ord(c) < 127 for c in token) and type(reply["version"]) is str
                    and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", reply["version"]), "Actual private gh credential identity differs")
            self._context, self._token = actor, token
            self._version = reply["version"]
        return self._token

    @property
    def credential_binding(self):
        require(self._token is not None and self._actor() == self._context, "Observe the actual gh account first")
        # Private only; never part of public output or portable state.
        return hashlib.sha256(json.dumps(self._context, sort_keys=True).encode() + b"\0" + self._token.encode()).hexdigest()

    @property
    def credential_provenance(self):
        require(self._token is not None and self._actor() == self._context, "Observe the actual gh credential first")
        return {"provider": "gh", "version": self._version, "host": "github.com", "account_context": "NORMAL_LOCAL_UID",
                "executable_sha256": self._context["executable"]["sha256"]}

    def request(self, method, path, body, *, seconds):
        self.last_response = None
        started = time.monotonic()
        try:
            request_allowance(seconds)
            deadline = started + min(seconds, self.runtime_settings.limits.request_timeout_seconds)
            self.validator(method, path, body, seconds)
            require(self._binding == (self.target.node_id, self.target.database_id), "Bind the personal recipient first")
            require(path == "/user" or path == "/graphql" or path.partition("?")[0] == self.target.api
                    or path.startswith(self.target.api + "/"), "Personal route targets another repository")
            if path == "/graphql":
                require(body["query"] in (REF_QUERY, PERSONAL_REF_QUERY, REFS_QUERY, UPDATE_REFS_MUTATION), "Unsupported personal GraphQL query")
                identity = body["variables"]["input"]["repositoryId"] if body["query"] == UPDATE_REFS_MUTATION else body["variables"].get("id")
                require(identity == self.target.node_id, "Personal GraphQL recipient differs")
            mutation = method == "PUT" or method == "POST" and (path != "/graphql" or body["query"] == UPDATE_REFS_MUTATION)
            if mutation:
                require(callable(self.authorize_write) and self.authorize_write() is True,
                        "Separate current publication/quiescence approval is required")
            require(_supported(), "Bounded Linux credential/HTTP supervision unavailable")
            remaining = deadline - time.monotonic()
            require(remaining > 0, "Authorization exhausted request budget")
            token = self._credential(remaining)
            remaining = deadline - time.monotonic()
            require(remaining > 0, "Credential lookup exhausted request budget")
            payload = json.dumps({"kind": "http", "method": method, "path": path, "body": body,
                "seconds": remaining, "token": token}, separators=(",", ":"), allow_nan=False).encode()
            from .runtime_limits import reached
            reached("http.supervision_requested")
            raw_reply = supervised_output(payload, remaining, child=self.http_child)
            reached("http.supervision_returned")
            reply = decode(raw_reply, 2097152)
            fields(reply, "status body_base64 headers")
            require(type(reply["status"]) is int and 100 <= reply["status"] <= 599 and not 300 <= reply["status"] <= 399
                    and type(reply["body_base64"]) is str and type(reply["headers"]) is list and len(reply["headers"]) <= 128,
                    "Malformed private HTTP response")
            headers = reply["headers"]
            require(all(type(h) is list and len(h) == 2 and all(type(x) is str for x in h) for h in headers)
                    and sum(len(k) + len(v) for k, v in headers) <= 65536, "Malformed private response headers")
            raw = base64.b64decode(reply["body_base64"], validate=True)
            require(len(raw) <= 1048576 and self._actor() == self._context, "Response or gh execution context changed")
            headers = tuple((k.lower(), v) for k, v in headers)
            native = ReadResponse(reply["status"], None, headers)
            ordinary_read = method == "GET" and (path == "/user" or bool(PATH.fullmatch(path)
                or ENROLLMENT_PATH.fullmatch(path)) and "/rules/branches/" not in path)
            validated = checked(SimpleNamespace(get=lambda _: native), self.target.owner + "/" + self.target.name,
                path, retain_final_response=ordinary_read)
            require(validated.status == reply["status"], "Unknown native control headers or exhausted rate budget")
            require(not (method == "GET" and reply["status"] == 200 and "/rules/branches/" in path
                    and "?" not in path and any(k == "link" for k, _ in headers)), "Ambiguous nonpaginated rules response")
            # Rejected responses cannot be resurfaced through the read adapter.
            self.last_response = (reply["status"], raw, headers)
            return Response(reply["status"], raw)
        except UnconfirmedValidation:
            raise  # The shared M7 service must retain its durable stop hazard.
        except (ADPError, ValueError, TypeError, KeyError, OSError):
            raise NetworkTransportError("UNKNOWN_PERSONAL_HTTP: verify normal-user gh login, exact approval and supported bounded transport") from None


class PersonalDiscoveryRead:
    """Preserve actual native status/headers through the accepted M4 parser."""
    def __init__(self, service):
        self.service = service
        self.runtime_settings = service.runtime_settings

    def get(self, path, *, seconds=None):
        self.service.transport.last_response = None
        try:
            body = self.service.request("GET", path, missing=True, seconds=seconds)
        except (ADPError, OSError):
            body = None
        observed = self.service.transport.last_response
        if observed is None or self.service.unconfirmed_contexts():
            return ReadResponse(0, None)
        status, raw, headers = observed
        return ReadResponse(status, body if status == 200 else retained_error(status, raw, headers, path), headers)
