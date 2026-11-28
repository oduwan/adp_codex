"""Minimal stopped-receipt prerequisites for Issue69 late-stage qualification.

Synthetic external transport and Codex-shaped retained receipts ONLY. No actual
model, GitHub target or complete lifecycle controller is substituted for a stage.
"""
import json
from dataclasses import replace
from unittest.mock import patch

from adp.codex_runtime import CodexExecRuntime
from adp.discovery_schema import digest
from adp.execution_types import Capabilities, Role, WorkerResult
from adp.guard_types import Outcome, data
from adp.personal_enrollment import apply_personal
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductCoordinator
from adp.personal_publication import PersonalPublication
from adp.personal_storage import approval, create_private
from adp.personal_track import PersonalTrack
from adp.schema import encode
from adp.storage import atomic
from personal_fixtures import NativePersonalReads
from personal_product_fixtures import ProductFixture
from personal_track_fixtures import TrackTransport
from network_fixtures import gv


class ResidualTransport(TrackTransport):
    def request(self, method, path, body, *, seconds):
        if method == "GET" and path.startswith(self.target.api + "/pulls?"):
            from urllib.parse import parse_qs
            from copy import deepcopy
            from adp.network_http import Response
            query = parse_qs(path.partition("?")[2])
            for pull in self.pulls:
                pull["head"]["sha"] = gv(self.server.root, "rev-parse", "refs/heads/" + pull["head"]["ref"])
            rows = self.pulls
            if "head" in query:
                selected = query["head"][0].split(":", 1)[1]
                rows = [pull for pull in rows if pull["head"]["ref"] == selected]
            raw = json.dumps(deepcopy(rows)).encode()
            self.last_response = 200, raw, ()
            return Response(200, raw)
        if method == "GET" and getattr(self.f, "private_free", False) and ("/rules/branches/" in path or path.partition("?")[0].endswith("/protection")):
            from test_personal_rules import denied
            from adp.network_http import Response
            response = denied(classic=path.partition("?")[0].endswith("/protection"))
            raw = json.dumps(response.body).encode()
            self.last_response = response.status, raw, response.headers
            return Response(response.status, raw)
        if method == "GET" and path.startswith(self.target.api + "/git/ref/heads/"):
            from urllib.parse import unquote
            from adp.network_http import Response
            ref = "refs/heads/" + unquote(path.split("/git/ref/heads/", 1)[1])
            raw = json.dumps({"ref": ref, "object": {"sha": gv(self.server.root, "rev-parse", ref)}}).encode()
            self.last_response = 200, raw, ()
            return Response(200, raw)
        return super().request(method, path, body, seconds=seconds)


