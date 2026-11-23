"""Purpose-bound semantic receipts over one actual original Reviewer context."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .config import Config
from .discovery import DependencyPlanner, review_subject
from .discovery_schema import digest, typed
from .discovery_types import Identity, ReadinessReview, Snapshot, Status, Track
from .guard_types import Attestation, data
from .personal_enrollment import governance
from .personal_runner import LocalPolicyAdapter
from .personal_storage import read_private
from .personal_track import immutable, same_observation
from .policy import PolicyProvider
from .policy_types import SourceClaim, SourceKind
from .schema import require
from .ticket_preparation import (TicketPreparer, original_scope_subject, preparation_subject)
from .ticket_types import Clause, OriginalScope, Part, PreparationReview, Proposal


class FrozenObservation:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def discover(self):
        return self.snapshot


def scope_for(track, identity, paths, checks):
    original = track.originals[identity]
    reference = track.archive.frozen_reference(identity)
    dependencies = []
    for edge in original.issue.relations:
        if edge.kind == "BLOCKED_BY" and edge.confidence == "NATIVE":
            matches = [i for i, o in track.originals.items() if o.repository.name == edge.target.repository
                and o.issue.number == edge.target.number and i.issue_id == edge.target.issue_id]
            require(len(matches) == 1, "Original native prerequisite is outside the finite original inventory")
            dependencies.append(matches[0])
    # The reference denotes the COMPLETE original, not a generated replacement
    # acceptance specification. Its interpretation is judged with the full text.
    return OriginalScope(reference, "Complete the unchanged original " + original.issue.url,
        (Clause("objective", "OBJECTIVE", "Complete original title and body retained at " + reference),
         Clause("acceptance", "ACCEPTANCE", "original-ticket:" + original.issue.revision)),
        tuple(paths), tuple(checks), tuple(sorted(dependencies)))


def unsigned_policy(c):
    p = c.personal.plan
    root = Path(p["checkout"]["path"])
    require(digest(governance(root)) == p["governance_digest"], "Original governance changed before preparation")
    adapter = LocalPolicyAdapter(Config.discover(root, remote=p["checkout"]["remote"], repository_id=c.personal.repository_id),
        governance=tuple(d["path"] for d in c.personal.intent["governance"]), fingerprint_worktree=True)
    snapshot = adapter.inspect()
    start, end = p["window"]["issued_at"], p["window"]["expires_at"]
    claims = (SourceClaim(SourceKind.OPERATOR, "personal:exact-local-choices", digest(p), c.rules(), start, end),
        *(SourceClaim(d.kind, d.reference, d.digest, c.rules(), start, end) for d in snapshot.documents))
    return adapter, snapshot, claims


def semantic_bundle(track):
    c, p = track.c, track.personal.plan
    selected = typed(Identity, track.link["identity"])
    scope = scope_for(track, selected, p["paths"], p["required_check_names"])
    snapshot = track.seed()
    require(snapshot.repository.checkout_sha == p["checkout"]["head"]
            and snapshot.repository.checkout_ref == p["checkout"]["ref"], "Preparation source differs from the approved window")
    # Admission's original snapshot is immutable. Mechanical predecessor proof
    # summaries are frozen into that exact semantic bundle before its Reviewer.
    lineage = read_private(track.root / "admissions" / (digest(selected) + ".json"))
    completions = lineage["completions"]
    return {"schema_version": 1, "selected": data(selected), "snapshot": data(snapshot),
        "originals": [data(o) for _, o in sorted(track.originals.items())], "scope": data(scope),
        "policy_snapshot": lineage["policy_snapshot"], "policy_sources": lineage["policy_sources"],
        "proposal": {"parts": [data(Part("original", ("objective", "acceptance")))], "changes": [],
            "instructions": [], "exit_conditions": ["Original scope only; missing evidence or authority stops admission."]},
        "completion_observations": completions,
        "judgment": "Independently assess this complete unchanged original, every proposed clause/path/check/policy and actual native prerequisite disposition. An opaque criterion refers to ALL original acceptance, not a reduced replacement. Reject unresolved inferred dependencies, scope additions or unsupported project requirements. This approves preparation only; future Issues need separate operator scope/window and their own original Reviewer."}


class ContextAuthority:
    """Authenticate wrappers of the exact approved bundle, never arbitrary text."""
    def __init__(self, track, worker, bundle, policy):
        self.track, self.worker, self.bundle = track, worker, bundle
        self.policy = policy
        self.receipts = {}

    def subject(self, purpose, payload):
        """Closed typed, lossless projection; never attest a caller's hash."""
        expected = typed(OriginalScope, self.bundle["scope"])
        snapshot = typed(Snapshot, self.bundle["snapshot"])
        if purpose == "ticket/original-scope":
            require(type(payload) is OriginalScope and replace(payload, evidence=None) == expected,
                    "Unseen original-scope interpretation")
            return original_scope_subject(payload)
        if purpose == "discovery/readiness":
            require(type(payload) is ReadinessReview, "Typed readiness body required")
            completed = {typed(Identity, row["identity"]) for row in self.bundle["completion_observations"]}
            require(payload.identity in completed | {typed(Identity, self.bundle["selected"])}, "Unreviewed future original")
            original = self.track.originals[payload.identity]
            reference = ReadinessReview(payload.identity, "Complete the unchanged original " + original.issue.url,
                ("original-ticket:" + original.issue.revision,), tuple(s["reference"] for s in self.bundle["policy_sources"]),
                specification="KNOWN", policy="KNOWN", completed=payload.identity in completed,
                observed_at=snapshot.observed_at, expires_at=self.track.personal.plan["window"]["expires_at"])
            require(replace(payload, evidence=None) == reference, "Readiness adds unreviewed semantic claims/time/authority")
            return review_subject((snapshot,), payload)
        require(purpose == "ticket/preparation" and type(payload) is tuple and len(payload) == 5,
                "Unsupported preparation evidence purpose/body")
        original, scope, proposal, review, observed_track = payload
        selected = typed(Identity, self.bundle["selected"])
        require(original == self.track.originals[selected]
                and type(scope) is OriginalScope and replace(scope, evidence=None) == expected
                and self.verify(scope.evidence, purpose="ticket/original-scope", subject=original_scope_subject(scope)),
                "Preparation original/scope differs from the independently judged body")
        inspection = self.policy.inspect_repository()
        require(not inspection.conflicts and inspection.sources
                and data(inspection.snapshot) == self.bundle["policy_snapshot"], "Preparation policy/source changed")
        expected_proposal = Proposal(expected.original_reference, original.issue.revision, inspection.digest,
            (Part("original", ("objective", "acceptance")),), exit_conditions=tuple(self.bundle["proposal"]["exit_conditions"]))
        require(proposal == expected_proposal and type(review) is PreparationReview
                and replace(review, evidence=None) == PreparationReview("personal:coordinator", snapshot.observed_at,
                    self.track.personal.plan["window"]["expires_at"]), "Unseen preparation changes/partition/instructions/time")
        require(type(observed_track) is Track and observed_track.snapshots == (snapshot,), "Unreviewed discovery context")
        reviews = tuple(r for candidate in observed_track.candidates for r in candidate.reviews)
        for readiness in reviews:
            require(self.verify(readiness.evidence, purpose="discovery/readiness", subject=review_subject((snapshot,), readiness)),
                    "Unverified readiness in preparation")
        replanned = DependencyPlanner(authority=self, clock=self.track.c.clock).plan((snapshot,), reviews=reviews)
        require(replanned == observed_track, "Preparation is not the actual reviewed M4 derivation")
        return preparation_subject(original, scope, proposal, review, observed_track)

    def evidence(self, purpose, payload):
        c = self.track.c
        require(c.original_approval() == self.worker, "Actual original Reviewer differs")
        require(self.worker["context"].get("track_preparation") == self.bundle
                and semantic_bundle(self.track) == self.bundle, "Preparation semantic projection changed")
        c.workers.actual(self.worker, approval=True, accounted=True)
        subject = self.subject(purpose, payload)
        principal = "worker:" + self.worker["request"]["id"]
        proof = Attestation(principal, "personal-track:" + digest({"bundle": self.bundle,
            "worker": self.worker["observation"], "purpose": purpose, "subject": subject}), subject)
        self.receipts[purpose, subject] = (proof, payload)
        return proof

    def verify(self, evidence, *, purpose, subject):
        retained = self.receipts.get((purpose, subject))
        if retained is None or retained[0] != evidence:
            return False
        self.track.c.workers.actual(self.worker, approval=True, accounted=True)
        require(self.worker["context"].get("track_preparation") == self.bundle
                and semantic_bundle(self.track) == self.bundle, "Current approved preparation context differs")
        require(self.subject(purpose, retained[1]) == subject, "Exact typed preparation subject differs")
        return True


