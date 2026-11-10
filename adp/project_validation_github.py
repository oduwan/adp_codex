"""Bounded fixed-origin GET observations of project GitHub checks/statuses.

No workflow dispatch, command runner, package installation, test configuration or
project write exists here. Transport and project provenance signer are explicitly
installed trusted integrations, not services obtained from issue/CI text.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from collections import Counter
from copy import copy
from dataclasses import replace
from datetime import datetime
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .discovery_github import Response
from .errors import ADPError
from .policy_schema import digest, ref
from .project_validation import observation_subject
from .project_validation_types import ProjectObservation, ProjectResult, ResultStatus
from .schema import decode, encode, integer, require, string

API = "https://api.github.com"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
ROUTE = re.compile(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/(?:pulls/[1-9][0-9]*|git/ref/heads/[A-Za-z0-9%_.-]+|commits/[0-9a-f]{40,64}/(?:statuses|check-runs|check-suites)))?(?:\?[A-Za-z0-9_=&-]+)?\Z")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubValidationHTTP:
    """GET only, fixed origin, no redirects and no error body disclosure."""
    def __init__(self, token: str):
        require(type(token) is str and 0 < len(token) <= 4096
                and all(32 < ord(c) < 127 for c in token), "Bounded authentication token required")
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirect())

    def get(self, path: str, *, seconds: float) -> Response:
        require(type(path) is str and ROUTE.fullmatch(path) and 0 < seconds <= 30,
                "Unsupported project-validation GET")
        route, separator, raw_query = path.partition("?")
        if separator:
            options = parse_qs(raw_query, strict_parsing=True)
            expected = {"page", "per_page", "filter"} if route.endswith("/check-runs") else {"page", "per_page"}
            require(route.endswith(("/statuses", "/check-runs", "/check-suites"))
                    and set(options) == expected and all(len(v) == 1 for v in options.values())
                    and all(options[k][0].isdigit() for k in ("page", "per_page"))
                    and 1 <= int(options["page"][0]) <= 20 and 1 <= int(options["per_page"][0]) <= 100
                    and ("filter" not in options or options["filter"] == ["all"]), "Unsupported GET query")
        if "/git/ref/heads/" in path:
            encoded = route.split("/git/ref/heads/", 1)[1]
            decoded = unquote(encoded)
            require(quote(decoded, safe="") == encoded, "Noncanonical source ref encoding")
            ref("refs/heads/" + decoded)
        request = urllib.request.Request(API + path, method="GET", headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10", "User-Agent": "adp-project-evidence-read-only"})
        try:
            response = self._opener.open(request, timeout=seconds)
        except urllib.error.HTTPError as exc:
            response = exc
        except (OSError, urllib.error.URLError):
            return Response(0, None)
        with response:
            headers = tuple((k.lower(), v) for k, v in response.headers.items())
            if response.code != 200:
                return Response(response.code, None, headers)
            raw = response.read(1048577)
            require(len(raw) <= 1048576, "Project evidence response exceeds bounds")
            # Both the list statuses endpoint and object checks endpoint are supported.
            body = decode(b'{"response":' + raw + b'}', 1048590)["response"]
            return Response(response.code, body, headers)


def _time(value):
    require(type(value) is str and len(value) <= 40, "Missing provider record time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Provider time needs an explicit timezone")
    result = int(parsed.timestamp())
    integer(result)
    return result


class GitHubEvidenceSource:
    """Observe a pinned GitHub repository through an explicit read-only transport.

    `attest(query, observation)` must independently authenticate the transport's
    actual origin/identity/current inventory under the project's verifier. There
    is no default signer and no caller positive boolean grants provenance.
    Generic GitHub check-run/status IDs are native record identities; workflow
    attempt numbers and per-test denominators remain unavailable.
    """
    def __init__(self, name, repository_id, github_id, checks, transport, *, attest=None,
                 clock=None, per_page=100, maximum_pages=4):
        require(type(name) is str and NAME.fullmatch(name), "Invalid selected GitHub repository")
        string(repository_id)
        string(github_id)
        require(type(per_page) is int and 1 <= per_page <= 100
                and type(maximum_pages) is int and 1 <= maximum_pages <= 20, "Invalid GET inventory budget")
        self.name, self.repository_id, self.github_id = name, repository_id, github_id
        self.checks, self.transport, self.attest = checks, transport, attest
        self.clock = clock or (lambda: int(time.time()))
        self.per_page, self.maximum_pages = per_page, maximum_pages

    def _get(self, path):
        require(ROUTE.fullmatch(path), "Unsafe evidence route")
        left = self._deadline - time.monotonic()
        require(left > 0, "Observation request budget exhausted")
        response = self.transport.get(path, seconds=min(30, left))
        require(type(response) is Response and type(response.status) is int, "Invalid GET response")
        headers = {k.lower(): v for k, v in response.headers}
        if response.status != 200:
            self._coverage = "RATE_LIMITED" if response.status == 429 or response.status == 403 and (
                headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers) else "FORBIDDEN" if response.status in (401, 403) else "UNKNOWN"
            raise ADPError("Project evidence endpoint unavailable")
        encode({"body": response.body}, 1048590)
        if headers.get("x-ratelimit-remaining") == "0":
            self._coverage = "RATE_LIMITED"
            raise ADPError("Project evidence rate budget exhausted")
        return response

    def _pages(self, path, field=None, query=""):
        items, seen, total = [], set(), None
        for page in range(1, self.maximum_pages + 1):
            route = f"{path}?{query + '&' if query else ''}per_page={self.per_page}&page={page}"
            response = self._get(route)
            if field is None:
                batch = response.body
            else:
                require(type(response.body) is dict, "Invalid check inventory")
                batch = response.body.get(field)
                count = response.body.get("total_count")
                integer(count)
                require(total is None or total == count, "Inventory size changed across pages")
                total = count
                require(total <= 256, "Inventory exceeds supported complete observation bound")
            require(type(batch) is list and len(batch) <= self.per_page, "Malformed/oversized evidence page")
            for row in batch:
                require(type(row) is dict and type(row.get("id")) is int and row["id"] > 0,
                        "Missing native result identity")
                require(row["id"] not in seen, "Duplicate/overlapping inventory page")
                seen.add(row["id"])
            items.extend(batch)
            require(len(items) <= 256, "Inventory exceeds supported bound")
            next_page = False
            link = dict((k.lower(), v) for k, v in response.headers).get("link", "")
            if link:
                for entry in link.split(","):
                    match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="([a-z]+)"\s*', entry)
                    require(match is not None, "Malformed pagination metadata")
                    if match[2] == "next":
                        parsed = urlsplit(match[1])
                        expected = parse_qs(route.split("?", 1)[1])
                        expected["page"] = [str(page + 1)]
                        require(parsed.scheme == "https" and parsed.netloc == "api.github.com"
                                and parsed.path == path and not parsed.fragment and parse_qs(parsed.query) == expected,
                                "Unsafe/nonsequential pagination")
                        next_page = True
            if not next_page and len(batch) < self.per_page:
                require(total is None or len(items) == total, "Incomplete check inventory")
                return items
        self._coverage = "PARTIAL"
        raise ADPError("Project evidence pagination budget exhausted")

    def _context(self, request):
        require(request.repository_id == self.repository_id, "Project repository binding differs")
        prefix = "/repos/" + self.name
        metadata = self._get(prefix).body
        require(type(metadata) is dict and str(metadata.get("id")) == self.github_id
                and type(metadata.get("full_name")) is str and metadata["full_name"].lower() == self.name.lower(),
                "GitHub repository identity changed")
        ref(request.source_ref)
        require(request.source_ref.startswith("refs/heads/"), "Only explicit source branches are supported")
        branch = self._get(prefix + "/git/ref/heads/" + quote(request.source_ref[11:], safe="")).body
        require(type(branch) is dict and branch.get("ref") == request.source_ref
                and branch.get("object", {}).get("sha") == request.revision, "Current source branch differs")
        pull = None
        if request.pull is not None:
            pull = self._get(prefix + "/pulls/" + str(request.pull.number)).body
            require(type(pull) is dict and str(pull.get("node_id", pull.get("id"))) == request.pull.id
                    and pull.get("number") == request.pull.number and pull.get("state") == "open"
                    and str(pull.get("base", {}).get("repo", {}).get("id")) == self.github_id
                    and str(pull.get("head", {}).get("repo", {}).get("id")) == self.github_id
                    and pull.get("head", {}).get("sha") == request.revision
                    and "refs/heads/" + pull.get("head", {}).get("ref", "") == request.source_ref,
                    "PR repository or exact current HEAD differs")
        return digest({"repository": {k: metadata[k] for k in ("id", "full_name")},
                       "ref": branch, "pull": pull})

    def observe(self, query):
        # Parallel lanes can share a configured read-only source without sharing
        # mutable request deadlines/coverage. The transport remains trusted.
        return copy(self)._observe(query)

    def _observe(self, query):
        request = query.request
        self._deadline = time.monotonic() + query.budget_ms / 1000
        self._coverage = "UNKNOWN"
        now = self.clock()
        integer(now)
        results = []
        try:
            context = self._context(request)
            kinds = {c.provider for c in self.checks if c.phase == request.phase}
            prefix = "/repos/" + self.name + "/commits/" + request.revision
            inventories = []
            if "github-status" in kinds:
                statuses = self._pages(prefix + "/statuses")
                inventories.append(("/statuses", None, "", digest({"items": statuses})))
                current_names = set()
                for row in statuses:  # GitHub documents reverse chronological order.
                    name, state = row["context"], row["state"]
                    current = name not in current_names
                    current_names.add(name)
                    require(row.get("url") == API + "/repos/" + self.name + "/statuses/" + str(row["id"]),
                            "Foreign native status record")
                    results.append(ProjectResult(name, "github-status", "github-user:" + str(row["creator"]["id"]),
                        self.repository_id, request.revision, str(row["id"]), None,
                        {"success": ResultStatus.PASS, "failure": ResultStatus.FAIL, "error": ResultStatus.ERROR,
                         "pending": ResultStatus.PENDING}.get(state, ResultStatus.UNKNOWN),
                        _time(row["updated_at"]), current=current, provider_status=state))
            if "github-check" in kinds:
                # The reference endpoint truncates at 1000 suites. A bounded full
                # suite inventory first refuses that unsupported envelope.
                suites = self._pages(prefix + "/check-suites", "check_suites")
                inventories.append(("/check-suites", "check_suites", "", digest({"items": suites})))
                runs = self._pages(prefix + "/check-runs", "check_runs", "filter=all")
                inventories.append(("/check-runs", "check_runs", "filter=all", digest({"items": runs})))
                identities = Counter((r.get("name"), r.get("app", {}).get("id")) for r in runs)
                for row in runs:
                    require(row.get("head_sha") == request.revision
                            and row.get("url") == API + "/repos/" + self.name + "/check-runs/" + str(row["id"]),
                            "Foreign check-run source")
                    state, conclusion = row["status"], row.get("conclusion")
                    status = ResultStatus.PENDING if state in ("queued", "in_progress", "waiting", "requested", "pending") else {
                        "success": ResultStatus.PASS, "failure": ResultStatus.FAIL, "timed_out": ResultStatus.TIMEOUT,
                        "cancelled": ResultStatus.CANCELLED, "skipped": ResultStatus.SKIP,
                        "neutral": ResultStatus.SKIP, "action_required": ResultStatus.ERROR,
                        "stale": ResultStatus.UNKNOWN}.get(conclusion, ResultStatus.UNKNOWN) if state == "completed" else ResultStatus.UNKNOWN
                    # No undocumented ordering/Actions attempt inference. Multiple
                    # same-name/app runs remain ambiguous; a project-specific
                    # adapter may authenticate authoritative supersession instead.
                    unique = identities[(row["name"], row["app"]["id"])] == 1
                    reported = row.get("completed_at") or row.get("started_at")
                    results.append(ProjectResult(row["name"], "github-check", "github-app:" + str(row["app"]["id"]),
                        self.repository_id, request.revision, str(row["id"]), None, status,
                        _time(reported) if reported is not None else now, complete=unique,
                        provider_status=state + ":" + (conclusion or "unavailable")))
            for suffix, field, query_string, previous in inventories:
                if digest({"items": self._pages(prefix + suffix, field, query_string)}) != previous:
                    self._coverage = "CHANGED"
                    raise ADPError("Project CI inventory changed during observation")
            require(self._context(request) == context, "Repository/PR/ref changed during observation")
            observed = ProjectObservation(digest(query), now, True, tuple(results))
        except (ADPError, OSError, KeyError, TypeError, ValueError, AttributeError):
            observed = ProjectObservation(digest(query), now, False, tuple(results), self._coverage)
        if self.attest is not None:
            observed = replace(observed, evidence=self.attest(query, observed))
        return observed
