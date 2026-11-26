"""Small seeded Product stages; synthetic approval seams, no Worker campaign."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json
import time

from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.guard_types import data
from adp.network_git import GitHubTarget
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
    def seeded(self, product_type=PersonalProduct):
        """Seed an admitted, already reviewed SHA; do not pretend to run Codex."""
        self.now = int(time.time())
        plan, original, docs = self.plan()
        self.personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
            transport=self.transport, clock=lambda: self.now)
        run(self.a, "worktree", "add", "-b", plan["feature"]["branch"], str(self.personal.feature))
        self.c = ProductCoordinator(self.personal, self.transport, None, clock=lambda: int(time.time()))
        self.c.initialize_run()
        row = self.c.record()
        row.update(phase="LOCAL_DRAFT_CODE_REVIEWED", revision=plan["checkout"]["head"], developer="synthetic-author",
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
        def boundary():
            try:
                return final()
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
            "product_iteration": 1, "kind": "PRODUCT", "stage": "PUBLISH", "jobs": {}, "review": None}
        p.journal.change(lambda e, s, t: p.publication.admit_task(e, key(self.c.task_id), admitted))
        p.review_seal = Mock(return_value="independently-seeded-exact-review")
        return p

    def test_seeded_three_issue_pr_fits_original_budget(self):
        p = self.seeded()
        proposal = p.proposed("PR", title="Original task", body="Refs #1")
        calls = []
        actual = self.http.request
        def counted(method, path, body, *, seconds):
            calls.append((method, path))
            return actual(method, path, body, seconds=seconds)
        self.http.request = counted
        before = len(self.http.server.calls)
        p.c.fresh = Mock(side_effect=AssertionError("No unrelated inventory inside intent"))
        result = p.intent("PR", reviewed=proposal["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True, title="Original task", body="Refs #1")
        self.assertEqual(result["status"], "PR_PRESENT")
        self.assertEqual(len(self.http.effects), 1)
        p.c.fresh.assert_not_called()
        records = list(p.service.measurements)
        print("PRODUCT_STAGE_COSTS " + json.dumps(records, sort_keys=True), flush=True)
        print("PRODUCT_HTTP_CALLS " + json.dumps(calls), flush=True)
        self.assertLessEqual(len(calls), 128)
        self.assertFalse(any("/issues?state=" in path or "/pulls?state=all&per_page=" in path for _, path in calls))
        self.assertFalse(any("/issues/2" in path or "/issues/3" in path for _, path in calls))