def prepare(track):
    c = track.c
    worker = c.original_approval()
    bundle = semantic_bundle(track)
    require(worker["context"].get("track_preparation") == bundle, "Original Reviewer did not inspect this preparation")
    retained = read_private(c.personal.state / "prepared-track.json", optional=True)
    if retained is None:
        require(same_observation(track.current().snapshot, typed(Snapshot, bundle["snapshot"])),
                "Native admission context changed after its independent judgment")
    else:
        # Re-derive the actual conserved packet/proof below; an opaque pointer
        # to another valid same-Issue packet cannot substitute for this window.
        c.fresh()
    adapter, source, claims = unsigned_policy(c)
    require(data(source) == bundle["policy_snapshot"] and [data(claim) for claim in claims] == bundle["policy_sources"], "Reviewed policy changed")
    policy = PolicyProvider(adapter, authority=c.authority, clock=c.clock)
    policy.sources = tuple(c.authority.source(policy, claim, source) for claim in claims)
    inspection = policy.inspect_repository()
    require(not inspection.conflicts and inspection.sources, "Reviewed current policy is not verified")
    authority = ContextAuthority(track, worker, bundle, policy)
    snapshot = typed(Snapshot, bundle["snapshot"])
    scope = typed(OriginalScope, bundle["scope"])
    scope = replace(scope, evidence=authority.evidence("ticket/original-scope", scope))
    selected = scope_for(track, typed(Identity, track.link["identity"]), c.personal.plan["paths"], c.personal.plan["required_check_names"])
    completed = {typed(Identity, row["identity"]): row for row in bundle["completion_observations"]}
    reviews = []
    for identity in (*sorted(completed), typed(Identity, track.link["identity"])):
        original = track.originals[identity]
        review = ReadinessReview(identity, "Complete the unchanged original " + original.issue.url,
            ("original-ticket:" + original.issue.revision,), tuple(s.reference for s in inspection.sources),
            specification="KNOWN", policy="KNOWN", completed=identity in completed,
            observed_at=snapshot.observed_at, expires_at=c.personal.plan["window"]["expires_at"])
        review = replace(review, evidence=authority.evidence("discovery/readiness", review))
        reviews.append(review)
    planner = DependencyPlanner(authority=authority, clock=c.clock)
    track_view = planner.plan((snapshot,), reviews=tuple(reviews))
    candidate = next(item for item in track_view.candidates if item.identity == typed(Identity, track.link["identity"]))
    require(not any(edge.kind == "PULL_REQUEST" for edge in candidate.issue.relations),
            "An existing linked PR needs independent reassessment, not a new original admission")
    require(candidate.status == Status.READY, "Original preparation is not READY in the actual native dependency graph")
    proposal = Proposal(scope.original_reference, candidate.issue.revision, inspection.digest,
        (Part("original", ("objective", "acceptance")),), exit_conditions=tuple(bundle["proposal"]["exit_conditions"]))
    # Evidence/true policy hashes are mechanical wrappers. All semantic fields
    # must project losslessly to the actual independently approved context.
    require(data(replace(scope, evidence=None)) == bundle["scope"]
            and [data(part) for part in proposal.parts] == bundle["proposal"]["parts"] and not proposal.changes
            and not proposal.instructions and proposal.exit_conditions == tuple(bundle["proposal"]["exit_conditions"])
            and proposal.expected_issue_revision == track.originals[candidate.identity].issue.revision,
            "Preparation adds unseen semantic content")
    review = PreparationReview("personal:coordinator", snapshot.observed_at, c.personal.plan["window"]["expires_at"])
    review = replace(review, evidence=authority.evidence("ticket/preparation",
        (track.originals[candidate.identity], scope, proposal, review, track_view)))
    preparer = TicketPreparer(adapters=(FrozenObservation(snapshot),), planner=planner, policy=policy,
        authority=authority, archive=track.archive, clock=c.clock)
    result = preparer.prepare(scope, proposal, review, readiness_reviews=tuple(reviews))
    require(result.status == Status.READY and result.packet is not None, "Actual TicketPreparer refused the original admission")
    immutable(c.personal.state / "prepared-track.json", {"schema_version": 1, "packet": result.packet_reference,
        "worker": worker["request"]["id"], "bundle": digest(bundle)})
    return result.packet
