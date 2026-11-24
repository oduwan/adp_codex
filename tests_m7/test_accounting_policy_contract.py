"""Offline policy primitives; no worker, check, host probe or forge effects."""
import unittest
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from adp.errors import ADPError
from adp.execution_types import Role, WorkerRequest
from adp.guard_types import data
from adp.personal_recovery import grant, Recovery
from adp.discovery_schema import digest
from adp.schema import encode
from adp.storage import atomic


class AccountingPolicyContractTests(unittest.TestCase):
    def test_local_journal_v2_requires_exact_purpose_and_two_live_fences(self):
        from adp.memory import Memory
        from adp.personal_recovery import journal_purpose
        purpose = journal_purpose("guard", {"immutable_original_intent": 1})
        legacy = {"base": "a" * 40, "state": {}, "tasks": {}}
        Memory._journal_fence(legacy, None, None, recovering=True)
        pending = {**legacy, "schema_version": 2, "policy_fence": purpose}
        callback = lambda: None
        for changed, fence, before in ((None, None, None), (purpose, None, callback), (purpose, callback, None),
                ({**purpose, "stage": "result"}, callback, callback),
                ({**purpose, "subject": "b" * 64}, callback, callback)):
            with self.subTest(purpose=changed), self.assertRaises(ADPError):
                Memory._journal_fence(pending, changed, fence, before, recovering=True)
        Memory._journal_fence(pending, purpose, callback, callback, recovering=True)
        for changed in ({**pending, "extra": True}, {**pending, "schema_version": True},
                {**pending, "policy_fence": {**purpose, "policy": "GENERAL_UNSAFE_BYPASS"}}):
            with self.subTest(changed=changed), self.assertRaises(ADPError):
                Memory._journal_fence(changed, purpose, callback, callback, recovering=True)

    def test_complete_future_projection_is_bounded_before_irreversible_accounting(self):
        from adp.personal_episode import bound_projection
        ordinary = {"original": "Original scope", "candidate_source": "x" * 12000, "track_preparation": "y" * 12000}
        bound_projection({"descriptor": "x" * 100}, {"intent": "x" * 100}, ordinary)
        # Individually bounded source and metadata can exceed the actual total
        # prompt limit when combined. Neither constituent limit is relaxed.
        oversized = {**ordinary, "native_originals": "z" * 12000}
        for descriptor, intent, context in (({}, {}, oversized), ({"full_descriptor": "x" * 131072}, {}, ordinary),
                ({}, {"full_intent": "x" * 131072}, ordinary)):
            with self.subTest(kind=list(descriptor) + list(intent)), self.assertRaises(ADPError):
                bound_projection(descriptor, intent, context)

    def test_marker_restoration_keeps_original_prepared_authority_across_another_crash(self):
        from adp.personal_recovery import immutable, submission_provenance
        with TemporaryDirectory(prefix="adp-offline-marker-") as temporary:
            directory = Path(temporary)
            original, master = {"immutable": "stage"}, {"immutable": "master"}
            payload = {"stage": "guard", "master": digest(master), "intent": digest(original), "canonical": {"step": 0}}
            token, _ = grant("reconcile-guard", digest(payload), 1000)
            restored = {"stage": "guard", "intent": digest(original), "reconciliation": digest(token), "prepared_at": 1001}
            path = directory / "submission-provenance" / "guard.json"
            immutable(directory / "reconciliations" / (digest(token) + ".json"), {"approval": token, "payload": payload})
            immutable(path, restored)
            # A subsequent live grant does not overwrite old provenance.
            other, _ = grant("reconcile-guard", digest(payload), 1100)
            self.assertNotEqual(token, other)
            self.assertEqual(submission_provenance(directory, "guard", original, master), restored)
            self.assertEqual(read_bytes := path.read_bytes(), encode(restored))
            for changed_original, changed_master in (({"changed": True}, master), (original, {"changed": True})):
                with self.assertRaises(ADPError):submission_provenance(directory, "guard", changed_original, changed_master)
            self.assertEqual(path.read_bytes(), read_bytes)

    def test_final_archival_fence_refuses_expiry_during_proof_and_changed_master(self):
        with TemporaryDirectory(prefix="adp-offline-accounting-clock-") as temporary:
            r = Recovery.__new__(Recovery)
            r.root = Path(temporary); r.master_path = r.root / "intent.json"
            clock = [1000]
            r.c = SimpleNamespace(clock=lambda: clock[0], memory=SimpleNamespace(_owner=lambda state: None))
            master = {"state": {}}
            payload = {"head": "a" * 40, "master": digest(master)}
            token, proof = grant("guard", digest(payload), clock[0])
            intent = {"approval": token, "grant": proof, "submitted_at": clock[0], "payload": payload}
            atomic(r.master_path, encode(master)); atomic(r.root / "guard-intent.json", encode(intent))
            r.canonical = lambda m: {"step": 0, "head": payload["head"], "pending": None}
            r.validate_evidence = lambda m: clock.__setitem__(0, proof["expires_at"])
            with self.assertRaisesRegex(ADPError, "expired"):
                r._fence("guard", master, payload, token, intent)
            self.assertEqual({p.name for p in r.root.iterdir()}, {"intent.json", "guard-intent.json"})
            clock[0] = 1000
            atomic(r.master_path, encode({"state": {"changed": True}}))
            with self.assertRaisesRegex(ADPError, "changed"):
                r._fence("guard", master, payload, token, intent)

    def test_historical_batch_requires_actual_object_bytes_and_complete_closure(self):
        from adp.personal_history_git import object_inventory
        raw = b"bounded immutable synthetic object"
        identifier = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        wire = (identifier + " blob " + str(len(raw)) + "\n").encode() + raw + b"\n"
        memory = SimpleNamespace(config=SimpleNamespace(root="unused-offline-fixture"))
        with patch("adp.personal_history_git.git", return_value=wire) as call:
            self.assertEqual(object_inventory(memory, [identifier]), ((identifier, "blob", len(raw)),))
            self.assertEqual(call.call_args.args[2], "--batch")
        changes = (wire[:-1], (identifier + " missing\n").encode(), wire + b"unexpected\n",
            wire.replace(b"blob", b"tree", 1), wire.replace(raw, b"x" * len(raw)),
            wire.replace(str(len(raw)).encode(), b"65537", 1))
        for changed in changes:
            with self.subTest(changed=hashlib.sha256(changed).hexdigest()), \
                 patch("adp.personal_history_git.git", return_value=changed), self.assertRaises(ADPError):
                object_inventory(memory, [identifier])

    def test_history_memo_rechecks_closure_and_never_caches_a_missing_object_pass(self):
        from adp.personal_history_git import verify, _WITNESSES
        _WITNESSES.clear()
        heads = [n * 40 for n in ("a", "b", "c")]
        expected = [({"state": i}, {"task": i}) for i in range(3)]
        memory = SimpleNamespace(config=SimpleNamespace(root="offline", identity="fixture"),
            _read_ref=lambda head: expected[heads.index(head)])
        def value(root, *args):
            if args[0] == "rev-parse":return "d" * 40
            index = heads.index(args[-1]);return heads[index] + " " + heads[index-1]
        objects = (("a" * 40, "commit", 10),)
        with patch("adp.personal_history_git.storage_context", return_value=("private-context",)) as context, \
             patch("adp.personal_history_git.value", side_effect=value), \
             patch("adp.personal_history_git.git", return_value=b""), \
             patch("adp.personal_history_git.object_inventory", return_value=objects) as inventory:
            verify(memory, heads, expected, engine="e" * 64, host="f" * 64)
            verify(memory, heads, expected, engine="e" * 64, host="f" * 64)
            self.assertEqual(context.call_count, 2)
            self.assertEqual(inventory.call_count, 2)
            inventory.side_effect = ADPError("Synthetic missing retained blob")
            with self.assertRaises(ADPError):verify(memory, heads, expected, engine="e" * 64, host="f" * 64)
        _WITNESSES.clear()

    def test_purpose_subject_and_engine_are_not_interchangeable(self):
        token, body = grant("guard", "a" * 64, 1000)
        self.assertEqual(grant("guard", "a" * 64, 1001, token), (token, body))
        for purpose, subject in (("result", "a" * 64), ("episode", "a" * 64), ("guard", "b" * 64)):
            with self.subTest(purpose=purpose), self.assertRaises(ADPError):grant(purpose, subject, 1001, token)
        with patch("adp.personal_recovery.engine_digest", return_value="f" * 64), self.assertRaises(ADPError):
            grant("guard", "a" * 64, 1001, token)

    def test_consent_expiry_is_exclusive_without_backdating_or_renewal(self):
        token, _ = grant("guard", "a" * 64, 1000)
        for now in (999, 1300, 2000):
            with self.subTest(now=now), self.assertRaises(ADPError):grant("guard", "a" * 64, now, token)
        with self.assertRaises(ADPError):
            grant("episode", "a" * 64, 1000, window={"issued_at": 1000, "expires_at": 4601, "nonce": "a" * 32})

    def test_malformed_or_ambiguous_consent_never_yields_authority(self):
        for token in ("", "ae1:guard", "ae1:result:1000:1300:" + "a" * 32 + ":" + "b" * 64,
                      "ae1:guard:1000:1300:bad:" + "b" * 64):
            with self.subTest(token=token[:20]), self.assertRaises((ADPError, ValueError)):
                grant("guard", "a" * 64, 1001, token)

    def test_only_integer_measurements_inside_both_original_caps_qualify(self):
        request = WorkerRequest("a" * 64, "personal:fixture", 1, Role.DEVELOPER, "b" * 40,
            "/tmp/disposable-not-executed", "Synthetic not dispatched", 300, 1300)
        row = {"request": data(request), "observation": {"elapsed_seconds": 300, "samples": 1, "payload_bytes": 100}}
        Recovery.measurements(row, {"seconds": 300, "samples": 1, "payload_bytes": 100})
        for field, bad in (("elapsed_seconds", -1), ("elapsed_seconds", True), ("elapsed_seconds", 301),
                           ("samples", 10001), ("samples", 1.5), ("payload_bytes", 1048577)):
            changed = {**row, "observation": {**row["observation"], field: bad}}
            with self.subTest(field=field, bad=bad), self.assertRaises(ADPError):Recovery.measurements(changed)
        with self.assertRaises(ADPError):Recovery.measurements(row, {"seconds": 299, "samples": 1, "payload_bytes": 100})
