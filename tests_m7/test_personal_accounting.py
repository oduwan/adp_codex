"""Focused finite archival/episode tests, exclusively disposable synthetic data."""
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
import json
import unittest

from adp.accounting_policy import entry
from adp.errors import ADPError
from adp.personal_episode import load_episode
from adp.personal_history import archived
from adp.schema import key
from adp.discovery_schema import digest
from adp.guard_types import Action, ActionKind, Observation, Outcome
from adp.personal_storage import read_private
from adp.storage import atomic, locked
from adp.schema import encode
from accounting_fixtures import AccountingFixture


class AccountingRecoveryTests(AccountingFixture):
    def test_guard_first_unknown_keeps_notrun_and_original_counters(self):
        m = self.archive()
        observed = self.c.memory.inspect()
        self.assertEqual((observed["state"], observed["tasks"]), (m["result_state"], m["result_tasks"]))
        self.assertEqual(self.c.worker(m["request"])["observation"]["result"]["outcome"], "NOTRUN")
        self.assertEqual(self.recovery.status()["status"], "ARCHIVED_UNKNOWN_NOT_ACCEPTED")
        self.assertEqual(archived(self.personal)[0], m)
        self.assertEqual(len(self.requests), 2)
        from adp.personal_recovery_cli import observe
        from adp.personal_storage import PersonalBlocked
        path = self.runtime.directory / (m["request"] + ".stop.json")
        raw = path.read_bytes()
        path.unlink()
        with patch("adp.personal_cli.discovery_token", side_effect=AssertionError("No credentials")), self.assertRaises(PersonalBlocked) as failed:
            observe(self.c, m["request"])
        self.assertEqual(failed.exception.reason, "ARCHIVAL_EVIDENCE_UNVERIFIED")
        atomic(path, raw)
        self.assertEqual(observe(self.c, m["request"])["status"], "ARCHIVAL_OBSERVATION_VERIFIED")

    def test_preflight_refuses_scope_caps_permissions_host_and_nonaccounting_hazards(self):
        self.incident()
        before = self.c.memory.inspect()
        changes = ({"paths": ["product"]}, {"developers": 3}, {"worker_seconds": 301}, {"code_reviewers": 1},
            {"seconds": 3601}, {"branch": "trunk"}, {"checks": []}, {"workspace": str(self.a)}, {"developers": True},
            {"commit_body": "unapproved{template}"})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ADPError):
                self.recovery.preview("guard", request=self.row["request"]["id"], choices={**self.child_choices, **change})
            self.assertFalse(self.recovery.master_path.exists())
            self.assertEqual(self.c.memory.inspect(), before)
        from adp.personal_recovery_cli import observe
        with patch.object(self.runtime, "host", "f" * 64), self.assertRaisesRegex(ADPError, "original trusted UID"):
            observe(self.c, self.row["request"]["id"])
        repo = self.transport.api.responses[self.prefix].body
        repo["permissions"]["push"] = False
        with self.assertRaises(ADPError):
            self.recovery.preview("guard", request=self.row["request"]["id"], choices=self.child_choices)
        repo["permissions"]["push"] = True
        # A real recorded additional M2 hazard is not the accounting exception.
        req = self.c.worker(self.c.record()["original_review"])["requirement"]
        permit = self.c.guard.begin(self.c.task_id, req, Action("personal:coordinator", ActionKind.CHECK, "negative:hazard", "One synthetic negative"))
        self.c.guard.observe(self.c.task_id, req, permit, Observation(Outcome.UNKNOWN, ("fixture:hazard",), (), risk="containment"))
        after = self.c.memory.inspect()
        with self.assertRaises(ADPError):
            self.recovery.preview("guard", request=self.row["request"]["id"], choices=self.child_choices)
        self.assertEqual(self.c.memory.inspect(), after)

    def test_cas_interruption_lost_result_and_duplicate_recovery_are_exact(self):
        self.incident()
        request = self.row["request"]["id"]
        view, _, _ = self.recovery.preview("guard", request=request, choices=self.child_choices)
        from adp.execution_memory import invocation_lock
        with invocation_lock(self.c.memory.control), self.assertRaises(ADPError):
            self.recovery.apply("guard", reviewed=view["approval"], authorized=True, acknowledge=True, request=request, choices=self.child_choices)
        self.assertFalse(self.recovery.master_path.exists())
        write = self.c.memory._write_files
        def interrupted(state, tasks, **kwargs):
            atomic(self.c.memory.path / "state.json", encode(state))
            raise OSError("Synthetic interrupted canonical write")
        with patch.object(self.c.memory, "_write_files", side_effect=interrupted), self.assertRaises(OSError):
            self.recovery.apply("guard", reviewed=view["approval"], authorized=True, acknowledge=True, request=request, choices=self.child_choices)
        journal = (self.c.memory.control / "pending.json").read_bytes()
        for arguments in ({}, {"before_effects": lambda: None}, {"_fence": lambda: None}):
            with self.subTest(recovery=tuple(arguments)), self.assertRaisesRegex(ADPError, "exact-purpose"):
                self.c.memory.recover(**arguments)
            self.assertEqual((self.c.memory.control / "pending.json").read_bytes(), journal)
        proposed, _ = self.recovery.reconcile_preview("guard")
        self.recovery.reconcile("guard", reviewed=proposed["approval"], authorized=True)
        h1 = self.c.memory.inspect()
        result, _, _ = self.recovery.preview("result")
        with patch.object(self.c.memory, "_accept_result", side_effect=OSError("Synthetic lost M1 delivery reply")), self.assertRaises(OSError):
            self.recovery.apply("result", reviewed=result["approval"], authorized=True, acknowledge=True)
        self.assertEqual(self.c.memory.inspect()["local_head"], h1["local_head"])
        self.assertEqual(self.c.memory.inspect()["inbox_count"], 1)
        proposed, _ = self.recovery.reconcile_preview("result")
        self.recovery.reconcile("result", reviewed=proposed["approval"], authorized=True)
        final = self.c.memory.inspect()
        self.recovery.apply("result", reviewed=result["approval"], authorized=True, acknowledge=True)
        self.assertEqual(self.c.memory.inspect(), final)
        self.assertEqual(final["state"]["progress_guard"], h1["state"]["progress_guard"])
        self.assertEqual(len(self.requests), 2)

    def test_stage_marker_and_restoration_crashes_recover_without_replacing_original_intents(self):
        from adp.personal_recovery import immutable
        self.incident()
        for stage in ("guard", "result"):
            proposal = self.recovery.preview(stage, request=self.row["request"]["id"], choices=self.child_choices)[0]
            def missing_marker(path, body):
                if path.name == stage + "-submitted.json":raise OSError("Synthetic pre-marker interruption")
                immutable(path, body)
            with patch("adp.personal_recovery.immutable", side_effect=missing_marker), self.assertRaises(OSError):
                self.recovery.apply(stage, reviewed=proposal["approval"], authorized=True, acknowledge=True,
                    request=self.row["request"]["id"], choices=self.child_choices)
            original = read_private(self.recovery.root / (stage + "-intent.json"))
            reconciliation = self.recovery.reconcile_preview(stage)[0]
            with patch("adp.personal_recovery.immutable", side_effect=missing_marker), self.assertRaises(OSError):
                self.recovery.reconcile(stage, reviewed=reconciliation["approval"], authorized=True)
            provenance = read_private(self.recovery.root / "submission-provenance" / (stage + ".json"))
            self.now += 1
            reconciliation = self.recovery.reconcile_preview(stage)[0]
            self.recovery.reconcile(stage, reviewed=reconciliation["approval"], authorized=True)
            self.assertEqual(read_private(self.recovery.root / (stage + "-intent.json")), original)
            self.assertEqual(read_private(self.recovery.root / "submission-provenance" / (stage + ".json")), provenance)
        self.assertEqual(len(read_private(self.recovery.root / "archive.json")["recovery"]), 6)
        self.assertEqual(archived(self.personal)[0], self.recovery.master())
        self.assertEqual(len(self.requests), 2)

    def test_native_readonly_observer_omits_private_subject_and_never_launches(self):
        from adp.cli import parser
        from adp.personal_cli import run
        self.incident()
        before = self.c.memory.inspect()
        for surface in ("personal", "codex"):
            args = [surface, "archive-observe", "--repo", str(self.a), "--remote", "forge", "--directory", str(self.directory),
                    "--request", self.row["request"]["id"]] + (["--personal"] if surface == "codex" else [])
            with patch.object(self.runtime, "capabilities", side_effect=AssertionError("No probe")), \
                 patch.object(self.runtime, "dispatch", side_effect=AssertionError("No worker")), \
                 patch("adp.personal_cli.discovery_token", side_effect=AssertionError("No credential request")):
                report, code = run(parser().parse_args(args), runtime=self.runtime, clock=lambda: self.now)
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "ARCHIVAL_OBSERVATION_VERIFIED")
            public = json.dumps(report)
            for private in (self.runtime.host, str(self.directory), self.row["request"]["prompt"], self.row["observation"]["receipt"]):
                self.assertNotIn(private, public)
            self.assertEqual(self.c.memory.inspect(), before)
        self.assertEqual(len(self.requests), 2)

    def test_missing_descriptor_intent_recovers_same_episode_and_cannot_replenish(self):
        from adp.personal_episode import Continuation, immutable
        self.archive()
        self.continuation = Continuation(self.c)
        view, d = self.continuation.preview()
        def crash(path, body):
            if path == self.continuation.directory / "intent.json":
                raise OSError("Synthetic descriptor/intent interruption")
            immutable(path, body)
        with patch("adp.personal_episode.immutable", side_effect=crash), self.assertRaises(OSError):
            self.continuation.apply(reviewed=view["approval"], authorized=True)
        self.assertFalse((self.continuation.directory / "intent.json").exists())
        proposed = self.continuation.reconcile_preview()[0]
        self.continuation.reconcile(reviewed=proposed["approval"], authorized=True)
        first = self.c.memory.inspect()
        self.continuation.apply(reviewed=view["approval"], authorized=True)
        self.assertEqual(self.c.memory.inspect(), first)
        relation = entry(first["state"])
        for operation in (lambda: self.c.memory.assign(self.c.task_id, "worker:forbidden"),
                          lambda: self.c.memory.set_revision(self.c.task_id, "f" * 40),
                          lambda: self.continuation.preview()):
            with self.assertRaises(ADPError):operation()
            self.assertEqual(self.c.memory.inspect(), first)
        self.c.memory.handoff()
        owner = (self.c.memory.control / "owner.json").read_bytes()
        with self.assertRaises(ADPError):self.c.memory.claim("forbidden-generation")
        self.assertEqual((self.c.memory.control / "owner.json").read_bytes(), owner)
        self.assertEqual(entry(self.c.memory.inspect()["state"])["allocations"], relation["allocations"])

    def test_expired_published_episode_cannot_activate_or_get_a_new_window(self):
        from adp.personal_episode import Continuation, immutable
        self.archive()
        continuation = Continuation(self.c)
        view, _ = continuation.preview()
        def interrupted(path, body):
            if path.name == "activation.json":raise OSError("Synthetic H3/activation interruption")
            immutable(path, body)
        with patch("adp.personal_episode.immutable", side_effect=interrupted), self.assertRaises(OSError):
            continuation.apply(reviewed=view["approval"], authorized=True)
        child = load_episode(continuation.directory)
        from adp.guard import ProgressGuard
        from adp.guard_types import DecisionKind
        generic = ProgressGuard(self.c.memory, clock=lambda: self.now)
        relation = entry(self.c.memory.inspect()["state"])
        self.assertEqual(generic.inspect(relation["child_id"], relation["child_requirement"]).kind, DecisionKind.OPERATOR_DECISION_REQUIRED)
        checkpoint = self.c.memory.inspect()["local_head"]
        with self.assertRaises(ADPError):
            generic.begin(relation["child_id"], relation["child_requirement"],
                Action("fixture:unqualified", ActionKind.CHECK, "fixture:unactivated", "No execution without exact activation"))
        self.assertEqual(self.c.memory.inspect()["local_head"], checkpoint)
        self.now = child.plan["window"]["expires_at"] + 1
        proposed = continuation.reconcile_preview()[0]
        self.assertEqual(continuation.reconcile(reviewed=proposed["approval"], authorized=True)["status"], "BLOCKED_WINDOW_EXPIRED_OR_REVOKED")
        self.assertFalse((child.directory / "activation.json").exists())
        with self.assertRaises(ADPError):child.active()
        with self.assertRaises(ADPError):continuation.preview()


