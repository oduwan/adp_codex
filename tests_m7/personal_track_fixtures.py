"""Only owned disposable Git + synthetic native API/worker evidence, NOT M8."""
import copy
import json
from pathlib import Path
import re
from unittest.mock import patch

from adp.codex_runtime import CodexExecRuntime
from adp.discovery_github import GitHubDiscoveryAdapter
from adp.discovery_schema import digest
from adp.execution_types import Capabilities, RuntimeObservation, RuntimeStatus, WorkerResult
from adp.guard_types import Outcome
from adp.network_git import GitHubTarget
from adp.network_http import NetworkTransportError, Response
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductCoordinator
from adp.personal_product_http import PersonalProjectRead
from adp.personal_publication import PersonalPublication
from adp.personal_runner import PersonalCoordinator
from adp.personal_storage import load_state
from adp.personal_track import PersonalTrack
from adp.personal_track_preparation import prepare
from personal_fixtures import NativePersonalReads
from personal_product_fixtures import ProductFixture, ProductTransport
from network_fixtures import gv
from test_config import run


class TrackTransport(ProductTransport):
    def __init__(self, fixture, root, target):
        super().__init__(fixture, root, target)
        self.pulls = fixture.all_pulls
        self.comments = fixture.all_comments
        self.report_loss = None

    def request(self, method, path, body, *, seconds):
        base = self.target.api
        if method == "GET" and path.startswith(base + "/pulls?"):
            for p in self.pulls:
                p["head"]["sha"] = gv(self.server.root, "rev-parse", "refs/heads/" + p["head"]["ref"])
            data = copy.deepcopy(self.pulls)
        elif method == "GET" and path == base + "/branches/trunk":
            data = {**copy.deepcopy(self.f.transport.api.responses[path].body),
                "commit": {"sha": gv(self.server.root, "rev-parse", "refs/heads/trunk")}}
        elif method == "GET" and re.fullmatch(re.escape(base) + r"/pulls/[1-9][0-9]*", path):
            data = copy.deepcopy(next(p for p in self.pulls if str(p["number"]) == path.rsplit("/", 1)[1]))
            data["head"]["sha"] = gv(self.server.root, "rev-parse", "refs/heads/" + data["head"]["ref"])
        elif method == "PUT" and path.endswith("/merge"):
            all_pulls = self.pulls
            self.pulls = [next(p for p in all_pulls if "/" + str(p["number"]) + "/merge" in path)]
            try:
                return super().request(method, path, body, seconds=seconds)
            finally:
                self.pulls = all_pulls
        elif method == "POST" and path.endswith("/comments"):
            assert self.authorize_write() is True
            self.effects.append((method, path, copy.deepcopy(body)))
            if self.report_loss == "before":
                raise NetworkTransportError("Synthetic stopped lost comment request")
            number = int(path.split("/")[-2])
            identifier = 500 + len(self.comments)
            data = {"id": identifier, "node_id": "IC_owned_" + str(identifier), "body": body["body"],
                "user": {"id": 91, "node_id": "USER_owned_91"},
                "html_url": "https://github.com/" + self.f.name + "/issues/" + str(number) + "#issuecomment-" + str(identifier),
                "issue_url": "https://api.github.com" + base + "/issues/" + str(number),
                "created_at": "2026-11-09T08:00:01Z", "updated_at": "2026-11-09T08:00:01Z"}
            self.comments.append(data)
            self.f.transport.api.responses[base + "/issues/" + str(number)].body["updated_at"] = data["created_at"]
            for row in self.f.transport.api.responses[base + "/issues?state=all&sort=created&direction=asc&per_page=100&page=1"].body:
                if row["number"] == number:
                    row["updated_at"] = data["created_at"]
            from adp.discovery_github import Response as ReadResponse
            self.f.transport.api.responses[base + "/issues/" + str(number) + "/comments?per_page=100&page=1"] = ReadResponse(200,
                [c for c in self.comments if c["issue_url"].endswith("/" + str(number))])
            if self.report_loss == "after":
                self.report_loss = None
                self.last_response = (201, json.dumps(data).encode(), ())
                raise NetworkTransportError("Synthetic stopped lost comment response")
        else:
            return super().request(method, path, body, seconds=seconds)
        self.last_response = (200, json.dumps(data).encode(), ())
        return Response(200, json.dumps(data).encode())


