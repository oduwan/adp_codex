"""Focused actual personal CI consumer recovery; synthetic guard/HTTP boundaries."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.errors import ADPError
from adp.guard_types import Baseline, Decision, DecisionKind, Permit, Requirement, data
from adp.personal_product import PersonalProduct
from adp.schema import require


class PersonalProductAvailabilityTests(unittest.TestCase):
    def fixture(self):
        f = PersonalProduct.__new__(PersonalProduct)
        self.now = 1000
        f.clock = lambda: self.now
        f.personal = SimpleNamespace(repository_id="17", plan={"repository": {"name": "owned/project"},
            "window": {"maximum_check_observations": 3}, "required_check_names": ["unit"]})
        f.ci_specification = Requirement("task", "personal-post-pr-validation", ("prescribed-ci-qualified",))
        run = {"observations": 1}
        f.c = SimpleNamespace(task_id="task", record=lambda: run, save=Mock(), revision=lambda: "a" * 40, allowed=Mock())
        facts = {"checks": ["unit"], "base_sha": "b" * 40, "policy": {"origins": {}, "digest": "c" * 64}}
        view = {"operation": "CI", "facts": facts, "expires_at": 1300, "issued_at": 1000,
            "nonce": "d" * 32, "revision": "a" * 40, "accept_native_records": True}
        entry = {"view": view, "approval": f.token(view, "c" * 64), "binding": "c" * 64,
            "phase": "PREPARED", "checks": [], "result": None, "reservation": None}
        row = {"execution": [entry], "gates": [], "review": "historical-review"}
        f.record, f.save = lambda: row, Mock()
        f.facts, f.pull = Mock(return_value=facts), Mock()
        f.service = SimpleNamespace(bounded=nullcontext, _check_stop=Mock())
        f.target, f.read = SimpleNamespace(ref="refs/heads/work/task"), object()
        f.proof = Mock(return_value=None)
        context = {"generation": 1, "revision": "a" * 40}
        item = {"sequence": 0, "active": None, "last": None, "unresolved": ["prescribed-ci-qualified"], "mode": "normal"}
        decision = Decision(DecisionKind.ALLOW, "synthetic reserved observation",
            Baseline("17", "e" * 64, "task", "personal-post-pr-validation", "f" * 64,
                "a" * 40, 0, 1, 0, 0, "b" * 64, ("prescribed-ci-qualified",)))
        measurements = []
        def begin(task, requirement, action):
            require(item["active"] is None, "Already active")
            item["active"] = {"id": "a" * 64, "context": context, "action": data(action), "started": 1000, "deadline": 1045}
            item["sequence"] += 1
            return Permit("a" * 64, decision)
        def active(state, task, observed, token):
            require(observed["active"] is not None and observed["active"]["id"] == token
                    and observed["active"]["context"] == context, "Unrelated reservation")
            return observed["active"]
        def observe(task, requirement, permit, measured):
            active({}, {}, item, permit.token)
            measurements.append(data(measured))
            item["last"] = {"context": context, "observation": data(measured)}
            item["active"] = None
            item["sequence"] += 1
        f.guard = SimpleNamespace(admission_subject=lambda *args: "subject", register=lambda *args: "e" * 64,
            _snapshot=lambda *args: ({}, {}, item), _context=lambda *args: context,
            begin=begin, inspect=lambda *args: decision, _active=active, observe=observe)
        return f, entry, row, run, item, measurements

    def test_missing_ambiguous_or_unavailable_identity_is_once_accounted_unknown(self):
        for inventory, error, required_origin in (({}, None, None), ({}, ADPError("PRIVATE_UNAVAILABLE"), None),
                ({"unit": ("github-check", "github-app:9")}, None, 10)):
            f, entry, row, run, item, measurements = self.fixture()
            if required_origin:
                entry["view"]["facts"]["policy"]["origins"]["unit"] = required_origin
            with self.subTest(origin=required_origin, unavailable=error is not None), patch(
                    "adp.personal_product.native_inventory", return_value=inventory, side_effect=error) as native:
                result = f.observe_ci(entry)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertFalse(result["qualified"])
                self.assertEqual(result["reason"], "NATIVE_CHECK_IDENTITY_UNAVAILABLE")
                self.assertEqual(run["observations"], 2)
                self.assertEqual(len(measurements), 1)
                self.assertIsNone(item["active"])
                self.assertIsNone(row["review"])
                self.assertNotIn("PRIVATE_UNAVAILABLE", str(result))
                self.assertEqual(entry["checks"], [])
                self.now = 1100  # Accounted recovery needs no renewed live reservation.
                self.assertEqual(f.observe_ci(entry), result)
                native.assert_called_once()
                self.assertEqual(f.facts.call_count, 1)
                self.assertEqual(f.pull.call_count, 1)
                self.assertEqual(run["observations"], 2)
                self.assertEqual(len(measurements), 1)

    def test_expired_changed_or_unsafe_saved_permit_prevents_any_identity_read(self):
        for condition in ("expired", "unsafe", "token", "context"):
            f, entry, row, run, item, measurements = self.fixture()
            f.reserve_ci(entry)
            if condition == "expired":
                self.now = 1045
            elif condition == "unsafe":
                item["mode"] = "unsafe"
            elif condition == "token":
                item["active"]["id"] = "b" * 64
            else:
                item["active"]["context"] = {"generation": 2}
            with self.subTest(condition=condition), patch("adp.personal_product.native_inventory") as native:
                with self.assertRaises(ADPError):
                    f.observe_ci(entry)
                native.assert_not_called()
                f.facts.assert_not_called()
                f.pull.assert_not_called()
                self.assertEqual(run["observations"], 1)
                self.assertEqual(measurements, [])

    def test_lost_delivery_is_unknown_without_another_native_read_or_charge(self):
        f, entry, row, run, item, measurements = self.fixture()
        f.reserve_ci(entry)
        f.charge_ci(entry)
        self.assertEqual(run["observations"], 2)
        entry["phase"] = "PREPARED"  # Crash after counter checkpoint, before phase checkpoint.
        f.charge_ci(entry)
        self.assertEqual(run["observations"], 2)
        with patch("adp.personal_product.native_inventory") as native:
            result = f.observe_ci(entry)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["reason"], "LOST_CHECK_DELIVERY")
            self.assertEqual(f.observe_ci(entry), result)
            native.assert_not_called()
            f.facts.assert_not_called()
            f.pull.assert_not_called()
        self.assertEqual(run["observations"], 2)
        self.assertEqual(len(measurements), 1)
