"""Shared authorities cannot replay evidence between distinct repositories."""
from pathlib import Path

from adp.errors import ADPError
from adp.guard import ProgressGuard
from adp.guard_types import (Action, ActionKind, Campaign, Classification, ForensicPlan,
                            ForensicReport, Observation, Outcome, Progress, ProgressKind)
from test_guard import Checkpoints, GuardFixture


class RepositoryDomainTests(GuardFixture):
    def test_all_evidence_subjects_and_permits_bind_repository_identity(self):
        other = Checkpoints(Path(self.temp.name) / "other-repository")
        _, state, tasks = other._start()
        other.config.identity = "synthetic:distinct-repository"
        state["repository_id"] = other.config.identity
        for task in tasks.values():
            task["repository_id"] = other.config.identity
        other._checkpoint(None, state, tasks)
        other_guard = ProgressGuard(other, authority=self.authority, clock=lambda: self.now)

        def admit(guard, spec):
            subject = guard.admission_subject("task-A", spec)
            return guard.register("task-A", spec, self.authority.attest(subject, "admission"))

        other_identifier = admit(other_guard, self.spec)
        self.assertEqual(other_identifier, self.identifier)  # same stable contract/gate
        self.assertNotEqual(self.guard.admission_subject("task-A", self.spec),
                            other_guard.admission_subject("task-A", self.spec))
        action = Action("author-A", ActionKind.CHECK, "identical source and hypothesis")
        first = self.guard.begin("task-A", self.identifier, action)
        second = other_guard.begin("task-A", self.identifier, action)
        self.assertNotEqual(first.token, second.token)
        self.assertNotEqual(first.decision.baseline.repository_id, second.decision.baseline.repository_id)
        observed = Observation(Outcome.PASS, ("fixture:measured",), ("criterion-B",),
            Progress(ProgressKind.REQUIREMENT_VERIFIED, "criterion-A", ("fixture:positive-proof",)))
        subject_a = self.guard.progress_subject("task-A", self.identifier, first, observed)
        subject_b = other_guard.progress_subject("task-A", self.identifier, second, observed)
        self.assertNotEqual(subject_a, subject_b)
        receipt = self.authority.attest(subject_a, "progress")
        self.guard.observe("task-A", self.identifier, first, observed, evidence=receipt)
        with self.assertRaises(ADPError):
            other_guard.observe("task-A", self.identifier, second, observed, evidence=receipt)
        actual = other.inspect()["state"]["progress_guard"]["requirements"][self.identifier]
        self.assertEqual(actual["unresolved"], list(self.spec.acceptance))

        from dataclasses import replace
        forensic = replace(self.spec, gate="forensic-domain")
        ids = [admit(guard, forensic) for guard in (self.guard, other_guard)]
        for guard, identifier in zip((self.guard, other_guard), ids):
            for _ in range(3):
                permit = guard.begin("task-A", identifier, action)
                guard.observe("task-A", identifier, permit,
                    Observation(Outcome.FAIL, ("fixture:identical-failure",), forensic.acceptance))
        request_a = self.guard.request_forensic("task-A", ids[0])
        request_b = other_guard.request_forensic("task-A", ids[1])
        self.assertNotEqual(request_a["id"], request_b["id"])
        plan = ForensicPlan("one proof", "positive", "negative", "unknown", ("safety",))
        report_a = ForensicReport(request_a["id"], Classification.UNCLASSIFIED,
            ("fixture:independent",), "same report", plan)
        report_b = replace(report_a, request_id=request_b["id"])
        subject_a = self.guard.forensic_subject("task-A", ids[0], report_a)
        subject_b = other_guard.forensic_subject("task-A", ids[1], report_b)
        self.assertNotEqual(subject_a, subject_b)
        receipt = self.authority.attest(subject_a, "forensic")
        self.guard.accept_forensic("task-A", ids[0], report_a, receipt)
        with self.assertRaises(ADPError):
            other_guard.accept_forensic("task-A", ids[1], report_a, receipt)
        with self.assertRaises(ADPError):
            other_guard.accept_forensic("task-A", ids[1], report_b, receipt)

        campaign_spec = replace(self.spec, gate="campaign-domain")
        ids = [admit(guard, campaign_spec) for guard in (self.guard, other_guard)]
        census = Campaign(("one",), "fixture:identical-inventory")
        subject_a = self.guard.campaign_subject("task-A", ids[0], census)
        subject_b = other_guard.campaign_subject("task-A", ids[1], census)
        self.assertNotEqual(subject_a, subject_b)
        with self.assertRaises(ADPError):
            other_guard.start_campaign("task-A", ids[1], census,
                self.authority.attest(subject_a, "campaign"))
