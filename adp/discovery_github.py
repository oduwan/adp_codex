"""Bounded GET-only GitHub REST discovery, with explicit incomplete coverage."""
from __future__ import annotations

import copy
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from .config import Config
from .errors import ADPError
from .git import value
from .schema import integer, require, string
from .discovery_schema import (MAX_ITEMS, NAME, digest, json_value, key, text,
    validate_snapshot)
from .discovery_types import (Coverage, Identity, Issue, PullRequest, Relation,
    Repository, Snapshot, Target, Text)

API = "https://api.github.com"
MAX_RESPONSE = 1024 * 1024
PATH = re.compile(r"/repos/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}(?:/(?:issues|pulls)(?:/[1-9][0-9]*(?:/(?:comments|timeline|sub_issues|dependencies/blocked_by))?)?)?(?:\?[A-Za-z0-9_=&-]+)?\Z")


@dataclass(frozen=True)
class Response:
    status: int
    body: object
    headers: tuple[tuple[str, str], ...] = ()


class ReadOnlyTransport(Protocol):
    def get(self, path: str) -> Response: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubHTTPTransport:
    """Only fixed-origin HTTPS GETs. No redirects, subprocesses or disk cache."""
    def __init__(self, token: str):
        require(type(token) is str and 0 < len(token) <= 4096
                and all(32 < ord(c) < 127 for c in token), "A bounded authentication token is required")
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirect())

    def get(self, path: str) -> Response:
        require(type(path) is str and PATH.fullmatch(path), "Unsupported read-only GitHub path")
        request = urllib.request.Request(API + path, method="GET", headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "adp-codex-read-only"})
        try:
            response = self._opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError):
            return Response(0, None)
        with response:
            headers = tuple((k.lower(), v) for k, v in response.headers.items())
            raw = response.read(MAX_RESPONSE + 1)
            require(len(raw) <= MAX_RESPONSE, "GitHub response exceeds bounds")
            # Error bodies can contain private data; keep only status/headers.
            body = json_value(raw, MAX_RESPONSE) if response.code == 200 else None
            return Response(response.code, body, headers)


class FixtureTransport:
    """Explicit API responses for offline callers. Missing entries are UNKNOWN."""
    def __init__(self, responses: dict[str, Response | tuple[Response, ...]]):
        self.responses = copy.deepcopy(responses)
        self.calls: list[str] = []
        self._positions: dict[str, int] = {}

    def get(self, path: str) -> Response:
        require(PATH.fullmatch(path), "Unsupported fixture GET path")
        self.calls.append(path)
        item = self.responses.get(path, Response(404, None))
        if type(item) is tuple:
            position = self._positions.get(path, 0)
            self._positions[path] = position + 1
            item = item[min(position, len(item) - 1)]
        return copy.deepcopy(item)


def _id(item: dict) -> str:
    raw = item.get("node_id", item.get("id"))
    require(type(raw) in (str, int) and type(raw) is not bool, "Missing opaque GitHub object identity")
    result = str(raw)
    string(result)
    return result


def _repo_id(item: dict) -> str:
    raw = item.get("id")
    require(type(raw) in (str, int) and type(raw) is not bool, "Missing stable repository identity")
    string(str(raw))
    return str(raw)


def _author(item: dict) -> str:
    # Numeric/node user identity avoids interpreting mutable login text as role.
    user = item.get("user")
    return "github-user:" + _id(user) if type(user) is dict else "UNKNOWN"


def _issue_revision(item: dict) -> str:
    # List/detail representations have different incidental API fields.
    # Bind the semantic issue revision, not those representation differences.
    return digest({"id": _id(item), "url": item.get("url"), "number": item.get("number"),
        "title": item.get("title"), "body": item.get("body"), "state": item.get("state"),
        "state_reason": item.get("state_reason"), "updated_at": item.get("updated_at"),
        "author": _author(item), "labels": sorted(l["name"] if type(l) is dict else l for l in item.get("labels", [])),
        "assignees": sorted(_id(a) for a in item.get("assignees", []))})


def _target(item: dict) -> Target:
    require(type(item) is dict, "Malformed linked issue")
    match = re.fullmatch(r"https://api.github.com/repos/([^/]+/[^/]+)/(?:issues|pulls)/([1-9][0-9]*)", item.get("url", ""))
    require(match and NAME.fullmatch(match[1]), "Unverified linked repository/source URL")
    require(type(item.get("number")) is int and item["number"] == int(match[2]), "Linked issue number/URL mismatch")
    return Target(match[1], int(match[2]), _id(item))


