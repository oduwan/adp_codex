"""REPORT phase boundaries with synthetic receipts; no workers or live HTTP."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.codex_runtime import CodexExecRuntime
from adp.discovery_schema import digest
from adp.discovery_types import Identity, Issue
from adp.errors import ADPError
from adp.execution_memory import ExecutionJournal
from adp.github_product import GitHubProductForge
from adp.guard import ProgressGuard
from adp.guard_types import Attestation, data
from adp.network_http import NetworkTransportError
from adp.personal_history import _anchor
from adp.personal_report_child import validate_report
from adp.personal_storage import read_private
from adp.personal_track import PersonalTrack
from adp.schema import encode, key
from adp.storage import atomic
import test_accounting_writers as writers


class HistoricalRemainder(Exception):
    """Stop the overlay unit proof before independent historical Worker checks."""


class ReportPhaseTests(unittest.TestCase):
    def writer(self):
        helper = writers.AccountingWriterTests()
        f, p = helper.writer("REPORT")
        self.addCleanup(helper.doCleanups)
        f.service._confirmed_stop()  # Pre-effect stage, no request started.
        return f, p

    def overlay(self):
        f, p = self.writer()
        personal = p.personal
        personal.state = personal.directory = f.control
        personal.intent = {"kind": "PERSONAL", "approval": "setup"}
        personal.plan["window"] = {"issued_at": 90, "expires_at": 190}
        personal.plan["issue_id"] = "original"
        p.c.task_id = "personal:" + digest({"repository": personal.repository_id, "issue": personal.plan["issue_id"]})
        old_key, task_key = key("original"), key(p.c.task_id)
        task = f.snapshot["tasks"].pop(old_key)
        task["key"] = task_key
        f.snapshot["tasks"][task_key] = task
        guard = f.snapshot["state"]["progress_guard"]
        guard["task_epochs"] = {task_key: 1}
        item = guard["requirements"][f.requirement]
        item["tasks"], item["active"]["context"] = [task_key], ProgressGuard._context(f.snapshot["state"], task)
        p.active["reservation"]["decision"]["baseline"]["task_key"] = task_key
        p.c.product, p.c.transport, p.c.clock = p, None, p.clock
        task["assignments"] = {}
        p._writing = (*p._writing[:2], deepcopy(f.snapshot))
        historical = deepcopy(f.snapshot["state"])
        historical["progress_guard"]["requirements"] = {}
        p.c.memory.config = SimpleNamespace(root=f.control)
        p.c.memory._read_ref = Mock(return_value=(historical, deepcopy(f.snapshot["tasks"])))
        personal.memory = lambda: p.c.memory
        identity = Identity(personal.repository_id, "original")
        track = PersonalTrack.__new__(PersonalTrack)
        original = Issue(identity, 1, "https://github.com/owned/disposable/issues/1", "Original", "Frozen scope",
            "OPEN", None, "2026-11-09T08:00:00Z", "a"*64, (), (), (), (), ())
        track.c, track.personal, track.originals = p.c, personal, {identity: original}
        track.completion_path = lambda _: f.control / "completion.json"
        old_run = {"coordination": None, "source": "unchanged"}
        run = {**old_run, "coordination": {"label": "personal-report:" + p.active["action"],
            "permit": p.active["reservation"], "requirement": p.active["requirement"]}}
        product = {"gates": [{"actual": "unchanged"}]}
        receipt = dict.fromkeys("schema_version identity directory setup checkpoint accepted_at original packet source tree merge actor pull merge_payload workers run product ci files acceptance".split())
        receipt.update(schema_version=1, identity=data(identity), directory=str(f.control), setup="setup",
            checkpoint="1"*40, accepted_at=100, original=data(track.originals[identity]), source="d"*40,
            tree="2"*40, merge="3"*40, workers={"4"*64: "5"*64}, run=digest(old_run),
            product=digest(product), ci=product["gates"][-1], files={},
            acceptance="OPERATOR_CONFIRMED_CURRENT_PROJECT_ACCEPTANCE")
        for name, value in (("completion", receipt), ("run", run), ("product", product), ("report", {})):
            atomic(f.control / (name + ".json"), encode(value))
        self.enterContext(patch("adp.personal_track.load_state", return_value=personal))
        self.enterContext(patch("adp.personal_track.git"))
        # This unit proves the exact overlay and original digests. It does not
        # substitute a mocked receipt for genuine accepted-completion proof.
        self.enterContext(patch.object(CodexExecRuntime, "__init__", side_effect=HistoricalRemainder))
        return f, p, track, identity

    def test_pre_effect_overlay_uses_same_subject_without_inventing_a_request(self):
        f, p, track, identity = self.overlay()
        before = deepcopy(f.snapshot)
        with f.service.bounded(), self.assertRaises(HistoricalRemainder):
            track.accepted(identity)
        self.assertEqual(f.c.memory.inspect.call_count, 1)
        self.assertEqual(f.snapshot, before)
        self.assertFalse(f.service.unconfirmed_contexts())
        self.assertFalse(f.service._hazard_path().exists())
        with f.service.bounded(), self.assertRaisesRegex(ADPError, "stop boundary"):
            p.write_authorized()  # An overlay proof is never POST authority.
        self.assertEqual(f.http_calls, [])

    def test_pre_effect_overlay_refuses_changed_reservation_and_accepted_evidence(self):
        for change in ("label", "permit", "requirement", "run", "product", "claim", "owner",
                       "generation", "checkpoint", "source", "submitted", "expired", "revoked", "unknown"):
            with self.subTest(change=change):
                f, p, track, identity = self.overlay()
                run = read_private(f.control / "run.json")
                if change in ("label", "permit", "requirement"):run["coordination"][change] = "foreign"
                if change == "run":run["source"] = "foreign"
                atomic(f.control / "run.json", encode(run))
                if change == "product":atomic(f.control / "product.json", encode({"gates": [{"foreign": True}]}))
                if change == "claim":atomic(f.claim_path, encode({"foreign": True}))
                if change == "owner":f.snapshot["local_owner"] = False
                if change == "generation":f.snapshot["state"]["generation"] += 1
                if change == "checkpoint":f.snapshot["local_head"] = "f"*40
                if change == "source":f.snapshot["tasks"][key(p.c.task_id)]["source_revision"] = "f"*40
                if change == "submitted":f.snapshot["state"]["execution"]["actions"][f.identifier]["status"] = "PREPARED"
                if change == "expired":f.now = 180
                if change == "revoked":f.revoked = True
                if change == "unknown":f.service._start_request()
                with f.service.bounded(), self.assertRaises(ADPError):track.accepted(identity)
                self.assertEqual(f.http_calls, [])

    def test_short_actual_forge_submission_and_lost_response_never_dispatch_twice(self):
        for loss in (None, "before", "after"):
            with self.subTest(loss=loss):
                f, p = self.writer()
                p.c.memory.config = SimpleNamespace(identity=f.target.memory_id)
                p.c.memory.control = f.control
                p.c.runtime = None
                journal = ExecutionJournal.__new__(ExecutionJournal)
                journal.memory, journal.inspect = p.c.memory, p.c.memory.inspect
                authority = SimpleNamespace(verify=lambda proof, **kw: proof.subject == kw["subject"])
                forge = GitHubProductForge(f.service, journal, authority, personal=True)
                p.forge = forge
                payload = {"target": "https://github.com/owned/disposable/issues/1",
                    "body": "Implemented the original requirement.", "revision": p.c.revision()}
                action = f.snapshot["state"]["execution"]["actions"][f.identifier]
                action.update(status="PREPARED", payload=payload)
                dispatch = forge.prepare_dispatch(f.identifier, action)
                action["status"] = "SUBMITTED"
                p._writing = (f.identifier, deepcopy(action), deepcopy(f.snapshot))
                p.active["view"].update(original_observation={}, facts={})
                p.live = lambda: p.active["view"]
                p.original, p.facts = lambda: {}, lambda: {}
                p._policy_final = Mock(return_value=True)
                def accepted(*args, **kw):
                    self.assertFalse(f.service.unconfirmed_contexts())
                    self.assertTrue(p._submitted_authorized(_observed=f.c.memory.inspect()))
                    return {"separately_qualified": "completion"}
                p.c.track = SimpleNamespace(link={"identity": data(Identity(f.target.memory_id, "original"))}, accepted=accepted)
                posts, comments = [], []
                def reply(raw, seconds, **kw):
                    request = json.loads(raw)
                    if request["method"] == "POST":
                        posts.append(request)
                        if loss == "before":raise NetworkTransportError("Synthetic confirmed stop before effect")
                        comments.append({"body": request["body"]["body"],
                            "html_url": payload["target"] + "#issuecomment-1"})
                        if loss == "after":raise NetworkTransportError("Synthetic confirmed stop after effect")
                        body = comments[-1]
                    else:
                        body = comments if "/comments?" in request["path"] else {"id": 17, "full_name": "owned/disposable"}
                    return json.dumps({"status": 200, "headers": [],
                        "body_base64": base64.b64encode(json.dumps(body).encode()).decode()}).encode()
                f.child.side_effect = reply
                f.transport.validator = validate_report
                f.transport.authorize_write = p.write_authorized
                effect = Attestation("fixture:operator", "fixture:effect", digest({"id": f.identifier, "plan": "exact", "payload": payload}))
                with f.service.bounded():
                    observed = forge.submit(f.identifier, "REPORT", payload, authorization=effect,
                        plan_digest="exact", dispatch=dispatch, validate=p.final_boundary)
                    self.assertEqual(observed.status, "UNKNOWN" if loss == "before" else "PRESENT")
                    with self.assertRaisesRegex(ADPError, "one-use"):
                        forge.submit(f.identifier, "REPORT", payload, authorization=effect,
                            plan_digest="exact", dispatch=dispatch, validate=p.final_boundary)
                    self.assertEqual(forge.observe(f.identifier, "REPORT", payload, attempted=True), observed)
                self.assertEqual(len(posts), 1)
                self.assertEqual(len(comments), 0 if loss == "before" else 1)
                self.assertFalse(f.service.unconfirmed_contexts())
                p._policy_final.assert_called_once_with()


class ActivationAvailabilityTests(unittest.TestCase):
    def test_missing_activation_is_domain_refusal_at_first_historical_consumer(self):
        with TemporaryDirectory() as directory:
            root = SimpleNamespace(directory=Path(directory))
            memory = SimpleNamespace(inspect=Mock(side_effect=AssertionError("No canonical mutation/observation before activation")))
            with self.assertRaisesRegex(ADPError, "Exact episode activation is missing"):
                _anchor(root, memory, {}, {}, {})
            memory.inspect.assert_not_called()

    def test_invalid_activation_and_unrelated_io_are_not_hidden_as_missing(self):
        with TemporaryDirectory() as directory:
            from adp.personal_episode import episode_directory
            root = SimpleNamespace(directory=Path(directory))
            path = episode_directory(root) / "activation.json"
            path.parent.mkdir(parents=True)
            for raw in (b"not-json", encode({"wrong": "fields"})):
                atomic(path, raw)
                with self.assertRaises(ADPError) as error:_anchor(root, None, {}, {}, {})
                self.assertNotIn("activation is missing", str(error.exception))
            with patch("adp.personal_history.read_private", side_effect=PermissionError("Synthetic protected I/O")), \
                 self.assertRaises(PermissionError):_anchor(root, None, {}, {}, {})
