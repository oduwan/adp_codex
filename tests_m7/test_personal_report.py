"""Product-comment identity, least authority and actual-component recovery."""
import copy
from dataclasses import replace
from types import SimpleNamespace
import unittest

from adp.discovery_github import API, _author, _id, _issue_revision, inferred
from adp.discovery_github import Response
from adp.discovery_schema import digest
from adp.discovery_types import Identity, Issue, Relation, Target, Text
from adp.errors import ADPError
from adp.execution_github import GitHubForgeBackend
from adp.execution_types import ExternalObservation
from adp.personal_report import PersonalReport, own_report_delta
from adp.personal_report_child import validate_report
from personal_track_fixtures import TrackFixture


class PersonalReportReceiptTests(unittest.TestCase):
    def comment(self):
        return {"id": 500, "node_id": "IC_opaque", "user": {"id": 91, "node_id": "U_opaque"},
            "body": "Implemented the original behavior.", "created_at": "2026-11-09T08:00:01Z", "updated_at": "2026-11-09T08:00:01Z",
            "html_url": "https://github.com/personal/project/issues/2#issuecomment-500",
            "issue_url": API + "/repos/personal/project/issues/2"}

    def test_opaque_comment_and_author_delta_preserves_original_native_dependencies(self):
        raw = {"id": 1002, "node_id": "I2", "number": 2, "url": API + "/repos/personal/project/issues/2",
            "title": "Original", "body": "Original acceptance", "state": "open", "state_reason": None,
            "updated_at": "2026-11-09T08:00:00Z", "user": {"id": 71, "node_id": "U_original"}, "labels": [], "assignees": []}
        edge = Relation("BLOCKED_BY", Target("personal/project", 1, "I1"), "NATIVE", "native:source")
        before = Issue(Identity("17", "I2"), 2, "https://github.com/personal/project/issues/2", raw["title"], raw["body"],
            "open", None, raw["updated_at"], _issue_revision(raw), (), (), ("github-user:U_original",), (), (edge,))
        comment = self.comment()
        raw = dict(raw, updated_at=comment["created_at"])
        text = Text(_id(comment), comment["body"], _author(comment), comment["updated_at"],
            API + "/repos/personal/project/issues/2/comments#" + _id(comment))
        after = replace(before, updated_at=raw["updated_at"], revision=_issue_revision(raw), comments=(text,),
            authors=tuple(sorted((*before.authors, text.author))))
        self.assertTrue(own_report_delta(before, after, comment, raw))
        for changed in (replace(after, body="Extra unapproved scope"), replace(after, relations=()),
                replace(after, comments=(replace(text, body="Changed product claim"),)), replace(after, revision="0" * 64)):
            with self.subTest(changed=changed.revision), self.assertRaises(ADPError):
                own_report_delta(before, changed, comment, raw)
        wrong = dict(raw, updated_at="2026-11-09T08:00:02Z")
        with self.assertRaises(ADPError):
            own_report_delta(before, after, comment, wrong)

    def test_exact_report_identity_foreign_actor_alias_and_split_inventory_fail_closed(self):
        f = object.__new__(PersonalReport)
        owner = {"account_id": 91, "repository_id": "17", "read_access": True, "push_access": True, "admin_access": True}
        metadata = {"id": 17, "node_id": "R_opaque", "full_name": "personal/project", "owner": {"id": 91, "type": "User"},
            "permissions": {"pull": True, "push": True, "admin": True}}
        f.personal = SimpleNamespace(repository_id="17", plan={"issue": 2, "owner": owner})
        f.target = SimpleNamespace(api="/repos/personal/project", node_id="R_opaque")
        f.service = SimpleNamespace(unconfirmed_contexts=lambda: (), request=lambda *args: metadata)
        f.read = SimpleNamespace(get=lambda path: Response(200, {"id": 91} if path == "/user" else metadata))
        row = {"action": "a" * 64, "view": {"body": "Implemented the original behavior.", "revision": "b" * 40}, "comment": None}
        comment = self.comment()
        comment["body"] = row["view"]["body"] + "\n\n" + GitHubForgeBackend.marker(row["action"])
        present = ExternalObservation("PRESENT", comment["html_url"], row["view"]["revision"], digest(row["view"]["body"]))
        f.journal = SimpleNamespace(inspect=lambda: {"state": {"execution": {"actions": {row["action"]:
            {"payload": {"target": "https://github.com/personal/project/issues/2", "body": row["view"]["body"], "revision": row["view"]["revision"]}}}}}})
        inventory, observed = [comment], present
        f.forge = SimpleNamespace(repository="personal/project", marker=GitHubForgeBackend.marker,
            inventory=lambda *args: inventory, observe=lambda *args, **kwargs: observed)
        self.assertEqual(f.observed_report(row)[1]["node_id"], "IC_opaque")
        controls = [dict(comment, id=True), dict(comment, user={"id": 91.0, "node_id": "U_opaque"}),
            dict(comment, user={"id": 92, "node_id": "U_foreign"}), dict(comment, node_id=False),
            dict(comment, html_url="https://github.com/personal/project/issues/3#issuecomment-500"),
            dict(comment, issue_url=API + "/repos/foreign/project/issues/2"), dict(comment, created_at=None),
            dict(comment, body="Different body")]
        for changed in controls:
            inventory = [changed]
            with self.subTest(fields=sorted(changed)), self.assertRaises((ADPError, ValueError)):
                f.observed_report(row)
        for changed in (None, [comment, copy.deepcopy(comment)]):
            inventory = changed
            with self.assertRaises(ADPError):
                f.observed_report(row)
        inventory = [comment]
        for changed in (replace(present, reference=comment["html_url"] + "0"), replace(present, revision="c" * 40),
                replace(present, body_digest="d" * 64)):
            observed = changed
            with self.assertRaises(ADPError):
                f.observed_report(row)

    def test_report_transport_cannot_create_pr_merge_upload_or_expand_request_bounds(self):
        validate_report("POST", "/repos/personal/project/issues/2/comments", {"body": "Exact outcome"}, 5)
        for method, path, body, seconds in (
            ("POST", "/repos/personal/project/pulls", {"body": "x"}, 5),
            ("PUT", "/repos/personal/project/pulls/10/merge", {"sha": "a" * 40, "merge_method": "merge"}, 5),
            ("POST", "/repos/personal/project/git/blobs", {"content": "x", "encoding": "utf-8"}, 5),
            ("PATCH", "/repos/personal/project/issues/2", {"state": "closed"}, 5),
            ("POST", "/graphql", {"query": "mutation { closeIssue }", "variables": {}}, 5),
            ("POST", "/repos/personal/project/issues/2/comments", {"body": "x"}, 6)):
            with self.subTest(method=method, path=path), self.assertRaises((ADPError, ValueError, TypeError)):
                validate_report(method, path, body, seconds)


