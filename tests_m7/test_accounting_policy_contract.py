"""Offline policy primitives; no worker, check, host probe or forge effects."""
import unittest
import hashlib
from dataclasses import dataclass, replace
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
    def test_same_call_view_requires_fresh_exact_canonical_subject_and_keeps_public_tuple(self):
        from copy import deepcopy
        from adp.personal_episode import same_observation
        from adp.personal_history import archived
        view = {"health": "SYNCED", "local_owner": True, "local_head": "a" * 40, "remote_head": "a" * 40,
            "state": {"generation": 1, "owner": {"id": "original"}, "lineage": "exact"},
            "tasks": {"original": {"source": "b" * 40}}, "inbox_count": 0,
            "recovery_slots": [], "recovery_journal": None}
        same_observation(view, deepcopy(view))
        for changed in ({"local_head": "c" * 40}, {"remote_head": "c" * 40}, {"local_owner": False},
                {"state": {**view["state"], "generation": 2}}, {"state": {**view["state"], "owner": None}},
                {"state": {**view["state"], "lineage": "changed"}}, {"tasks": {}}, {"inbox_count": 1},
                {"health": "REMOTE_MISMATCH"}):
            with self.subTest(changed=changed), self.assertRaises(ADPError):
                same_observation(view, {**deepcopy(view), **changed})
        pending = {**view, "health": "RECOVERY_REQUIRED", "recovery_journal": "d" * 64, "recovery_slots": ["exact-slot"]}
        with self.assertRaises(ADPError):same_observation(pending, pending)
        same_observation(pending, deepcopy(pending), recovery=True)
        for change in ({"recovery_journal": "e" * 64}, {"recovery_slots": []}):
            with self.assertRaises(ADPError):same_observation(pending, {**pending, **change}, recovery=True)
        first = ({"master": 1}, {"receipt": 1}, {"context-1"}, view, [{"authenticated": 1}])
        second = ({"master": 2}, {"receipt": 2}, {"context-2"}, {**view, "local_head": "f" * 40}, [])
        with patch("adp.personal_history._archived_view", side_effect=(first, second)) as actual:
            self.assertEqual(archived("protected-subject"), first[:3])
            self.assertEqual(archived("protected-subject"), second[:3])
            self.assertEqual(actual.call_count, 2)  # Fresh proof, no retained ALLOW.

    def test_publication_binding_keeps_origin_historical_and_requires_current_live_reviews(self):
        from adp.personal_publication import PersonalPublication
        from adp.guard_types import DecisionKind
        from adp.discovery_github import Response
        from adp.schema import key
        from unittest.mock import Mock
        task_id, revision = "personal:offline-binding", "a" * 40
        result = {"outcome": "PASS"}
        workers, assignments, guards = {}, {}, {}
        for purpose in ("original", "code"):
            identifier = purpose + "-request"
            workers[identifier] = {"purpose": purpose, "phase": "ACCOUNTED", "assignment": {"assignment_id": identifier},
                "request": {"generation": 1, "revision": revision}, "requirement": purpose}
            assignments[identifier] = {"status": "accepted", "worker": "worker:" + identifier,
                "generation": 1, "source_revision": revision, "result": result}
            guards[purpose] = {"approval": {"context": "exact-current-context"}}
        task = {"key": key(task_id), "source_revision": revision, "assignments": assignments, "iteration": 1}
        observed = {"health": "SYNCED", "local_owner": True, "tasks": {key(task_id): task},
            "state": {"generation": 1, "progress_guard": {"requirements": guards, "task_epochs": {key(task_id): 1}}}}
        origin = {"kind": "RETAINED_UNACCEPTED", "evidence": "b" * 64}
        def historical_origin(*, historical=False):
            self.assertTrue(historical, "Digest projection must not recursively reauthorize source")
            return origin
        row = {"revision": revision, "original_review": "original-request", "code_review": "code-request",
            "phase": "LOCAL_DRAFT_CODE_REVIEWED", "coordination": None}
        c = SimpleNamespace(task_id=task_id, episode=True, record=lambda: row, worker=lambda n: workers[n],
            workers=SimpleNamespace(result=lambda _: result, fence=lambda: None),
            guard=SimpleNamespace(_decision=Mock(return_value=SimpleNamespace(kind=DecisionKind.ALLOW)),
                _context=lambda *a: "exact-current-context"), source_origin=historical_origin,
            memory=SimpleNamespace(inspect=lambda: observed), transport=None)
        p = PersonalPublication.__new__(PersonalPublication);p.c = c
        sealed = p.review_binding()
        origin["evidence"] = "c" * 64
        self.assertNotEqual(p.review_binding(), sealed)
        for changed in ("owner", "source", "guard", "approval"):
            with self.subTest(changed=changed):
                if changed == "owner":observed["local_owner"] = False
                if changed == "source":task["source_revision"] = "d" * 40
                if changed == "guard":c.guard._decision.return_value.kind = DecisionKind.STOP_UNSAFE
                if changed == "approval":guards["code"]["approval"] = None
                with self.assertRaises(ADPError):p.review_binding()
                observed["local_owner"] = True;task["source_revision"] = revision
                c.guard._decision.return_value.kind = DecisionKind.ALLOW;guards["code"]["approval"] = {"context": "exact-current-context"}
        base = "/repos/owned/disposable/issues/1"
        p.original_bases = lambda: (base,)
        p.read = SimpleNamespace(get=lambda path: Response(200, {}))
        c.fresh = lambda: [c.transport.get(base + suffix) for suffix in ("", "/comments?per_page=100&page=1",
            "/timeline?per_page=100&page=1", "/dependencies/blocked_by?per_page=100&page=1", "/sub_issues?per_page=100&page=1")]
        for rejected in ("original_approval", "verify_local_review"):
            c.original_approval = Mock();c.verify_local_review = Mock()
            setattr(c, rejected, Mock(side_effect=ADPError("Synthetic live review revoked")))
            with self.subTest(rejected=rejected), self.assertRaisesRegex(ADPError, "live review revoked"):
                p.local()

    def test_check_charge_precedes_exact_m3_authorization_without_reusing_old_grant(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
        import test_policy as accepted_policy
        from adp.personal_runner import PersonalCoordinator
        from adp.policy_types import Authorization, Effect, Operation, Request
        f = accepted_policy.PolicyFixture()
        f.setUp()
        old = f.provider.plan(f.task, Request(Operation.VALIDATE))
        old_grant = Authorization(f.authority.sign(f.provider.authorization_subject(old), "operation"))
        charged = []
        def charge(identifier):
            charged.append(identifier)
            f.safety.value = replace(f.safety.value, memory_head="e" * 40)
        def authorize(plan):
            return Authorization(f.authority.sign(f.provider.authorization_subject(plan), "operation"))
        @dataclass
        class UnknownGate:
            status: str = "UNKNOWN"
            qualified: bool = False
        def observe(phase, *, authorization, budget_ms):
            self.assertEqual(charged, ["local:exact-permit"])
            current = f.provider.plan(f.task, Request(Operation.VALIDATE))
            self.assertEqual(f.provider.decide(current, authorization).effect, Effect.ALLOW)
            self.assertNotEqual(f.provider.decide(current, old_grant).effect, Effect.ALLOW)
            return UnknownGate()  # No project check or PASS is fabricated.
        record = {"observations": 0}
        plan = {"required_check_names": ["unit"], "unresolved_check_names": [], "repository": {"name": "owned/disposable"},
            "window": {"maximum_check_observations": 3, "issued_at": 90, "expires_at": 200}}
        c = SimpleNamespace(personal=SimpleNamespace(plan=plan, feature=Path("/tmp/not-executed"),
            state=Path("/tmp/not-created"), repository_id=f.task.repository_id), record=lambda: record, ci_transport=object(),
            provider=lambda *a: (f.provider, f.task), authority=SimpleNamespace(authorize=authorize,
                check_policy=lambda plan, policy: policy, native_observation=lambda *a: None), checks=lambda: (),
            charge_check=charge, save=lambda row: None, task_id=f.task.task_id, seconds_left=lambda: 100,
            guard=SimpleNamespace(_snapshot=lambda *a: (None, None, {"active": {"deadline": 200}})), clock=lambda: 100)
        permit = SimpleNamespace(token="exact-permit", decision=SimpleNamespace(baseline=SimpleNamespace(requirement_id=f.task.requirement_id)))
        with patch("adp.personal_runner.ProjectValidation", return_value=SimpleNamespace(observe=observe)):
            result = PersonalCoordinator.observe_checks(c, permit)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["qualified"])
        self.assertEqual(record["observations"], 1)

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
        from adp.personal_history_git import verify
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
            first = verify(memory, heads, expected)
            self.assertEqual(verify(memory, heads, expected), first)
            # The historical test ID is retained. The removed module-global
            # memo is replaced by caller-local witnesses and actual opening/
            # closing storage checks on EVERY read, never a remembered PASS.
            self.assertEqual(context.call_count, 4)
            self.assertEqual(inventory.call_count, 2)
            inventory.side_effect = ADPError("Synthetic missing retained blob")
            with self.assertRaises(ADPError):verify(memory, heads, expected)

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
