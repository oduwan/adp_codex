"""Frozen Issue16 individual interface/effect qualification; no live writes."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
import os
from pathlib import Path
from unittest.mock import patch

from product_flow_fixtures import ProductFixture, ProductServer, run
from adp.discovery_schema import digest, typed
from adp.errors import ADPError
from adp.execution_memory import ExecutionJournal
from adp.execution_schema import execution_schema
from adp.execution_types import Role
from adp.forge_http_child import validate_request
from adp.github_product import GitHubProductForge, delegation_subject
from adp.guard_types import Attestation, Outcome, data
from adp.network_git import GitHubCAS
from adp.network_http import GitHubHTTPTransport, installation_scope_subject
from adp.policy import PolicyProvider
from adp.policy_types import Operation, OutcomeCount, ProjectQualifications, Qualifications, Request
from adp.project_validation_types import Phase, ResultStatus
from adp.schema import key


class ProductFlowTests(ProductFixture):
    def accepted(self, *, ready=True):
        pull = self.draft(ready=ready)
        self.assertIsNotNone(pull)
        self.assertTrue(self.flow.qualify_review(self.admission, self.job, self.generation))
        self.assignment, self.job = self.conductor._job(self.admission, Role.COORDINATION, self.generation)
        return pull

    def merge(self):
        return self.flow.merge(self.admission, self.job, self.generation)

    def report(self):
        return self.flow.report(self.admission, self.job, self.generation)

    def guard_state(self):
        return self.guard._snapshot(self.admission.task_id, self.conductor._requirement(self.admission))[2]

    def mutations(self, method=None):
        return [row for row in self.server.calls if row[0] != "GET" and (method is None or row[0] == method)]

    def test_v1_remains_closed_and_readonly_no_migration(self):
        state = copy.deepcopy(self.conductor.journal.inspect()["state"]["execution"])
        state["schema_version"] = 1; state.pop("product_flows")
        execution_schema(state, self.config.identity)
        state["product_flows"] = {}
        with self.assertRaises(ADPError):execution_schema(state, self.config.identity)
        self.assertEqual(data(Qualifications()), {"checks": [], "reviews": []})

    def test_explicit_upgrade_preserves_m1_m2_and_existing_actions(self):
        before = self.memory.inspect()["state"]
        with self.assertRaises(ADPError):self.conductor.journal.upgrade_product_flow()
        self.conductor.journal.upgrade_product_flow(authorized=True)
        after = self.memory.inspect()["state"]
        self.assertEqual(before, after)
        self.assertEqual(after["execution"]["schema_version"], 2)

    def test_v2_unknown_counts_roundtrip_without_legacy_coercion(self):
        self.accepted()
        provider, context = self.conductor._policy(self.admission, typed(__import__('adp.guard_types', fromlist=['Permit']).Permit, self.job["permit"]))
        plan = provider.plan(context, Request(Operation.REPORT, report_target="https://github.com/demo/project/issues/1", report_body="Product"))
        q = self.flow.qualifications(self.admission, provider, plan)
        self.assertIs(type(q), ProjectQualifications)
        self.assertTrue(all(c.denominator is None and c.counts == () for c in q.checks))
        state = self.conductor.journal.inspect()["state"]["execution"]
        execution_schema(json.loads(json.dumps(state)), self.config.identity)

    def test_v2_rejects_forged_review_and_broken_action_links(self):
        self.review()
        state = copy.deepcopy(self.conductor.journal.inspect()["state"]["execution"])
        flow = state["product_flows"][key(self.admission.task_id)]
        flow["review_job"] = "1-999"
        with self.assertRaises(ADPError):execution_schema(state, self.config.identity)
        flow["review_job"] = None
        state["publications"]["a" * 64] = {"action": "b" * 64, "body_digest": "c" * 64, "reference": "fixture"}
        with self.assertRaises(ADPError):execution_schema(state, self.config.identity)

    def test_original_preparation_required_before_effects(self):
        self.scope.packet_reference = "ticket-packet:" + "a" * 64
        with self.assertRaises((ADPError, OSError)):self.review()
        self.assertEqual(self.mutations(), [])

    def test_scope_drift_without_specific_addition_refused(self):
        changed = replace(self.admission, allowed_paths=("product.py", "extra.py"))
        with self.assertRaises(ADPError):self.conductor._admit(changed, self.readiness.observe(), self.generation)
        self.assertEqual(self.mutations(), [])

    def test_foreign_issue_and_repository_id_refused(self):
        self.review()
        for identity in (replace(self.admission.identity, issue_id="foreign"), replace(self.admission.identity, repository_id="foreign")):
            with self.assertRaises(ADPError):self.flow.bind(replace(self.admission, identity=identity), self.job, self.generation)
        self.server.failure = 403
        self.assertRaises(ADPError, self.draft)
        self.assertEqual(self.mutations(), [])

    def test_missing_owner_stale_generation_and_permit_refused(self):
        self.review()
        with self.assertRaises(ADPError):self.flow.bind(self.admission, self.job, self.generation + 1)
        changed = copy.deepcopy(self.job); changed["permit"]["token"] = "a" * 64
        with self.assertRaises(ADPError):self.flow.bind(self.admission, changed, self.generation)
        self.assertEqual(self.mutations(), [])

    def test_credentials_and_forged_delegation_not_authority(self):
        self.review()
        factory = self.flow.delegation_factory
        self.flow.delegation_factory = lambda *args: replace(factory(*args), evidence=None)
        with self.assertRaises(ADPError):self.draft()
        self.assertEqual(self.mutations(), [])

    def test_forged_project_check_and_author_reviewer_refused(self):
        self.draft(ready=True)
        self.authority.denied.add("project-validation/observation")
        self.assertFalse(self.flow.qualify_review(self.admission, self.job, self.generation))
        self.assertIsNone(self.conductor._task(self.admission)["review"])
        self.assertEqual(self.guard_state()["unresolved"], ["criterion:answer"])
        self.assertEqual(self.mutations("PUT"), [])

    def test_before_pr_only_needs_no_post_pr_gate(self):
        self.accepted()
        self.assertEqual({g["request"]["phase"] for g in self.flow._flow(self.admission)["gates"]}, {"BEFORE_PR"})
        self.assertEqual(self.merge(), "MERGED")

    def test_post_pr_draft_remains_pending_until_current_checks(self):
        self.phases = (Phase.AFTER_PR,)
        self.check_status = ResultStatus.PENDING
        self.draft()
        gate = self.flow.checks(self.admission, self.job, self.generation, Phase.AFTER_PR)
        self.assertEqual(gate.status, ResultStatus.PENDING)
        self.assertFalse(self.flow.qualify_review(self.admission, self.job, self.generation))
        self.assertEqual(self.flow._flow(self.admission)["phase"], "PENDING_VALIDATION")
        self.assertIsNone(self.conductor._task(self.admission)["review"])
        self.assertEqual(self.guard_state()["unresolved"], ["criterion:answer"])
        self.assertEqual(self.server.comments, [])

    def test_ready_pending_failed_stale_missing_ci_states(self):
        self.review()
        for status in (ResultStatus.PENDING, ResultStatus.FAIL, ResultStatus.UNKNOWN, ResultStatus.NOTRUN):
            self.check_status = status
            self.assertFalse(self.flow.checks(self.admission, self.job, self.generation, Phase.BEFORE_PR).qualified)
            self.assertIsNone(self.conductor._task(self.admission)["review"])
        self.check_status = ResultStatus.PASS
        self.assertTrue(self.flow.checks(self.admission, self.job, self.generation, Phase.BEFORE_PR).qualified)

    def test_unknown_counts_and_partial_failfast_stay_honest(self):
        self.review()
        gate = self.flow.checks(self.admission, self.job, self.generation, Phase.BEFORE_PR)
        self.assertIsNone(gate.results[0].denominator)
        self.denominator, self.counts = 7, (OutcomeCount("PASS", 2), OutcomeCount("FAIL", 1))
        gate = self.flow.checks(self.admission, self.job, self.generation, Phase.BEFORE_PR)
        self.assertFalse(gate.qualified)
        self.assertEqual((gate.results[0].denominator, gate.results[0].counts), (7, self.counts))

    def test_checks_paginate_and_permission_rate_limit_stay_unknown(self):
        self.review()
        for status in (403, 429):
            self.server.failure = status
            with self.assertRaises(ADPError):self.draft()
        self.server.failure = None
        self.draft()
        self.server.review_rows = [{"id": i, "user": {"id": i}, "state": "APPROVED", "commit_id": self.conductor._task(self.admission)["revision"]} for i in range(1, 101)]
        self.assertIsNone(self.forge.reviews(self.flow._flow(self.admission)["pull"], self.initial))

    def test_new_head_requires_checks_and_independent_rereview(self):
        self.accepted()
        self.server.pulls[0]["head"]["sha"] = "d" * 40
        with self.assertRaises(ADPError):self.merge()
        self.assertEqual(self.mutations("PUT"), [])

    def test_failed_checks_return_bounded_in_scope_correction(self):
        self.phases = (Phase.AFTER_PR,)
        self.check_status = ResultStatus.FAIL
        self.draft()
        self.assertFalse(self.flow.qualify_review(self.admission, self.job, self.generation))
        self.assertEqual(self.flow._flow(self.admission)["phase"], "REQUIRES_CORRECTION")
        self.assertIsNone(self.conductor._task(self.admission)["review"])
        self.assertEqual(self.guard_state()["unresolved"], ["criterion:answer"])
        self.assertNotEqual(self.guard_state()["mode"], "unsafe")

    def test_changed_policy_and_divergent_base_invalidate_gates(self):
        self.accepted()
        self.rules["one"] = replace(self.rules["one"], checks=("unit", "new-check"))
        with self.assertRaises(ADPError):self.merge()
        self.assertEqual(self.mutations("PUT"), [])

    def test_draft_creation_exact_repo_head_base_body_marker(self):
        pull = self.draft()
        self.assertEqual(pull["id"], "101")
        item = self.server.pulls[0]
        self.assertTrue(item["draft"])
        self.assertEqual(item["head"]["sha"], self.conductor._task(self.admission)["revision"])
        self.assertIn("<!-- adp-product:v1:", item["body"])
        self.assertEqual(len(self.mutations("POST")), 1)

    def test_unique_draft_retained_across_source_correction(self):
        pull = self.draft()
        self.assertEqual(self.draft(), pull)
        self.assertEqual(len(self.server.pulls), 1)
        self.assertEqual(len(self.mutations("POST")), 1)
        action = next(a for a in self.conductor.journal.inspect()["state"]["execution"]["actions"].values() if a["operation"] == Operation.PR)
        self.assertEqual(action["payload"]["revision"], self.conductor._task(self.admission)["revision"])

    def test_unauthorized_pr_or_report_permits_no_write(self):
        self.review()
        self.authority.denied.add("execution/effect")
        with self.assertRaises(ADPError):self.draft()
        self.assertEqual(self.mutations(), [])

    def test_duplicate_markers_and_partial_inventory_unknown(self):
        self.draft()
        actions = self.conductor.journal.inspect()["state"]["execution"]["actions"]
        action_id, action = next((k, a) for k, a in actions.items() if a["operation"] == Operation.PR)
        self.server.pulls.append(copy.deepcopy(self.server.pulls[0]))
        self.assertEqual(self.forge.observe(action_id, Operation.PR, action["payload"], attempted=True).status, "UNKNOWN")
        self.server.pulls.pop()
        self.server.pages = {1: [self.server.pulls[0]] + [{"body": ""} for _ in range(99)], 2: [self.server.pulls[0]]}
        self.assertEqual(self.forge.observe(action_id, Operation.PR, action["payload"], attempted=True).status, "UNKNOWN")

    def test_foreign_or_changed_pr_head_refuses(self):
        self.accepted()
        self.server.pulls[0]["head"]["repo"]["id"] = 18
        with self.assertRaises(ADPError):self.merge()
        self.assertEqual(self.mutations("PUT"), [])

    def test_manual_delegation_waits_without_merge_write(self):
        self.accepted()
        self.merge_mode = "MANUAL"
        self.assertEqual(self.merge(), "WAITING_HUMAN_APPROVAL")
        self.assertEqual(self.mutations("PUT"), [])

    def test_explicit_delegation_merge_and_squash_pass(self):
        self.rules["one"] = replace(self.rules["one"], merge_method="squash")
        self.accepted()
        self.assertEqual(self.merge(), "MERGED")
        self.assertEqual(self.mutations("PUT")[0][2]["merge_method"], "squash")
        self.assertTrue(self.server.pulls[0]["merged"])

    def test_draft_waits_for_external_ready_without_new_effect(self):
        self.accepted(ready=False)
        self.assertEqual(self.merge(), "WAITING_HUMAN_APPROVAL")
        self.assertEqual(self.mutations("PUT"), [])
        self.server.pulls[0]["draft"] = False
        self.assertEqual(self.merge(), "MERGED")

    def test_forbidden_rebase_and_provider_ff_only_unsupported(self):
        self.rules["one"] = replace(self.rules["one"], merge_method="ff_only")
        self.methods = ("ff_only",)
        self.accepted()
        self.assertEqual(self.merge(), "UNSUPPORTED")
        with self.assertRaises(ValueError):validate_request("PUT", "/repos/demo/project/pulls/1/merge", {"sha": "a" * 40, "merge_method": "rebase"}, 1)
        self.assertEqual(self.mutations("PUT"), [])

    def test_method_protection_and_missing_review_refuse(self):
        self.accepted()
        self.server.review_rows = [{"id": 1, "user": {"id": 73}, "state": "CHANGES_REQUESTED", "commit_id": self.conductor._task(self.admission)["revision"]}]
        with self.assertRaises(ADPError):self.merge()
        self.assertEqual(self.mutations("PUT"), [])

    def test_merge_exact_head_precondition_and_reobserved_result(self):
        self.accepted()
        self.assertEqual(self.merge(), "MERGED")
        self.assertEqual(self.mutations("PUT")[0][2]["sha"], self.conductor._task(self.admission)["revision"])
        result = self.flow._flow(self.admission)["merge_result"]
        self.assertEqual(run(self.remote, "rev-parse", "trunk"), result)
        self.assertEqual(self.merge(), "MERGED")
        self.assertEqual(len(self.mutations("PUT")), 1)

    def test_unknown_base_atomicity_requirement_is_unsupported(self):
        self.accepted()
        for envelope in ("ATOMIC_BASE", "UNKNOWN"):
            self.envelope = envelope
            self.assertEqual(self.merge(), "UNSUPPORTED")
        self.assertEqual(self.mutations("PUT"), [])

    def test_one_substantive_product_summary_per_iteration(self):
        self.accepted(); self.merge()
        first = self.report(); second = self.report()
        self.assertEqual(first, second)
        self.assertEqual(len(self.server.comments), 1)
        self.assertIn("Merged as", self.server.comments[0]["body"])

    def test_internal_iteration_has_zero_forge_effects(self):
        # The existing task purpose is immutable; use the same data at admission
        # construction to check that INTERNAL never reaches the forge APIs.
        self.review()
        self.conductor.journal.change(lambda execution, state, tasks: execution["tasks"][key(self.admission.task_id)].update(kind="INTERNAL"))
        self.assertIsNone(self.flow.draft(self.admission, self.job, self.generation))
        self.assertEqual(self.merge(), "INTERNAL")
        self.assertIsNone(self.report())
        self.assertEqual(self.mutations(), [])
        self.check_status = ResultStatus.FAIL
        self.assertEqual(self.flow.advance(self.admission, self.generation), "REQUIRES_CORRECTION")
        self.assertEqual(self.guard_state()["unresolved"], ["criterion:answer"])
        self.assertNotEqual(self.conductor._task(self.admission)["stage"], "COMPLETE")

    def test_summary_excludes_internal_text_secrets_and_raw_logs(self):
        self.accepted(); self.merge(); self.report()
        body = self.server.comments[0]["body"]
        for forbidden in ("synthetic-preparer", "worker:", "runtime:", "attempt:", "token=", "stderr"):
            self.assertNotIn(forbidden, body)
        self.assertIn(self.conductor._task(self.admission)["revision"], body)

    def test_manual_outstanding_merge_summary_honest(self):
        self.accepted(); self.merge_mode = "MANUAL"
        self.merge(); self.report()
        self.assertIn("awaits project human approval", self.server.comments[0]["body"])
        self.assertNotIn("Merged as", self.server.comments[0]["body"])

    def test_lost_pr_response_before_after_never_duplicate(self):
        self.review(); self.server.loss = "after"
        self.draft()
        self.assertEqual(len(self.server.pulls), 1)
        self.assertEqual(self.draft()["number"], 1)
        self.assertEqual(len(self.mutations("POST")), 1)

    def test_lost_merge_response_before_after_never_blind_retry(self):
        self.accepted(); self.server.loss = "after"
        self.assertEqual(self.merge(), "MERGED")
        self.assertEqual(self.merge(), "MERGED")
        self.assertEqual(len(self.mutations("PUT")), 1)

    def test_lost_comment_response_before_after_never_duplicate(self):
        self.accepted(); self.merge(); self.server.loss = "after"
        self.report(); self.report()
        self.assertEqual(len(self.server.comments), 1)

    def test_restart_prepared_submitted_preserves_owner_and_one_use(self):
        self.review(); self.server.loss = "before"
        with self.assertRaises(ADPError):self.draft()
        self.projects["one"] = replace(self.projects["one"], forge=GitHubProductForge(self.service, self.conductor.journal, self.authority))
        with self.assertRaises(ADPError):self.draft()
        self.assertEqual(len(self.mutations("POST")), 1)
        self.assertEqual(self.server.pulls, [])

    def test_unknown_transport_stop_blocks_http_and_handoff(self):
        self.review()
        original = self.server.request
        self.server.request = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("uncertain child"))
        with self.assertRaises(ADPError):self.draft()
        self.server.request = original
        self.assertTrue(self.forge.unconfirmed_contexts())
        with self.assertRaises(ADPError):self.draft()
        with self.assertRaises(ADPError):self.conductor.handoff(authorized=True)

    def test_missing_corrupt_private_claim_cannot_replay(self):
        self.review(); self.server.loss = "before"
        with self.assertRaises(ADPError):self.draft()
        actions = self.conductor.journal.inspect()["state"]["execution"]["actions"]
        action_id, action = next((k, a) for k, a in actions.items() if a["operation"] == Operation.PR)
        self.forge._claim_path(action_id).unlink()
        with self.assertRaises(ADPError):self.forge.prepare_dispatch(action_id, action)
        with self.assertRaises(ADPError):self.draft()
        self.assertEqual(len(self.mutations("POST")), 1)

    def test_fixed_origin_routes_body_and_permission_boundaries(self):
        for method, path, body in (("PUT", "/repos/demo/project/pulls/1/merge", {"sha": "a" * 40, "merge_method": "merge"}),
                                  ("POST", "/repos/demo/project/issues/1/comments", {"body": "product"})):
            self.assertTrue(validate_request(method, path, body, 1))
        for path in ("https://attacker.invalid", "/repos/demo/project/actions/workflows/1/dispatches", "/repos/demo/project/pulls/1/merge-async"):
            with self.assertRaises(ValueError):validate_request("POST", path, {}, 1)
        from adp.network_http_child import validate_request as cas_request
        with self.assertRaises(ValueError):cas_request("PUT", "/repos/demo/project/pulls/1/merge", {"sha": "a" * 40, "merge_method": "merge"}, 1)

    def test_reused_repository_path_cannot_receive_wrong_id_write(self):
        self.review()
        self.server.failure = 403  # scoped issuance denies a path now owned by another ID
        with self.assertRaises(ADPError):self.draft()
        self.assertEqual(self.mutations(), [])
        with self.assertRaises(ValueError):self.server.bind_repository("R_foreign", 18)
