"""Prospective policy, recorded feedback and legacy refusal; no execution."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.errors import ADPError
from adp.discovery_schema import digest
from adp.guard_types import Action, ActionKind
from adp.personal_runner import PersonalCoordinator
from adp.personal_product_review import ProductCoordinator
from adp.personal_storage import PersonalBlocked


class DevelopmentCompatibilityTests(unittest.TestCase):
    def controller(self):
        c = PersonalCoordinator.__new__(PersonalCoordinator)
        c.episode = False
        c.record = Mock(return_value={"schema_version": 2, "phase": "DEVELOP", "developer": "old", "gates": []})
        self.prior = {"phase": "ACCOUNTED", "purpose": "develop", "request": {"id": "old"}, "observation": None}
        c.worker = Mock(return_value=self.prior)
        c.workers = SimpleNamespace(records=Mock(return_value=[]))
        return c

    def developer(self, finding=None, predecessor="old"):
        return {"purpose": "develop", "request": {"id": "new"}, "context": {"development_protocol": 2,
            "feedback": [] if finding is None else [finding], "development_attempt": {
                "kind": "INITIAL" if finding is None else "CORRECTION", "predecessor": None if finding is None else predecessor,
                "finding": None if finding is None else digest(finding)}}}

    def test_initial_and_concrete_correction_are_distinct_without_self_approval(self):
        c = self.controller()
        self.assertEqual(c.development_kind(self.developer()), ActionKind.CHECK)
        failure = {"outcome": "NOTRUN", "approved": False, "summary": "actual noncompletion"}
        worker = self.developer(failure)
        with self.assertRaises(ADPError):c.development_kind(worker)
        self.prior["observation"] = {"result": failure}
        c.workers.records.return_value = [self.prior]
        self.assertEqual(c.development_kind(worker), ActionKind.CORRECTION)
        ready = {"outcome": "PASS", "approved": False, "summary": "locally ready, not failure"}
        self.prior["observation"] = {"result": ready}
        with self.assertRaises(ADPError):c.development_kind(self.developer(ready))

    def test_adopted_candidate_correction_has_no_invented_developer_predecessor(self):
        c = self.controller(); c.episode = True
        failure = {"outcome": "FAIL", "approved": False, "summary": "independent adopted-source finding"}
        review = {"phase": "ACCOUNTED", "purpose": "code", "observation": {"result": failure}}
        c.workers.records.return_value = [review]
        worker = self.developer(failure, "adoption-exact")
        with patch("adp.personal_adoption.adopted", return_value={"label": "adoption-exact"}) as adopted:
            self.assertEqual(c.development_kind(worker), ActionKind.CORRECTION)
            adopted.assert_called_once_with(c, historical=True)
        with patch("adp.personal_adoption.adopted", return_value={"label": "adoption-foreign"}), self.assertRaises(ADPError):
            c.development_kind(worker)

    def test_code_action_requires_current_exact_context_not_an_older_initial_author(self):
        c = self.controller()
        c.record.return_value = {"phase": "CODE", "developer": "current", "revision": "a" * 40}
        context = {"development_protocol": 2, "developer": "old", "revision": "a" * 40}
        worker = {"purpose": "code", "context": context, "request": {"revision": "a" * 40}}
        c.context = Mock(return_value={**context, "developer": "current"})
        with self.assertRaises(ADPError):c.worker_action(worker, Action("reviewer", ActionKind.REVIEW, "one"))
        c.worker.assert_not_called()

    def test_legacy_window_refuses_new_authority_without_mutating_issued_consent(self):
        c = self.controller()
        legacy = {"schema_version": 1, "generation": 7, "phase": "DEVELOP", "developer": "historical"}
        c.record.return_value = legacy
        before = deepcopy(legacy)
        with self.assertRaises(PersonalBlocked) as refused:c.require_development_protocol()
        self.assertEqual(refused.exception.subreason, "LEGACY_PROTOCOL")
        self.assertEqual(legacy, before)
        # One executor and one set of accounting hooks serves both personal ports.
        self.assertIs(ProductCoordinator.worker_action, PersonalCoordinator.worker_action)
        self.assertIs(ProductCoordinator.worker_accounted, PersonalCoordinator.worker_accounted)
        self.assertIs(ProductCoordinator.conclude, PersonalCoordinator.conclude)

    def test_successful_developer_is_not_its_own_terminal_evaluation(self):
        c = self.controller()
        c.record.return_value = {"schema_version": 2, "phase": "STAGE", "developer": "new"}
        before = deepcopy(c.record.return_value)
        c.worker_accounted({"purpose": "develop", "context": {"development_protocol": 2}})
        self.assertEqual(c.record.return_value, before)  # Retained reads cannot rewind later phases.
