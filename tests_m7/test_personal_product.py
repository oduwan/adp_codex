"""Full actual personal/M1/M2/M3/M7/#21 composition; SYNTHETIC runtime/API."""
from dataclasses import replace
import json
from unittest.mock import patch

from adp.errors import ADPError
from adp.guard_types import DecisionKind
from adp.schema import key
from personal_product_fixtures import ProductFixture
from network_fixtures import gv


class PersonalProductTests(ProductFixture):
    def test_wrong_repository_permissions_published_head_base_and_expiry_refuse(self):
        f = self.product_ready()
        p = f.proposed("PR", title="Original task", body="Refs #1")
        repo = self.transport.api.responses[self.prefix].body
        initial_refs = self.http.server.refs
        for field, changed in (("id", 18), ("default_branch", "other"), ("permissions", {"pull": True, "push": False, "admin": True})):
            original = repo[field]
            repo[field] = changed
            with self.subTest(field=field), self.assertRaises(ADPError):
                f.intent("PR", reviewed=p["approval"], authorized=True, authorize_memory=True,
                    assume_quiescence=True, confirm_rules=True, title="Original task", body="Refs #1")
            repo[field] = original
        for ref in (f.target.ref, "refs/heads/trunk"):
            changed_refs = {**initial_refs(), ref: "b" * 40}
            with patch.object(self.http.server, "refs", return_value=changed_refs), self.subTest(ref=ref), self.assertRaises(ADPError):
                f.intent("PR", reviewed=p["approval"], authorized=True, authorize_memory=True,
                    assume_quiescence=True, confirm_rules=True, title="Original task", body="Refs #1")
        self.assertEqual(self.http.effects, [])
        self.assertIsNone(f.record())
        self.now = p["result"]["expires_at"]
        with self.assertRaises(ADPError):
            f.intent("PR", reviewed=p["approval"], authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True, title="Original task", body="Refs #1")
        self.assertEqual(self.http.effects, [])

    def test_one_pr_lost_ack_independent_review_manual_default_and_verified_merge(self):
        f = self.product_ready()
        p = self.create_pr(loss="after")
        identity = f.record()["pull"]
        self.assertNotEqual(identity["id"], identity["node_id"])
        writes = len(self.http.effects)
        self.assertEqual(f.intent("PR", reviewed=p["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True)["status"], "PR_PRESENT")
        self.assertEqual(len(self.http.effects), writes)
        from copy import deepcopy
        alternate = deepcopy(self.http.pulls[0]); alternate.update(id=9999, number=99)
        self.http.pulls.append(alternate)
        with self.assertRaisesRegex(ADPError, "duplicate source PR"):
            f.pull()
        self.http.pulls.pop()
        approved_body = self.http.pulls[0]["body"]
        self.http.pulls[0]["body"] = "Closes #1"
        with self.assertRaisesRegex(ADPError, "PR text differs"):
            f.pull()
        self.http.pulls[0]["body"] = approved_body
        with self.assertRaises(ADPError):
            f.intent("PR", reviewed=p["approval"], authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True, title="Changed unapproved title")
        unknown = self.execute_product("CI")
        self.assertEqual(unknown["status"], "UNKNOWN")
        result = self.execute_product("CI", confirm_no_checks=True)
        self.assertEqual(result["status"], "NOT_REQUIRED")
        self.assertFalse(result["qualified"])
        proposal = f.execution_preview("REVIEW")
        with patch.object(self.c.workers, "finish", side_effect=OSError("synthetic interrupted review accounting")):
            with self.assertRaisesRegex(OSError, "interrupted review accounting"):
                f.execute("REVIEW", reviewed=proposal["approval"], authorized=True)
        pending = [r for r in self.c.workers.records() if r["purpose"] == "product"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["phase"], "STOPPED")
        requirement = pending[0]["requirement"]
        sequence = self.c.guard._snapshot(self.c.task_id, requirement)[2]["sequence"]
        before = len(self.c.workers.records())
        self.assertEqual(f.execute("REVIEW", reviewed=proposal["approval"], authorized=True)["status"], "PRODUCT_REVIEWED")
        self.assertEqual(len(self.c.workers.records()), before)
        self.assertEqual(self.c.guard._snapshot(self.c.task_id, requirement)[2]["sequence"], sequence)
        waiting = f.proposed("MERGE", method="merge", delegate=True)
        self.assertEqual(waiting["status"], "WAITING_HUMAN_APPROVAL")
        self.assertIsNone(waiting["approval"])
        self.http.pulls[0]["draft"] = False  # Explicit separately external actor, not ADP readiness.
        manual = f.proposed("MERGE", method="merge")
        self.assertEqual(manual["status"], "WAITING_HUMAN_APPROVAL")
        with self.assertRaises(ADPError):
            self.merge_product(manual)
        approved = f.proposed("MERGE", method="merge", delegate=True)
        self.http.loss = "after"
        merged = self.merge_product(approved)
        self.assertEqual(merged["status"], "MERGED_DELEGATED_VERIFIED")
        self.assertEqual(gv(self.store, "rev-parse", "refs/heads/trunk"), merged["revision"])
        self.assertEqual(f.status()["status"], "MERGED_DELEGATED_VERIFIED")
        self.assertEqual([m for m, _, _ in self.http.effects], ["POST", "PUT"])
        self.assertEqual(len({r["observation"]["context_id"] for r in self.c.workers.records()}), 5)
        state = self.c.memory.inspect()["state"]
        self.assertEqual(state["execution"]["schema_version"], 2)
        self.assertEqual(state["execution"]["tasks"][key(self.c.task_id)]["jobs"], {})
        self.assertEqual(self.c.guard._snapshot(self.c.task_id, self.c.requirement("develop"))[2]["unresolved"], [])
        self.assertEqual(merged["runtime_qualification"], "NOTRUN")

    def test_actual_post_pr_native_ci_uses_opaque_identity_and_fresh_merge_check(self):
        self.choices = replace(self.choices, checks=("unit",), accept_native_job_records=True)
        f = self.product_ready()
        self.create_pr()
        result = self.execute_product("CI", accept_native=True)
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(result["qualified"])
        gate = result["gate"]
        self.assertEqual(gate["request"]["pull"]["id"], self.http.pulls[0]["node_id"])
        self.assertIsNone(gate["results"][0]["denominator"])
        self.assertIsNone(gate["results"][0]["attempt_id"])
        self.assertEqual(gate["results"][0]["counts"], [])
        # The own native cross-reference may appear after creating this PR.
        from adp.discovery_github import Response
        pull = self.http.pulls[0]
        event = {"event": "cross-referenced", "source": {"issue": {"node_id": pull["node_id"],
            "id": pull["id"], "number": pull["number"], "url": pull["url"], "pull_request": {}}}}
        self.transport.api.responses[self.prefix + "/issues/1/timeline?per_page=100&page=1"] = Response(200, [event])
        self.assertEqual(self.execute_product("REVIEW")["status"], "PRODUCT_REVIEWED")
        self.assertEqual(len(self.c.original_relation_delta), 1)
        self.http.pulls[0]["draft"] = False
        approved = f.proposed("MERGE", method="merge", delegate=True)
        self.assertEqual(self.merge_product(approved)["status"], "MERGED_DELEGATED_VERIFIED")
        self.assertEqual(self.c.record()["observations"], self.personal.plan["window"]["maximum_check_observations"])
        self.assertEqual(len([e for e in f.record()["execution"] if e["view"]["operation"] == "CI"]), 2)

    def test_lost_undelivered_pr_and_missing_history_never_repeat_post(self):
        f = self.product_ready()
        p = f.proposed("PR", title="Original task", body="Refs #1")
        self.http.loss = "before"
        with self.assertRaises(ADPError):
            f.intent("PR", reviewed=p["approval"], authorized=True, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True, title="Original task", body="Refs #1")
        self.assertEqual(len(self.http.effects), 1)
        self.assertEqual(self.http.pulls, [])
        original = f.record()["intents"][0]
        action = f.journal.inspect()["state"]["execution"]["actions"][original["action"]]
        self.assertEqual(action["status"], "SUBMITTED")
        self.http.loss = None
        for title in ("Original task", "Changed title"):
            with self.subTest(title=title), self.assertRaises(ADPError):
                self.reconnect_product().intent("PR", reviewed=p["approval"], authorized=True, authorize_memory=True,
                    assume_quiescence=True, confirm_rules=True, title=title, body="Refs #1")
        self.assertEqual(len(self.http.effects), 1)
        f.path.unlink()
        with self.assertRaises(ADPError):
            self.reconnect_product().record()
        self.assertEqual(len(self.http.effects), 1)

    def test_failed_ci_correction_preserves_counters_review_and_one_pr(self):
        self.choices = replace(self.choices, checks=("unit",), accept_native_job_records=True)
        f = self.product_ready()
        self.create_pr()
        old_sha, old_review = self.c.revision(), self.c.record()["code_review"]
        self.http.conclusion = "failure"
        failed = self.execute_product("CI", accept_native=True)
        self.assertEqual(failed["status"], "FAIL")
        self.assertIsNone(f.record()["review"])
        base_dispatch = self.dispatch
        def correction(request):
            observed = base_dispatch(request)
            context = json.loads(request.prompt.split("\n", 1)[1])
            if context["purpose"] == "develop":
                from pathlib import Path
                from adp.execution_containment import source_seal
                (Path(request.workspace) / "product").write_text("corrected original ticket\n")
            return observed
        self.runtime.dispatch.side_effect = correction
        result = self.execute_product("CORRECT")
        self.assertEqual(result["status"], "CORRECTED_REQUIRES_NEW_PUBLICATION")
        self.assertNotEqual(self.c.revision(), old_sha)
        self.assertNotEqual(self.c.record()["code_review"], old_review)
        self.assertEqual(self.c.record()["observations"], 2)
        pub = f.publication_backend(transport=self.http)
        self.http.authorize_write = pub.write_authorized
        proposal = pub.preview()
        published = pub.publish(reviewed=proposal["approval"], authorized=True, assume_quiescence=True, confirm_project_rules=True)
        self.assertEqual(published["status"], "PUBLISHED_UNACCEPTED")
        self.product = f = self.reconnect_product()
        self.http.conclusion = "success"
        self.assertEqual(self.execute_product("CI", accept_native=True)["status"], "PASS")
        self.assertEqual(len(self.http.pulls), 1)
        self.assertEqual(sum(method == "POST" for method, _, _ in self.http.effects), 1)
        with self.assertRaisesRegex(ADPError, "role budget"):
            self.execute_product("REVIEW")
        roles = [r["purpose"] for r in self.c.workers.records()]
        self.assertEqual(roles.count("develop"), 2)
        self.assertEqual(roles.count("code"), 2)
        self.assertEqual(roles.count("product"), 0)
        self.assertEqual(self.c.record()["observations"], 3)
        self.assertEqual(f.record()["gates"][0]["status"], "FAIL")
        self.assertFalse(any(m == "PUT" for m, _, _ in self.http.effects))
