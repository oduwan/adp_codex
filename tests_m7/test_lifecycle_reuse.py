"""Issue69 owning-stage reuse and fresh boundary negatives; no live effects."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.execution_types import Role, RuntimeObservation, RuntimeStatus, WorkerRequest, WorkerResult
from adp.guard_types import Outcome, Requirement, data
from adp.personal_product import PersonalProduct
from adp.personal_product_review import ProductAuthority
from adp.personal_workers import PersonalWorkers
from adp.schema import key
import test_trusted_product_stages as stages


class LifecycleReuseTests(unittest.TestCase):
    def authority(self):
        directory = TemporaryDirectory(); self.addCleanup(directory.cleanup)
        subject = {"state": {"generation": 1}}
        memory = SimpleNamespace(inspect=Mock(side_effect=lambda: deepcopy(subject)))
        spec = Requirement("task", "effects", ("exact",))
        flow = SimpleNamespace(specification=spec, ci_specification=spec,
            guard=SimpleNamespace(admission_subject=lambda task, value: digest(data(value))))
        c = SimpleNamespace(episode=False, task_id="task", product=flow,
            personal=SimpleNamespace(state=Path(directory.name), intent={"approval": "original"},
                plan={"window": {"expires_at": 200}}), memory=memory, clock=lambda: 100,
            live=Mock(side_effect=memory.inspect), require_development_protocol=Mock())
        return ProductAuthority(c), subject, spec

    def test_product_proof_and_verify_use_their_own_actual_observation(self):
        authority, subject, spec = self.authority()
        evidence = authority._proof("admission", digest(data(spec)), "product-admission", data(spec), "personal:operator")
        self.assertTrue(authority.verify(evidence, purpose="admission", subject=digest(data(spec))))
        self.assertEqual(authority.c.memory.inspect.call_count, 2)
        self.assertEqual(authority.c.live.call_count, 2)
        subject["state"]["generation"] += 1
        self.assertFalse(authority.verify(evidence, purpose="admission", subject=digest(data(spec))))
        self.assertEqual(authority.c.memory.inspect.call_count, 3)
        subject["state"]["generation"] = 1
        authority.c.clock = lambda: 200
        self.assertFalse(authority.verify(evidence, purpose="admission", subject=digest(data(spec))))

    def test_proof_has_no_positive_cache_after_revocation_or_changed_receipt(self):
        from adp.personal_storage import read_private
        from adp.schema import encode
        from adp.storage import atomic
        a, _, spec = self.authority()
        evidence = a._proof("admission", digest(data(spec)), "product-admission", data(spec), "personal:operator")
        a.c.live.side_effect = ADPError("Revoked")
        self.assertFalse(a.verify(evidence, purpose="admission", subject=digest(data(spec))))
        a.c.live.side_effect = a.c.memory.inspect
        path = a.directory / (evidence.reference.removeprefix("personal:") + ".json")
        body = read_private(path); body["generation"] += 1
        atomic(path, encode(body))
        self.assertFalse(a.verify(evidence, purpose="admission", subject=digest(data(spec))))

    def worker(self, episode=False):
        from adp.codex_runtime import CodexExecRuntime
        request = WorkerRequest("a"*64, "task", 1, Role.REVIEWER, "b"*40,
            "/tmp/disposable-not-executed", "Synthetic observation only", 300, 400)
        result = WorkerResult(Outcome.PASS, True, ("code",), "Synthetic independent review")
        observation = RuntimeObservation(request.id, "c"*64, RuntimeStatus.COMPLETED, "distinct-context",
            result, "runtime:" + request.id + ":" + "d"*64, 1, digest(request), 1, 100, True)
        row = {"request": data(request), "host": observation.host, "purpose": "code", "phase": "ACCOUNTED",
            "assignment": {"assignment_id": "assignment"}, "observation": data(observation), "requirement": "review"}
        assignment = {"worker": "worker:" + request.id, "generation": 1, "source_revision": request.revision,
            "status": "accepted", "result": PersonalWorkers.result(row)}
        state = {"health": "SYNCED", "local_owner": True, "state": {"generation": 1},
            "tasks": {key("task"): {"source_revision": request.revision, "assignments": {"assignment": assignment}}}}
        runtime = CodexExecRuntime.__new__(CodexExecRuntime)
        runtime.host, runtime.observe = observation.host, Mock(return_value=observation)
        c = SimpleNamespace(episode=episode, task_id="task", runtime=runtime,
            memory=SimpleNamespace(inspect=Mock(side_effect=lambda: deepcopy(state))), allowed=Mock(),
            guard=SimpleNamespace(_get=Mock(return_value={"active": None}),
                _snapshot=Mock(side_effect=AssertionError("No redundant guard snapshot"))))
        relation = {"host": observation.host, "usage": {"requests": {request.id: {"purpose": "code"}}}}
        c.personal = SimpleNamespace(_active_view=Mock(side_effect=lambda **kw: (relation, (), c.memory.inspect())))
        workers = PersonalWorkers.__new__(PersonalWorkers); workers.c = c
        workers.records = Mock(return_value=[row])
        return workers, row, state

    def test_stopped_worker_assignment_and_guard_share_post_runtime_snapshot(self):
        for episode in (False, True):
            workers, row, state = self.worker(episode)
            with self.subTest(episode=episode):
                self.assertEqual(workers.actual(row, approval=True, accounted=True).context_id, "distinct-context")
                self.assertEqual(workers.c.memory.inspect.call_count, 1)
                workers.c.guard._snapshot.assert_not_called()
                observed = workers.c.allowed.call_args.kwargs["_observed"]
                self.assertEqual(observed, state)
                self.assertEqual(workers.c.personal._active_view.call_count, int(episode))
                # A later invocation must observe the changed canonical assignment.
                state["tasks"][key("task")]["assignments"]["assignment"]["status"] = "pending"
                with self.assertRaises(ADPError):workers.actual(row, approval=True, accounted=True)

    def test_episode_callback_cannot_mix_old_assignment_and_new_generation(self):
        workers, row, state = self.worker(True)
        def changed(**kw):
            state["state"]["generation"] += 1
            return {"host": row["host"]}, (), workers.c.memory.inspect()
        workers.c.personal._active_view.side_effect = changed
        with self.assertRaises(ADPError):workers.actual(row, approval=True, accounted=True)
        workers.c.allowed.assert_not_called()

    def test_accounted_worker_needs_current_health_and_independent_context(self):
        for change in ("health", "owner", "generation", "stop", "context"):
            w, row, state = self.worker()
            if change == "health":state["health"] = "RECOVERY_REQUIRED"
            if change == "owner":state["local_owner"] = False
            if change == "generation":state["state"]["generation"] = 2
            if change == "stop":
                from dataclasses import replace
                w.c.runtime.observe.return_value = replace(w.c.runtime.observe.return_value, stopped=False)
            if change == "context":w.records.return_value.append({"request": {"id": "other"}, "observation": row["observation"]})
            with self.subTest(change=change), self.assertRaises(ADPError):w.actual(row, approval=True, accounted=True)

    def test_new_ci_reuses_completed_entry_but_restart_requalifies_scope(self):
        f = stages.TrustedProductStageTests(methodName="runTest")
        p, _ = f.product()
        entry = {"phase": "PREPARED", "approval": "exact", "view": {"revision": "a"*40}}
        p.record, p.save = lambda: {"execution": [entry]}, Mock()
        p.local, p.original = Mock(), Mock(side_effect=ADPError("Changed original dependency"))
        p.observe_ci = Mock(return_value={"status": "PENDING"})
        self.assertEqual(p._execute_selected("CI", entry, "exact", _admitted=True), {"status": "PENDING"})
        p.local.assert_not_called();p.original.assert_not_called()
        entry["phase"] = "PREPARED"
        with self.assertRaisesRegex(ADPError, "dependency"):p._execute_selected("CI", entry, "exact")
        p.local.assert_called_once();self.assertEqual(p.observe_ci.call_count, 1)

    def test_review_context_qualifies_ci_once_after_context_callbacks(self):
        p = PersonalProduct.__new__(PersonalProduct)
        latest = {"status": "NOT_REQUIRED", "policy": "actual-observed-policy", "revision": "a"*40}
        events = []
        p.c = SimpleNamespace(context=lambda kind: events.append("context") or {"revision": "a"*40})
        p.personal = SimpleNamespace(plan={"criterion": "original"})
        p.record = lambda: {"pull": "exact-pr"}
        p.qualified = Mock(side_effect=lambda: events.append("CI") or latest)
        context = p.review_context()
        self.assertEqual(events, ["context", "CI"])
        self.assertEqual(context["actual_post_pr_evidence"], latest)
        self.assertEqual(context["validation_binding"], p.validation_binding(_latest=latest))
        p.qualified.assert_called_once()
        p.qualified.side_effect = ADPError("Missing or stale CI")
        with self.assertRaisesRegex(ADPError, "CI"):p.review_context()

    def test_product_uses_one_original_semantic_path_for_all_stages(self):
        p = PersonalProduct.__new__(PersonalProduct)
        p.publication = SimpleNamespace(original=Mock(return_value={"actual-selected-scope": "same"}))
        captured = {}; qualified = {"fresh": "original"}
        self.assertEqual(p.original(_capture=captured, _qualified=qualified), {"actual-selected-scope": "same"})
        p.publication.original.assert_called_once_with(_capture=captured, _qualified=qualified)
        p.publication.original.side_effect = ADPError("Changed selected scope or native dependencies")
        with self.assertRaisesRegex(ADPError, "native dependencies"):p.original()

    def test_personal_pull_detail_keeps_both_repository_identities_without_extra_get(self):
        from contextlib import nullcontext
        from adp.discovery_github import Response
        from adp.github_product import GitHubProductForge
        f = GitHubProductForge.__new__(GitHubProductForge)
        f.repository, f.repository_id, f.head_ref = "owned/project", "17", "refs/heads/task"
        f.service = SimpleNamespace(bounded=lambda **kw: nullcontext(),
            target=SimpleNamespace(memory_id="opaque:repository", node_id="R_owned"))
        repository = {"id": 17, "node_id": "R_owned", "full_name": f.repository}
        original = {"id": 900, "number": 10, "html_url": "https://github.com/owned/project/pull/10",
            "draft": True, "state": "open", "merged": False,
            "head": {"ref": "task", "sha": "a"*40, "repo": deepcopy(repository)},
            "base": {"ref": "trunk", "sha": "b"*40, "repo": deepcopy(repository)}}
        f.transport = SimpleNamespace(request=Mock(return_value=Response(200, original)))
        f._identity = Mock(return_value=False)
        identity = {"id": "900", "number": 10, "repository_id": "opaque:repository", "url": original["html_url"]}
        def pull():return f.pull(identity, revision="a"*40, source_ref=f.head_ref or "refs/heads/task",
            base_ref="refs/heads/trunk", expected_base="b"*40)
        self.assertEqual(pull(), original);f._identity.assert_not_called()
        self.assertEqual(f.transport.request.call_count, 1)
        for side in ("head", "base"):
            for field, wrong in (("id", 18), ("node_id", "foreign"), ("full_name", "foreign/project")):
                changed = deepcopy(original);changed[side]["repo"][field] = wrong
                f.transport.request.return_value = Response(200, changed)
                with self.subTest(side=side, field=field):self.assertIsNone(pull())
        f.head_ref = None
        f.transport.request.reset_mock()
        self.assertIsNone(pull());f._identity.assert_called_once()
        f.transport.request.assert_not_called()  # Signed/generic default remains independent.

    def test_report_preview_uses_the_actual_status_acceptance_and_original_observation_once(self):
        from contextlib import nullcontext
        from adp.discovery_types import Identity
        from adp.personal_report import PersonalReport
        from adp.runtime_limits import DEFAULTS
        p = PersonalReport.__new__(PersonalReport)
        identity = Identity("17", "opaque-issue")
        accepted = {"source": "a"*40, "tree": "b"*40, "merge": "c"*40, "actor": 91,
            "pull": {"url": "https://github.com/owned/project/pull/10"}, "ci": {"status": "PASS"}}
        observation = SimpleNamespace(snapshot="actual-originals")
        track = SimpleNamespace(link={"identity": data(identity)},
            status=Mock(side_effect=AssertionError("Reporting does not select next scope")),
            accepted=Mock(return_value=accepted),
            current=Mock(side_effect=AssertionError("Do not scan the same track again")))
        p.clock = lambda: 100
        p.service = SimpleNamespace(limits=DEFAULTS, bounded=lambda **kw: nullcontext())
        p.c = SimpleNamespace(episode=False, runtime="explicit-runtime", task_id="task", track=track,
            revision=lambda: "a"*40, record=lambda: {"feature_administration": "owned"},
            memory=SimpleNamespace(inspect=lambda: {"health": "SYNCED", "local_owner": True, "local_head": "d"*40, "canonical_head": "d"*40, "remote_head": "d"*40, "inbox_count": 0, "state": {"generation": 1}, "tasks": {}}))
        p.c.live = p.c.memory.inspect
        def accepted_once(selected, **kwargs):
            kwargs["_capture"][selected] = (None, p.c.memory.inspect(), None, accepted, None)
            return track.accepted.result
        track.accepted.side_effect = accepted_once
        track.accepted.result = accepted
        p.personal = SimpleNamespace(plan={"window": {"expires_at": 200}, "repository": {"name": "owned/project"},
            "issue": 1}, intent={"approval": "original", "original": {"title": "Original", "url": "https://github.com/owned/project/issues/1"}})
        p.transport, p.target = SimpleNamespace(credential_binding="credential"), SimpleNamespace(ref="refs/heads/task")
        p.local, p.facts = Mock(return_value="review"), Mock(return_value={})
        issue = SimpleNamespace(identity=identity)
        p.original = Mock(side_effect=lambda **kw: kw["_capture"].update(issues=[issue]) or {})
        consumed = []
        result = p.report_preview(_observation=consumed)
        self.assertEqual(result["status"], "REPORT_PROPOSED")
        self.assertEqual(consumed, [issue])
        self.assertEqual(track.accepted.call_count, 1)
        self.assertEqual(track.accepted.call_args.args, (identity,))
        p.local.assert_called_once_with(genuine=False, _observed=p.c.memory.inspect())
        track.status.assert_not_called();track.current.assert_not_called()
        track.accepted.result = None
        with self.assertRaisesRegex(ADPError, "actual accepted completion"):p.report_preview()
        track.accepted.result = accepted
        p.c.live = lambda: {**p.c.memory.inspect(), "local_head": "e"*40}
        with self.assertRaisesRegex(ADPError, "subject advanced"):p.report_preview()
        p.c.live = p.c.memory.inspect
        track.accepted.side_effect = lambda *a, **kw: accepted
        with self.assertRaisesRegex(ADPError, "qualification is missing"):p.report_preview()

    def test_status_uses_qualified_snapshot_and_only_accepted_native_parent_unblocks_next(self):
        from adp.personal_track import PersonalTrack
        from adp.ticket_types import OriginalTicket
        import personal_fixtures
        fixture = personal_fixtures.PersonalFixture(methodName="runTest");fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        observation, _ = fixture.observe()
        originals = {i.identity: OriginalTicket(observation.snapshot.repository, i, fixture.now)
            for i in observation.snapshot.issues}
        first = next(i for i in originals if originals[i].issue.number == 1)
        track = PersonalTrack.__new__(PersonalTrack)
        track.c = SimpleNamespace(episode=False, transport=fixture.transport, clock=lambda: observation.snapshot.observed_at)
        track.originals, track.link = originals, {"identity": data(first)}
        track.current = Mock(return_value=observation)
        track.links = lambda: [{"identity": data(first), "directory": str(fixture.base)}]
        subject = {"health": "SYNCED", "state": {"execution": {"actions": {}}}}
        personal = SimpleNamespace(memory=lambda: SimpleNamespace(control=fixture.base,
            inspect=Mock(side_effect=AssertionError("Use the actual closing accepted snapshot"))))
        receipt = {"packet": "ticket-packet:" + "a"*64}
        def accepted(identity, **kw):
            kw["_capture"][identity] = (None, subject, None, receipt, None)
            return receipt
        track.accepted = Mock(side_effect=accepted)
        with patch("adp.personal_track.load_state", return_value=personal), patch("adp.personal_episode.settled_guards", return_value=True):
            result = track.status()[0]
            self.assertEqual(result["next_issue"], 2)
            self.assertEqual(result["issues"][2]["status"], "BLOCKED_DEPENDENCY")
            self.assertEqual(result["next_admission"], "NOT_AUTHORIZED")
            subject["state"]["execution"]["actions"] = {"unfinished": {"status": "SUBMITTED"}}
            with self.assertRaisesRegex(ADPError, "unfinished/uncertain"):track.status()
        track.current.assert_called()

    def test_completion_targets_original_and_preserves_post_status_checkpoint(self):
        from adp.discovery_types import Identity, Issue
        from adp.personal_track import PersonalTrack
        identity = Identity("17", "original")
        original = Issue(identity, 1, "https://github.com/owned/project/issues/1", "Original", "Scope", "open", None,
            "2026-11-09T00:00:00Z", "a"*64, (), (), (), (), ())
        directory = TemporaryDirectory();self.addCleanup(directory.cleanup)
        subject = {"local_head": "c"*40, "state": {"execution": {"actions": {}}}}
        c = SimpleNamespace(episode=False, revision=lambda: "a"*40,
            fresh=Mock(side_effect=AssertionError("No unrelated future inventory")),
            record=lambda: {"coordination": None}, workers=SimpleNamespace(records=lambda: [{"phase": "ACCOUNTED"}]),
            memory=SimpleNamespace(inspect=lambda: deepcopy(subject)))
        p = SimpleNamespace(c=c, publication=SimpleNamespace(checkout=Mock()),
            local=Mock(), original=Mock(), qualified=Mock(), verify_review=Mock(),
            status=Mock(side_effect=lambda: subject.update(local_head="d"*40) or {
                "status": "MERGED_DELEGATED_VERIFIED", "revision": "e"*40, "pull": "exact-pr"}),
            pull=Mock(return_value={"merged_by": {"id": 91}}), port=SimpleNamespace(_value=lambda *args: "b"*40),
            validation_binding=lambda **kw: "actual-CI", record=lambda: {"review": "independent"},
            service=SimpleNamespace(unconfirmed_contexts=lambda: False))
        track = PersonalTrack.__new__(PersonalTrack)
        track.c = c;track.personal = SimpleNamespace(state=Path(directory.name), intent={"original": data(original)},
            plan={"window": {"expires_at": 200}})
        track.index, track.link, track.originals = {"repository": "17"}, {"identity": data(identity)}, {identity: data(original)}
        preview = PersonalTrack.completion_preview
        while hasattr(preview, "__wrapped__"):preview = preview.__wrapped__
        with patch("adp.personal_track.read_private", return_value={"packet": "prepared"}), \
                patch("adp.personal_episode.settled_guards", return_value=True):
            result = preview(track, p)
            self.assertEqual(result["result"]["checkpoint"], "d"*40)
            p.publication.checkout.assert_called_once();p.local.assert_called_once();p.original.assert_called_once()
            c.fresh.assert_not_called()
            p.original.side_effect = ADPError("Changed selected prerequisite")
            p.status.reset_mock()
            with self.assertRaisesRegex(ADPError, "prerequisite"):preview(track, p)
            p.status.assert_not_called()
