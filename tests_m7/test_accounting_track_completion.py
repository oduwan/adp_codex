"""Focused v2 predecessor acceptance through existing synthetic M7 ports only."""
import json
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

from adp.discovery_schema import digest
from adp.network_git import GitHubTarget, GitHubCAS
from adp.network_http import Response
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductCoordinator
from adp.personal_publication import PersonalPublication
from adp.personal_storage import read_private
from adp.personal_storage import load_state
from adp.personal_enrollment import PersonalChoices
from adp.personal_product_http import PersonalProjectRead
from adp.personal_runner import PersonalCoordinator
from adp.codex_runtime import CodexExecRuntime
from adp.execution_types import Capabilities
from adp.git import git, value
from adp.errors import ADPError
from accounting_fixtures import AccountingFixture
from personal_track_fixtures import TrackTransport
import test_personal_accounting as candidate_flow


class AccountingTransport(TrackTransport):
    def request(self, method, path, body, *, seconds):
        response = super().request(method, path, body, seconds=seconds)
        if method == "GET" and path.partition("?")[0].endswith("/check-runs"):
            result = json.loads(response.body)
            for row in result["check_runs"]:
                row.update(name="tests", started_at=datetime.fromtimestamp(self.f.now - 5, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    completed_at=datetime.fromtimestamp(self.f.now - 1, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            response = Response(response.status, json.dumps(result).encode())
            self.last_response = (response.status, response.body, ())
        return response


class AccountingTrackCompletionTests(AccountingFixture):
    def enroll_next(self, number):
        identity = next(i for i, o in self.c.track.originals.items() if o.issue.number == number)
        choices = PersonalChoices(number, self.c.track.root / "windows" / digest(identity), ("product",),
            branch="work/issue-" + str(number), checks=("tests",), accept_native_job_records=True)
        proposal = self.c.track.next_preview(self.product, choices)
        result = self.c.track.next(self.product, choices, reviewed=proposal["approval"],
            setup_approval=proposal["setup_approval"], authorized=True)
        self.assertEqual(result["status"], "NEXT_ENROLLED_SCOPE_REVIEW_REQUIRED")
        self.personal = load_state(Path(result["directory"]))
        self.runtime = CodexExecRuntime(self.personal.state / "runtime")
        patch.object(self.runtime, "capabilities", return_value=Capabilities("codex-exec", self.runtime.host,
            "SYNTHETIC_NOT_GENUINE_RUNTIME", True, True, True, True, 1)).start()
        patch.object(self.runtime, "dispatch", side_effect=self.dispatch).start()
        p = self.personal.plan
        target = GitHubTarget(self.rid, p["repository"]["node_id"], 17, *self.name.split("/"), p["feature"]["branch"])
        self.http = AccountingTransport(self, self.store, target)
        service = GitHubCAS(target, self.http)
        service.bind_control(self.personal.memory().control)
        self.c = PersonalCoordinator(self.personal, PersonalProjectRead(service), self.native, runtime=self.runtime, clock=lambda: self.now)
        return identity

    def synchronize(self, merge):
        git(self.a, "fetch", "--no-tags", "--no-write-fetch-head", str(self.store), merge)
        git(self.a, "merge", "--ff-only", merge)
        self.transport.api.responses[self.prefix + "/branches/trunk"].body["commit"] = {"sha": merge}

    def test_only_full_fresh_merged_accepted_successor_unblocks_the_native_chain(self):
        # Reuse the focused real-port synthetic candidate procedure, never a
        # fake Developer PASS or fabricated accepted-completion receipt.
        candidate_flow.AccountingCandidateTests.test_scope_then_explicit_candidate_copy_and_fresh_staged_sha_reviews(self)
        source = self.c.revision()
        self.store = self.base / "owned-synthetic-forge.git"
        self.store.mkdir()
        git(self.store, "init", "--bare", "--initial-branch=trunk")
        git(self.store, "fetch", "--no-tags", "--no-write-fetch-head", "--no-auto-maintenance", str(self.a), self.personal.plan["checkout"]["head"])
        git(self.store, "update-ref", "refs/heads/trunk", self.personal.plan["checkout"]["head"])
        self.all_pulls, self.all_comments = [], []
        p = self.personal.plan
        target = GitHubTarget(self.rid, p["repository"]["node_id"], 17, *self.name.split("/"), p["feature"]["branch"])
        self.http = AccountingTransport(self, self.store, target)
        self.transport.api.responses[self.prefix].body.update(allow_merge_commit=True, allow_squash_merge=True)
        pub = PersonalPublication(self.c, transport=self.http)
        self.http.authorize_write = pub.write_authorized
        proposed = pub.preview()
        self.assertEqual(pub.publish(reviewed=proposed["approval"], authorized=True, assume_quiescence=True,
            confirm_project_rules=True)["status"], "PUBLISHED_UNACCEPTED")
        self.c = ProductCoordinator(self.personal, self.transport, self.native, runtime=self.runtime, clock=lambda: self.now)
        product = PersonalProduct(self.c, transport=self.http)
        self.product = product
        self.http.authorize_write = product.write_authorized
        identity = next(i for i, o in self.c.track.originals.items() if o.issue.number == 1)
        self.assertIsNone(self.c.track.accepted(identity))
        proposal = product.proposed("PR", title="Complete the original Issue", body="Implement the admitted scope. Refs #1")
        product.intent("PR", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True, title=proposal["result"]["title"], body=proposal["result"]["body"])
        self.assertIsNone(self.c.track.accepted(identity))
        for purpose in ("CI", "REVIEW"):
            proposal = product.execution_preview(purpose, accept_native=purpose == "CI")
            result = product.execute(purpose, reviewed=proposal["approval"], authorized=True, accept_native=purpose == "CI")
            self.assertEqual(result["status"], "PASS" if purpose == "CI" else "PRODUCT_REVIEWED")
        self.assertIsNone(self.c.track.accepted(identity))
        self.http.pulls[0]["draft"] = False  # Separate synthetic project actor.
        proposal = product.proposed("MERGE", method="merge", delegate=True)
        product.intent("MERGE", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True, method="merge", delegate=True, accept_envelope=True)
        self.assertIsNone(self.c.track.accepted(identity))
        proposal = self.c.track.completion_preview(product)
        receipt = self.c.track.complete(product, reviewed=proposal["approval"], authorized=True, confirm_acceptance=True)
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["source"], source)
        self.assertEqual(receipt["origin"]["kind"], "RETAINED_UNACCEPTED")
        self.assertEqual(len(self.requests), 6)
        _, token = self.c.invocation("handoff")
        self.c.run(reviewed=token, authorized=True, operation="handoff")
        self.now = p["window"]["expires_at"] + 1
        self.assertEqual(self.c.track.accepted(identity, transport=self.http), receipt)
        state = self.c.track.status(transport=self.http)[0]
        self.assertEqual(state["next_issue"], 2)
        self.assertEqual(next(r for r in state["issues"] if r["issue"] == 3)["status"], "BLOCKED_DEPENDENCY")
        self.assertEqual(read_private(self.original_personal.state / "workers" / (self.recovery.master()["request"] + ".json"))["phase"], "STOPPED")
        # Continue only after real-port synthetic accepted completion, owner
        # release and explicit new-original admission. No M8 worker is launched.
        self.synchronize(receipt["merge"])
        second = self.enroll_next(2)
        self.check_root = self.personal.feature
        _, token = self.c.invocation()
        self.assertEqual(self.c.run(reviewed=token, authorized=True)["status"], "LOCAL_DRAFT_CODE_REVIEWED")
        pub = PersonalPublication(self.c, transport=self.http)
        self.http.authorize_write = pub.write_authorized
        proposal = pub.preview()
        pub.publish(reviewed=proposal["approval"], authorized=True, assume_quiescence=True, confirm_project_rules=True)
        self.c = ProductCoordinator(self.personal, self.c.transport, self.native, runtime=self.runtime, clock=lambda: self.now)
        self.product = PersonalProduct(self.c, transport=self.http)
        self.http.authorize_write = self.product.write_authorized
        proposal = self.product.proposed("PR", title="Complete original Issue 2", body="Admitted scope only. Refs #2")
        self.product.intent("PR", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True, title=proposal["result"]["title"], body=proposal["result"]["body"])
        for purpose in ("CI", "REVIEW"):
            proposal = self.product.execution_preview(purpose, accept_native=purpose == "CI")
            self.product.execute(purpose, reviewed=proposal["approval"], authorized=True, accept_native=purpose == "CI")
        next(p for p in self.all_pulls if p["head"]["ref"] == self.product.target.branch)["draft"] = False
        proposal = self.product.proposed("MERGE", method="merge", delegate=True)
        self.product.intent("MERGE", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True, method="merge", delegate=True, accept_envelope=True)
        proposal = self.c.track.completion_preview(self.product)
        second_receipt = self.c.track.complete(self.product, reviewed=proposal["approval"], authorized=True, confirm_acceptance=True)
        self.assertEqual(second_receipt["schema_version"], 1)
        self.assertEqual(self.c.track.status(transport=self.http)[0]["next_issue"], 3)
        self.synchronize(second_receipt["merge"])
        # Installed normal CLI supplies GET-only PersonalGitHubRead, not the
        # service wrapper used above. Its existing native read port must be
        # selected BEFORE effective historical episode resolution.
        from adp.cli import parser
        from adp.personal_cli import run as personal_cli
        args = parser().parse_args(["personal", "track-status", "--repo", str(self.a), "--remote", "forge",
            "--directory", str(self.personal.directory)])
        with patch("adp.personal_product_http.PersonalProductTransport", return_value=self.http) as selected:
            report, exit_code = personal_cli(args, transport=self.transport, runtime=self.runtime, clock=lambda: self.now)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["result"]["next_issue"], 3)
        selected.assert_called_once()
        # Original archival proof now observes the exact accepted later merge;
        # no cached first-Issue success substitutes for the normal v1 evidence.
        from adp.personal_history_track import READ_TRANSPORT
        from adp.personal_history import archived
        from adp.personal_storage import PersonalBlocked
        with self.assertRaises(PersonalBlocked) as unavailable:
            archived(self.original_personal)
        self.assertEqual(unavailable.exception.reason, "HISTORICAL_NATIVE_READ_REQUIRED")
        binding = READ_TRANSPORT.set(self.http)
        try:
            archived(self.original_personal)
            git(self.a, "update-ref", "refs/heads/unadmitted-negative", second_receipt["merge"])
            with self.assertRaises(ADPError):archived(self.original_personal)
            git(self.a, "update-ref", "-d", "refs/heads/unadmitted-negative")
        finally:
            READ_TRANSPORT.reset(binding)
        third = self.enroll_next(3)
        self.assertNotEqual(second, third)
        self.assertIsNone(self.c.record())
        self.assertEqual(len(self.requests), 11)
