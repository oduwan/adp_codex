"""Two synthetic GitHub-like tracks and external authorities; no live service."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from discovery_fixtures import discover, issue
from test_policy import profile

from adp.discovery import DependencyPlanner, review_subject
from adp.discovery_types import ReadinessReview
from adp.guard_types import Attestation
from adp.policy import PolicyProvider
from adp.policy_adapters import MockRepositoryAdapter
from adp.policy_types import Document, Ref, RepositorySnapshot, SourceClaim, SourceKind
from adp.ticket_preparation import (TicketArchive, TicketPreparer, original_scope_subject,
    preparation_subject)
from adp.ticket_types import Clause, OriginalScope, Part, PreparationReview, Proposal


def git(root, *args):
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
        env=environment, stderr=subprocess.DEVNULL).decode().strip()


class Authority:
    """Explicit issued fixture receipts, not an always-true verifier."""
    def __init__(self):
        self.receipts = set()

    def receipt(self, subject, purpose, actor="independent-preparer-reviewer"):
        evidence = Attestation(actor, "synthetic:" + purpose, subject)
        self.receipts.add((evidence, purpose))
        return evidence

    def verify(self, evidence, *, purpose, subject):
        return evidence.subject == subject and (evidence, purpose) in self.receipts


class Adapter:
    def __init__(self, snapshot):
        self.snapshot, self.reads = snapshot, 0

    def discover(self):
        self.reads += 1
        return self.snapshot


class Project:
    def __init__(self, root, variant="A"):
        self.root, self.now = root, 100
        self.product = root / "product"
        self.product.mkdir()
        self.rules = profile(variant)
        self.branch = self.rules.base_branch
        git(self.product, "init", "-b", self.branch)
        git(self.product, "config", "user.name", "Disposable fixture")
        git(self.product, "config", "user.email", "fixture@example.invalid")
        (self.product / "src").mkdir()
        (self.product / "src/feature.txt").write_text("original project source\n")
        (self.product / "AGENTS.md").write_text("Use this project's prescribed checks.\n")
        git(self.product, "add", ".")
        git(self.product, "commit", "-m", "Initial disposable fixture")
        self.sha = git(self.product, "rev-parse", "HEAD")
        name, rid = ("alpha/product", "opaque-repo-A") if variant == "A" else ("beta/firmware", "opaque-repo-B")
        self.snapshot, self.transport = discover(name=name, rid=rid)
        self.snapshot = replace(self.snapshot, repository=replace(self.snapshot.repository,
            checkout_ref="refs/heads/" + self.branch, checkout_sha=self.sha))
        self.adapter = Adapter(self.snapshot)
        self.authority = Authority()
        self.planner = DependencyPlanner(authority=self.authority, clock=lambda: self.now)
        document = Document("project-policy.json", SourceKind.PROFILE, "e" * 64, self.rules)
        source = RepositorySnapshot(rid, "project-selected", "f" * 64, "refs/heads/" + self.branch,
            self.sha, "1" * 64, True, (Ref("refs/heads/" + self.branch, self.sha),),
            (Ref("refs/heads/" + self.branch, self.sha),), (document,))
        self.policy_adapter = MockRepositoryAdapter(source)
        temporary = PolicyProvider(self.policy_adapter, authority=self.authority, clock=lambda: self.now)
        claim = SourceClaim(SourceKind.PROFILE, document.reference, document.digest, self.rules, 90, 200)
        claim = replace(claim, evidence=self.authority.receipt(temporary.source_subject(claim), "policy/profile"))
        self.policy = PolicyProvider(self.policy_adapter, sources=(claim,), authority=self.authority, clock=lambda: self.now)
        self.archive = TicketArchive(root / "private-ticket-evidence", protected_roots=(self.product,))
        self.reference = self.archive.freeze(self.snapshot, self.snapshot.issues[0].identity)
        self.original = self.archive.original(self.reference)
        self.scope = OriginalScope(self.reference, "Bounded original behavior",
            (Clause("goal", "OBJECTIVE", "Bounded original behavior"),
             Clause("accept", "ACCEPTANCE", "Preserve the original observable acceptance"),
             Clause("interface", "INTERFACE", "Existing product interface"),
             Clause("check", "CHECK", "Use only project prescribed checks")),
            ("src/feature.txt",), tuple(sorted(self.rules.checks)), ())
        self.scope = replace(self.scope, evidence=self.authority.receipt(original_scope_subject(self.scope), "ticket/original-scope"))
        self.proposal = Proposal(self.reference, self.snapshot.issues[0].revision, self.policy.inspect_repository().digest,
            (Part("whole-ticket", tuple(c.id for c in self.scope.clauses)),),
            instructions=("project:AGENTS.md",), exit_conditions=("Original acceptance verified or explicit bounded stop",))
        self.preparer = TicketPreparer(adapters=(self.adapter,), planner=self.planner, policy=self.policy,
            authority=self.authority, archive=self.archive, clock=lambda: self.now)

    def ready_reviews(self, *, scope=None, acceptance=None, **changes):
        scope = scope or self.scope
        reviews = []
        for current in self.adapter.snapshot.issues:
            review = ReadinessReview(current.identity, scope.goal,
                acceptance or tuple(c.text for c in scope.clauses if c.kind == "ACCEPTANCE"),
                ("project-policy.json",), specification="KNOWN", policy="KNOWN", observed_at=90, expires_at=200)
            review = replace(review, **changes)
            review = replace(review, evidence=self.authority.receipt(
                review_subject((self.adapter.snapshot,), review), "discovery/readiness", "independent-readiness"))
            reviews.append(review)
        return tuple(reviews)

    def prepare(self, *, scope=None, proposal=None, review=None, readiness_reviews=None, additions=(), **kwargs):
        scope, proposal = scope or self.scope, proposal or self.proposal
        readiness_reviews = self.ready_reviews(scope=scope) if readiness_reviews is None else readiness_reviews
        if review is None:
            track = self.preparer.observe(reviews=readiness_reviews)
            review = PreparationReview("ticket-preparer", 90, 200)
            review = replace(review, evidence=self.authority.receipt(
                preparation_subject(self.original, scope, proposal, review, track), "ticket/preparation"))
        return self.preparer.prepare(scope, proposal, review, readiness_reviews=readiness_reviews, additions=additions, **kwargs)
