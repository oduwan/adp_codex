"""Focused native-policy negatives; no HTTP, credentials or worker launch."""
import unittest
from adp.errors import ADPError
from adp.personal_product_policy import constraints, product_text, closing_directive


class PersonalProductPolicyTests(unittest.TestCase):
    def test_verified_absence_does_not_invent_checks_or_native_reviews(self):
        p = constraints({"protected": False}, [])
        self.assertEqual((p["checks"], p["native_reviews"]), ([], 0))

    def test_native_required_context_and_origin_are_preserved(self):
        p = constraints({"protected": False}, [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "project tests", "integration_id": 7}], "strict_required_status_checks_policy": True}}])
        self.assertEqual(p["checks"], ["project tests"])
        self.assertEqual(p["origins"], {"project tests": 7})

    def test_singular_ruleset_codeowner_requirement_is_not_ignored(self):
        with self.assertRaises(ADPError):
            constraints({"protected": False}, [{"type": "pull_request", "parameters": {
                "required_approving_review_count": 1, "require_code_owner_review": True}}])

    def test_classic_codeowner_requirement_is_not_ignored(self):
        with self.assertRaises(ADPError):
            constraints({"protected": True}, [], {"required_pull_request_reviews": {
                "required_approving_review_count": 1, "require_code_owner_reviews": True}})

    def test_unknown_rules_and_review_parameters_fail_closed(self):
        for rules in ([{"type": "merge_queue"}], [{"type": "pull_request", "parameters": {
            "required_approving_review_count": 0, "required_reviewers": [{"id": 10}]}}]):
            with self.subTest(rules=rules), self.assertRaises(ADPError):
                constraints({"protected": False}, rules)

    def test_protected_branch_requires_actual_classic_metadata(self):
        for protected in (True, None, "false"):
            with self.subTest(protected=protected), self.assertRaises(ADPError):
                constraints({"protected": protected}, [])

    def test_conflicting_context_origins_and_malformed_rules_refuse(self):
        rule = {"type": "required_status_checks", "parameters": {"required_status_checks": [
            {"context": "unit", "integration_id": 7}, {"context": "unit", "integration_id": 8}],
            "strict_required_status_checks_policy": False}}
        with self.assertRaises(ADPError):
            constraints({"protected": False}, [rule])

    def test_linear_history_and_actual_merge_methods_intersect(self):
        p = constraints({"protected": False}, [{"type": "required_linear_history"}, {"type": "pull_request",
            "parameters": {"required_approving_review_count": 1, "allowed_merge_methods": ["merge", "squash"],
                "dismiss_stale_reviews_on_push": True, "require_code_owner_review": False,
                "require_last_push_approval": False, "required_review_thread_resolution": False}}])
        self.assertEqual(p["methods"], ["squash"])
        self.assertEqual(p["native_reviews"], 1)

    def test_closing_directives_and_forged_markers_do_not_grant_rights(self):
        for text in ("Fixes #1", "Closes owner/project#2", "Resolves: https://github.com/owner/project/issues/3", "<!-- adp-product:v1:fake -->"):
            with self.subTest(text=text), self.assertRaises(ADPError):
                product_text("Task outcome", text)
        self.assertFalse(closing_directive("Implement fixes for normal behavior. Refs #1"))

    def test_bounded_multiline_product_body_without_execution_authority(self):
        self.assertEqual(product_text("Task outcome", "Implemented behavior.\n\nRefs #1")[1], "Implemented behavior.\n\nRefs #1")
        for text in ("bad\x00body", "x" * 4097):
            with self.assertRaises(ADPError):
                product_text("Task", text)