def inferred(body: str, repository: str, source: str) -> tuple[Relation, ...]:
    """Conservative references only; text is never interpreted as authority."""
    result = []
    pattern = r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)|(?<![\w/])(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#([1-9][0-9]*)"
    for match in re.finditer(pattern, body):
        name, number = (match[1], match[2]) if match[1] else (match[3] or repository, match[4])
        prefix = body[max(0, body.rfind("\n", 0, match.start()) + 1):match.start()].lower()
        kind = "DUPLICATE_OF" if "duplicate of" in prefix else "SUPERSEDED_BY" if "superseded by" in prefix else (
            "BLOCKED_BY" if any(p in prefix for p in ("depends on", "blocked by", "requires")) else "RELATED")
        result.append(Relation(kind, Target(name, int(number)), "INFERRED", source + ":" + str(match.start())))
        require(len(result) <= 256, "Too many textual references")
    return tuple(result)


class GitHubDiscoveryAdapter:
    def __init__(self, repository: str, transport: ReadOnlyTransport, *, expected_id: str | None = None,
                 config: Config | None = None, clock=None, per_page=100, max_pages=20, max_requests=2048):
        require(type(repository) is str and NAME.fullmatch(repository), "Select an explicit GitHub owner/repository")
        require(type(per_page) is int and 1 <= per_page <= 100 and type(max_pages) is int
                and 1 <= max_pages <= 20 and type(max_requests) is int and 1 <= max_requests <= 2048, "Invalid discovery budget")
        if expected_id is not None:
            string(expected_id)
        self.name, self.transport, self.expected_id, self.config = repository, transport, expected_id, config
        self.clock = clock or (lambda: int(time.time()))
        self.per_page, self.max_pages, self.max_requests = per_page, max_pages, max_requests

    def _get(self, path):
        if self._halt or self._requests >= self.max_requests:
            return Response(-1, None)
        self._requests += 1
        try:
            response = self.transport.get(path)
            require(type(response) is Response and type(response.status) is int
                    and type(response.headers) is tuple, "Malformed GitHub transport response")
            require(len(response.headers) <= 128, "Too many HTTP headers")
            headers = {}
            for name, value in response.headers:
                string(name, 128)
                string(value, 4096)
                require(name.lower() not in headers, "Duplicate HTTP header")
                headers[name.lower()] = value
            # Bound even injected responses; credentials and error bodies are
            # never included in the observation or diagnostics.
            if response.status == 200:
                from .schema import encode
                encode(response.body, MAX_RESPONSE)
            if response.status in (401, 403, 429) or headers.get("x-ratelimit-remaining") == "0":
                self._halt = True
            return Response(response.status, response.body, tuple(headers.items()))
        except (ADPError, OSError, ValueError, TypeError):
            return Response(0, None)

    @staticmethod
    def _failure(response):
        headers = dict(response.headers)
        if response.status == -1:
            return "NOTRUN", "Request budget exhausted or rate-limit containment active"
        if response.status == 429 or response.status == 403 and (
                headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers):
            return "RATE_LIMITED", "Rate limit; no automatic retry"
        if response.status in (401, 403):
            return "FORBIDDEN", "Authentication/permission unavailable"
        return "UNKNOWN", "Unavailable, malformed, redirected or unsupported metadata"

    def _coverage(self, name, path, status, values, pages, detail="", response=None):
        retry = None
        if response is not None:
            raw = dict(response.headers).get("retry-after", "")
            retry = int(raw) if raw.isdigit() and len(raw) < 10 else None
            reset = dict(response.headers).get("x-ratelimit-reset", "")
            if retry is None and reset.isdigit() and len(reset) < 18:
                retry = max(0, int(reset) - self._now)
        self._coverage_items.append(Coverage(name, status, API + path, digest(values), pages, detail, retry))

    def _one(self, path, name):
        response = self._get(path)
        if response.status != 200 or type(response.body) is not dict:
            status, detail = self._failure(response)
            self._coverage(name, path, status, None, 0, detail, response)
            return None
        self._coverage(name, path, "COMPLETE", response.body, 1)
        return response.body

    def _pages(self, path, name, query=""):
        items, page = [], 1
        seen = set()
        while page <= self.max_pages:
            route = f"{path}?{query + '&' if query else ''}per_page={self.per_page}&page={page}"
            response = self._get(route)
            if response.status != 200 or type(response.body) is not list:
                status, detail = self._failure(response)
                self._coverage(name, path, status if not items else "PARTIAL", items, page - 1, detail, response)
                return items
            batch = response.body
            if len(batch) > self.per_page:
                self._coverage(name, path, "PARTIAL", items, page - 1, "Page exceeds requested inventory bound")
                return items
            duplicate = any(digest(item) in seen for item in batch)
            seen.update(digest(item) for item in batch)
            items.extend(batch)
            if len(items) > MAX_ITEMS or duplicate:
                items = items[:MAX_ITEMS]
                self._coverage(name, path, "PARTIAL", items, page, "Duplicate/overlapping pages or inventory bound exceeded")
                return items
            link = dict(response.headers).get("link", "")
            has_next = False
            if link:
                for entry in link.split(","):
                    match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="([a-z]+)"\s*', entry)
                    if match is None:
                        self._coverage(name, path, "PARTIAL", items, page, "Malformed pagination link")
                        return items
                    if match[2] == "next":
                        try:
                            parsed = urlsplit(match[1])
                        except ValueError:
                            self._coverage(name, path, "PARTIAL", items, page, "Malformed pagination URL")
                            return items
                        expected = parse_qs(route.split("?", 1)[1])
                        expected["page"] = [str(page + 1)]
                        if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.path != path or parsed.fragment or parse_qs(parsed.query) != expected:
                            self._coverage(name, path, "PARTIAL", items, page, "Unsafe or nonsequential pagination link")
                            return items
                        has_next = True
            if not has_next and len(batch) < self.per_page:
                self._coverage(name, path, "COMPLETE", items, page)
                return items
            page += 1
        self._coverage(name, path, "PARTIAL", items, page - 1, "Pagination budget exhausted")
        return items

    def _local(self):
        if self.config is None:
            return None, None, None
        cfg = Config.discover(self.config.root, remote=self.config.remote, repository_id=self.config.identity)
        endpoint = value(cfg.root, "remote", "get-url", cfg.remote)
        match = re.fullmatch(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?", endpoint)
        require(match and match[1].lower() == self.name.lower(), "Selected Git remote does not identify the requested GitHub repository")
        return cfg.identity, value(cfg.root, "symbolic-ref", "--quiet", "HEAD"), value(cfg.root, "rev-parse", "HEAD")

    def discover(self) -> Snapshot:
        self._halt, self._requests, self._coverage_items = False, 0, []
        self._now = self.clock()
        integer(self._now)
        local = self._local()
        prefix = "/repos/" + self.name
        metadata = self._one(prefix, "repository")
        require(metadata is not None, "Repository identity cannot be authenticated; discovery refused")
        rid = _repo_id(metadata)
        require(type(metadata.get("full_name")) is str and metadata["full_name"].lower() == self.name.lower()
                and (self.expected_id is None or rid == self.expected_id), "GitHub repository identity mismatch")
        repo = Repository(rid, metadata["full_name"], "https://github.com/" + metadata["full_name"], *local)
        issue_rows = self._pages(prefix + "/issues", "issues", "state=all&sort=created&direction=asc")
        pull_rows = self._pages(prefix + "/pulls", "pulls", "state=all&sort=created&direction=asc")
        issues, pulls = {}, {}
        for row in issue_rows:
            if type(row) is dict and "pull_request" in row:
                continue
            try:
                target = _target(row)
                require(target.repository.lower() == repo.name.lower(), "Foreign issue inventory")
                number, iid = target.number, Identity(rid, target.issue_id)
                require(number not in issues, "Duplicate/conflicting issue inventory identity")
                base = prefix + "/issues/" + str(number)
                label = "issue:" + key(iid)
                comments_raw = self._pages(base + "/comments", label + ":comments")
                timeline = self._pages(base + "/timeline", label + ":timeline")
                dependencies = self._pages(base + "/dependencies/blocked_by", label + ":blocked_by")
                children = self._pages(base + "/sub_issues", label + ":sub_issues")
                comments = tuple(sorted((Text(_id(c), c.get("body") or "", _author(c), c["updated_at"],
                    f"{API}{base}/comments#{_id(c)}") for c in comments_raw), key=lambda c: c.id))
                relations = [Relation("BLOCKED_BY", _target(dep), "NATIVE", API + base + "/dependencies/blocked_by") for dep in dependencies]
                relations.extend(Relation("SUB_ISSUE", _target(child), "NATIVE", API + base + "/sub_issues") for child in children)
                notices = []
                for event in timeline:
                    if type(event) is dict and event.get("event") in {"marked_as_duplicate", "unmarked_as_duplicate"}:
                        notices.append("Native duplicate history requires current canonical disposition assessment: " + digest(event))
                    if type(event) is dict and event.get("event") == "cross-referenced":
                        source = event.get("source", {}).get("issue")
                        if type(source) is dict and "pull_request" in source:
                            relations.append(Relation("PULL_REQUEST", _target(source), "NATIVE", API + base + "/timeline#" + digest(event)))
                body = row.get("body") or ""
                text(body)
                relations.extend(inferred(body, repo.name, API + base + ":body"))
                for comment in comments:
                    relations.extend(inferred(comment.body, repo.name, comment.source))
                current = self._one(base, label + ":current")
                if current is None or _issue_revision(current) != _issue_revision(row):
                    self._coverage(label + ":stable", base, "CHANGED", None, 0, "Issue changed or became inaccessible during observation")
                else:
                    self._coverage(label + ":stable", base, "COMPLETE", current, 1)
                issue = Issue(iid, number, f"{repo.url}/issues/{number}", row["title"], body, row["state"],
                    row.get("state_reason"), row["updated_at"], _issue_revision(row),
                    tuple(sorted(l["name"] if type(l) is dict else l for l in row.get("labels", []))),
                    tuple(sorted(_id(a) for a in row.get("assignees", []))),
                    tuple(sorted({_author(row), *(c.author for c in comments)})), comments,
                    tuple(sorted(set(relations), key=lambda r: (r.kind, r.target.repository, r.target.number, r.source))), tuple(sorted(set(notices))))
                from .discovery_schema import validate_issue
                validate_issue(issue, repo)
                if "UNKNOWN" in issue.authors:
                    self._coverage(label + ":authors", base, "UNKNOWN", None, 0, "Canonical source author identity unavailable")
                require(number not in issues, "Duplicate/conflicting issue inventory identity")
                issues[number] = issue
            except (ADPError, KeyError, TypeError, ValueError, AttributeError):
                self._coverage("invalid-issue:" + str(len(self._coverage_items)), prefix + "/issues", "PARTIAL", None, 0, "Malformed, conflicting or oversized issue observation")
        for row in pull_rows:
            try:
                require(type(row) is dict and type(row.get("number")) is int, "Malformed PR inventory")
                number = row["number"]
                integer(number, 1)
                route = prefix + "/pulls/" + str(number)
                current = self._one(route, "pull:" + str(number))
                if current is None:
                    continue
                require(current.get("number") == number and _id(current) == _id(row)
                        and current.get("url") == API + route, "PR identity mismatch")
                if (row.get("head", {}).get("sha"), row.get("updated_at")) != (current.get("head", {}).get("sha"), current.get("updated_at")):
                    self._coverage("pull-stable:" + str(number), route, "CHANGED", None, 0, "PR HEAD/revision changed during observation")
                head, base = current.get("head") or {}, current.get("base") or {}
                require(base.get("repo") is not None and _repo_id(base["repo"]) == rid, "Foreign PR base repository")
                pr = PullRequest(Identity(rid, _id(current)), number, f"{repo.url}/pull/{number}", current["state"],
                    current["updated_at"], digest(current), head.get("sha"), head.get("ref"),
                    _repo_id(head["repo"]) if head.get("repo") else None, base.get("sha"), base.get("ref"),
                    current.get("merged"), current.get("draft"))
                if None in (pr.head_sha, pr.head_ref, pr.head_repository_id, pr.base_sha, pr.base_ref, pr.merged, pr.draft):
                    self._coverage("pull-incomplete:" + str(number), route, "UNKNOWN", None, 0, "Incomplete PR refs/disposition")
                require(number not in pulls, "Duplicate PR inventory")
                pulls[number] = pr
            except (ADPError, KeyError, TypeError, ValueError, AttributeError):
                self._coverage("invalid-pull:" + str(len(self._coverage_items)), prefix + "/pulls", "PARTIAL", None, 0, "Malformed or conflicting PR observation")
        # Re-observe inventory membership/revisions and identity. REST does not
        # offer a transaction; drift is reported rather than silently mixed.
        refreshed_issues = self._pages(prefix + "/issues", "issues-refresh", "state=all&sort=created&direction=asc")
        refreshed_pulls = self._pages(prefix + "/pulls", "pulls-refresh", "state=all&sort=created&direction=asc")
        if digest(sorted(issue_rows, key=digest)) != digest(sorted(refreshed_issues, key=digest)) or digest(sorted(pull_rows, key=digest)) != digest(sorted(refreshed_pulls, key=digest)):
            self._coverage("inventory-stable", prefix, "CHANGED", None, 0, "Inventory changed during discovery")
        else:
            self._coverage("inventory-stable", prefix, "COMPLETE", None, 1)
        latest = self._one(prefix, "repository-refresh")
        if latest is None or _repo_id(latest) != rid or self._local() != local:
            self._coverage("context-stable", prefix, "CHANGED", None, 0, "Repository identity or checkout changed during discovery")
        else:
            self._coverage("context-stable", prefix, "COMPLETE", None, 1)
        result = Snapshot(repo, tuple(issues[n] for n in sorted(issues)), tuple(pulls[n] for n in sorted(pulls)),
                          tuple(sorted(self._coverage_items, key=lambda c: c.name)), self._now)
        validate_snapshot(result)
        return result
