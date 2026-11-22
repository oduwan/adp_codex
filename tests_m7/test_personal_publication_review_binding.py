"""Actual canonical revocation during an immutable synthetic upload batch."""
from adp.errors import ADPError
from personal_publication_fixtures import PublicationFixture


class PersonalPublicationReviewBindingTests(PublicationFixture):
    def revoked_check(self, purpose):
        pub = self.ready()
        proposal = pub.preview()
        row = self.c.record()
        worker = self.c.worker(row["code_review" if purpose == "code" else "original_review"])
        def revoke():
            # Owned synthetic canonical fixture: simulate operator revocation,
            # without introducing an engine reset/revocation API or new right.
            def changed(state, task, item):
                if purpose == "code":
                    item["approval"] = None
                else:
                    item["mode"], item["reason"] = "unsafe", "Synthetic original-scope review revocation"
            self.c.guard._change(self.c.task_id, worker["requirement"], changed)
        self.http.server.after_upload = revoke
        with self.assertRaises((ADPError, OSError)):
            self.publish(proposal["approval"])
        self.assertEqual([kind for kind, _ in self.http.server.mutations], ["blobs"])
        self.assertNotIn(pub.target.ref, self.http.server.refs())
        _, _, current = self.c.guard._snapshot(self.c.task_id, worker["requirement"])
        if purpose == "code":
            self.assertIsNone(current["approval"])
        else:
            self.assertEqual(current["mode"], "unsafe")
        self.assertTrue(self.c.memory.inspect()["local_owner"])
        self.assertEqual(len(self.requests), 4)

    def test_code_approval_revocation_stops_before_the_next_object(self):
        self.revoked_check("code")

    def test_original_scope_revocation_stops_before_the_next_object(self):
        self.revoked_check("original")
