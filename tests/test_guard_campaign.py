"""Finite diagnostic censuses retain denominator and every non-PASS outcome."""
from dataclasses import replace

from adp.errors import ADPError, Conflict
from adp.guard import GuardRefusal
from adp.guard_types import Campaign, DecisionKind, Outcome
from test_guard import GuardFixture


class CampaignTests(GuardFixture):
    def start(self, spec):
        subject = self.guard.campaign_subject("task-A", self.identifier, spec)
        return self.guard.start_campaign("task-A", self.identifier, spec,
            self.authority.attest(subject, "campaign"))

    def test_non_fail_fast_census_preserves_all_counts_and_denominator(self):
        outcomes = (Outcome.FAIL, Outcome.ERROR, Outcome.TIMEOUT, Outcome.PASS,
                    Outcome.SKIP, Outcome.NOTRUN, Outcome.FAIL, Outcome.PASS)
        inventory = tuple(f"method-{index}" for index in range(len(outcomes)))
        token = self.start(Campaign(inventory, "fixture:original-campaign", inventory[-2:]))
        for index, outcome in enumerate(outcomes):
            case, admission = self.guard.next_case("task-A", self.identifier, token)
            self.assertEqual(case, inventory[index])
            self.assertEqual(admission.scope, "campaign")
            decision = self.guard.record_case("task-A", self.identifier, token, case, outcome)
            if index < len(outcomes) - 1:
                self.assertEqual(decision.kind, DecisionKind.ALLOW)
                with self.assertRaises(GuardRefusal):
                    self.run_attempt()
        summary = self.guard.campaign_summary("task-A", self.identifier)
        self.assertEqual(summary["original_denominator"], 8)
        self.assertEqual(summary["counts"], {"PASS": 1, "FAIL": 1, "ERROR": 1,
            "TIMEOUT": 1, "SKIP": 1, "NOTRUN": 1, "QUARANTINED": 2})
        self.assertEqual(sum(summary["counts"].values()), 8)
        self.assertEqual(summary["raw_counts"]["FAIL"], 2)
        self.assertEqual(summary["raw_counts"]["PASS"], 2)
        self.assertEqual(summary["observed"], 8)
        self.assertEqual(summary["attempted"], 6)
        self.assertFalse(summary["formal_acceptance"])
        self.assertFalse(summary["all_observed_pass"])
        self.assertTrue(summary["complete"])
        self.assertIsNone(summary["stopped"])
        self.assertEqual(decision.kind, DecisionKind.FORENSIC_REQUIRED)
        with self.assertRaises(Conflict):
            self.guard.record_case("task-A", self.identifier, token, inventory[-1], Outcome.PASS)

    def test_quarantine_and_notrun_cannot_create_pass(self):
        for index, outcomes in enumerate(((Outcome.PASS, Outcome.PASS), (Outcome.PASS, Outcome.NOTRUN))):
            self.identifier = self.register(replace(self.spec, gate=f"quarantine:{index}"))
            spec = Campaign(("one", "two"), "fixture:excluded", ("two",))
            token = self.start(spec)
            for case, outcome in zip(spec.inventory, outcomes):
                self.guard.record_case("task-A", self.identifier, token, case, outcome)
            summary = self.guard.campaign_summary("task-A", self.identifier)
            self.assertEqual(summary["counts"]["PASS"], 1)
            self.assertEqual(summary["counts"]["QUARANTINED"], 1)
            self.assertFalse(summary["all_observed_pass"])
            self.assertFalse(summary["formal_acceptance"])

    def test_safety_contamination_and_containment_stop_remaining_cases(self):
        for index, risk in enumerate(("safety", "contamination", "authority", "containment")):
            self.identifier = self.register(replace(self.spec, gate=f"stop:{index}"))
            token = self.start(Campaign(("one", "two", "three"), "fixture:stopped"))
            decision = self.guard.record_case("task-A", self.identifier, token, "one", Outcome.ERROR, risk=risk)
            self.assertEqual(decision.kind, DecisionKind.STOP_UNSAFE)
            summary = self.guard.campaign_summary("task-A", self.identifier)
            self.assertEqual(summary["counts"]["ERROR"], 1)
            self.assertEqual(summary["counts"]["NOTRUN"], 2)
            self.assertEqual(summary["original_denominator"], 3)
            with self.assertRaises(GuardRefusal):
                self.guard.next_case("task-A", self.identifier, token)
            with self.assertRaises(Conflict):
                self.guard.record_case("task-A", self.identifier, token, "two", Outcome.PASS)

    def test_deadline_clock_and_source_checks_precede_next_admission(self):
        for index, violation in enumerate(("deadline", "clock", "source", "generation")):
            self.identifier = self.register(replace(self.spec, gate=f"containment:{index}"))
            token = self.start(Campaign(("one", "two"), "fixture:limits", seconds=2))
            if violation == "deadline":
                self.now += 3
            elif violation == "clock":
                self.now -= 1
            elif violation == "source":
                self.memory.mutate_task("task-A", revision="b" * 40)
            else:
                self.memory.mutate_task("task-A", generation=2)
            with self.assertRaises(GuardRefusal) as denied:
                self.guard.next_case("task-A", self.identifier, token)
            self.assertEqual(denied.exception.decision.kind, DecisionKind.STOP_UNSAFE)
            self.assertEqual(self.guard.campaign_summary("task-A", self.identifier)["counts"]["NOTRUN"], 2)
            self.now = max(self.now, 100)

    def test_inventory_reorder_budget_widening_and_repeated_campaign_refused(self):
        spec = Campaign(("one", "two"), "fixture:bounded", samples=2, payload_bytes=2)
        token = self.start(spec)
        with self.assertRaises(ADPError):
            self.guard.record_case("task-A", self.identifier, token, "two", Outcome.PASS)
        self.guard.record_case("task-A", self.identifier, token, "one", Outcome.PASS, samples=2)
        decision = self.guard.record_case("task-A", self.identifier, token, "two", Outcome.FAIL, samples=1)
        self.assertEqual(decision.kind, DecisionKind.STOP_UNSAFE)
        summary = self.guard.campaign_summary("task-A", self.identifier)
        self.assertEqual(summary["counts"]["FAIL"], 1)
        with self.assertRaises(ADPError):
            self.guard.campaign_subject("task-A", self.identifier, replace(spec, seconds=3601))
        with self.assertRaises(GuardRefusal):
            self.start(spec)
        self.identifier = self.register(replace(self.spec, gate="single-census"))
        token = self.start(Campaign(("one",), "fixture:single"))
        self.guard.record_case("task-A", self.identifier, token, "one", Outcome.PASS)
        with self.assertRaises(ADPError):
            self.start(Campaign(("new alias",), "fixture:repeated"))

    def test_campaign_can_finish_after_stall_but_cannot_override_escalation(self):
        self.stall()
        spec = Campaign(("assertion-A", "assertion-B"), "fixture:authorized-survey")
        token = self.start(spec)
        self.guard.record_case("task-A", self.identifier, token, "assertion-A", Outcome.FAIL)
        self.guard.record_case("task-A", self.identifier, token, "assertion-B", Outcome.ERROR)
        self.assertTrue(self.guard.campaign_summary("task-A", self.identifier)["complete"])
        self.assertEqual(self.guard.inspect("task-A", self.identifier).kind, DecisionKind.FORENSIC_REQUIRED)
        self.review(finite=False)
        with self.assertRaises(GuardRefusal):
            self.start(spec)

    def test_large_fixed_inventory_is_bounded_and_restart_persistent(self):
        spec = Campaign(tuple(f"case-{index}" for index in range(256)), "fixture:finite-inventory")
        token = self.start(spec)
        self.guard.record_case("task-A", self.identifier, token, "case-0", Outcome.FAIL)
        from adp.guard import ProgressGuard
        self.guard = ProgressGuard(self.memory, authority=self.authority, clock=lambda: self.now)
        self.assertEqual(self.guard.next_case("task-A", self.identifier, token)[0], "case-1")
        summary = self.guard.campaign_summary("task-A", self.identifier)
        self.assertEqual(summary["original_denominator"], 256)
        self.assertEqual(summary["counts"]["NOTRUN"], 255)
        with self.assertRaises(ADPError):
            self.guard.campaign_subject("task-A", self.identifier,
                replace(spec, inventory=spec.inventory + ("too-many",)))
