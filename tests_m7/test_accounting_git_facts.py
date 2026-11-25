"""Actual disposable Git objects; private fact reuse confers no authority."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from adp.config import Config
from adp.errors import ADPError
from adp.execution_ports import GitExecutionPort, index_digest
from adp.git import git, value
from adp.personal_git import administration as native_admin
from adp.personal_history_product_git import HistoryReadPort, administration, observe, _FACTS


class AccountingGitFactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="adp-accounting-git-facts-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "product"
        self.root.mkdir()
        self.prepare(self.root)
        self.addCleanup(_FACTS.clear)
        _FACTS.clear()

    def prepare(self, root):
        git(root, "init", "--initial-branch=trunk")
        git(root, "config", "user.name", "Synthetic Owner")
        git(root, "config", "user.email", "owner@example.test")
        git(root, "remote", "add", "forge", "https://github.com/owned/disposable.git")
        (root / "product").write_text("Original source\n")
        (root / "empty").write_bytes(b"")
        git(root, "add", "product", "empty");git(root, "commit", "-m", "Original scope")
        base = value(root, "rev-parse", "HEAD")
        git(root, "checkout", "-b", "work/original")
        (root / "product").write_text("In-scope candidate\n")
        git(root, "add", "product")
        action = {"operation": "COMMIT", "revision": base, "source_ref": "refs/heads/work/original",
            "target": "refs/heads/work/original", "payload": {"subject": "Implement original scope", "body": "Refs #1",
                "index_digest": index_digest(root)}, "status": "OBSERVED", "observation": None}
        git(root, "commit", "-m", "Implement original scope", "-m", "Refs #1")
        revision = value(root, "rev-parse", "HEAD")
        config = Config.discover(root, remote="forge", repository_id="opaque:fixture")
        bound = Path(native_admin(root)["directory"]["path"])
        self.action, self.revision = action, revision
        self.port, self.native = HistoryReadPort(config, bound_git_directory=bound), GitExecutionPort(config, bound_git_directory=bound)

    def test_final_input_seal_observes_child_proof_source_credential_and_consent_drift(self):
        from types import SimpleNamespace
        from adp.personal_read_frame import _inputs
        from adp.schema import key
        from adp.storage import atomic
        state, runtime, evidence = (self.root.parent / name for name in ("private-state", "private-runtime", "private-evidence"))
        for path in (state, runtime, evidence):path.mkdir(mode=0o700)
        request, proof = "a" * 64, "b" * 64
        record, stop = runtime / (request + ".json"), runtime / (request + ".stop.json")
        attestation = evidence / (proof + ".json")
        for path in (record, stop, attestation):atomic(path, b"{}\n")
        workers = [{"request": {"id": request}}]
        from adp.personal_enrollment import governance
        from adp.discovery_schema import digest
        source = {"revision": self.revision, "tree": value(self.root, "rev-parse", "HEAD^{tree}"),
            "source_ref": "refs/heads/work/original", "administration": digest(administration(self.root))}
        run, consent = {"current": "exact", "revision": self.revision}, {"view": {**source, "exact": True}, "credential_binding": "synthetic-only"}
        plan = {"feature": {"branch": "work/original"}, "governance_digest": digest(governance(self.root)),
            "effects": {"marker": str(state / "marker.json")}}
        c = SimpleNamespace(task_id="original", personal=SimpleNamespace(state=state, feature=self.root, directory=state,
            root=SimpleNamespace(state=state, directory=state), plan=plan), track=None,
            runtime=SimpleNamespace(directory=runtime, _path=lambda identifier: runtime / (identifier + ".json")),
            authority=SimpleNamespace(directory=evidence), workers=SimpleNamespace(records=lambda: workers), record=lambda: run)
        owner = SimpleNamespace(c=c, port=self.native, record=lambda **kwargs: consent,
            active={"view": {**source, "source_tree": source["tree"]}, "binding": "synthetic-only", "action": "one"},
            transport=SimpleNamespace(credential_binding="synthetic-only"))
        observed = {"state": {"progress_guard": {"requirements": {"code": {"tasks": [key(c.task_id)],
            "approval": {"reference": "personal:" + proof}}}}}}
        baseline = _inputs(owner, observed, product=False)
        for path in (record, stop, attestation):
            raw = path.read_bytes();atomic(path, b"{ }\n")
            self.assertNotEqual(_inputs(owner, observed, product=False), baseline)
            atomic(path, raw)
            self.assertEqual(_inputs(owner, observed, product=False), baseline)
        raw = stop.read_bytes();stop.unlink()
        self.assertNotEqual(_inputs(owner, observed, product=False), baseline);atomic(stop, raw)
        consent["view"]["exact"] = False
        self.assertNotEqual(_inputs(owner, observed, product=False), baseline);consent["view"]["exact"] = True
        owner.transport.credential_binding = "changed"
        with self.assertRaises(ADPError):_inputs(owner, observed, product=False)
        owner.transport.credential_binding = "synthetic-only"
        raw = (self.root / "product").read_bytes();(self.root / "product").write_bytes(b"Uncommitted source\n")
        with self.assertRaises(ADPError):_inputs(owner, observed, product=False)
        (self.root / "product").write_bytes(raw)
        self.assertEqual(_inputs(owner, observed, product=False), baseline)
        expected = _inputs(owner, observed, product=True);owner.active["action"] = "other"
        self.assertNotEqual(_inputs(owner, observed, product=True), expected)

    def test_original_source_engine_and_physical_administration_remain_fixed(self):
        from types import SimpleNamespace
        from adp.personal_read_frame import _legacy_inputs
        from adp.execution_containment import source_seal
        from adp.personal_recovery import engine_digest
        from adp.schema import encode
        from adp.storage import atomic
        state = self.root.parent / "historical-private";state.mkdir(mode=0o700)
        physical = administration(self.root)
        personal = SimpleNamespace(feature=self.root, state=state, plan={"paths": ["product"],
            "checkout": {"path": str(self.root)}, "administration": deepcopy(physical)})
        atomic(state / "run.json", encode({"feature_administration": physical}))
        master = {"engine": engine_digest(), "view": {"binding": {"evidence": {"seals": {
            "feature": source_seal(self.root), "outside": source_seal(self.root, ("product",)),
            "outer": source_seal(self.root), "admin": "historical refs may legitimately differ"}}}}}
        c = SimpleNamespace(personal=SimpleNamespace(root=personal, descriptor={"base": {"engine": master["engine"]}}))
        expected = _legacy_inputs(c, master)
        raw = (self.root / "product").read_bytes();(self.root / "product").write_bytes(b"Changed old unaccepted candidate\n")
        with self.assertRaisesRegex(ADPError, "unaccepted source changed"):_legacy_inputs(c, master)
        (self.root / "product").write_bytes(raw)
        self.assertEqual(_legacy_inputs(c, master), expected)
        personal.plan["administration"]["root"]["inode"] += 1
        with self.assertRaisesRegex(ADPError, "physical administration changed"):_legacy_inputs(c, master)
        personal.plan["administration"] = deepcopy(physical)
        master["engine"] = "0" * 64
        with self.assertRaisesRegex(ADPError, "recovery source changed"):_legacy_inputs(c, master)

    def test_warm_facts_match_native_reduce_spawns_and_preserve_files_and_refs(self):
        expected = self.native.observe(self.action)
        self.assertEqual(observe(self.port, self.action, self.revision), expected)
        calls = []
        original = git
        def counted(*args, **kwargs):
            calls.append(args[1:]);return original(*args, **kwargs)
        before = (value(self.root, "for-each-ref", "--format=%(refname) %(objectname)"),
            (self.root / ".git" / "index").read_bytes(), (self.root / ".git" / "config").read_bytes(),
            (self.root / "product").read_bytes())
        with patch("adp.git.git", side_effect=counted), patch("adp.execution_ports.git", side_effect=counted), \
             patch("adp.personal_history_product_git.git", side_effect=counted):
            self.assertEqual(self.native.observe(self.action), expected)
            native_calls = len(calls);calls.clear()
            self.assertEqual(observe(self.port, self.action, self.revision), expected)
            warm_calls = len(calls)
        self.assertLess(warm_calls, native_calls)
        self.assertEqual((value(self.root, "for-each-ref", "--format=%(refname) %(objectname)"),
            (self.root / ".git" / "index").read_bytes(), (self.root / ".git" / "config").read_bytes(),
            (self.root / "product").read_bytes()), before)
        print("SYNTHETIC_GIT_READ_SPAWNS native=" + str(native_calls) + " warm=" + str(warm_calls), flush=True)
        self.assertEqual(administration(self.root), native_admin(self.root))
        with self.assertRaises(ADPError):self.port.submit({}, None, None, None)

    def test_ref_action_config_and_physical_permission_changes_are_reobserved(self):
        expected = observe(self.port, self.action, self.revision)
        changed = deepcopy(self.action);changed["payload"]["subject"] = "Unapproved message"
        self.assertNotEqual(observe(self.port, changed, self.revision).status, "PRESENT")
        git(self.root, "config", "adp.synthetic-fresh-input", "changed")
        with patch.object(self.port, "observe", wraps=self.port.observe) as native:
            self.assertEqual(observe(self.port, self.action, self.revision), expected)
            native.assert_called_once()  # Fresh config invalidates decoded facts.
        git(self.root, "checkout", "trunk")
        with self.assertRaises(ADPError):observe(self.port, self.action, self.revision)
        git(self.root, "checkout", "work/original")
        common = self.root / ".git";mode = common.stat().st_mode & 0o777
        common.chmod(0o777)
        try:
            with self.assertRaises(ADPError):observe(self.port, self.action, self.revision)
        finally:common.chmod(mode)
        saved = self.root / "saved-git"
        common.rename(saved);common.symlink_to(saved, target_is_directory=True)
        try:
            with self.assertRaises(ADPError):observe(self.port, self.action, self.revision)
        finally:common.unlink();saved.rename(common)
        self.assertEqual(observe(self.port, self.action, self.revision), expected)
        replacement = "refs/replace/" + self.action["revision"]
        git(self.root, "update-ref", replacement, self.revision, "0" * 40)
        try:
            with patch.object(self.port, "observe", wraps=self.port.observe) as native:
                try:observe(self.port, self.action, self.revision)
                except ADPError:pass  # Native cyclic-ancestry refusal is valid.
                native.assert_called_once()  # Never a warm immutable-fact hit.
        finally:git(self.root, "update-ref", "-d", replacement, self.revision)

    def test_missing_or_corrupt_object_bytes_never_reuse_verified_facts(self):
        expected = observe(self.port, self.action, self.revision)
        blob = value(self.root, "rev-parse", "HEAD:product")
        path = self.root / ".git" / "objects" / blob[:2] / blob[2:]
        original = path.read_bytes();saved = path.with_name(path.name + ".retained")
        path.rename(saved)
        try:
            with self.assertRaises(ADPError):observe(self.port, self.action, self.revision)
        finally:saved.rename(path)
        mode = path.stat().st_mode & 0o777
        path.chmod(0o600)  # Owned disposable loose objects are normally read-only.
        path.write_bytes(b"corrupt synthetic object")
        try:
            with self.assertRaises(ADPError):observe(self.port, self.action, self.revision)
        finally:
            path.write_bytes(original);path.chmod(mode)
        self.assertEqual(observe(self.port, self.action, self.revision), expected)

    def test_large_objects_and_newline_path_framing_use_unchanged_native_observation(self):
        base = self.revision
        (self.root / "product").write_bytes(b"x" * 65537)
        git(self.root, "add", "product")
        action = deepcopy(self.action);action["revision"] = base;action["payload"]["index_digest"] = index_digest(self.root)
        git(self.root, "commit", "-m", action["payload"]["subject"], "-m", action["payload"]["body"])
        revision = value(self.root, "rev-parse", "HEAD")
        expected = self.native.observe(action)
        self.assertEqual(observe(self.port, action, revision), expected)
        self.assertFalse(_FACTS)
        special = Path(self.temporary.name) / "newline\ncomponent"
        special.mkdir();self.prepare(special)
        self.assertEqual(administration(special), native_admin(special))
        self.assertEqual(observe(self.port, self.action, self.revision), self.native.observe(self.action))
