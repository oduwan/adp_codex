"""Focused invocation facts and live fences, under the approved D4 trust model.

Malicious same-UID historical changes INSIDE a qualified invocation are outside
this model. The old ABA replay tests are retired, not reported as passing that
excluded threat. Entry/restart corruption and actual receipt protection remain.
"""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.personal_read_frame import (_CURRENT, _READ_ONLY, archive, forbid_writes,
    protected_runtime, publication_live, qualification, reader_engine)
from adp.schema import require


class AccountingReadFrameTests(unittest.TestCase):
    def test_terminal_runtime_needs_current_bound_stop_receipt(self):
        from contextlib import nullcontext
        from adp.codex_runtime import CodexExecRuntime
        from adp.execution_types import RuntimeStatus, WorkerResult
        from adp.guard_types import Outcome, data
        from adp.schema import encode
        from adp.storage import atomic
        for personal in (False, True):
            with self.subTest(personal=personal), TemporaryDirectory() as directory:
                c, _, _, _ = self.fixture()
                runtime = CodexExecRuntime(Path(directory));identifier = "e" * 64
                raw = {"host": runtime.host, "request_digest": "a" * 64, "status": "COMPLETED",
                    "pid": 51001, "start_time": "synthetic-only", "context": "synthetic:" + identifier,
                    "result": data(WorkerResult(Outcome.PASS, True, ("code",), "Synthetic only")),
                    "elapsed": 1, "samples": 1, "payload_bytes": 100, "stopped": True}
                runtime._save(identifier, raw)
                path = runtime.directory / (identifier + ".stop.json")
                receipt = {"request_digest": raw["request_digest"], "pid": raw["pid"],
                    "status": "EXITED", "stopped": True, "cli_exit": 0}
                original = runtime._path(identifier).read_bytes()
                with qualification(c) if personal else nullcontext():
                    missing = runtime.observe(identifier)
                    self.assertEqual(missing.status, RuntimeStatus.UNKNOWN)
                    self.assertIs(missing.stopped, False)
                    atomic(path, encode({**receipt, "status": "UNKNOWN", "stopped": False}))
                    self.assertEqual(runtime.observe(identifier).status, RuntimeStatus.UNKNOWN)
                    atomic(path, encode(receipt))
                    complete = runtime.observe(identifier)
                    self.assertEqual(complete.status, RuntimeStatus.COMPLETED)
                    self.assertIs(complete.stopped, True)
                    for changed in ({"pid": 51002}, {"request_digest": "b" * 64}):
                        atomic(path, encode({**receipt, **changed}))
                        with self.assertRaises(ADPError):runtime.observe(identifier)
                    path.unlink()
                    self.assertEqual(runtime._path(identifier).read_bytes(), original)
                    runtime._save(identifier, {**raw, "status": "RUNNING", "stopped": False})
                    with patch("adp.codex_runtime._start_time", return_value="synthetic-only"):
                        self.assertEqual(runtime.observe(identifier).status, RuntimeStatus.RUNNING)
                    runtime._save(identifier, {**raw, "status": "UNSUPPORTED_RUNTIME", "pid": None, "result": None})
                    self.assertEqual(runtime.observe(identifier).status, RuntimeStatus.UNSUPPORTED_RUNTIME)

    def test_absent_new_runtime_is_not_started_without_creating_evidence(self):
        from adp.codex_runtime import CodexExecRuntime
        from adp.execution_types import RuntimeStatus
        c, _, _, _ = self.fixture()
        with TemporaryDirectory() as directory:
            root = Path(directory);runtime = CodexExecRuntime(root / "runtime");identifier = "f" * 64
            with qualification(c):
                self.assertEqual(runtime.observe(identifier).status, RuntimeStatus.NOT_STARTED)
                self.assertIsNone(runtime._stop_receipt(identifier, {}))
                self.assertFalse(runtime.directory.exists())
                runtime.directory.mkdir(mode=0o777);runtime.directory.chmod(0o777)
                with self.assertRaises(ADPError):runtime.observe(identifier)
                runtime.directory.rmdir();runtime.directory.symlink_to(root / "absent")
                with self.assertRaises(ADPError):runtime.observe(identifier)
                runtime.directory.unlink();runtime.directory.write_text("not a directory")
                with self.assertRaises(ADPError):runtime.observe(identifier)

    def test_writes_cross_thread_reuse_and_exceptions_cannot_escape_the_read_boundary(self):
        from adp.memory import Memory
        from adp.personal_authority import PersonalAuthority
        from adp.personal_publication import PersonalPublication
        from adp.personal_runner import PersonalCoordinator
        from adp.personal_workers import PersonalWorkers
        from adp.codex_runtime import CodexExecRuntime
        from adp.network_git import GitHubCAS, GitHubTarget
        from adp.personal_product import PersonalProduct
        c, p, _, _ = self.fixture()
        memory = Memory.__new__(Memory)
        network = GitHubCAS(GitHubTarget("opaque:fenced", "R_fenced", 1, "owned", "disposable", "work/original"),
            SimpleNamespace(bind_repository=lambda *identity: None))
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
            (network.request, ("GET", "/synthetic"), {}),
            (PersonalProduct.save, (object(), {}), {}),
            (PersonalProduct.write_authorized, (object(),), {}),
            (PersonalProduct.local, (object(),), {"genuine": True}),
            (PersonalPublication.live, (SimpleNamespace(c=c),), {"review": False}))
        def read(**kwargs):
            self.assertTrue(_READ_ONLY.get())
            for function, args, keywords in calls:
                with self.subTest(caller=function.__qualname__), self.assertRaisesRegex(ADPError, "cannot admit, write or execute"):
                    function(*args, **keywords)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(copy_context().run, archive, c.personal.root, c.memory, None, c.personal)
                with self.assertRaises(ADPError):future.result()
            raise OSError("Synthetic read interruption")
        p._live_current = read
        with self.assertRaises(OSError):publication_live(p)
        self.assertIsNone(_CURRENT.get())
        self.assertFalse(_READ_ONLY.get())

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

    def test_initial_protected_read_requires_complete_bytes_and_safe_opened_metadata(self):
        from adp.config import load_json
        from adp.ticket_preparation import TicketArchive
        import os
        with TemporaryDirectory() as directory:
            root = Path(directory);path = root / "receipt.json"
            path.write_bytes(b'{} trailing');path.chmod(0o600)
            with patch("adp.config.os.read", return_value=b'{}'), self.assertRaises(ADPError):
                load_json(path, protected=True)
            path.write_bytes(b'{"original":true}')
            self.assertEqual(load_json(path, protected=True), {"original": True})
            with self.assertRaises(ADPError):load_json(path, path.stat().st_size - 1, protected=True)
            path.chmod(0o644)
            with self.assertRaises(ADPError):load_json(path, protected=True)
            self.assertEqual(load_json(path), {"original": True})  # Ordinary signed reads unchanged.
            path.chmod(0o600)
            with patch("adp.config.os.getuid", return_value=os.getuid() + 1), self.assertRaises(ADPError):
                load_json(path, protected=True)
            link = root / "hardlink";os.link(path, link)
            with self.assertRaises(ADPError):load_json(path, protected=True)
            link.unlink();link.symlink_to(path)
            with self.assertRaises(ADPError):load_json(link, protected=True)
            archive = TicketArchive(root / "tickets", protected_roots=(root / "product",))
            ticket = archive.directory / "original-proof.json"
            ticket.write_bytes(b'{} trailing');ticket.chmod(0o600)
            with patch("adp.ticket_preparation.os.read", return_value=b'{}'), self.assertRaises(ADPError):
                archive._read(ticket)

    def fixture(self):
        receipt = {"archive": "exact", "result": "a" * 40}
        old = {"mode": "STOP_UNSAFE", "counters": {"attempts": 1}}
        task = {"original": {"status": "UNKNOWN"}}
        relation = {"parent_requirement": "old", "archive": digest(receipt), "parent_task": "original",
            "parent_guard": digest(old), "parent_task_digest": digest(task["original"]), "usage": {"requests": {}}}
        guard = {"schema_version": 2, "requirements": {"old": old}, "task_epochs": {"original": 1},
            "accounting_continuation": relation}
        observed = {"health": "SYNCED", "local_owner": True, "local_head": "a" * 40, "remote_head": "a" * 40,
            "state": {"generation": 1, "owner": "original", "progress_guard": guard}, "tasks": task, "inbox_count": 0}
        master = {"view": {"binding": {"task_key": "original"}}, "state": deepcopy(observed["state"]),
            "result_state": deepcopy(observed["state"]), "result_tasks": deepcopy(task)}
        data = {"valid": True, "full": 0, "now": 100, "revoked": False}
        memory = SimpleNamespace(config=SimpleNamespace(root=Path("/synthetic/memory")), common=Path("/synthetic/common"),
            control=Path("/synthetic/control"), pinned_local_remote=Path("/synthetic/remote"),
            inspect=lambda **kw: deepcopy(observed))
        personal = SimpleNamespace(root=object(), repository_id="opaque", intent={"episode": 1}, descriptor={"episode": 1})
        c = SimpleNamespace(episode=True, task_id="original", personal=personal, memory=memory,
            runtime=SimpleNamespace(host="synthetic", directory=Path("/synthetic/runtime")))
        def fence():
            require(data["now"] < 150 and not data["revoked"], "Expired/revoked consent")
        c.episode_fence = fence
        c.clock = lambda: data["now"]
        def full(**kw):
            self.assertTrue(protected_runtime(), "Protection must start before the cold proof")
            data["full"] += 1
            require(data["valid"], "Initial historical evidence unverified")
            kw["_capture"].update(archive=(master, receipt, {"original-context"}, deepcopy(observed), [{"worker": 1}]),
                historical_basis={"schema_version": 1, "checkpoint": "a" * 40,
                    "relation_digest": digest({k: v for k, v in relation.items() if k != "usage"})},
                historical_engine="b" * 64, subject=deepcopy(observed), installed=("verified H3", {}))
            return relation, {"original-context"}, deepcopy(observed)
        personal._active_view = full
        p = SimpleNamespace(c=c, consent={"view": {"issued_at": 50, "expires_at": 150}})
        p.record = lambda **kw: deepcopy(p.consent)
        p._live_current = lambda **kw: (fence(), deepcopy(p.consent))[1]
        patcher = patch("adp.personal_history.git", return_value=b"");patcher.start();self.addCleanup(patcher.stop)
        return c, p, observed, data

    def test_one_cold_entry_fresh_projection_and_restart_qualification(self):
        c, p, observed, data = self.fixture()
        with qualification(c):
            for _ in range(5):
                cap = {}
                proof = archive(c.personal.root, c.memory, None, c.personal, _capture=cap)
                self.assertEqual(proof[3], observed)
                self.assertEqual(cap["subject"], observed)
                self.assertEqual(cap["installed"], ("verified H3", {}))
                proof[0]["result_tasks"].clear()
            self.assertEqual(data["full"], 1)
            observed["state"]["progress_guard"]["accounting_continuation"]["usage"]["requests"]["new"] = "counted"
            archive(c.personal.root, c.memory, None, c.personal)
            self.assertEqual(data["full"], 1)
        self.assertIsNone(_CURRENT.get())
        publication_live(p)
        self.assertEqual(data["full"], 2)
        data["valid"] = False
        with self.assertRaises(ADPError):publication_live(p)
        self.assertIsNone(_CURRENT.get())

    def test_current_parent_owner_generation_tasks_guards_and_relation_cannot_drift(self):
        c, _, observed, _ = self.fixture()
        with qualification(c):
            baseline = deepcopy(observed)
            changes = [lambda: observed.update(health="DIVERGED"), lambda: observed["state"].update(owner="foreign"),
                lambda: observed["state"].update(generation=2), lambda: observed["tasks"]["original"].update(status="PASS"),
                lambda: observed["state"]["progress_guard"]["requirements"]["old"].update(mode="normal"),
                lambda: observed["state"]["progress_guard"]["task_epochs"].update(original=2),
                lambda: observed["state"]["progress_guard"]["accounting_continuation"].update(archive="changed")]
            for change in changes:
                change()
                with self.assertRaises(ADPError):archive(c.personal.root, c.memory, None, c.personal)
                observed.clear();observed.update(deepcopy(baseline))
            observed["state"]["owner"] = None  # History after authorized handoff is observable, never ALLOW.
            archive(c.personal.root, c.memory, None, c.personal)

    def test_cross_thread_identity_exception_cleanup_and_read_only_barrier(self):
        c, p, _, _ = self.fixture()
        with qualification(c):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(ADPError):pool.submit(copy_context().run, publication_live, p).result()
            token = _READ_ONLY.set(True)
            try:
                with self.assertRaises(ADPError):forbid_writes()
            finally:_READ_ONLY.reset(token)
            forbid_writes()  # Facts alone never hold a write capability or ban normal authorized operations.
        p._live_current = lambda **kw: (_ for _ in ()).throw(ValueError("ordinary product exception"))
        with self.assertRaises(ValueError):publication_live(p)
        self.assertIsNone(_CURRENT.get());self.assertFalse(_READ_ONLY.get())

    def test_initial_corruption_and_missing_history_refuse_before_operation(self):
        c, p, _, data = self.fixture()
        for failure in (ADPError("Corrupted historical object"), FileNotFoundError("Missing original receipt")):
            with patch.object(c.personal, "_active_view", side_effect=failure), patch.object(p, "_live_current") as body:
                with self.assertRaises(type(failure)):publication_live(p)
                body.assert_not_called()
        self.assertEqual(data["full"], 0)

    def test_reader_digest_is_pure_invocation_data_and_not_an_allow_decision(self):
        c, _, _, _ = self.fixture()
        with patch("adp.personal_recovery.engine_digest", return_value="c" * 64) as engine:
            with qualification(c):
                capture = deepcopy(_CURRENT.get()["capture"])
                for _ in range(8):self.assertEqual(reader_engine(capture), "c" * 64)
                self.assertEqual(engine.call_count, 1)
                capture["historical_engine"] = "d" * 64
                with self.assertRaises(ADPError):reader_engine(capture)
        self.assertFalse(protected_runtime())

    def test_nested_different_receivers_get_independent_scopes(self):
        c, _, _, data = self.fixture()
        other, _, _, second = self.fixture()
        with qualification(c):
            parent = _CURRENT.get()
            with qualification(other):self.assertIs(_CURRENT.get()["c"], other)
            self.assertIs(_CURRENT.get(), parent)
        self.assertEqual((data["full"], second["full"]), (1, 1))

    def test_expiry_revocation_are_fresh_without_nested_worktree_admission(self):
        c, p, _, data = self.fixture()
        with qualification(c):
            for name, changed in (("now", 150), ("revoked", True)):
                original = data[name];data[name] = changed
                with self.assertRaises(ADPError):publication_live(p)
                data[name] = original

    def test_canonical_change_during_read_is_not_adopted_by_closing_fence(self):
        _, p, observed, _ = self.fixture()
        def read(**kw):
            observed["local_head"] = "c" * 40
            return deepcopy(p.consent)
        p._live_current = read
        with self.assertRaises(ADPError):publication_live(p)
        c, p, observed, data = self.fixture()
        def changed_generation(**kw):
            observed["state"]["generation"] += 1
            return deepcopy(p.consent)
        p._live_current = changed_generation
        with self.assertRaises(ADPError):publication_live(p)
        p._live_current = lambda **kw: {**p.consent, "unapproved": True}
        with self.assertRaises(ADPError):publication_live(p)
        p._live_current = lambda **kw: deepcopy(p.consent)
        c.episode_fence = lambda: None  # A longer parent grant cannot extend this operation consent.
        def elapsed(**kw):
            data["now"] = 150
            return deepcopy(p.consent)
        p._live_current = elapsed
        with self.assertRaises(ADPError):publication_live(p)
        from adp.personal_read_frame import product_live
        for field in ("view", "binding", "action", "reservation"):
            with self.subTest(product_context=field):
                c, p, _, _ = self.fixture()
                p.active = {"view": {"issued_at": 50, "expires_at": 150}, "binding": "exact",
                            "action": "original", "reservation": {"permit": "exact"}}
                def product_read(**kwargs):
                    if field == "view":p.active["view"]["expires_at"] = 1000
                    elif field == "reservation":p.active[field]["permit"] = "unapproved"
                    else:p.active[field] = "changed"
                    return p.active["view"]
                p._live_current = product_read
                with self.assertRaises(ADPError):product_live(p)
                self.assertIsNone(_CURRENT.get())

    def test_new_personal_runtime_receipts_keep_permissions_and_signed_reads_unchanged(self):
        from adp.codex_runtime import CodexExecRuntime
        from adp.storage import atomic
        from adp.schema import encode
        c, _, _, _ = self.fixture()
        with TemporaryDirectory() as temporary:
            runtime = CodexExecRuntime(Path(temporary));identifier = "f" * 64
            path = runtime._path(identifier)
            with qualification(c):
                atomic(path, encode({"actual": "newly-created"}))
                self.assertEqual(runtime._read(identifier), {"actual": "newly-created"})
                runtime.directory.chmod(0o777)
                with self.assertRaises(ADPError):runtime._read(identifier)
                runtime.directory.chmod(0o700)
                path.chmod(0o644)
                with self.assertRaises(ADPError):runtime._read(identifier)
            self.assertEqual(runtime._read(identifier), {"actual": "newly-created"})

    def test_ticket_archive_opened_bytes_preserve_bounds_and_permissions(self):
        from adp.ticket_preparation import TicketArchive, MAX_ARTIFACT
        from adp.personal_storage import LIMIT
        from adp.storage import atomic
        import os
        with TemporaryDirectory() as temporary:
            root = Path(temporary);a = TicketArchive(root / "archive", protected_roots=(root / "product",))
            path = a.directory / "original-proof.json"
            raw = b'{"original":"' + b'x' * (LIMIT + 1) + b'"}\n';atomic(path, raw)
            self.assertLess(len(raw), MAX_ARTIFACT);self.assertEqual(a._read(path), raw)
            native_open = os.open
            def change(*args, **kw):
                fd = native_open(*args, **kw);path.chmod(0o400);return fd
            with patch("adp.ticket_preparation.os.open", side_effect=change):
                with self.assertRaises(ADPError):a._read(path)
