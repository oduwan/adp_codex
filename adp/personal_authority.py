"""Explicit local operator consent and authentic runtime/native observations.

These content-addressed private receipts are NOT signatures, providers or
portable delegations. Verification rechecks the underlying typed evidence.
"""
from __future__ import annotations

from dataclasses import replace

from .discovery_schema import digest, typed
from .errors import ADPError
from .guard_types import Attestation, Observation, Permit, Requirement, data
from .personal_storage import LIMIT, create_private, read_private
from .policy import PolicyProvider
from .policy_types import Authorization, Effect, Operation, Plan, Qualifications, SourceClaim
from .schema import encode, fields, require
from .storage import atomic


class PersonalAuthority:
    def __init__(self, coordinator):
        self.c = coordinator
        self.directory = coordinator.personal.state / "evidence"

    def qualify_accounting(self, state, task):
        """Observational capability; no c.live/Guard call or evidence write."""
        if not self.c.episode:
            return False
        from .accounting_policy import entry
        relation, _, subject = self.c.personal._active_view(memory=self.c.memory)
        observed = self.c.memory.inspect()
        from .personal_episode import same_observation
        same_observation(subject, observed)
        require(observed["health"] == "SYNCED" and observed["local_owner"]
                and observed["state"] == state and observed["tasks"].get(task["key"]) == task
                and relation == entry(state) and task["key"] == relation["child_task"]
                and all(identifier == relation["parent_requirement"] or item["mode"] == "normal"
                        for identifier, item in state["progress_guard"]["requirements"].items()), "Accounting qualification subject differs")
        self.c.episode_fence()  # Fresh UTC/revocation after the complete proof.
        return True

    def fence_accounting(self):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        if not self.c.episode:
            return False
        _, _, subject = self.c.personal._active_view(memory=self.c.memory, allow_expired=False, now=self.c.clock())
        observed = self.c.memory.inspect(recovery=True)
        from .personal_episode import same_observation
        same_observation(subject, observed, recovery=True)
        self.c.memory._owner(observed["state"])
        self.c.episode_fence()
        return True

    def _proof(self, purpose, subject, kind, payload, principal):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        self.c.live()
        body = {"schema_version": 1, "purpose": purpose, "subject": subject, "kind": kind,
            "payload": payload, "principal": principal, "approval": self.c.personal.intent["approval"],
            "generation": self.c.memory.inspect()["state"]["generation"],
            "expires_at": self.c.personal.plan["window"]["expires_at"]}
        self._validate(body)
        evidence = Attestation(principal, "personal:" + digest(body), subject)
        create_private(self.directory)
        path = self.directory / (digest(body) + ".json")
        if path.exists():
            require(read_private(path) == body, "Immutable personal evidence conflicts")
        else:
            atomic(path, encode(body, LIMIT), replace=False)
        return evidence

    def verify(self, evidence, *, purpose, subject):
        try:
            self.c.live()
            require(type(evidence) is Attestation and evidence.reference.startswith("personal:"), "Expected local personal evidence")
            reference = evidence.reference.removeprefix("personal:")
            require(len(reference) == 64 and all(c in "0123456789abcdef" for c in reference), "Unsafe evidence reference")
            body = read_private(self.directory / (reference + ".json"))
            require(digest(body) == reference and evidence == Attestation(body["principal"], "personal:" + reference, body["subject"])
                    and body["purpose"] == purpose and body["subject"] == subject, "Evidence purpose or subject differs")
            self._validate(body)
            return True
        except (ADPError, OSError, KeyError, ValueError, TypeError):
            return False

    def _validate(self, body):
        fields(body, "schema_version purpose subject kind payload principal approval generation expires_at")
        require(body["schema_version"] == 1 and body["approval"] == self.c.personal.intent["approval"]
                and body["generation"] == self.c.memory.inspect()["state"]["generation"]
                and self.c.clock() < body["expires_at"] == self.c.personal.plan["window"]["expires_at"],
                "Personal authority expired or ownership changed")
        kind, payload, purpose, subject = (body[name] for name in ("kind", "payload", "purpose", "subject"))
        if kind == "admission":
            spec = typed(Requirement, payload["requirement"])
            require(purpose == "admission" and payload["task_id"] == self.c.task_id
                    and spec in tuple(self.c.specification(p) for p in ("original", "candidate", "develop", "feature"))
                    and subject == self.c.guard.admission_subject(self.c.task_id, spec)
                    and body["principal"] == "personal:operator", "Unapproved personal requirement")
        elif kind == "source":
            claim = typed(SourceClaim, payload["claim"])
            self.c.original_approval()
            from .policy_types import RepositorySnapshot, SourceKind
            snapshot = typed(RepositorySnapshot, payload["snapshot"])
            if claim.kind == SourceKind.OPERATOR:
                require(claim.reference == "personal:exact-local-choices" and claim.document_digest == digest(self.c.personal.plan),
                        "Operator source differs from the exact local choices")
            else:
                require(any(d.reference == claim.reference and d.kind == claim.kind and d.digest == claim.document_digest
                            for d in snapshot.documents), "Governance interpretation differs from actual committed bytes")
            require(purpose == "policy/" + claim.kind.lower() and claim.rules == self.c.rules()
                    and claim.evidence is None and claim.expires_at == body["expires_at"]
                    and claim.document_digest == payload["digest"]
                    and subject == self.c.source_subject(claim, typed_snapshot=payload["snapshot"]),
                    "Unverified personal policy interpretation")
        elif kind == "operation":
            plan = typed(Plan, payload["plan"])
            require(purpose == "policy/operation" and subject == PolicyProvider.authorization_subject(plan, Qualifications()),
                    "Operation evidence differs from the exact plan")
            self.c.validate_operation(plan)
        elif kind == "progress":
            row = self.c.worker(payload["request_id"])
            self.c.workers.actual(row, approval=True)
            measured = typed(Observation, payload["observation"])
            _, _, item = self.c.guard._snapshot(self.c.task_id, row["requirement"])
            if item["active"] is not None and item["active"]["id"] == row["permit"]["token"]:
                require(subject == self.c.guard.progress_subject(self.c.task_id, row["requirement"], typed(Permit, row["permit"]), measured),
                        "Independent progress subject differs from its active baseline")
            else:
                require((item["last"] is not None and item["last"]["context"] == row["guard_context"]
                         and item["last"]["observation"] == payload["observation"])
                        or (row["purpose"] == "code" and item["approval"] is not None
                            and item["approval"]["context"] == row["guard_context"] and item["approval"]["subject"] == subject),
                        "Independent progress is not present in canonical M2 state")
            require(purpose == "progress" and body["principal"] == "worker:" + row["request"]["id"]
                    and measured.evidence == (row["observation"]["receipt"],) and measured.progress is not None,
                    "Independent progress differs from its actual reservation")
            from .guard_types import ProgressKind
            expected = ProgressKind.CORRECTION_APPROVED if row["purpose"] == "code" else ProgressKind.REQUIREMENT_VERIFIED
            require(measured.progress.kind == expected and measured.progress.evidence == measured.evidence
                    and measured.progress.fact == ("exact-code-reviewed" if row["purpose"] == "code" else row["purpose"]),
                    "Worker purpose cannot establish another kind of progress")
        elif kind == "check-policy":
            from .project_validation import policy_subject
            from .project_validation_types import EvidencePolicy
            policy = typed(EvidencePolicy, payload["policy"])
            plan = typed(Plan, payload["plan"])
            require(purpose == "project-validation/policy" and policy.evidence is None
                    and policy.checks == self.c.checks() and subject == policy_subject(plan, policy)
                    and plan.request.operation == Operation.VALIDATE, "Native check policy differs from approved names/origins")
        elif kind == "native-checks":
            from .project_validation import observation_subject
            from .project_validation_types import ObservationQuery, ProjectObservation
            query, observed = typed(ObservationQuery, payload["query"]), typed(ProjectObservation, payload["observation"])
            require(purpose == "project-validation/observation" and observed.evidence is None
                    and query.request.repository_id == self.c.personal.repository_id
                    and query.request.revision == self.c.revision() and subject == observation_subject(query, observed)
                    and 0 <= self.c.clock() - observed.observed_at <= 300,
                    "Native check observation is stale or for another source")
        else:
            raise ADPError("Unsupported personal evidence kind")

    def operator_evidence(self, purpose, subject, context):
        require(purpose == "admission", "No blanket personal operator attestation")
        return self._proof(purpose, subject, "admission", context, "personal:operator")

    def source(self, provider, claim, snapshot):
        return replace(claim, evidence=self._proof("policy/" + claim.kind.lower(), provider.source_subject(claim, snapshot),
            "source", {"claim": data(claim), "snapshot": data(snapshot), "digest": claim.document_digest}, "personal:operator"))

    def authorize(self, plan):
        self.c.validate_operation(plan)
        return Authorization(self._proof("policy/operation", PolicyProvider.authorization_subject(plan),
            "operation", {"plan": data(plan)}, "personal:operator"))

    def worker_progress(self, row, observation):
        subject = self.c.guard.progress_subject(self.c.task_id, row["requirement"], typed(Permit, row["permit"]), observation)
        return self._proof("progress", subject, "progress", {"request_id": row["request"]["id"], "observation": data(observation)},
                           "worker:" + row["request"]["id"])

    def check_policy(self, plan, policy):
        from .project_validation import policy_subject
        return replace(policy, evidence=self._proof("project-validation/policy", policy_subject(plan, policy),
            "check-policy", {"plan": data(plan), "policy": data(policy)}, "personal:operator"))

    def native_observation(self, query, observation):
        """Installed native adapter callback only; never a worker-reported PASS."""
        from .project_validation import observation_subject
        return self._proof("project-validation/observation", observation_subject(query, observation), "native-checks",
            {"query": data(query), "observation": data(observation)}, "personal:native-github")
