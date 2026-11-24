"""Actual M4/raw-read projection only; no worker or mutation qualification."""
from types import SimpleNamespace

from adp.discovery import complete_snapshot
from adp.discovery_github import Response
from adp.errors import ADPError
from adp.personal_enrollment import selection
from adp.personal_publication import OriginalRead, PersonalPublication
from personal_fixtures import PersonalFixture
from test_config import snapshot


class PersonalPublicationProjectionTests(PersonalFixture):
    def preflight(self):
        observed, _ = self.observe()
        publication = object.__new__(PersonalPublication)
        publication.personal = SimpleNamespace(plan={"issue": 2, "repository": {"name": self.name}})
        publication.target = SimpleNamespace(api=self.prefix)
        publication.c = SimpleNamespace(track=SimpleNamespace(originals={
            issue.identity: SimpleNamespace(issue=issue) for issue in observed.snapshot.issues}))
        publication.read, publication.clock = self.transport, lambda: self.now
        bases = publication.original_bases()
        capture = OriginalRead(self.transport, bases[0], additional=bases[1:])
        actual, _ = selection(self.a, "forge", self.rid, capture)
        self.assertTrue(complete_snapshot(actual.snapshot))
        return publication, capture.observed, actual.snapshot

    def test_complete_preflight_and_targeted_reads_bind_all_originals_and_native_edges(self):
        before = snapshot(self.base)
        publication, approved, actual = self.preflight()
        calls = len(self.transport.calls)
        self.assertEqual(publication.current_original(), approved)
        self.assertEqual(len(self.transport.calls) - calls, 18)
        for number in (1, 2, 3):
            base = self.prefix + "/issues/" + str(number)
            self.assertIn(base, approved)
            for suffix in OriginalRead.SUFFIXES:
                self.assertIn(base + "/" + suffix + "?per_page=100&page=1", approved)
        for number in (2, 3):
            issue = next(i for i in actual.issues if i.number == number)
            self.assertEqual([(r.target.number, r.confidence) for r in issue.relations if r.kind == "BLOCKED_BY"],
                [(number - 1, "NATIVE")])
        self.assertEqual(snapshot(self.base), before)

    def test_changed_or_unavailable_parent_and_native_metadata_cannot_qualify(self):
        publication, approved, _ = self.preflight()
        parent = self.transport.api.responses[self.prefix + "/issues/1"].body
        original = parent["body"]
        parent["body"] = "Unapproved changed predecessor scope"
        self.assertNotEqual(publication.current_original(), approved)
        parent["body"] = original
        dependencies = self.prefix + "/issues/2/dependencies/blocked_by?per_page=100&page=1"
        retained = self.transport.api.responses[dependencies]
        self.transport.api.responses[dependencies] = Response(200, [])
        self.assertNotEqual(publication.current_original(), approved)
        self.transport.api.responses[dependencies] = retained
        route = self.prefix + "/issues/1/comments?per_page=100&page=1"
        for response in (Response(403, {}), Response(429, {}), Response(200, [], (("Link",
                '<https://api.github.com/repos/foreign/project/issues/1/comments?per_page=100&page=2>; rel="next"'),))):
            self.transport.api.responses[route] = response
            with self.subTest(status=response.status), self.assertRaises(ADPError):
                publication.current_original()
