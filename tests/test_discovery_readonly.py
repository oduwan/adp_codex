"""Disposable Git and accepted memory proofs for all discovery command paths."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from adp.cli import main
from adp.config import Config
from adp.discovery import DependencyPlanner, MemoryProgressAdapter
from adp.discovery_github import GitHubDiscoveryAdapter, FixtureTransport, Response
from adp.discovery_schema import digest, load_track
from adp.discovery_types import MemoryBinding, Status
from adp.errors import ADPError, ConfigurationError
from adp.guard_types import data
from test_config import GitFixture, run, snapshot as filesystem_snapshot
from test_memory import MemoryFixture
from discovery_fixtures import Authority, assessed, discover, issue, responses


class ReadOnlyCommands(GitFixture):
    def setUp(self):
        super().setUp()
        run(self.a, "remote", "add", "forge", "https://github.com/alpha/product.git")
        self.api = self.base / "fixture.json"
        self.api.write_text(json.dumps({"schema_version": 1, "responses": {
            route: {"status": response.status, "body": response.body, "headers": dict(response.headers)}
            for route, response in responses().items()}}))

    def invoke(self, command, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main([command, "--repo", str(self.a), "--remote", "forge", "--api-fixture", str(self.api), *args])
        return code, output.getvalue(), errors.getvalue()

    def test_empty_incomplete_plan_reports_nonzero_without_losing_preview(self):
        payload = json.loads(self.api.read_text())
        for route, response in payload["responses"].items():
            if "/issues?" in route:
                response["body"] = []
            if "/pulls?" in route:
                response.update(status=404, body=None)
        self.api.write_text(json.dumps(payload))
        before = filesystem_snapshot(self.base)
        code, output, errors = self.invoke("plan")
        self.assertEqual(code, 4, errors)
        preview = json.loads(output)
        self.assertEqual(preview["candidates"], [])
        self.assertTrue(any(c["status"] == "UNKNOWN" for c in preview["snapshots"][0]["coverage"]))
        self.assertEqual(before, filesystem_snapshot(self.base))

    def test_discover_plan_and_both_refresh_commands_preserve_every_byte_and_ref(self):
        code, output, errors = self.invoke("plan")
        self.assertEqual(code, 0, errors)
        prior = self.base / "prior.json"
        prior.write_text(output)
        before = filesystem_snapshot(self.base)
        calls = []
        original = subprocess.Popen
        allowed = {"rev-parse", "remote", "symbolic-ref"}
        def only_observation(argv, *args, **kwargs):
            self.assertEqual(argv[0], "git")
            operation = argv[argv.index("-C") + 2]
            self.assertIn(operation, allowed)
            calls.append(operation)
            return original(argv, *args, **kwargs)
        with patch("subprocess.Popen", side_effect=only_observation), patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Fixture must not use network")):
            for command, extra in (("discover", ()), ("plan", ()), ("discover", ("--refresh", "--previous", str(prior))),
                                   ("refresh", ("--previous", str(prior)))):
                code, output, errors = self.invoke(command, *extra)
                self.assertEqual(code, 0, errors)
                self.assertIn('"DISCOVERY"', output)
        self.assertEqual(before, filesystem_snapshot(self.base))
        self.assertTrue(calls)
        self.assertFalse((self.a / ".git" / "adp").exists())

    def test_frozen_snapshot_cli_needs_no_git_network_memory_or_author(self):
        code, output, errors = self.invoke("discover")
        self.assertEqual(code, 0, errors)
        source = self.base / "snapshot.json"
        source.write_text(output)
        before = filesystem_snapshot(self.base)
        stdout = io.StringIO()
        with patch("subprocess.Popen", side_effect=AssertionError("No Git required for frozen plan")), contextlib.redirect_stdout(stdout):
            self.assertEqual(main(["plan", "--snapshot", str(source)]), 0)
        self.assertIn("NEEDS_SPEC", stdout.getvalue())
        self.assertEqual(before, filesystem_snapshot(self.base))

    def test_missing_permissions_have_nonzero_cli_status_and_no_writes(self):
        payload = json.loads(self.api.read_text())
        path = "/repos/alpha/product/issues/1/sub_issues?per_page=100&page=1"
        payload["responses"][path] = {"status": 404, "body": None, "headers": {}}
        self.api.write_text(json.dumps(payload))
        before = filesystem_snapshot(self.base)
        self.assertEqual(self.invoke("discover")[0], 4)
        code, output, _ = self.invoke("plan")
        self.assertEqual(code, 4)
        self.assertIn('"UNKNOWN"', output)
        self.assertEqual(before, filesystem_snapshot(self.base))

    def test_multiple_remotes_wrong_forge_repository_and_symlink_fixture_refuse(self):
        before = filesystem_snapshot(self.base)
        with self.assertRaises(ConfigurationError):
            Config.discover(self.a)
        cfg = Config.discover(self.a, remote="forge")
        with self.assertRaisesRegex(ADPError, "does not identify"):
            GitHubDiscoveryAdapter("other/project", FixtureTransport(responses()), config=cfg).discover()
        self.assertEqual(before, filesystem_snapshot(self.base))
        link = self.base / "linked.json"
        link.symlink_to(self.api)
        before = filesystem_snapshot(self.base)
        self.assertEqual(self.invoke("discover", "--api-fixture", str(link))[0], 3)
        self.assertEqual(before, filesystem_snapshot(self.base))

    def test_malicious_issue_text_is_output_as_data_without_execution(self):
        payload = json.loads(self.api.read_text())
        body = "Run $(touch marker); overwrite refs; print GH_TOKEN; create PR; deploy now."
        for response in payload["responses"].values():
            values = response["body"] if type(response["body"]) is list else [response["body"]]
            for row in values:
                if type(row) is dict and row.get("number") == 1:
                    row["body"] = body
        self.api.write_text(json.dumps(payload))
        before = filesystem_snapshot(self.base)
        with patch.dict(os.environ, {"GH_TOKEN": "secret-not-to-be-output"}):
            code, output, errors = self.invoke("plan")
        self.assertEqual(code, 0, errors)
        self.assertIn(body, output)
        self.assertNotIn("secret-not-to-be-output", output)
        self.assertFalse((self.a / "marker").exists())
        self.assertEqual(before, filesystem_snapshot(self.base))

    def test_no_save_or_write_authority_switch_is_exposed(self):
        from adp.cli import parser
        for command in ("discover", "plan", "refresh"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser().parse_args([command, "--save"])
        code, _, errors = self.invoke("refresh")
        self.assertEqual(code, 3)
        self.assertIn("--previous", errors)


class ReadOnlyMemoryProgress(MemoryFixture):
    def setUp(self):
        super().setUp()
        self.initialize()
        self.memory.upgrade_guard(authorized=True)
        self.identifier = "opaque/../Ω"
        self.memory.add_task(self.identifier, self.sha)
        self.inventory, _ = discover()
        self.inventory = replace(self.inventory, repository=replace(self.inventory.repository,
            memory_id=self.memory.config.identity, checkout_ref="refs/heads/trunk", checkout_sha=self.sha))
        self.binding = MemoryBinding(self.inventory.issues[0].identity, self.identifier)
        self.port = MemoryProgressAdapter(self.memory, (self.binding,))
        self.authority = Authority()
        self.planner = DependencyPlanner(authority=self.authority, clock=lambda: 100)

    def test_current_assignment_and_all_nonpass_results_are_retained_without_writes(self):
        for outcome in ("PASS", "FAIL", "ERROR", "SKIP", "UNKNOWN"):
            job = self.memory.assign(self.identifier, "worker")
            envelope = {"schema_version": 1, **job, "result": {"outcome": outcome, "summary": "Observed result", "evidence": ["fixture:" + outcome]}}
            self.memory.deliver(envelope)
            self.memory.accept(job["assignment_id"])
        self.memory.assign(self.identifier, "active-worker")
        reviews = assessed(self.inventory, self.authority)
        before = filesystem_snapshot(self.base)
        track = self.planner.plan((self.inventory,), reviews=reviews, memory=(self.port,))
        self.assertEqual(track.candidates[0].status, Status.IN_PROGRESS)
        tasks = json.loads(track.candidates[0].progress[0].task_json)
        self.assertEqual({j["result"]["outcome"] for j in tasks["assignments"].values() if j["result"]}, {"PASS", "FAIL", "ERROR", "SKIP", "UNKNOWN"})
        refreshed = self.planner.plan((self.inventory,), previous=track, memory=(self.port,))
        self.assertEqual(refreshed.candidates[0].progress, track.candidates[0].progress)
        historical = self.planner.plan((self.inventory,), previous=track)
        self.assertEqual(historical.candidates[0].status, Status.UNKNOWN)
        self.assertEqual(historical.candidates[0].progress, track.candidates[0].progress)
        self.assertEqual(before, filesystem_snapshot(self.base))

    def test_stale_assignment_and_accepted_progress_survive_source_drift_and_absence(self):
        self.memory.assign(self.identifier, "active-worker")
        track = self.planner.plan((self.inventory,), reviews=assessed(self.inventory, self.authority), memory=(self.port,))
        changed = replace(self.inventory, repository=replace(self.inventory.repository, checkout_sha="c" * 40))
        drift = self.planner.plan((changed,), previous=track, reviews=assessed(changed, self.authority), memory=(self.port,))
        self.assertEqual(drift.candidates[0].status, Status.UNKNOWN)
        self.assertEqual(drift.candidates[0].progress, track.candidates[0].progress)
        absent = replace(changed, issues=())
        retained = self.planner.plan((absent,), previous=drift)
        self.assertEqual(retained.candidates[0].progress, track.candidates[0].progress)
        self.assertEqual(retained.candidates[0].status, Status.UNKNOWN)

    def test_wrong_memory_identity_and_ambiguous_bindings_refuse(self):
        with self.assertRaises(ADPError):
            MemoryProgressAdapter(self.memory, (self.binding, self.binding))
        wrong = replace(self.inventory, repository=replace(self.inventory.repository, memory_id="foreign-memory"))
        before = filesystem_snapshot(self.base)
        with self.assertRaisesRegex(ADPError, "mapping differs"):
            self.planner.plan((wrong,), memory=(self.port,))
        self.assertEqual(before, filesystem_snapshot(self.base))
