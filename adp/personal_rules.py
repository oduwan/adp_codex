"""Personal-only, freshly observed Free-private capability fallback.

No 403 is absence, no cached entitlement or synthetic signed-provider proof.
The shared M7 service still owns supervision, budgets, uploads and exact CAS.
"""
from __future__ import annotations

from urllib.parse import quote
from types import SimpleNamespace

from .discovery_schema import digest
from .github_rules import checked, plan_error
from .network_git import REF_QUERY
from .network_objects import oid
from .personal_github import owned_repository
from .schema import require
from .errors import ADPError

# Independent identity/ref/permission observation without inaccessible classic
# fields. All GraphQL errors still refuse. Signed mode keeps its original query.
PERSONAL_REF_QUERY = REF_QUERY.replace(" branchProtectionRule { id }", "").replace(
    "    branchProtectionRules(first: 1) { totalCount nodes { id } pageInfo { hasNextPage } }\n", "").replace(
    "viewerPermission\n", "viewerPermission\n    defaultBranchRef { name prefix target { oid __typename } }\n")


def private_repository(read, repository: dict, expected_owner: dict) -> dict:
    name = repository["name"]
    owner = owned_repository(read, name, repository["repository_id"])
    response = checked(read, name, "/repos/" + name)
    repo = response.body
    require(response.status == 200 and type(repo) is dict and owner == expected_owner
            and all(owner.get(k) is True for k in ("read_access", "push_access", "admin_access"))
            and type(repo.get("id")) is int and repo["id"] == repository["database_id"]
            and repo.get("node_id") == repository["node_id"] and repo.get("full_name") == name
            and repo.get("private") is True and repo.get("default_branch") == repository["default_branch"]
            and type(repo.get("owner")) is dict and repo["owner"].get("type") == "User"
            and type(repo["owner"].get("id")) is int and repo["owner"]["id"] == owner["account_id"]
            and type(repo.get("permissions")) is dict
            and all(repo["permissions"].get(k) is True for k in ("pull", "push", "admin")),
            "PLAN_UNAVAILABLE: fresh private personal owner/admin identity required")
    return {"repository": repository, "owner": owner, "private": True}


def supported_branch(response, branch: str, expected=None):
    row = response.body
    require(response.status == 200 and type(row) is dict and row.get("name") == branch
            and row.get("protected") is False and type(row.get("commit")) is dict,
            "PLAN_UNAVAILABLE: fresh unprotected supported branch evidence required")
    revision = oid(row["commit"].get("sha"))
    require(expected is None or revision == expected, "Current branch and exact ref disagree")
    return revision


def enrollment_rules(read, repository: dict, owner: dict, branch: str) -> dict:
    from .enrollment import branch_rules
    name = repository["name"]
    # Keep ordinary/signed enrollment byte-compatible; opt in here only.
    observations = {}
    def get(path):
        response = checked(read, name, path)
        observations[path] = response
        return response
    bounded = SimpleNamespace(get=get)
    value = branch_rules(bounded, name, branch)
    path = "/repos/" + name + "/rules/branches/" + quote(branch, safe="")
    result = observations[path]
    unavailable = plan_error(result, path)
    if unavailable is not None:
        try:
            identity = private_repository(read, repository, owner)
            supported_branch(observations["/repos/" + name + "/branches/" + quote(branch, safe="")], branch)
        except (ADPError, OSError, ValueError, TypeError):
            value["rules_action"] = "Exact plan error observed, but fresh private owner/admin and supported unprotected branch evidence are still required. No write is authorized."
            return value
        value.update(rules="PLAN_UNAVAILABLE", rules_digest=digest({"availability": unavailable, "identity": identity}),
            rules_action="Review project governance and checks; separately accept the exact plan-disabled operation before any GitHub write.")
    elif result.status == 200 and type(result.body) is list and (len(result.body) >= 100 or any(k == "link" for k, _ in result.headers)):
        value.update(rules="UNKNOWN", required_check_contexts=[], rules_digest=None)
    if value["rules"] == "UNKNOWN":
        value["rules_action"] = "Verify complete current rules and protection access; an arbitrary denial or incomplete response is not absent policy."
    return value


