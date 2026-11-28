"""Owned disposable Git and synthetic durable Codex-shaped receipts only."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

from adp.codex_runtime import CodexExecRuntime
from adp.discovery_schema import digest
from adp.execution_types import Capabilities, Role, WorkerResult
from adp.guard_types import Outcome, data
from adp.personal_enrollment import apply_personal
from adp.personal_runner import PersonalCoordinator
from adp import personal_workers
from adp.personal_storage import approval, create_private
from adp.schema import encode
from adp.storage import atomic
from personal_fixtures import PersonalFixture


class StoppedNotRunFixture(PersonalFixture):
    def stopped(self):
        p, original, docs = self.plan()
        self.personal = apply_personal(p, original, docs, approved=approval(p), authorized=True,
            transport=self.transport, clock=lambda: self.now)
        self.runtime = CodexExecRuntime(self.personal.state / "runtime")
        self.requests = []
        self.c = PersonalCoordinator(self.personal, self.transport, None, runtime=self.runtime, clock=lambda: self.now)
        if getattr(self, "stricter_limits", None) is not None:
            specification = self.c.specification
            patch.object(self.c, "specification", side_effect=lambda purpose:
                replace(specification(purpose), limits=self.stricter_limits) if purpose == "develop" else specification(purpose)).start()
        caps = Capabilities("codex-exec", self.runtime.host, "SYNTHETIC_NOT_GENUINE_RUNTIME", True, True, True, True, 1)
        self.addCleanup(patch.stopall)
        patch.object(self.runtime, "capabilities", return_value=caps).start()
        patch.object(self.runtime, "dispatch", side_effect=self.dispatch).start()
        self.c.initialize_run()
        run = self.c.record(); run["schema_version"] = 1
        self.c.save(run)
        original_prompt = personal_workers.prompt
        def historical_prompt(purpose, context):
            with patch.object(personal_workers, "protocol", return_value=1):
                return original_prompt(purpose, context)
        # Build original version-1 synthetic history, rather than relabel new
        # CHECK attempts as old CORRECTION attempts. This fixture-only bridge
        # grants no production legacy dispatch route and ends before return.
        with patch.object(self.c, "require_development_protocol"), \
             patch.object(personal_workers, "protocol", return_value=2), \
             patch.object(personal_workers, "prompt", side_effect=historical_prompt):
            original = self.c.workers.execute("original", self.c.context("original"), self.a)
            run = self.c.record()
            run.update(original_review=original["request"]["id"], phase="FEATURE")
            self.c.save(run)
            self.c.prepare_feature()
            with patch.object(self.c.workers, "finish", side_effect=OSError("Synthetic stopped-before-accounting interruption")):
                with self.assertRaises(OSError):
                    self.c.workers.execute("develop", self.c.context("develop"), self.personal.feature)
        self.row = next(r for r in self.c.workers.records() if r["purpose"] == "develop")
        return self.row

    def dispatch(self, request):
        self.requests.append(request)
        developer = request.role == Role.DEVELOPER
        if developer:
            (Path(request.workspace) / "product").write_text("Synthetic in-scope unfinished implementation\n")
        result = WorkerResult(Outcome.NOTRUN if developer else Outcome.PASS, not developer,
            () if developer else ("original",), "Synthetic receipt; never genuine execution evidence")
        create_private(self.runtime.directory)
        raw = {"host": self.runtime.host, "request_digest": digest(request), "status": "COMPLETED",
            "pid": 50000 + len(self.requests), "start_time": "synthetic-only", "context": "synthetic:" + request.id,
            "result": data(result), "elapsed": 1, "samples": 1, "payload_bytes": 100, "stopped": True}
        self.runtime._save(request.id, raw)
        stop = {"request_digest": digest(request), "pid": raw["pid"], "status": "EXITED", "stopped": True, "cli_exit": 0}
        atomic(self.runtime.directory / (request.id + ".stop.json"), encode(stop))
        return self.runtime.observe(request.id)

    def expired(self):
        self.stopped()
        self.now = self.personal.plan["window"]["expires_at"] + 1
        return self.row
