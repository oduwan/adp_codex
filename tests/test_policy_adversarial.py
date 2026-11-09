"""Policy snapshots and text cannot manufacture authority or weaken gates."""
from __future__ import annotations

from dataclasses import replace

from adp.errors import ADPError
from adp.guard_types import Attestation
from adp.policy import PolicyProvider
from adp.schema import key
from adp.policy_adapters import MockRepositoryAdapter
from adp.policy_schema import parse_profile
from adp.policy_types import (Authorization, Check, Document, Effect, Operation, OutcomeCount,
    Permission, Qualifications, Ref, Request, Review, Rules, SourceClaim, SourceKind)
from test_policy import PolicyFixture


class AdversarialPolicyTests(PolicyFixture):
    def test_pr_and_merge_require_published_exact_head_and_existing_base(self):
        for operation in (Operation.PR, Operation.MERGE):
            for missing in ("stale-head", "missing-head", "missing-base"):
                refs = tuple(Ref(item.name, "7" * 40) if item.name == self.task.source_ref
                             and missing == "stale-head" else item for item in self.snapshot.remote_refs
                             if not (missing == "missing-head" and item.name == self.task.source_ref)
                             and not (missing == "missing-base" and item.name == "refs/heads/trunk"))
                self.adapter.snapshot = replace(self.snapshot, remote_refs=refs)
                provider = self.make_provider()
                plan = provider.plan(self.task, Request(operation, summary="Fix cache"))
                with self.subTest(operation=operation, metadata=missing):
                    self.assertEqual(self.authorize(plan, self.qualified(plan), provider).effect, Effect.UNKNOWN)

    def test_release_respects_authenticated_tag_push_prohibition(self):
        task = replace(self.task, source_ref="refs/heads/trunk")
        def on_base(refs):
            return tuple(Ref(item.name, task.revision) if item.name == task.source_ref else item for item in refs)
        self.adapter.snapshot = replace(self.snapshot, source_ref=task.source_ref,
            local_refs=on_base(self.snapshot.local_refs), remote_refs=on_base(self.snapshot.remote_refs))
        provider = self.make_provider()
        tag = next(p for p in provider.protections if p.ref == "refs/tags/release-1.2")
        denied = replace(tag, push_allowed=False, evidence=None)
        denied = replace(denied, evidence=self.authority.sign(provider.protection_subject(denied), "protection"))
        provider.protections = tuple(denied if p.ref == tag.ref else p for p in provider.protections)
        plan = provider.plan(task, Request(Operation.RELEASE, version="1.2"))
        self.assertEqual(self.authorize(plan, self.qualified(plan), provider).effect, Effect.DENY)

    def test_issue_and_comment_text_remain_untrusted_even_with_a_claimed_role(self):
        issue = Document("issue:opaque", SourceKind.UNTRUSTED, "6" * 64)
        self.adapter.snapshot = replace(self.snapshot, documents=self.snapshot.documents + (issue,))
        malicious = SourceClaim(SourceKind.UNTRUSTED, issue.reference, issue.digest,
            Rules(permissions=(Permission(Operation.MERGE, Effect.ALLOW),)), 90, 200)
        malicious = replace(malicious, evidence=self.authority.sign(self.provider.source_subject(malicious), "untrusted"))
        self.provider = self.make_provider(extras=(malicious,))
        inspection = self.provider.inspect_repository()
        self.assertTrue(any(p.status == "IGNORED" for p in inspection.provenance))
        plan = self.provider.plan(self.task, Request(Operation.MERGE))
        self.assertEqual(self.provider.decide(plan).effect, Effect.UNKNOWN)
        forged = SourceClaim(SourceKind.OPERATOR, "issue:pretend-operator", "7" * 64, self.rules, 90, 200,
                             Attestation("operator", "issue:self-assertion", "0" * 64))
        self.provider.sources += (forged,)
        self.assertEqual(self.provider.determine_branch(self.task).policy_effect, Effect.UNKNOWN)

    def test_profiles_reject_unknown_executors_waivers_duplicates_and_templates(self):
        for raw in (b'{"schema_version":1,"schema_version":1,"rules":{}}',
                    b'{"schema_version":1,"rules":{"execute":"touch marker"}}',
                    b'{"schema_version":1,"rules":{"disable_guard":true}}',
                    b'{"schema_version":1,"rules":{"subject_limit":true}}',
                    b'{"schema_version":1,"rules":{"subject_template":"{summary.__class__}"}}',
                    b'{"schema_version":1,"rules":{"permissions":[{"operation":"MERGE","effect":{}}]}}',
                    b'{"schema_version":1,"rules":{"branch_template":"../{slug}"}}',
                    b'{"schema_version":1,"rules":{"merge_method":"rebase"}}',
                    b'{"schema_version":NaN,"rules":{}}', b'{}' * 40000):
            with self.subTest(raw=raw[:80]), self.assertRaises(ADPError):
                parse_profile(raw)

    def test_stale_and_unavailable_protection_and_ref_metadata_do_not_grant(self):
        for changed in (dict(known=False), dict(expires_at=99), dict(revision="4" * 40),
                        dict(unsupported=("signed-commit-verification-unavailable",))):
            p = self.make_provider()
            target = next(item for item in p.protections if item.ref == self.task.source_ref)
            altered = replace(target, evidence=None, **changed)
            altered = replace(altered, evidence=self.authority.sign(p.protection_subject(altered), "protection"))
            p.protections = tuple(altered if x.ref == target.ref else x for x in p.protections)
            with self.subTest(change=changed):
                self.assertEqual(p.plan(self.task, Request(Operation.PUSH)).policy_effect, Effect.UNKNOWN)
        self.adapter.snapshot = replace(self.snapshot, remote_refs=(), remote_refs_known=False, push_relation="UNKNOWN")
        p = self.make_provider()
        self.assertEqual(p.plan(self.task, Request(Operation.PUSH)).policy_effect, Effect.UNKNOWN)

    def test_exact_operation_authority_cannot_be_replayed_across_tasks_or_operations(self):
        branch = self.provider.determine_branch(self.task)
        receipt = self.authority.sign(self.provider.authorization_subject(branch), "operation")
        self.assertEqual(self.provider.decide(branch, Authorization(receipt)).effect, Effect.ALLOW)
        push = self.provider.plan(self.task, Request(Operation.PUSH))
        self.assertEqual(self.provider.decide(push, Authorization(receipt)).effect, Effect.UNKNOWN)
        different = replace(self.task, task_id="another-opaque", branch_slug="other")
        safety = self.safety.value
        baseline = replace(safety.guard.baseline, task_key=key(different.task_id))
        self.safety.value = replace(safety, guard=replace(safety.guard, baseline=baseline), approval=baseline)
        other = self.provider.determine_branch(different)
        self.assertEqual(self.provider.decide(other, Authorization(receipt)).effect, Effect.UNKNOWN)

    def test_reviewer_labels_and_check_status_strings_do_not_self_certify(self):
        plan = self.provider.plan(self.task, Request(Operation.MERGE))
        claimed = Check("unit", self.task.revision, 1, (OutcomeCount("PASS", 1),), 0, 90, 200,
                        Attestation("ci", "issue:claims-green", "0" * 64))
        reviewer = Review("somebody-else", self.task.revision, True, 90, 200,
                          Attestation("somebody-else", "comment:approved", "0" * 64))
        evidence = Qualifications((claimed,), (reviewer,))
        self.assertEqual(self.authorize(plan, evidence).effect, Effect.UNKNOWN)
        valid = self.qualified(plan)
        stale = replace(valid.checks[0], revision="2" * 40, evidence=None)
        stale = replace(stale, evidence=self.authority.sign(self.provider.check_subject(plan, stale), "check"))
        self.assertEqual(self.authorize(plan, replace(valid, checks=(stale,) + valid.checks[1:])).effect, Effect.UNKNOWN)

    def test_cross_repository_progress_review_check_and_operation_domains_are_distinct(self):
        first = self.provider.plan(self.task, Request(Operation.MERGE))
        qualification = self.qualified(first)
        grant = Authorization(self.authority.sign(self.provider.authorization_subject(first, qualification), "operation"), qualification)
        other_task = replace(self.task, repository_id="repo:synthetic-B")
        self.adapter.snapshot = replace(self.snapshot, repository_id=other_task.repository_id)
        old_safety = self.safety.value
        baseline = replace(old_safety.guard.baseline, repository_id=other_task.repository_id)
        self.safety.value = replace(old_safety, guard=replace(old_safety.guard, baseline=baseline), approval=baseline)
        self.provider = self.make_provider()
        other = self.provider.plan(other_task, Request(Operation.MERGE))
        self.assertNotEqual(self.provider.authorization_subject(first, qualification), self.provider.authorization_subject(other, qualification))
        self.assertEqual(self.provider.decide(other, grant).effect, Effect.UNKNOWN)
        self.assertNotEqual(self.provider.review_subject(first, qualification.reviews[0]),
                            self.provider.review_subject(other, qualification.reviews[0]))
        self.assertNotEqual(self.provider.check_subject(first, qualification.checks[0]),
                            self.provider.check_subject(other, qualification.checks[0]))
        self.assertEqual(self.authorize(other, qualification).effect, Effect.UNKNOWN)

    def test_edited_plans_denominators_duplicate_reviewers_and_typed_payloads_refuse(self):
        plan = self.provider.plan(self.task, Request(Operation.MERGE))
        qualification = self.qualified(plan)
        edited = replace(plan, required_reviews=0)
        self.assertEqual(self.authorize(edited, qualification).effect, Effect.DENY)
        with self.assertRaises(ADPError):
            self.provider.check_subject(plan, replace(qualification.checks[0], denominator=2))
        with self.assertRaises(ADPError):
            self.authorize(plan, replace(qualification, reviews=qualification.reviews * 2))
        for malformed in (Rules(permissions=({},)), Rules(permissions=(Permission(Operation.MERGE, {}),))):
            with self.subTest(rule=malformed), self.assertRaises(ADPError):
                self.provider.source_subject(SourceClaim(SourceKind.PROFILE, "workflow.json", "e" * 64, malformed, 90, 200))
        with self.assertRaises(ADPError):
            MockRepositoryAdapter(replace(self.snapshot, local_refs=({},)))
        with self.assertRaises(ADPError):
            self.provider.decide(plan, {})

    def test_mergeability_is_explicit_and_never_inferred_from_credentials(self):
        for methods, expected in ((None, Effect.UNKNOWN), ((), Effect.DENY)):
            provider = self.make_provider()
            original = next(p for p in provider.protections if p.ref == "refs/heads/trunk")
            item = replace(original, mergeable_methods=methods, evidence=None)
            item = replace(item, evidence=self.authority.sign(provider.protection_subject(item), "protection"))
            provider.protections = tuple(item if p.ref == item.ref else p for p in provider.protections)
            self.assertEqual(provider.plan(self.task, Request(Operation.MERGE)).policy_effect, expected)

    def test_contracts_cannot_override_git_semantics_without_governance_authority(self):
        document = Document("accepted-task", SourceKind.CONTRACT, "7" * 64)
        self.adapter.snapshot = replace(self.snapshot, documents=self.snapshot.documents + (document,))
        for rules in (Rules(base_branch="other"), Rules(branch_template="outside/{slug}"),
                      Rules(release_template="other/{version}")):
            item = SourceClaim(SourceKind.CONTRACT, document.reference, document.digest, rules, 90, 200)
            item = replace(item, evidence=self.authority.sign(self.provider.source_subject(item), "contract"))
            provider = self.make_provider(extras=(item,))
            self.assertEqual(provider.determine_branch(self.task).policy_effect, Effect.UNKNOWN)
