"""Original-scope conservation and read-only READY admission, synthetic tracks."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from adp.discovery import review_subject
from adp.discovery_schema import digest, key
from adp.discovery_types import Identity, Relation, Status, Target
from adp.errors import ADPError
from adp.guard_types import Attestation, data
from adp.ticket_preparation import (TicketArchive, TicketPreparer, addition_subject,
    change_digest, original_scope_subject, preparation_subject, ready_window)
from adp.ticket_types import (ChangeKind, Clause, Part, PreparationReview,
    ScopeAdditionApproval, TicketChange)
from ticket_fixtures import Project, git


class TicketPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="adp-ticket22-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = Project(self.root)

    def test_original_is_immutable_and_fully_reconstructible(self):
        p = self.project
        self.assertEqual(p.archive.original(p.reference).issue, p.snapshot.issues[0])
        self.assertEqual(p.archive.freeze(p.snapshot, p.original.issue.identity), p.reference)
        updated = replace(p.snapshot, issues=(replace(p.original.issue, body="Rewritten acceptance", revision="a" * 64),))
        with self.assertRaisesRegex(ADPError, "already frozen"):
            p.archive.freeze(updated, p.original.issue.identity)
        self.assertEqual(p.archive.original(p.reference), p.original)

    def test_distinct_project_profiles_preserved_without_adp_conventions(self):
        second = self.root / "other"
        second.mkdir()
        for p in (self.project, Project(second, "B")):
            result = p.prepare()
            self.assertEqual(result.status, Status.READY)
            self.assertEqual(result.packet.base_ref, "refs/heads/" + p.branch)
            self.assertEqual(result.packet.base_sha, p.sha)
            self.assertEqual(result.packet.checks, tuple(sorted(p.rules.checks)))
            self.assertEqual(result.packet.execution_authority, "UNKNOWN")
            self.assertEqual(result.packet.blocked_integrations, ("PROJECT_VALIDATION:#21", "GITHUB_EXECUTION:#16"))

    def test_schema_or_caller_claim_alone_cannot_approve_scope(self):
        p = self.project
        self.assertEqual(p.prepare(scope=replace(p.scope, evidence=None)).status, Status.BLOCKED_OPERATOR)
        p.preparer.authority = None
        self.assertEqual(p.prepare().status, Status.BLOCKED_OPERATOR)

    def test_issue_author_and_preparer_cannot_self_approve(self):
        p = self.project
        for actor in (*p.original.issue.authors, "ticket-preparer"):
            scope = replace(p.scope, evidence=p.authority.receipt(original_scope_subject(p.scope), "ticket/original-scope", actor))
            self.assertEqual(p.prepare(scope=scope).status, Status.BLOCKED_OPERATOR)
            track = p.preparer.observe(reviews=p.ready_reviews())
            review = PreparationReview("ticket-preparer", 90, 200)
            review = replace(review, evidence=p.authority.receipt(
                preparation_subject(p.original, p.scope, p.proposal, review, track), "ticket/preparation", actor))
            self.assertEqual(p.prepare(review=review).status, Status.BLOCKED_OPERATOR)

    def test_extra_product_feature_needs_specific_external_approval(self):
        p = self.project
        change = TicketChange("extra", ChangeKind.ADDITION, "SCOPE", "Original scope", "Add unrelated behavior",
            added_clauses=(Clause("extra", "OBJECTIVE", "New unrelated feature"),))
        proposal = replace(p.proposal, changes=(change,), parts=(Part("whole", ("goal", "accept", "interface", "check", "extra")),))
        self.assertEqual(p.prepare(proposal=proposal).status, Status.BLOCKED_OPERATOR)

    def test_test_integration_and_infrastructure_additions_cannot_hide_in_clarification(self):
        p = self.project
        for text in ("new test suite", "new integration campaign", "CI runner provisioning"):
            change = TicketChange("hidden", ChangeKind.CLARIFICATION, "EXPLANATION", "", text,
                added_clauses=(Clause("hidden", "CHECK", text),))
            with self.subTest(text=text), self.assertRaisesRegex(ADPError, "hide"):
                p.prepare(proposal=replace(p.proposal, changes=(change,)))

    def test_approval_binds_original_version_exact_diff_and_added_scope(self):
        p = self.project
        change = TicketChange("extra", ChangeKind.ADDITION, "SCOPE", "Original", "Specific approved addition",
            added_clauses=(Clause("extra", "OBJECTIVE", "Specific additional behavior"),))
        proposal = replace(p.proposal, changes=(change,), parts=(Part("whole", ("goal", "accept", "interface", "check", "extra")),))
        approval = ScopeAdditionApproval("extra", p.reference, change_digest(change), 90, 200)
        approval = replace(approval, evidence=p.authority.receipt(addition_subject(approval), "ticket/scope-addition", "external-operator"))
        result = p.prepare(proposal=proposal, additions=(approval,))
        self.assertEqual(result.status, Status.READY)
        self.assertEqual(result.packet.clauses[:4], p.scope.clauses)
        retained = p.archive.preparation(result.packet.preparation_reference)
        self.assertEqual(retained["proposal"], data(proposal))
        self.assertEqual(retained["additions"], [data(approval)])
        self.assertEqual(retained["scope"], data(p.scope))
        for invalid in (replace(approval, original_reference="ticket-original:" + "a" * 64),
                replace(approval, change_digest="a" * 64), replace(approval, expires_at=99),
                replace(approval, evidence=p.authority.receipt(addition_subject(approval), "ticket/edit", "external-operator"))):
            with self.subTest(invalid=invalid):
                self.assertEqual(p.prepare(proposal=proposal, additions=(invalid,)).status, Status.BLOCKED_OPERATOR)

    def test_unknown_classification_remains_operator_blocked(self):
        p = self.project
        change = TicketChange("unclear", ChangeKind.UNKNOWN, "EXPLANATION", "", "Possibly more work")
        self.assertEqual(p.prepare(proposal=replace(p.proposal, changes=(change,))).status, Status.BLOCKED_OPERATOR)

    def test_valid_split_conserves_original_and_keeps_dependency_order(self):
        p = self.project
        parts = (Part("first", ("goal", "interface")), Part("second", ("accept", "check"), ("first",)))
        split = TicketChange("partition", ChangeKind.SPLIT, "PARTITION", "whole-ticket", "first then second")
        result = p.prepare(proposal=replace(p.proposal, parts=parts, changes=(split,)))
        self.assertEqual(result.status, Status.READY)
        self.assertEqual(result.packet.parts, parts)
        self.assertEqual(result.packet.clauses, p.scope.clauses)

    def test_split_dropped_duplicate_extra_and_cyclic_scope_refused(self):
        p = self.project
        split = TicketChange("partition", ChangeKind.SPLIT, "PARTITION", "whole", "parts")
        variants = ((Part("part", ("goal", "accept", "interface")),),
            (Part("part", ("goal", "accept", "interface", "check", "unknown")),),
            (Part("one", ("goal", "accept")), Part("two", ("accept", "interface", "check"))),
            (Part("one", ("goal", "accept"), ("two",)), Part("two", ("interface", "check"), ("one",))))
        for parts in variants:
            with self.subTest(parts=parts), self.assertRaises(ADPError):
                p.prepare(proposal=replace(p.proposal, parts=parts, changes=(split,)))

    def test_unreviewed_partition_cannot_pass_from_shape_alone(self):
        p = self.project
        proposal = replace(p.proposal, parts=(Part("one", ("goal", "accept")), Part("two", ("interface", "check"))))
        with self.assertRaisesRegex(ADPError, "Split requires"):
            p.prepare(proposal=proposal)
        proposal = replace(proposal, changes=(TicketChange("split", ChangeKind.SPLIT, "PARTITION", "whole", "parts"),))
        review = PreparationReview("ticket-preparer", 90, 200)
        self.assertEqual(p.prepare(proposal=proposal, review=review).status, Status.BLOCKED_OPERATOR)

    def test_ready_edited_issue_cannot_launder_original_scope(self):
        p = self.project
        original = p.snapshot.issues[0]
        changed = replace(original, body="Add a new unrelated test suite", revision="a" * 64)
        p.adapter.snapshot = replace(p.snapshot, issues=(changed,))
        proposal = replace(p.proposal, expected_issue_revision=changed.revision)
        self.assertEqual(p.prepare(proposal=proposal).status, Status.UNKNOWN)
        self.assertEqual(p.archive.original(p.reference).issue.body, original.body)

    def test_silent_acceptance_rewrite_or_removed_clause_refused(self):
        p = self.project
        clauses = tuple(replace(c, text="Weaker acceptance") if c.id == "accept" else c for c in p.scope.clauses)
        self.assertEqual(p.prepare(scope=replace(p.scope, clauses=clauses)).status, Status.BLOCKED_OPERATOR)
        with self.assertRaises(ADPError):
            p.prepare(proposal=replace(p.proposal, parts=(Part("whole", ("goal", "interface", "check")),)))
        self.assertEqual(p.prepare(readiness_reviews=p.ready_reviews(acceptance=("Weaker acceptance",))).status, Status.BLOCKED_OPERATOR)

    def test_exact_clarification_diff_requires_fresh_observation_and_review(self):
        p = self.project
        body = p.original.issue.body + " Clarification of the same behavior."
        change = TicketChange("clarify", ChangeKind.CLARIFICATION, "BODY", p.original.issue.body, body)
        proposal = replace(p.proposal, changes=(change,))
        self.assertEqual(p.prepare(proposal=proposal).status, Status.UNKNOWN)
        updated = replace(p.original.issue, body=body, revision="a" * 64)
        p.adapter.snapshot = replace(p.snapshot, issues=(updated,))
        proposal = replace(proposal, expected_issue_revision=updated.revision)
        self.assertEqual(p.prepare(proposal=proposal).status, Status.READY)
        bad = replace(change, before="Invented original")
        with self.assertRaisesRegex(ADPError, "preserve original"):
            p.prepare(proposal=replace(proposal, changes=(bad,)))

    def test_stale_issue_version_and_mid_observation_change_refused(self):
        p = self.project
        p.adapter.snapshot = replace(p.snapshot, issues=(replace(p.original.issue, revision="b" * 64),))
        self.assertEqual(p.prepare().status, Status.UNKNOWN)
        self.assertGreater(p.adapter.reads, 0)

    def test_incomplete_and_permission_limited_inventory_never_ready(self):
        p = self.project
        for state in ("PARTIAL", "FORBIDDEN", "RATE_LIMITED", "UNKNOWN", "NOTRUN"):
            p.adapter.snapshot = replace(p.snapshot, coverage=(replace(p.snapshot.coverage[0], status=state), *p.snapshot.coverage[1:]))
            with self.subTest(state=state):
                self.assertEqual(p.prepare().status, Status.UNKNOWN)

    def test_native_cycles_duplicates_and_missing_specs_block_admission(self):
        p = self.project
        relation = Relation("BLOCKED_BY", Target(p.snapshot.repository.name, p.original.issue.number,
            p.original.issue.identity.issue_id), "NATIVE", "synthetic:self-cycle")
        p.adapter.snapshot = replace(p.snapshot, issues=(replace(p.original.issue, relations=(relation,)),))
        self.assertEqual(p.prepare().status, Status.BLOCKED_DEPENDENCY)
        p.adapter.snapshot = p.snapshot
        self.assertEqual(p.prepare(readiness_reviews=p.ready_reviews(specification="UNKNOWN")).status, Status.NEEDS_SPEC)
        self.assertEqual(p.prepare(readiness_reviews=p.ready_reviews(duplicate_of=p.original.issue.identity)).status, Status.BLOCKED_DEPENDENCY)

    def test_hidden_dependency_expansion_requires_specific_scope_authority(self):
        p = self.project
        change = TicketChange("new-dep", ChangeKind.CLARIFICATION, "EXPLANATION", "", "Extra prerequisite",
            added_dependencies=(Identity("foreign", "new-task"),))
        with self.assertRaisesRegex(ADPError, "hide"):
            p.prepare(proposal=replace(p.proposal, changes=(change,)))

    def test_source_head_policy_and_repository_changes_invalidate_packet(self):
        p = self.project
        original_source = p.policy_adapter.snapshot
        for changed in (replace(original_source, revision="b" * 40),
                replace(original_source, repository_id="foreign-repo"),
                replace(original_source, source_ref="refs/heads/other"),
                replace(original_source, documents=())):
            p.policy_adapter.snapshot = changed
            with self.subTest(changed=changed):
                self.assertEqual(p.prepare().status, Status.BLOCKED_OPERATOR)
        p.policy_adapter.snapshot = original_source
        self.assertEqual(p.prepare().status, Status.READY)

    def test_expired_cross_domain_and_foreign_preparation_receipts_refused(self):
        p = self.project
        reviews = p.ready_reviews()
        track = p.preparer.observe(reviews=reviews)
        for start, end, purpose in ((90, 99, "ticket/preparation"), (101, 200, "ticket/preparation"),
                (90, 200, "policy/operation"), (90, 5000, "ticket/preparation")):
            review = PreparationReview("ticket-preparer", start, end)
            review = replace(review, evidence=p.authority.receipt(
                preparation_subject(p.original, p.scope, p.proposal, review, track), purpose))
            self.assertEqual(p.prepare(review=review, readiness_reviews=reviews).status, Status.BLOCKED_OPERATOR)

    def test_original_project_check_identities_cannot_be_invented_or_removed(self):
        p = self.project
        for checks in ((), ("invented-new-suite",)):
            scope = replace(p.scope, checks=checks, evidence=None)
            scope = replace(scope, evidence=p.authority.receipt(original_scope_subject(scope), "ticket/original-scope"))
            self.assertEqual(p.prepare(scope=scope).status, Status.BLOCKED_OPERATOR)
        self.assertFalse(hasattr(p.prepare().packet, "test_denominator"))

    def test_ticket_edit_and_execution_remain_blocked_without_dependency_integration(self):
        p = self.project
        self.assertEqual(p.preparer.submit_ticket_changes(p.proposal).status, Status.BLOCKED_DEPENDENCY)
        self.assertEqual(p.preparer.execute(p.prepare().packet).status, Status.BLOCKED_DEPENDENCY)
        self.assertTrue(p.transport.calls)
        self.assertFalse(hasattr(p.transport, "post"))

    def test_restart_reuses_immutable_baseline_but_reobserves_current_issue(self):
        p = self.project
        first = p.prepare()
        archive = TicketArchive(p.archive.directory, protected_roots=(p.product,))
        self.assertEqual(archive.original(p.reference), p.original)
        retained = archive.preparation(first.packet.preparation_reference)
        self.assertEqual(retained["subject"], first.packet.preparation_digest)
        self.assertEqual(retained["proposal"], data(p.proposal))
        p.preparer = TicketPreparer(adapters=(p.adapter,), planner=p.planner, policy=p.policy,
            authority=p.authority, archive=archive, clock=lambda: p.now)
        self.assertEqual(p.prepare().packet_reference, first.packet_reference)
        p.adapter.snapshot = replace(p.snapshot, issues=(replace(p.original.issue, body="Changed after restart"),))
        self.assertEqual(p.prepare().status, Status.UNKNOWN)

    def test_bounded_ready_window_uses_live_order_and_consumed_identities(self):
        p = self.project
        track = p.preparer.observe(reviews=p.ready_reviews())
        identity = p.original.issue.identity
        self.assertEqual(ready_window(track, (identity,)), (identity,))
        self.assertEqual(ready_window(track, (identity,), consumed=(identity,)), ())
        with self.assertRaises(ADPError):
            ready_window(track, (identity, identity))
        blocked = p.preparer.observe()
        self.assertEqual(ready_window(blocked, (identity,)), ())

    def test_product_files_refs_configuration_and_ci_remain_unchanged(self):
        p = self.project
        def seal():
            return {str(path.relative_to(p.product)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in p.product.rglob("*") if path.is_file()}
        before = seal()
        refs = git(p.product, "for-each-ref", "--format=%(refname) %(objectname)")
        self.assertEqual(p.prepare().status, Status.READY)
        self.assertEqual(seal(), before)
        self.assertEqual(git(p.product, "for-each-ref", "--format=%(refname) %(objectname)"), refs)
        self.assertEqual(git(p.product, "status", "--porcelain"), "")

    def test_private_archive_rejects_product_locations_and_unsafe_links(self):
        p = self.project
        with self.assertRaises(ADPError):
            TicketArchive(p.product / "evidence", protected_roots=(p.product,))
        path = p.archive.directory / ("original-" + p.reference.split(":")[1] + ".json")
        raw = path.read_bytes()
        path.unlink()
        external = self.root / "outside.json"
        external.write_bytes(raw)
        path.symlink_to(external)
        with self.assertRaises(ADPError):
            p.archive.original(p.reference)
        path.unlink()
        os.link(external, path)
        with self.assertRaises(ADPError):
            p.archive.original(p.reference)

    def test_missing_malformed_and_corrupted_original_evidence_refused(self):
        p = self.project
        for reference in ("../../private", "ticket-original:not-a-hash", "ticket-original:" + "0" * 64):
            with self.subTest(reference=reference), self.assertRaises((ADPError, OSError)):
                p.archive.original(reference)
        path = p.archive.directory / ("original-" + p.reference.split(":")[1] + ".json")
        path.write_text('{"schema_version":99}')
        with self.assertRaisesRegex(ADPError, "hash mismatch"):
            p.archive.original(p.reference)

    def test_credential_shaped_prepared_data_never_enters_packet_artifact(self):
        p = self.project
        proposal = replace(p.proposal, instructions=("token=fixturecredentialvalue123",))
        before = set(p.archive.directory.iterdir())
        with self.assertRaisesRegex(ADPError, "Sensitive preparation output"):
            p.prepare(proposal=proposal)
        self.assertEqual(set(p.archive.directory.iterdir()), before)

    def test_large_original_is_refused_without_truncation(self):
        p = self.project
        import adp.ticket_preparation as module
        from unittest.mock import patch
        with patch.object(module, "MAX_ARTIFACT", 100):
            with self.assertRaises(ADPError):
                p.archive.freeze(p.snapshot, p.original.issue.identity)

    def test_identical_snapshot_policy_and_approval_produce_identical_packet(self):
        first, second = self.project.prepare(), self.project.prepare()
        self.assertEqual(first, second)
        self.assertEqual(data(first.packet)["original_reference"], self.project.reference)

    def test_atomic_freeze_preflights_both_original_and_baseline_capacity(self):
        import adp.ticket_preparation as module
        from adp.schema import encode
        from adp.ticket_types import OriginalTicket
        from unittest.mock import patch
        for bound in ("files", "bytes"):
            folder = self.root / ("capacity-" + bound)
            folder.mkdir()
            p = Project(folder)
            new = replace(p.original.issue, identity=Identity(p.snapshot.repository.id, "second-issue"),
                number=2, url=p.snapshot.repository.url + "/issues/2", revision="a" * 64)
            snapshot = replace(p.snapshot, issues=(new,))
            value = data(OriginalTicket(snapshot.repository, new, snapshot.observed_at))
            before = {path.name: path.read_bytes() for path in p.archive.directory.iterdir()}
            if bound == "files":
                parameter, maximum = "MAX_ARTIFACTS", 3  # Two originals already; both new copies need two slots.
            else:
                parameter = "MAX_ARCHIVE"
                maximum = sum(len(raw) for name, raw in before.items() if name != "lock") + len(encode(value, module.MAX_ARTIFACT))
            with self.subTest(bound=bound), patch.object(module, parameter, maximum):
                with self.assertRaisesRegex(ADPError, "capacity"):
                    p.archive.freeze(snapshot, new.identity)
                self.assertEqual({path.name: path.read_bytes() for path in p.archive.directory.iterdir()}, before)

    def test_observation_elapsed_time_rechecks_all_final_evidence_lifetimes(self):
        for expiring in ("preparation", "readiness", "policy", "addition"):
            folder = self.root / ("freshness-" + expiring)
            folder.mkdir()
            p = Project(folder)
            if expiring != "policy":
                claim = replace(p.policy.sources[0], expires_at=400, evidence=None)
                claim = replace(claim, evidence=p.authority.receipt(p.policy.source_subject(claim), "policy/profile"))
                p.policy.sources = (claim,)
            proposal = replace(p.proposal, policy_digest=p.policy.inspect_repository().digest)
            additions = ()
            if expiring == "addition":
                change = TicketChange("extra", ChangeKind.ADDITION, "SCOPE", "Original", "Specific extra behavior",
                    added_clauses=(Clause("extra", "OBJECTIVE", "Specific additional behavior"),))
                proposal = replace(proposal, changes=(change,), parts=(Part("whole", ("goal", "accept", "interface", "check", "extra")),))
                approval = ScopeAdditionApproval("extra", p.reference, change_digest(change), 90, 200)
                additions = (replace(approval, evidence=p.authority.receipt(addition_subject(approval), "ticket/scope-addition", "external-operator")),)
            reviews = p.ready_reviews(expires_at=200 if expiring == "readiness" else 400)
            track = p.preparer.observe(reviews=reviews)
            review = PreparationReview("ticket-preparer", 90, 200 if expiring == "preparation" else 400)
            review = replace(review, evidence=p.authority.receipt(
                preparation_subject(p.original, p.scope, proposal, review, track), "ticket/preparation"))
            now = [100]
            p.preparer.clock = lambda: now[0]
            original_discover = p.adapter.discover
            def advance():
                snapshot = original_discover()
                now[0] = 201
                return snapshot
            p.adapter.discover = advance
            before = set(p.archive.directory.iterdir())
            with self.subTest(expiring=expiring):
                result = p.preparer.prepare(p.scope, proposal, review, readiness_reviews=reviews, additions=additions)
                self.assertNotEqual(result.status, Status.READY)
                self.assertEqual(set(p.archive.directory.iterdir()), before)
