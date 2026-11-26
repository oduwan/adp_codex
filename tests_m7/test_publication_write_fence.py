"""Focused D3 callbacks and negative read envelopes, with no live HTTP/workers."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch

from adp.discovery_github import Response
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.guard import ProgressGuard
from adp.guard_types import Baseline, Decision, DecisionKind, Permit, data
from adp.network_git import GitHubCAS, GitHubTarget
from adp.network_http import UPDATE_REFS_MUTATION
from adp.network_objects import ObjectPayload, object_oid
from adp.personal_network import PersonalGitHubTransport
from adp.personal_publication import OriginalRead, PersonalPublication
from adp.policy_types import Operation, Ref
from adp.runtime_limits import RuntimeSettings
from adp.schema import encode, key, require
from adp.storage import atomic


class PublicationWriteFenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="adp-direct-write-fence-")
        self.addCleanup(self.directory.cleanup)
        self.control = Path(self.directory.name)
        self.now, self.revoked, self.seal = 100, False, "actual-inputs"
        self.actor = {"uid": 1001, "config": "synthetic-only"}
        self.addCleanup(patch.stopall)
        patch("adp.personal_network._supported", return_value=True).start()
        patch.object(PersonalGitHubTransport, "_actor", side_effect=lambda: self.actor).start()
        self.child = patch("adp.personal_network.supervised_output", side_effect=self.reply).start()
        self.target = GitHubTarget("repo:disposable", "R_disposable", 17, "owned", "disposable", "work/original")
        self.transport = PersonalGitHubTransport(self.target, runtime_settings=RuntimeSettings())
        self.transport._token, self.transport._context, self.transport._version = "SYNTHETIC_NOT_CREDENTIAL", self.actor, "0.0.0"
        self.service = GitHubCAS(self.target, self.transport, personal=True, runtime_settings=RuntimeSettings())
        self.service.bind_control(self.control)
        self.identifier, self.requirement, self.token = "a" * 64, "b" * 64, "c" * 64
        task = {"key": key("original"), "source_revision": "d" * 40, "iteration": 1}
        state = {"repository_id": self.target.memory_id, "schema_version": 3, "generation": 1,
            "owner": {"id": "owned"}, "progress_guard": {"schema_version": 2, "task_epochs": {task["key"]: 1}, "requirements": {}}}
        action = {"status": "SUBMITTED", "operation": Operation.PUSH}
        state["execution"] = {"actions": {self.identifier: action}}
        context = ProgressGuard._context(state, task)
        reserved = {"actor": "synthetic-only"}
        state["progress_guard"]["requirements"][self.requirement] = {"tasks": [task["key"]], "mode": "normal",
            "active": {"id": self.token, "context": context, "action": reserved, "started": 95, "deadline": 180}}
        self.snapshot = {"health": "SYNCED", "local_owner": True, "local_head": "e" * 40, "remote_head": "e" * 40,
            "state": state, "tasks": {task["key"]: task}, "inbox_count": 0}
        baseline = Baseline(self.target.memory_id, self.requirement, "contract", "gate", task["key"], task["source_revision"],
            1, 1, 1, 0, "f" * 64, ())
        permit = Permit(self.token, Decision(DecisionKind.ALLOW, "synthetic reservation", baseline))
        self.row = {"view": {"issued_at": 90, "expires_at": 190}, "requirement": self.requirement, "action_id": self.identifier,
            "reservation": {"permit": data(permit), "context": context, "action": reserved},
            "credential_binding": self.transport.credential_binding}
        self.claim_path = self.control / "original-claim.json"
        self.claim = {"intent": self.identifier, "source": "exact-synthetic"}
        atomic(self.claim_path, encode(self.claim))
        memory = SimpleNamespace(inspect=Mock(side_effect=lambda: deepcopy(self.snapshot)))
        self.c = SimpleNamespace(episode=True, task_id="original", memory=memory,
            live=Mock(side_effect=AssertionError("No live/history reconstruction per object")), episode_fence=self.episode_fence)
        self.p = PersonalPublication.__new__(PersonalPublication)
        self.p.c, self.p.service, self.p.transport, self.p.target = self.c, self.service, self.transport, self.target
        self.p.clock, self.p._dispatching, self.p._write_basis = lambda: self.now, True, None
        self.p.guard = ProgressGuard(memory, clock=lambda: self.now)
        self.p.guard._snapshot = Mock(side_effect=AssertionError("No second Memory inspection"))
        self.p.journal = SimpleNamespace(inspect=Mock(side_effect=AssertionError("No journal snapshot")))
        self.p.port = SimpleNamespace(service=self.service, _claim_path=lambda _: self.claim_path,
            _claim=lambda *args: self.claim)
        self.legacy = {"immutable": "authenticated-at-entry"}
        patch("adp.personal_read_frame._identity", return_value=("same-serialized-invocation",)).start()
        patch("adp.personal_read_frame.current_source", side_effect=lambda *a, **k:
            require(self.seal == "actual-inputs", "Current source changed")).start()
        from adp.personal_read_frame import _CURRENT
        self.invocation = {"c": self.c}
        token = _CURRENT.set(self.invocation);self.addCleanup(_CURRENT.reset, token)
        self.p.record = lambda **kw: deepcopy(self.row)
        patch("adp.personal_history._archived_view", side_effect=AssertionError("No archived semantic replay")).start()
        patch("adp.personal_history_git.storage_context", return_value=("actual-pinned-context",)).start()
        patch("adp.personal_history_git.object_inventory", return_value=(("1" * 40, "commit", 10),)).start()
        self.transport.authorize_write = self.p.write_authorized
        self.http_calls = []

    def episode_fence(self):
        require(not self.revoked and self.now < 190, "Original episode expired/revoked")

    def inputs(self):
        return self.seal, deepcopy(self.row), {}, ()

    def seed(self, budget):
        self.p._write_basis = {"identity": ("same-serialized-invocation",), "service": self.service, "transport": self.transport,
            "target": self.target, "consent": deepcopy(self.row), "invocation": self.invocation, "subject": deepcopy(self.snapshot),
            "archive": ({"historical": "not-replayed"},), "budget": budget,
            "caps": (budget.end, budget.request_seconds, budget.maximum_calls),
            "historical_objects": ((False, ("actual-pinned-context",), (("1" * 40, "commit", 10),)),)}

    def reply(self, raw, seconds, **kwargs):
        request = json.loads(raw)
        self.assertEqual(request["kind"], "http")
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, 10)
        self.http_calls.append(request)
        if request["path"] == "/graphql":
            body = {"data": {"updateRefs": {"clientMutationId": request["body"]["variables"]["input"]["clientMutationId"]}}}
        else:
            body = {"sha": object_oid("blob", base64.b64decode(request["body"]["content"]))}
        return json.dumps({"status": 200, "headers": [], "body_base64": base64.b64encode(json.dumps(body).encode()).decode()}).encode()

    def blob(self, content=b"one"):
        self.service.upload((ObjectPayload(object_oid("blob", content), "blob", {"encoding": "base64", "content": base64.b64encode(content).decode()}),))

    def test_real_transport_callback_admits_finite_objects_and_cas_with_one_late_memory_read(self):
        with self.service.bounded() as budget:
            self.seed(budget)
            for content in (b"one", b"two", b"three"):self.blob(content)
            self.service.cas("d" * 40, "e" * 40, self.identifier)
            self.assertEqual((budget.calls, budget.transport_calls), (4, 4))
        self.assertEqual(len(self.http_calls), 4)
        self.assertEqual(self.c.memory.inspect.call_count, 4)
        self.c.live.assert_not_called(); self.p.guard._snapshot.assert_not_called(); self.p.journal.inspect.assert_not_called()
        self.assertFalse(self.service.unconfirmed_contexts())

    def test_between_object_canonical_owner_permit_epoch_and_counter_changes_refuse(self):
        changes = ({"local_head": "f" * 40}, {"remote_head": "f" * 40}, {"local_owner": False}, {"inbox_count": 1},
            {"state": {**self.snapshot["state"], "generation": 2}})
        states = []
        for field in ("permit", "epoch", "counters"):
            state = deepcopy(self.snapshot["state"])
            if field == "permit":state["progress_guard"]["requirements"][self.requirement]["active"]["id"] = "f" * 64
            if field == "epoch":state["progress_guard"]["task_epochs"][key("original")] += 1
            if field == "counters":state["progress_guard"]["requirements"][self.requirement]["counters"] = {"failures": 1}
            states.append({"state": state})
        for changed in (*changes, *states):
            original = deepcopy(self.snapshot)
            with self.service.bounded() as budget:
                self.seed(budget)
                self.blob()
                before = len(self.http_calls)
                self.snapshot.update(changed)
                with self.assertRaises((ADPError, OSError)):self.blob(b"refused")
                self.assertEqual(len(self.http_calls), before)
            self.snapshot = original

    def test_claim_revocation_and_credential_drift_refuse_before_child(self):
        for kind in ("claim", "intent", "revocation", "credential", "deadline", "clock-rollback"):
            with self.service.bounded() as budget:
                self.seed(budget)
                before = len(self.http_calls)
                if kind == "claim":atomic(self.claim_path, encode({"intent": "foreign"}))
                if kind == "intent":self.row["view"]["expires_at"] = 191
                if kind == "revocation":self.revoked = True
                if kind == "credential":self.actor = {"uid": 1002}
                if kind == "deadline":self.now = 180
                if kind == "clock-rollback":self.now = 94
                with self.assertRaises((ADPError, OSError)):self.blob()
                self.assertEqual(len(self.http_calls), before)
            atomic(self.claim_path, encode(self.claim)); self.seal = "actual-inputs"
            self.row["view"]["expires_at"] = 190; self.revoked = False; self.now = 100
            self.actor = self.transport._context

    def test_old_stop_marker_and_expired_or_exhausted_budget_never_launch(self):
        for kind in ("marker", "time", "count"):
            before = len(self.http_calls)
            with self.assertRaises((ADPError, OSError)):
                with self.service.bounded() as budget:
                    self.seed(budget)
                    if kind == "marker":atomic(self.service._hazard_path(), encode({"status": "UNKNOWN"}))
                    if kind == "time":budget.end = time.monotonic() - 1
                    if kind == "count":budget.calls = budget.maximum_calls
                    self.blob()
            self.assertEqual(len(self.http_calls), before)
            if kind == "marker":self.service._hazard_path().unlink()


class NegativeReadEnvelopeTests(unittest.TestCase):
    def test_shared_host_fingerprint_preserves_original_format_and_observes_namespace_changes(self):
        from adp.codex_runtime import CodexExecRuntime, _host_identity
        with TemporaryDirectory() as directory:
            runtime = CodexExecRuntime(Path(directory))
            self.assertEqual(runtime.host, _host_identity())
            with patch("adp.codex_runtime.os.readlink", return_value="pid:[synthetic-other]"):
                self.assertNotEqual(_host_identity(), runtime.host)

    def test_original_expected_paths_refuse_before_fetch_and_bind_actual_body(self):
        root = "/repos/owned/disposable/issues/1"
        transport = SimpleNamespace(get=Mock(return_value=Response(200, {"original": True})))
        expected = {root: digest({"body": {"original": True}, "pagination": []})}
        reader = OriginalRead(transport, root)
        self.assertEqual(reader.get(root).status, 200)
        before = transport.get.call_count
        self.assertEqual(reader.get(root + "/comments?per_page=100&page=2").status, 200)
        self.assertEqual(transport.get.call_count, before + 1)
        transport.get.return_value = Response(200, {"original": "changed"})
        with self.assertRaises(ADPError):reader.get(root)

    def service(self, pages):
        target = GitHubTarget("opaque", "R_disposable", 17, "owned", "disposable", "work/original")
        transport = SimpleNamespace(bind_repository=lambda *a: None, runtime_settings=RuntimeSettings())
        service = GitHubCAS(target, transport)
        service._repository = Mock(side_effect=lambda *a: {"refs": pages.pop(0)})
        return service

    @staticmethod
    def page(names, *, more=False, cursor=None, prefix="refs/heads/"):
        return {"nodes": [{"prefix": prefix, "name": name, "target": {"oid": "a" * 40}} for name in names],
            "pageInfo": {"hasNextPage": more, "endCursor": cursor}}

    def test_fresh_refs_complete_and_empty_or_unknown_paging_fail_within_bound(self):
        expected = (Ref("refs/heads/one", "a" * 40), Ref("refs/heads/two", "a" * 40))
        service = self.service([self.page(["one"], more=True, cursor="1"), self.page(["two"]), self.page([], prefix="refs/tags/")])
        self.assertEqual(service.refs(), expected)
        self.assertEqual(service._repository.call_count, 3)  # max(1,2)+max(1,0)
        for pages in ([self.page(["one"], more=True, cursor="1"), self.page(["two"], more=True, cursor="1")],
                [self.page(["one", "one"])], [{"nodes": [], "pageInfo": {}}]):
            service = self.service(pages)
            with self.assertRaises(ADPError):service.refs()
            self.assertLessEqual(service._repository.call_count, 3)

    def test_request_count_lower_bound_unknown_and_supported_tail_do_not_charge_or_renew(self):
        from adp.runtime_limits import Budget
        from adp.personal_storage import PersonalBlocked
        p = PersonalPublication.__new__(PersonalPublication)
        budget = Budget(time.monotonic() + 150)
        p._write_basis = {"budget": budget}
        initial = (budget.end, budget.calls, budget.maximum_calls)
        for count in (0, 2, 127):
            self.assertEqual(p.admit_objects((None,) * count, budget, object()), "LOWER_BOUND_FITS")
            self.assertEqual((budget.end, budget.calls, budget.maximum_calls), initial)
        for count, calls in ((128, 0), (512, 0), (2, 126)):
            budget.calls = calls
            before = (budget.end, budget.calls, budget.maximum_calls)
            with self.assertRaises(PersonalBlocked) as error:p.admit_objects((None,) * count, budget, object())
            self.assertTrue(error.exception.reason.endswith("INSUFFICIENT"))
            self.assertEqual((budget.end, budget.calls, budget.maximum_calls), before)

    def test_mode_envelope_is_fresh_scoped_and_never_turns_a_403_into_absence(self):
        from test_personal_rules import Native
        from adp.personal_rules import enrollment_rules
        f = Native()
        f.service.personal_policy_binding = (None,)  # Previously approved normal mode.
        with self.assertRaises(ADPError):f.service.inspect_ref(writable=True)
        self.assertGreater(len(f.calls), 1)  # Ordinary v1 observation path is preserved.
        f = Native()
        observed = enrollment_rules(f, f.repository, f.owner, "trunk")
        self.assertNotEqual(observed["rules"], "UNKNOWN")
        f = Native(); f.service.inspect_ref(writable=True)
        policy = deepcopy(f.service.personal_policy)
        f.service.personal_policy_binding = (policy,); f.calls.clear()
        self.assertIsNotNone(f.service.inspect_ref(writable=True))
        self.assertLessEqual(len(f.calls), 8)
        f = Native(); f.service.personal_policy_binding = (None,)
        path = f.prefix + "/rules/branches/work%2Ftask"
        f.entries[path] = Response(403, {"message": "Access denied"})
        with self.assertRaises(ADPError):f.service.inspect_ref(writable=True)
        self.assertGreaterEqual(len(f.calls), 1)