class TrackFixture(ProductFixture):
    def setUp(self):
        super().setUp()
        self.all_pulls, self.all_comments = [], []
        self.transport.api.responses[self.prefix + "/branches/trunk"].body["commit"] = {"sha": gv(self.a, "rev-parse", "HEAD")}
        self.http_by_identity, self.runtime_by_identity = {}, {}
        original_init = GitHubDiscoveryAdapter.__init__
        fixture = self
        def with_clock(adapter, *args, **kwargs):
            original_init(adapter, *args, **kwargs)
            adapter.clock = lambda: fixture.now
        patch.object(GitHubDiscoveryAdapter, "__init__", with_clock).start()
        actual_accepted = PersonalTrack.accepted
        def accepted(track, identity, *, transport=None, runtime=None):
            return actual_accepted(track, identity, transport=fixture.http_by_identity.get(identity, transport),
                runtime=fixture.runtime_by_identity.get(identity, runtime))
        patch.object(PersonalTrack, "accepted", accepted).start()
        self.addCleanup(patch.stopall)

    def dispatch(self, request):
        self.requests.append(request)
        context = json.loads(request.prompt.split("\n", 1)[1])
        purpose = context["purpose"]
        if purpose == "develop":
            (Path(request.workspace) / "product").write_text("original ticket " + str(context["original"]["number"]) + " implemented\n")
        result = WorkerResult(Outcome.PASS, purpose != "develop", () if purpose == "develop" else (purpose,), "Synthetic offline fixture verdict")
        observed = RuntimeObservation(request.id, self.runtime.host, RuntimeStatus.COMPLETED, "synthetic-context:" + request.id,
            result, "runtime:synthetic:" + request.id, 1, digest(request), 1, 100, True)
        self.observed[request.id] = observed
        return observed

    def enroll_track(self):
        from dataclasses import replace
        self.transport.api.responses[self.prefix].body.update(allow_merge_commit=True, allow_squash_merge=True)
        self.choices = replace(self.choices, checks=("unit",), accept_native_job_records=True)
        self.enroll(NativePersonalReads(self))
        _, token = PersonalTrack.registration(self.c, (1, 2, 3))
        self.track = PersonalTrack.register(self.c, (1, 2, 3), reviewed=token, authorized=True)
        identity = next(i for i, o in self.track.originals.items() if o.issue.number == 1)
        self.runtime_by_identity[identity] = self.runtime
        patch.object(CodexExecRuntime, "observe", lambda runtime, identity: self.observed.get(identity,
            RuntimeObservation(identity, runtime.host, RuntimeStatus.NOT_STARTED, None, None, "runtime:not-started", 0))).start()
        self.store = self.base / "track-forge.git"
        self.store.mkdir()
        gv(self.store, "init", "--bare", "--initial-branch=trunk")
        gv(self.store, "fetch", "--no-tags", "--no-write-fetch-head", "--no-auto-maintenance", str(self.a), gv(self.a, "rev-parse", "HEAD"))
        gv(self.store, "update-ref", "refs/heads/trunk", gv(self.a, "rev-parse", "HEAD"))
        return self.track

    def scope_only(self):
        self.c.initialize_run()
        worker = self.c.workers.execute("original", self.c.context("original"), self.a)
        row = self.c.record()
        row.update(original_review=worker["request"]["id"], phase="FEATURE")
        self.c.save(row)
        return prepare(self.c.track)

    def local_and_publish(self):
        _, token = self.c.invocation()
        result = self.c.run(reviewed=token, authorized=True)
        self.assertEqual(result["status"], "LOCAL_DRAFT_CODE_REVIEWED")
        p = self.personal.plan
        target = GitHubTarget(self.rid, p["repository"]["node_id"], 17, *self.name.split("/"), p["feature"]["branch"])
        identity = next(i for i, o in self.c.track.originals.items() if o.issue.number == p["issue"])
        self.http = self.http_by_identity.get(identity) or TrackTransport(self, self.store, target)
        self.http_by_identity[identity] = self.http
        pub = PersonalPublication(self.c, transport=self.http)
        self.http.authorize_write = pub.write_authorized
        proposed = pub.preview()
        self.publish(proposed["approval"], publisher=pub)
        self.c = ProductCoordinator(self.personal, self.transport, NativePersonalReads(self), runtime=self.runtime, clock=lambda: self.now)
        self.product = PersonalProduct(self.c, transport=self.http)
        self.http.authorize_write = self.product.write_authorized
        return self.product

    def merged(self, *, loss_pr=None, loss_merge=None):
        self.local_and_publish()
        self.create_pr(loss=loss_pr)
        self.assertEqual(self.execute_product("CI", accept_native=True)["status"], "PASS")
        self.assertEqual(self.execute_product("REVIEW")["status"], "PRODUCT_REVIEWED")
        current = next(p for p in self.all_pulls if p["head"]["ref"] == self.product.target.branch)
        current["draft"] = False  # Explicit separate synthetic actor.
        proposal = self.product.proposed("MERGE", method="merge", delegate=True)
        self.http.loss = loss_merge
        try:
            self.merge_product(proposal)
        except Exception as error:
            # Preserve the actual failed gate before TemporaryDirectory cleanup.
            # No reobservation, altered exception/assertion, or extra allowance.
            try:
                from adp.schema import encode
                record = self.product.record()
                state = self.c.memory.inspect()["state"]
                latest = next((e for e in reversed(record["execution"]) if e["view"]["operation"] == "CI"), None)
                evidence = {"kind": "SYNTHETIC_COMPONENT_FAILURE", "issue": self.personal.plan["issue"],
                    "task": self.c.task_id, "source": self.c.record()["revision"], "pull": record["pull"],
                    "latest_ci": None if latest is None else {"phase": latest["phase"], "result": latest["result"]},
                    "observations": self.c.record()["observations"],
                    "maximum_observations": self.personal.plan["window"]["maximum_check_observations"],
                    "guards": {i: {k: row[k] for k in ("sequence", "mode", "counters", "limits")}
                        for i, row in state["progress_guard"]["requirements"].items()},
                    "http_calls": self.product.service._budget.get().calls if self.product.service._budget.get() else None,
                    "effects": [method for method, _, _ in self.http.effects]}
                error.add_note(encode(evidence, 32768).decode("utf-8"))
            except Exception as unavailable:
                error.add_note("Bounded private gate evidence unavailable: " + type(unavailable).__name__)
            raise
        preview = self.c.track.completion_preview(self.product)
        return self.c.track.complete(self.product, reviewed=preview["approval"], authorized=True, confirm_acceptance=True)

    def synchronize(self, merge):
        # Fixture preparation by the project owner; ADP itself does NOT fetch.
        run(self.a, "fetch", "--no-tags", "--no-write-fetch-head", str(self.store), merge)
        run(self.a, "merge", "--ff-only", merge)

    def next_choices(self, number):
        from adp.personal_enrollment import PersonalChoices
        identity = next(i for i, o in self.c.track.originals.items() if o.issue.number == number)
        return PersonalChoices(number, self.c.track.root / "windows" / digest(identity), ("product",),
            branch="work/issue-" + str(number), checks=("unit",), accept_native_job_records=True)

    def advance(self, number):
        choices = self.next_choices(number)
        proposed = self.c.track.next_preview(self.product, choices)
        result = self.c.track.next(self.product, choices, reviewed=proposed["approval"],
            setup_approval=proposed["setup_approval"], authorized=True)
        self.assertEqual(result["status"], "NEXT_ENROLLED_SCOPE_REVIEW_REQUIRED")
        self.personal = load_state(Path(result["directory"]))
        self.runtime = CodexExecRuntime(self.personal.state / "runtime")
        caps = Capabilities("codex-exec", self.runtime.host, "SYNTHETIC_TEST_ONLY", True, True, True, True, 1)
        patch.object(self.runtime, "capabilities", return_value=caps).start()
        patch.object(self.runtime, "dispatch", side_effect=self.dispatch).start()
        p = self.personal.plan
        from adp.network_git import GitHubCAS
        target = GitHubTarget(self.rid, p["repository"]["node_id"], 17, *self.name.split("/"), p["feature"]["branch"])
        http = TrackTransport(self, self.store, target)
        service = GitHubCAS(target, http)
        service.bind_control(self.personal.memory().control)
        self.c = PersonalCoordinator(self.personal, PersonalProjectRead(service), NativePersonalReads(self), runtime=self.runtime, clock=lambda: self.now)
        identity = next(i for i, o in self.c.track.originals.items() if o.issue.number == number)
        self.runtime_by_identity[identity] = self.runtime
        self.http_by_identity[identity] = http
        self.track = self.c.track
        return result
