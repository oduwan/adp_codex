"""Explicit GitHub Git Data transport and exact expected-old GraphQL CAS.

No installation, discovery mutation, force, staging ref, merge or retry fallback.
The accepted local bare port and canonical state schemas remain unchanged.
"""
from __future__ import annotations

import contextvars
import hashlib
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .config import Config, load_json, remote_identity, safe_path
from .discovery_schema import digest
from .errors import ADPError, GitError
from .execution_memory import ExecutionJournal
from .execution_ports import GitExecutionPort, UnconfirmedValidation
from .execution_types import ExternalObservation
from .git import value
from .guard_types import data
from .network_http import HTTPTransport, NetworkTransportError, UPDATE_REFS_MUTATION
from .network_objects import closure, oid
from .policy import PolicyProvider
from .policy_adapters import GitPolicyAdapter
from .policy_schema import branch
from .policy_types import Effect, Operation, Ref
from .schema import decode, encode, require, string

ZERO = "0" * 40
REF_QUERY = """query ADPRef($id: ID!, $ref: String!) {
  node(id: $id) { ... on Repository {
    id databaseId nameWithOwner viewerPermission
    ref(qualifiedName: $ref) { name prefix target { oid __typename } branchProtectionRule { id } }
    branchProtectionRules(first: 1) { totalCount nodes { id } pageInfo { hasNextPage } }
  } }
}"""
REFS_QUERY = """query ADPRefs($id: ID!, $prefix: String!, $after: String) {
  node(id: $id) { ... on Repository {
    id databaseId nameWithOwner viewerPermission
    refs(refPrefix: $prefix, first: 100, after: $after) {
      nodes { name prefix target { oid } } pageInfo { hasNextPage endCursor }
    }
  } }
}"""


@dataclass(frozen=True)
class GitHubTarget:
    memory_id: str
    node_id: str
    database_id: int
    owner: str
    name: str
    branch: str

    def __post_init__(self):
        string(self.memory_id)
        string(self.node_id)
        require(type(self.database_id) is int and self.database_id > 0, "Pin the canonical GitHub repository ID")
        for name in (self.owner, self.name):
            require(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", name)
                    and name not in (".", ".."), "Invalid pinned GitHub repository name")
        branch(self.branch)

    @property
    def endpoint(self):
        return f"https://github.com/{self.owner}/{self.name}"

    @property
    def fingerprint(self):
        return hashlib.sha256(self.endpoint.encode()).hexdigest()

    @property
    def ref(self):
        return "refs/heads/" + self.branch

    @property
    def api(self):
        return f"/repos/{self.owner}/{self.name}"


class NetworkUncertain(OSError):
    """No response text, URL, credential or arbitrary external exception escapes."""


@dataclass
class _Budget:
    end: float
    calls: int = 0