def inspect_ref(service, *, writable: bool):
    if not writable:
        repo = service._repository(PERSONAL_REF_QUERY, {"ref": service.target.ref})
        return ref_value(repo, service.target.branch)
    from .personal_network import PersonalDiscoveryRead
    read, target = PersonalDiscoveryRead(service), service.target
    name = target.owner + "/" + target.name
    result = checked(read, name, target.api + "/rules/branches/" + quote(target.branch, safe=""))
    unavailable = plan_error(result, target.api + "/rules/branches/" + quote(target.branch, safe=""))
    policy = None
    if unavailable is None:
        require(result.status == 200 and result.body == [] and type(result.body) is list
                and not any(k == "link" for k, _ in result.headers), "UNKNOWN: feature rules unavailable or constrained")
        current = service._inspect_ref(writable=True)
    else:
        binding = service.personal_context
        require(binding is not None, "PLAN_UNAVAILABLE: exact personal repository context required")
        repository, owner = binding
        require(repository["node_id"] == target.node_id and repository["database_id"] == target.database_id
                and repository["repository_id"] == target.memory_id and repository["name"] == name,
                "Personal capability context targets another immutable repository")
        identity = private_repository(read, repository, owner)
        repo = service._repository(PERSONAL_REF_QUERY, {"ref": target.ref})
        require(repo.get("viewerPermission") == "ADMIN", "UNKNOWN: independent owner permission unavailable")
        current = ref_value(repo, target.branch)
        default = repository["default_branch"]
        default_sha = ref_value({"ref": repo.get("defaultBranchRef")}, default)
        require(default_sha is not None, "UNKNOWN: current default ref unavailable")
        supported_branch(checked(read, name, target.api + "/branches/" + quote(default, safe="")), default, default_sha)
        if current is not None:
            supported_branch(checked(read, name, target.api + "/branches/" + quote(target.branch, safe="")), target.branch, current)
        # For a positively absent feature, the existing default witnesses the
        # repository-level classic capability. A feature 404 proves no policy.
        classic_branch = target.branch if current is not None else default
        classic_path = target.api + "/branches/" + quote(classic_branch, safe="") + "/protection"
        classic = plan_error(checked(read, name, classic_path), classic_path)
        require(classic is not None, "UNKNOWN: classic protection is not verified plan-disabled")
        policy = {"availability": "PLAN_UNAVAILABLE", "identity": identity, "ref": target.ref,
            "rules": unavailable, "classic": classic, "classic_scope": "REPOSITORY_PRIVATE_PLAN",
            "protection_absence": "NOT_INDEPENDENTLY_OBSERVED"}
    require(service.personal_policy_binding is None or service.personal_policy_binding == (policy,),
            "Current feature policy/entitlement differs from exact approval")
    service.personal_policy = policy
    return current


def ref_value(repo: dict, branch: str):
    require("ref" in repo, "UNKNOWN: missing exact ref metadata")
    row = repo["ref"]
    if row is None:
        return None
    require(type(row) is dict and row.get("prefix") == "refs/heads/" and row.get("name") == branch
            and type(row.get("target")) is dict and row["target"].get("__typename") == "Commit", "UNKNOWN: malformed exact branch")
    return oid(row["target"].get("oid"))


def product_refs(service, base_ref):
    """Current exact feature/default pair; no claim of a complete ref inventory."""
    repo = service._repository(PERSONAL_REF_QUERY, {"ref": service.target.ref})
    require(repo.get("viewerPermission") in ("WRITE", "MAINTAIN", "ADMIN")
            and base_ref.startswith("refs/heads/"), "UNKNOWN: current product ref permission unavailable")
    source = ref_value(repo, service.target.branch)
    base = ref_value({"ref": repo.get("defaultBranchRef")}, base_ref.removeprefix("refs/heads/"))
    require(source is not None and base is not None, "UNKNOWN: exact product refs unavailable")
    return {service.target.ref: source, base_ref: base}
