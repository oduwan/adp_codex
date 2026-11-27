"""Small seeded Product stages; synthetic approval seams, no Worker campaign."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json
import time

from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.guard_types import data
from adp.network_git import GitHubTarget, GitHubPolicyAdapter
from adp.policy import PolicyProvider
from adp.personal_enrollment import apply_personal
from adp.personal_history_product_git import administration
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductCoordinator
from adp.personal_publication import PersonalPublication
from adp.personal_storage import approval
from adp.personal_track import PersonalTrack
from adp.schema import key
from personal_fixtures import PersonalFixture
from personal_product_fixtures import ProductTransport
from test_config import run
from test_guard import SyntheticAuthority


class ProductWorkTests(PersonalFixture):
    def seeded(self, product_type=PersonalProduct, *, publication=False, ci_transport=None):
        """Seed an admitted, already reviewed SHA; do not pretend to run Codex."""
        self.now = int(time.time())
        plan, original, docs = self.plan(ci_transport=ci_transport)
        self.personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
            transport=self.transport, ci_transport=ci_transport, clock=lambda: self.now)
        run(self.a, "worktree", "add", "-b", plan["feature"]["branch"], str(self.personal.feature))
        self.c = ProductCoordinator(self.personal, self.transport, None, clock=lambda: int(time.time()))
        self.c.initialize_run()
        # Model an actual in-scope product commit, not a zero-diff PR that the
        # synthetic forge happens to accept. Canonical M1 follows that SHA.
        (self.personal.feature / "product").write_text("original task implementation\n")
        run(self.personal.feature, "add", "--", "product")
        run(self.personal.feature, "commit", "-m", plan["commit_message"], "-m", plan["commit_body"])
        revision = run(self.personal.feature, "rev-parse", "HEAD")
        self.assertNotEqual(revision, plan["checkout"]["head"])
        self.assertEqual(run(self.a, "rev-parse", "refs/heads/trunk"), plan["checkout"]["head"])
        self.assertEqual(run(self.a, "rev-parse", "refs/heads/" + plan["feature"]["branch"]), revision)
        self.assertEqual(run(self.personal.feature, "rev-parse", "HEAD^"), plan["checkout"]["head"])
        run(self.personal.feature, "merge-base", "--is-ancestor", plan["checkout"]["head"], revision)
        self.assertEqual(run(self.personal.feature, "diff", "--name-only", plan["checkout"]["head"], revision), "product")
        self.assertEqual(run(self.personal.feature, "status", "--porcelain"), "")
        self.c.memory.set_revision(self.c.task_id, revision)
        task = self.c.memory.inspect()["tasks"][key(self.c.task_id)]
        self.assertEqual(task["source_revision"], revision)
        row = self.c.record()
        row.update(phase="LOCAL_DRAFT_CODE_REVIEWED", revision=revision, developer="synthetic-author",
            feature_administration=administration(self.personal.feature))
        self.c.save(row)
        self.c.original_approval = Mock()
        self.c.verify_local_review = Mock()
        self.c.workers.fence = Mock()
        self.c.source_authors = lambda: ("worker:synthetic-author",)
        target = GitHubTarget(self.rid, plan["repository"]["node_id"], 17, *self.name.split("/"), plan["feature"]["branch"])
        self.http = ProductTransport(self, self.a, target)
        self.transport.api.responses[self.prefix].body.update(allow_merge_commit=True, allow_squash_merge=True)
        self.product = p = product_type(self.c, transport=self.http)
        def write():
            try:
                return p.write_authorized()
            except BaseException as exc:
                print("PRODUCT_WRITE_REFUSAL " + type(exc).__name__ + ": " + str(exc), flush=True)
                raise
        self.http.authorize_write = write
        final = p.final_boundary
        def boundary(**kwargs):
            try:
                return final(**kwargs)
            except BaseException as exc:
                print("PRODUCT_FINAL_REFUSAL " + type(exc).__name__ + ": " + str(exc), flush=True)
                raise
        p.final_boundary = boundary
        # Exact native first-Issue closure is empty; the other two originals
        # still carry #2 BLOCKED_BY #1 and #3 BLOCKED_BY #2 through actual M4.
        observed, _ = self.observe()
        track = PersonalTrack.__new__(PersonalTrack)
        track.c, track.personal = self.c, self.personal
        track.originals = {i.identity: SimpleNamespace(issue=i) for i in observed.snapshot.issues}
        track.root = self.personal.state
        track.link = {"identity": original["identity"]}
        track.seed = lambda: observed.snapshot
        track.require_attachment = Mock()  # Seeded attachment, not NEXT/enrollment qualification.
        track.accepted = Mock(side_effect=AssertionError("Issue1 has no accepted predecessor"))
        self.c.track = track
        authority = SyntheticAuthority()
        self.c.authority = p.guard.authority = self.c.guard.authority = p.forge.authority = authority
        p.proof = lambda purpose, subject, *args, **kwargs: authority.attest(subject, purpose)
        admitted = {"task_id": self.c.task_id, "identity": original["identity"],
            "workspace_key": digest(plan["administration"]), "admission": digest({"synthetic": "scope"}),
            "issue_digest": plan["original_digest"], "revision": row["revision"], "source_ref": target.ref,
            "product_iteration": task["iteration"], "kind": "PRODUCT", "stage": "PUBLISH", "jobs": {}, "review": None}
        if not publication:
            p.journal.change(lambda e, s, t: p.publication.admit_task(e, key(self.c.task_id), admitted))
        p.review_seal = Mock(return_value="independently-seeded-exact-review")
        return p

    def pr_stage(self, number=1):
        from dataclasses import replace
        self.choices = replace(self.choices, issue=number, branch="work/issue-" + str(number))
        p = self.seeded()
        from personal_product_fixtures import accepted_native_fixture
        accepted_native_fixture(self, p, number)
        body = "Refs #" + str(number)
        proposal = p.proposed("PR", title="Original task", body=body)
        calls = []
        actual = self.http.request
        def counted(method, path, body, *, seconds):
            calls.append((method, path))
            return actual(method, path, body, seconds=seconds)
        self.http.request = counted
        p.c.fresh = Mock(side_effect=AssertionError("No unrelated inventory inside intent"))
        plan, decide, inspect = PolicyProvider.plan, PolicyProvider.decide, GitHubPolicyAdapter.inspect
        with (patch.object(PolicyProvider, "plan", autospec=True, side_effect=plan) as plans,
              patch.object(PolicyProvider, "decide", autospec=True, side_effect=decide) as decisions,
              patch.object(GitHubPolicyAdapter, "inspect", autospec=True, side_effect=inspect) as inspections,
              patch.object(p, "facts", wraps=p.facts) as facts,
              patch.object(p, "original", wraps=p.original) as originals,
              patch.object(p.publication, "current_original", wraps=p.publication.current_original) as native_originals):
            result = p.intent("PR", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True, title="Original task", body=body)
            counts = {"plan": plans.call_count, "decide": decisions.call_count, "policy_inspect": inspections.call_count,
                "facts": facts.call_count, "original": originals.call_count, "current_original": native_originals.call_count,
                "fresh": p.c.fresh.call_count}
            self.assertEqual(counts, {"plan": 3, "decide": 1, "policy_inspect": 3,
                "facts": 3, "original": 2, "current_original": 2, "fresh": 0})
            print("PRODUCT_LOGICAL_CALLS " + json.dumps(counts, sort_keys=True), flush=True)
        self.assertEqual(result["status"], "PR_PRESENT")
        self.assertEqual(len(self.http.effects), 1)
        p.c.fresh.assert_not_called()
        records = list(p.service.measurements)
        print("PRODUCT_ISSUE " + str(number), flush=True)
        print("PRODUCT_STAGE_COSTS " + json.dumps(records, sort_keys=True), flush=True)
        print("PRODUCT_HTTP_CALLS " + json.dumps(calls), flush=True)
        self.assertLessEqual(len(calls), 128)
        self.assertLessEqual(records[-1]["transport_calls"], 112)
        self.assertFalse(any("/issues?state=" in path or "/pulls?state=all&per_page=" in path for _, path in calls))
        for future in range(number + 1, 4):
            self.assertFalse(any("/issues/" + str(future) in path for _, path in calls))

    def test_seeded_three_issue_pr_fits_original_budget(self):
        self.pr_stage()

    def test_second_original_pr_fits_original_budget(self):
        self.pr_stage(2)

    def test_third_original_pr_fits_original_budget(self):
        self.pr_stage(3)

    def test_final_m3_reobserves_permission_after_submitted_and_prevents_post(self):
        p = self.seeded()
        proposal = p.proposed("PR", title="Original task", body="Refs #1")
        inventories = 0
        def change(method, path):
            nonlocal inventories
            if method == "GET" and path.startswith(p.target.api + "/pulls?"):
                inventories += 1
                if inventories == 2:  # New consent first, then final pre-effect inventory.
                    self.http.server.permission = "READ"
        self.http.hook = change
        with self.assertRaises(ADPError):
            p.intent("PR", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True, title="Original task", body="Refs #1")
        self.assertGreaterEqual(inventories, 2)
        self.assertEqual(self.http.effects, [])
        intent = p.record()["intents"][0]
        action = p.journal.inspect()["state"]["execution"]["actions"][intent["action"]]
        self.assertEqual(action["status"], "SUBMITTED")
        self.assertEqual(self.http.pulls, [])

    def test_seeded_post_pr_ci_uses_native_exact_sha_and_one_cold_admission(self):
        """Seed only PR acceptance, then exercise the actual #21 CI stages."""
        from dataclasses import replace
        from adp.network_http import Response
        self.choices = replace(self.choices, checks=("unit",), accept_native_job_records=True)
        from personal_fixtures import NativePersonalReads
        p = self.seeded(ci_transport=NativePersonalReads(self))
        proposal = p.proposed("PR", title="Original task", body="Refs #1")
        row = p.initialize()
        action = digest({"personal-product": proposal["result"]})
        repository = {"id": 17, "node_id": p.target.node_id, "full_name": self.name}
        pull = {"id": 2010, "node_id": "PR-seeded", "number": 10, "html_url": "https://github.com/" + self.name + "/pull/10",
            "title": "Original task", "body": "Refs #1\n\n" + p.forge.marker(action), "draft": True,
            "state": "open", "merged": False, "head": {"sha": self.c.revision(), "ref": p.target.branch, "repo": repository},
            "base": {"sha": proposal["result"]["facts"]["base_sha"], "ref": "trunk", "repo": repository}}
        self.http.pulls.append(pull)
        row["pull"] = {"id": "2010", "node_id": "PR-seeded", "number": 10, "repository_id": self.rid, "url": pull["html_url"]}
        row["intents"].append({"view": proposal["result"], "approval": proposal["approval"], "binding": proposal["binding"],
            "action": action, "requirement": None, "reservation": None, "observation": None})
        p.save(row)
        request = self.http.request
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10))
        completed = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
        def current_checks(method, path, body, **kw):
            result = request(method, path, body, **kw)
            if "/check-runs?" in path:
                result_body = json.loads(result.body)
                for check in result_body["check_runs"]:
                    check["started_at"] = started
                    check["completed_at"] = completed
                raw = json.dumps(result_body).encode()
                self.http.last_response = result.status, raw, ()
                return Response(result.status, raw)
            return result
        self.http.request = current_checks
        preview = p.execution_preview("CI", accept_native=True)
        with patch.object(p, "local", wraps=p.local) as local, patch.object(p, "original", wraps=p.original) as originals:
            result = p.execute("CI", reviewed=preview["approval"], authorized=True, accept_native=True)
            print("PRODUCT_CI_STAGE_COSTS " + json.dumps(list(p.service.measurements), sort_keys=True), flush=True)
            self.assertEqual(result["status"], "PASS", result)
            self.assertTrue(result["qualified"])
            self.assertEqual(sum(call.kwargs.get("genuine", True) for call in local.call_args_list), 1)
            self.assertEqual(local.call_count, 2)  # Cold entry plus current nested M3 live fence.
            self.assertEqual(originals.call_count, 1)
        self.assertEqual(result["gate"]["request"]["revision"], self.c.revision())
        self.assertEqual(result["gate"]["request"]["pull"]["id"], "PR-seeded")
        self.assertEqual(self.c.record()["observations"], 1)
        retained = p.execute("CI", reviewed=preview["approval"], authorized=True, accept_native=True)
        self.assertEqual(retained["status"], "RETAINED_OBSERVATION")
        self.assertEqual(retained["freshness"], "NOT_REOBSERVED")
        self.assertEqual(self.c.record()["observations"], 1)
        self.assertEqual(self.http.effects, [])

