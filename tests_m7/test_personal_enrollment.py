"""Focused personal enrollment tests; fixtures are not genuine Codex evidence."""
from dataclasses import replace
import json
from unittest.mock import patch

from adp.discovery_github import Response
from adp.errors import ADPError
from adp.git import value
from adp.personal_enrollment import apply_personal, selection
from adp.memory import Memory
from adp.personal_storage import approval, load_state
from personal_fixtures import PersonalFixture
from test_config import run, snapshot


class PersonalEnrollmentTests(PersonalFixture):
    def test_expiry_during_remote_observation_prevents_first_write(self):
        plan, original, docs = self.plan()
        before = snapshot(self.base)
        def advance(*args, **kwargs):
            result = selection(*args, **kwargs)
            self.now = plan["window"]["expires_at"]
            return result
        with patch("adp.personal_enrollment.selection", side_effect=advance), self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        self.assertEqual(snapshot(self.base), before)

    def test_interrupted_pristine_claim_recovers_without_reinitializing(self):
        plan, original, docs = self.plan()
        with patch.object(Memory, "claim", side_effect=OSError("Synthetic interruption before first claim")), self.assertRaises(OSError):
            apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        partial = load_state(self.directory)
        checkpoint = partial.memory().inspect()["local_head"]
        self.assertEqual(partial.intent["phase"], "PREPARED")
        with patch.object(Memory, "initialize", side_effect=AssertionError("Do not initialize again")):
            resumed = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                                     transport=self.transport, clock=lambda: self.now)
        self.assertTrue(resumed.memory().inspect()["local_owner"])
        self.assertNotEqual(checkpoint, resumed.memory().inspect()["local_head"])
        self.assertEqual(resumed.memory().inspect()["state"]["generation"], 1)

    def test_reapplying_enrollment_after_branch_switch_refuses_without_reset(self):
        plan, original, docs = self.plan()
        personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                                  transport=self.transport, clock=lambda: self.now)
        before = personal.memory().inspect()
        run(self.a, "checkout", "-b", "another")
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        self.assertEqual(personal.memory().inspect(), before)

    def test_managed_installation_is_not_a_state_or_feature_destination(self):
        installed = self.base / "installed-engine"
        with patch("adp.personal_enrollment.installer_root", return_value=installed):
            with self.assertRaises(ADPError):
                self.plan(choices=replace(self.choices, directory=installed / "personal"))
            with self.assertRaises(ADPError):
                self.plan(choices=replace(self.choices, workspace=installed / "feature"))
        self.assertFalse(installed.exists())

    def test_unsupported_m3_operands_refuse_during_read_only_planning(self):
        before = snapshot(self.base)
        for choices in (replace(self.choices, commit_body="literal {task}"),
                        replace(self.choices, branch="work/" + "x" * 97)):
            with self.subTest(choices=choices), self.assertRaises(ADPError):
                self.plan(choices=choices)
        self.assertEqual(snapshot(self.base), before)

    def test_plan_and_decline_are_read_only_without_external_providers(self):
        before = snapshot(self.base)
        plan, original, docs = self.plan()
        self.assertEqual(snapshot(self.base), before)
        self.assertFalse(self.directory.exists())
        self.assertEqual(plan["mode"], "PERSONAL")
        self.assertEqual(plan["checks"], [])
        self.assertEqual(docs, [])
        self.assertEqual(original["number"], 1)
        self.assertEqual(plan["window"]["maximum_rounds"], 1)
        self.assertEqual(plan["window"]["maximum_parallel"], 1)
        self.assertEqual(plan["merge_mode"], "MANUAL")
        self.assertNotIn("PUSH", plan["operations"])
        self.assertNotIn("PRIVATE_ACCOUNT_PROFILE", str(plan))
        self.assertEqual(plan["feature"]["preparation"], "AFTER_INDEPENDENT_POLICY_REVIEW")
        self.assertEqual(value(self.a, "symbolic-ref", "HEAD"), "refs/heads/trunk")

    def test_exact_apply_creates_actual_m1_m2_locally_and_reuses_owner(self):
        plan, original, docs = self.plan()
        token = approval(plan)
        personal = apply_personal(plan, original, docs, approved=token, authorized=True,
                                  transport=self.transport, clock=lambda: self.now)
        memory = personal.memory()
        observed = memory.inspect()
        self.assertEqual(observed["health"], "SYNCED")
        self.assertTrue(observed["local_owner"])
        self.assertEqual(observed["state"]["schema_version"], 3)
        self.assertEqual(observed["state"]["execution"]["schema_version"], 1)
        again = apply_personal(plan, original, docs, approved=token, authorized=True,
                               transport=self.transport, clock=lambda: self.now)
        self.assertEqual(again.memory().inspect(), observed)
        self.assertEqual(load_state(self.directory).intent["phase"], "ENROLLED")
        self.assertEqual(value(self.a, "symbolic-ref", "HEAD"), "refs/heads/trunk")
        self.assertFalse(personal.feature.exists())
        self.assertFalse(any("trust" in p.name or "credential" in p.name for p in self.directory.iterdir()))

    def test_missing_or_changed_approval_never_creates_state(self):
        plan, original, docs = self.plan()
        before = snapshot(self.base)
        for authorized, token in ((False, approval(plan)), (True, "p1.0.1." + "0" * 32 + "." + "0" * 64)):
            with self.subTest(authorized=authorized), self.assertRaises(ADPError):
                apply_personal(plan, original, docs, approved=token, authorized=authorized,
                               transport=self.transport, clock=lambda: self.now)
        self.assertEqual(snapshot(self.base), before)

    def test_changed_source_and_expired_window_fail_closed(self):
        plan, original, docs = self.plan()
        token = approval(plan)
        run(self.a, "commit", "--allow-empty", "-m", "Fixture source advanced")
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=token, authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        self.assertEqual(snapshot(self.base), before)
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=token, authorized=True,
                           transport=self.transport, clock=lambda: plan["window"]["expires_at"])
        self.assertFalse(self.directory.exists())

    def test_unknown_rules_are_not_absent_or_merge_authority(self):
        self.transport.api.responses[self.prefix + "/rules/branches/trunk"] = Response(403, None)
        plan, _, _ = self.plan()
        self.assertEqual(plan["check_requirements"], "UNKNOWN")
        self.assertTrue(any(row["rules"] == "UNKNOWN" for row in plan["branch_rules"]))
        self.assertEqual(plan["publication"], "NOT_DELEGATED")
        self.assertNotIn("MERGE", plan["operations"])
        second, _, _ = self.plan(choices=replace(self.choices, issue=2))
        self.assertEqual(second["admission"], "BLOCKED_DEPENDENCY")

    def test_foreign_account_unsafe_paths_and_wrong_repository_refuse(self):
        before = snapshot(self.base)
        self.transport.account = Response(200, {"id": 92})
        with self.assertRaises(ADPError):
            self.plan()
        self.transport.account = Response(200, {"id": 91})
        for paths in ((".git/config",), ("../escape",), ("/outside",)):
            with self.subTest(paths=paths), self.assertRaises(ADPError):
                self.plan(choices=replace(self.choices, paths=paths))
        with self.assertRaises(ADPError):
            self.plan(choices=replace(self.choices, directory=self.a / "private"))
        metadata = dict(self.transport.api.responses[self.prefix].body)
        self.transport.api.responses[self.prefix] = Response(200, {**metadata, "id": 18})
        with self.assertRaises(ADPError):
            self.plan()
        self.assertEqual(snapshot(self.base), before)

    def test_original_change_and_foreign_private_files_refuse_before_writes(self):
        plan, original, docs = self.plan()
        route = self.prefix + "/issues/1"
        previous = self.transport.api.responses[route]
        changed = {**previous.body, "body": "Changed original specification"}
        self.transport.api.responses[route] = Response(200, changed)
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        self.assertEqual(snapshot(self.base), before)
        self.transport.api.responses[route] = previous
        self.directory.mkdir(mode=0o700)
        (self.directory / "unrelated").write_text("Do not adopt this directory")
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            self.plan()
        self.assertEqual(snapshot(self.base), before)

    def test_symlink_state_and_reenrollment_do_not_reset_memory(self):
        alias = self.base / "state-link"
        alias.symlink_to(self.directory)
        with self.assertRaises(ADPError):
            self.plan(choices=replace(self.choices, directory=alias))
        plan, original, docs = self.plan()
        personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                                  transport=self.transport, clock=lambda: self.now)
        memory = personal.memory()
        before = memory.inspect()
        with self.assertRaises(ADPError):
            self.plan(choices=replace(self.choices, directory=self.base / "another-state"))
        self.assertEqual(memory.inspect(), before)

    def test_required_checks_keep_real_names_when_evidence_is_unavailable(self):
        self.transport.api.responses[self.prefix + "/rules/branches/trunk"] = Response(200, [{
            "type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "unit"}]}}])
        plan, original, docs = self.plan()
        self.assertEqual(plan["check_requirements"], "PRESENT")
        self.assertEqual(plan["required_check_names"], ["unit"])
        self.assertEqual(plan["unresolved_check_names"], ["unit"])
        self.assertEqual(plan["check_identity_status"], "UNKNOWN")
        self.assertEqual(plan["checks"], [])
        personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                                  transport=self.transport, clock=lambda: self.now)
        self.assertTrue(personal.memory().inspect()["local_owner"])
        self.assertFalse(personal.feature.exists())
        self.assertNotIn("PASS", str(personal.intent))

    def test_altered_role_limits_and_lost_marker_are_not_new_authority(self):
        plan, original, docs = self.plan()
        personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                                  transport=self.transport, clock=lambda: self.now)
        path = self.directory / "personal.json"
        retained = path.read_text()
        changed = json.loads(retained)
        changed["plan"]["window"]["developers"] = 3
        changed["approval"] = approval(changed["plan"])
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ADPError, "limits"):
            load_state(self.directory)
        path.write_text(retained)
        marker = self.base / "a/.git/adp-personal"
        next(marker.glob("*.json")).unlink()
        with self.assertRaisesRegex(ADPError, "marker"):
            load_state(self.directory)
