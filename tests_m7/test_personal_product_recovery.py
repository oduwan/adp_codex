"""Narrow recovery/containment wiring negatives; no actual process or HTTP."""
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from adp.errors import ADPError
from adp.execution_types import ExternalObservation
from adp.personal_product import PersonalProduct
from adp.policy_types import Ref


class PersonalProductRecoveryTests(unittest.TestCase):
    def execution(self, directory, *, revision="a" * 40):
        f = PersonalProduct.__new__(PersonalProduct)
        f.personal = SimpleNamespace(feature=Path(directory) / "product")
        f.clock = lambda: 1000
        f.c = SimpleNamespace(memory=SimpleNamespace(control=Path(directory)), revision=lambda: revision,
            workers=SimpleNamespace(execute=Mock(side_effect=OSError("synthetic interrupted worker wait"))), stop_workers=Mock(), resume_product_review=Mock(return_value=None))
        view = {"operation": "REVIEW", "issued_at": 1000, "expires_at": 1300, "nonce": "b" * 32, "revision": "a" * 40, "facts": {}, "validation": "binding"}
        token = f.token(view, "c" * 64)
        entry = {"view": view, "approval": token, "binding": "c" * 64, "phase": "PREPARED", "checks": [], "result": None, "reservation": None}
        row = {"pull": {"number": 10}, "execution": [entry], "review": None}
        f.record, f.local, f.review_context, f.save = lambda: row, lambda: None, lambda: {}, lambda row: None
        f.service = SimpleNamespace(bounded=lambda **kw: nullcontext())
        f.facts = lambda: {}
        entry["view"]["facts"] = {"base_sha": "f" * 40}
        f.facts = lambda: {"base_sha": "f" * 40}
        f.pull = lambda **kwargs: row["pull"]
        f.validation_binding = lambda: "binding"
        token = f.token(view, "c" * 64)
        entry["approval"] = token
        return f, token

    def test_worker_exception_reuses_foreground_stop_cleanup(self):
        with TemporaryDirectory(prefix="adp-synthetic-stop-") as directory:
            f, token = self.execution(directory)
            with self.assertRaisesRegex(OSError, "synthetic interrupted worker wait"):
                f.execute("REVIEW", reviewed=token, authorized=True)
            f.c.stop_workers.assert_called_once_with()

    def test_pending_review_approval_cannot_be_rebound_to_changed_source(self):
        with TemporaryDirectory(prefix="adp-synthetic-source-") as directory:
            f, token = self.execution(directory, revision="d" * 40)
            f.c.workers.execute.side_effect = None
            f.c.workers.execute.return_value = {"request": {"id": "e" * 64}}
            f.c.workers.actual = lambda *args, **kwargs: SimpleNamespace(result=SimpleNamespace(approved=True))
            with self.assertRaises(ADPError):
                f.execute("REVIEW", reviewed=token, authorized=True)
            f.c.workers.execute.assert_not_called()

    def test_native_manual_merge_without_ci_review_is_event_only(self):
        f = PersonalProduct.__new__(PersonalProduct)
        source = "a" * 40
        row = {"pull": {"id": "2010", "node_id": "PR_actual", "number": 10, "repository_id": "17", "url": "https://github.com/owned/project/pull/10"},
            "intents": [{"view": {"operation": "PR", "facts": {"base_ref": "refs/heads/trunk", "base_sha": "b" * 40}, "method": None},
                         "action": "c" * 64, "observation": {}}]}
        f.record = lambda: row
        f.c = SimpleNamespace(record=lambda: {}, check_administration=lambda row: None, revision=lambda: source)
        f.target = SimpleNamespace(ref="refs/heads/work/task")
        f.service = SimpleNamespace(bounded=lambda **kw: nullcontext(), _check_stop=lambda: None, refs=lambda: (Ref(f.target.ref, source),))
        f.pull = lambda **kwargs: {"merged": True, "merged_by": {"id": 91}}
        f.port = SimpleNamespace(_value=lambda *args: "e" * 40)
        f.forge = SimpleNamespace(observe=lambda *args, **kwargs: ExternalObservation("PRESENT", "https://github.com/owned/project/pull/10", "f" * 40))
        f.journal = SimpleNamespace(inspect=lambda: {"state": {"execution": {"actions": {}}}})
        f.qualified = Mock(side_effect=ADPError("Actual project checks missing"))
        f.verify_review = Mock(side_effect=ADPError("Actual independent review missing"))
        result = f.status()
        self.assertEqual(result["status"], "EXTERNAL_MERGE_OBSERVED_UNQUALIFIED")
        self.assertEqual(result["qualification"], "UNKNOWN")
        self.assertEqual(result["revision"], "f" * 40)
