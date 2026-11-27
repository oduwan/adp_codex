"""Issue63 stage controls; no Worker, forge mutation or lifecycle campaign."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import subprocess
import time
from unittest.mock import Mock, patch

from adp.discovery_github import FixtureTransport, Response
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.git import git, value
from adp.personal_enrollment import governance
from adp.personal_history_product_git import administration
from adp.personal_product import PersonalProduct
from adp.personal_publication import PersonalPublication
from adp.personal_read_frame import current_source
from adp.schema import key, require
from discovery_fixtures import issue, responses
from test_config import run


class TrustedProductStageTests(unittest.TestCase):
    def product(self, episode=False):
        p = PersonalProduct.__new__(PersonalProduct)
        p.clock = lambda: 100
        observed = {"state": {"generation": 1}, "tasks": {key("task"): {"source_revision": "a" * 40}}}
        p.c = SimpleNamespace(episode=episode, task_id="task", revision=lambda: "a" * 40,
            live=Mock(return_value=observed), memory=SimpleNamespace(inspect=Mock(return_value=observed)),
            record=lambda: {"phase": "LOCAL_DRAFT_CODE_REVIEWED", "feature_administration": {"admitted": True}},
            workers=SimpleNamespace(fence=Mock()), original_approval=Mock(), verify_local_review=Mock(),
            fresh=Mock(side_effect=AssertionError("No full rediscovery in admitted local helper")))
        p.personal = SimpleNamespace(plan={"feature": {"branch": "work/task"}})
        p.port = SimpleNamespace(_value=Mock(side_effect=AssertionError("No nested worktree probe")))
        p.review_seal = Mock(return_value="accepted-review")
        p.history_binding = Mock(return_value={})
        p.active = {"view": {"issued_at": 90, "expires_at": 190, "generation": 1,
            "revision": "a" * 40, "source_ref": "refs/heads/work/task", "review_binding": "accepted-review"},
            "binding": "credential"}
        p.transport = SimpleNamespace(credential_binding="credential")
        return p, observed

    def test_cold_local_entry_and_nested_live_have_distinct_obligations(self):
        for episode in (False, True):
            with self.subTest(episode=episode):
                p, _ = self.product(episode)
                self.assertEqual(p.local(), "accepted-review")
                p.c.workers.fence.assert_called_once_with()
                p.c.original_approval.assert_called_once_with()
                p.c.verify_local_review.assert_called_once_with()
                for _ in range(3):
                    self.assertIs(p._live_current(), p.active["view"])
                p.c.workers.fence.assert_called_once_with()
                p.c.verify_local_review.assert_called_once_with()
                p.c.fresh.assert_not_called()
                p.port._value.assert_not_called()
                self.assertEqual(p.c.live.call_count, 4)  # Each call obtains current authority.
                self.assertEqual(p.c.memory.inspect.call_count, 1)  # Only the cold post-review checkpoint.
                self.assertTrue(all(call.kwargs["_observed"] is p.c.live.return_value
                    for call in p.review_seal.call_args_list))

    def test_cold_entry_refuses_unaccepted_source_and_unstopped_worker(self):
        p, observed = self.product()
        p.c.record = lambda: {"phase": "CODE"}
        with self.assertRaises(ADPError):p.local()
        p.c.record = lambda: {"phase": "LOCAL_DRAFT_CODE_REVIEWED", "feature_administration": {"admitted": True}}
        p.c.workers.fence.side_effect = ADPError("Worker stop is unconfirmed")
        with self.assertRaisesRegex(ADPError, "stop is unconfirmed"):p.local()
        p.c.verify_local_review.assert_not_called()
        p.c.workers.fence.side_effect = None
        observed["tasks"][key("task")]["source_revision"] = "b" * 40
        with self.assertRaisesRegex(ADPError, "canonical source"):p.local()
        p.review_seal.assert_not_called()

    def test_nested_live_still_refuses_generation_review_credential_and_expiry(self):
        for kind in ("generation", "review", "credential", "expiry"):
            p, observed = self.product()
            if kind == "generation":observed["state"]["generation"] = 2
            if kind == "review":p.review_seal.return_value = "new-unapproved-review"
            if kind == "credential":p.transport.credential_binding = "foreign"
            if kind == "expiry":p.clock = lambda: 190
            with self.subTest(kind=kind), self.assertRaises(ADPError):p._live_current()

    def originals(self):
        name, rid = "owned/project", "17"
        rows = [issue(n, name=name) for n in (1, 2, 3)]
        entries = responses(rows, name=name, rid=rid)
        for n in (2, 3):
            entries[f"/repos/{name}/issues/{n}/dependencies/blocked_by?per_page=100&page=1"] = Response(200, [rows[n-2]])
        p = PersonalPublication.__new__(PersonalPublication)
        p.personal = SimpleNamespace(repository_id=rid, plan={"repository": {"name": name}})
        p.read = FixtureTransport(entries)
        p.service = SimpleNamespace(limits=SimpleNamespace(request_limit=128))
        p.clock = lambda: 100
        p.original_bases = lambda: tuple(f"/repos/{name}/issues/{n}" for n in (1, 2, 3))
        return p

    def test_shared_native_decoder_preserves_edges_without_unrelated_inventory(self):
        p = self.originals()
        issues = []
        raw = p.current_original(_issues=issues)
        self.assertEqual({(i.number, r.target.number) for i in issues for r in i.relations
                          if r.kind == "BLOCKED_BY"}, {(2, 1), (3, 2)})
        self.assertEqual(len(p.read.calls), 18)
        self.assertEqual(len(raw), 15)  # Before/after share one exact receipt key.
        self.assertFalse(any("state=all" in path for path in p.read.calls))

    def test_shared_native_decoder_refuses_incomplete_or_changed_original(self):
        base = "/repos/owned/project/issues/2"
        for kind in ("forbidden", "missing", "malformed", "changed", "pagination"):
            p = self.originals()
            if kind in ("forbidden", "missing"):
                p.read.responses[base + "/dependencies/blocked_by?per_page=100&page=1"] = Response(403 if kind == "forbidden" else 404, None)
            if kind == "malformed":p.read.responses[base] = Response(200, {"number": 2})
            if kind == "changed":
                first = p.read.responses[base]
                p.read.responses[base] = (first, Response(200, {**first.body, "body": "new scope"}))
            if kind == "pagination":p.read.responses[base + "/comments?per_page=100&page=1"] = Response(200, [], (("link", "omitted-next"),))
            with self.subTest(kind=kind), self.assertRaises(ADPError):p.current_original(_issues=[])

    def test_immutable_handoff_is_once_but_remote_and_canonical_checks_remain_fresh(self):
        from test_runtime_limits import service
        p = PersonalPublication.__new__(PersonalPublication)
        observed = {"health": "SYNCED", "local_owner": True, "local_head": "a"*40, "remote_head": "a"*40,
                    "inbox_count": 0, "state": {"generation": 1}, "tasks": {}}
        p.c = SimpleNamespace(episode=False, track=None, task_id="task", runtime=object(),
            memory=SimpleNamespace(inspect=lambda: deepcopy(observed)), live=Mock(return_value=observed),
            record=lambda: {"phase": "LOCAL_DRAFT_CODE_REVIEWED", "coordination": None},
            workers=SimpleNamespace(fence=Mock()), original_approval=Mock(), verify_local_review=Mock(),
            check_administration=Mock())
        p.personal = SimpleNamespace(plan={"checkout": {"path": "/tmp/owned-source", "remote": "forge"},
            "feature": {"prepare": True}, "governance_digest": digest([])})
        p.service, p.target = service(), SimpleNamespace(ref="refs/heads/work/task")
        p.transport = p.service.transport
        p._dispatching, p._write_basis = True, None
        row = {"approval": "exact-consent", "view": {"revision": "a"*40, "canonical_review_binding": "reviewed",
            "original_observation": {"ticket": "admitted"}, "expected_old": None}}
        p.live, p.record, p.review_binding = Mock(), Mock(return_value=row), Mock(return_value="reviewed")
        def original(**kw):
            if kw.get("_capture") is not None:kw["_capture"]["identity"] = ("observed", "same-boundary")
            return {"ticket": "admitted"}
        p.original, p.remote = Mock(side_effect=original), Mock(return_value=None)
        with p.service.bounded() as budget, patch("adp.personal_read_frame.current_source") as source, \
                patch("adp.enrollment.local_checkout", return_value=p.personal.plan["checkout"]), \
                patch("adp.personal_enrollment.governance", return_value=[]):
            p.local()  # The owning operation's actual cold handoff, once.
            p.original.reset_mock()
            entry = (budget, p.c.runtime, p.c.task_id, row["approval"], "a"*40, "reviewed", {})
            with self.assertRaises(ADPError):p.validate_dispatch()  # No entry/restart bypass.
            p.validate_dispatch(_entry=entry);p.validate_dispatch(_entry=entry)
            source.assert_called_once()
            p.c.workers.fence.assert_called_once()
            p.c.verify_local_review.assert_called_once()
            self.assertEqual((p.original.call_count, p.remote.call_count), (2, 2))
            observed["state"]["generation"] = 2
            with self.assertRaises(ADPError):p.validate_dispatch(_entry=entry)
            self.assertEqual(source.call_count, 1)

    def test_actual_source_ref_index_and_worktree_are_checked_at_handoff(self):
        with TemporaryDirectory(prefix="adp-trusted-handoff-") as directory:
            root = Path(directory)
            run(root, "init", "--initial-branch=work")
            run(root, "config", "user.name", "Fixture");run(root, "config", "user.email", "fixture@example.org")
            (root / "product").write_text("candidate\n")
            run(root, "add", "product");run(root, "commit", "-m", "fixture")
            revision = value(root, "rev-parse", "HEAD")
            personal = SimpleNamespace(feature=root, plan={"feature": {"branch": "work"},
                "governance_digest": digest(governance(root))})
            p = SimpleNamespace(c=SimpleNamespace(personal=personal, revision=lambda: revision),
                port=SimpleNamespace(_value=lambda *a: value(root, *a), _git=lambda *a: git(root, *a)),
                transport=SimpleNamespace(credential_binding="operator"))
            consent = {"view": {"revision": revision, "source_tree": value(root, "rev-parse", "HEAD^{tree}"),
                "source_ref": "refs/heads/work", "administration": digest(administration(root))}, "binding": "operator"}
            started = time.perf_counter()
            with patch("subprocess.Popen", wraps=subprocess.Popen) as native:
                current_source(p, consent, product=True)
            print("TRUSTED_SOURCE_HANDOFF " + str({"native_git_processes": native.call_count,
                "wall_seconds": time.perf_counter()-started, "samples": 1}), flush=True)
            for kind in ("SHA", "worktree", "index", "ref"):
                with self.subTest(kind=kind):
                    if kind == "SHA":consent["view"]["revision"] = "f" * 40
                    if kind == "worktree":(root / "product").write_text("not accepted\n")
                    if kind == "index":run(root, "update-index", "--assume-unchanged", "product")
                    if kind == "ref":consent["view"]["source_ref"] = "refs/heads/foreign"
                    with self.assertRaises(ADPError):current_source(p, consent, product=True)
                    consent["view"]["revision"], consent["view"]["source_ref"] = revision, "refs/heads/work"
                    (root / "product").write_text("candidate\n")
                    run(root, "update-index", "--no-assume-unchanged", "product")


    def test_new_ci_scope_is_checked_before_observation_but_submitted_recovery_is_not_readmitted(self):
        p, _ = self.product()
        p.original = Mock(side_effect=ADPError("Original dependency changed"))
        p.observe_ci = Mock(return_value={"status": "UNKNOWN"})
        entry = {"phase": "PREPARED", "approval": "exact", "view": {"revision": "a"*40}}
        p.record = lambda: {"execution": [entry]}
        p.save = Mock()
        with self.assertRaisesRegex(ADPError, "dependency changed"):
            p._execute_selected("CI", entry, "exact")
        p.observe_ci.assert_not_called()
        p.original.reset_mock()
        p.c.workers.fence.reset_mock()
        entry["phase"] = "SUBMITTED"
        self.assertEqual(p._execute_selected("CI", entry, "exact"), {"status": "UNKNOWN"})
        p.original.assert_not_called()
        p.c.workers.fence.assert_not_called()

    def test_retained_review_recovery_precedes_generic_local_admission(self):
        p, _ = self.product()
        p.c.record = lambda: {"phase": "CODE"}  # Generic local would refuse a partial role transition.
        worker = {"request": {"id": "original-stopped-context"}}
        p.c.resume_product_review = Mock(return_value=worker)
        p.c.workers.actual = Mock(return_value=SimpleNamespace(result=SimpleNamespace(approved=True)))
        p.c.stop_workers = Mock()
        p.c.workers.execute = Mock(side_effect=AssertionError("Never launch a replacement"))
        p.original = Mock(side_effect=AssertionError("Retained review has its own cold recovery proof"))
        p.local = Mock(side_effect=lambda **k: require(k.get("genuine") is False, "No generic cold admission before recovery"))
        from contextlib import nullcontext
        p.service = SimpleNamespace(bounded=lambda: nullcontext())
        p.facts = lambda: {"base_sha": "b"*40}
        p.pull = Mock()
        p.validation_binding = lambda: "original-CI"
        entry = {"phase": "PREPARED", "approval": "exact", "view": {"revision": "a"*40,
            "facts": {"base_sha": "b"*40}, "validation": "original-CI"}}
        row = {"execution": [entry]}
        p.record, p.save = lambda: row, Mock()
        self.assertEqual(p._execute_selected("REVIEW", entry, "exact")["status"], "PRODUCT_REVIEWED")
        p.c.workers.execute.assert_not_called()
        p.c.resume_product_review.assert_called_once_with(entry)
        p.c.stop_workers.assert_called_once_with()

    def test_retained_correction_keeps_its_stage_specific_recovery(self):
        p, _ = self.product()
        p.local = Mock(side_effect=AssertionError("In-flight correction is not an accepted-code entry"))
        p.original = Mock(side_effect=AssertionError("Existing Worker admission owns this recovery"))
        p.c.stop_workers = Mock()
        p.correct = Mock(return_value={"status": "CORRECTION_PENDING"})
        entry = {"phase": "PREPARED", "approval": "exact"}
        row = {"correction": {"approval": "exact"}, "execution": [entry]}
        p.record, p.save = lambda: row, Mock()
        self.assertEqual(p._execute_selected("CORRECT", entry, "exact"), {"status": "CORRECTION_PENDING"})
        p.correct.assert_called_once_with(entry)
        p.local.assert_not_called()
        p.c.stop_workers.assert_called_once_with()

    def test_canonical_code_reviewer_sha_cannot_be_reinterpreted(self):
        p = PersonalProduct.__new__(PersonalProduct)
        result = {"outcome": "PASS", "summary": "synthetic exact review", "evidence": ["fixture:review"]}
        task = {"source_revision": "a"*40, "assignments": {n: {"status": "accepted", "generation": 1, "result": result}
                for n in ("scope", "code")}}
        state = {"health": "SYNCED", "local_owner": True,
                 "state": {"generation": 1, "progress_guard": {"task_epochs": {key("task"): 1}}},
                 "tasks": {key("task"): task}}
        workers = {n: {"request": {"id": n, "revision": "a"*40}, "assignment": {"assignment_id": n},
            "requirement": n, "observation": {"synthetic": "stopped"}} for n in ("scope", "code")}
        p.c = SimpleNamespace(task_id="task", memory=SimpleNamespace(inspect=lambda: deepcopy(state)),
            record=lambda: {"original_review": "scope", "code_review": "code"}, worker=lambda name, **kw: workers[name],
            workers=SimpleNamespace(result=lambda worker: result, records=lambda: list(workers.values())), allowed=Mock(),
            guard=SimpleNamespace(_get=lambda *a: {"active": None, "approval": "fixture"}))
        original = p.review_seal()
        workers["code"]["request"]["revision"] = "b"*40
        with self.assertRaisesRegex(ADPError, "different canonical SHA"):p.review_seal()
        self.assertIsInstance(original, str)

    def test_remote_branch_rules_and_original_scope_do_not_inherit_local_trust(self):
        pub = self.originals()
        originals = []
        pub.current_original(_issues=originals)
        pub.original_bases = lambda: ("/repos/owned/project/issues/1",)
        base = "/repos/owned/project"
        pub.read.responses[base + "/branches/trunk"] = Response(200, {"name": "trunk", "protected": False})
        pub.read.responses[base + "/rules/branches/trunk"] = Response(200, [])
        p = PersonalProduct.__new__(PersonalProduct)
        p.publication, p.read = pub, pub.read
        from adp.guard_types import data
        expected = digest(data(originals[0]))
        p.personal = SimpleNamespace(plan={"repository": {"name": "owned/project"}, "owner": {},
            "issue_id": originals[0].identity.issue_id, "native_prerequisites": [], "branch_rules": [{
            "ref": "refs/heads/trunk", "protected": False, "rules": "OBSERVED",
            "required_check_contexts": [], "rules_digest": digest([])}]})
        p.c = SimpleNamespace(track=None, original_matches=lambda issue: digest(data(issue)) == expected)
        p.original()
        route = base + "/rules/branches/trunk"
        for response in (Response(403, {"message": "forbidden"}), Response(200, [{"type": "deletion"}])):
            pub.read.responses[route] = response
            with self.subTest(response=response.status), self.assertRaises(ADPError):p.original()
        pub.read.responses[route] = Response(200, [])
        pub.read.responses[base + "/issues/1/dependencies/blocked_by?per_page=100&page=1"] = Response(200, [issue(3, name="owned/project")])
        with self.assertRaisesRegex(ADPError, "scope or native dependencies"):p.original()

    def test_unselected_runner_keeps_admin_validation_and_selected_wrong_port_refuses(self):
        from adp.personal_runner import PersonalCoordinator
        from adp.personal_storage import INTENT
        c = PersonalCoordinator.__new__(PersonalCoordinator)
        intent = {"phase": "ENROLLED", "approval": "original"}
        c.personal = SimpleNamespace(directory=Path("/synthetic/personal"), feature=Path("/synthetic/feature"),
            repository_id="17", intent=intent,
            plan={"effects": {"marker": "/synthetic/marker"}, "window": {"issued_at": 90, "expires_at": 190}})
        c.track, c.episode, c.clock = None, False, lambda: 100
        observed = {"health": "SYNCED", "local_owner": True, "state": {"generation": 1}}
        c.memory = SimpleNamespace(inspect=lambda: deepcopy(observed))
        c.record, c.check_administration = lambda: None, Mock()
        def private(path):
            return intent if path.name == INTENT else {"schema_version": 1,
                "directory": str(c.personal.directory), "approval": "original"}
        with patch("adp.personal_runner.read_private", side_effect=private):
            c.live()
            c.check_administration.assert_called_once_with(None)
            c.publication = SimpleNamespace(c=c, personal=c.personal,
                cfg=SimpleNamespace(root=c.personal.feature), target=SimpleNamespace(memory_id="17"))
            c.live()
            c.check_administration.assert_called_once_with(None)
            c.publication.cfg.root = Path("/unadmitted/feature")
            with self.assertRaisesRegex(ADPError, "differs from the admitted"):c.live()
            c.publication.cfg.root = c.personal.feature
            observed["local_owner"] = False
            with self.assertRaisesRegex(ADPError, "M1 owner"):c.live()
