"""Narrow GitHub.com plan-error recognition, not policy or write authority."""
from __future__ import annotations

import re
from types import SimpleNamespace

from .discovery_github import GitHubDiscoveryAdapter, Response
from .discovery_schema import digest, json_value
from .errors import ADPError

MESSAGE = "Upgrade to GitHub Pro or make this repository public to enable this feature."
RULES_DOC = "https://docs.github.com/rest/repos/rules#get-rules-for-a-branch"
PROTECTION_DOC = "https://docs.github.com/rest/branches/branch-protection#get-branch-protection"
PLAN_ASSENT = ("I accept the verified private personal repository plan limitation for this exact operation; "
    "protection absence is not independently observed, and no project requirement or check is waived.")


def checked(read, name: str, path: str, *, retain_final_response=False) -> Response:
    """Reuse M4's header/control validation without changing its deny behavior."""
    parser = GitHubDiscoveryAdapter(name, read, max_requests=1)
    parser._halt, parser._requests = False, 0
    response = parser._get(path)
    # A final rate-exhausted 200 remains valid for discovery, never for a write.
    return Response(0, None) if response.status == 200 and parser._halt and not retain_final_response else response


def plan_error(response: Response, path: str) -> dict | None:
    """Only the retained exact REST error; no exception strings or substrings.

    The caller's authenticated transport fixes TLS origin to api.github.com.
    This recognizes availability only. Ownership/ref/consent are separate gates.
    """
    match = re.fullmatch(r"/repos/([^/]+/[^/]+)/(?:rules/branches/([^/?]+)(?:\?per_page=100&page=1)?|branches/([^/?]+)/protection)", path)
    if not match or type(response) is not Response or response.status != 403:
        return None
    clean = checked(SimpleNamespace(get=lambda _: response), match[1], path)
    headers = dict(clean.headers)
    if (clean.status != 403 or headers.get("content-type", "").lower() not in
            ("application/json", "application/json; charset=utf-8")
            or any(k in headers for k in ("link", "location", "retry-after"))
            or any(k in headers and (not re.fullmatch(r"[0-9]{1,20}", headers[k]) or int(headers[k]) == 0)
                   for k in ("x-ratelimit-remaining", "x-ratelimit-reset"))):
        return None
    expected = {"message": MESSAGE, "documentation_url": RULES_DOC if match[2] else PROTECTION_DOC, "status": "403"}
    if type(clean.body) is not dict or clean.body != expected:
        return None
    return {"status": "PLAN_UNAVAILABLE", "http_status": 403, "evidence": digest(expected)}


def retained_error(status: int, raw: bytes, headers: tuple, path: str) -> dict | None:
    """Retain only three recognized constant fields; discard every other error."""
    if type(status) is not int or status != 403 or type(raw) is not bytes or len(raw) > 4096:
        return None
    try:
        body = json_value(raw, 4096)
        return body if plan_error(Response(status, body, headers), path) is not None else None
    except (ADPError, ValueError, TypeError):
        return None
