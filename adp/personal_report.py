"""One separately authorized substantive report using the actual M7 forge."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from datetime import datetime
import re
import secrets

from .personal_read_frame import qualified as historical_operation
from .discovery_github import API, _author, _id, _issue_revision, inferred
from .discovery_schema import digest, typed
from .discovery_types import Identity, Issue
from .errors import ADPError
from .execution_memory import invocation_lock
from .guard_types import Permit, data
from .personal_github import owned_repository
from .personal_product import PersonalProduct, ASSENT, ENVELOPE, TOKEN
from .github_product import DelegationProfile, delegation_subject
from .personal_product_http import PersonalProductTransport
from .personal_product_policy import product_text
from .personal_publication import WARRANT
from .personal_report_child import validate_report
from .personal_storage import LIMIT, read_private
from .personal_track import immutable
from .network_git import GitHubTarget
from .policy_types import Effect, Operation, Request
from .schema import encode, fields, key, require
from .storage import atomic
from .runtime_limits import bind_consent, network_operation


class PersonalReportTransport(PersonalProductTransport):
    validator = staticmethod(validate_report)
    http_child = "personal_report_child.py"


def own_report_delta(before, after, comment, raw):
    """Lossless, purpose-bound reconciliation of this exact authorized addition."""
    require(comment["body"] and comment["updated_at"] == comment["created_at"]
            and after.updated_at == comment["created_at"] and _issue_revision(raw) == after.revision,
            "Own report timing/version is not causally qualified")
    require(datetime.fromisoformat(after.updated_at.replace("Z", "+00:00")) >=
            datetime.fromisoformat(before.updated_at.replace("Z", "+00:00")), "Own report cannot reverse original source time")
    prior = dict(raw, updated_at=before.updated_at)
    require(_issue_revision(prior) == before.revision, "Original source version changed beyond the authorized comment")
    extra = [text for text in after.comments if text not in before.comments]
    require(len(extra) == 1 and extra[0].id == _id(comment) and extra[0].body == comment["body"]
            and extra[0].author == _author(comment)
            and extra[0].updated_at == comment["updated_at"], "Unexpected comment/author/body delta")
    # Use the canonical repository name from the authenticated source URL.
    repository = after.url.split("https://github.com/", 1)[1].split("/issues/", 1)[0]
    additions = inferred(extra[0].body, repository, extra[0].source)
    retained = replace(after, updated_at=before.updated_at, revision=before.revision,
        comments=tuple(t for t in after.comments if t != extra[0]),
        authors=tuple(a for a in after.authors if a != extra[0].author or a in before.authors),
        relations=tuple(r for r in after.relations if r not in additions))
    require(retained == before, "Original scope, native dependencies or previous evidence changed")
    return True


class PersonalReport(PersonalProduct):
    def __init__(self, coordinator, *, transport=None):
        p = coordinator.personal.plan
        target = GitHubTarget(coordinator.personal.repository_id, p["repository"]["node_id"],
            p["repository"]["database_id"], *p["repository"]["name"].split("/"), p["feature"]["branch"])
        transport = transport or PersonalReportTransport(target,
            protected_roots=(coordinator.personal.feature, Path(p["checkout"]["path"]), coordinator.personal.directory,
                Path(__file__).resolve().parents[1]), authorize_write=self.write_authorized)
        super().__init__(coordinator, transport=transport)
        require(coordinator.track is not None, "Select a frozen personal track first")
        self.report_path = self.personal.state / "report.json"

    def report_record(self):
        row = read_private(self.report_path, optional=True)
        if row is not None:
            fields(row, "view approval binding action requirement reservation observation before after comment")
            require(row["view"]["operation"] == "REPORT" and row["approval"] == self.token(row["view"], row["binding"])
                    and row["action"] == self.report_key(), "Original report identity/consent changed")
            require(row["reservation"] is None and row["requirement"] is None
                    or row["reservation"] is not None
                    and row["requirement"] == typed(Permit, row["reservation"]).decision.baseline.requirement_id,
                    "Report must retain its exact original M2 requirement/permit")
        return row

    def report_key(self):
        task = self.c.memory.inspect()["tasks"][key(self.c.task_id)]
        return digest({"repository": self.personal.repository_id, "task": self.c.task_id, "iteration": task["iteration"]})

    def save_report(self, row):
        atomic(self.report_path, encode(row, LIMIT))

    @network_operation("product.report_preview")
    @historical_operation
    def report_preview(self, *, approved=None):
        now = self.clock()
        if approved is None:
            issued, expires, nonce = now, min(now + 300, self.personal.plan["window"]["expires_at"]), secrets.token_hex(16)
        else:
            match = TOKEN.fullmatch(approved or "")
            require(match is not None, "Exact separate report consent required")
            issued, expires, nonce = int(match[1]), int(match[2]), match[3]
        require(issued <= now < expires <= self.personal.plan["window"]["expires_at"] and expires - issued <= 300,
                "Original report window expired")
        bind_consent({"runtime_limits": self.service.limits.values(), "expires_at": expires}, now)
        track = self.c.track
        identity = typed(Identity, track.link["identity"])
        with self.service.bounded():
            accepted = track.accepted(identity, transport=self.transport, runtime=self.c.runtime)
            require(accepted is not None, "Only actual accepted completion can produce a product report")
            capture = {} if self.c.episode else None
            seal = self.local(_history_capture=capture)
            facts = self.facts()
            original = self.original()
            current, _, _ = track.status(transport=self.transport)
            body = ("Implemented original Issue " + str(self.personal.plan["issue"]) + ": " + self.personal.intent["original"]["title"]
                + "\n\nReviewed source: `" + accepted["source"] + "`. " + accepted["pull"]["url"]
                + "\nProject checks at acceptance: " + accepted["ci"]["status"]
                + ". Independent review approved that exact source."
                + "\nMerged as `" + accepted["merge"] + "` by github-user:" + str(accepted["actor"]) + "."
                + ("\nNext original Issue " + str(current["next_issue"]) + " needs separate scope/window approval."
                    if current["next_issue"] is not None else "\nTrack: " + current["status"] + "."))
            product_text("Product outcome", body)
            observed = self.c.memory.inspect()
            view = {"operation": "REPORT", "runtime_limits": self.service.limits.values(),
                "setup": self.personal.intent["approval"], "repository": self.personal.plan["repository"],
                "revision": self.c.revision(), "source_tree": accepted["tree"], "source_ref": self.target.ref,
                "facts": facts, "method": None, "title": None, "body": body,
                "target": self.personal.intent["original"]["url"], "completion": digest(accepted),
                "review_binding": seal, "original_observation": original,
                "administration": digest(self.c.record()["feature_administration"]),
                "policy_assent": ASSENT, "administrative_quiescence_warrant": WARRANT,
                "merge_envelope": ENVELOPE, "generation": observed["state"]["generation"],
                "checkpoint": observed["local_head"], "issued_at": issued, "expires_at": expires, "nonce": nonce}
            if capture is not None:
                from .personal_episode import same_observation
                same_observation(capture["subject"], observed)
                view.update(self.history_binding(capture=capture))
            return {"status": "REPORT_PROPOSED", "result": view, "approval": self.token(view, self.transport.credential_binding),
                "binding": self.transport.credential_binding}

    def final_boundary(self):
        view = self.live()
        require(self.original() == view["original_observation"] and self.facts() == view["facts"],
                "Current original source/project/report conditions changed")
        require(self.c.track.accepted(typed(Identity, self.c.track.link["identity"]), transport=self.transport,
                    runtime=self.c.runtime) is not None and self._policy_final() is True,
                "Current exact accepted completion and M3 authority required")

    @network_operation("product.report_observation")
    @historical_operation
    def observed_report(self, row):
        bind_consent(row["view"])
        owner = owned_repository(self.read, self.forge.repository, self.personal.repository_id)
        metadata = self.service.request("GET", self.target.api)
        require(owner == self.personal.plan["owner"] and type(metadata) is dict and metadata.get("node_id") == self.target.node_id,
                "Current report repository/account identity or permissions changed")
        action = self.journal.inspect()["state"]["execution"]["actions"].get(row["action"])
        require(action is not None, "Durable canonical report intent required")
        observed = self.forge.observe(row["action"], Operation.REPORT, action["payload"], attempted=True)
        require(observed.status == "PRESENT" and not self.service.unconfirmed_contexts(), "UNKNOWN report; observe only, never POST again")
        inventory = self.forge.inventory(Operation.REPORT, action["payload"])
        require(inventory is not None, "Complete exact target comment inventory required")
        matches = [item for item in inventory if self.forge.marker(row["action"]) in (item.get("body") or "")]
        require(len(matches) == 1, "Duplicate/foreign report marker")
        comment = matches[0]
        expected = "https://github.com/" + self.forge.repository + "/issues/" + str(self.personal.plan["issue"])
        require(type(comment.get("id")) is int and comment["id"] > 0
                and comment.get("html_url") == expected + "#issuecomment-" + str(comment["id"])
                and comment.get("issue_url") == API + self.target.api + "/issues/" + str(self.personal.plan["issue"])
                and type(comment.get("user")) is dict and type(comment["user"].get("id")) is int
                and comment["user"]["id"] == self.personal.plan["owner"]["account_id"]
                and comment.get("body") == row["view"]["body"] + "\n\n" + self.forge.marker(row["action"]),
                "Exact report target/account/identity/body is unknown")
        _id(comment); _author(comment)
        require(observed.reference == comment["html_url"] and observed.revision == row["view"]["revision"]
                and observed.body_digest == digest(row["view"]["body"]), "Consecutive report observations disagree")
        require(all(type(comment.get(name)) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", comment[name])
                for name in ("created_at", "updated_at")), "Report timestamp evidence is missing/malformed")
        if row["comment"] is not None:
            before = row["comment"]
            require(all(comment.get(name) == before.get(name) for name in
                ("id", "node_id", "html_url", "issue_url", "body", "created_at", "updated_at"))
                and _author(comment) == _author(before), "Accepted own report identity or metadata changed")
        return observed, comment

    @network_operation("product.report")
    @historical_operation
    def report(self, *, reviewed, authorized, authorize_memory, assume_quiescence, confirm_rules):
        require(authorized is True and authorize_memory is True and assume_quiescence is True and confirm_rules is True,
                "Separate exact REPORT, memory, rules and administrative-quiescence approvals required")
        self.c.live()
        with invocation_lock(self.c.memory.control):
            row = self.report_record()
            retained = row is not None
            if row is None:
                proposal = self.report_preview(approved=reviewed)
                require(proposal["approval"] == reviewed, "Exact report proposal changed")
                current = self.c.track.current()
                issue = next(i for i in current.snapshot.issues if data(i.identity) == self.c.track.link["identity"])
                row = {"view": proposal["result"], "approval": reviewed, "binding": proposal["binding"],
                    "action": self.report_key(), "requirement": None, "reservation": None, "observation": None,
                    "before": data(issue), "after": None, "comment": None}
                immutable(self.report_path, row)
            require(row["approval"] == reviewed, "Only the original report may reconcile")
            bind_consent(row["view"])
            self.active = row
            self.history_binding(view=row["view"])
            actions = self.journal.inspect()["state"]["execution"]["actions"]
            if row["action"] not in actions:
                self.live()
                if retained:
                    self.local()
                    require(self.original() == row["view"]["original_observation"] and self.facts() == row["view"]["facts"],
                            "Retained report original or project policy changed")
                permit = self.c.reserve("personal-report:" + row["action"])
                row["reservation"] = data(permit)
                row["requirement"] = permit.decision.baseline.requirement_id
                self.save_report(row)
                with self.service.bounded():
                    provider, task = self.provider(permit)
                    plan = provider.plan(task, Request(Operation.REPORT, report_target=row["view"]["target"], report_body=row["view"]["body"]))
                    q = self.qualifications(provider, plan)
                    profile = DelegationProfile(self.personal.repository_id, self.personal.plan["issue_id"], self.c.task_id,
                        plan.task.iteration, self.target.ref, row["view"]["facts"]["base_ref"], self.c.revision(), plan.policy_digest,
                        self.personal.plan["original_digest"], ("REPORT",), "MANUAL", (), "UNKNOWN",
                        row["view"]["issued_at"], row["view"]["expires_at"])
                    profile = replace(profile, evidence=self.proof("github-product/delegation", delegation_subject(profile),
                        "report-delegation", {"profile": data(profile), "plan": data(plan)}))
                    require(self.c.authority.verify(profile.evidence, purpose="github-product/delegation", subject=delegation_subject(profile)),
                            "Separate operation-specific REPORT delegation required")
                    authorization = self.authorize(provider, plan, q)
                    require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Actual M3 refused the exact REPORT")
                    payload = {**data(plan.payload), "revision": task.revision}
                    action = {"task_key": key(self.c.task_id), "generation": task.generation, "operation": "REPORT",
                        "revision": task.revision, "source_ref": task.source_ref, "target": plan.target_ref,
                        "expected_target": plan.expected_target, "payload": payload, "status": "PREPARED", "observation": None,
                        "plan_digest": digest(plan)}
                    self.journal.change(lambda e, s, t: e["actions"].update({row["action"]: action}))
                    dispatch = self.forge.prepare_dispatch(row["action"], action)
                    self.journal.change(lambda e, s, t: e["actions"][row["action"]].update(status="SUBMITTED"))
                    current = provider.plan(task, plan.request)
                    require(replace(current, safety=plan.safety) == plan, "Report plan changed after checkpoint")
                    plan = current
                    authorization = self.authorize(provider, plan, q)
                    require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Fresh checkpoint-bound M3 refused report")
                    effect = self.proof("execution/effect", digest({"id": row["action"], "plan": digest(plan), "payload": payload}),
                        "effect", {"id": row["action"], "plan": digest(plan), "payload": payload})
                    self._policy_final = lambda: provider.decide(plan, authorization).effect == Effect.ALLOW
                from .personal_read_frame import current_source
                self.c.workers.fence()
                current_source(self, row, product=True)  # One immutable handoff.
                self._writing = (row["action"], {**action, "status": "SUBMITTED"}, self.c.memory.inspect())
                try:
                    self.forge.submit(row["action"], Operation.REPORT, payload, authorization=effect,
                        plan_digest=digest(plan), dispatch=dispatch, validate=self.final_boundary)
                except (ADPError, OSError):
                    pass
                finally:
                    self._writing = None
            with self.service.bounded():
                observed, comment = self.observed_report(row)
                canonical = self.journal.inspect()["state"]["execution"]
                publication = {"action": row["action"], "body_digest": digest(row["view"]["body"]), "reference": observed.reference}
                if (row["after"] is not None and row["observation"] == data(observed)
                        and canonical["actions"][row["action"]]["status"] == "OBSERVED"
                        and canonical["publications"].get(row["action"]) == publication
                        and self.c.record()["coordination"] is None):
                    self.c.allowed(row["requirement"])
                    return {"status": "REPORTED", "reference": observed.reference, "revision": self.c.revision(),
                        "accounting": "ALREADY_RECONCILED", "runtime_qualification": "NOTRUN"}
                self.journal.change(lambda e, s, t: e["actions"][row["action"]].update(status="OBSERVED", observation=data(observed)))
                # Reconcile only this authenticated own comment addition.
                p = self.personal.plan
                from .personal_enrollment import selection
                observation, owner = selection(Path(p["checkout"]["path"]), p["checkout"]["remote"], self.personal.repository_id, self.read)
                after = next(i for i in observation.snapshot.issues if data(i.identity) == self.c.track.link["identity"])
                raw = self.service.request("GET", self.target.api + "/issues/" + str(p["issue"]))
                require(owner == p["owner"], "Current report account/permission changed")
                own_report_delta(typed(Issue, row["before"]), after, comment, raw)
                row.update(observation=data(observed), comment=comment, after=data(after)); self.save_report(row)
                self.journal.change(lambda e, s, t: e["publications"].update({row["action"]:
                    {"action": row["action"], "body_digest": digest(row["view"]["body"]), "reference": observed.reference}}))
                if self.c.record()["coordination"] is not None:
                    self.c.conclude(typed(Permit, row["reservation"]), "personal:report:" + row["action"])
                return {"status": "REPORTED", "reference": observed.reference, "revision": self.c.revision(), "runtime_qualification": "NOTRUN"}
