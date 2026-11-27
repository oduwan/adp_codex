"""Issue71 local contract proofs, not genuine Codex/pilot qualification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from dataclasses import replace

from adp.errors import ADPError
from adp.execution_types import WorkerResult
from adp.guard_types import Outcome
from adp import personal_workers as workers
from adp.execution_containment import source_seal


class DeveloperContractTests(unittest.TestCase):
    def context(self):
        return {"purpose": "develop", "paths": ["product", "test_product.py"], "development_protocol": 2}

    def test_prospective_prompt_requires_scoped_testing_and_defines_candidate_pass(self):
        message = workers.prompt("develop", self.context())
        self.assertNotIn("or execute project checks", message)
        self.assertIn("must execute", message)
        self.assertIn("newly added", message)
        self.assertIn("focused", message)
        self.assertIn("approved=false", message)
        self.assertIn("not independent approval", message)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", message)

    def test_legacy_prompt_identity_is_preserved_and_unknown_versions_refuse(self):
        context = {"purpose": "develop", "paths": ["product", "test_product.py"]}
        self.assertEqual(hashlib.sha256(workers.prompt("develop", context).encode()).hexdigest(),
            "589de6a25ba99e7cb76d73373249aa21255e9ddb1fb33aa2582a41ebd2e33e56")
        with self.assertRaises(ADPError):workers.prompt("develop", {**context, "development_protocol": 999})

    def test_bounded_real_local_test_uses_workspace_temp_without_outside_artifacts(self):
        with TemporaryDirectory(prefix="adp-development-contract-") as directory:
            root = Path(directory)
            (root / "product").write_text("original scope\n")
            before = source_seal(root, ("product", "test_product.py"))
            (root / "test_product.py").write_text(
                "import os, pathlib, tempfile, unittest\n"
                "class Local(unittest.TestCase):\n"
                " def test_original(self):\n"
                "  self.assertEqual(pathlib.Path('product').read_text(), 'original scope\\n')\n"
                "  with tempfile.TemporaryDirectory(dir='.') as d:\n"
                "   pathlib.Path(d, 'scratch').write_text('temporary')\n")
            command = [sys.executable, "-B", "-m", "unittest", "test_product", "-v"]
            completed = subprocess.run(command, cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10, check=False)
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertIn(b"Ran 1 test", completed.stdout)
            report = json.dumps({"change": "Implemented original scope", "checks": [
                {"command": "python -B -m unittest test_product -v", "outcome": "PASS", "result": "1/1 PASS"}], "limitations": "Local only; CI unqualified"})
            result = WorkerResult(Outcome.PASS, False, (), report)
            workers.developer_validation(self.context(), result)
            self.assertFalse((root / "__pycache__").exists())
            self.assertEqual(source_seal(root, ("product", "test_product.py")), before)
            original_test = (root / "test_product.py").read_text()
            (root / "test_product.py").write_text("import unittest\nclass Failed(unittest.TestCase):\n def test_failure(self): self.fail('concrete finding')\n")
            failed = subprocess.run(command, cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10, check=False)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn(b"concrete finding", failed.stdout)
            wrong = json.loads(report);wrong["checks"][0]["outcome"] = "FAIL"
            with self.assertRaises(ADPError):workers.developer_validation(self.context(), WorkerResult(Outcome.PASS, False, (), json.dumps(wrong)))
            (root / "test_product.py").write_text(original_test)
            corrected = subprocess.run(command, cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10, check=False)
            self.assertEqual(corrected.returncode, 0, corrected.stdout)
            self.assertIn(b"Ran 1 test", corrected.stdout)
            workers.developer_validation(self.context(), result)

    def test_pass_without_local_evidence_or_with_self_approval_refuses(self):
        for summary in ("Implemented; no tests", json.dumps({"change": "done", "checks": [], "limitations": ""})):
            with self.subTest(summary=summary), self.assertRaises(ADPError):
                workers.developer_validation(self.context(), WorkerResult(Outcome.PASS, False, (), summary))
        workers.developer_validation(self.context(), WorkerResult(Outcome.NOTRUN, False, (), "Focused tool unavailable; not executed"))
        # Legacy raw observations are authenticated as issued, not retrofitted.
        workers.developer_validation({}, WorkerResult(Outcome.PASS, False, (), "Historical summary"))
        report = json.dumps({"change": "done", "checks": [{"command": "focused", "outcome": "PASS", "result": "1/1"}], "limitations": ""})
        result = WorkerResult(Outcome.PASS, False, (), report)
        for invalid in (replace(result, approved=True), replace(result, criteria=("develop",)),
                replace(result, summary=report[:-1] + ',"change":"duplicate"}')):
            with self.assertRaises(ADPError):workers.developer_validation(self.context(), invalid)
