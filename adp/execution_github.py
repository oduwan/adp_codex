"""Explicitly authorized PR/product-comment port, separate from M4 GETs."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .discovery_github import API, Response, _NoRedirect
from .discovery_schema import NAME, digest, json_value
from .execution_types import ExternalObservation
from .policy_types import Operation
from .schema import encode, require


class GitHubMutationTransport:
    def __init__(self, token):
        require(type(token) is str and 0 < len(token) <= 4096 and all(32 < ord(c) < 127 for c in token), "Explicit forge authentication is required")
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirect())

    def request(self, method, path, payload=None):
        require(method in ("GET", "POST") and re.fullmatch(r"/repos/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*(?:/(?:pulls|issues)(?:/[1-9][0-9]*(?:/comments)?)?)?(?:\?[A-Za-z0-9_=&-]+)?", path), "Unsupported forge request")
        request = urllib.request.Request(API + path, data=encode(payload) if payload is not None else None, method=method,
            headers={"Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json", "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "adp-conductor"})
        try:
            response = self._opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError):
            return Response(0, None)
        with response:
            raw = response.read(1048577)
            require(len(raw) <= 1048576, "Forge response exceeds bounds")
            return Response(response.code, json_value(raw, 1048576) if response.code in (200, 201) else None)


class GitHubForgeBackend:
    """Observe before submission and after uncertain responses. Never retry blind.

    GitHub comments have no atomic create-if-absent key. After any possible
    submission, an empty search is UNKNOWN, even if pagination completed. Only
    the actual exact marker/body/HEAD can reconcile a lost response as PRESENT.
    """
    def __init__(self, repository, repository_id, transport, authority):
        require(type(repository) is str and NAME.fullmatch(repository), "Explicit GitHub repository required")
        self.repository, self.repository_id = repository, str(repository_id)
        self.transport, self.authority = transport, authority

    @staticmethod
    def marker(key):
        require(re.fullmatch(r"[0-9a-f]{64}", key), "Invalid stable publication identity")
        return "<!-- adp-product:v1:" + key + " -->"

    def _identity(self):
        observed = self.transport.request("GET", "/repos/" + self.repository)
        return (observed.status == 200 and type(observed.body) is dict
            and str(observed.body.get("id")) == self.repository_id
            and observed.body.get("full_name", "").lower() == self.repository.lower())

    def _route(self, operation, payload):
        if operation == Operation.PR:
            return "/repos/" + self.repository + "/pulls"
        require(operation == Operation.REPORT, "Only PR and product-report mutations are supported")
        match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/issues/([1-9][0-9]*)", payload.get("target", ""))
        require(match and match[1].lower() == self.repository.lower(), "Product report target is outside the admitted repository")
        return "/repos/" + self.repository + "/issues/" + match[2] + "/comments"

    def observe(self, key, operation, payload, *, attempted=False):
        if not self._identity():
            return ExternalObservation("UNKNOWN")
        route = self._route(operation, payload)
        suffix = "state=all&" if operation == Operation.PR else ""
        marker = self.marker(key)
        expected_body = payload["body"] + "\n\n" + marker
        count, matches = 0, []
        for page in range(1, 21):
            response = self.transport.request("GET", f"{route}?{suffix}per_page=100&page={page}")
            if response.status != 200 or type(response.body) is not list:
                return ExternalObservation("UNKNOWN")
            count += len(response.body)
            if count > 256:
                return ExternalObservation("UNKNOWN")
            if any(type(item) is not dict or item.get("body") is not None and type(item.get("body")) is not str for item in response.body):
                return ExternalObservation("UNKNOWN")
            matches.extend(item for item in response.body if marker in (item.get("body") or ""))
            if len(matches) > 1:
                return ExternalObservation("UNKNOWN")
            if len(response.body) < 100:
                break
        else:
            return ExternalObservation("UNKNOWN")
        if not matches:
            return ExternalObservation("UNKNOWN" if attempted else "ABSENT")
        item = matches[0]
        if item.get("body") != expected_body:
            return ExternalObservation("UNKNOWN")
        revision = payload["revision"]
        if operation == Operation.PR:
            number = item.get("number")
            if type(number) is not int or number < 1:
                return ExternalObservation("UNKNOWN")
            detail = self.transport.request("GET", route + "/" + str(number))
            if detail.status != 200 or type(detail.body) is not dict:
                return ExternalObservation("UNKNOWN")
            head, base = detail.body.get("head") or {}, detail.body.get("base") or {}
            if type(head) is not dict or type(base) is not dict or any(type(ref.get("repo")) is not dict for ref in (head, base)):
                return ExternalObservation("UNKNOWN")
            revision = head.get("sha")
            if (revision != payload["revision"] or detail.body.get("title") != payload["title"]
                    or detail.body.get("body") != expected_body or detail.body.get("draft") is not payload["draft"]
                    or base.get("ref") != payload["base_ref"].removeprefix("refs/heads/")
                    or head.get("ref") != payload["head_ref"].removeprefix("refs/heads/")
                    or any(str(ref.get("repo", {}).get("id")) != self.repository_id
                           or ref.get("repo", {}).get("full_name", "").lower() != self.repository.lower() for ref in (head, base))):
                return ExternalObservation("UNKNOWN")
        reference = item.get("html_url")
        if type(reference) is not str or not reference.startswith("https://github.com/" + self.repository + "/"):
            return ExternalObservation("UNKNOWN")
        return ExternalObservation("PRESENT", reference, revision, digest(payload["body"]))

    def submit(self, key, operation, payload, *, authorization=None, plan_digest=None):
        subject = digest({"id": key, "plan": plan_digest, "payload": payload})
        require(authorization is not None and self.authority is not None
                and self.authority.verify(authorization, purpose="execution/effect", subject=subject) is True,
                "Git credentials grant no mutation authority")
        require(self._identity(), "Repository identity/permissions changed")
        route = self._route(operation, payload)
        body = payload["body"] + "\n\n" + self.marker(key)
        if operation == Operation.PR:
            request = {"head": payload["head_ref"].removeprefix("refs/heads/"),
                "base": payload["base_ref"].removeprefix("refs/heads/"), "title": payload["title"], "draft": payload["draft"], "body": body}
        else:
            request = {"body": body}
        response = self.transport.request("POST", route, request)
        # A response alone is not sufficient: observe actual source/body/HEAD.
        return self.observe(key, operation, payload, attempted=True)
