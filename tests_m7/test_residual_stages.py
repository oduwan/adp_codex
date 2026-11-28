"""R5 actual MERGE/completion/REPORT/NEXT with retained synthetic prerequisites."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import resource
import time
from collections import Counter
from contextlib import ExitStack
from unittest.mock import patch

from adp.memory import Memory
from adp.policy import PolicyProvider
from adp.personal_report import PersonalReport
from adp.personal_storage import load_state
from adp.runtime_limits import capture_measurements
from residual_stage_fixtures import ResidualStageFixture
from test_config import run


class ResidualStageTests(ResidualStageFixture):
    def measure(self, name, call):
        counts = Counter()
        from adp.project_validation import ProjectValidation
        actual_unknown = ProjectValidation._unknown
        def unknown(validation, request, reason):
            import sys, traceback
            error = sys.exception()
            print("NATIVE_CI_UNKNOWN " + json.dumps({"stage": name, "reason": reason,
                "exception": type(error).__name__ if error else None,
                "message": str(error)[:512] if error else None,
                "frames": [{"function": frame.name, "line": frame.lineno, "file": Path(frame.filename).name}
                    for frame in traceback.extract_tb(error.__traceback__)[-10:]] if error else []}, sort_keys=True), flush=True)
            return actual_unknown(validation, request, reason)
        actual_http = self.http.request
        def http(method, path, body, **kw):
            counts["http:" + method + " " + path] += 1
            return actual_http(method, path, body, **kw)
        actual_plan, actual_inspect = PolicyProvider.plan, Memory.inspect
        def plan(*a, **kw):
            counts["plans"] += 1
            return actual_plan(*a, **kw)
        def inspect(*a, **kw):
            counts["memory"] += 1
            return actual_inspect(*a, **kw)
        from adp import git
        actual_git = git.git
        def observed_git(*a, **kw):
            counts["git"] += 1
            return actual_git(*a, **kw)
        # Existing Git helpers retain imported bindings. Patch each binding to
        # the same actual function; no helper result is replaced.
        import sys
        started, cpu = time.perf_counter(), time.process_time()
        child = resource.getrusage(resource.RUSAGE_CHILDREN)
        with ExitStack() as stack:
            for module in tuple(sys.modules.values()):
                if getattr(module, "__name__", "").startswith("adp.") and getattr(module, "git", None) is actual_git:
                    stack.enter_context(patch.object(module, "git", observed_git))
            stack.enter_context(patch.object(self.http, "request", http))
            stack.enter_context(patch.object(PolicyProvider, "plan", plan))
            stack.enter_context(patch.object(Memory, "inspect", inspect))
            stack.enter_context(patch.object(ProjectValidation, "_unknown", unknown))
            with capture_measurements() as telemetry:
                try:
                    result = call()
                finally:
                    after = resource.getrusage(resource.RUSAGE_CHILDREN)
                    print("RESIDUAL_STAGE " + json.dumps({"stage": name, "issue": self.personal.plan["issue"], "counts": dict(counts),
                        "wall": time.perf_counter()-started, "cpu": time.process_time()-cpu,
                        "child_cpu": after.ru_utime+after.ru_stime-child.ru_utime-child.ru_stime,
                        "telemetry_dropped": telemetry["dropped"], "telemetry_errors": telemetry["errors"],
                        "operations": list(telemetry["rows"])}, sort_keys=True), flush=True)
                    if __import__("sys").exception() is not None:
                        error = __import__("sys").exception()
                        try:self.retain(name+".failed")
                        except Exception as retention:error.add_note("Private fixture retention failed: " + type(retention).__name__)
        self.retain(name)
        self.assertEqual((telemetry["dropped"], telemetry["errors"]), (0, 0))
        for operation in telemetry["rows"]:
            self.assertGreater(operation["operation_remaining_seconds"], 0)
            self.assertGreaterEqual(operation["requests_remaining"], 0)
        return result

    def retain(self, stage):
        """Private raw disposable-fixture evidence only, never an engine input."""
        destination = os.environ.get("ADP_FOCUSED_EVIDENCE")
        if destination is None:return
        root = Path(destination)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = root / (str(self.personal.plan["issue"])+"-"+stage)
        if path.exists():raise AssertionError("Never overwrite retained fixture evidence")
        shutil.copytree(self.base, path, symlinks=True)
        manifest = {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file() and not p.is_symlink()}
        (root / (path.name+".hashes.json")).write_text(json.dumps(manifest, sort_keys=True)+"\n")
        print("FIXTURE_EVIDENCE " + json.dumps({"stage": stage, "issue": self.personal.plan["issue"],
            "files": len(manifest), "manifest_sha256": hashlib.sha256((root / (path.name+".hashes.json")).read_bytes()).hexdigest()}, sort_keys=True), flush=True)

    def original_stages(self, number):
        p = self.late_prerequisites(current=number > 1)
        self.assertEqual(self.personal.plan["issue"], number)
        proposal = self.measure("merge.preview", lambda: p.proposed("MERGE", method="merge", delegate=True))
        merged = self.measure("merge.intent", lambda: p.intent("MERGE", reviewed=proposal["approval"], authorized=True,
            authorize_memory=True, assume_quiescence=True, confirm_rules=True, method="merge", delegate=True,
            accept_envelope=True, accept_plan_unavailable=self.private_free))
        self.assertEqual(merged["status"], "MERGED_DELEGATED_VERIFIED")
        self.assertEqual(len([e for e in self.http.effects if e[0] == "PUT"]), 1)
        track = self.c.track
        preview = self.measure("completion.preview", lambda: track.completion_preview(p))
        accepted = self.measure("completion.apply", lambda: track.complete(p, reviewed=preview["approval"], authorized=True, confirm_acceptance=True))
        self.assertEqual(accepted["source"], self.c.revision())
        report = PersonalReport(self.c, transport=self.http)
        self.http.authorize_write = report.write_authorized
        proposed = self.measure("report.preview", report.report_preview)
        result = self.measure("report.intent", lambda: report.report(reviewed=proposed["approval"], authorized=True,
            authorize_memory=True, assume_quiescence=True, confirm_rules=True))
        self.assertEqual(result["status"], "REPORTED")
        self.assertEqual(len(self.all_comments), number)
        # Observation-only repeat must not dispatch a second comment.
        repeated = self.measure("report.reobserve", lambda: report.report(reviewed=proposed["approval"], authorized=True,
            authorize_memory=True, assume_quiescence=True, confirm_rules=True))
        self.assertEqual(repeated["status"], "REPORTED")
        self.assertEqual(len(self.all_comments), number)
        run(self.a, "fetch", "--no-tags", "--no-write-fetch-head", str(self.store), accepted["merge"])
        run(self.a, "merge", "--ff-only", accepted["merge"])
        if number == 3:
            return
        from dataclasses import replace
        from adp.discovery_schema import digest
        successor = next(i for i, o in track.originals.items() if o.issue.number == number+1)
        choices = replace(self.choices, issue=number+1, directory=track.root / "windows" / digest(successor), branch="work/issue-"+str(number+1))
        preview = self.measure("next.preview", lambda: track.next_preview(report, choices))
        result = self.measure("next.apply", lambda: track.next(report, choices, reviewed=preview["approval"],
            setup_approval=preview["setup_approval"], authorized=True))
        self.assertEqual(result["status"], "NEXT_ENROLLED_SCOPE_REVIEW_REQUIRED")
        from pathlib import Path
        child = load_state(Path(result["directory"]))
        self.assertIsNone(self.personal.memory().inspect()["state"]["owner"])
        self.assertTrue(child.memory().inspect()["local_owner"])
        self.assertFalse((child.state / "run.json").exists())
        self.assertEqual(child.memory().inspect()["state"]["generation"], 1)
        from adp.personal_product_review import ProductCoordinator
        self.personal, self.choices, self.directory = child, choices, child.directory
        self.connect_runtime()
        self.c = ProductCoordinator(child, report.read, report.read, runtime=self.runtime, clock=lambda: self.now)
        self.assertTrue(self.c.track.require_attachment() is None)
        status = self.measure("next.successor_status", lambda: self.c.track.status(transport=self.http)[0])
        selected = next(r for r in status["issues"] if r["issue"] == number+1)
        self.assertNotEqual(selected["status"], "READY")
        self.assertEqual(selected["completion"], "NOT_ACCEPTED")

    def test_three_original_late_stages_and_private_free_native_policy(self):
        self.private_free = True
        for number in (1, 2, 3):
            print("ORIGINAL_STAGE_CASE " + str(number), flush=True)
            self.original_stages(number)
        self.assertEqual(len(self.all_comments), 3)
        self.assertEqual(len(self.all_pulls), 3)
        self.assertTrue(all(p["merged"] is True for p in self.all_pulls))
