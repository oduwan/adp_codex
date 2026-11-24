"""Focused v2 predecessor acceptance through existing synthetic M7 ports only."""
import json
from datetime import datetime, timezone

from adp.discovery_schema import digest
from adp.network_git import GitHubTarget
from adp.network_http import Response
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductCoordinator
from adp.personal_publication import PersonalPublication
from adp.personal_storage import read_private
from adp.git import git, value
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
