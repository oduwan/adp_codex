"""Qualifier seal/inventory checks only; never execute either full suite."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import qualification_support as support
import qualify_m6 as m6
import qualify_m7 as m7


class QualificationPreflightTests(unittest.TestCase):
    def paths(self):
        return sorted((ROOT / "docs/operations").glob("*_TEST_INVENTORY.json"))

    def test_current_preflights_preserve_exact_ids_without_running_suites(self):
        with patch.object(unittest.TextTestRunner, "run", side_effect=AssertionError("No full suite authorized")):
            source, plan, core, _ = m6.preflight()
            m7source, inventories, actual, _ = m7.preflight(self.paths())
        self.assertEqual(source, m7source)
        self.assertEqual(plan["accepted_regression_denominator"], 193)
        self.assertEqual(len(core), json.loads((ROOT / "docs/qualification/M6_PROCEDURES.json").read_text())["current_test_denominator"])
        self.assertIn("test_discovery_github.GitHubDiscoveryTests.test_foreign_issue_does_not_poison_later_valid_inventory_number", core)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(sorted(case for cases in inventories.values() for case in cases), actual)
        # The previously listed 566 IDs remain literally present. Their old
        # evidence is not relabeled as the current complete inventory.
        base = "eb24548a6ce1c606c3fdf74b045c0d27ca339ba9"
        old_paths = subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", base, "docs/operations"], text=True).splitlines()
        prior = [case for path in old_paths if path.endswith("_TEST_INVENTORY.json")
            for case in json.loads(subprocess.check_output(["git", "-C", str(ROOT), "show", base + ":" + path], text=True))]
        self.assertEqual(len(prior), 566)
        self.assertEqual(len(set(prior)), 566)
        self.assertTrue(set(prior) <= set(actual))
        original = subprocess.check_output(["git", "-C", str(ROOT), "show", m7.BASE + ":tests/test_discovery_github.py"], text=True)
        amendment = (
            "    def test_foreign_issue_does_not_poison_later_valid_inventory_number(self):\n"
            "        snapshot, _ = discover([issue(1, name=\"foreign/product\"), issue(1)])\n"
            "        self.assertEqual([i.number for i in snapshot.issues], [1])\n"
            "        self.assertTrue(any(c.status == \"PARTIAL\" for c in snapshot.coverage))\n\n")
        self.assertEqual((ROOT / "tests/test_discovery_github.py").read_text(),
            original.replace("class GitHubDiscoveryTests(unittest.TestCase):\n", "class GitHubDiscoveryTests(unittest.TestCase):\n" + amendment, 1))
        real = subprocess.check_output
        def dirty(args, **kwargs):
            return b" M tests/fixture\n" if args[-2:] == ["status", "--porcelain"] else real(args, **kwargs)
        with patch.object(subprocess, "check_output", side_effect=dirty):
            with self.assertRaisesRegex(ValueError, "clean"):m6.preflight()
            with self.assertRaisesRegex(ValueError, "clean"):m7.preflight(self.paths())

    def test_unapproved_blob_or_original_amendment_seal_refuses(self):
        real = subprocess.check_output
        for target in ("HEAD:tests/test_memory.py", "HEAD:tests/test_discovery_github.py", "original"):
            def changed(args, **kwargs):
                result = real(args, **kwargs)
                if args[-1] == target:return "0" * 40 + "\n"
                if target == "original" and "ls-tree" in args:
                    return result.replace(b"a9f39bebac1f171835068b46f6a00f9041d6cf9c", b"0" * 40)
                return result
            with self.subTest(target=target), patch.object(subprocess, "check_output", side_effect=changed), \
                 self.assertRaises(ValueError):support.verify_test_sources(ROOT, m7.BASE)

    def test_missing_duplicate_and_replaced_inventory_ids_refuse(self):
        paths = self.paths()
        raw = paths[0].read_text()
        cases, real = json.loads(raw), json.loads
        for wrong in (cases[1:], cases + [cases[0]], ["test_foreign.Unknown.test_missing", *cases[1:]]):
            with self.subTest(kind=len(wrong)), patch.object(json, "loads", side_effect=lambda text, **kw:
                    deepcopy(wrong) if text == raw else real(text, **kw)), self.assertRaises(ValueError):
                m7.preflight(paths)
        with self.assertRaisesRegex(ValueError, "inside source"):
            m7.preflight([ROOT / "tests/not-an-operation-inventory.json"])

    def test_core_denominator_scenario_and_plan_hash_drift_refuse(self):
        path = ROOT / "docs/qualification/M6_PROCEDURES.json"
        raw, real = path.read_text(), json.loads
        good = real(raw)
        for change in ({"current_test_denominator": 210}, {"plan_sha256": "0" * 64}, {"scenarios": good["scenarios"][1:]}):
            wrong = {**good, **change}
            with self.subTest(change=next(iter(change))), patch.object(json, "loads", side_effect=lambda text, **kw:
                    deepcopy(wrong) if text == raw else real(text, **kw)), self.assertRaisesRegex(ValueError, "inventory"):
                m6.preflight()
