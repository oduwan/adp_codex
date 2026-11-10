"""Journal-backed GitHub product effects; never a source of project authority."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .config import load_json, safe_path
from .discovery_github import Response
from .discovery_schema import digest, typed
from .errors import ADPError
from .execution_github import GitHubForgeBackend
from .execution_memory import ExecutionJournal
from .execution_privacy import credential_shaped
from .execution_types import ExternalObservation
from .forge_http_child import validate_request
from .guard_types import Attestation, data
from .network_git import GitHubCAS
from .network_http import GitHubHTTPTransport
from .policy_schema import fingerprint, fresh, ref, sha
from .policy_types import Operation
from .schema import encode, integer, require, string
from .storage import sync_directory


class GitHubForgeHTTPTransport(GitHubHTTPTransport):
    permissions = (("contents", "write"), ("issues", "write"), ("metadata", "read"), ("pull_requests", "write"))
    validator = staticmethod(validate_request)
    child = "forge_http_child.py"


@dataclass(frozen=True)
class DelegationProfile:
    repository_id: str
    issue_id: str
    task_id: str
    iteration: int
    source_ref: str
    base_ref: str
    revision: str
    policy_digest: str
    scope_digest: str
    operations: tuple[str, ...]
    merge_mode: str
    methods: tuple[str, ...]
    merge_envelope: str
    observed_at: int
    expires_at: int
    evidence: Attestation | None = None


def delegation_subject(profile):
    require(type(profile) is DelegationProfile, "Explicit project delegation required")
    for item in (profile.repository_id, profile.issue_id, profile.task_id):
        string(item)
    integer(profile.iteration, 1)
    ref(profile.source_ref); ref(profile.base_ref); sha(profile.revision)
    fingerprint(profile.policy_digest); fingerprint(profile.scope_digest)
    require(type(profile.operations) is tuple and len(set(profile.operations)) == len(profile.operations)
            and set(profile.operations) <= {Operation.PR, Operation.MERGE, Operation.REPORT}, "Unsupported project delegation")
    require(profile.merge_mode in ("MANUAL", "DELEGATED") and type(profile.methods) is tuple
            and set(profile.methods) <= {"merge", "squash", "ff_only"}, "Unsupported merge delegation")
    require(profile.merge_envelope in ("HEAD_ATOMIC_BASE_OBSERVED", "ATOMIC_BASE", "UNKNOWN"), "Unknown merge envelope")
    integer(profile.observed_at); integer(profile.expires_at)
    payload = data(profile); payload.pop("evidence")
    return digest({"domain": "github-product/delegation", "profile": payload})


class _Responses:
    def __init__(self, service):
        self.service = service

    def request(self, method, path, payload=None):
        try:
            return Response(200, self.service.request(method, path, payload))
        except (ADPError, OSError):
            return Response(0, None)


class GitHubProductForge(GitHubForgeBackend):
    """One-use M5 intents, #14 transport fencing, exact native merge HEAD.

    The native merge API has no atomic base precondition. Only independently
    authenticated HEAD_ATOMIC_BASE_OBSERVED project assent qualifies it.
    """
    def __init__(self, service, journal, authority):
        require(type(service) is GitHubCAS and type(journal) is ExecutionJournal,
                "Actual pinned service and execution journal required")
        target = service.target
        require(journal.memory.config.identity == target.memory_id, "Forge/memory repository differs")
        service.bind_control(journal.memory.control)
        super().__init__(target.owner + "/" + target.name, str(target.database_id), _Responses(service), authority)
        self.service, self.journal = service, journal
        self._dispatches = {}

    def unconfirmed_contexts(self):
        return self.service.unconfirmed_contexts()

    def _canonical(self, key, operation, payload):
        observed = self.journal.inspect()
        row = observed["state"]["execution"]["actions"].get(key)
        require(row is not None and row["operation"] == operation and row["payload"] == payload,
                "Exact canonical forge intent required")
        return observed, row

    def _claim_path(self, key):
        return safe_path(self.journal.memory.control / ("forge-intent-" + key + ".json"))

    def prepare_dispatch(self, key, action):
        self.service._check_stop()
        observed, row = self._canonical(key, action["operation"], action["payload"])
        require(observed["local_owner"] and row["status"] == "PREPARED"
                and row["generation"] == observed["state"]["generation"], "Fresh owning PREPARED forge intent required")
        claim = {"intent": key, "generation": row["generation"], "payload": digest(row["payload"]),
                 "operation": row["operation"], "repository": self.repository_id}
        try:
            descriptor = os.open(self._claim_path(key), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError:
            raise ADPError("UNKNOWN: forge intent already consumed or unsafe; no retry") from None
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encode(claim)); stream.flush(); os.fsync(stream.fileno())
        sync_directory(self.journal.memory.control)
        ticket = object()
        self._dispatches[ticket] = (key, claim)
        return ticket

    def pull(self, identity, *, revision, source_ref, base_ref, expected_base=None):
        """Fresh current PR observation, distinct from historical create intent."""
        require(type(identity) is dict, "Exact PR identity required")
        integer(identity["number"], 1)
        if not self._identity():
            return None
        response = self.transport.request("GET", f"/repos/{self.repository}/pulls/{identity['number']}")
        item = response.body
        if response.status != 200 or type(item) is not dict:
            return None
        head, base = item.get("head"), item.get("base")
        if (type(head) is not dict or type(base) is not dict or str(item.get("id")) != identity["id"]
                or identity["repository_id"] != self.service.target.memory_id or item.get("number") != identity["number"]
                or head.get("sha") != revision or head.get("ref") != source_ref.removeprefix("refs/heads/")
                or base.get("ref") != base_ref.removeprefix("refs/heads/")
                or expected_base is not None and base.get("sha") != expected_base
                or any(type(p.get("repo")) is not dict or str(p["repo"].get("id")) != self.repository_id
                    or p["repo"].get("node_id") != self.service.target.node_id
                    or p["repo"].get("full_name", "").lower() != self.repository.lower() for p in (head, base))
                or item.get("html_url") != identity["url"] or type(item.get("draft")) is not bool
                or item.get("state") not in ("open", "closed") or type(item.get("merged")) is not bool):
            return None
        return item

    def reviews(self, identity, revision):
        """Complete review inventory, authenticated by the installed authority.

        Latest non-comment verdict per canonical provider user is authoritative.
        Authorship and externally configured obligations are verified separately.
        """
        rows, seen = {}, set()
        for page in range(1, 21):
            reply = self.transport.request("GET", f"/repos/{self.repository}/pulls/{identity['number']}/reviews?per_page=100&page={page}")
            if reply.status != 200 or type(reply.body) is not list or len(seen) + len(reply.body) > 256:
                return None
            for item in reply.body:
                if (type(item) is not dict or type(item.get("id")) is not int or item["id"] in seen
                        or type(item.get("user")) is not dict or type(item["user"].get("id")) is not int
                        or item.get("state") not in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING")):
                    return None
                seen.add(item["id"])
                if item["state"] != "COMMENTED":
                    actor = str(item["user"]["id"])
                    if actor not in rows or rows[actor]["id"] < item["id"]:
                        rows[actor] = item
            if len(reply.body) < 100:
                return tuple(rows[k] for k in sorted(rows))
        return None

    def observe(self, key, operation, payload, *, attempted=False):
        self.service._check_stop()
        if operation != Operation.MERGE:
            # A recovered PREPARED intent with a private claim is uncertain too.
            attempted = attempted or self._claim_path(key).exists()
            return super().observe(key, operation, payload, attempted=attempted)
        item = self.pull(payload["pull"], revision=payload["revision"], source_ref=payload["head_ref"], base_ref=payload["base_ref"])
        if item is None:
            return ExternalObservation("UNKNOWN")
        if not item["merged"]:
            return ExternalObservation("UNKNOWN" if attempted or self._claim_path(key).exists() else "ABSENT")
        result = item.get("merge_commit_sha")
        try:
            sha(result)
            commit = self.service.request("GET", f"/repos/{self.repository}/git/commits/{result}")
            parents = [p["sha"] for p in commit["parents"]]
            require(commit["sha"] == result and commit["tree"]["sha"] == payload["source_tree"], "Merged source differs")
            expected = [payload["expected_base"], payload["revision"]] if payload["method"] == "merge" else [payload["expected_base"]]
            require(parents == expected, "Merged ancestry differs from observed base and reviewed source")
            return ExternalObservation("PRESENT", payload["pull"]["url"], result)
        except (ADPError, OSError, KeyError, TypeError):
            return ExternalObservation("UNKNOWN")

    def submit(self, key, operation, payload, *, authorization=None, plan_digest=None, dispatch=None, validate=None):
        require(callable(validate), "Fresh final M1/M2/M3 validation callback required")
        require(dispatch in self._dispatches, "Fresh one-use forge dispatch required")
        canonical_key, claim = self._dispatches.pop(dispatch)
        observed, row = self._canonical(key, operation, payload)
        require(canonical_key == key and load_json(self._claim_path(key)) == claim
                and observed["local_owner"] and row["status"] == "SUBMITTED"
                and row["generation"] == observed["state"]["generation"], "Forge owner/claim changed")
        subject = digest({"id": key, "plan": plan_digest, "payload": payload})
        require(type(authorization) is Attestation and self.authority.verify(authorization,
            purpose="execution/effect", subject=subject) is True, "Explicit exact-effect authority required")
        require(not credential_shaped(payload), "Sensitive forge payload refused")
        with self.service.bounded():
            if operation != Operation.MERGE:
                return super().submit(key, operation, payload, authorization=authorization, plan_digest=plan_digest,
                    before_mutation=validate)
            require(payload["method"] in ("merge", "squash") and payload["envelope"] == "HEAD_ATOMIC_BASE_OBSERVED",
                    "UNSUPPORTED: provider merge method/base envelope")
            item = self.pull(payload["pull"], revision=payload["revision"], source_ref=payload["head_ref"],
                base_ref=payload["base_ref"], expected_base=payload["expected_base"])
            require(item is not None and item["draft"] is False and item["state"] == "open" and not item["merged"],
                    "Fresh exact ready PR/head/base required")
            validate()  # after all provider reads, immediately before PUT
            # Native API atomically tests HEAD only. This is deliberately not #14 CAS.
            try:
                self.service.request("PUT", f"/repos/{self.repository}/pulls/{payload['pull']['number']}/merge",
                    {"sha": payload["revision"], "merge_method": payload["method"]})
            except (ADPError, OSError):
                pass
            return self.observe(key, operation, payload, attempted=True)
