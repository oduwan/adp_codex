"""Personal enrollment reads: existing gh login is access, never delegation."""
from __future__ import annotations

import urllib.error
import urllib.request

from .discovery_github import API, MAX_RESPONSE, GitHubDiscoveryAdapter, GitHubHTTPTransport, Response
from .discovery_schema import json_value
from .personal_storage import PersonalBlocked
from .schema import require


class PersonalGitHubRead(GitHubHTTPTransport):
    """The existing GET-only discovery routes plus one fixed account endpoint.

    Account profile data is immediately reduced to an immutable numeric ID by
    owned_repository(); it is never passed to workers or retained in memory.
    No mutation, credential issuance or arbitrary URL is supported.
    """
    def get(self, path):
        if path != "/user":
            return super().get(path)
        request = urllib.request.Request(API + "/user", method="GET", headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "adp-codex-read-only"})
        try:
            response = self._opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError):
            return Response(0, None)
        with response:
            raw = response.read(MAX_RESPONSE + 1)
            require(len(raw) <= MAX_RESPONSE, "Account observation exceeds bounds")
            return Response(response.code, json_value(raw, MAX_RESPONSE) if response.code == 200 else None,
                            tuple((name.lower(), value) for name, value in response.headers.items()))


def owned_repository(transport, name, expected_id=None):
    # Reuse accepted header/control/rate-limit validation without widening the
    # ordinary discovery transport's route allowlist. Exhaustion stops this read.
    bounded = GitHubDiscoveryAdapter(name, transport, max_requests=2)
    bounded._halt, bounded._requests = False, 0
    account, repository = bounded._get("/user"), bounded._get("/repos/" + name)
    if account.status != 200 or repository.status != 200:
        raise PersonalBlocked("OWNERSHIP_UNAVAILABLE", "Authenticate the owning account for this exact GitHub repository.")
    user, repo = account.body, repository.body
    require(type(user) is dict and type(user.get("id")) is int and user["id"] > 0,
            "Authenticated account identity is unavailable")
    require(type(repo) is dict and type(repo.get("id")) is int and repo["id"] > 0
            and repo.get("full_name") == name and expected_id in (None, str(repo["id"])),
            "Canonical repository identity changed")
    owner, permissions = repo.get("owner"), repo.get("permissions")
    if (type(owner) is not dict or owner.get("type") != "User" or type(owner.get("id")) is not int or owner["id"] != user["id"]
            or type(permissions) is not dict or permissions.get("pull") is not True):
        raise PersonalBlocked("PERSONAL_OWNER_REQUIRED", "Use personal mode only for an observed personally owned repository with current read access.")
    return {"account_id": user["id"], "repository_id": str(repo["id"]),
            "read_access": True,
            "push_access": permissions.get("push") if type(permissions.get("push")) is bool else None,
            "admin_access": permissions.get("admin") if type(permissions.get("admin")) is bool else None}
