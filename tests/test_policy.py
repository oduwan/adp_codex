"""Synthetic policy decisions with explicit independent, out-of-band authority."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace

from adp.errors import ADPError
from adp.guard_types import Attestation, Baseline, Decision as GuardDecision, DecisionKind
from adp.policy import PolicyProvider
from adp.policy_adapters import MockRepositoryAdapter
from adp.policy_schema import digest
from adp.policy_types import (Authorization, Check, Document, Effect, Operation, OutcomeCount,
    Permission, Protection, Qualifications, Ref, RepositorySnapshot, Request, Review,
    Rules, Safety, SourceClaim, SourceKind, Task)
from adp.schema import key


class Authority:
    def __init__(self):
        self.receipts = set()

    def sign(self, subject, purpose, principal=None):
        principal = principal or ("operator" if purpose in ("operation", "operator") else "independent-" + purpose)
        evidence = Attestation(principal, "fixture:" + purpose, subject)
        self.receipts.add((evidence, "policy/" + purpose))
        return evidence

    def verify(self, evidence, *, purpose, subject):
        return evidence.subject == subject and (evidence, purpose) in self.receipts


class SafetyPort:
    def __init__(self, safety):
        self.value = safety
        self.calls = 0

    def observe(self, task):
        self.calls += 1
        return self.value


def profile(variant="A"):
    return Rules(
        permissions=tuple(Permission(op, Effect.ALLOW if (variant == "A" or op != Operation.MERGE) else Effect.DENY)
                          for op in Operation if op not in (Operation.FORCE_PUSH, Operation.REBASE, Operation.REWRITE)),
        base_branch="trunk" if variant == "A" else "integration",
        branch_template="work/{slug}" if variant == "A" else "change-{slug}",
        subject_template="change({task}): {summary}" if variant == "A" else "{summary}",
        body_template="Work: {task}" if variant == "A" else "Ticket={task}",
        subject_limit=72 if variant == "A" else 110,
        pr_title_template="[{task}] {summary}" if variant == "A" else "{summary} / {task}",
        pr_draft=variant == "A", merge_method="squash" if variant == "A" else "ff_only",
        release_template="release-{version}" if variant == "A" else "build/{version}",
        environments=("sandbox",), checks=("unit", "integration") if variant == "A" else ("portable",),
        reviews=1 if variant == "A" else 2)


class PolicyFixture(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.authority = Authority()
        self.rules = profile()
        self.task = Task("repo:synthetic-A", "ABC-opaque", "cache-fix", "a" * 40,
                         "refs/heads/work/cache-fix", "b" * 64, 1, 7, 1, ("developer",))
        baseline = Baseline(self.task.repository_id, self.task.requirement_id, "contract:accepted",
            "gate:accepted", key(self.task.task_id), self.task.revision, 1, 1, 7, 9, "c" * 64, ())
        self.safety = SafetyPort(Safety(GuardDecision(DecisionKind.ALLOW, "verified progress", baseline),
                                      True, ("developer",), "d" * 40, baseline))
        self.document = Document("workflow.json", SourceKind.PROFILE, "e" * 64, self.rules)
        self.snapshot = RepositorySnapshot(self.task.repository_id, "team", "f" * 64,
            self.task.source_ref, self.task.revision, "1" * 64, True,
            (Ref(self.task.source_ref, self.task.revision), Ref("refs/heads/trunk", "9" * 40)),
            (Ref(self.task.source_ref, self.task.revision), Ref("refs/heads/trunk", "9" * 40)),
            (self.document,), push_relation="SAME")
        self.adapter = MockRepositoryAdapter(self.snapshot)
        self.provider = self.make_provider()

    def make_provider(self, *, rules=None, kind=SourceKind.PROFILE, reference="workflow.json", extras=()):
        rules = rules or self.rules
        doc = next((d for d in self.adapter.snapshot.documents if d.reference == reference), None)
        claim = SourceClaim(kind, reference, doc.digest if doc else "e" * 64, rules, 90, 200)
        p = PolicyProvider(self.adapter, authority=self.authority, safety=self.safety, clock=lambda: self.now)
        claim = replace(claim, evidence=self.authority.sign(p.source_subject(claim), kind.lower()))
        protections = []
        for ref in (self.task.source_ref, "refs/heads/" + rules.base_branch, "refs/tags/release-1.2", "refs/tags/build/1.2"):
            old = next((r.revision for r in self.adapter.snapshot.remote_refs if r.name == ref), None)
            item = Protection(ref, old, True, True, True, (), 0, ("merge", "squash", "ff_only"), (),
                              "fixture:protection", 90, 200)
            item = replace(item, mergeable_methods=("merge", "squash", "ff_only"))
            item = replace(item, evidence=self.authority.sign(p.protection_subject(item), "protection"))
            protections.append(item)
        return PolicyProvider(self.adapter, sources=(claim, *extras), protections=tuple(protections),
            authority=self.authority, safety=self.safety, clock=lambda: self.now)

    def qualified(self, plan, *, outcome="PASS", quarantine=0, reviewers=1):
        checks = []
        for name in plan.required_checks:
            item = Check(name, plan.task.revision, 1, (OutcomeCount(outcome, 1),), quarantine, 90, 200)
            item = replace(item, evidence=self.authority.sign(self.provider.check_subject(plan, item), "check"))
            checks.append(item)
        reviews = []
        for number in range(reviewers):
            principal = f"reviewer-{number}"
            item = Review(principal, plan.task.revision, True, 90, 200)
            item = replace(item, evidence=self.authority.sign(self.provider.review_subject(plan, item), "review", principal))
            reviews.append(item)
        return Qualifications(tuple(checks), tuple(reviews))

    def authorize(self, plan, qualifications=Qualifications(), provider=None):
        provider = provider or self.provider
        evidence = self.authority.sign(provider.authorization_subject(plan, qualifications), "operation")
        return provider.decide(plan, Authorization(evidence, qualifications))


class PolicyDecisionTests(PolicyFixture):
    def test_distinct_project_rules_and_no_implicit_write(self):
        self.assertEqual(self.provider.determine_branch(self.task).payload.name, "work/cache-fix")
        commit = self.provider.determine_commit(self.task, "Fix cache")
        self.assertEqual(commit.payload.subject, "change(ABC-opaque): Fix cache")
        self.assertEqual(commit.payload.body, "Work: ABC-opaque")
        self.assertEqual(self.provider.decide(commit).effect, Effect.UNKNOWN)
        self.assertEqual(self.authorize(commit).effect, Effect.ALLOW)
        pr = self.provider.determine_pr(self.task, "Fix cache")
        self.assertTrue(pr.payload.draft)
        self.assertEqual(self.authorize(pr).effect, Effect.ALLOW)
        self.assertEqual(self.provider.determine_validation(self.task).required_checks, ("integration", "unit"))

    def test_merge_requires_separate_rights_checks_independence_and_m2_approval(self):
        plan = self.provider.plan(self.task, Request(Operation.MERGE))
        self.assertEqual(plan.payload.method, "squash")
        self.assertEqual(self.authorize(plan).effect, Effect.UNKNOWN)
        qualified = self.qualified(plan)
        self.assertEqual(self.authorize(plan, qualified).effect, Effect.ALLOW)
        self.assertEqual(self.provider.decide(plan).effect, Effect.UNKNOWN)  # credential success is not a grant
        self.safety.value = replace(self.safety.value, approval=None)
        plan = self.provider.plan(self.task, Request(Operation.MERGE))
        self.assertEqual(self.authorize(plan, self.qualified(plan)).effect, Effect.UNKNOWN)

    def test_every_nonpass_and_quarantine_remains_nonpass(self):
        for outcome in ("FAIL", "ERROR", "TIMEOUT", "SKIP", "NOTRUN", "UNKNOWN"):
            plan = self.provider.plan(self.task, Request(Operation.MERGE))
            with self.subTest(outcome=outcome):
                self.assertEqual(self.authorize(plan, self.qualified(plan, outcome=outcome)).effect, Effect.DENY)
        plan = self.provider.plan(self.task, Request(Operation.MERGE))
        self.assertEqual(self.authorize(plan, self.qualified(plan, quarantine=1)).effect, Effect.DENY)

    def test_changed_head_ref_index_and_guard_reject_cached_authority(self):
        for field, value in (("revision", "2" * 40), ("index_digest", "2" * 64),
                             ("remote_fingerprint", "3" * 64), ("source_ref", "refs/heads/elsewhere")):
            self.adapter.snapshot = self.snapshot
            self.provider = self.make_provider()
            plan = self.provider.determine_branch(self.task)
            grant = Authorization(self.authority.sign(self.provider.authorization_subject(plan), "operation"))
            self.adapter.snapshot = replace(self.snapshot, **{field: value})
            with self.subTest(field=field):
                self.assertEqual(self.provider.decide(plan, grant).effect, Effect.DENY)
        self.adapter.snapshot = self.snapshot
        self.provider = self.make_provider()
        plan = self.provider.determine_branch(self.task)
        self.safety.value = replace(self.safety.value, guard=replace(self.safety.value.guard,
            baseline=replace(self.safety.value.guard.baseline, sequence=10)), approval=None)
        self.assertEqual(self.authorize(plan).effect, Effect.DENY)

    def test_guard_ownership_and_independent_review_cannot_be_waived(self):
        for kind in (DecisionKind.STOP_UNSAFE, DecisionKind.OPERATOR_DECISION_REQUIRED, DecisionKind.FORENSIC_REQUIRED):
            original = self.safety.value
            self.safety.value = replace(original, guard=replace(original.guard, kind=kind), approval=None)
            plan = self.provider.determine_branch(self.task)
            self.assertEqual(self.authorize(plan).effect, Effect.DENY)
            self.safety.value = original
        self.safety.value = replace(self.safety.value, owns_memory=False)
        self.assertEqual(self.authorize(self.provider.determine_branch(self.task)).effect, Effect.DENY)
        self.safety.value = replace(self.safety.value, owns_memory=True)
        plan = self.provider.plan(self.task, Request(Operation.MERGE))
        qualified = self.qualified(plan)
        own = Review("developer", self.task.revision, True, 90, 200)
        own = replace(own, evidence=self.authority.sign(self.provider.review_subject(plan, own), "review", "developer"))
        self.assertEqual(self.authorize(plan, replace(qualified, reviews=(own,))).effect, Effect.DENY)
        blocking = Review("blocking-reviewer", self.task.revision, False, 90, 200)
        blocking = replace(blocking, evidence=self.authority.sign(self.provider.review_subject(plan, blocking), "review", "blocking-reviewer"))
        self.assertEqual(self.authorize(plan, replace(qualified, reviews=qualified.reviews + (blocking,))).effect, Effect.DENY)

    def test_missing_unverified_and_conflicting_policy_fail_closed(self):
        empty = PolicyProvider(MockRepositoryAdapter(replace(self.snapshot, documents=())), safety=self.safety)
        self.assertEqual(empty.determine_branch(self.task).policy_effect, Effect.UNKNOWN)
        no_authority = PolicyProvider(self.adapter, sources=self.provider.sources, safety=self.safety)
        self.assertEqual(no_authority.determine_branch(self.task).policy_effect, Effect.UNKNOWN)
        governance = Document("AGENTS.md", SourceKind.GOVERNANCE, "4" * 64)
        contribution = Document("CONTRIBUTING.md", SourceKind.GOVERNANCE, "5" * 64)
        self.adapter.snapshot = replace(self.snapshot, documents=(governance, contribution))
        claims = []
        for document, rules in ((governance, self.rules), (contribution, replace(self.rules, branch_template="other/{slug}"))):
            item = SourceClaim(document.kind, document.reference, document.digest, rules, 90, 200)
            item = replace(item, evidence=self.authority.sign(self.provider.source_subject(item), "governance"))
            claims.append(item)
        conflict = PolicyProvider(self.adapter, sources=tuple(claims), authority=self.authority, safety=self.safety, clock=lambda: self.now)
        self.assertEqual(conflict.determine_branch(self.task).policy_effect, Effect.UNKNOWN)

    def test_provenance_priority_and_contracts_cannot_grant_rights(self):
        gov = Document("AGENTS.md", SourceKind.GOVERNANCE, "4" * 64)
        self.adapter.snapshot = replace(self.snapshot, documents=(gov, self.document))
        override = SourceClaim(SourceKind.GOVERNANCE, gov.reference, gov.digest,
            replace(self.rules, branch_template="governed/{slug}"), 90, 200)
        override = replace(override, evidence=self.authority.sign(self.provider.source_subject(override), "governance"))
        self.provider = self.make_provider(extras=(override,))
        self.assertEqual(self.provider.determine_branch(self.task).payload.name, "governed/cache-fix")
        contract = Document("accepted-contract", SourceKind.CONTRACT, "6" * 64)
        self.adapter.snapshot = replace(self.snapshot, documents=(contract,))
        claimed = self.make_provider(kind=SourceKind.CONTRACT, reference=contract.reference)
        self.assertEqual(claimed.determine_branch(self.task).policy_effect, Effect.UNKNOWN)

    def test_protections_divergence_and_rewrite_never_silently_fallback(self):
        for op in (Operation.FORCE_PUSH, Operation.REBASE, Operation.REWRITE):
            self.assertEqual(self.provider.plan(self.task, Request(op)).policy_effect, Effect.DENY)
        self.provider.protections = ()
        self.assertEqual(self.provider.plan(self.task, Request(Operation.PUSH)).policy_effect, Effect.UNKNOWN)
        self.provider = self.make_provider()
        target = next(p for p in self.provider.protections if p.ref == self.task.source_ref)
        target = replace(target, push_allowed=False, evidence=None)
        target = replace(target, evidence=self.authority.sign(self.provider.protection_subject(target), "protection"))
        self.provider.protections = tuple(target if p.ref == target.ref else p for p in self.provider.protections)
        self.assertEqual(self.provider.plan(self.task, Request(Operation.PUSH)).policy_effect, Effect.DENY)
        self.adapter.snapshot = replace(self.snapshot, push_relation="DIVERGED")
        self.assertEqual(self.provider.plan(self.task, Request(Operation.PUSH)).policy_effect, Effect.DENY)
