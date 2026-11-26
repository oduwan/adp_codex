"""Focused existing-writer seams; no genuine workers, HTTP or integration claim."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.personal_product import PersonalProduct
from adp.personal_report import PersonalReport
from adp.personal_republication import RevisionPublication
from adp.personal_publication import PersonalPublication
from adp.personal_storage import create_private
from adp.schema import encode, key
from adp.storage import atomic
import test_publication_write_fence as fence_fixtures


class AccountingWriterTests(unittest.TestCase):
    def writer(self, operation="PR"):
        # Reuse the existing direct-fence fixture. Cold proof and source seals
        # are separately qualified; only these explicit seams are mocked here.
        f = fence_fixtures.PublicationWriteFenceTests();f.setUp();self.addCleanup(f.doCleanups)
        p = (PersonalReport if operation == "REPORT" else PersonalProduct).__new__(
            PersonalReport if operation == "REPORT" else PersonalProduct)
        p.c, p.service, p.transport, p.guard = f.c, f.service, f.transport, f.p.guard
        p.clock, p.personal = lambda: f.now, SimpleNamespace(repository_id=f.target.memory_id)
        p.c.personal = p.personal
        p.active = {"action": f.identifier, "view": {"operation": operation, "generation": 1,
            "revision": "d" * 40, "issued_at": 90, "expires_at": 190},
            "binding": f.transport.credential_binding, "reservation": f.row["reservation"]["permit"],
            "requirement": f.requirement}
        action = f.snapshot["state"]["execution"]["actions"][f.identifier]
        action.update(operation=operation, generation=1, payload={"exact": "effect"})
        p._writing = (f.identifier, deepcopy(action), None, deepcopy(f.snapshot))
        p.record = lambda: {"intents": [deepcopy(p.active)]}
        p.report_record = lambda: deepcopy(p.active)
        p._live_current = lambda: p.active["view"]
        p.forge = SimpleNamespace(_claim_path=lambda _: f.claim_path, repository_id=str(f.target.database_id))
        claim = {"intent": f.identifier, "generation": 1, "payload": digest(action["payload"]),
                 "operation": operation, "repository": p.forge.repository_id}
        atomic(f.claim_path, encode(claim))
        return f, p

    def test_pr_merge_report_use_same_late_canonical_fence(self):
        for operation in ("PR", "MERGE", "REPORT"):
            with self.subTest(operation=operation):
                f, p = self.writer(operation)
                with f.service.bounded():self.assertTrue(p.write_authorized())
                self.assertEqual(f.c.memory.inspect.call_count, 1)
                f.p.guard._snapshot.assert_not_called()
                self.assertEqual(f.http_calls, [])

    def test_late_owner_generation_source_and_submitted_changes_refuse(self):
        changes = (lambda s: s.update(local_owner=False), lambda s: s["state"].update(generation=2),
            lambda s: s["tasks"][key("original")].update(source_revision="e" * 40),
            lambda s: s["state"]["execution"]["actions"].clear(), lambda s: s.update(local_head="f" * 40),
            lambda s: s["state"]["progress_guard"]["requirements"][f.requirement].update(sequence=7))
        f, p = self.writer()
        baseline = deepcopy(f.snapshot)
        for change in changes:
            change(f.snapshot)
            with self.subTest(change=change), f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
            f.snapshot = deepcopy(baseline)

    def test_expired_future_start_revoked_claim_and_intent_refuse(self):
        f, p = self.writer("REPORT")
        active = f.snapshot["state"]["progress_guard"]["requirements"][f.requirement]["active"]
        for now in (94, 180):
            f.now = now
            with f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
        f.now = 100;f.revoked = True
        with f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
        f.revoked = False
        atomic(f.claim_path, encode({"foreign": "claim"}))
        with f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
        p.report_record = lambda: {**p.active, "binding": "changed"}
        with f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
        self.assertEqual(active["deadline"], 180)

    def test_credential_work_cannot_cross_m2_deadline(self):
        f, p = self.writer()
        binding = p.active["binding"]
        class LateCredential:
            @property
            def credential_binding(self):
                f.now = 181
                return binding
        p.transport = LateCredential()
        with f.service.bounded(), self.assertRaises(ADPError):p.write_authorized()
        self.assertEqual(f.http_calls, [])

    def test_revision_constructor_is_nonissuing_but_new_local_admission_checks_binding(self):
        with TemporaryDirectory() as directory:
            c = SimpleNamespace(episode=True, revision=lambda: "a" * 40,
                personal=SimpleNamespace(state=Path(directory)))
            product = SimpleNamespace(c=c, record=Mock(side_effect=AssertionError("No writer check in constructor")))
            def initialize(p, coordinator, **kw):p.c, p.personal = coordinator, coordinator.personal
            with patch.object(PersonalPublication, "__init__", initialize):publication = RevisionPublication(product)
            product.record.assert_not_called()
            product.record = lambda: {"correction": {"approval": "exact"},
                "execution": [{"approval": "exact", "view": {"reader_engine": "old"}}]}
            product.history_binding = Mock(side_effect=ADPError("Changed reader"))
            with patch.object(PersonalPublication, "local") as local:
                with self.assertRaises(ADPError):publication.local()
                local.assert_not_called()
                product.history_binding.side_effect = None
                publication.local()
                local.assert_called_once_with(_history_capture=None)

    def test_post_h3_adoption_uses_literal_recorded_engine_without_new_grant(self):
        from adp.personal_adoption import adopted
        from adp.personal_recovery import grant
        with TemporaryDirectory() as directory:
            state = Path(directory);create_private(state / "adoption-files")
            rows = [{"path": "one", "digest": "a" * 64}, {"path": "two", "digest": "b" * 64}]
            payload = {"episode": "c" * 64}
            with patch("adp.personal_recovery.engine_digest", return_value="d" * 64):
                approval, body = grant("adoption", digest(payload), 100)
            intent = {"approval": approval, "grant": body, "submitted_at": 100, "payload": payload}
            receipt = {"schema_version": 1, "kind": "RETAINED_UNACCEPTED", "episode": payload["episode"],
                "archive": digest({"original": "archive"}), "original_request": "e" * 64,
                "scope_review": digest({"review": "independent"}), "intent": digest(intent), "source": "f" * 40,
                "manifest": rows, "files": {}}
            for row in rows:
                value = {"file": row, "intent": digest(intent), "authorization": "old"}
                atomic(state / "adoption-files" / (digest(row["path"]) + ".json"), encode(value))
                receipt["files"][row["path"]] = digest(value)
            atomic(state / "adoption-intent.json", encode(intent));atomic(state / "adoption.json", encode(receipt))
            c = SimpleNamespace(personal=SimpleNamespace(state=state, descriptor={"episode": payload["episode"]}))
            material = ({"request": "e" * 64, "blueprint": {"material": rows}}, {"original": "archive"}, {"review": "independent"})
            with patch("adp.personal_adoption.original_material", return_value=material), \
                 patch("adp.personal_adoption.grant", side_effect=AssertionError("No new consent")):
                self.assertEqual(adopted(c, historical=True)["evidence"], digest(receipt))
                intent["grant"]["engine"] = "0" * 64
                receipt["intent"] = digest(intent)
                atomic(state / "adoption-intent.json", encode(intent));atomic(state / "adoption.json", encode(receipt))
                with self.assertRaises(ADPError):adopted(c, historical=True)