class AccountingCandidateTests(AccountingFixture):
    def test_scope_then_explicit_candidate_copy_and_fresh_staged_sha_reviews(self):
        from adp.personal_adoption import Adoption
        self.child()
        print("SYNTHETIC_STAGE: EPISODE_ACTIVE; no genuine runtime", flush=True)
        _, token = self.c.invocation()
        self.assertEqual(self.c.run(reviewed=token, authorized=True)["status"], "CANDIDATE_ADOPTION_REQUIRED")
        print("SYNTHETIC_STAGE: FRESH_SCOPE_AND_FEATURE; no genuine runtime", flush=True)
        self.assertEqual(len(self.requests), 3)
        baseline = self.c.memory.inspect()
        for purpose in ("original", "develop"):
            with self.subTest(purpose=purpose), self.assertRaises(ADPError):
                self.c.workers.execute(purpose, {**self.c.context(purpose), "unapproved_extra_context": True},
                    self.a if purpose == "original" else self.personal.feature)
            self.assertEqual(self.c.memory.inspect(), baseline)
        adoption = Adoption(self.c)
        view, _ = adoption.preview()
        copy = adoption.copy
        def interrupted(intent, row, permit):
            copy(intent, row, permit)
            raise OSError("Synthetic interruption after first atomic file")
        with patch.object(adoption, "copy", side_effect=interrupted), self.assertRaises(OSError):
            adoption.apply(reviewed=view["approval"], authorized=True)
        foreign = self.personal.feature / "foreign.txt"
        foreign.write_text("Noncandidate negative control\n")
        with self.assertRaises(ADPError):adoption.apply(reviewed=view["approval"], authorized=True)
        foreign.unlink()
        result = adoption.apply(reviewed=view["approval"], authorized=True)
        print("SYNTHETIC_STAGE: EXPLICIT_CANDIDATE_COPY; not accepted", flush=True)
        self.assertEqual(result["status"], "CANDIDATE_ADOPTED_UNACCEPTED")
        self.assertIsNone(self.c.record()["developer"])
        self.assertEqual(len(self.requests), 3)
        self.check_root = self.personal.feature
        _, token = self.c.invocation("resume")
        result = self.c.run(reviewed=token, authorized=True, operation="resume")
        print("SYNTHETIC_STAGE: LOCAL_REVIEW_RETURNED; synthetic evidence only", flush=True)
        self.assertEqual(result["status"], "LOCAL_DRAFT_CODE_REVIEWED")
        self.assertEqual(result["product_acceptance"], "NOT_ACCEPTED")
        self.assertEqual(len(self.requests), 5)
        self.assertEqual(self.c.source_origin()["kind"], "RETAINED_UNACCEPTED")
        self.assertEqual(self.c.worker(self.c.record()["code_review"])["request"]["revision"], self.c.revision())
        relation = entry(self.c.memory.inspect()["state"])
        self.assertEqual(len(relation["usage"]["requests"]), 3)
        self.assertEqual(relation["usage"]["checks"], 1)
        self.assertEqual(self.original_c.memory.inspect()["state"]["progress_guard"]["requirements"][relation["parent_requirement"]]["mode"], "unsafe")
        self.assertIsNone(self.c.track.accepted(next(i for i, o in self.c.track.originals.items() if o.issue.number == 1)))
        from adp.personal_publication import PersonalPublication
        projection = PersonalPublication.__new__(PersonalPublication);projection.c = self.c
        binding = projection.review_binding()
        with patch.object(self.c, "original_approval", side_effect=AssertionError("No repeated live judgment in a binding projection")):
            self.assertEqual(projection.review_binding(), binding)
        before = self.c.memory.inspect()
        stop = self.runtime.directory / (self.c.record()["original_review"] + ".stop.json")
        raw = stop.read_bytes();stop.unlink()
        with self.assertRaises((ADPError, OSError)):projection.review_binding()
        atomic(stop, raw)
        self.assertEqual(self.c.memory.inspect(), before)
        self.assertEqual(projection.review_binding(), binding)
        # A read frame may share factual inputs only until its independent
        # closing proof. Losing the real retained stop during a nested check
        # must refuse before the outer publication read can return a result.
        from types import SimpleNamespace
        from adp.personal_read_frame import publication_live
        old_stop = self.original_c.runtime.directory / (self.recovery.master()["request"] + ".stop.json")
        original_stop = old_stop.read_bytes()
        for lose_on in (1, 2):
            read_calls, returned = [], []
            def interrupted_read(**kwargs):
                read_calls.append(True)
                if len(read_calls) == lose_on:
                    old_stop.unlink()
                self.c.live()
                returned.append(True)
                return {"unaccepted": True, "view": {"issued_at": self.now - 1, "expires_at": self.now + 1}}
            try:
                with self.assertRaises((ADPError, OSError)):
                    publication_live(SimpleNamespace(c=self.c, _live_current=interrupted_read))
            finally:
                atomic(old_stop, original_stop)
            self.assertEqual(len(read_calls), lose_on)
            self.assertEqual(len(returned), lose_on)  # Refusal came after the completed body.
        self.assertEqual(self.c.memory.inspect(), before)
        self.assertEqual(projection.review_binding(), binding)
        # A replacement of an ancestry commit lies outside a HEAD/tree fact
        # witness. The full fresh administration/ref proof must still refuse.
        from adp.git import git
        replacement = "refs/replace/" + self.personal.plan["checkout"]["head"]
        git(self.personal.feature, "update-ref", replacement, self.c.revision(), "0" * 40)
        try:
            with self.assertRaises(ADPError):projection.review_binding()
        finally:git(self.personal.feature, "update-ref", "-d", replacement, self.c.revision())
        self.assertEqual(self.c.memory.inspect(), before)
        self.assertEqual(projection.review_binding(), binding)

    def test_one_append_only_episode_preserves_parent_and_scope_quota(self):
        result = self.episode()
        self.assertEqual(result["status"], "CONTINUATION_SCOPE_REVIEW_REQUIRED")
        observed = self.c.memory.inspect()
        relation = entry(observed["state"])
        self.assertIsNotNone(relation)
        self.assertEqual(observed["tasks"][relation["parent_task"]], self.recovery.master()["result_tasks"][relation["parent_task"]])
        child = load_episode(self.continuation.directory)
        self.assertEqual(child.active()[0], relation)
        self.assertEqual(relation["allocations"]["previous_used"]["scope_reviewers"], 1)
        self.assertEqual(relation["allocations"]["current"]["scope_reviewers"], 1)
        self.assertEqual(relation["allocations"]["current"]["forensic_reviewers"], 0)
        self.assertEqual(observed["state"]["progress_guard"]["requirements"][relation["parent_requirement"]]["mode"], "unsafe")
        self.assertEqual(len(self.requests), 2)
