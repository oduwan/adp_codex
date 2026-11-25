"""Deterministic private read-boundary negatives; no workers or forge calls."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.errors import ADPError
from adp.personal_read_frame import _CURRENT, active, archive, product_live, publication_live
from adp.schema import require


class AccountingReadFrameTests(unittest.TestCase):
    def fixture(self):
        observed = {"health": "SYNCED", "local_owner": True, "local_head": "a" * 40, "remote_head": "a" * 40,
            "state": {"generation": 1, "owner": "original", "guard": "exact"}, "tasks": {"original": {}}, "inbox_count": 0}
        inputs = {"raw": "original", "valid": True, "now": 100, "expires": 200, "revoked": False,
            "full": 0, "reads": 0, "events": [], "seal": {"review": "exact"}, "during_close": None}
        def inspect():
            inputs["reads"] += 1
            return deepcopy(observed)
        def fence():
            require(inputs["now"] < inputs["expires"] and not inputs["revoked"], "Consent expired or revoked")
        personal = SimpleNamespace(root=SimpleNamespace(intent={"original": 1}), intent={"episode": 1},
            descriptor={"binding": 1}, repository_id="opaque:owned")
        c = SimpleNamespace(personal=personal, task_id="personal:original", episode=True,
            memory=SimpleNamespace(config=SimpleNamespace(root=Path("/synthetic/memory")), common=Path("/synthetic/common"),
                control=Path("/synthetic/control"), inspect=inspect),
            runtime=SimpleNamespace(host="exact-host", directory=Path("/synthetic/runtime")),
            clock=lambda: inputs["now"], episode_fence=fence)
        def full(**kwargs):
            self.assertIsNone(_CURRENT.get(), "Closing proof must not validate itself from a frame")
            inputs["full"] += 1
            inputs["events"].append("FULL")
            if inputs["full"] == 2 and inputs["during_close"]:
                if inputs["during_close"] == "publication_expiry":inputs["now"] = 150
                else:inputs["seal"][inputs["during_close"]] = "changed during closing proof"
            require(inputs["valid"], "Raw evidence unverified")
            proof = ({"raw": inputs["raw"]}, {"archive": 1}, {"old-context"}, inspect(), [{"worker": 1}])
            kwargs["_capture"]["archive"] = proof
            fence()
            return {"lineage": inputs["raw"]}, {"old-context"}, inspect()
        personal._active_view = full
        publication = SimpleNamespace(c=c)
        probe = patch("adp.personal_read_frame._inputs", side_effect=lambda *args, **kwargs: deepcopy(inputs["seal"]))
        probe.start();self.addCleanup(probe.stop)
        return c, publication, observed, inputs

    def test_independent_full_boundaries_fresh_nested_reads_and_no_cross_call_cache(self):
        c, p, _, inputs = self.fixture()
        def read(**kwargs):
            self.assertEqual(kwargs, {"review": True})
            inputs["events"].append("BODY")
            for _ in range(10):
                before = inputs["reads"]
                factual = active(c.personal, c.memory, None)
                self.assertGreater(inputs["reads"], before)
                self.assertEqual(factual[0], {"lineage": "original"})
                factual[0]["lineage"] = "caller cannot change proof"
                self.assertEqual(archive(c.personal.root, c.memory, None, c.personal)[0], {"raw": "original"})
                self.assertIsNone(active(c.personal, object(), None))
            return {"publication": "exact", "view": {"issued_at": 50, "expires_at": 150}}
        p._live_current = read
        self.assertEqual(publication_live(p), {"publication": "exact", "view": {"issued_at": 50, "expires_at": 150}})
        self.assertEqual(inputs["full"], 2)
        # General safety invariant: the LAST actual full proof follows the
        # LAST semantic body. The historical 324 order FULL/BODY/FULL/BODY
        # violates it regardless of the number of nested role checks.
        self.assertGreater(max(i for i, e in enumerate(inputs["events"]) if e == "FULL"),
            max(i for i, e in enumerate(inputs["events"]) if e == "BODY"))
        self.assertEqual(inputs["events"].count("BODY"), 1)
        self.assertIsNone(_CURRENT.get())
        publication_live(p)
        self.assertEqual(inputs["full"], 4)
        inputs["valid"] = False
        with self.assertRaises(ADPError):publication_live(p)
        self.assertIsNone(_CURRENT.get())
        c, p, _, inputs = self.fixture()
        p.active = {"view": {"issued_at": 50, "expires_at": 150}, "binding": "exact", "action": "original", "reservation": "exact"}
        def product_read(**kwargs):
            self.assertEqual(kwargs, {"genuine": False})
            active(c.personal, c.memory, None)
            return p.active["view"]
        p._live_current = product_read
        result = product_live(p)
        self.assertEqual(result, p.active["view"])
        self.assertIsNot(result, p.active["view"])
        result["expires_at"] = 1000
        self.assertEqual(p.active["view"]["expires_at"], 150)
        self.assertEqual(inputs["full"], 2)

    def test_changed_raw_source_identity_canonical_or_final_review_never_returns_success(self):
        for change in ("raw", "missing", "raw_second", "missing_second", "host", "descriptor", "coordinator", "head", "owner", "task", "inbox", "guard", "expiry", "revoked", "review", "publication_expiry"):
            with self.subTest(change=change):
                c, p, observed, inputs = self.fixture()
                parts, bodies = [], []
                def read(**kwargs):
                    bodies.append(True)
                    inputs["events"].append("BODY")
                    for phase in (1, 2):
                        parts.append(phase)
                        if phase == 1:
                            if change == "raw":inputs["raw"] = "changed-stop/source/activation"
                            elif change == "missing":inputs["valid"] = False
                            elif change == "host":c.runtime.host = "foreign"
                            elif change == "descriptor":c.personal.descriptor["binding"] = 2
                            elif change == "coordinator":p.c = object()
                            elif change == "head":observed["remote_head"] = "b" * 40
                            elif change == "owner":observed["local_owner"] = False
                            elif change == "task":observed["tasks"]["original"] = {"assignment": "changed"}
                            elif change == "inbox":observed["inbox_count"] = 1
                            elif change == "guard":observed["state"]["guard"] = "changed"
                            elif change == "expiry":inputs["now"] = 200
                            elif change == "revoked":inputs["revoked"] = True
                            elif change in ("review", "publication_expiry"):inputs["during_close"] = change
                        if phase == 2 and change == "raw_second":inputs["raw"] = "changed-after-last-nested-check"
                        if phase == 2 and change == "missing_second":inputs["valid"] = False
                        active(c.personal, c.memory, None)
                    return {"view": {"issued_at": 50, "expires_at": 150}}
                p._live_current = read
                with self.assertRaises(ADPError):publication_live(p)
                self.assertEqual(len(bodies), 1)
                if change in ("raw", "missing", "raw_second", "missing_second"):
                    self.assertEqual(parts, [1, 2])  # Closing proof follows even the last nested read.
                self.assertIsNone(_CURRENT.get())
        for field in ("source", "review", "runtime", "credential", "progress-proof", "adoption"):
            with self.subTest(changed_during_closing=field):
                c, p, _, inputs = self.fixture()
                def read(**kwargs):
                    inputs["during_close"] = field
                    return {"view": {"issued_at": 50, "expires_at": 150}}
                p._live_current = read
                with self.assertRaises(ADPError):publication_live(p)
                self.assertIsNone(_CURRENT.get())
        for field in ("view", "binding", "action", "reservation"):
            with self.subTest(product_context=field):
                c, p, _, _ = self.fixture()
                p.active = {"view": {"issued_at": 50, "expires_at": 150}, "binding": "exact", "action": "original", "reservation": {"permit": "exact"}}
                def product_read(**kwargs):
                    if field == "view":p.active["view"]["expires_at"] = 1000
                    elif field == "reservation":p.active[field]["permit"] = "unapproved"
                    else:p.active[field] = "changed"
                    return p.active["view"]
                p._live_current = product_read
                with self.assertRaises(ADPError):product_live(p)
                self.assertIsNone(_CURRENT.get())

    def test_writes_cross_thread_reuse_and_exceptions_cannot_escape_the_read_boundary(self):
        from adp.memory import Memory
        from adp.personal_authority import PersonalAuthority
        from adp.personal_publication import PersonalPublication
        from adp.personal_runner import PersonalCoordinator
        from adp.personal_workers import PersonalWorkers
        from adp.codex_runtime import CodexExecRuntime
        from adp.network_git import GitHubCAS
        from adp.personal_product import PersonalProduct
        c, p, _, _ = self.fixture()
        memory = Memory.__new__(Memory)
        calls = ((memory.initialize, (), {}), (memory._start, (), {}), (memory._checkpoint, (None, {}, {}), {}),
            (memory._write_files, ({}, {}), {}), (memory._finish, ({},), {}), (memory.recover, (), {}),
            (memory.deliver, ({},), {}), (memory._deliver, ({}, {}, {}), {}), (memory.cleanup_inbox, (), {}),
            (memory.discard_inbox, ("original",), {}),
            (PersonalAuthority.fence_accounting, (object(),), {}),
            (PersonalAuthority._proof, (object(), "purpose", "subject", "kind", {}, "principal"), {}),
            (PersonalCoordinator.requirement, (object(), "develop"), {}),
            (PersonalCoordinator.save, (object(), {}), {}),
            (PersonalPublication.save, (object(), {}), {}),
            (PersonalWorkers.save, (object(), {}), {}),
            (CodexExecRuntime.dispatch, (object(), object()), {}),
            (GitHubCAS.request, (object(), "GET", "/synthetic"), {}),
            (PersonalProduct.save, (object(), {}), {}),
            (PersonalProduct.write_authorized, (object(),), {}),
            (PersonalProduct.live, (SimpleNamespace(c=c),), {"genuine": True}),
            (PersonalPublication.live, (object(),), {"review": False}))
        def read(**kwargs):
            for function, args, keywords in calls:
                with self.assertRaisesRegex(ADPError, "cannot admit, write or execute"):
                    function(*args, **keywords)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(copy_context().run, active, c.personal, c.memory, None)
                with self.assertRaises(ADPError):future.result()
            raise OSError("Synthetic read interruption")
        p._live_current = read
        with self.assertRaises(OSError):publication_live(p)
        self.assertIsNone(_CURRENT.get())

    def test_existing_episode_gate_refuses_missing_or_changed_baseline_without_admission(self):
        from adp.guard_schema import requirement_id
        from adp.guard_types import data
        from adp.personal_runner import PersonalCoordinator
        c = PersonalCoordinator.__new__(PersonalCoordinator)
        c.episode, c.task_id = True, "original"
        c.personal = SimpleNamespace(plan={"criterion": "original-requirement"})
        expected = data(c.specification("develop"))
        item = {**deepcopy(expected), "tasks": ["original-key"]}
        c.guard = SimpleNamespace(_snapshot=lambda *args: ({}, {"key": "original-key"}, item))
        wanted = requirement_id(expected["contract"], expected["gate"])
        self.assertEqual(c.review_requirement(), wanted)
        for name in ("contract", "gate", "acceptance", "dependencies", "limits", "tasks"):
            original = item[name]
            item[name] = [] if type(original) is list else {} if type(original) is dict else "changed"
            if item[name] == original:item[name] = ["unapproved"]
            with self.subTest(field=name), self.assertRaises(ADPError):c.review_requirement()
            item[name] = original
        def missing(*args):raise ADPError("Missing original gate")
        c.guard._snapshot = missing
        with self.assertRaises(ADPError):c.review_requirement()

    def test_private_seal_preserves_bytes_permissions_and_honest_absence(self):
        from tempfile import TemporaryDirectory
        from adp.personal_read_frame import _private_digest
        import hashlib
        import os
        with TemporaryDirectory(prefix="adp-private-read-seal-") as temporary:
            p = Path(temporary) / "receipt"
            self.assertIsNone(_private_digest(p))
            p.write_bytes(b"original\n");p.chmod(0o600)
            self.assertEqual(_private_digest(p), hashlib.sha256(p.read_bytes()).hexdigest())
            first = _private_digest(p)
            with patch("adp.personal_read_frame.os.read", return_value=b"short"):
                with self.assertRaises(ADPError):_private_digest(p)
            p.write_bytes(b"changed\n")
            self.assertNotEqual(_private_digest(p), first)
            p.chmod(0o644)
            with self.assertRaises(ADPError):_private_digest(p)
            p.chmod(0o600)
            hardlink = Path(temporary) / "hardlink";os.link(p, hardlink)
            try:
                with self.assertRaises(ADPError):_private_digest(p)
            finally:hardlink.unlink()
            link = Path(temporary) / "symlink";link.symlink_to(p)
            with self.assertRaises(ADPError):_private_digest(link)
            from adp.personal_storage import LIMIT
            p.write_bytes(b"x" * (LIMIT + 1))
            with self.assertRaises(ADPError):_private_digest(p)
            fifo = Path(temporary) / "fifo";os.mkfifo(fifo, 0o600)
            with self.assertRaises(ADPError):_private_digest(fifo)
