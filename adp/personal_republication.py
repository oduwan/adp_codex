"""Append-only corrected-SHA selection of the actual #40 publisher."""
from .discovery_schema import digest
from .personal_publication import PersonalPublication
from .personal_storage import create_private, read_private
from .policy_types import Operation
from .schema import key, require


class RevisionPublication(PersonalPublication):
    def __init__(self, product, *, transport=None):
        super().__init__(product.c, transport=transport)
        self.product = product
        self.path = self.personal.state / "publication-revisions" / (self.c.revision() + ".json")

    def local(self, *, _history_capture=None, _qualification=None):
        correction = self.product.record()["correction"]
        if self.c.episode:
            require(correction is not None, "Exact correction intent required")
            execution = next(e for e in self.product.record()["execution"] if e["approval"] == correction["approval"])
            self.product.history_binding(view=execution["view"])
        return super().local(_history_capture=_history_capture, _qualification=_qualification)

    def history(self):
        row = self.product.record()
        require(row is not None and row["correction"] is not None, "Only an admitted original-ticket correction may republish")
        receipts = {}
        for p in row["publications"]:
            path = self.personal.state / ("publication.json" if p["legacy"] else "publication-revisions/" + p["revision"] + ".json")
            receipt = read_private(path)
            require(receipt["view"]["revision"] == p["revision"] and receipt["action_id"] == p["action"], "Publication history identity changed")
            receipts[p["action"]] = receipt
        for identity, action in self.journal.inspect()["state"]["execution"]["actions"].items():
            if action["task_key"] == key(self.c.task_id) and action["operation"] == Operation.PUSH:
                require(identity in receipts and (action["revision"] == self.c.revision() or action["status"] == "OBSERVED"),
                        "Missing or uncertain publication history; never replace an intent")
        return row, receipts

    def record(self, *, _observed=None):
        row, receipts = self.history()
        current = read_private(self.path, optional=True)
        if current is None:
            require(not any(p["revision"] == self.c.revision() for p in row["publications"]), "Lost corrected publication intent cannot be recreated")
            return None
        return super().record(_observed=_observed)

    def save(self, receipt):
        row, _ = self.history()
        if not any(p["revision"] == self.c.revision() for p in row["publications"]):
            require(len(row["publications"]) < 2, "Original publication revision bound exhausted")
            row["publications"].append({"revision": self.c.revision(), "action": receipt["action_id"], "legacy": False})
            self.product.save(row)  # A crash cannot authorize another new intent.
        create_private(self.path.parent)
        super().save(receipt)

    def admit_task(self, execution, task_key, task):
        self.history()
        existing = execution["tasks"].get(task_key)
        require(existing is not None and not existing["jobs"] and existing["review"] is None
                and all(existing[k] == task[k] for k in existing if k not in ("revision", "product_iteration"))
                and task["revision"] == self.c.memory.inspect()["tasks"][task_key]["source_revision"], "Canonical corrected source differs")
        execution["tasks"][task_key] = task
