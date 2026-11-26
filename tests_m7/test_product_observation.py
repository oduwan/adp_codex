"""Same-stage actual snapshots and single late Product gate; no runtime proof."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from adp.errors import ADPError
from adp.guard import ProgressGuard
from adp.personal_product import PersonalProduct
from adp.personal_runner import PersonalCoordinator
from adp.schema import key
import test_accounting_writers as writers


class ProductObservationTests(unittest.TestCase):
    def review(self):
        p = PersonalProduct.__new__(PersonalProduct)
        result = {"outcome": "PASS", "summary": "synthetic independent review", "evidence": ["fixture:review"]}
        task = {"key": key("task"), "source_revision": "a"*40, "iteration": 1,
            "assignments": {n: {"status": "accepted", "generation": 1, "result": deepcopy(result)} for n in ("scope", "code")}}
        state = {"schema_version": 2, "generation": 1, "repository_id": "repo",
            "progress_guard": {"schema_version": 1, "task_epochs": {task["key"]: 1}, "requirements": {}}}
        for name in ("scope", "code"):
            state["progress_guard"]["requirements"][name] = {"tasks": [task["key"]], "active": None,
                "mode": "normal", "reason": "Admitted", "campaign": None, "contract": "reviews", "gate": name,
                "sequence": 1, "unresolved": [], "approval": {"context": ProgressGuard._context(state, task)}}
        observed = {"health": "SYNCED", "local_owner": True, "state": state, "tasks": {task["key"]: task}}
        workers = {n: {"request": {"id": n, "revision": "a"*40}, "assignment": {"assignment_id": n},
            "requirement": n, "observation": {"synthetic": "stopped"}} for n in ("scope", "code")}
        memory = SimpleNamespace(inspect=Mock(side_effect=lambda: deepcopy(observed)))
        c = SimpleNamespace(task_id="task", memory=memory, guard=ProgressGuard(memory, clock=lambda: 100),
            record=lambda: {"original_review": "scope", "code_review": "code"},
            workers=SimpleNamespace(result=lambda worker: deepcopy(result), records=Mock(return_value=list(workers.values()))))
        c.worker = lambda name, **kw: PersonalCoordinator.worker(c, name, **kw)
        c.allowed = lambda requirement, **kw: PersonalCoordinator.allowed(c, requirement, **kw)
        c.guard._snapshot = Mock(side_effect=AssertionError("No second canonical snapshot"))
        p.c, p.clock = c, lambda: 100
        return p, observed, workers

    def test_both_reviewers_and_guard_decisions_share_one_actual_snapshot(self):
        p, observed, _ = self.review()
        first = p.review_seal()
        self.assertEqual(p.c.memory.inspect.call_count, 1)
        p.c.workers.records.assert_called_once_with()
        self.assertEqual(p.review_seal(_observed=observed), first)
        self.assertEqual(p.c.memory.inspect.call_count, 1)
        p.c.guard._snapshot.assert_not_called()

    def test_shared_worker_inventory_still_refuses_ambiguous_role_identity(self):
        p, observed, workers = self.review()
        p.c.workers.records.return_value.append(deepcopy(workers["code"]))
        with self.assertRaisesRegex(ADPError, "worker record is missing"):p.review_seal(_observed=observed)
        p.c.workers.records.assert_called_once_with()

    def test_current_review_assignment_source_owner_and_guard_refusals_remain(self):
        for change in ("source", "assignment", "generation", "owner", "health", "stop"):
            p, observed, workers = self.review()
            if change == "source":workers["code"]["request"]["revision"] = "b"*40
            if change == "assignment":observed["tasks"][key("task")]["assignments"]["code"]["status"] = "pending"
            if change == "generation":observed["state"]["generation"] = 2
            if change == "owner":observed["local_owner"] = False
            if change == "health":observed["health"] = "RECOVERY_REQUIRED"
            if change == "stop":observed["state"]["progress_guard"]["requirements"]["code"]["mode"] = "unsafe"
            with self.subTest(change=change), self.assertRaises(ADPError):p.review_seal(_observed=observed)
            p.c.memory.inspect.assert_not_called()

    def writer(self, operation="PR"):
        helper = writers.AccountingWriterTests()
        f, p = helper.writer(operation)
        self.addCleanup(helper.doCleanups)
        return f, p

    def test_credential_callback_canonical_drift_precedes_the_only_late_snapshot(self):
        for operation in ("PR", "MERGE", "REPORT"):
            for change in ("head", "owner", "generation", "permit"):
                f, p = self.writer(operation)
                binding = p.active["binding"]
                class Credential:
                    @property
                    def credential_binding(self):
                        if change == "head":f.snapshot["local_head"] = "f"*40
                        if change == "owner":f.snapshot["local_owner"] = False
                        if change == "generation":f.snapshot["state"]["generation"] = 2
                        if change == "permit":f.snapshot["state"]["progress_guard"]["requirements"][f.requirement]["active"] = None
                        return binding
                p.service.transport = p.transport = Credential()
                with self.subTest(operation=operation, change=change), f.service.bounded(), self.assertRaises(ADPError):
                    p.write_authorized()
                self.assertEqual(f.c.memory.inspect.call_count, 1)
                p._live_current.assert_not_called()
                self.assertEqual(f.http_calls, [])

    def test_recipient_transport_or_invocation_drift_never_reaches_native_effect(self):
        for change in ("transport", "repository", "invocation"):
            f, p = self.writer()
            if change == "transport":p.service.transport = object()
            if change == "repository":p.active["view"]["repository"] = {"node_id": "foreign", "database_id": 18}
            if change == "invocation":f.invocation["identity"] = ("different-host-context",)
            with self.subTest(change=change), f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
            self.assertEqual(f.http_calls, [])

    def test_only_exact_current_request_marker_is_admitted_and_never_cleared(self):
        from adp.personal_storage import read_private
        from adp.schema import encode
        from adp.storage import atomic
        f, p = self.writer()
        path = f.service._hazard_path()
        original = read_private(path)
        with f.service.bounded():self.assertTrue(p.write_authorized())
        self.assertEqual(read_private(path), original)
        self.assertTrue(f.service.unconfirmed_contexts())
        for wrong in (None, {"status": "IN_FLIGHT_OR_UNKNOWN", "repository": "foreign"}, {"status": "STOPPED"}):
            if wrong is None:path.unlink()
            else:atomic(path, encode(wrong))
            with self.subTest(wrong=wrong), f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
        atomic(path, encode(original));f.service._live_unknown = False
        with f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()

    def test_missing_product_journal_keeps_original_upgrade_and_health_gates(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            p = PersonalProduct.__new__(PersonalProduct)
            p.path = Path(directory) / "product.json"
            p.c = SimpleNamespace(task_id="task", memory=SimpleNamespace(inspect=Mock(side_effect=AssertionError("Use actual supplied snapshot"))))
            observed = {"health": "SYNCED", "state": {"schema_version": 3, "execution": {"actions": {}}}}
            self.assertIsNone(p.record(_observed=observed))
            for health, schema in (("RECOVERY_REQUIRED", 3), ("SYNCED", 2)):
                current = deepcopy(observed);current["health"] = health;current["state"]["schema_version"] = schema
                with self.subTest(health=health, schema=schema), self.assertRaises(ADPError):p.record(_observed=current)
            p.c.memory.inspect.assert_not_called()

    def test_report_identity_parsing_reuses_snapshot_and_refuses_changed_iteration(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from adp.personal_report import PersonalReport
        from adp.schema import encode
        from adp.storage import atomic
        with TemporaryDirectory() as directory:
            p = PersonalReport.__new__(PersonalReport)
            p.report_path = Path(directory) / "report.json"
            p.personal = SimpleNamespace(repository_id="repo")
            p.c = SimpleNamespace(task_id="task", memory=SimpleNamespace(inspect=Mock(side_effect=AssertionError("No hidden report-key observation"))))
            observed = {"tasks": {key("task"): {"iteration": 1}}}
            view = {"operation": "REPORT", "issued_at": 90, "expires_at": 190, "nonce": "a"*32}
            row = {"view": view, "binding": "credential", "approval": p.token(view, "credential"),
                "action": p.report_key(_observed=observed), "requirement": None, "reservation": None,
                "observation": None, "before": None, "after": None, "comment": None}
            atomic(p.report_path, encode(row))
            self.assertEqual(p.report_record(_observed=observed), row)
            observed["tasks"][key("task")]["iteration"] = 2
            with self.assertRaises(ADPError):p.report_record(_observed=observed)
            p.c.memory.inspect.assert_not_called()

    def test_private_intent_callback_change_precedes_late_canonical_observation(self):
        f, p = self.writer()
        def record(**kw):
            f.snapshot["state"]["generation"] = 2
            return {"intents": [deepcopy(p.active)]}
        p.record = record
        with f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
        self.assertEqual(f.c.memory.inspect.call_count, 1)
        self.assertEqual(f.http_calls, [])
