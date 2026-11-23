"""Own publication observations cannot rewrite the admitted original ticket."""
from dataclasses import replace
import unittest

from adp.discovery_types import Identity, Issue, Relation, Target
from adp.errors import ADPError
from adp.guard_types import data
from adp.personal_product_review import original_with_own_relation


class PersonalProductRelationTests(unittest.TestCase):
    def setUp(self):
        self.issue = Issue(Identity("17", "I_original"), 1, "https://github.com/owned/project/issues/1",
            "Original scope", "Original acceptance", "open", None, "2026-11-09T08:00:00Z", "a" * 64,
            (), (), ("github-user:91",), (), ())
        self.pull = {"id": "2010", "node_id": "PR_actual", "number": 10}
        self.edge = Relation("PULL_REQUEST", Target("owned/project", 10, "PR_actual"), "NATIVE",
            "https://api.github.com/repos/owned/project/issues/1/timeline#" + "b" * 64)

    def test_only_new_exact_own_native_pr_link_is_reconciled(self):
        current = replace(self.issue, relations=(self.edge,))
        self.assertEqual(original_with_own_relation(data(self.issue), current, self.pull, "owned/project"), [data(self.edge)])
        self.assertEqual(self.issue.relations, ())
        self.assertEqual(current.relations, (self.edge,))

    def test_scope_version_foreign_links_and_lost_previous_evidence_refuse(self):
        for edge in (replace(self.edge, confidence="INFERRED"), replace(self.edge, kind="BLOCKED_BY"),
            replace(self.edge, target=Target("foreign/project", 10, "PR_actual")),
            replace(self.edge, target=Target("owned/project", 11, "PR_actual")),
            replace(self.edge, target=Target("owned/project", 10, "2010"))):
            with self.subTest(edge=edge), self.assertRaises(ADPError):
                original_with_own_relation(data(self.issue), replace(self.issue, relations=(edge,)), self.pull, "owned/project")
        for changed in (replace(self.issue, title="Extra functionality"), replace(self.issue, updated_at="2026-11-10T08:00:00Z"),
            replace(self.issue, revision="c" * 64)):
            with self.subTest(issue=changed), self.assertRaises(ADPError):
                original_with_own_relation(data(self.issue), replace(changed, relations=(self.edge,)), self.pull, "owned/project")
        previous = replace(self.issue, relations=(replace(self.edge, target=Target("owned/project", 8, "PR_prior")),))
        with self.assertRaises(ADPError):
            original_with_own_relation(data(previous), replace(self.issue, relations=(self.edge,)), self.pull, "owned/project")
