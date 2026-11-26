"""Bounded targeted reconciliation after an existing effect; no new dispatch."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from adp.discovery_github import API, FixtureTransport, Response
from adp.discovery_schema import digest
from adp.errors import ADPError
from adp.execution_github import GitHubForgeBackend
from adp.execution_types import ExternalObservation
from adp.guard_types import data
from adp.personal_product import PersonalProduct
from adp.personal_publication import PersonalPublication
from adp.personal_report import PersonalReport
from adp.personal_rules import inspect_ref
from discovery_fixtures import issue, responses
from test_personal_rules import Native, HEAD


class ProductCleanupTests(unittest.TestCase):
    def fixture(self):
        directory = TemporaryDirectory(prefix="adp-report-reconcile-")
        self.addCleanup(directory.cleanup)
        name, prefix = "owned/project", "/repos/owned/project"
        rows = [issue(n, name=name) for n in (1, 2, 3)]
        for row in rows:row["updated_at"] = "2026-11-09T08:00:00Z"
        entries = responses(rows, name=name, rid="17")
        entries[prefix + "/issues/2/dependencies/blocked_by?per_page=100&page=1"] = Response(200, [rows[0]])
        metadata = {"id": 17, "node_id": "R_owned", "full_name": name, "owner": {"id": 91, "type": "User"},
            "permissions": {"pull": True, "push": True, "admin": True}}
        entries.update({"/user": Response(200, {"id": 91}), prefix: Response(200, metadata)})
        read = FixtureTransport(entries)
        native_get = read.get
        def personal_get(path):
            if path == "/user":
                read.calls.append(path)
                return deepcopy(read.responses[path])
            return native_get(path)
        read.get = personal_get  # Personal account route; ordinary M4 grammar stays unchanged.
        rows = [read.responses[prefix + "/issues/" + str(n)].body for n in (1, 2, 3)]
        owner = {"account_id": 91, "repository_id": "17", "read_access": True, "push_access": True, "admin_access": True}
        personal = SimpleNamespace(repository_id="17", plan={"repository": {"name": name}, "owner": owner, "issue": 2})
        p = PersonalReport.__new__(PersonalReport)
        p.personal, p.read, p.target = personal, read, SimpleNamespace(api=prefix)
        p.c = SimpleNamespace(episode=False, live=Mock(), allowed=Mock(), task_id="task", revision=lambda: "b"*40,
            memory=SimpleNamespace(control=Path(directory.name)), record=lambda: {"coordination": None},
            track=SimpleNamespace(link={"identity": {"repository_id": "17", "issue_id": rows[1]["node_id"], "forge": "github"}}))
        publication = PersonalPublication.__new__(PersonalPublication)
        publication.c, publication.personal, publication.read = p.c, personal, read
        publication.target = p.target
        publication.service, publication.clock = SimpleNamespace(limits=SimpleNamespace(request_limit=128)), lambda: 100
        originals = []
        publication.current_original(_issues=originals, _prerequisites=())
        before = originals[0]
        action = "a"*64
        body = "Implemented the admitted behavior."
        comment = {"id": 500, "node_id": "IC_owned", "user": {"id": 91, "node_id": "U_operator"},
            "body": body + "\n\n" + GitHubForgeBackend.marker(action),
            "created_at": "2026-11-09T08:00:01Z", "updated_at": "2026-11-09T08:00:01Z",
            "html_url": "https://github.com/owned/project/issues/2#issuecomment-500",
            "issue_url": API + prefix + "/issues/2"}
        rows[1]["updated_at"] = comment["created_at"]
        read.responses[prefix + "/issues/2/comments?per_page=100&page=1"] = Response(200, [deepcopy(comment)])
        observed = ExternalObservation("PRESENT", comment["html_url"], "b"*40, digest(body))
        row = {"view": {"operation": "REPORT", "body": body, "revision": "b"*40}, "approval": "original",
            "action": action, "before": data(before), "after": None, "comment": None, "observation": None, "requirement": "existing"}
        canonical = {"actions": {action: {"status": "SUBMITTED"}}, "publications": {}}
        p.report_record = lambda: deepcopy(row)
        p.save_report = lambda changed: row.update(deepcopy(changed))
        p.history_binding = Mock()
        p.journal = SimpleNamespace(inspect=lambda: {"state": {"execution": canonical}},
            change=lambda change: change(canonical, None, None))
        p.service = SimpleNamespace(bounded=lambda **kw: nullcontext(), request=lambda method, route: deepcopy(read.get(route).body))
        p.publication = publication
        p.observed_report = Mock(return_value=(observed, comment))  # Actual marker controls qualified separately.
        p.forge = SimpleNamespace(submit=Mock())
        return p, read, row, canonical, rows

    def reconcile(self, p):
        return p.report(reviewed="original", authorized=True, authorize_memory=True,
            assume_quiescence=True, confirm_rules=True)

    def test_selected_report_reconciliation_reads_nine_endpoints_and_is_idempotent(self):
        p, read, row, canonical, _ = self.fixture()
        read.calls.clear()
        with patch("adp.personal_enrollment.selection", side_effect=AssertionError("No whole-project rediscovery after report")):
            result = self.reconcile(p)
            self.assertEqual(result["status"], "REPORTED")
            self.assertEqual(len(read.calls), 9)
            self.assertFalse(any("/issues?" in path or "/pulls?" in path or "/issues/1/" in path or "/issues/3/" in path for path in read.calls))
            self.assertEqual(canonical["actions"][row["action"]]["status"], "OBSERVED")
            self.assertIsNotNone(row["after"])
            self.assertEqual(self.reconcile(p)["accounting"], "ALREADY_RECONCILED")
            self.assertEqual(len(read.calls), 9)  # Retained exact receipt; no source or mutation replay.
        p.forge.submit.assert_not_called()

    def test_report_selected_scope_edge_comment_owner_and_raw_drift_refuse(self):
        for change in ("scope", "edge", "comment", "owner", "identity", "raw", "unavailable", "pagination"):
            p, read, row, canonical, rows = self.fixture()
            prefix = p.target.api
            if change == "scope":rows[1]["body"] = "Unapproved scope"
            if change == "edge":read.responses[prefix + "/issues/2/dependencies/blocked_by?per_page=100&page=1"] = Response(200, [rows[2]])
            if change == "comment":read.responses[prefix + "/issues/2/comments?per_page=100&page=1"].body[0]["body"] = "Changed product claim"
            if change == "owner":read.responses["/user"] = Response(200, {"id": 92})
            if change == "identity":rows[1]["node_id"] = "foreign-opaque-id"
            if change == "raw":p.service.request = lambda *args: {**rows[1], "updated_at": "2026-11-09T08:00:02Z"}
            if change == "unavailable":read.responses[prefix + "/issues/2/timeline?per_page=100&page=1"] = Response(403, None)
            if change == "pagination":read.responses[prefix + "/issues/2/comments?per_page=100&page=1"] = Response(200, [], (("link", "omitted"),))
            with self.subTest(change=change), self.assertRaises(ADPError):self.reconcile(p)
            p.forge.submit.assert_not_called()
            self.assertIsNone(row["after"])
            self.assertEqual(canonical["publications"], {})

    def test_report_unknown_delivery_never_falls_through_to_new_submission(self):
        p, read, row, _, _ = self.fixture()
        p.observed_report.side_effect = ADPError("UNKNOWN: no observed original comment")
        read.calls.clear()
        for _ in range(2):
            with self.assertRaisesRegex(ADPError, "UNKNOWN"):self.reconcile(p)
        p.forge.submit.assert_not_called()
        self.assertEqual(read.calls, [])
        self.assertIsNone(row["after"])

    def test_readonly_known_ref_does_not_require_write_or_enumerate_all_refs(self):
        f = Native();f.permission = "READ"
        f.service.refs = Mock(side_effect=AssertionError("No global ref inventory for known source"))
        self.assertEqual(inspect_ref(f.service, writable=False), HEAD)
        self.assertEqual(f.calls, [("POST", "/graphql")])
        f.current = None
        self.assertIsNone(inspect_ref(f.service, writable=False))
        f.graph_error = [{"message": "forbidden"}]
        with self.assertRaises(ADPError):inspect_ref(f.service, writable=False)

    def test_history_record_parsing_reuses_actual_same_stage_subject(self):
        p = PersonalProduct.__new__(PersonalProduct)
        p.c = SimpleNamespace(episode=True)
        p.record = Mock(return_value={"schema_version": 2})
        capture = {"qualified": "actual"};observed = {"actual": "same-stage"}
        binding = {"historical_basis": "original", "historical_engine": "original", "reader_engine": "current"}
        with patch("adp.personal_history._reader_binding", return_value=binding):
            self.assertEqual(p.history_binding(capture=capture, view=binding, _observed=observed), binding)
        p.record.assert_called_once_with(_observed=observed)
