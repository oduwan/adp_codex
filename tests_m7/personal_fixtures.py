"""Owned disposable sources and synthetic GETs; never a runtime qualification."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from adp.discovery_github import FixtureTransport, Response
from adp.personal_enrollment import PersonalChoices, plan_personal, selection
from discovery_fixtures import issue, responses
from test_config import GitFixture, run


class PersonalReads:
    def __init__(self, entries):
        self.api = FixtureTransport(entries)
        self.account = Response(200, {"id": 91, "private_profile_field": "PRIVATE_ACCOUNT_PROFILE"})
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return self.account if path == "/user" else self.api.get(path)


class PersonalFixture(GitFixture):
    def setUp(self):
        super().setUp()
        self.name, self.rid = "personal/project", "17"
        self.prefix = "/repos/" + self.name
        run(self.a, "remote", "add", "forge", "https://github.com/" + self.name + ".git")
        rows = [issue(n, name=self.name) for n in (1, 2, 3)]
        entries = responses(rows, name=self.name, rid=self.rid)
        entries[self.prefix] = Response(200, {"id": 17, "node_id": "R_personal", "full_name": self.name,
            "default_branch": "trunk", "owner": {"id": 91, "type": "User"},
            "permissions": {"pull": True, "push": True, "admin": True}})
        for n in (2, 3):
            entries[f"{self.prefix}/issues/{n}/dependencies/blocked_by?per_page=100&page=1"] = Response(200, [rows[n - 2]])
        entries[self.prefix + "/branches/trunk"] = Response(200, {"name": "trunk", "protected": False})
        entries[self.prefix + "/rules/branches/trunk"] = Response(200, [])
        self.transport = PersonalReads(entries)
        self.directory = self.base / "personal-state"
        self.choices = PersonalChoices(1, self.directory, ("product",), branch="work/issue-1")
        self.now = 1000

    def observe(self):
        return selection(self.a, "forge", self.rid, self.transport)

    def plan(self, *, choices=None, approved=None, ci_transport=None):
        observation, owner = self.observe()
        return plan_personal(observation, owner, choices or self.choices, approved=approved,
                             ci_transport=ci_transport, clock=lambda: self.now)


class NativePersonalReads:
    """Synthetic native GitHub job inventory bound to the actual fixture HEAD."""
    def __init__(self, fixture):
        self.f = fixture
        self.conclusion = "success"
        self.app = 9

    def get(self, path, *, seconds):
        from adp.git import value
        root = self.f.a
        sha, ref = value(root, "rev-parse", "HEAD"), value(root, "symbolic-ref", "HEAD")
        prefix = self.f.prefix
        if path == prefix:
            return Response(200, {"id": 17, "full_name": self.f.name})
        if path.startswith(prefix + "/git/ref/heads/"):
            return Response(200, {"ref": ref, "object": {"sha": sha}})
        route = path.partition("?")[0]
        if route.endswith("/statuses"):
            return Response(200, [])
        if route.endswith("/check-suites"):
            return Response(200, {"total_count": 1, "check_suites": [{"id": 70}]})
        if route.endswith("/check-runs"):
            return Response(200, {"total_count": 1, "check_runs": [{"id": 71, "name": "unit", "head_sha": sha,
                "url": "https://api.github.com" + prefix + "/check-runs/71", "app": {"id": self.app},
                "status": "completed", "conclusion": self.conclusion,
                "started_at": "1970-01-01T00:16:30Z", "completed_at": "1970-01-01T00:16:35Z"}]})
        raise AssertionError("Unexpected focused native GET")
