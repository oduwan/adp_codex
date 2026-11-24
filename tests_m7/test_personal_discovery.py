"""Personal semantic fingerprints on disposable fixtures; no pilot operations."""
from copy import deepcopy
from dataclasses import replace
import json
from unittest.mock import patch

from adp.discovery_github import API, FixtureTransport, GitHubDiscoveryAdapter, Response
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.guard_types import data
from adp.operator_authority import remote_semantics
from adp.personal_discovery import PersonalGitHubDiscoveryAdapter
from adp.personal_enrollment import apply_personal
from adp.personal_track import same_observation
from adp.personal_storage import approval
from discovery_fixtures import pull, responses, issue
from personal_fixtures import PersonalFixture
from test_config import snapshot


def repository(name="personal/project", rid=17, node="R_personal", owner=91):
    return {"id": rid, "node_id": node, "name": name.split("/")[1], "full_name": name,
        "url": API + "/repos/" + name, "html_url": "https://github.com/" + name,
        "private": True, "default_branch": "trunk",
        "owner": {"id": owner, "login": name.split("/")[0], "type": "User"},
        "permissions": {"pull": True, "push": True, "admin": True}}


class RotatingRead:
    """Synthetic incidental values change at every fresh native observation."""
    def __init__(self, source, prefix):
        self.source, self.prefix, self.sequence = source, prefix, 0

    def get(self, path):
        observed = self.source.get(path)
        body = deepcopy(observed.body)
        self.sequence += 1
        marker = "synthetic-ephemeral-value-" + str(self.sequence)
        if path == self.prefix and type(body) is dict:
            body["temp_clone_token"] = marker
        if path.partition("?")[0].startswith(self.prefix + "/pulls"):
            for row in body if type(body) is list else [body]:
                if type(row) is dict:
                    for side in ("head", "base"):
                        if type(row.get(side)) is dict and type(row[side].get("repo")) is dict:
                            row[side]["repo"]["temp_clone_token"] = marker + "-" + side
        return Response(observed.status, body, observed.headers)


