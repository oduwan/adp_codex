"""Focused actual M1/M2/M3/M7 composition with SYNTHETIC worker/API records."""
import json
from unittest.mock import patch

from adp.errors import ADPError
from adp.execution_ports import UnconfirmedValidation
from adp.guard_types import Outcome
from adp.personal_publication import WARRANT, POLICY_ASSENT
from adp.personal_storage import approval, read_private
from adp.schema import encode, key
from adp.storage import atomic
from network_fixtures import gv
from personal_publication_fixtures import PublicationFixture
from test_config import run, snapshot


class PersonalPublicationTests(PublicationFixture):
    def test_separate_consent_absent_ref_exact_objects_and_unaccepted_result(self):
        pub = self.ready()
        before = self.observation_snapshot()
        proposal = pub.preview()
        self.assertEqual(self.observation_snapshot(), before)
        self.assertFalse(pub.path.exists())
        self.assertFalse(pub.evidence.exists())
        self.assertFalse(list(self.c.memory.control.glob("network-cas-*.json")))
        self.assertEqual(proposal["status"], "PUBLICATION_PROPOSED")
        self.assertEqual(proposal["result"]["administrative_quiescence_warrant"], WARRANT)
        self.assertEqual(proposal["result"]["project_policy_assent"], POLICY_ASSENT)
        self.assertIsNone(proposal["result"]["expected_old"])
        for flags in ((False, True, True), (True, False, True), (True, True, False)):
            with self.subTest(flags=flags), self.assertRaises(ADPError):
                pub.publish(reviewed=proposal["approval"], authorized=flags[0], assume_quiescence=flags[1], confirm_project_rules=flags[2])
        with self.assertRaises(ADPError):
            self.publish(approval(self.personal.plan))
        self.assertEqual(self.observation_snapshot(), before)
        with patch.object(pub, "proof", wraps=pub.proof) as proofs:
            result = self.publish(proposal["approval"])
        self.assertFalse(any(call.args[0] == "progress" for call in proofs.call_args_list))
        self.assertEqual(result["status"], "PUBLISHED_UNACCEPTED")
        self.assertEqual(result["product_acceptance"], "NOT_ACCEPTED")
        guard = pub.guard._snapshot(self.c.task_id, pub.record()["requirement"])[2]
        self.assertIsNone(guard["last"]["observation"]["progress"])
        self.assertEqual(guard["unresolved"], ["published"])
        self.assertEqual(result["independent_publication_progress"], "NOT_CLAIMED")
        head = gv(self.personal.feature, "rev-parse", "HEAD")
        self.assertEqual(self.http.server.refs()[pub.target.ref], head)
        self.assertEqual(gv(self.store, "cat-file", "commit", head), gv(self.personal.feature, "cat-file", "commit", head))
        updates = [row for kind, row in self.http.server.mutations if kind == "ref"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["beforeOid"], "0" * 40)
        state = self.c.memory.inspect()["state"]["execution"]
        self.assertEqual(state["tasks"][key(self.c.task_id)]["jobs"], {})
        self.assertIsNone(state["tasks"][key(self.c.task_id)]["review"])
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(len({o.context_id for o in self.observed.values()}), 4)
        self.assertEqual(self.c.guard._snapshot(self.c.task_id, self.c.requirement("develop"))[2]["unresolved"], [self.personal.plan["criterion"]])
        self.assertEqual(pub.status()["status"], "PUBLICATION_PRESENT")
        self.assertFalse(any("pulls" in path or "comments" in path for method, path, _ in self.http.server.calls if method != "GET" and path != "/graphql"))

    def test_existing_ref_atomic_race_and_restart_never_blindly_retry(self):
        pub = self.ready(absent=False, intermediate=True)
        proposal = pub.preview()
        self.assertEqual(proposal["result"]["expected_old"], self.initial)
        self.http.server.before_cas = lambda: gv(self.store, "update-ref", pub.target.ref, self.middle, self.initial)
        with self.assertRaises(ADPError):
            self.publish(proposal["approval"])
        self.assertEqual(self.http.server.refs()[pub.target.ref], self.middle)
        self.assertEqual(gv(self.store, "merge-base", self.middle, self.c.revision()), self.middle)
        before = len(self.http.server.mutations)
        state = self.c.memory.inspect()["state"]["progress_guard"]
        resumed = self.reconnect_publisher()
        with self.assertRaises(ADPError):
            self.publish(proposal["approval"], publisher=resumed)
        self.assertEqual(len(self.http.server.mutations), before)
        self.assertEqual(self.c.memory.inspect()["state"]["progress_guard"], state)

    def test_lost_ack_and_crash_after_cas_reconcile_the_same_action_once(self):
        pub = self.ready(absent=False)
        proposal = pub.preview()
        self.http.server.lose_ack = True
        with patch.object(pub, "settle", side_effect=OSError("Synthetic crash before canonical observed receipt")), self.assertRaises(OSError):
            self.publish(proposal["approval"])
        action = pub.journal.inspect()["state"]["execution"]["actions"][pub.record()["action_id"]]
        self.assertEqual(action["status"], "SUBMITTED")
        writes = len(self.http.server.mutations)
        resumed = self.reconnect_publisher()
        self.assertEqual(self.publish(proposal["approval"], publisher=resumed)["status"], "PUBLISHED_UNACCEPTED")
        counters = self.c.memory.inspect()["state"]["progress_guard"]
        self.assertEqual(self.publish(proposal["approval"], publisher=resumed)["status"], "PUBLISHED_UNACCEPTED")
        self.assertEqual(self.c.memory.inspect()["state"]["progress_guard"], counters)
        self.assertEqual(len(self.http.server.mutations), writes)
        self.assertEqual(sum(kind == "ref" for kind, _ in self.http.server.mutations), 1)
        update = next(payload for kind, payload in self.http.server.mutations if kind == "ref")
        self.assertEqual(update["beforeOid"], self.initial)
        self.assertEqual(update["afterOid"], self.c.revision())

    def test_account_permissions_rules_default_and_credential_drift_are_not_consent(self):
        pub = self.ready()
        proposal = pub.preview()
        before = self.observation_snapshot()
        changes = [(self.http.server, "permission", "READ"), (self.http.server, "rules", [{"type": "required_status_checks"}]),
                   (self.http.server, "legacy", 1), (self.http, "credential_binding", "f" * 64)]
        for obj, field, changed in changes:
            original = getattr(obj, field)
            setattr(obj, field, changed)
            with self.subTest(field=field), self.assertRaises((ADPError, OSError)):
                self.publish(proposal["approval"])
            setattr(obj, field, original)
        repo = self.transport.api.responses[self.prefix]
        old_default = repo.body["default_branch"]
        repo.body["default_branch"] = pub.target.branch
        with self.assertRaises(ADPError):
            self.publish(proposal["approval"])
        repo.body["default_branch"] = old_default
        old_id = self.transport.account.body["id"]
        self.transport.account.body["id"] = 92
        with self.assertRaises(ADPError):
            self.publish(proposal["approval"])
        self.transport.account.body["id"] = old_id
        self.assertEqual(self.http.server.mutations, [])
        self.assertEqual(self.observation_snapshot(), before)
        self.now = proposal["result"]["expires_at"]
        with self.assertRaises(ADPError):
            self.publish(proposal["approval"])
        self.assertFalse(pub.path.exists())

    def test_unknown_stop_and_lost_private_history_never_allow_handoff_or_replacement(self):
        pub = self.ready()
        proposal = pub.preview()
        original = self.http.request
        def uncertain(method, path, body, *, seconds):
            if method == "POST" and "/git/" in path:
                raise UnconfirmedValidation("validation:synthetic-unknown-stop", str(self.base))
            return original(method, path, body, seconds=seconds)
        self.http.request = uncertain
        with self.assertRaises((ADPError, OSError)):
            self.publish(proposal["approval"])
        self.assertTrue(pub.service.unconfirmed_contexts())
        self.assertEqual(self.http.server.mutations, [])
        _, handoff = self.c.invocation("handoff")
        with self.assertRaises(ADPError):
            self.c.run(reviewed=handoff, authorized=True, operation="handoff")
        pub.path.unlink()
        with self.assertRaises(ADPError):
            self.reconnect_publisher().preview()
        self.assertTrue(self.c.memory.inspect()["local_owner"])

    def test_source_drift_during_upload_prevents_final_cas(self):
        pub = self.ready()
        proposal = pub.preview()
        before = self.http.server.refs()
        self.http.server.after_upload = lambda: gv(self.personal.feature, "update-ref", pub.target.ref, self.initial, self.c.revision())
        with self.assertRaises((ADPError, OSError)):
            self.publish(proposal["approval"])
        self.assertEqual(self.http.server.refs(), before)
        self.assertFalse(any(kind == "ref" for kind, _ in self.http.server.mutations))

    def test_prepared_claim_loss_and_tampered_approval_never_mint_replay(self):
        pub = self.ready()
        proposal = pub.preview()
        original = pub.port.prepare_dispatch
        def interrupted(action_id, action):
            original(action_id, action)
            raise OSError("Synthetic crash after exclusive claim")
        with patch.object(pub.port, "prepare_dispatch", side_effect=interrupted), self.assertRaises(OSError):
            self.publish(proposal["approval"])
        self.assertEqual(self.http.server.mutations, [])
        row = pub.record()
        pub.port._claim_path(row["action_id"]).unlink()
        with self.assertRaises(ADPError):
            self.publish(proposal["approval"], publisher=self.reconnect_publisher())
        corrupt = read_private(pub.path)
        corrupt["view"]["expected_old"] = "1" * 40
        corrupt["action_id"] = __import__("adp.discovery_schema", fromlist=["digest"]).digest({"personal-publication": corrupt["view"]})
        atomic(pub.path, encode(corrupt))
        with self.assertRaises(ADPError):
            self.reconnect_publisher().preview()
        self.assertEqual(self.http.server.mutations, [])
