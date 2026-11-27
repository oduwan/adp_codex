"""Selected native 1→2→3 publication stages, not a Worker/track campaign.

Cold review/admission and predecessor acceptance are explicit synthetic seams.
Actual targeted M4, Memory, M2, M3, Git objects, native CAS, and settlement run.
"""
from dataclasses import replace
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from adp.discovery_github import Response
from adp.errors import ADPError
from adp.network_git import GitHubTarget
from adp.personal_publication import PersonalPublication
from adp.personal_track import PersonalTrack
from adp.guard_types import data
from personal_publication_fixtures import PersonalObjectTransport
from test_config import run
import test_product_work as product_work


class PublicationWorkTests(unittest.TestCase):
    def test_identical_fresh_scope_reuses_semantics_and_changed_scope_or_edge_refuses(self):
        from adp.discovery_schema import digest
        from adp.runtime_limits import DEFAULTS
        import personal_fixtures
        f = personal_fixtures.PersonalFixture(methodName="runTest"); f.setUp()
        self.addCleanup(f.doCleanups)
        observation, owner = f.observe()
        selected = next(i for i in observation.snapshot.issues if i.number == 1)
        pub = PersonalPublication.__new__(PersonalPublication)
        pub.c = SimpleNamespace(track=None, original_matches=Mock(side_effect=lambda i: data(i) == data(selected)))
        pub.personal = SimpleNamespace(repository_id=f.rid, plan={"issue": 1, "issue_id": selected.identity.issue_id,
            "repository": observation.repository, "owner": owner, "native_prerequisites": [],
            "branch_rules": observation.facts["branch_rules"]})
        pub.target = SimpleNamespace(api=f.prefix)
        pub.read, pub.clock, pub.service = f.transport, lambda: f.now, SimpleNamespace(limits=DEFAULTS)
        qualified = {}
        first = pub.original(_capture=qualified)
        pub.c.original_matches.assert_called_once()
        future = f.transport.api.responses[f.prefix + "/issues/3"].body
        future["body"] = "Unadmitted future change"
        self.assertEqual(pub.original(_qualified=qualified, _capture={}), first)
        pub.c.original_matches.assert_called_once()  # Actual GETs, one semantic interpretation.
        row = f.transport.api.responses[f.prefix + "/issues/1"].body
        original = row["body"]
        row["body"] = "Unapproved selected change"
        with self.assertRaises(ADPError):pub.original(_qualified=qualified, _capture={})
        row["body"] = original
        route = f.prefix + "/issues/1/dependencies/blocked_by?per_page=100&page=1"
        before = f.transport.api.responses[route]
        f.transport.api.responses[route] = Response(200, [f.transport.api.responses[f.prefix + "/issues/3"].body])
        with self.assertRaises(ADPError):pub.original(_qualified=qualified, _capture={})
        f.transport.api.responses[route] = before
        self.assertEqual(pub.original(_capture={}), first)  # A new entry interprets again.
        self.assertEqual(pub.c.original_matches.call_count, 2)

    def test_scoped_publication_refs_do_not_reconstruct_global_inventory(self):
        from adp.network_git import GitHubPolicyAdapter
        from test_personal_rules import Native, HEAD
        f = Native()
        f.service.refs = Mock(side_effect=AssertionError("No unrelated ref inventory"))
        with patch("adp.network_git._endpoint"):
            adapter = GitHubPolicyAdapter(SimpleNamespace(), f.service, push_ref=f.target.ref)
            self.assertEqual([(r.name, r.revision) for r in adapter._remote_refs(None)], [(f.target.ref, HEAD)])
            f.current = None
            self.assertEqual(adapter._remote_refs(None), ())
        self.assertEqual(f.calls, [("POST", "/graphql"), ("POST", "/graphql")])
        with self.assertRaises(ADPError):GitHubPolicyAdapter(SimpleNamespace(), f.service, push_ref="refs/heads/foreign")
        f.service.personal = False
        with self.assertRaises(ADPError):GitHubPolicyAdapter(SimpleNamespace(), f.service, push_ref=f.target.ref)

    def test_same_boundary_private_identity_reuse_preserves_all_semantic_checks(self):
        from copy import deepcopy
        from adp.personal_github import owned_repository
        from adp.personal_rules import private_repository
        from test_personal_rules import Native
        f, repository = Native(), {}
        owner = owned_repository(f, "owned/project", "17", _repository=repository)
        self.assertEqual(len(f.calls), 2)
        result = private_repository(f, f.repository, f.owner, _identity=(repository, owner))
        self.assertEqual(len(f.calls), 2)
        self.assertEqual(result["owner"], f.owner)
        for field, changed in (("private", False), ("node_id", "other"), ("default_branch", "other"),
                ("permissions", {"pull": True, "push": False, "admin": True}), ("owner", {"type": "User", "id": 92})):
            row = {**deepcopy(repository), field: changed}
            with self.subTest(field=field), self.assertRaises(ADPError):
                private_repository(f, f.repository, f.owner, _identity=(row, owner))
        self.assertEqual(len(f.calls), 2)

    def test_same_stage_policy_reuse_still_observes_late_memory_authority(self):
        import test_runtime_work
        fixture = test_runtime_work.RuntimeWorkTests(methodName="runTest"); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        pub, f, _ = fixture.policy_projection()
        prove = pub.proof.side_effect
        def changed(purpose, subject, *args):
            result = prove(purpose, subject, *args)
            if purpose == "policy/operation":f.safety.value = replace(f.safety.value, owns_memory=False)
            return result
        pub.proof.side_effect = changed
        with patch("adp.personal_publication.GitHubPolicyAdapter", return_value=f.adapter), \
                patch("adp.personal_publication.ReservedSafety", return_value=f.safety), self.assertRaises(ADPError):
            pub.provider(object())
        self.assertGreaterEqual(f.safety.calls, 2)

    def stage(self, number, *, plan_disabled=False):
        timezone = patch.dict("os.environ", {"TZ": "UTC"}); timezone.start()
        self.addCleanup(timezone.stop)
        f = product_work.ProductWorkTests(methodName="runTest"); f.setUp()
        self.addCleanup(f.doCleanups)
        f.choices = replace(f.choices, issue=number, branch="work/issue-" + str(number))
        if plan_disabled:
            from test_personal_rules import denied
            f.transport.api.responses[f.prefix].body["private"] = True
            f.transport.api.responses[f.prefix + "/branches/trunk"].body["commit"] = {"sha": run(f.a, "rev-parse", "HEAD")}
            f.transport.api.responses[f.prefix + "/rules/branches/trunk"] = denied()
        p = f.seeded(publication=True)
        def accepted(identity, **kw):
            if p.c.track.originals[identity].issue.number >= number:
                return None
            if kw.get("_capture") is not None:
                kw["_capture"][identity] = ("synthetic historical admission seam",)
            return {"qualification": "SYNTHETIC_ACCEPTANCE_SEAM"}
        p.c.track.accepted = Mock(side_effect=accepted)
        row = f.c.record(); row.update(original_review="seeded-original", code_review="seeded-code")
        f.c.save(row)
        f.c.worker = Mock(return_value={"observation": {"receipt": "synthetic:stopped-independent-code"}})
        f.c.workers.records = Mock(return_value=[{"synthetic_stopped_scope_and_code": "NOT_GENUINE_RUNTIME"}])
        root = f.base / "publication-store.git"; root.mkdir()
        initial = f.personal.plan["checkout"]["head"]
        run(root, "init", "--bare", "--initial-branch=trunk")
        run(root, "fetch", "--no-tags", "--no-write-fetch-head", "--no-auto-maintenance", str(f.a), initial)
        run(root, "update-ref", "refs/heads/trunk", initial)
        target = GitHubTarget(f.rid, "R_personal", 17, *f.name.split("/"), f.personal.plan["feature"]["branch"])
        http = PersonalObjectTransport(f, root, target)
        pub = PersonalPublication(f.c, transport=http)
        pub.review_binding = Mock(return_value="synthetic-independent-exact-sha-review")
        http.authorize_write = pub.write_authorized
        if plan_disabled:
            from test_personal_rules import denied
            from adp.network_http import Response as NativeResponse
            for branch in ("trunk", "work%2Fissue-" + str(number)):
                f.transport.api.responses[f.prefix + "/rules/branches/" + branch] = denied()
                f.transport.api.responses[f.prefix + "/branches/" + branch + "/protection"] = denied(classic=True)
            f.transport.api.responses[f.prefix + "/branches/work%2Fissue-" + str(number)] = Response(200,
                {"name": target.branch, "protected": False, "commit": {"sha": f.c.revision()}})
            http.server.permission = "ADMIN"
            ordinary = http.request
            def request(method, path, body, **kw):
                if method == "GET" and ("/rules/branches/" in path or path.endswith("/protection")):
                    if path.endswith("/protection"):
                        from copy import deepcopy
                        f.transport.calls.append(path)
                        reply = deepcopy(f.transport.api.responses.get(path, Response(404, None)))
                    else:
                        reply = f.transport.get(path)
                    raw = json.dumps(reply.body).encode()
                    http.last_response = reply.status, raw, reply.headers
                    return NativeResponse(reply.status, raw)
                return ordinary(method, path, body, **kw)
            http.request = request
        return f, pub, http

    def publish(self, number, *, plan_disabled=False):
        f, pub, http = self.stage(number, plan_disabled=plan_disabled)
        proposal = pub.preview()
        calls = []; actual = http.request
        def counted(method, path, body, **kw):
            calls.append((method, path)); return actual(method, path, body, **kw)
        http.request = counted
        f.c.fresh = Mock(side_effect=AssertionError("No unrelated complete discovery during publication"))
        result = pub.publish(
            reviewed=proposal["approval"], authorized=True, assume_quiescence=True, confirm_project_rules=True,
            accept_plan_unavailable=plan_disabled)
        self.assertEqual(result["status"], "PUBLISHED_UNACCEPTED")
        self.assertEqual(result["product_acceptance"], "NOT_ACCEPTED")
        self.assertEqual(http.server.refs()[pub.target.ref], f.c.revision())
        self.assertEqual(sum(kind == "ref" for kind, _ in http.server.mutations), 1)
        self.assertEqual(pub.journal.inspect()["state"]["execution"]["actions"][pub.record()["action_id"]]["status"], "OBSERVED")
        self.assertEqual(pub.service.measurements[-1]["boundaries"]["effect.settled"], 1)
        self.assertLessEqual(len(calls), 112)
        f.c.fresh.assert_not_called()
        self.assertFalse(any("/issues?" in path or "/pulls?" in path for _, path in calls))
        for future in range(number + 1, 4):
            self.assertFalse(any("/issues/" + str(future) in path for _, path in calls))
        print("PUBLICATION_NATIVE_STAGE " + json.dumps({"issue": number, "plan_disabled": plan_disabled, "http_calls": len(calls),
            "costs": list(pub.service.measurements), "seams": "synthetic stopped review and accepted predecessor; not runtime proof"}, sort_keys=True), flush=True)

    def test_issue1_through_cas_and_settlement(self):
        self.publish(1)

    def test_issue2_through_cas_and_settlement(self):
        self.publish(2)

    def test_issue3_through_cas_and_settlement(self):
        self.publish(3)

    def test_issue3_verified_private_plan_disabled_through_cas_and_settlement(self):
        self.publish(3, plan_disabled=True)

    def test_changed_dependency_or_scope_refuses_but_unrelated_future_does_not(self):
        f, pub, http = self.stage(2)
        baseline = pub.original()
        future = f.transport.api.responses[f.prefix + "/issues/3"].body
        future["body"] = "Unrelated future remains unadmitted"
        self.assertEqual(pub.original(), baseline)
        selected = f.transport.api.responses[f.prefix + "/issues/2"].body
        selected["body"] = "Unapproved selected change"
        with self.assertRaises(ADPError):pub.original()
        selected["body"] = f.personal.intent["original"]["body"]
        route = f.prefix + "/issues/2/dependencies/blocked_by?per_page=100&page=1"
        f.transport.api.responses[route] = Response(200, [])
        with self.assertRaises(ADPError):pub.original()
        self.assertEqual(http.server.mutations, [])

    def test_standalone_dispatch_cannot_borrow_cold_qualification_from_another_operation(self):
        f, pub, _ = self.stage(1)
        with self.assertRaises(ADPError):pub.validate_dispatch()
        self.assertIsNone(pub._write_basis)

    def test_qualified_predecessor_reuses_history_but_keeps_current_pr_and_memory(self):
        from copy import deepcopy
        from adp.discovery_types import Identity, Issue, Repository
        from adp.ticket_types import OriginalTicket
        identity = Identity("repo", "opaque")
        original = OriginalTicket(Repository("repo", "owned/project", "https://github.com/owned/project"),
            Issue(identity, 1, "https://github.com/owned/project/issues/1", "Original", "Original scope", "open", None,
                "2026-11-09T00:00:00Z", "a"*64, (), (), (), (), ()), 100)
        receipt = {"identity": data(identity), "original": data(original), "source": "a"*40, "merge": "b"*40,
            "pull": {"id": "10", "number": 1, "repository_id": "repo", "url": "https://example.invalid/pull/1", "node_id": "opaque-pr"},
            "actor": 91, "merge_payload": {"head_ref": "refs/heads/task", "base_ref": "refs/heads/trunk"}}
        previous = {"state": "closed", "merged": True, "node_id": "opaque-pr", "base": {"sha": "c"*40},
            "merge_commit_sha": "b"*40, "merged_by": {"id": 91}, "title": "Original", "body": "Original scope"}
        subject = {"health": "SYNCED", "local_owner": False, "state": {"owner": None, "generation": 1}}
        memory = SimpleNamespace(inspect=Mock(return_value=deepcopy(subject)))
        product = SimpleNamespace(forge=SimpleNamespace(pull=Mock(return_value=deepcopy(previous))))
        track = PersonalTrack.__new__(PersonalTrack)
        track.c = SimpleNamespace(transport=None)
        track.originals = {identity: original}
        qualified = (memory, subject, product, receipt, previous)
        self.assertIs(track.accepted(identity, _qualified=qualified), receipt)
        memory.inspect.assert_called_once_with()
        product.forge.pull.assert_called_once()
        for field, changed in (("title", "Changed"), ("body", "Changed"), ("merged", False),
                ("state", "open"), ("node_id", "other"), ("merge_commit_sha", "d"*40), ("merged_by", {"id": 92})):
            product.forge.pull.return_value = {**previous, field: changed}
            with self.subTest(field=field), self.assertRaises(ADPError):track.accepted(identity, _qualified=qualified)
        product.forge.pull.return_value = deepcopy(previous)
        memory.inspect.return_value["state"]["generation"] = 2
        with self.assertRaises(ADPError):track.accepted(identity, _qualified=qualified)
