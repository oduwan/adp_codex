"""Translate positively observed native constraints; unknown is never absence."""
from __future__ import annotations

import re
from urllib.parse import quote

from .discovery_schema import digest
from .schema import integer, require, string


def product_text(title, body):
    string(title, 256)
    require(type(body) is str and 0 < len(body) <= 4096 and all(ord(c) >= 32 and ord(c) != 127 or c == "\n" for c in body), "Invalid bounded PR body")
    require("adp-product:" not in title + body and not closing_directive(title + "\n" + body),
            "PR text cannot grant undelegated issue closure or forge markers")
    return title, body


def closing_directive(text):
    return re.search(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+(?:#[1-9][0-9]*|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*|https://github\.com/[^\s]+/issues/[1-9][0-9]*)", text, re.I) is not None


def constraints(branch, rules, legacy=None):
    """Supported subset, no bypass: unknown fields with acceptance effects refuse."""
    require(type(branch) is dict and type(branch.get("protected")) is bool
            and type(rules) is list and len(rules) <= 100, "Current branch/rule knowledge required")
    checks, origins, reviews, linear = set(), {}, 0, False

    def statuses(entries, key):
        require(type(entries) is list and len(entries) <= 32, "Required check inventory is incomplete")
        for row in entries:
            require(type(row) is dict, "Malformed required check")
            name = row.get("context"); string(name, 128)
            provider = row.get(key)
            require(provider is None or type(provider) is int and provider >= -1, "Unknown check origin")
            checks.add(name)
            if provider not in (None, -1):
                require(name not in origins or origins[name] == provider, "Conflicting required check origins")
                origins[name] = provider

    def pull(parameters, *, classic=False):
        require(type(parameters) is dict, "Incomplete native PR requirements")
        nonlocal reviews
        count = parameters.get("required_approving_review_count")
        integer(count)
        require(count <= 16, "Native review requirement exceeds bounds")
        reviews = max(reviews, count)
        booleans = (("dismiss_stale_reviews", "require_code_owner_reviews", "require_last_push_approval") if classic else
            ("dismiss_stale_reviews_on_push", "require_code_owner_review", "require_last_push_approval", "required_review_thread_resolution"))
        require(all(type(parameters.get(name)) is bool for name in booleans), "Unknown mandatory native review field")
        for name in booleans:
            if name not in ("dismiss_stale_reviews", "dismiss_stale_reviews_on_push"):
                require(parameters[name] is False, "Unsupported native review obligation: " + name)
        allowed = ({"url", "dismissal_restrictions", "bypass_pull_request_allowances", "dismiss_stale_reviews", "require_code_owner_reviews", "require_last_push_approval", "required_approving_review_count"}
            if classic else {"dismiss_stale_reviews_on_push", "require_code_owner_review", "require_last_push_approval", "required_approving_review_count", "required_review_thread_resolution", "allowed_merge_methods"})
        require(set(parameters) <= allowed, "Unsupported native review parameter")
        if classic:
            require(all(parameters.get(k) in (None, {}) for k in ("dismissal_restrictions", "bypass_pull_request_allowances")), "Unsupported review actor exceptions")

    for row in rules:
        require(type(row) is dict and type(row.get("type")) is str, "Malformed native rule")
        kind, p = row["type"], row.get("parameters")
        if kind == "required_status_checks":
            require(type(p) is dict, "Incomplete native status rule")
            statuses(p.get("required_status_checks"), "integration_id")
            require(type(p.get("strict_required_status_checks_policy")) is bool,
                    "Unknown required status branch policy")
        elif kind == "pull_request":
            pull(p)
            if "allowed_merge_methods" in p:
                require(type(p["allowed_merge_methods"]) is list and p["allowed_merge_methods"], "Unknown merge methods")
        elif kind == "required_linear_history":
            linear = True
        else:
            require(kind in ("deletion", "non_fast_forward"), "Unsupported active native rule: " + kind)
    if branch["protected"]:
        require(type(legacy) is dict, "UNKNOWN: protected branch metadata unavailable")
        # Rulesets may coexist with classic protection; a 404 is not absence.
        status = legacy.get("required_status_checks")
        require(status is None or type(status) is dict, "Malformed classic checks")
        if status is not None:
            require(type(status.get("strict")) is bool, "Unknown classic check policy")
            entries = status.get("checks")
            if entries is None:
                entries = [{"context": name} for name in status.get("contexts", [])]
            statuses(entries, "app_id")
            require(set(status.get("contexts", [])) <= checks, "Inconsistent native check inventory")
        pr = legacy.get("required_pull_request_reviews")
        if pr is not None:
            pull(pr, classic=True)
        for name in ("required_signatures", "required_conversation_resolution", "lock_branch"):
            value = legacy.get(name)
            require(value is None or type(value) is dict and value.get("enabled") is False,
                    "Unsupported enabled native protection: " + name)
        require(legacy.get("restrictions") is None, "Restricted actor policy requires human verification")
        value = legacy.get("required_linear_history")
        require(value is None or type(value) is dict and type(value.get("enabled")) is bool,
                "Unknown native linear-history policy")
        linear |= value is not None and value["enabled"]
        allowed = {"url", "required_status_checks", "required_pull_request_reviews", "restrictions", "enforce_admins",
                   "required_linear_history", "allow_force_pushes", "allow_deletions", "block_creations", "required_signatures",
                   "required_conversation_resolution", "lock_branch", "allow_fork_syncing"}
        require(set(legacy) <= allowed, "Unknown classic protection constraint")
    require(len(checks) <= 32, "Required checks exceed accepted capacity")
    methods = {"squash"} if linear else {"merge", "squash"}
    for row in rules:
        if row["type"] == "pull_request" and "allowed_merge_methods" in row["parameters"]:
            methods &= set(row["parameters"]["allowed_merge_methods"])
    return {"checks": sorted(checks), "origins": origins, "native_reviews": reviews, "methods": sorted(methods)}


def observe_policy(read, target, base_ref):
    """Bounded complete native pages through the accepted authenticated read port."""
    branch = base_ref.removeprefix("refs/heads/")
    prefix = target.api
    current = read.get(prefix + "/branches/" + quote(branch, safe=""))
    require(current.status == 200 and type(current.body) is dict and current.body.get("name") == branch,
            "UNKNOWN: current base branch is unavailable")
    rules, ids = [], set()
    for page in range(1, 21):
        result = read.get(prefix + "/rules/branches/" + quote(branch, safe="") + f"?per_page=100&page={page}")
        require(result.status == 200 and type(result.body) is list and len(result.body) <= 100,
                "UNKNOWN: current native rules are unavailable")
        for row in result.body:
            identity = digest(row)
            require(identity not in ids, "Duplicate native rule observation")
            ids.add(identity); rules.append(row)
        require(len(rules) <= 100, "Native policy exceeds supported bound")
        if len(result.body) < 100:
            require(not any(k.lower() == "link" for k, _ in result.headers), "Ambiguous rule pagination")
            break
    else:
        raise ValueError("Incomplete native rules")
    legacy = None
    if current.body.get("protected") is True:
        observed = read.get(prefix + "/branches/" + quote(branch, safe="") + "/protection")
        require(observed.status == 200, "UNKNOWN: required classic protection access unavailable")
        legacy = observed.body
    value = constraints(current.body, rules, legacy)
    return {**value, "digest": digest({"branch": current.body, "rules": rules, "legacy": legacy})}