class GitHubCAS:
    """Authenticated observations and immutable upload; rights remain external."""
    def __init__(self, target: GitHubTarget, transport: HTTPTransport):
        require(type(target) is GitHubTarget, "Select a typed pinned GitHub target")
        require(callable(getattr(transport, "bind_repository", None)), "A repository-ID-confined authenticated transport is required")
        transport.bind_repository(target.node_id, target.database_id)
        self.target, self.transport = target, transport
        self._budget = contextvars.ContextVar("adp-network-budget", default=None)
        self.control = None
        self._live_unknown = False

    def bind_control(self, control):
        control = safe_path(control)
        require(self.control is None or self.control == control, "Network service control binding changed")
        self.control = control

    def _hazard_path(self):
        return safe_path(self.control / ("network-stop-" + self.target.fingerprint + ".json")) if self.control is not None else None

    def unconfirmed_contexts(self):
        path = self._hazard_path()
        return ("network:" + self.target.fingerprint,) if self._live_unknown or path is not None and path.exists() else ()

    def _check_stop(self):
        require(not self.unconfirmed_contexts(), "UNKNOWN: unconfirmed network transport stop requires operator reconciliation")

    def _start_request(self):
        self._live_unknown = True
        path = self._hazard_path()
        if path is not None:
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encode({"status": "IN_FLIGHT_OR_UNKNOWN", "repository": self.target.node_id}))
                    stream.flush(); os.fsync(stream.fileno())
                from .storage import sync_directory
                sync_directory(path.parent)
            except OSError:
                # No transport has launched. Do not turn failed safety persistence
                # into an ordinary reconnect/reobservation path.
                raise ADPError("UNKNOWN: cannot persist transport stop boundary; no request launched") from None

    def _confirmed_stop(self):
        path = self._hazard_path()
        try:
            if path is not None:
                path.unlink()
                from .storage import sync_directory
                sync_directory(path.parent)
        except OSError:
            raise ADPError("UNKNOWN: cannot confirm durable transport stop boundary") from None
        self._live_unknown = False

    @contextmanager
    def bounded(self):
        token = self._budget.set(_Budget(time.monotonic() + 45))
        try:
            yield
        finally:
            self._budget.reset(token)

    def request(self, method, path, payload=None, *, missing=False):
        self._check_stop()
        budget = self._budget.get() or _Budget(time.monotonic() + 20)
        budget.calls += 1
        left = budget.end - time.monotonic()
        require(budget.calls <= 128 and left > 0, "Network operation exhausted its fixed budget")
        self._start_request()
        try:
            response = self.transport.request(method, path, payload, seconds=min(5.0, left))
        except UnconfirmedValidation as exc:
            raise ADPError("UNKNOWN: unconfirmed network transport stop requires operator reconciliation") from None
        except NetworkTransportError:
            # The qualified transport raises this only after confirmed stop or
            # before launch. UnconfirmedValidation has a separate durable path.
            self._confirmed_stop()
            raise NetworkUncertain("UNKNOWN: stopped trusted transport did not confirm delivery") from None
        except Exception:
            # An arbitrary transport exception does not prove a process stopped.
            raise NetworkUncertain("UNKNOWN: trusted network transport did not confirm a response") from None
        self._confirmed_stop()
        require(type(response.status) is int and type(response.body) is bytes and len(response.body) <= 1048576,
                "UNKNOWN: malformed or oversized network response")
        if missing and response.status == 404:
            return None
        if response.status not in (200, 201):
            raise NetworkUncertain("UNKNOWN: GitHub request refused (HTTP " + str(response.status) + ")")
        try:
            wrapped = decode(b'{"value":' + response.body + b'}', 1048600)
            require(set(wrapped) == {"value"}, "Invalid response envelope")
            return wrapped["value"]
        except ADPError:
            raise NetworkUncertain("UNKNOWN: malformed GitHub JSON response") from None

    def _repository(self, query, variables):
        raw = self.request("POST", "/graphql", {"query": query, "variables": {"id": self.target.node_id, **variables}})
        require(type(raw) is dict and not raw.get("errors") and type(raw.get("data")) is dict,
                "UNKNOWN: incomplete GraphQL repository observation")
        repo = raw["data"].get("node")
        require(type(repo) is dict and type(repo.get("databaseId")) is int
                and (repo.get("id"), repo.get("databaseId"), repo.get("nameWithOwner"))
                == (self.target.node_id, self.target.database_id, self.target.owner + "/" + self.target.name),
                "UNKNOWN: canonical GitHub repository binding changed")
        return repo

    def refs(self):
        result = []
        with self.bounded() if self._budget.get() is None else _unchanged():
            for prefix in ("refs/heads/", "refs/tags/"):
                after, cursors = None, set()
                while True:
                    repo = self._repository(REFS_QUERY, {"prefix": prefix, "after": after})
                    connection = repo.get("refs")
                    require(type(connection) is dict and type(connection.get("nodes")) is list
                            and type(connection.get("pageInfo")) is dict, "UNKNOWN: partial ref inventory")
                    for item in connection["nodes"]:
                        require(type(item) is dict and item.get("prefix") == prefix and type(item.get("target")) is dict,
                                "UNKNOWN: malformed remote ref")
                        name = item.get("name")
                        branch(name)
                        result.append(Ref(prefix + name, oid(item["target"].get("oid"))))
                    require(len(result) <= 4096 and len({r.name for r in result}) == len(result), "UNKNOWN: duplicate/oversized ref inventory")
                    page = connection["pageInfo"]
                    require(type(page.get("hasNextPage")) is bool, "UNKNOWN: incomplete pagination")
                    if page["hasNextPage"] is False:
                        break
                    after = page.get("endCursor")
                    string(after, 512)
                    require(after not in cursors, "UNKNOWN: repeated pagination cursor")
                    cursors.add(after)
        return tuple(sorted(result, key=lambda r: r.name))

    def inspect_ref(self, *, writable=False):
        repo = self._repository(REF_QUERY, {"ref": self.target.ref})
        require("ref" in repo, "UNKNOWN: missing exact ref metadata")
        item = repo["ref"]
        current = None
        if item is not None:
            require(type(item) is dict and item.get("prefix") == "refs/heads/" and item.get("name") == self.target.branch
                    and type(item.get("target")) is dict and item["target"].get("__typename") == "Commit",
                    "UNKNOWN: malformed exact branch observation")
            current = oid(item["target"].get("oid"))
        if writable:
            require(repo.get("viewerPermission") in ("WRITE", "MAINTAIN", "ADMIN"), "UNKNOWN: authenticated write permission unavailable")
            if item is not None:
                require("branchProtectionRule" in item and item["branchProtectionRule"] is None,
                        "UNSUPPORTED_ATOMIC_REF: protected branch or unavailable protection")
            else:
                protection = repo.get("branchProtectionRules")
                require(type(protection) is dict and type(protection.get("totalCount")) is int
                        and protection["totalCount"] == 0 and protection.get("nodes") == []
                        and protection.get("pageInfo") == {"hasNextPage": False},
                        "UNSUPPORTED_ATOMIC_REF: absent-branch classic protection not provably empty")
            rules = self.request("GET", self.target.api + "/rules/branches/" + quote(self.target.branch, safe=""))
            require(type(rules) is list and rules == [], "UNSUPPORTED_ATOMIC_REF: branch rules unknown or constrained")
        return current

    def known_commit(self, sha):
        result = self.request("GET", self.target.api + "/git/commits/" + oid(sha), missing=True)
        if result is None:
            return False
        require(type(result) is dict and result.get("sha") == sha, "UNKNOWN: remote object identity mismatch")
        return True

    def upload(self, objects):
        for item in objects:
            response = self.request("POST", self.target.api + "/git/" + {"blob": "blobs", "tree": "trees", "commit": "commits"}[item.kind], item.payload)
            require(type(response) is dict and response.get("sha") == item.oid,
                    "UNSUPPORTED_ATOMIC_REF: provider changed immutable object identity")

    def cas(self, expected, revision, intent_id):
        payload = {"repositoryId": self.target.node_id, "clientMutationId": intent_id,
                   "refUpdates": [{"name": self.target.ref, "beforeOid": expected or ZERO,
                                   "afterOid": oid(revision), "force": False}]}
        raw = self.request("POST", "/graphql", {"query": UPDATE_REFS_MUTATION, "variables": {"input": payload}})
        require(type(raw) is dict and not raw.get("errors") and type(raw.get("data")) is dict
                and type(raw["data"].get("updateRefs")) is dict
                and raw["data"]["updateRefs"].get("clientMutationId") == intent_id,
                "UNKNOWN: GraphQL CAS acknowledgement incomplete")


