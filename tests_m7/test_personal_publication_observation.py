"""Focused receipt comparisons reuse M4 fixtures; no publication or worker."""
from types import SimpleNamespace

from adp.discovery_github import Response
from adp.errors import ADPError
from adp.personal_publication import OriginalRead, PersonalPublication
from adp.runtime_limits import DEFAULTS
from personal_fixtures import PersonalFixture


class PersonalPublicationObservationTests(PersonalFixture):
    def validated_baseline(self):
        transport = self.transport
        capture = OriginalRead(transport, self.prefix + "/issues/1")
        self.transport = capture
        observation, _ = self.observe()  # Actual complete accepted M4 discovery.
        self.assertEqual(observation.facts["discovery"], "COMPLETE")
        self.assertEqual(len(capture.observed), 5)
        self.transport = transport
        pub = PersonalPublication.__new__(PersonalPublication)
        pub.personal = SimpleNamespace(plan={"issue": 1, "repository": {"name": self.name}})
        pub.target = SimpleNamespace(api=self.prefix)
        pub.read, pub.clock = transport, lambda: self.now
        pub.service = SimpleNamespace(limits=DEFAULTS)
        return pub, capture.observed

    def test_targeted_receipts_are_the_actual_validated_original_and_detect_changes(self):
        pub, baseline = self.validated_baseline()
        self.assertEqual(pub.current_original(), baseline)
        base = self.prefix + "/issues/1"
        for path, changed in ((base, {**self.transport.api.responses[base].body, "body": "Unapproved scope; same timestamp"}),
                (base + "/comments?per_page=100&page=1", [{"id": 90, "body": "Unapproved amendment"}]),
                (base + "/dependencies/blocked_by?per_page=100&page=1", [{"id": 91, "number": 3}]),
                (base + "/timeline?per_page=100&page=1", [{"event": "marked_as_duplicate"}]),
                (base + "/sub_issues?per_page=100&page=1", [{"id": 92, "number": 2}])):
            original = self.transport.api.responses[path]
            self.transport.api.responses[path] = Response(200, changed)
            with self.subTest(path=path):
                self.assertNotEqual(pub.current_original(), baseline)
            self.transport.api.responses[path] = original

    def test_targeted_partial_forbidden_conflicting_and_unstable_records_fail_closed(self):
        pub, _ = self.validated_baseline()
        base = self.prefix + "/issues/1"
        route = base + "/comments?per_page=100&page=1"
        original = self.transport.api.responses[route]
        for response in (Response(403, None), Response(200, [], (("link", "malformed"),)),
                         Response(200, [], (("link", ""), ("Link", "")))):
            self.transport.api.responses[route] = response
            with self.subTest(response=response), self.assertRaises(ADPError):
                pub.current_original()
        self.transport.api.responses[route] = original
        first = self.transport.api.responses[base]
        second = Response(200, {**first.body, "body": "Changed between reads"})
        self.transport.api.responses[base] = (first, second)
        with self.assertRaises(ADPError):
            pub.current_original()