class PersonalDiscoveryTests(PersonalFixture):
    def rotating(self):
        self.transport.api.responses[self.prefix] = Response(200, repository())
        self.transport = RotatingRead(self.transport, self.prefix)

    def test_rotating_repository_keeps_exact_approved_plan_and_applies(self):
        self.rotating()
        before = snapshot(self.base)
        plan, original, docs = self.plan()
        token = approval(plan)
        try:
            second, second_original, second_docs = self.plan(approved=token)
        except ADPError:
            self.fail("Incidental repository transport rotation invalidated the exact personal plan")
        self.assertEqual((second, second_original, second_docs), (plan, original, docs))
        self.assertEqual(snapshot(self.base), before)
        self.assertNotIn("synthetic-ephemeral-value", json.dumps(plan))
        personal = apply_personal(plan, original, docs, approved=token, authorized=True,
            transport=self.transport, clock=lambda: self.now)
        observed = personal.memory().inspect()
        self.assertTrue(observed["local_owner"])
        self.assertEqual(personal.intent["phase"], "ENROLLED")
        self.assertFalse(personal.feature.exists())
        self.assertNotIn("synthetic-ephemeral-value", json.dumps(personal.intent))

    def adapter(self, entries, *, personal=True, per_page=100, rotating=True):
        source = FixtureTransport(entries)
        transport = RotatingRead(source, self.prefix) if rotating else source
        cls = PersonalGitHubDiscoveryAdapter if personal else GitHubDiscoveryAdapter
        return cls(self.name, transport, expected_id=self.rid, per_page=per_page, clock=lambda: self.now)

    def entries(self, *, prs=False, per_page=100):
        rows = [issue(n, name=self.name) for n in (1, 2, 3)]
        pr = pull(name=self.name, rid=17)
        pr["head"]["repo"] = repository("fork/project", 18, "R_fork", 92)
        pr["base"]["repo"] = repository()
        entries = responses(rows, [pr] if prs else [], name=self.name, rid=self.rid, per_page=per_page)
        entries[self.prefix] = Response(200, repository())
        for n in (2, 3):
            entries[f"{self.prefix}/issues/{n}/dependencies/blocked_by?per_page={per_page}&page=1"] = Response(200, [rows[n - 2]])
        return entries

    def test_initial_refresh_coverage_stable_and_raw_evidence_untouched(self):
        entries = self.entries()
        original = deepcopy(entries)
        adapter = self.adapter(entries)
        first, second = adapter.discover(), adapter.discover()
        self.assertEqual(first, second)
        self.assertEqual(first, self.adapter(entries, rotating=False).discover())
        self.assertEqual(remote_semantics((first,)), remote_semantics((second,)))
        self.assertTrue(all(c.status == "COMPLETE" for c in first.coverage))
        for name in ("repository", "repository-refresh"):
            self.assertEqual(next(c.digest for c in first.coverage if c.name == name), digest(repository()))
        self.assertEqual(entries, original)
        raw = adapter.transport.get(self.prefix)
        saved = deepcopy(raw)
        semantic = adapter._semantic(self.prefix, raw.body)
        self.assertNotIn("temp_clone_token", semantic)
        self.assertIn("temp_clone_token", raw.body)
        self.assertEqual(raw, saved)
        self.assertNotIn("synthetic-ephemeral-value", json.dumps(data(first)))

    def test_pr_head_base_inventory_detail_refresh_and_native_next_snapshot(self):
        adapter = self.adapter(self.entries(prs=True))
        first, second = adapter.discover(), adapter.discover()
        self.assertEqual(first, second)
        self.assertEqual(first, self.adapter(self.entries(prs=True), rotating=False).discover())
        self.assertTrue(same_observation(first, replace(second, observed_at=self.now + 1)))
        self.assertTrue(all(c.status == "COMPLETE" for c in first.coverage))
        self.assertEqual(len(first.pulls), 1)
        self.assertEqual(first.pulls[0].revision, second.pulls[0].revision)
        edges = [(i.number, r.kind, r.target.number) for i in first.issues for r in i.relations if r.confidence == "NATIVE"]
        self.assertEqual(edges, [(2, "BLOCKED_BY", 1), (3, "BLOCKED_BY", 2)])
        self.assertNotIn("synthetic-ephemeral-value", json.dumps(data(first)))

    def test_malformed_nested_repository_never_completes_pr_discovery(self):
        for side in ("head", "base"):
            with self.subTest(side=side):
                entries = self.entries(prs=True)
                detail = self.prefix + "/pulls/10"
                # Inventory and detail must be independently observed objects.
                entries[detail] = Response(200, deepcopy(entries[detail].body))
                entries[detail].body[side]["repo"]["private"] = 1
                observed = self.adapter(entries).discover()
                self.assertEqual(observed.pulls, ())
                self.assertTrue(any(c.status != "COMPLETE" for c in observed.coverage))
                inventory = self.prefix + "/pulls?state=all&sort=created&direction=asc&per_page=100&page=1"
                entries[inventory].body[0][side]["repo"]["private"] = 1
                with self.assertRaisesRegex(ADPError, "Malformed personal repository transport metadata"):
                    self.adapter(entries).discover()

    def test_rotating_pr_duplicates_still_mark_inventory_partial(self):
        entries = self.entries(prs=True, per_page=1)
        route = self.prefix + "/pulls?state=all&sort=created&direction=asc&per_page=1&page=2"
        entries[route] = entries[route.replace("page=2", "page=1")]
        adapter = self.adapter(entries, per_page=1)
        observed = adapter.discover()
        self.assertTrue(any(c.name == "pulls" and c.status == "PARTIAL" for c in observed.coverage))
        self.assertEqual(len(observed.pulls), 1)
        self.assertEqual(adapter.transport.source.calls.count(self.prefix + "/pulls/10"), 1)

    def test_default_raw_receipts_and_no_token_personal_compatibility(self):
        entries = self.entries(prs=True)
        plain = self.adapter(entries, personal=False, rotating=False).discover()
        self.assertEqual(self.adapter(entries, rotating=False).discover(), plain)
        self.assertEqual(next(c.digest for c in plain.coverage if c.name == "repository"), digest(repository()))
        current = self.adapter(entries, personal=False)
        first, second = current.discover(), current.discover()
        self.assertNotEqual(remote_semantics((first,)), remote_semantics((second,)))
        self.assertNotEqual(first.pulls[0].revision, second.pulls[0].revision)
        self.assertTrue(any(c.name == "inventory-stable" and c.status == "CHANGED" for c in first.coverage))
        # Accepted opaque/minimal default shapes are not tightened globally.
        minimal = responses(name=self.name, rid=self.rid)
        self.assertEqual(self.adapter(minimal, rotating=False).discover(),
                         self.adapter(minimal, personal=False, rotating=False).discover())

    def test_repo_semantic_changes_remain_bound_or_refused(self):
        baseline = remote_semantics((self.adapter(self.entries()).discover(),))
        changes = ({"id": 18}, {"node_id": "R_changed"}, {"full_name": "other/project"},
            {"name": "other"}, {"owner": {"id": 92, "login": "personal", "type": "User"}},
            {"private": False}, {"default_branch": "other"}, {"permissions": {"pull": True, "push": False}},
            {"archived": True}, {"has_new_transport_hint": "changed"}, {"protection": {"enforce_admins": True}})
        for change in changes:
            with self.subTest(fields=list(change)):
                entries = self.entries()
                entries[self.prefix] = Response(200, {**repository(), **change})
                try:
                    observed = self.adapter(entries).discover()
                except ADPError:
                    continue
                self.assertNotEqual(remote_semantics((observed,)), baseline)

    def test_pr_semantic_changes_remain_bound_and_invalidate_observation(self):
        entries = self.entries(prs=True)
        baseline = self.adapter(entries).discover()
        changes = (("head", "sha", "c" * 40), ("base", "sha", "d" * 40),
            ("head", "ref", "work/new"), ("base", "ref", "other"),
            (None, "state", "closed"), (None, "merged", True), (None, "draft", False),
            (None, "title", "Changed user text"), (None, "unknown_field", "changed"))
        for side, field, value in changes:
            with self.subTest(side=side, field=field):
                changed = deepcopy(entries)
                row = changed[self.prefix + "/pulls/10"].body
                (row[side] if side else row)[field] = value
                observed = self.adapter(changed).discover()
                self.assertNotEqual(remote_semantics((observed,)), remote_semantics((baseline,)))
                self.assertFalse(same_observation(observed, baseline))
                self.assertNotEqual(observed.pulls[0].revision, baseline.pulls[0].revision)

    def test_issue_revision_and_native_dependencies_are_not_projected(self):
        entries = self.entries()
        baseline = self.adapter(entries).discover()
        for endpoint in ("/issues/1", "/issues/2/dependencies/blocked_by?per_page=100&page=1"):
            with self.subTest(endpoint=endpoint):
                changed = deepcopy(entries)
                if "blocked_by" in endpoint:
                    changed[self.prefix + endpoint] = Response(200, [])
                else:
                    changed[self.prefix + endpoint].body["body"] = "Changed original scope"
                observed = self.adapter(changed).discover()
                self.assertNotEqual(remote_semantics((observed,)), remote_semantics((baseline,)))

    def test_projection_does_not_strip_user_text_unknown_slots_or_fields(self):
        adapter = self.adapter(self.entries())
        text = {"temp_clone_token": "user-authored", "body": "temp_clone_token is acceptance text"}
        for path in ("/issues", "/issues/1", "/issues/1/comments", "/issues/1/timeline"):
            self.assertEqual(adapter._semantic(self.prefix + path, text), text)
        pr = self.entries(prs=True)[self.prefix + "/pulls/10"].body
        pr.update(title="temp_clone_token=user-authored", body="Keep exact content", temp_clone_token="unknown PR field")
        pr["head"]["repo"].update(temp_clone_token="synthetic", custom={"temp_clone_token": "bind nested unknown"})
        pr["head"]["repo"]["source"] = {**repository(), "temp_clone_token": "unqualified nested slot"}
        saved = deepcopy(pr)
        projected = adapter._semantic(self.prefix + "/pulls/10", pr)
        self.assertEqual(pr, saved)
        self.assertEqual(projected["temp_clone_token"], "unknown PR field")
        self.assertEqual(projected["title"], pr["title"])
        self.assertEqual(projected["head"]["repo"]["source"], pr["head"]["repo"]["source"])
        self.assertEqual(projected["head"]["repo"]["custom"], {"temp_clone_token": "bind nested unknown"})
        changed = deepcopy(pr)
        changed["head"]["repo"]["custom"]["temp_clone_token"] = "different"
        self.assertNotEqual(adapter._fingerprint(self.prefix + "/pulls/10", pr),
                            adapter._fingerprint(self.prefix + "/pulls/10", changed))

    def test_malformed_token_bearing_repository_shapes_fail_closed_without_value(self):
        adapter = self.adapter(self.entries())
        changes = ({"id": True}, {"id": 17.0}, {"id": "17"}, {"id": None},
            {"node_id": ""}, {"name": "other"}, {"url": "https://evil.invalid/repo"},
            {"private": 1}, {"owner": {"id": True, "login": "personal", "type": "User"}},
            {"owner": {"id": 91, "login": "wrong", "type": "User"}},
            {"permissions": {"push": 1}}, {"temp_clone_token": None}, {"temp_clone_token": []},
            {"temp_clone_token": ""}, {"temp_clone_token": "x" * 4097})
        for change in changes:
            with self.subTest(fields=list(change)):
                raw = {**repository(), "temp_clone_token": "SYNTHETIC_PRIVATE_MARKER", **change}
                with self.assertRaises(ADPError) as caught:
                    adapter._semantic(self.prefix, raw)
                self.assertNotIn("SYNTHETIC_PRIVATE_MARKER", str(caught.exception))
                self.assertEqual(raw, {**repository(), "temp_clone_token": "SYNTHETIC_PRIVATE_MARKER", **change})

    def test_selected_identity_and_fork_repository_conflicts_fail_closed(self):
        for side, foreign in (("base", repository("fork/project", 18, "R_fork", 92)),
                ("head", repository("personal/project", 18)),
                ("head", repository("fork/project", 17, "R_fork", 92))):
            with self.subTest(side=side, rid=foreign["id"]):
                entries = self.entries(prs=True)
                entries[self.prefix + "/pulls/10"].body[side]["repo"] = foreign
                try:
                    observed = self.adapter(entries).discover()
                except ADPError:
                    continue
                self.assertTrue(any(c.status != "COMPLETE" for c in observed.coverage))
                self.assertEqual(observed.pulls, ())

    def test_true_drift_expiry_and_reused_approval_cannot_write_state(self):
        self.rotating()
        source = self.transport.source.api.responses
        plan, original, docs = self.plan()
        token = approval(plan)
        before = snapshot(self.base)
        source[self.prefix].body["private"] = False
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=token, authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        source[self.prefix].body["private"] = True
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=token, authorized=True,
                           transport=self.transport, clock=lambda: plan["window"]["expires_at"])
        for choice in (replace(self.choices, directory=self.base / "another-state"), replace(self.choices, issue=2)):
            with self.subTest(issue=choice.issue), self.assertRaises(ADPError):
                self.plan(choices=choice, approved=token)
        self.assertEqual(snapshot(self.base), before)
        self.assertFalse(self.directory.exists())

    def test_rules_checks_and_governance_drift_keep_exact_approval_gate(self):
        self.rotating()
        plan, original, docs = self.plan()
        before = snapshot(self.base)
        route = self.prefix + "/rules/branches/trunk"
        source = self.transport.source.api.responses
        source[route] = Response(200, [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "new-required-check"}]}}])
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        self.assertEqual(snapshot(self.base), before)
        source[route] = Response(200, [])
        (self.a / "AGENTS.md").write_text("Require the project's newly changed acceptance review.\n")
        changed_source = snapshot(self.base)
        with self.assertRaises(ADPError):
            apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        self.assertEqual(snapshot(self.base), changed_source)

    def test_legacy_raw_bound_approval_is_not_migrated_or_relabelled(self):
        self.rotating()
        # Reproduce a previously bound raw observation without caching it.
        with patch("adp.personal_discovery.PersonalGitHubDiscoveryAdapter", GitHubDiscoveryAdapter):
            legacy, original, docs = self.plan()
        before = snapshot(self.base)
        with self.assertRaises(ADPError):
            apply_personal(legacy, original, docs, approved=approval(legacy), authorized=True,
                           transport=self.transport, clock=lambda: self.now)
        self.assertEqual(snapshot(self.base), before)

    def test_reapply_exact_enrollment_does_not_reset_m1_m2_on_rotation(self):
        self.rotating()
        plan, original, docs = self.plan()
        personal = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                                  transport=self.transport, clock=lambda: self.now)
        before = personal.memory().inspect()
        again = apply_personal(plan, original, docs, approved=approval(plan), authorized=True,
                               transport=self.transport, clock=lambda: self.now)
        self.assertEqual(again.memory().inspect(), before)