class ResidualStageFixture(ProductFixture):
    def setUp(self):
        super().setUp()
        import hashlib, subprocess, sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        files = list((root / "adp").glob("*.py")) + [Path(__file__), root / "tests_m7/test_residual_stages.py"]
        print("FOCUSED_SOURCE " + json.dumps({"head": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
            "dirty": bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"])),
            "python": sys.version, "sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}, sort_keys=True), flush=True)
        from adp.discovery_github import GitHubDiscoveryAdapter
        original = GitHubDiscoveryAdapter.__init__
        def clocked(adapter, *args, **kwargs):
            kwargs.setdefault("clock", lambda: self.now)
            original(adapter, *args, **kwargs)
        patch.object(GitHubDiscoveryAdapter, "__init__", clocked).start()
        self.addCleanup(patch.stopall)
        from adp.personal_network import PersonalGitHubTransport
        live = patch.object(PersonalGitHubTransport, "request", side_effect=AssertionError("No live HTTP in focused fixtures")).start()
        credential = patch.object(PersonalGitHubTransport, "_credential", side_effect=AssertionError("No live credentials in focused fixtures")).start()
        self.addCleanup(live.assert_not_called)
        self.addCleanup(credential.assert_not_called)

    def enroll(self, ci_transport=None):
        self.transport.api.responses[self.prefix + "/branches/trunk"].body["commit"] = {"sha": gv(self.a, "rev-parse", "HEAD")}
        ci_transport = ci_transport or NativePersonalReads(self)
        plan, original, docs = self.plan(ci_transport=ci_transport)
        self.personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
            transport=self.transport, ci_transport=ci_transport, clock=lambda: self.now)
        self.connect_runtime()
        self.c = ProductCoordinator(self.personal, self.transport, ci_transport,
            runtime=self.runtime, clock=lambda: self.now)
        _, token = PersonalTrack.registration(self.c, (1, 2, 3))
        self.track = PersonalTrack.register(self.c, (1, 2, 3), reviewed=token, authorized=True)

    def connect_runtime(self):
        self.runtime = CodexExecRuntime(self.personal.state / "runtime")
        self.requests = []
        caps = Capabilities("codex-exec", self.runtime.host, "SYNTHETIC_RETAINED_RECEIPTS_ONLY", True, True, True, True, 1)
        self.addCleanup(patch.stopall)
        patch.object(self.runtime, "capabilities", return_value=caps).start()
        patch.object(self.runtime, "dispatch", side_effect=AssertionError("No Worker launch in late-stage qualification")).start()

    def seed_receipt(self, request):
        self.requests.append(request)
        purpose = json.loads(request.prompt.split("\n", 1)[1])["purpose"]
        if purpose == "develop":
            from pathlib import Path
            (Path(request.workspace) / "product").write_text("Original issue " + str(self.personal.plan["issue"]) + " candidate\n")
        summary = "Synthetic stopped independent prerequisite; NOT genuine Codex"
        if purpose == "develop":
            summary = json.dumps({"change": "Fixture original candidate", "checks": [{"command": "existing-check",
                "outcome": "PASS", "result": "Synthetic local fixture"}], "limitations": "No genuine runtime qualification"})
        result = WorkerResult(Outcome.PASS, request.role == Role.REVIEWER,
            () if request.role == Role.DEVELOPER else (purpose,), summary)
        create_private(self.runtime.directory)
        raw = {"host": self.runtime.host, "request_digest": digest(request), "status": "COMPLETED",
            "pid": 50000 + len(self.requests), "start_time": "synthetic-only", "context": "synthetic-distinct:" + request.id,
            "result": data(result), "elapsed": 1, "samples": 1, "payload_bytes": 100, "stopped": True}
        self.runtime._save(request.id, raw)
        atomic(self.runtime.directory / (request.id + ".stop.json"), encode({"request_digest": digest(request),
            "pid": raw["pid"], "status": "EXITED", "stopped": True, "cli_exit": 0}))
        return self.runtime.observe(request.id)

    def seed_worker(self, purpose, workspace):
        """Seed retained stopped evidence through real M1/M2 accounting only."""
        import secrets
        from adp.execution_types import WorkerRequest
        from adp.execution_containment import source_seal, admin_seal
        from adp.personal_workers import prompt
        from adp.guard_types import Action, ActionKind
        c = self.c
        print("SEEDED_PREREQUISITE_BEGIN " + purpose, flush=True)
        context = self.product.review_context() if purpose == "product" else c.context(purpose)
        request = WorkerRequest(secrets.token_hex(32), c.task_id, c.memory.inspect()["state"]["generation"],
            Role.DEVELOPER if purpose == "develop" else Role.REVIEWER, c.revision(), str(workspace),
            prompt(purpose, context), 300, self.now + 300)
        row = {"schema_version": 1, "purpose": purpose, "request": data(request), "context": context,
            "assignment": c.memory.assign(c.task_id, "worker:" + request.id), "requirement": c.requirement(purpose),
            "permit": None, "phase": "PREPARED", "observation": None, "source": source_seal(workspace),
            "admin": admin_seal(workspace), "outside": source_seal(workspace, tuple(c.personal.plan["paths"]) if purpose == "develop" else ()),
            "result_source": None, "result_admin": None, "expires_at": c.personal.plan["window"]["expires_at"],
            "host": self.runtime.host, "guard_context": None}
        c.workers.save(row)
        action = Action("worker:" + request.id if purpose == "develop" else "personal:independent-observation",
            ActionKind.CHECK if purpose == "develop" else ActionKind.REVIEW, "worker:" + request.id, "Retained independent fixture evidence", seconds=300)
        action = c.worker_action(row, action)
        permit = c.guard.begin(c.task_id, row["requirement"], action)
        row.update(permit=data(permit), guard_context=c.guard._snapshot(c.task_id, row["requirement"])[2]["active"]["context"])
        observed = self.seed_receipt(request)  # Fixture file generation, NOT runtime.dispatch/worker launch.
        row.update(phase="STOPPED", observation=data(observed), result_source=source_seal(workspace), result_admin=admin_seal(workspace))
        c.workers.save(row)
        c.workers.finish(row)
        print("SEEDED_PREREQUISITE_ACCOUNTED " + purpose, flush=True)
        return c.worker(request.id)

    def late_prerequisites(self, *, current=False):
        from adp.personal_git import administration
        from adp.personal_track_preparation import prepare
        self.choices = replace(self.choices, checks=("unit",), accept_native_job_records=True)
        if not current:
            self.all_pulls, self.all_comments = [], []
            if getattr(self, "private_free", False):
                from test_personal_rules import denied
                self.transport.api.responses[self.prefix].body["private"] = True
                self.transport.api.responses[self.prefix + "/rules/branches/trunk"] = denied()
                self.transport.api.responses[self.prefix + "/branches/trunk/protection"] = denied(classic=True)
            self.enroll()
        c = self.c
        c.initialize_run()
        original = self.seed_worker("original", self.a)
        row = c.record(); row.update(original_review=original["request"]["id"], phase="FEATURE"); c.save(row)
        prepare(c.track)
        gv(self.a, "worktree", "add", "-b", self.personal.plan["feature"]["branch"], str(self.personal.feature))
        row = c.record(); row.update(feature_administration=administration(self.personal.feature), phase="DEVELOP"); c.save(row)
        self.seed_worker("develop", self.personal.feature)
        gv(self.personal.feature, "add", "--", "product")
        gv(self.personal.feature, "commit", "-m", self.personal.plan["commit_message"], "-m", self.personal.plan["commit_body"])
        revision = gv(self.personal.feature, "rev-parse", "HEAD")
        c.memory.set_revision(c.task_id, revision)
        row = c.record(); row.update(revision=revision, phase="CODE", feature_administration=administration(self.personal.feature)); c.save(row)
        self.seed_worker("code", self.personal.feature)
        row = c.record(); row["phase"] = "LOCAL_DRAFT_CODE_REVIEWED"; c.save(row)
        target = __import__("adp.network_git", fromlist=["GitHubTarget"]).GitHubTarget(self.rid,
            self.personal.plan["repository"]["node_id"], 17, *self.name.split("/"), self.personal.plan["feature"]["branch"])
        if not current:
            self.store = self.base / "stage-forge.git"; self.store.mkdir()
            gv(self.store, "init", "--bare", "--initial-branch=trunk")
        gv(self.store, "fetch", "--no-tags", "--no-write-fetch-head", str(self.a), revision)
        if not current:
            gv(self.store, "update-ref", "refs/heads/trunk", self.personal.plan["checkout"]["head"])
        self.assertEqual(gv(self.store, "rev-parse", "refs/heads/trunk"), self.personal.plan["checkout"]["head"])
        gv(self.store, "update-ref", target.ref, revision)
        self.http = ResidualTransport(self, self.store, target)
        if getattr(self, "private_free", False):self.http.server.permission = "ADMIN"
        self.transport.api.responses[self.prefix].body.update(allow_merge_commit=True, allow_squash_merge=True)
        self.product = p = PersonalProduct(c, transport=self.http)
        c.ci_transport = p.read  # NEXT/enrollment reads use the same actual Budget/transport port.
        self.http.authorize_write = p.write_authorized
        # Seed observed immutable publication prerequisite in the existing M7
        # journal. Its live native ref is real fixture Git; no publication is run.
        p.journal.upgrade(authorized=True); p.journal.upgrade_product_flow(authorized=True)
        from adp.schema import key
        task = c.memory.inspect()["tasks"][key(c.task_id)]
        admitted = {"task_id": c.task_id, "identity": {"repository_id": self.rid, "issue_id": self.personal.plan["issue_id"], "forge": "github"},
            "workspace_key": digest(self.personal.plan["administration"]), "admission": digest({"seeded": "scope"}),
            "issue_digest": self.personal.plan["original_digest"], "revision": revision, "source_ref": target.ref,
            "product_iteration": task["iteration"], "kind": "PRODUCT", "stage": "PUBLISH", "jobs": {}, "review": None}
        p.journal.change(lambda e, s, t: p.publication.admit_task(e, key(c.task_id), admitted))
        # A previously created, exact Draft PR is an explicitly seeded external
        # prerequisite. PR creation itself is NOT measured/qualified here.
        number = 9 + self.personal.plan["issue"]
        body = "Refs #" + str(self.personal.plan["issue"])
        proposed = p.proposed("PR", title="Original candidate", body=body)
        row = p.initialize()
        action = digest({"personal-product": proposed["result"]})
        repo = {"id": 17, "node_id": p.target.node_id, "full_name": self.name}
        pull = {"id": 2000+number, "node_id": "PR_seeded_"+str(number), "number": number,
            "html_url": "https://github.com/" + self.name + "/pull/"+str(number),
            "url": "https://api.github.com" + self.prefix + "/pulls/"+str(number), "updated_at": "2026-11-09T08:00:00Z", "user": {"id": 91},
            "title": "Original candidate", "body": body + "\n\n" + p.forge.marker(action), "draft": False,
            "state": "open", "merged": False, "mergeable": True, "mergeable_state": "clean",
            "head": {"ref": p.target.branch, "sha": self.c.revision(), "repo": repo},
            "base": {"ref": "trunk", "sha": proposed["result"]["facts"]["base_sha"], "repo": repo}}
        self.all_pulls.append(pull)
        row["pull"] = {"id": str(pull["id"]), "node_id": pull["node_id"], "number": number,
            "repository_id": self.rid, "url": pull["html_url"]}
        row["intents"].append({"view": proposed["result"], "approval": proposed["approval"], "binding": proposed["binding"],
            "action": action, "requirement": None, "reservation": None, "observation": None})
        p.save(row)
        self.assertEqual(self.execute_product("CI", accept_native=True)["status"], "PASS")
        worker = self.seed_worker("product", self.personal.feature)
        row = p.record(); row["review"] = worker["request"]["id"]; p.save(row)
        return p
