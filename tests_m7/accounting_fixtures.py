"""Synthetic stopped receipts and native three-Issue graph; no live runtime."""
from dataclasses import replace
from pathlib import Path
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from adp.discovery_github import GitHubDiscoveryAdapter, Response
from adp.git import value
from adp.personal_episode import Continuation
from adp.personal_enrollment import apply_personal
from adp.execution_types import Role
from adp.codex_runtime import CodexExecRuntime
from adp.execution_types import Capabilities, WorkerResult
from adp.guard_types import Outcome, data
from adp.discovery_schema import digest
from adp.schema import encode
from adp.storage import atomic
from adp.personal_storage import create_private
from adp.personal_recovery import Recovery
from adp.personal_runner import PersonalCoordinator
from adp.personal_track import PersonalTrack
from adp.personal_track_preparation import prepare
from personal_fixtures import NativePersonalReads
from stopped_notrun_fixtures import StoppedNotRunFixture


class Checks(NativePersonalReads):
    def get(self, path, *, seconds):
        original = self.f
        self.f = SimpleNamespace(a=getattr(original, "check_root", original.a), prefix=original.prefix, name=original.name)
        try:
            response = super().get(path, seconds=seconds)
        finally:
            self.f = original
        if type(response.body) is dict and "check_runs" in response.body:
            for row in response.body["check_runs"]:
                row["name"] = "tests"
                row["started_at"] = datetime.fromtimestamp(self.f.now - 5, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                row["completed_at"] = datetime.fromtimestamp(self.f.now - 1, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return response


class AccountingFixture(StoppedNotRunFixture):
    def setUp(self):
        patch.dict("os.environ", {"TZ": "UTC"}).start()
        self.addCleanup(patch.stopall)
        super().setUp()
        self.choices = replace(self.choices, paths=("product", "candidate.txt"), checks=("tests",), accept_native_job_records=True)
        self.native = Checks(self)
        original = GitHubDiscoveryAdapter.__init__
        patch.object(GitHubDiscoveryAdapter, "__init__", lambda adapter, *a, **kw:
            original(adapter, *a, **{**kw, "clock": lambda: self.now})).start()
        self.addCleanup(patch.stopall)
        self.transport.api.responses[self.prefix + "/branches/trunk"] = Response(200, {"name": "trunk", "protected": False,
            "commit": {"sha": value(self.a, "rev-parse", "HEAD")}})

    def plan(self, **kwargs):
        return super().plan(ci_transport=self.native, **kwargs)

    def dispatch(self, request):
        if ":accounting:" in request.task_id or getattr(self, "personal", None) is not None and self.personal.plan["issue"] > 1:
            purpose = json.loads(request.prompt.split("\n", 1)[1])["purpose"]
            self.requests.append(request)
            if purpose == "develop":
                (Path(request.workspace) / "product").write_text("Synthetic original Issue " + str(self.personal.plan["issue"]) + " implementation\n")
            result = WorkerResult(Outcome.PASS, purpose != "develop", () if purpose == "develop" else (purpose,), "Synthetic independent episode judgment; NOT genuine runtime")
            create_private(self.runtime.directory)
            raw = {"host": self.runtime.host, "request_digest": digest(request), "status": "COMPLETED",
                "pid": 51000 + len(self.requests), "start_time": "synthetic-only", "context": "synthetic:" + request.id,
                "result": data(result), "elapsed": 1, "samples": 1, "payload_bytes": 100, "stopped": True}
            self.runtime._save(request.id, raw)
            atomic(self.runtime.directory / (request.id + ".stop.json"), encode({"request_digest": digest(request),
                "pid": raw["pid"], "status": "EXITED", "stopped": True, "cli_exit": 0}))
            return self.runtime.observe(request.id)
        if request.role == Role.DEVELOPER:
            (Path(request.workspace) / "candidate.txt").write_text("Unaccepted candidate only\n")
        return super().dispatch(request)

    def incident(self):
        initialize, feature = PersonalCoordinator.initialize_run, PersonalCoordinator.prepare_feature
        def register(c):
            c.ci_transport = self.native
            if c.track is None:
                _, token = PersonalTrack.registration(c, (1, 2, 3))
                PersonalTrack.register(c, (1, 2, 3), reviewed=token, authorized=True)
            return initialize(c)
        def prepared(c):
            prepare(c.track)
            return feature(c)
        with patch.object(PersonalCoordinator, "initialize_run", register), patch.object(PersonalCoordinator, "prepare_feature", prepared), \
             patch("stopped_notrun_fixtures.apply_personal", side_effect=lambda *a, **kw: apply_personal(*a, ci_transport=self.native, **kw)):
            self.expired()
        self.recovery = Recovery(self.c)
        self.child_choices = {"branch": "work/issue-1-accounting", "workspace": str(self.base / "child-feature"),
            "paths": ["product", "candidate.txt"], "checks": ["tests"], "commit_message": "Implement original scope",
            "commit_body": "", "seconds": 1800, "developers": 0, "candidate_reviewers": 1,
            "code_reviewers": 2, "maximum_check_observations": 3, "worker_seconds": 300}
        return self.row

    def archive(self):
        self.incident()
        for stage in ("guard", "result"):
            view, _, _ = self.recovery.preview(stage, request=self.row["request"]["id"], choices=self.child_choices)
            self.recovery.apply(stage, reviewed=view["approval"], authorized=True, acknowledge=True,
                request=self.row["request"]["id"], choices=self.child_choices)
        return self.recovery.master()

    def episode(self):
        self.archive()
        self.continuation = Continuation(self.c)
        view, _ = self.continuation.preview()
        return self.continuation.apply(reviewed=view["approval"], authorized=True)

    def child(self):
        from adp.personal_episode import load_episode
        self.episode()
        self.original_c, self.original_personal = self.c, self.personal
        self.personal = load_episode(self.continuation.directory)
        self.runtime = CodexExecRuntime(self.personal.state / "runtime")
        patch.object(self.runtime, "capabilities", return_value=Capabilities("codex-exec", self.runtime.host,
            "SYNTHETIC_NOT_GENUINE_RUNTIME", True, True, True, True, 1)).start()
        patch.object(self.runtime, "dispatch", side_effect=self.dispatch).start()
        self.c = PersonalCoordinator(self.personal, self.transport, self.native, runtime=self.runtime, clock=lambda: self.now)
        return self.c