@contextmanager
def _unchanged():
    yield


class GitHubPolicyAdapter(GitPolicyAdapter):
    """Local accepted policy inspection, HTTP-only authenticated remote refs."""
    def __init__(self, config: Config, service: GitHubCAS, **kwargs):
        super().__init__(config, **kwargs)
        self.service = service

    def _remote_refs(self, config):
        _endpoint(config, self.service.target)
        return self.service.refs()


def _endpoint(config, target):
    current = Config.discover(config.root, remote=config.remote, repository_id=config.identity)
    endpoint = value(current.root, "remote", "get-url", current.remote)
    require(current.identity == target.memory_id and remote_identity(endpoint, current.root) == target.endpoint
            and endpoint in (target.endpoint, target.endpoint + ".git"), "Network repository/endpoint fingerprint differs")


class GitHubGitExecutionPort(GitExecutionPort):
    """Explicit selection; journal-backed one-use network PUSH only.

    Caller status and possession of an authorization never permit a second try.
    A SUBMITTED action with no exact observed result remains UNKNOWN on restart.
    """
    def __init__(self, config: Config, service: GitHubCAS, journal: ExecutionJournal):
        super().__init__(config)
        require(type(service) is GitHubCAS and type(journal) is ExecutionJournal, "Actual GitHub service and M5 journal required")
        self.service, self.journal = service, journal
        self._dispatches = {}
        _endpoint(config, service.target)
        require(journal.memory.config.identity == config.identity, "Network port/journal identity differs")
        memory_config = journal.memory.config
        memory_endpoint = value(memory_config.root, "remote", "get-url", memory_config.remote)
        require(remote_identity(memory_endpoint, memory_config.root).startswith("file:"),
                "UNSUPPORTED_ATOMIC_REF: use a separate local coordination remote; network M1 transport is not qualified here")
        require(not journal.memory.control.resolve().is_relative_to(self.root.resolve()), "Keep private intents outside product source")
        self.service.bind_control(journal.memory.control)

    def unconfirmed_contexts(self):
        return self.service.unconfirmed_contexts()

    def _intent(self, action):
        observed = self.journal.inspect()
        same = ("task_key", "generation", "operation", "revision", "source_ref", "target", "expected_target", "payload")
        matches = [(key, row) for key, row in observed["state"]["execution"]["actions"].items()
                   if all(row.get(k) == action.get(k) for k in same)]
        require(len(matches) == 1, "An exact unique durable M5 intent is required")
        return observed, *matches[0]

    def _claim_path(self, action_id):
        return safe_path(self.journal.memory.control / ("network-cas-" + action_id + ".json"))

    def _claim(self, action_id, action):
        return {"intent": action_id, "generation": action["generation"], "repository": self.config.identity,
                "github_node": self.service.target.node_id, "github_database_id": self.service.target.database_id,
                "endpoint": self.service.target.fingerprint, "ref": action["target"],
                "old": action["expected_target"], "new": action["revision"], "action": digest({k: action[k] for k in
                    ("task_key", "generation", "operation", "revision", "source_ref", "target", "expected_target", "payload")})}

    def prepare_dispatch(self, action_id, action):
        """Mint once at actual PREPARED→SUBMITTED, never from recovered intent."""
        if action["operation"] != Operation.PUSH:
            return None
        self.service._check_stop()
        _endpoint(self.config, self.service.target)
        observed, canonical_id, row = self._intent(action)
        require(canonical_id == action_id and row["status"] == "PREPARED" and observed["local_owner"]
                and observed["state"]["generation"] == action["generation"], "Fresh owning PREPARED intent required")
        claim = self._claim(action_id, action)
        try:
            descriptor = os.open(self._claim_path(action_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            raise ADPError("UNKNOWN: network intent was already consumed; no automatic retry") from None
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encode(claim)); stream.flush(); os.fsync(stream.fileno())
        from .storage import sync_directory
        sync_directory(self.journal.memory.control)
        ticket = object()
        self._dispatches[ticket] = (action_id, claim)
        return ticket

    def _authorize(self, action, provider, plan, authorization):
        require(type(provider) is PolicyProvider and type(provider.adapter) is GitHubPolicyAdapter and provider.adapter.service is self.service,
                "Network policy must use the same authenticated bounded HTTP observations")
        require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Fresh exact-operation M3 authorization is required")
        require(plan.request.operation == Operation.PUSH and plan.task.repository_id == self.config.identity
                and provider.adapter.config.root == self.root and plan.task.revision == action["revision"]
                and plan.task.source_ref == action["source_ref"] and plan.target_ref == action["target"]
                and plan.expected_target == action["expected_target"] and data(plan.payload) == action["payload"]
                and plan.remote == self.config.remote and plan.remote_fingerprint == self.service.target.fingerprint,
                "Network effect differs from the exact authorized M3 plan")
        _endpoint(self.config, self.service.target)
        require(action["target"] == self.service.target.ref and action["source_ref"] == action["target"]
                and value(self.root, "rev-parse", "HEAD") == oid(action["revision"])
                and value(self.root, "symbolic-ref", "HEAD") == action["source_ref"], "Network source/ref changed")
        if action["expected_target"] is not None:
            oid(action["expected_target"])
            require(value(self.root, "--no-replace-objects", "merge-base", action["expected_target"], action["revision"])
                    == action["expected_target"], "Non-fast-forward network update refused")
        observed, key, row = self._intent(action)
        require(observed["local_owner"] and observed["state"]["generation"] == action["generation"]
                and row["status"] == "SUBMITTED", "Current owning generation and SUBMITTED intent required")
        return key

    def remote_revision(self, ref):
        require(ref == self.service.target.ref, "Network port is pinned to one branch")
        _endpoint(self.config, self.service.target)
        return self.service.inspect_ref()

    def observe(self, action):
        if action["operation"] != Operation.PUSH:
            return super().observe(action)
        try:
            self.service._check_stop()
            _endpoint(self.config, self.service.target)
            require(action["target"] == self.service.target.ref and action["source_ref"] == self.service.target.ref,
                    "Network ref binding differs")
            require(value(self.root, "rev-parse", "HEAD") == action["revision"]
                    and value(self.root, "symbolic-ref", "HEAD") == action["source_ref"], "Local source changed")
            _, action_id, row = self._intent(action)
            remote = self.service.inspect_ref()
            if remote == action["revision"]:
                return ExternalObservation("PRESENT", action["target"], remote)
            if row["status"] == "PREPARED" and not self._claim_path(action_id).exists() and remote == action["expected_target"]:
                return ExternalObservation("ABSENT")
        except (ADPError, OSError, KeyError):
            pass
        return ExternalObservation("UNKNOWN")

    def submit(self, action, provider, plan, authorization, *, dispatch=None):
        if action["operation"] != Operation.PUSH:
            return super().submit(action, provider, plan, authorization)
        require(dispatch in self._dispatches, "Fresh one-use network dispatch capability required")
        action_id, claim = self._dispatches.pop(dispatch)
        require(claim == self._claim(action_id, action) and load_json(self._claim_path(action_id)) == claim,
                "Network claim is missing, corrupt or belongs to another intent")
        with self.service.bounded():
            require(self._authorize(action, provider, plan, authorization) == action_id, "Network intent changed")
            require(self.service.inspect_ref(writable=True) == action["expected_target"], "Remote changed before immutable object transfer")
            objects = closure(self.root, action["revision"], self.service.known_commit)
            self._authorize(action, provider, plan, authorization)
            self.service.upload(objects)
            # Upload latency/source/ownership/policy drift cannot authorize late CAS.
            self._authorize(action, provider, plan, authorization)
            require(self.service.inspect_ref(writable=True) == action["expected_target"], "Remote changed before atomic CAS")
            try:
                self.service.cas(action["expected_target"], action["revision"], action_id)
            except (ADPError, OSError):
                return self.observe(action)
            return self.observe(action)
