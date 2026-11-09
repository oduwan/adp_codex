"""Synthetic API data only; no real GitHub requests or write operations."""
from __future__ import annotations

from dataclasses import replace

from adp.discovery import review_subject
from adp.discovery_github import API, FixtureTransport, GitHubDiscoveryAdapter, Response
from adp.discovery_types import ReadinessReview
from adp.guard_types import Attestation


def issue(number=1, *, name="alpha/product", iid=None, body="Observable change with bounded acceptance.", state="open"):
    return {"id": number + 1000, "node_id": iid or "I-opaque-" + str(number), "number": number,
        "url": f"{API}/repos/{name}/issues/{number}", "title": "Task " + str(number), "body": body,
        "state": state, "state_reason": "completed" if state == "closed" else None,
        "updated_at": "2026-11-09T08:00:00Z", "labels": [], "assignees": [],
        "user": {"id": 71, "node_id": "U-author"}}


def pull(number=10, *, name="alpha/product", rid="repo-opaque-A", sha="a" * 40, state="open"):
    return {"id": number + 2000, "node_id": "PR-opaque-" + str(number), "number": number,
        "url": f"{API}/repos/{name}/pulls/{number}", "state": state, "updated_at": "2026-11-09T08:00:00Z",
        "head": {"sha": sha, "ref": "work/task", "repo": {"id": "fork-opaque"}},
        "base": {"sha": "b" * 40, "ref": "trunk", "repo": {"id": rid}}, "merged": False, "draft": True}


def responses(rows=None, prs=None, *, name="alpha/product", rid="repo-opaque-A", per_page=100):
    rows, prs = rows if rows is not None else [issue(name=name)], prs or []
    prefix = "/repos/" + name
    result = {prefix: Response(200, {"id": rid, "node_id": "R-opaque", "full_name": name})}
    for resource, values in (("issues", rows), ("pulls", prs)):
        page = 1
        offset = 0
        while True:
            batch = values[offset:offset + per_page]
            result[f"{prefix}/{resource}?state=all&sort=created&direction=asc&per_page={per_page}&page={page}"] = Response(200, batch)
            if len(batch) < per_page:
                break
            offset += per_page
            page += 1
    for row in rows:
        if "pull_request" in row:
            continue
        route = prefix + "/issues/" + str(row["number"])
        result[route] = Response(200, row)
        for endpoint in ("comments", "timeline", "dependencies/blocked_by", "sub_issues"):
            result[f"{route}/{endpoint}?per_page={per_page}&page=1"] = Response(200, [])
    for pr in prs:
        result[prefix + "/pulls/" + str(pr["number"])] = Response(200, pr)
    return result


def discover(rows=None, prs=None, *, name="alpha/product", rid="repo-opaque-A", changed=None, **kwargs):
    entries = responses(rows, prs, name=name, rid=rid, per_page=kwargs.get("per_page", 100))
    entries.update(changed or {})
    transport = FixtureTransport(entries)
    adapter = GitHubDiscoveryAdapter(name, transport, expected_id=rid, clock=lambda: 100, **kwargs)
    return adapter.discover(), transport


class Authority:
    def __init__(self):
        self.receipts = set()

    def sign(self, snapshots, review, reviewer="independent-reviewer"):
        evidence = Attestation(reviewer, "fixture:scope-contract-and-policy", review_subject(snapshots, review))
        self.receipts.add((evidence, "discovery/readiness"))
        return replace(review, evidence=evidence)

    def verify(self, evidence, *, purpose, subject):
        return evidence.subject == subject and (evidence, purpose) in self.receipts


def assessed(snapshot, authority, *, snapshots=None, **changes):
    context = snapshots or (snapshot,)
    return tuple(authority.sign(context, replace(ReadinessReview(i.identity, "Bounded external scope", ("Observable acceptance",),
        ("project:verified-policy",), specification="KNOWN", policy="KNOWN", observed_at=90, expires_at=200), **changes))
        for i in snapshot.issues)