class PersonalReportFlowTests(TrackFixture):
    def test_one_lost_response_report_reconciles_exact_original_without_duplicate_or_budget_reset(self):
        self.enroll_track()
        accepted = self.merged()
        report = PersonalReport(self.c, transport=self.http)
        self.http.authorize_write = report.write_authorized
        proposed = report.report_preview()
        before = self.c.memory.inspect()
        with self.assertRaises(ADPError):
            report.report(reviewed=proposed["approval"], authorized=False, authorize_memory=True,
                assume_quiescence=True, confirm_rules=True)
        self.assertEqual(before, self.c.memory.inspect())
        self.assertEqual(self.all_comments, [])
        self.http.report_loss = "after"
        result = report.report(reviewed=proposed["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True)
        self.assertEqual(result["status"], "REPORTED")
        self.assertEqual(len(self.all_comments), 1)
        state = self.c.memory.inspect()
        again = report.report(reviewed=proposed["approval"], authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True)
        self.assertEqual(again["reference"], result["reference"])
        self.assertEqual(len(self.all_comments), 1)
        self.assertEqual(state["state"]["progress_guard"], self.c.memory.inspect()["state"]["progress_guard"])
        self.assertEqual(len([row for row in self.http.effects if row[1].endswith("/comments")]), 1)
        self.assertIn(accepted["source"], self.all_comments[0]["body"])
        self.assertNotIn("SYNTHETIC", self.all_comments[0]["body"])
        self.assertEqual(self.c.track.status(transport=self.http)[0]["next_issue"], 2)
        identity = next(i for i, original in self.c.track.originals.items() if original.issue.number == 1)
        with self.assertRaises(ADPError):
            self.c.track.original_issue(identity, self.c.track.originals[identity].issue)
