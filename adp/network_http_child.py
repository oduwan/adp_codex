"""Trusted, fixed-origin GitHub HTTP child; never a worker or shell command.

Only private stdin carries the credential. The parent bounds this whole process
with the accepted Linux subreaper, including blocking DNS/TLS/partial reads.
This module is intentionally standard-library-only when executed with -I.
"""
from __future__ import annotations

import base64
import http.client
import json
import math
import re
import ssl
import sys
from urllib.parse import quote, unquote

MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_INPUT_BYTES = MAX_BODY_BYTES + 8192
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 5
UPDATE_REFS_MUTATION = "mutation ADPUpdateRefs($input: UpdateRefsInput!) { updateRefs(input: $input) { clientMutationId } }"


def _text(value: object, maximum: int) -> bool:
    return (type(value) is str and 0 < len(value) <= maximum
            and all(32 <= ord(c) != 127 for c in value))


def _branch(value: object) -> bool:
    return (type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,239}", value) is not None
            and not any(part in value for part in ("..", "//", "@{"))
            and not value.endswith(("/", "."))
            and all(not p.startswith(".") and not p.endswith(".lock") for p in value.split("/")))


def validate_request(method: object, path: object, body: object, seconds: object) -> bytes:
    """Reject unrepresentable routes before looking up a credential or spawning."""
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= MAX_SECONDS or not _text(path, 1024)
            or any(c in path for c in ("?", "#", "\\", "\x00"))):
        raise ValueError("Invalid bounded HTTP request")
    if type(method) is not str or method not in ("GET", "POST"):
        raise ValueError("Unsupported HTTP method")
    if body is not None and type(body) is not dict:
        raise ValueError("HTTP body must be a JSON object")
    if method == "GET" and body is not None:
        raise ValueError("GET body is unsupported")
    if method == "POST" and body is None:
        raise ValueError("Explicit POST body required")
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("HTTP body exceeds bound")
    if path == "/graphql":
        if method != "POST" or set(body) != {"query", "variables"} or type(body["variables"]) is not dict:
            raise ValueError("Unsupported GraphQL request")
        query = body["query"]
        if type(query) is not str or len(query) > 65536:
            raise ValueError("Invalid GraphQL query")
        if query == UPDATE_REFS_MUTATION:
            variables = body["variables"]
            if set(variables) != {"input"} or type(variables["input"]) is not dict:
                raise ValueError("Invalid CAS variables")
            value = variables["input"]
            if (set(value) != {"repositoryId", "refUpdates", "clientMutationId"}
                    or not _text(value["repositoryId"], 256) or not _text(value["clientMutationId"], 128)
                    or type(value["refUpdates"]) is not list or len(value["refUpdates"]) != 1):
                raise ValueError("Invalid CAS input")
            update = value["refUpdates"][0]
            if (type(update) is not dict or set(update) != {"name", "beforeOid", "afterOid", "force"}
                    or type(update["name"]) is not str or not update["name"].startswith("refs/heads/")
                    or not _branch(update["name"][11:]) or update["force"] is not False
                    or any(type(update[k]) is not str or re.fullmatch(r"[0-9a-f]{40}", update[k]) is None
                           for k in ("beforeOid", "afterOid")) or update["afterOid"] == "0" * 40):
                raise ValueError("Only one exact non-force branch CAS is supported")
        elif (re.match(r"\s*query\s+(?:ADPRef|ADPRefs)\b", query) is None
                or re.search(r"\bmutation\b", query) is not None):
            raise ValueError("Unsupported GraphQL operation")
        return raw
    match = re.fullmatch(r"/repos/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})/(.+)", path)
    if match is None or match[2] in (".", ".."):
        raise ValueError("Unsupported fixed-origin API path")
    tail = match[3]
    if (method == "POST" and tail in ("git/blobs", "git/trees", "git/commits")):
        return raw
    if method == "GET" and re.fullmatch(r"git/(?:blobs|trees|commits)/[0-9a-f]{40}", tail):
        return raw
    if method == "GET" and tail.startswith("rules/branches/"):
        encoded = tail[len("rules/branches/"):]
        decoded = unquote(encoded, errors="strict")
        if _branch(decoded) and quote(decoded, safe="") == encoded:
            return raw
    raise ValueError("Unsupported API operation")


def exchange(value: object, validator=validate_request) -> dict:
    """One HTTPS request, no retries, redirects, proxy environment or helper."""
    if type(value) is not dict or set(value) != {"method", "path", "body", "seconds", "token"}:
        raise ValueError("Invalid private request")
    body = validator(value["method"], value["path"], value["body"], value["seconds"])
    token = value["token"]
    if type(token) is not str or not 0 < len(token) <= 4096 or not all(33 <= ord(c) < 127 for c in token):
        raise ValueError("Invalid credential")
    connection = http.client.HTTPSConnection("api.github.com", 443,
        timeout=value["seconds"], context=ssl.create_default_context())
    try:
        connection.request(value["method"], value["path"],
            body=body if value["method"] != "GET" else None,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2026-03-10", "Content-Type": "application/json",
                     "User-Agent": "adp-codex-network-cas"})
        response = connection.getresponse()
        if not 100 <= response.status <= 599 or 300 <= response.status <= 399:
            raise ValueError("HTTP redirects are unsupported")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("HTTP response exceeds bound")
        return {"status": response.status, "body_base64": base64.b64encode(raw).decode("ascii")}
    finally:
        connection.close()


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("Private input exceeds bound")
        result = exchange(json.loads(raw))
        output = (json.dumps(result, separators=(",", ":")) + "\n").encode()
        if len(output) > MAX_OUTPUT_BYTES:
            raise ValueError("Private output exceeds bound")
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        # Never print request, response, credential or exception strings.
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
