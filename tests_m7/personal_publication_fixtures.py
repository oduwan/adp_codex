"""Owned offline stores with explicit broad-personal/quiescence fixture auth.

This does not attest a real gh login, actual GitHub write or genuine model run.
"""
import json
from pathlib import Path
from unittest.mock import patch

from adp.discovery_schema import digest
from adp.network_git import GitHubTarget
from adp.network_http import Response
from adp.personal_publication import PersonalPublication
from personal_fixtures import PersonalFixture
import test_personal_execution as baseline_personal
from network_fixtures import ObjectServer, gv
from test_config import run, snapshot


class PersonalObjectTransport:
    """Controlled GitHub semantics; actual OIDs and update-ref expected-old CAS.

    bind_repository pins the recipient only. Broad fixture permissions are NOT
    described as a single-ID installation issuance or independent signature.
    """
    def __init__(self, fixture, root, target):
        self.f, self.target = fixture, target
        self.server = ObjectServer(root, target)
        self.runtime_settings = self.server.runtime_settings
        self.server.scope_ids = (target.database_id, target.database_id + 1)
        self.credential_binding = "c" * 64
        self.credential_provenance = {"provider": "SYNTHETIC_GH_FIXTURE", "version": "NOT_GENUINE"}
        self.last_response = None
        self.authorize_write = None

    def bind_repository(self, node_id, database_id):
        assert (node_id, database_id) == (self.target.node_id, self.target.database_id)

    def request(self, method, path, body, *, seconds):
        assert 0 < seconds <= self.runtime_settings.limits.request_timeout_seconds
        mutation = method == "POST" and (path != "/graphql" or "mutation " in body["query"])
        if mutation:
            assert self.authorize_write is not None and self.authorize_write() is True
        discovery = (method == "GET" and (path == "/user" or path == self.target.api
            or "/issues" in path or "/pulls" in path or "/branches/" in path and "/rules/" not in path
            or path == self.target.api + "/rules/branches/trunk"))
        if discovery:
            observed = self.f.transport.get(path)
            response = Response(observed.status, json.dumps(observed.body).encode())
            headers = observed.headers
        else:
            response = self.server.request(method, path, body, seconds=seconds)
            headers = ()
        self.last_response = (response.status, response.body, headers)
        return response


class PublicationFixture(PersonalFixture):
    # Reuse the accepted synthetic runtime helpers without importing/inheriting
    # another TestCase's methods into the new qualification denominator.
    enroll = baseline_personal.PersonalExecutionTests.enroll
    dispatch = baseline_personal.PersonalExecutionTests.dispatch

    def setUp(self):
        # M7's byte-preserving Git Data contract supports canonical UTC commit
        # actors only. Create this new fixture's commits in that supported
        # environment; the accepted non-UTC refusal tests remain unchanged.
        timezone = patch.dict("os.environ", {"TZ": "UTC"})
        timezone.start()
        self.addCleanup(timezone.stop)
        super().setUp()

    def observation_snapshot(self):
        # Accepted M7 necessarily creates/removes a private request-stop marker.
        # Exempt only that directory's mtime, retaining modes and all contents.
        tree = snapshot(self.base)
        control = str(self.c.memory.control.relative_to(self.base))
        mode, _, kind = tree[control].split(":", 2)
        self.assertEqual(kind, "directory")
        tree[control] = mode + ":private-network-control-mtime:" + kind
        identities = {str(p.relative_to(self.personal.directory)): (p.lstat().st_dev, p.lstat().st_ino, p.lstat().st_mode)
                      for p in self.personal.directory.rglob("*")}
        return {"tree": tree, "private_identities": identities, "memory": self.c.memory.inspect(), "github_refs": self.http.server.refs()}

    def ready(self, *, absent=True, intermediate=False):
        self.initial = gv(self.a, "rev-parse", "HEAD")
        if intermediate:
            run(self.a, "commit", "--allow-empty", "-m", "Synthetic intermediate product parent")
            self.middle = gv(self.a, "rev-parse", "HEAD")
        self.enroll()
        _, token = self.c.invocation()
        result = self.c.run(reviewed=token, authorized=True)
        self.assertEqual(result["status"], "LOCAL_DRAFT_CODE_REVIEWED")
        p = self.personal.plan
        target = GitHubTarget(self.rid, p["repository"]["node_id"], 17, *self.name.split("/"), p["feature"]["branch"])
        self.store = self.base / "synthetic-github-store.git"
        self.store.mkdir()
        gv(self.store, "init", "--bare", "--initial-branch=trunk")
        gv(self.store, "fetch", "--no-tags", "--no-write-fetch-head", "--no-auto-maintenance", str(self.a), self.initial)
        gv(self.store, "update-ref", "refs/heads/trunk", self.initial)
        if not absent:
            gv(self.store, "update-ref", target.ref, self.initial)
        self.http = PersonalObjectTransport(self, self.store, target)
        self.publisher = self.reconnect_publisher()
        return self.publisher

    def reconnect_publisher(self):
        publisher = PersonalPublication(self.c, transport=self.http)
        self.http.authorize_write = publisher.write_authorized
        return publisher

    def publish(self, token, *, publisher=None):
        return (publisher or self.publisher).publish(reviewed=token, authorized=True,
            assume_quiescence=True, confirm_project_rules=True)
