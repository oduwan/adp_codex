"""Opt-in REAL Codex proof on an owned disposable synthetic project only.

Never part of the unattended test suite; needs authenticated supported CLI and
explicit operator execution authorization. The synthetic provisioner contains no
live GitHub transport. JSON evidence goes to an explicitly selected external file.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from adp.codex_runtime import CodexExecRuntime
from adp.conductor import Conductor
from adp.discovery_schema import digest
from adp.execution_types import Role, RuntimeStatus
from adp.git import value
from execution_fixtures import ExecutionFixture


class AuditedRuntime(CodexExecRuntime):
    def __init__(self, directory):
        super().__init__(directory)
        self.observations, self.requests = {}, {}

    def dispatch(self, request):
        self.requests[request.id] = request
        result = super().dispatch(request)
        self.observations[request.id] = result
        return result

    def wait(self, request_id):
        result = super().wait(request_id)
        self.observations[request_id] = result
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorize-disposable-execution", action="store_true")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if not args.authorize_disposable_execution:
        parser.error("explicit disposable execution authority required")
    if args.evidence.absolute().is_relative_to(ROOT):
        parser.error("runtime evidence must stay outside source history")
    fixture = ExecutionFixture()
    fixture.setUp()
    runtime = AuditedRuntime(fixture.base / "real-runtime")
    fixture.authority.runtime = runtime
    fixture.guard.clock = lambda: int(time.time())
    engine = Conductor(fixture.memory, fixture.guard, fixture.readiness, runtime, fixture.authority,
                       fixture.projects, clock=lambda: fixture.now)
    report = {"source_head": value(ROOT, "rev-parse", "HEAD"), "runtime": runtime.capabilities().__dict__,
              "project": "disposable synthetic answer contract", "live_github_mutations": 0}
    try:
        report["execution"] = engine.run(fixture.admissions[:1], maximum_parallel=1, rounds=2, authorized=True)
        report["workers"] = [{"role": runtime.requests[rid].role, "request_id": rid, "context_id": obs.context_id,
            "revision": runtime.requests[rid].revision, "status": obs.status, "receipt": obs.receipt,
            "request_digest": obs.request_digest, "result": obs.result.__dict__ if obs.result else None}
            for rid, obs in runtime.observations.items()]
        report["product_head"] = value(fixture.projects["one"].root, "rev-parse", "HEAD")
        report["product_content"] = (fixture.projects["one"].root / "product.py").read_text()
        roles = {w["role"] for w in report["workers"] if w["status"] == RuntimeStatus.COMPLETED}
        contexts = [w["context_id"] for w in report["workers"]]
        report["qualified"] = (report["execution"]["status"] == "COMPLETE" and {Role.DEVELOPER,Role.REVIEWER} <= roles
                               and len(set(contexts)) == len(contexts))
    except Exception as exc:
        report.update(qualified=False, error=type(exc).__name__ + ": " + str(exc))
    finally:
        report["evidence_digest"] = digest(report)
        args.evidence.write_text(json.dumps(report, indent=2, sort_keys=True))
        fixture.doCleanups()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["qualified"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
