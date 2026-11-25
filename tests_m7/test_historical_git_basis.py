"""D2 focused disposable Git and offline consent controls, no live runtime."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.errors import ADPError
from adp.git import git, value
from adp.memory import Memory
from adp.personal_history import _historical_grant, _reader_binding
from adp.personal_history_git import storage_context, verify
from adp.personal_recovery import grant
from personal_fixtures import GitFixture


class HistoricalGitBasisTests(GitFixture):
    def setUp(self):
        super().setUp()
        self.memory = Memory(self.config(), pinned_local_remote=self.remote)
        self.memory.initialize(authorized=True)
        self.memory.claim("disposable-basis-owner")
        self.heads, self.expected = [], []
        self.take()
        revision = value(self.a, "rev-parse", "HEAD")
        for name in ("original", "continuation"):
            self.memory.add_task(name, revision)
            self.take()

    def take(self):
        observed = self.memory.inspect()
        self.heads.append(observed["local_head"])
        self.expected.append((observed["state"], observed["tasks"]))

    def test_actual_stable_objects_both_replicas_and_readonly_concurrent_reads(self):
        before = (git(self.a, "show-ref"), git(self.remote, "show-ref"),
            (self.memory.path / "state.json").read_bytes(), (self.memory.common / "config").read_bytes())
        expected = verify(self.memory, self.heads, self.expected)
        self.assertEqual(tuple(row[0] for row in expected), (False, True))
        with ThreadPoolExecutor(max_workers=2) as pool:
            actual = list(pool.map(lambda _: verify(self.memory, self.heads, self.expected), range(2)))
        self.assertEqual(actual, [expected, expected])
        self.assertEqual((git(self.a, "show-ref"), git(self.remote, "show-ref"),
            (self.memory.path / "state.json").read_bytes(), (self.memory.common / "config").read_bytes()), before)
        changed = deepcopy(self.expected); changed[-1][0]["revision"] += 1
        with self.assertRaises(ADPError):verify(self.memory, self.heads, changed)
        with self.assertRaises(ADPError):verify(self.memory, self.heads[::-1], self.expected[::-1])

    def test_missing_and_corrupt_bare_or_local_objects_never_inherit_a_pass(self):
        baseline = verify(self.memory, self.heads, self.expected)
        identifier = value(self.a, "rev-parse", self.heads[0] + ":state.json")
        for common in (self.memory.common, self.remote):
            path = common / "objects" / identifier[:2] / identifier[2:]
            self.assertTrue(path.is_file(), "Disposable fixture must have a real loose object")
            saved = path.with_name(path.name + ".retained")
            original, mode = path.read_bytes(), path.stat().st_mode & 0o777
            path.rename(saved)
            try:
                with self.assertRaises(ADPError):verify(self.memory, self.heads, self.expected)
            finally:saved.rename(path)
            path.chmod(0o600); path.write_bytes(b"Corrupt disposable historical object")
            try:
                with self.assertRaises(ADPError):verify(self.memory, self.heads, self.expected)
            finally:path.write_bytes(original); path.chmod(mode)
        self.assertEqual(verify(self.memory, self.heads, self.expected), baseline)

    def test_existing_branch_retains_objects_under_gc_without_added_refs(self):
        before = verify(self.memory, self.heads, self.expected)
        refs = (git(self.a, "show-ref"), git(self.remote, "show-ref"))
        for root in (self.a, self.remote):git(root, "gc", "--prune=now")
        self.assertEqual(verify(self.memory, self.heads, self.expected), before)
        self.assertEqual((git(self.a, "show-ref"), git(self.remote, "show-ref")), refs)
        self.assertEqual(self.memory.inspect()["local_head"], self.heads[-1])

    def test_each_storage_context_rejects_rewrites_alternates_and_promisors(self):
        for remote, common, root in ((False, self.memory.common, self.a), (True, self.remote, self.remote)):
            for leaf in ("info/grafts", "shallow", "objects/info/alternates", "objects/info/http-alternates"):
                path = common / leaf; path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"")
                try:
                    with self.assertRaises(ADPError):storage_context(self.memory, remote=remote)
                finally:path.unlink()
            git(root, "config", "remote.unsupported.promisor", "true")
            try:
                with self.assertRaises(ADPError):storage_context(self.memory, remote=remote)
            finally:git(root, "config", "--unset", "remote.unsupported.promisor")
            ref = "refs/replace/" + self.heads[0]
            git(root, "update-ref", ref, self.heads[-1], "0" * 40)
            try:
                with self.assertRaises(ADPError):storage_context(self.memory, remote=remote)
            finally:git(root, "update-ref", "-d", ref, self.heads[-1])

    def test_interrupted_read_creates_no_object_ref_consent_or_authority(self):
        refs = (git(self.a, "show-ref"), git(self.remote, "show-ref"))
        with patch("adp.personal_history_git.object_inventory", side_effect=OSError("Interrupted read")):
            with self.assertRaises(OSError):verify(self.memory, self.heads, self.expected)
        self.assertEqual((git(self.a, "show-ref"), git(self.remote, "show-ref")), refs)
        self.assertEqual(verify(self.memory, self.heads, self.expected), verify(self.memory, self.heads, self.expected))


class HistoricalConsentTests(unittest.TestCase):
    def test_literal_historical_decoder_cannot_issue_change_or_renew(self):
        subject, original = "a" * 64, "b" * 64
        for stage in ("guard", "result", "episode", "reconcile-guard", "reconcile-result"):
            with patch("adp.personal_recovery.engine_digest", return_value=original):token, body = grant(stage, subject, 100)
            with patch("adp.personal_recovery.engine_digest", return_value="c" * 64):
                self.assertEqual(_historical_grant(stage, subject, 100, token, original), body)
                with self.assertRaises(ADPError):grant(stage, subject, 101, token)
            for changed in ((stage, "d" * 64, 100, token, original), (stage, subject, 400, token, original),
                    (stage, subject, 100, token, "c" * 64), ("unsupported", subject, 100, token, original),
                    (stage, subject, True, token, original), (stage, subject, 100, None, original)):
                with self.assertRaises(ADPError):_historical_grant(*changed)

    def test_binding_has_no_raw_receipt_or_authority_and_current_reader_is_fresh(self):
        capture = {"historical_basis": {"schema_version": 1, "checkpoint": "a" * 40, "relation_digest": "b" * 64},
            "historical_engine": "c" * 64, "private": "RAW_RECEIPT_MUST_NOT_ESCAPE"}
        with patch("adp.personal_recovery.engine_digest", return_value="d" * 64):first = _reader_binding(capture)
        with patch("adp.personal_recovery.engine_digest", return_value="e" * 64):second = _reader_binding(capture)
        self.assertNotEqual(first, second)
        self.assertEqual(set(first), {"historical_basis", "historical_engine", "reader_engine"})
        self.assertNotIn("RAW_RECEIPT", str(first))
        first["historical_basis"]["checkpoint"] = "f" * 40
        self.assertEqual(capture["historical_basis"]["checkpoint"], "a" * 40)
        capture["historical_basis"]["extra"] = "unsupported"
        with self.assertRaises(ADPError):_reader_binding(capture)

    def test_staged_accounting_writer_families_refuse_before_any_effect(self):
        from adp.personal_product import PersonalProduct
        from adp.personal_republication import RevisionPublication
        from adp.personal_report import PersonalReport
        from adp.personal_track import PersonalTrack
        c = SimpleNamespace(episode=True)
        product = SimpleNamespace(c=c)
        calls = ((PersonalProduct.intent.__wrapped__, (product, "PR"), {"reviewed": "old", "authorized": True,
                    "authorize_memory": True, "assume_quiescence": True, "confirm_rules": True}),
            (PersonalProduct.execute.__wrapped__, (product, "REVIEW"), {"reviewed": "old", "authorized": True}),
            (PersonalProduct.write_authorized, (product,), {}),
            (PersonalReport.report.__wrapped__, (product,), {"reviewed": "old", "authorized": True,
                    "authorize_memory": True, "assume_quiescence": True, "confirm_rules": True}),
            (PersonalTrack.complete.__wrapped__, (product, product), {"reviewed": "old", "authorized": True, "confirm_acceptance": True}),
            (PersonalTrack.next.__wrapped__.__wrapped__, (product, product, None), {"reviewed": "old", "setup_approval": "old", "authorized": True}),
            (RevisionPublication, (product,), {}))
        for call, args, kwargs in calls:
            with self.subTest(call=call), self.assertRaisesRegex(ADPError, "ACCOUNTING_WRITER_CUTOVER_PENDING"):
                call(*args, **kwargs)

    def test_publication_live_rejects_old_schema_changed_basis_and_reader_before_git(self):
        from adp.personal_publication import PersonalPublication
        from adp.discovery_schema import digest
        capture = {"historical_basis": {"schema_version": 1, "checkpoint": "a" * 40, "relation_digest": "b" * 64},
            "historical_engine": "c" * 64}
        p = PersonalPublication.__new__(PersonalPublication)
        def live(**kwargs):
            kwargs["_history_capture"].update(deepcopy(capture))
            return {"state": {"generation": 1}}
        p.c = SimpleNamespace(episode=True, live=live)
        p.clock = lambda: 100
        p.port = SimpleNamespace(_value=lambda *args: self.fail("Changed binding must refuse before native Git"))
        with patch("adp.personal_recovery.engine_digest", return_value="d" * 64):
            original = {"schema_version": 2, "view": _reader_binding(capture)}
            for field, replacement in (("schema_version", 1), ("reader_engine", "e" * 64),
                    ("historical_engine", "e" * 64), ("historical_basis", {**capture["historical_basis"], "checkpoint": "f" * 40})):
                row = deepcopy(original)
                if field == "schema_version":row[field] = replacement
                else:row["view"][field] = replacement
                p.record = lambda **kwargs: row
                with self.subTest(field=field), self.assertRaisesRegex(ADPError, "changed accounting writer"):
                    p._live_current(review=False)


from accounting_fixtures import AccountingFixture


class HistoricalEpisodeBasisTests(AccountingFixture):
    def test_existing_h3_binds_literal_old_consent_and_refuses_changed_or_unavailable_evidence(self):
        from adp.discovery_schema import digest
        from adp.personal_episode import load_episode
        from adp.personal_storage import read_private
        from adp.schema import encode
        from adp.storage import atomic
        self.episode()
        root, memory = self.personal, self.c.memory
        child = load_episode(self.continuation.directory)
        capture = {}
        child._active_view(memory=memory, runtime=self.runtime, _capture=capture)
        basis = capture["historical_basis"]
        before = memory.inspect()
        self.assertEqual(basis["checkpoint"], before["local_head"])
        self.assertEqual(capture["historical_engine"], child.descriptor["base"]["engine"])
        self.assertEqual(len(capture["historical_objects"]), 4)  # Both stores, H2/H3 plus H0/H1/H2.
        consents = {p: p.read_bytes() for p in (root.state / "accounting-recovery").glob("*.json")}
        with patch("adp.personal_recovery.engine_digest", return_value="f" * 64), \
             patch("adp.personal_episode.engine_digest", return_value="f" * 64):
            reloaded = load_episode(self.continuation.directory)
            newer = {}
            reloaded._active_view(memory=memory, runtime=self.runtime, _capture=newer)
            self.assertEqual(newer["historical_basis"], basis)
            self.assertEqual(_reader_binding(newer)["reader_engine"], "f" * 64)
            self.assertEqual(newer["historical_engine"], capture["historical_engine"])
        self.assertEqual({p: p.read_bytes() for p in consents}, consents)
        self.assertEqual(memory.inspect(), before)
        # Historical reads may inspect an exact owned pending checkpoint.
        # This confers no SYNCED/live authority and changing the pending
        # document between opening and closing observations must refuse.
        from adp.personal_history import _anchor, _archived_view
        from adp.personal_episode import same_observation
        m = read_private(root.state / "accounting-recovery" / "intent.json")
        archive = read_private(root.state / "accounting-recovery" / "archive.json")
        pending = deepcopy(memory.inspect(recovery=True)); pending["health"] = "RECOVERY_REQUIRED"
        with patch.object(memory, "inspect", return_value=pending):
            historical = _anchor(root, memory, child.descriptor, m, archive)
            self.assertEqual(historical["subject"]["health"], "RECOVERY_REQUIRED")
            with self.assertRaises(ADPError):same_observation(before, historical["subject"])
        changed_pending = deepcopy(pending); changed_pending["recovery_journal"] = "changed-pending-document"
        with patch.object(memory, "inspect", side_effect=[pending, changed_pending]), self.assertRaisesRegex(ADPError, "subject advanced"):
            _archived_view(root, memory=memory, runtime=self.runtime, _child=child)
        master_path = root.state / "accounting-recovery" / "intent.json"
        original = master_path.read_bytes()
        changed = read_private(master_path); changed["engine"] = "e" * 64
        atomic(master_path, encode(changed))
        try:
            with self.assertRaises(ADPError):load_episode(self.continuation.directory)
        finally:atomic(master_path, original)
        stop = self.runtime.directory / (self.row["request"]["id"] + ".stop.json")
        original = stop.read_bytes(); stop.unlink()
        try:
            with self.assertRaises((ADPError, OSError)):child.active(memory=memory, runtime=self.runtime)
        finally:atomic(stop, original)
        branch = "refs/heads/" + memory.branch
        h2, h3 = read_private(root.state / "accounting-recovery" / "archive.json")["result"], basis["checkpoint"]
        for target in (h2, None):
            if target is None:git(memory.pinned_local_remote, "update-ref", "-d", branch, h3)
            else:git(memory.pinned_local_remote, "update-ref", branch, target, h3)
            try:
                with self.assertRaises(ADPError):load_episode(self.continuation.directory)
            finally:git(memory.pinned_local_remote, "update-ref", branch, h3, target or "0" * 40)
        self.assertEqual(memory.inspect(), before)
        self.assertEqual(digest(capture["historical_basis"]), digest(basis))
