"""Narrow real-Guard transition tests; synthetic authority is not runtime proof."""
from dataclasses import replace
from unittest.mock import patch

import test_guard as fixtures
from adp.errors import ADPError
from adp.guard_types import Action, ActionKind, DecisionKind, Observation, Outcome


class DevelopmentStageTests(fixtures.GuardFixture):
    def reserve(self):
        return self.guard.begin("task-A", self.identifier,
            Action("worker:original", ActionKind.CORRECTION, "worker:original", "fixed prospective stage"))

    def result(self, **kw):
        return replace(Observation(Outcome.PASS, ("runtime:stopped",), tuple(self.item()["unresolved"])), **kw)

    def test_historical_stage_shape_reproduces_premature_correction_threshold(self):
        for count in (1, 2):
            permit = self.reserve()
            self.guard.observe("task-A", self.identifier, permit, self.result())
            self.assertEqual(self.counters()["corrections"], count)
        self.assertEqual(self.guard.inspect("task-A", self.identifier).kind, DecisionKind.FORENSIC_REQUIRED)

    def test_repeated_notrun_retains_actual_outcome_and_genuine_unsuccessful_counts(self):
        for kind in (ActionKind.CHECK, ActionKind.CORRECTION):
            self.run_attempt(outcome=Outcome.NOTRUN, kind=kind)
        self.assertEqual((self.counters()["corrections"], self.counters()["stalls"], self.counters()["failures"]), (1, 2, 0))
        self.assertEqual(self.item()["last"]["observation"]["outcome"], Outcome.NOTRUN)
        self.assertIsNone(self.item()["approval"])
        self.assertEqual(self.run_attempt(outcome=Outcome.NOTRUN, kind=ActionKind.CORRECTION).kind, DecisionKind.FORENSIC_REQUIRED)
        with self.assertRaises(ADPError):self.reserve()

    def test_internal_stage_requires_explicit_exact_authority_without_checkpoint_change(self):
        permit = self.reserve()
        before = self.memory.inspect()
        with self.assertRaises(ADPError):self.guard.observe_stage("task-A", self.identifier, permit, self.result())
        self.assertEqual(self.memory.inspect(), before)
        with patch.object(self.authority, "qualify_stage", return_value=1, create=True), self.assertRaises(ADPError):
            self.guard.observe_stage("task-A", self.identifier, permit, self.result())
        self.assertEqual(self.memory.inspect(), before)

    def test_successful_internal_stage_preserves_counters_without_manufacturing_progress(self):
        self.run_attempt(kind=ActionKind.CORRECTION)
        before = self.counters()
        permit = self.reserve()
        with patch.object(self.authority, "qualify_stage", return_value=True, create=True) as verified:
            decision = self.guard.observe_stage("task-A", self.identifier, permit, self.result())
        verified.assert_called_once()
        self.assertEqual(decision.kind, DecisionKind.ALLOW)
        self.assertEqual(self.counters(), before)
        self.assertIsNone(self.item()["active"])
        self.assertIsNone(self.item()["approval"])
        self.assertEqual(self.item()["unresolved"], list(self.spec.acceptance))
        with self.assertRaises(ADPError):self.guard.observe_stage("task-A", self.identifier, permit, self.result())
        # The independent terminal evaluation still accounts a failed attempt.
        decision = self.run_attempt(kind=ActionKind.CORRECTION)
        self.assertEqual(decision.kind, DecisionKind.FORENSIC_REQUIRED)
        self.assertEqual(self.counters()["corrections"], 2)

    def test_stage_hazard_and_original_deadline_take_precedence(self):
        permit = self.reserve()
        self.now += 301
        with patch.object(self.authority, "qualify_stage", side_effect=AssertionError("unsafe first"), create=True):
            decision = self.guard.observe_stage("task-A", self.identifier, permit, self.result())
        self.assertEqual(decision.kind, DecisionKind.STOP_UNSAFE)
        self.assertIsNone(self.item()["active"])
        self.assertEqual(self.counters()["corrections"], 1)

    def test_qualification_cannot_extend_the_original_deadline(self):
        permit = self.reserve()
        def late(*args):
            self.now += 301
            return True
        with patch.object(self.authority, "qualify_stage", side_effect=late, create=True):
            decision = self.guard.observe_stage("task-A", self.identifier, permit, self.result())
        self.assertEqual(decision.kind, DecisionKind.STOP_UNSAFE)
        self.assertEqual(self.item()["last"]["observation"]["outcome"], Outcome.UNKNOWN)

    def test_changed_revision_and_nonpass_stage_cannot_skip_accounting(self):
        permit = self.reserve()
        with patch.object(self.authority, "qualify_stage", return_value=True, create=True):
            before = self.memory.inspect()
            with self.assertRaises(ADPError):
                self.guard.observe_stage("task-A", self.identifier, permit, self.result(outcome=Outcome.NOTRUN))
            self.assertEqual(self.memory.inspect(), before)
            self.memory.mutate_task("task-A", revision="b" * 40)
            with self.assertRaises(ADPError):self.guard.observe_stage("task-A", self.identifier, permit, self.result())
