"""Explicit operator-backed fixture services. No live repository/forge writes."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from adp.config import Config
from adp.conductor import Conductor, Project
from adp.discovery import DependencyPlanner
from adp.discovery_schema import digest
from adp.execution_memory import ExecutionJournal
from adp.execution_policy import M4ReadinessService
from adp.execution_ports import GitExecutionPort, LocalForgeBackend, SubprocessValidation
from adp.execution_types import (Admission, Capabilities, CheckCommand, Role, RuntimeObservation,
    RuntimeStatus, WorkerResult)
from adp.guard import ProgressGuard
from adp.guard_types import Attestation, Outcome, Requirement, data
from adp.memory import Memory
from adp.policy import PolicyProvider
from adp.policy_adapters import GitPolicyAdapter
from adp.policy_types import Authorization, Effect, Operation, Permission, Rules, SourceClaim, SourceKind
from test_config import run
from discovery_fixtures import Authority as DiscoveryAuthority, assessed, discover, issue


class FixtureAuthority:
    """Out-of-band fixture roster; workers cannot call or populate this object."""
    def __init__(self):
        self.receipts = set()
        self.denied = set()
        self.runtime = None

    def grant(self, *, purpose, subject, context=None):
        if purpose in self.denied:
            return None
        context = context or {}
        principal = context.get("principal") or (context.get("reviewer") if purpose == "policy/review" else None) or "operator:fixture"
        if purpose in ("progress", "forensic", "policy/review"):
            receipt = context.get("receipt")
            observations = list(self.runtime.observations.values()) if self.runtime is not None and hasattr(self.runtime, "observations") else []
            matching = [o for o in observations if o.receipt == receipt]
            if not matching or not matching[0].result.approved and purpose != "forensic":
                return None
            expected = "worker:" + matching[0].request_id
            if principal != expected:
                return None
        evidence = Attestation(principal, "fixture:authenticated-" + purpose, subject)
        self.receipts.add((evidence, purpose))
        return evidence

    def verify(self, evidence, *, purpose, subject):
        return evidence.subject == subject and (evidence, purpose) in self.receipts


class FixtureRuntime:
    def __init__(self):
        self.observations = {}
        self.requests = {}
        self.dispatch_count = 0
        self.reject_reviews = 0
        self.fail_developers = 0
        self.lose_response = False
        self.serial_corrections = False
        self.develop_count = 0
        self.host = "fixture:host"

    def capabilities(self):
        return Capabilities("fixture-runtime", self.host, "synthetic", True, True, True, True, 4)

    def dispatch(self, request):
        if request.id in self.observations:
            return self.observations[request.id]
        self.dispatch_count += 1
        self.requests[request.id] = request
        if request.role == Role.DEVELOPER:
            self.develop_count += 1
            (Path(request.workspace) / "product.py").write_text("def answer():\n    return 42\n" +
                ("# correction " + str(self.develop_count) + "\n" if self.serial_corrections else ""))
            result = WorkerResult(Outcome.FAIL if self.fail_developers else Outcome.PASS, False, (), "Bounded synthetic correction")
            self.fail_developers = max(0, self.fail_developers - 1)
        elif request.role == Role.REVIEWER:
            approved = self.reject_reviews == 0
            self.reject_reviews = max(0, self.reject_reviews - 1)
            result = WorkerResult(Outcome.PASS if approved else Outcome.FAIL, approved, ("criterion:answer",) if approved else (), "Exact-source independent fixture review")
        elif request.role == Role.FORENSIC:
            import ast
            from adp.guard_types import Classification, ForensicPlan, ForensicReport
            req = ast.literal_eval(request.prompt.split("Forensic request: ")[1])
            plan = ForensicPlan("one discriminating bounded correction", "accepted assertion verified", "measured failure persists",
                "uncertainty remains", ("deadline", "authority", "no progress"), seconds=30, samples=20, payload_bytes=10000)
            result = WorkerResult(Outcome.PASS, False, (), "Finite independent synthetic reassessment",
                ForensicReport(req["id"], Classification.PRODUCT_DEFECT, ("fixture:forensic-evidence",), "bounded correction evidence", plan))
        else:
            result = WorkerResult(Outcome.PASS, False, (), "Synthetic research")
        observation = RuntimeObservation(request.id, self.host, RuntimeStatus.COMPLETED, "fixture-context:" + request.id,
            result, "fixture:runtime-receipt:" + request.id, 0, digest(request))
        self.observations[request.id] = observation
        if self.lose_response:
            self.lose_response = False
            raise OSError("Synthetic lost dispatch response")
        return observation

    def observe(self, request_id):
        return self.observations.get(request_id, RuntimeObservation(request_id, self.host, RuntimeStatus.NOT_STARTED, None, None, "fixture:not-started", 0))

    def wait(self, request_id):
        return self.observe(request_id)

    def cancel(self, request_id):
        return self.observe(request_id)


class StaticDiscovery:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def discover(self):
        return self.snapshot


class PolicyApprover:
    def __init__(self, authority):
        self.authority = authority

    def authorize(self, plan, qualifications):
        evidence = self.authority.grant(purpose="policy/operation", subject=PolicyProvider.authorization_subject(plan, qualifications))
        return Authorization(evidence, qualifications) if evidence else None


class ExecutionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="adp-conductor-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / "remote.git"
        self.remote.mkdir()
        run(self.remote, "init", "--bare", "--initial-branch=trunk")
        self.control = self.base / "control"
        self.control.mkdir()
        run(self.control, "init", "--initial-branch=trunk")
        run(self.control, "config", "user.name", "Fixture")
        run(self.control, "config", "user.email", "fixture@example.org")
        (self.control / "product.py").write_text("def answer():\n    return 0\n")
        run(self.control, "add", ".")
        run(self.control, "commit", "-m", "synthetic accepted source")
        run(self.control, "remote", "add", "team", str(self.remote))
        run(self.control, "push", "team", "trunk")
        self.initial = run(self.control, "rev-parse", "HEAD")
        self.config = Config.discover(self.control, remote="team", branch="coordination/current", storage=self.base / "memory")
        self.memory = Memory(self.config)
        self.memory.initialize(authorized=True)
        self.memory.claim("fixture-conductor")
        self.memory.upgrade_guard(authorized=True)
        ExecutionJournal(self.memory).upgrade(authorized=True)
        self.authority, self.runtime = FixtureAuthority(), FixtureRuntime()
        self.authority.runtime = self.runtime
        self.now = 100
        self.guard = ProgressGuard(self.memory, authority=self.authority, clock=lambda: self.now)
        self.forge = LocalForgeBackend(self.base / "forge")
        self.projects, self.admissions, self.rules = {}, [], {}
        rows = [issue(1), issue(2)]
        inventory, _ = discover(rows)
        inventory = replace(inventory, repository=replace(inventory.repository,
            memory_id=self.config.identity, checkout_ref="refs/heads/trunk", checkout_sha=self.initial))
        discovery_authority = DiscoveryAuthority()
        self.discovery = StaticDiscovery(inventory)
        self.readiness = M4ReadinessService((self.discovery,), DependencyPlanner(authority=discovery_authority, clock=lambda: self.now),
            lambda snapshots: assessed(snapshots[0], discovery_authority, scope="answer returns 42", acceptance=("criterion:answer",)))
        # This checker is outside worker roots and counts a real assertion.
        self.checker = self.base / "check.py"
        self.checker.write_text("import json,os,sys\nsys.path.insert(0,os.getcwd())\nfrom product import answer\noutcomes={k:0 for k in ('PASS','FAIL','ERROR','TIMEOUT','SKIP','NOTRUN','UNKNOWN')}\noutcomes['PASS' if answer()==42 else 'FAIL']=1\nprint(json.dumps({'denominator':1,'counts':outcomes,'quarantined':0}))\n")
        import sys
        for index, name in enumerate(("one", "two"), 1):
            root = self.base / name
            run(self.base, "clone", "--origin", "team", str(self.remote), str(root))
            run(root, "config", "user.name", "Fixture")
            run(root, "config", "user.email", "fixture@example.org")
            branch = "work/" + name
            run(root, "checkout", "-b", branch)
            run(root, "push", "team", branch)
            rules = Rules(permissions=tuple(Permission(op, Effect.DENY if op in (Operation.MERGE, Operation.RELEASE, Operation.DEPLOY,
                Operation.FORCE_PUSH, Operation.REBASE, Operation.REWRITE) else Effect.ALLOW) for op in Operation),
                base_branch="trunk", branch_template="work/{slug}", subject_template="change: {summary}", body_template="Work {task}",
                subject_limit=100, pr_title_template="{summary}", pr_draft=True, checks=("unit",), reviews=1)
            self.rules[name] = rules
            cfg = Config.discover(root, remote="team", repository_id=self.config.identity)
            def policy(admission, safety, cfg=cfg, name=name):
                adapter = GitPolicyAdapter(cfg, governance=(), fingerprint_worktree=True)
                provider = PolicyProvider(adapter, authority=self.authority, safety=safety, clock=lambda: self.now)
                source = SourceClaim(SourceKind.OPERATOR, "fixture:accepted-project-policy", "b" * 64, self.rules[name], self.now, self.now + 300)
                evidence = self.authority.grant(purpose="policy/operator", subject=provider.source_subject(source))
                provider.sources = (replace(source, evidence=evidence),)
                from adp.policy_types import Protection
                snapshot = adapter.inspect()
                protections = []
                for ref in (snapshot.source_ref, "refs/heads/trunk"):
                    revision = next((r.revision for r in snapshot.remote_refs if r.name == ref), None)
                    p = Protection(ref, revision, True, True, False, (), 1, (), (), "fixture:protection", self.now, self.now + 300)
                    p = replace(p, evidence=self.authority.grant(purpose="policy/protection", subject=provider.protection_subject(p)))
                    protections.append(p)
                provider.protections = tuple(protections)
                return provider
            validator = SubprocessValidation((CheckCommand("unit", (sys.executable, "-B", str(self.checker)), 10, 1),), trusted_disposable=True)
            self.projects[name] = Project(root, policy, PolicyApprover(self.authority), GitExecutionPort(cfg, local_remotes=(self.remote,)), self.forge, validator)
            self.admissions.append(Admission(inventory.issues[index - 1].identity, "opaque-task-" + name, name, name, self.initial,
                Requirement("contract:" + name, "gate:answer", ("criterion:answer",)), "answer returns 42", "Return the accepted answer", ("product.py",)))
        self.admissions = tuple(self.admissions)
        self.conductor = Conductor(self.memory, self.guard, self.readiness, self.runtime, self.authority, self.projects, clock=lambda: self.now)
