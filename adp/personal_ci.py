"""Read-only native check identity discovery for personal plans.

An observed check is not automatically prescribed. Required names come from
project rules or an explicit operator choice. No test or workflow is executed.
"""
from __future__ import annotations

import time
from urllib.parse import quote

from .discovery_schema import digest
from .project_validation_github import GitHubEvidenceSource
from .project_validation_types import EvidenceRequest, Phase, RequiredCheck
from .schema import integer, require, string


def native_inventory(name, repository_id, source_ref, revision, transport, *, seconds=5):
    """Reuse #21's fixed-origin context and complete pagination checks.

    This only identifies actual origins. #21 later reobserves and evaluates the
    exact committed SHA and every prescribed result. Partial identity discovery
    cannot create a check policy or evidence of absent checks.
    """
    require(type(seconds) is int and 1 <= seconds <= 30, "Invalid native observation budget")
    source = GitHubEvidenceSource(name, repository_id, repository_id, (), transport)
    source._deadline = time.monotonic() + seconds
    source._coverage = "UNKNOWN"
    request = EvidenceRequest(repository_id, source_ref, revision, "0" * 64,
                              Phase.BEFORE_PR, "personal-plan", 0, 0, 0)
    before = source._context(request)
    prefix = "/repos/" + name + "/commits/" + quote(revision, safe="")
    specifications = (("/statuses", None, ""), ("/check-suites", "check_suites", ""),
                      ("/check-runs", "check_runs", "filter=all"))
    inventories = [(suffix, field, query, source._pages(prefix + suffix, field, query))
                   for suffix, field, query in specifications]
    require(before == source._context(request), "Native source identity changed")
    for suffix, field, query, records in inventories:
        require(digest(source._pages(prefix + suffix, field, query)) == digest(records),
                "Native check inventory changed")
    statuses, _, runs = (records for _, _, _, records in inventories)
    result = {}
    # A repeated check/app pair is ambiguous; statuses are documented newest first.
    seen = set()
    for row in statuses:
        require(type(row) is dict, "Malformed native status")
        check_name = row.get("context")
        string(check_name, 128)
        if check_name in seen:
            continue
        seen.add(check_name)
        require(type(row.get("creator")) is dict and type(row["creator"].get("id")) is int
                and row.get("url") == "https://api.github.com/repos/" + name + "/statuses/" + str(row.get("id")),
                "Native status provenance is unavailable")
        integer(row.get("id"), 1)
        integer(row["creator"]["id"], 1)
        result.setdefault(check_name, []).append(("github-status", "github-user:" + str(row["creator"]["id"])))
    for row in runs:
        require(type(row) is dict, "Malformed native check")
        check_name = row.get("name")
        string(check_name, 128)
        require(row.get("head_sha") == revision and type(row.get("app")) is dict
                and type(row["app"].get("id")) is int
                and row.get("url") == "https://api.github.com/repos/" + name + "/check-runs/" + str(row.get("id")),
                "Native check provenance is unavailable")
        integer(row.get("id"), 1)
        integer(row["app"]["id"], 1)
        result.setdefault(check_name, []).append(("github-check", "github-app:" + str(row["app"]["id"])))
    require(len(result) <= 32, "Native check identity inventory exceeds bounds")
    return {name: origins[0] for name, origins in result.items() if len(origins) == 1}


def prescribed_checks(names, inventory, *, accept_native_job_records=False):
    require(type(names) in (tuple, list) and len(names) <= 32 and len(set(names)) == len(names),
            "Prescribed native checks must be bounded and unique")
    result = []
    for name in names:
        string(name, 128)
        require(name in inventory, "Prescribed check origin is missing or ambiguous; retain UNKNOWN")
        provider, origin = inventory[name]
        result.append(RequiredCheck(name, provider, origin, Phase.BEFORE_PR,
                                    native_record_is_attempt=accept_native_job_records))
    return tuple(result)
