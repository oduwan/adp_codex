"""Focused guided protocol tests using existing non-M8 Git and provider fixtures."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests_m7"))
from operator_fixtures import OperatorFixture, run

from adp.cli import main
from adp.discovery_github import FixtureTransport, GitHubDiscoveryAdapter, Response
from adp.enrollment import read_intent
from adp.errors import ADPError
from adp.execution_memory import ExecutionJournal
from adp.git import value
from adp.memory import Memory
from adp.operator_profile import load_profile
from discovery_fixtures import issue, responses


class GuidedEnrollmentTests(OperatorFixture):
    def setUp(self):
        super().setUp()
        self.directory = self.auth / "guided"
        self.socket = self.auth / "proposal.sock"
        self.rows = [issue(n, name=self.name, body="Private fixture ticket context") for n in range(1, 4)]
        self.entries = responses(self.rows, name=self.name, rid=self.rid)
        self.prefix = "/repos/" + self.name
        self.entries[self.prefix] = Response(200, {"id": int(self.rid), "node_id": self.node,
                                                  "full_name": self.name, "default_branch": "trunk"})
        for n in (2, 3):
            self.entries[f"{self.prefix}/issues/{n}/dependencies/blocked_by?per_page=100&page=1"] = Response(200, self.rows[n - 2:n - 1])
        self.entries[self.prefix + "/branches/trunk"] = Response(200, {"name": "trunk", "protected": True})
        self.entries[self.prefix + "/rules/branches/trunk"] = Response(200, [{
            "type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "unit"}]}}])
        self.transport = FixtureTransport(self.entries)
        self.snap = GitHubDiscoveryAdapter(self.name, self.transport, expected_id=self.rid,
                                          config=self.profile.project_config(self.profile.tasks[0]),
                                          clock=lambda: self.now).discover()
        self.install_assessment()
        self.write(self.auth / "results.json", self.signed("project-evidence", {
            "repository_id": self.rid, "request": {"repository_id": self.rid, "source_ref": "refs/heads/work/one",
                "revision": self.head, "policy_digest": "c" * 64, "phase": "BEFORE_PR",
                "task_id": self.body["tasks"][0]["task_id"], "generation": 0,
                "task_epoch": 0, "iteration": 0, "pull": None}, "results": [],
            "observed_at": self.now, "complete": False, "coverage": "UNKNOWN"}))
        self.reply = self.signed("profile", copy.deepcopy(self.body))
        for patcher in (
            patch("adp.enrollment_cli.discovery_token", return_value="fixture-bootstrap-token"),
            patch("adp.enrollment_cli.GitHubHTTPTransport", side_effect=lambda token: self.transport),
            patch("adp.operator_controller.DiscoveryHTTP", side_effect=lambda token: self.transport),
            patch("adp.enrollment_cli.runtime_capability", return_value={"status": "SUPPORTED", "qualification": "NOTRUN"}),
            patch("adp.enrollment.runtime_capability", return_value={"status": "SUPPORTED", "qualification": "NOTRUN"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, command, *options, configured=True, proposal=True):
        argv = ["enroll", command, "--repo", str(self.product), "--remote", "origin"]
        if configured:
            argv += ["--directory", str(self.directory), "--operator-trust", str(self.trust)]
        if proposal:
            argv += ["--issue", "1", "--operator-socket", str(self.socket)]
        output = io.StringIO()
        with redirect_stdout(output):
            emitted = main(argv + list(options))
        report = json.loads(output.getvalue())
        for private in ("fixture-bootstrap-token", "fixture-private-", "key_hex", "Private fixture ticket context"):
            self.assertNotIn(private, output.getvalue())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["execution_authority"], "UNKNOWN")
        return emitted, report

    def proposed(self):
        with patch("adp.enrollment.exchange", return_value=self.reply) as exchange:
            code, report = self.call("plan")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "PROPOSED")
        return report, exchange

    def assert_blocked(self, report, code):
        self.assertIn(code, {entry["code"] for entry in report["blockers"]}, report)

    def test_inspection_reports_native_three_issue_graph_without_writes(self):
        code, report = self.call("inspect", configured=False, proposal=False)
        self.assertEqual(code, 0, report)
        facts = report["facts"]
        self.assertEqual(facts["repository"]["database_id"], int(self.rid))
        self.assertEqual(facts["repository"]["node_id"], self.node)
        self.assertEqual(facts["checkout"]["head"], self.head)
        self.assertEqual(facts["installation"]["engine"], "AVAILABLE")
        self.assertEqual([[(edge["kind"], edge["number"]) for edge in issue["native_dependencies"]]
                          for issue in facts["issues"]], [[], [("BLOCKED_BY", 1)], [("BLOCKED_BY", 2)]])
        self.assertEqual(facts["branch_rules"][1]["required_check_contexts"], ["unit"])
        self.assert_blocked(report, "AUTHORITY_NOT_ESTABLISHED")
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.profile.state.exists())
        self.assertEqual(value(self.bare, "for-each-ref"), "")
        self.assertEqual(value(self.product, "status", "--porcelain"), "")

    def test_plan_questions_and_missing_discovery_auth_are_structured(self):
        code, report = self.call("plan", configured=False, proposal=False)
        self.assertEqual(code, 4)
        self.assertEqual({r["id"] for r in report["questions"]},
                         {"enrollment_directory", "operator_trust", "operator_proposal_service", "issue"})
        from adp.enrollment import Blocked
        with patch("adp.enrollment_cli.discovery_token", side_effect=Blocked("DISCOVERY_CREDENTIAL_REQUIRED", "Authenticate GitHub CLI.")):
            code, report = self.call("inspect", configured=False, proposal=False)
        self.assertEqual(code, 4)
        self.assert_blocked(report, "DISCOVERY_CREDENTIAL_REQUIRED")

    def test_identity_mismatch_and_unsafe_paths_refuse(self):
        code, report = self.call("inspect", "--github-id", "9999", configured=False, proposal=False)
        self.assertEqual(code, 4)
        self.assert_blocked(report, "REPOSITORY_IDENTITY_MISMATCH")
        self.directory.symlink_to(self.product)
        code, report = self.call("plan")
        self.assertEqual(code, 4)
        self.assert_blocked(report, "UNSAFE_STALE_OR_UNAVAILABLE")
        self.assertFalse((self.product / "profile.json").exists())

    def test_provider_proposal_adapts_existing_signing_contract(self):
        report, exchange = self.proposed()
        socket, challenge = exchange.call_args.args
        self.assertEqual(socket, self.socket)
        self.assertEqual(challenge["required_kind"], "profile")
        self.assertEqual(challenge["context"]["issue"]["number"], 1)
        self.assertEqual(challenge["context"]["checkout"]["head"], self.head)
        self.assertNotIn("Private fixture ticket context", json.dumps(challenge))
        self.assertEqual(report["plan"]["effects"]["local_bare_remote"], str(self.bare))
        self.assertFalse(self.directory.exists())

    def test_protected_unix_service_returns_profile_without_manual_json(self):
        self.socket = self.auth / "decision.sock"
        (code, report), observed = self.serve_decision(lambda request: self.reply, lambda: self.call("plan"))
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "PROPOSED")
        self.assertEqual(observed[0]["purpose"], "enrollment/profile")
        self.assertEqual(observed[0]["context"]["enrollment_directory"], str(self.directory))
        self.assertFalse(self.directory.exists())

    def test_missing_provider_role_scope_credential_and_ci_block(self):
        cases = (
            ("policy.json", "PROJECT_POLICY_REQUIRED"),
            ("assessment.json", "INDEPENDENT_SCOPE_REQUIRED"),
            ("cas.credential.json", "SCOPED_CREDENTIAL_REQUIRED"),
            ("results.json", "PROJECT_CHECK_PROVIDER_REQUIRED"),
        )
        for filename, expected in cases:
            with self.subTest(filename=filename):
                path = self.auth / filename
                raw = path.read_bytes()
                path.unlink()
                try:
                    with patch("adp.enrollment.exchange", return_value=self.reply):
                        code, report = self.call("plan")
                    self.assertEqual(code, 4)
                    self.assert_blocked(report, expected)
                finally:
                    path.write_bytes(raw)
                    path.chmod(0o600)
        document = json.loads(self.trust.read_text())
        document["principals"] = [item for item in document["principals"] if item["roles"] != ["scope-reviewer"]]
        self.write(self.trust, document)
        with patch("adp.enrollment.exchange", return_value=self.reply):
            code, report = self.call("plan")
        self.assertEqual(code, 4)
        self.assert_blocked(report, "MISSING_TRUST_ROLE")
        self.assertFalse(self.directory.exists())

    def test_fabricated_approval_and_wrong_scope_refuse(self):
        incorrect = copy.deepcopy(self.body)
        incorrect["tasks"][0]["expected_revision"] = "a" * 40
        for reply, expected in (
            ({"approved": True, "status": "READY"}, "OPERATOR_PROPOSAL_REQUIRED"),
            (self.signed("profile", self.body, signer="automation"), "OPERATOR_PROPOSAL_REQUIRED"),
            (self.signed("profile", incorrect), "PROPOSAL_CONFLICT"),
        ):
            with self.subTest(expected=expected):
                with patch("adp.enrollment.exchange", return_value=reply):
                    code, report = self.call("plan")
                self.assertEqual(code, 4)
                self.assert_blocked(report, expected)
        self.assertFalse(self.directory.exists())

    def test_changed_branch_and_stale_issue_refuse_before_writes(self):
        plan, _ = self.proposed()
        run(self.product, "checkout", "-b", "work/wrong")
        with patch("adp.enrollment.exchange", return_value=self.reply):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4)
        self.assert_blocked(report, "PROPOSAL_CONFLICT")
        run(self.product, "checkout", "work/one")
        changed = issue(1, name=self.name, body="new source")
        self.transport.responses[self.prefix + "/issues/1"] = Response(200, changed)
        inventory = self.prefix + "/issues?state=all&sort=created&direction=asc&per_page=100&page=1"
        self.transport.responses[inventory] = Response(200, [changed, *self.rows[1:]])
        with patch("adp.enrollment.exchange", return_value=self.reply):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4)
        self.assertIn(report["blockers"][0]["code"], {"CONFIGURATION_UNKNOWN", "CONFIGURATION_STALE_OR_UNAVAILABLE"})
        self.assertFalse(self.directory.exists())

    def test_signed_policy_changed_between_approval_and_apply_refuses(self):
        from adp.enrollment import apply_plan

        def changed(plan, **kwargs):
            body = json.loads((self.auth / "policy.json").read_text())["payload"]
            self.sign_write("policy", body, issued=self.now - 3)
            return apply_plan(plan, **kwargs)

        plan, _ = self.proposed()
        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.enrollment_cli.apply_plan", side_effect=changed)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertIsNone(read_intent(self.directory))
        self.assertFalse(self.profile.state.exists())
        self.assertEqual(value(self.bare, "for-each-ref"), "")

    def test_stale_signed_check_bootstrap_refuses(self):
        path = self.auth / "results.json"
        body = json.loads(path.read_text())["payload"]
        body["request"]["revision"] = "a" * 40
        self.write(path, self.signed("project-evidence", body))
        with patch("adp.enrollment.exchange", return_value=self.reply):
            code, report = self.call("plan")
        self.assertEqual(code, 4)
        self.assert_blocked(report, "PROJECT_CHECK_PROVIDER_REQUIRED")

    def test_old_and_future_signed_check_observations_refuse(self):
        path = self.auth / "results.json"
        body = json.loads(path.read_text())["payload"]
        self.body["providers"]["validation"]["maximum_age"] = 15
        self.reply = self.signed("profile", copy.deepcopy(self.body))
        for timestamp in (self.now - 30, self.now + 120):
            with self.subTest(timestamp=timestamp):
                body["observed_at"] = timestamp
                self.write(path, self.signed("project-evidence", body, issued=self.now - 60))
                with patch("adp.enrollment.exchange", return_value=self.reply):
                    code, report = self.call("plan")
                self.assertEqual(code, 4, report)
                self.assert_blocked(report, "PROJECT_CHECK_PROVIDER_REQUIRED")
        self.assertFalse(self.directory.exists())

    def test_moved_head_during_apply_stops_before_memory_setup(self):
        from adp.operator_setup import setup

        def moved(profile, **kwargs):
            run(self.product, "commit", "--allow-empty", "-m", "fixture: concurrent source")
            return setup(profile, **kwargs)

        proposed, _ = self.proposed()
        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.enrollment.setup", side_effect=moved)):
            code, report = self.call("apply", "--approve", proposed["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertEqual(read_intent(self.directory)["phase"], "PENDING")
        self.assertFalse(self.profile.state.exists())
        self.assertEqual(value(self.bare, "for-each-ref"), "")

    def test_different_local_files_are_not_adopted(self):
        self.directory.mkdir(mode=0o700)
        unrelated = self.directory / "operator-notes"
        unrelated.write_text("existing")
        with patch("adp.enrollment.exchange") as exchange:
            code, report = self.call("plan")
        self.assertEqual(code, 4, report)
        exchange.assert_not_called()
        self.assertEqual(unrelated.read_text(), "existing")
        self.assertFalse((self.directory / "profile.json").exists())

    def test_retargeted_coordination_remote_requires_new_approval(self):
        from adp.enrollment import apply_plan

        alternate = self.base / "other.git"
        alternate.mkdir()
        run(alternate, "init", "--bare")
        plan, _ = self.proposed()

        def changed(prepared, **kwargs):
            run(self.control, "remote", "set-url", "memory", str(alternate))
            return apply_plan(prepared, **kwargs)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.enrollment_cli.apply_plan", side_effect=changed)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertIsNone(read_intent(self.directory))
        self.assertEqual(value(alternate, "for-each-ref"), "")

    def test_native_writes_keep_pinned_endpoint_after_remote_name_changes(self):
        from adp.memory import git as original_git

        alternate = self.base / "other.git"
        alternate.mkdir()
        run(alternate, "init", "--bare")
        plan, _ = self.proposed()
        sent = []

        def retarget(path, *args, **kwargs):
            if "push" in args and not sent:
                run(self.control, "remote", "set-url", "memory", str(alternate))
                sent.append(args)
            return original_git(path, *args, **kwargs)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.memory.git", side_effect=retarget)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertEqual(len(sent), 1)
        self.assertEqual(value(alternate, "for-each-ref"), "")
        self.assertTrue(value(self.bare, "for-each-ref"))

    def test_final_metadata_recheck_refuses_changed_default_branch(self):
        from adp.operator_setup import setup

        plan, _ = self.proposed()
        original = self.transport.get
        metadata_calls = []

        def get(path):
            response = original(path)
            if path == self.prefix:
                metadata_calls.append(path)
                if len(metadata_calls) == 3:
                    return Response(200, dict(response.body, default_branch="work/one"))
            return response

        def changed(profile, **kwargs):
            with patch.object(self.transport, "get", side_effect=get):
                return setup(profile, **kwargs)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.enrollment.setup", side_effect=changed)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertGreaterEqual(len(metadata_calls), 3)
        self.assertFalse(self.profile.state.exists())
        self.assertEqual(value(self.bare, "for-each-ref"), "")

    def test_branch_switch_at_final_metadata_read_refuses_same_sha(self):
        from adp.operator_setup import setup

        plan, _ = self.proposed()
        original = self.transport.get
        reads = []

        def get(path):
            if path == self.prefix:
                reads.append(path)
                if len(reads) == 3:
                    run(self.product, "checkout", "-b", "work/different")
            return original(path)

        def changed(profile, **kwargs):
            with patch.object(self.transport, "get", side_effect=get):
                return setup(profile, **kwargs)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.enrollment.setup", side_effect=changed)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertEqual(value(self.product, "rev-parse", "HEAD"), self.head)
        self.assertEqual(value(self.product, "symbolic-ref", "HEAD"), "refs/heads/work/different")
        self.assertFalse(self.profile.state.exists())
        self.assertEqual(value(self.bare, "for-each-ref"), "")

    def test_preexisting_checkpoint_between_inspections_stays_unowned_on_retry(self):
        from adp.operator_evidence import OperatorEvidence

        plan, _ = self.proposed()
        prepare = OperatorEvidence.prepare

        def initialize_between(inspector):
            prepare(inspector)
            Memory(inspector.profile.memory_config()).initialize(authorized=True)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch.object(OperatorEvidence, "prepare", initialize_between)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        installed = load_profile(self.directory / "profile.json", self.trust)
        memory = Memory(installed.memory_config())
        previous = memory.inspect()
        code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write", proposal=False)
        self.assertEqual(code, 4, report)
        self.assert_blocked(report, "M1_OWNERSHIP_REQUIRED")
        self.assertEqual(memory.inspect(), previous)
        self.assertIsNone(previous["state"]["owner"])

    def test_bound_common_git_directory_survives_checkout_gitfile_redirect(self):
        from adp.memory import git as original_git

        run(self.control, "commit", "--allow-empty", "-m", "fixture: coordination seed")
        lane = self.base / "linked-control"
        run(self.control, "worktree", "add", "-b", "control-lane", str(lane))
        self.body["memory"]["repo"] = str(lane)
        self.reply = self.signed("profile", copy.deepcopy(self.body))
        alternate = self.base / "alternate-control"
        alternate.mkdir()
        run(alternate, "init")
        plan, _ = self.proposed()
        visited = []

        def changed(path, *args, **kwargs):
            if "hash-object" in args and not visited:
                (lane / ".git").write_text(f"gitdir: {alternate / '.git'}\n")
                visited.append(args)
            return original_git(path, *args, **kwargs)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.memory.git", side_effect=changed)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertEqual(visited[0][:2], ("--git-dir", str(self.control / ".git")))
        self.assertIn("count: 0", value(alternate, "count-objects", "-v").splitlines())
        self.assertEqual(value(self.bare, "for-each-ref"), "")

    def test_bound_git_write_keeps_registered_memory_admin_after_gitfile_redirect(self):
        memory = Memory(self.profile.memory_config(), pinned_local_remote=self.bare)
        memory.initialize(authorized=True)
        alternate = self.base / "alternate-memory"
        run(self.control, "worktree", "add", "-b", "other-memory", str(alternate), memory.branch)
        gitfile = memory.path / ".git"
        previous_gitfile = gitfile.read_bytes()
        alternate_gitfile = (alternate / ".git").read_bytes()
        state = memory.path / "state.json"
        state.write_bytes(state.read_bytes() + b"\n")
        registered = memory._registered

        def redirect_after_registration():
            directory = registered()
            gitfile.write_bytes(alternate_gitfile)
            return directory

        try:
            with patch.object(memory, "_registered", side_effect=redirect_after_registration):
                memory._write_git(memory.path, "add", "--", "state.json")
        finally:
            gitfile.write_bytes(previous_gitfile)
        self.assertEqual(value(alternate, "diff", "--cached", "--name-only"), "")
        self.assertEqual(value(memory.path, "diff", "--cached", "--name-only"), "state.json")

    def test_claim_race_never_reclaims_a_released_generation(self):
        claim = Memory.claim
        plan, _ = self.proposed()

        def released(memory, label, **kwargs):
            if kwargs.get("initial_only"):
                claim(memory, label)
                memory.handoff()
            return claim(memory, label, **kwargs)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch.object(Memory, "claim", released)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        installed = load_profile(self.directory / "profile.json", self.trust)
        state = Memory(installed.memory_config()).inspect()["state"]
        self.assertIsNone(state["owner"])
        self.assertEqual(state["generation"], 1)
        self.assertEqual(state["schema_version"], 1)

    def test_initialization_race_never_claims_a_newly_appeared_checkpoint(self):
        initialize = Memory.initialize
        plan, _ = self.proposed()

        def concurrent(memory, **kwargs):
            initialize(memory, authorized=True)
            return initialize(memory, **kwargs)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch.object(Memory, "initialize", concurrent)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        installed = load_profile(self.directory / "profile.json", self.trust)
        state = Memory(installed.memory_config()).inspect()["state"]
        self.assertIsNone(state["owner"])
        self.assertEqual(state["generation"], 0)
        self.assertEqual(state["revision"], 1)

    def test_interruption_at_profile_publication_leaves_single_link_and_retries(self):
        from adp.storage import sync_directory

        plan, _ = self.proposed()

        def interrupted(directory):
            profile = self.directory / "profile.json"
            if directory == self.directory and profile.exists():
                self.assertEqual(profile.stat().st_nlink, 1)
                raise ADPError("fixture interruption before publication directory sync")
            return sync_directory(directory)

        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch("adp.storage.sync_directory", side_effect=interrupted)):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertEqual(read_intent(self.directory)["phase"], "PENDING")
        self.assertEqual((self.directory / "profile.json").stat().st_nlink, 1)
        code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write", proposal=False)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "ENROLLED")

    def test_exact_approval_real_setup_and_reconnect_preserve_released_generation(self):
        plan, _ = self.proposed()
        with patch("adp.enrollment.exchange", return_value=self.reply):
            code, report = self.call("apply", "--approve", "f" * 64, "--authorize-memory-write")
            self.assertEqual(code, 4)
            self.assert_blocked(report, "APPROVAL_MISMATCH")
            self.assertFalse(self.directory.exists())
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "ENROLLED")
        installed = load_profile(self.directory / "profile.json", self.trust)
        self.assertEqual(read_intent(self.directory)["phase"], "COMPLETE")
        memory = Memory(installed.memory_config())
        state = memory.inspect()["state"]
        self.assertEqual(state["execution"]["schema_version"], 3)
        memory.handoff()
        previous = memory.inspect()
        code, report = self.call("reconnect", proposal=False)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "RECONNECTED")
        code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write", proposal=False)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "ALREADY_ENROLLED")
        self.assertEqual(memory.inspect(), previous)

    def test_reconnect_refuses_a_different_remote_with_the_same_checkpoint(self):
        plan, _ = self.proposed()
        with patch("adp.enrollment.exchange", return_value=self.reply):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 0, report)
        explicit = ("--operator-profile", str(self.directory / "profile.json"), "--operator-trust", str(self.trust))
        code, report = self.call("reconnect", *explicit, configured=False, proposal=False)
        self.assertEqual(code, 0, report)
        copied = self.auth / "restored-profile.json"
        self.write(copied, self.reply)
        renamed = ("--operator-profile", str(copied), "--operator-trust", str(self.trust))
        code, report = self.call("reconnect", *renamed, configured=False, proposal=False)
        self.assertEqual(code, 0, report)
        record = self.profile.state / "enrollment.json"
        retained = json.loads(record.read_bytes())
        record.unlink()
        code, report = self.call("reconnect", *renamed, configured=False, proposal=False)
        self.assertEqual(code, 4, report)
        self.write(record, retained)
        alternate = self.base / "copy.git"
        run(self.base, "clone", "--bare", str(self.bare), str(alternate))
        run(self.control, "remote", "set-url", "memory", str(alternate))
        code, report = self.call("reconnect", proposal=False)
        self.assertEqual(code, 4, report)
        self.assertNotEqual(report["status"], "RECONNECTED")
        code, report = self.call("reconnect", *explicit, configured=False, proposal=False)
        self.assertEqual(code, 4, report)
        self.assertNotEqual(report["status"], "RECONNECTED")
        code, report = self.call("reconnect", *renamed, configured=False, proposal=False)
        self.assertEqual(code, 4, report)
        self.assertNotEqual(report["status"], "RECONNECTED")
        downgraded = {key: value for key, value in retained.items() if key != "guided_directory"}
        self.write(record, dict(downgraded, schema_version=1))
        for command in ("reconnect", "doctor", "preview"):
            with self.subTest(command=command):
                code, report = self.call(command, *renamed, configured=False, proposal=False)
                self.assertEqual(code, 4, report)
                self.assert_blocked(report, "GUIDED_RECORD_REQUIRED")
        code, report = self.call("reconnect", proposal=False)
        self.assertEqual(code, 4, report)
        self.assert_blocked(report, "GUIDED_RECORD_REQUIRED")

    def test_guided_diagnostics_report_missing_check_provider_as_unknown(self):
        plan, _ = self.proposed()
        with patch("adp.enrollment.exchange", return_value=self.reply):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 0, report)
        code, report = self.call("preview", proposal=False)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["result"]["configuration"], "CONFIGURATION_VERIFIED")
        record = self.profile.state / "enrollment.json"
        previous = record.read_bytes()
        (self.auth / "results.json").unlink()
        for command in ("doctor", "preview"):
            with self.subTest(command=command):
                code, report = self.call(command, proposal=False)
                self.assertEqual(code, 4, report)
                self.assertEqual(report["status"], "UNKNOWN")
                self.assertEqual(report["result"]["configuration"], "UNKNOWN")
                self.assert_blocked(report, "PROJECT_CHECK_PROVIDER_REQUIRED")
        self.assertEqual(record.read_bytes(), previous)

    def test_interrupted_enrollment_reuses_exact_intent_and_native_generation(self):
        plan, _ = self.proposed()
        with (patch("adp.enrollment.exchange", return_value=self.reply),
              patch.object(ExecutionJournal, "upgrade_track", side_effect=ADPError("fixture interruption"))):
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write")
        self.assertEqual(code, 4, report)
        self.assertEqual(read_intent(self.directory)["phase"], "PENDING")
        installed = load_profile(self.directory / "profile.json", self.trust)
        memory = Memory(installed.memory_config())
        generation = memory.inspect()["state"]["generation"]
        with patch("adp.enrollment.exchange") as exchange:
            code, report = self.call("apply", "--approve", plan["approval"], "--authorize-memory-write", proposal=False)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["result"]["generation"], generation)
        self.assertEqual(memory.inspect()["state"]["generation"], generation)
        exchange.assert_not_called()
