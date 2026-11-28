"""Prospective policy, recorded feedback and legacy refusal; no execution."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.errors import ADPError
from adp.discovery_schema import digest
from adp.guard_types import Action, ActionKind
from adp.guard_types import Outcome, data
from adp.execution_types import WorkerResult
from adp.execution_schema import worker_result
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

    def test_foreign_purpose_review_cannot_advance_or_save_the_code_journal(self):
        c = self.controller(); c.task_id = "task"
        journal = {"schema_version": 2, "phase": "CODE", "developer": "developer", "feedback": []}
        before = deepcopy(journal)
        c.record.return_value = journal; c.save = Mock()
        delivery = {"outcome": "PASS", "summary": "Observed code context", "evidence": ["runtime:purpose"]}
        c.workers.result = Mock(return_value=delivery)
        worker = {"purpose": "code", "context": {"development_protocol": 2}, "phase": "ACCOUNTED",
            "request": {"id": "code"}, "requirement": "product", "assignment": {"assignment_id": "assignment"},
            "guard_context": {}, "observation": {"receipt": "runtime:purpose"}}
        task = {"assignments": {"assignment": {"status": "accepted", "result": delivery}}}
        item = {"last": {"context": {}, "observation": {"outcome": "FAIL", "evidence": ["runtime:purpose"]}}}
        c.guard = SimpleNamespace(_snapshot=Mock(return_value=({}, task, item)))
        for criteria in (("foreign",), (), ("code", "foreign")):
            claimed = WorkerResult(Outcome.PASS, True, criteria, "A generic result is not exact-purpose approval")
            worker_result(claimed)  # These are valid generic results, not malformed fixtures.
            worker["observation"]["result"] = data(claimed)
            with self.subTest(criteria=criteria), self.assertRaises(PersonalBlocked) as refusal:
                c.worker_accounted(worker)
            self.assertEqual(refusal.exception.subreason, "REVIEW_PURPOSE_MISMATCH")
            c.save.assert_not_called(); self.assertEqual(journal, before)
        # Duplicated criteria is rejected earlier by the actual generic schema.
        with self.assertRaises(ADPError):worker_result(replace(claimed, criteria=("code", "code")))
        worker["observation"]["result"] = data(replace(claimed, criteria=("code",)))
        item["last"]["observation"]["outcome"] = "PASS"
        c.worker_accounted(worker)
        self.assertEqual((journal["phase"], journal["code_review"]), ("CHECKS", "code"))
        c.save.assert_called_once()
        c.worker_accounted(worker); c.save.assert_called_once()  # No replay/rewind.

    def test_h3_code_context_uses_historical_authorship_without_old_sha_authority(self):
        c = self.controller(); c.episode = True; c.track = None
        plan = {"paths": ["product"], "feature": {"branch": "work/task"}, "commit_message": "Scoped change",
            "commit_body": "", "required_check_names": [], "check_requirements": "UNKNOWN", "branch_rules": [],
            "checkout": {"head": "a" * 40}}
        c.personal = SimpleNamespace(plan=plan, repository_id="17", intent={"original": {}, "governance": []},
            feature=Path("/synthetic-never-accessed"), descriptor={"episode": "episode", "base": {"choices": {"paths": ["product"]}}})
        c.record.return_value = {"schema_version": 2, "phase": "CODE", "developer": "developer",
            "revision": "b" * 40, "feedback": [], "gates": []}
        c.worker.return_value = {"observation": {"result": {"outcome": "PASS", "approved": False}}}
        def origin(*, historical=False):
            if not historical:raise ADPError("The old-SHA Developer has no current CODE authorization")
            return {"kind": "DEVELOPER", "label": "developer", "source": "immutable-old-source"}
        c.source_origin = Mock(side_effect=origin)
        c.accounting_material = Mock(return_value=[])
        with patch("adp.personal_runner.git", return_value=b"committed diff"), patch("adp.personal_runner.index_digest", return_value="index"):
            context = c.context("code")
        c.source_origin.assert_called_once_with(historical=True)
        self.assertEqual(context["revision"], "b" * 40)
        self.assertEqual(context["source_origin"]["label"], "developer")
        self.assertNotIn("ALLOW", str(context["source_origin"]))

    def test_episode_protocol_version_cannot_reuse_an_older_consent(self):
        from adp.personal_recovery import grant
        window = {"issued_at": 100, "expires_at": 200, "nonce": "a" * 32}
        old = {"schema_version": 1, "window": window, "scope": "original", "limits": {"developers": 2}}
        token, body = grant("episode", digest(old), 100, window=window)
        self.assertEqual(grant("episode", digest(old), 110, token)[1], body)
        prospective = {**old, "schema_version": 2}
        with self.assertRaises(ADPError):grant("episode", digest(prospective), 110, token)
        fresh, current = grant("episode", digest(prospective), 110,
            window={"issued_at": 110, "expires_at": 200, "nonce": "b" * 32})
        self.assertNotEqual(fresh, token)
        self.assertEqual((current["issued_at"], current["expires_at"]), (110, 200))
        self.assertEqual(old["schema_version"], 1)
