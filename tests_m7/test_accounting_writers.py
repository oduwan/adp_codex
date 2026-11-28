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
    def test_deferred_accounting_proof_refuses_changed_original_before_canonical_effect(self):
        from dataclasses import replace
        from adp.discovery_types import Identity, Issue
        from adp.guard_types import data
        from adp.personal_runner import PersonalCoordinator
        from adp.runtime_limits import DEFAULTS
        original = Issue(Identity("17", "issue:1"), 1, "https://example.invalid/issues/1", "Original", "Unchanged",
                         "OPEN", None, "now", "a" * 64, (), (), (), (), ())
        proposal = PersonalProduct.proposed
        intent = PersonalProduct.intent
        while hasattr(proposal, "__wrapped__"):proposal = proposal.__wrapped__
        while hasattr(intent, "__wrapped__"):intent = intent.__wrapped__
        for episode in (True, False):
            with self.subTest(episode=episode):
                f, p = self.writer()
                p.c.memory.control, p.c.episode = f.claim_path.parent, episode
                p.c.track = None
                p.personal.plan = {"window": {"expires_at": 190}, "original_digest": digest(data(original)), "issue_id": original.identity.issue_id}
                observed, events = [original], []
                p.c.original_matches = lambda issue: PersonalCoordinator.original_matches(p.c, issue)
                p.c.fresh = Mock(side_effect=AssertionError("No full inventory in confirmation"))
                p.local = Mock(side_effect=lambda **kw: (events.append(("genuine", kw.get("genuine", True))), "exact")[1])
                def facts(**kw):
                    events.append("facts")
                    observed[0] = replace(original, body="Unapproved scope")
                    return {"policy": {}}
                def originals(*, _issues, **kw):
                    events.append("original")
                    _issues.extend(observed)
                    return {"map": "actual-current"}
                p.facts = facts
                from adp.personal_publication import PersonalPublication
                p.publication = PersonalPublication.__new__(PersonalPublication)
                p.publication.c, p.publication.personal = p.c, p.personal
                p.publication.current_original = originals
                p.record = lambda **kw: None
                p.proposed = lambda *a, **kw: proposal(p, *a, **kw)
                p.journal = SimpleNamespace(upgrade_product_flow=Mock())
                p.forge.submit = Mock()
                before = deepcopy(f.snapshot)
                with self.assertRaisesRegex(ADPError, "Original scope or native dependencies changed"):
                    intent(p, "PR", reviewed="product1.90.190." + "a" * 32 + "." + "b" * 64,
                        authorized=True, authorize_memory=True, assume_quiescence=True,
                        confirm_rules=True, title="Original", body="Original scope")
                self.assertEqual(events, [("genuine", True), "facts", "original"])
                self.assertEqual(f.snapshot, before)
                p.journal.upgrade_product_flow.assert_not_called()
                p.forge.submit.assert_not_called()

    def test_completion_late_expiry_or_canonical_change_never_poisons_immutable_slot(self):
        from adp.personal_track import PersonalTrack
        from adp.personal_storage import read_private
        from adp.discovery_types import Identity, Issue
        f, _ = self.writer()
        baseline = deepcopy(f.snapshot)
        original = Issue(Identity("17", "issue:1"), 1, "https://example.invalid/issues/1", "Original", "Unchanged",
                         "OPEN", None, "now", "a" * 64, (), (), (), (), ())
        for change in ("none", "expiry", "owner", "generation", "checkpoint", "guard", "source"):
            with self.subTest(change=change), TemporaryDirectory() as directory:
                state = Path(directory)
                create_private(state)
                track = PersonalTrack.__new__(PersonalTrack)
                current = deepcopy(baseline)
                clock = [100]
                def records():
                    if change == "expiry":clock[0] = 190
                    elif change == "owner":current["local_owner"] = False
                    elif change == "generation":current["state"]["generation"] += 1
                    elif change == "checkpoint":current["local_head"] = "0" * 40
                    elif change == "guard":current["state"]["progress_guard"]["changed"] = True
                    return []
                memory = SimpleNamespace(control=state, inspect=lambda: deepcopy(current))
                c = SimpleNamespace(memory=memory, clock=lambda: clock[0], episode=False,
                    workers=SimpleNamespace(records=records), record=lambda: {"feature_administration": {"original": True}})
                track.c = c
                track.personal = SimpleNamespace(state=state,
                    intent={"original": {}, "approval": "setup"}, directory=state,
                    plan={"window": {"issued_at": 90, "expires_at": 190}, "feature": {"branch": "work"}})
                track.originals = {original.identity: original}
                path = state / "completion.json"
                track.completion_path = lambda identity: path
                view = {"checkpoint": current["local_head"], "source": "a" * 40, "tree": "b" * 40,
                    "merge": "c" * 40, "actor": 1, "expires_at": 190}
                track.completion_preview = lambda p: {"approval": "exact", "result": view}
                track.accepted = Mock(return_value={"accepted": True})
                row = {"pull": {"id": 1, "number": 1, "repository_id": 17, "url": "https://example.invalid/pull/1"},
                    "intents": [{"view": {"operation": "PR", "revision": "f" * 40,
                        "facts": {"base_ref": "trunk", "base_sha": "d" * 40}}}],
                    "gates": [{"status": "PASS"}]}
                product = SimpleNamespace(record=lambda: row, target=SimpleNamespace(ref="refs/heads/work"),
                    transport=SimpleNamespace(credential_binding="exact"), c=SimpleNamespace(runtime=None))
                atomic(state / "prepared-track.json", encode({"packet": "original"}))
                complete = PersonalTrack.complete
                while hasattr(complete, "__wrapped__"):complete = complete.__wrapped__
                with patch("adp.personal_track.typed", return_value=original), \
                     patch("adp.personal_read_frame.current_source", side_effect=ADPError("Completion source differs") if change == "source" else None) as source_fence:
                    if change == "none":
                        self.assertEqual(complete(track, product, reviewed="exact", authorized=True,
                            confirm_acceptance=True), {"accepted": True})
                        self.assertEqual(read_private(path)["accepted_at"], 100)
                        self.assertEqual(source_fence.call_args.args[1]["view"]["revision"], view["source"])
                    else:
                        with self.assertRaises(ADPError):complete(track, product, reviewed="exact", authorized=True,
                            confirm_acceptance=True)
                        self.assertFalse(path.exists())
                        track.accepted.assert_not_called()

    def writer(self, operation="PR"):
        # Reuse the existing direct-fence fixture. Cold proof and source seals
        # are separately qualified; only these explicit seams are mocked here.
        f = fence_fixtures.PublicationWriteFenceTests();f.setUp();self.addCleanup(f.doCleanups)
        p = (PersonalReport if operation == "REPORT" else PersonalProduct).__new__(
            PersonalReport if operation == "REPORT" else PersonalProduct)
        p.c, p.service, p.transport, p.guard = f.c, f.service, f.transport, f.p.guard
        repository = {"node_id": f.target.node_id, "database_id": f.target.database_id}
        p.clock, p.personal = lambda: f.now, SimpleNamespace(repository_id=f.target.memory_id, plan={"repository": repository})
        p.target = f.target
        f.invocation["identity"] = ("same-serialized-invocation",)
        p.c.revision = lambda: "d" * 40
        p.c.personal = p.personal
        p.active = {"action": f.identifier, "view": {"operation": operation, "generation": 1,
            "revision": "d" * 40, "source_ref": f.target.ref, "repository": repository, "issued_at": 90, "expires_at": 190},
            "binding": f.transport.credential_binding, "reservation": f.row["reservation"]["permit"],
            "requirement": f.requirement}
        action = f.snapshot["state"]["execution"]["actions"][f.identifier]
        action.update(operation=operation, generation=1, payload={"exact": "effect"})
        p._writing = (f.identifier, deepcopy(action), deepcopy(f.snapshot))
        p.record = lambda **kw: {"intents": [deepcopy(p.active)]}
        p.report_record = lambda **kw: deepcopy(p.active)
        p._live_current = Mock(side_effect=AssertionError("No full live/Reviewer reconstruction in write callback"))
        p.forge = SimpleNamespace(service=f.service, _claim_path=lambda _: f.claim_path, repository_id=str(f.target.database_id))
        claim = {"intent": f.identifier, "generation": 1, "payload": digest(action["payload"]),
                 "operation": operation, "repository": p.forge.repository_id}
        atomic(f.claim_path, encode(claim))
        f.service._start_request()  # Direct callback fixture enters its exact own request hazard.
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
        p.report_record = lambda **kw: {**p.active, "binding": "changed"}
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
                local.assert_called_once_with(_history_capture=None, _qualification=None)

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
