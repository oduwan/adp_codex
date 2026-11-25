"""One separately approved personal feature publication through accepted M7.

This does not create PRs, accept products, merge, report or admit another issue.
It uses real canonical M5 actions, M1 ownership, M2 and the original GitHub CAS.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
import secrets

from .config import Config
from .discovery_github import GitHubDiscoveryAdapter
from .discovery_schema import digest, typed
from .errors import ADPError
from .enrollment import local_checkout
from .execution_memory import ExecutionJournal, invocation_lock
from .execution_policy import ReservedSafety
from .guard import ProgressGuard
from .guard_types import Action, ActionKind, Attestation, DecisionKind, Observation, Outcome, Permit, Requirement, data
from .network_git import GitHubCAS, GitHubGitExecutionPort, GitHubPolicyAdapter, GitHubTarget
from .personal_git import administration
from .personal_enrollment import governance
from .personal_github import owned_repository
from .personal_network import PersonalDiscoveryRead, PersonalGitHubTransport
from .personal_storage import LIMIT, PersonalBlocked, create_private, read_private
from .policy import PolicyProvider
from .policy_types import Authorization, Effect, Operation, Permission, Plan, Protection, Qualifications, RepositorySnapshot, Request, Rules, SourceClaim, SourceKind, Task
from .schema import encode, fields, key, require
from .storage import atomic
from .runtime_limits import bind_consent, consent_limits, measured, network_operation
from .github_rules import PLAN_ASSENT
from .personal_rules import enrollment_rules

WARRANT = "No repository rename, transfer, name reuse or credential-scope changes during this finite publication window."
POLICY_ASSENT = "I reviewed the supplied current project governance: this exact feature publication is permitted and has no unmet or unrepresented prepublication condition."
TOKEN = re.compile(r"publish[12]\.([0-9]{1,12})\.([0-9]{1,12})\.([0-9a-f]{32})\.([0-9a-f]{64})\Z")


class OriginalRead:
    """Transparent receipt digests of the actual selected M4 observations.

    The full successful preflight validates these same responses, not a later
    unrelated baseline. Targeted reobservation still uses M4's complete paging
    and control-header checks. Raw issue/comment bodies are never retained here.
    """
    SUFFIXES = ("comments", "timeline", "dependencies/blocked_by", "sub_issues")

    def __init__(self, transport, base, *, additional=(), expected=None):
        self.transport, self.base, self.observed = transport, base, {}
        self.expected = dict(expected) if expected is not None else None
        self.bases = (base, *additional)
        require(type(additional) is tuple and 1 <= len(self.bases) <= 8
                and len(set(self.bases)) == len(self.bases), "Bounded unique original observations required")

    def get(self, path):
        require(self.expected is None or path in self.expected, "UNKNOWN: original-ticket paging exceeded its approved paths")
        response = self.transport.get(path)
        if any(path == base or any(path.startswith(base + "/" + suffix + "?") for suffix in self.SUFFIXES)
               for base in self.bases):
            require(response.status == 200, "Complete current original-ticket evidence required")
            observed = digest({"body": response.body,
                "pagination": [(k.lower(), v) for k, v in response.headers if k.lower() == "link"]})
            require(self.expected is None or observed == self.expected[path], "UNKNOWN: original-ticket evidence changed")
            require(path not in self.observed or self.observed[path] == observed, "Original-ticket evidence changed during observation")
            self.observed[path] = observed
            require(len(self.observed) <= 81, "Original-ticket evidence exceeds accepted paging bounds")
        return response


class PersonalPublication:
    def qualify_accounting(self, state, task):
        return self.c.authority.qualify_accounting(state, task)

    def fence_accounting(self):
        return self.c.authority.fence_accounting()

    def __init__(self, coordinator, *, transport=None):
        self.c, self.personal = coordinator, coordinator.personal
        self.clock = coordinator.clock
        p = self.personal.plan
        self.target = GitHubTarget(self.personal.repository_id, p["repository"]["node_id"],
            p["repository"]["database_id"], *p["repository"]["name"].split("/"), p["feature"]["branch"])
        self.journal = ExecutionJournal(self.c.memory)
        self.path = self.personal.state / "publication.json"
        self.evidence = self.personal.state / "publication-evidence"
        self._dispatching = False
        self._write_basis = None
        self.c.check_administration(self.c.record())
        self.transport = transport or PersonalGitHubTransport(self.target,
            protected_roots=(self.personal.feature, Path(p["checkout"]["path"]), self.personal.directory, Path(__file__).resolve().parents[1]),
            authorize_write=self.write_authorized)
        self.service = GitHubCAS(self.target, self.transport, personal=True)
        self.service.personal_context = (p["repository"], p["owner"])
        self.service.bind_control(self.c.memory.control)
        self.read = PersonalDiscoveryRead(self.service)
        self.c.transport = self.read
        self.guard = ProgressGuard(self.c.memory, authority=self, clock=self.clock)
        self.specification = Requirement(self.c.task_id, "personal-publication", ("published",))
        self.cfg = Config.discover(self.personal.feature, remote=p["checkout"]["remote"], repository_id=self.personal.repository_id)
        self.port = GitHubGitExecutionPort(self.cfg, self.service, self.journal,
            bound_git_directory=Path(administration(self.personal.feature)["directory"]["path"]))

    def record(self, *, _observed=None):
        row = read_private(self.path, optional=True)
        if row is None:
            require(not any(a["task_key"] == key(self.c.task_id) and a["operation"] == Operation.PUSH
                for a in self.journal.inspect()["state"]["execution"]["actions"].values()),
                "Missing personal publication history cannot authorize a replacement effect")
            return None
        fields(row, "schema_version view approval credential_binding action_id requirement reservation pending_observation")
        require(type(row["schema_version"]) is int and row["schema_version"] in ((1, 2) if self.c.episode else (1,))
                and row["action_id"] == digest({"personal-publication": row["view"]})
                and row["view"]["setup_approval"] == self.personal.intent["approval"]
                and row["view"]["generation"] == (_observed if _observed is not None else self.c.memory.inspect())["state"]["generation"],
                "Publication identity, consent or ownership changed")
        view = row["view"]
        require(view.get("plan_policy") is None or view.get("plan_disabled_rules_assent") == PLAN_ASSENT,
                "Exact personal plan-disabled publication warrant is missing")
        require(view["administrative_quiescence_warrant"] == WARRANT and view["project_policy_assent"] == POLICY_ASSENT
                and view["operation"] == "PUSH" and view["force"] is False
                and row["approval"] == ".".join(("publish" + str(row["schema_version"]), str(view["issued_at"]), str(view["expires_at"]), view["nonce"],
                    digest({"view": view, "private_credential": row["credential_binding"]}))),
                "Retained publication consent was altered")
        return row

    def save(self, row):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        create_private(self.personal.state)
        atomic(self.path, encode(row, LIMIT))

    def admit_task(self, execution, task_key, task):
        existing = execution["tasks"].get(task_key)
        require(existing is None or existing == task, "Canonical publication task differs")
        execution["tasks"][task_key] = task

    def local(self, *, _history_capture=None):
        bases = self.original_bases()
        capture = OriginalRead(self.read, bases[0], additional=bases[1:])
        self.c.transport = capture
        try:
            self.c.fresh(_history_capture=_history_capture) if _history_capture is not None else self.c.fresh()
        finally:
            self.c.transport = self.read
        self.c.workers.fence()
        require(self.c.record()["phase"] == "LOCAL_DRAFT_CODE_REVIEWED" and self.c.record()["coordination"] is None,
                "Finish the actual reviewed local draft and reconcile its original guard work")
        review_binding = self.review_binding()
        self.c.original_approval()
        self.c.verify_local_review()
        require(self.review_binding() == review_binding, "Canonical review evidence changed during genuine verification")
        require(all(base in capture.observed and all(base + "/" + suffix + "?per_page=100&page=1" in capture.observed
            for suffix in capture.SUFFIXES) for base in bases), "Full preflight did not validate all original-ticket observations")
        return capture.observed, review_binding

    def review_binding(self, *, _observed=None):
        """Current canonical evidence sealed by full genuine batch review.

        Recompare per object; this is not a new approval or a substitute for
        runtime verification before and after the whole immutable batch.
        """
        observed = _observed if _observed is not None else self.c.memory.inspect()
        require(observed["health"] == "SYNCED" and observed["local_owner"], "Current review owner is required")
        state, task = observed["state"], observed["tasks"][key(self.c.task_id)]
        row, reviews = self.c.record(), {}
        require(task["source_revision"] == row["revision"], "Canonical reviewed source changed")
        for name, purpose in (("original_review", "original"), ("code_review", "code")):
            worker = self.c.worker(row[name])
            assignment = task["assignments"].get(worker["assignment"]["assignment_id"])
            require(worker["purpose"] == purpose and worker["phase"] == "ACCOUNTED" and assignment is not None
                    and assignment["status"] == "accepted" and assignment["worker"] == "worker:" + row[name]
                    and assignment["generation"] == worker["request"]["generation"] == state["generation"]
                    and assignment["source_revision"] == worker["request"]["revision"]
                    and assignment["result"] == self.c.workers.result(worker), "Canonical independent review assignment changed")
            item = state["progress_guard"]["requirements"][worker["requirement"]]
            require(self.c.guard._decision(worker["requirement"], state, task, item).kind == DecisionKind.ALLOW,
                    "Original or code review guard is no longer allowed")
            if purpose == "code":
                require(item["approval"] is not None and item["approval"]["context"] == self.c.guard._context(state, task),
                        "Current canonical code approval is missing")
            reviews[purpose] = {"assignment": assignment, "guard": item}
        binding = {"reviews": reviews, "revision": task["source_revision"], "iteration": task["iteration"],
            "generation": state["generation"], "epoch": state["progress_guard"]["task_epochs"][task["key"]]}
        if self.c.episode:
            # This seals provenance only. Full live original/code approval is
            # checked at the batch boundaries; do not recursively reauthorize
            # it inside every per-object metadata projection.
            binding["source_origin"] = self.c.source_origin(historical=True)
        return digest(binding)

    def original_bases(self):
        primary = self.target.api + "/issues/" + str(self.personal.plan["issue"])
        # The accepted metadata-only helper needs no execution coordinator.
        # A constructed coordinator still must explicitly expose its track.
        if not hasattr(self, "c") or self.c.track is None:
            return (primary,)
        return (primary, *(self.target.api + "/issues/" + str(number)
            for number in sorted(o.issue.number for o in self.c.track.originals.values())
            if number != self.personal.plan["issue"]))

    def current_original(self, *, expected=None):
        bases = self.original_bases()
        capture = OriginalRead(self.read, bases[0], additional=bases[1:], expected=expected)
        observer = GitHubDiscoveryAdapter(self.personal.plan["repository"]["name"], capture,
            max_requests=self.service.limits.request_limit, clock=self.clock)
        observer._halt, observer._requests, observer._coverage_items, observer._now = False, 0, [], self.clock()
        for index, base in enumerate(bases):
            observer._one(base, "original-before:" + str(index))
            for suffix in capture.SUFFIXES:
                observer._pages(base + "/" + suffix, "original-" + str(index) + ":" + suffix)
            observer._one(base, "original-after:" + str(index))
        require(all(item.status == "COMPLETE" for item in observer._coverage_items),
                "Original-ticket pagination, permissions or stability is unverified")
        return capture.observed

    def remote(self):
        p = self.personal.plan
        owner = owned_repository(self.read, p["repository"]["name"], self.personal.repository_id)
        observer = GitHubDiscoveryAdapter(p["repository"]["name"], self.read, max_requests=1)
        observer._halt, observer._requests = False, 0
        response = observer._get(self.target.api)
        require(response.status == 200 and type(response.body) is dict, "Current repository metadata unavailable")
        repo = response.body
        require(owner == p["owner"] and owner["push_access"] is True
                and repo.get("node_id") == self.target.node_id
                and repo.get("default_branch") == p["repository"]["default_branch"]
                and self.target.branch != repo["default_branch"], "Current owner, permission, identity or default branch differs")
        try:
            retained = self.record()
            self.service.personal_policy_binding = ((retained["view"].get("plan_policy"),) if retained is not None else None)
            bounded = self.c.episode and retained is not None and retained["schema_version"] == 2
            return self.service.inspect_ref(writable=True, **({"_bounded_personal": True} if bounded else {}))
        except (ADPError, OSError):
            raise PersonalBlocked("FEATURE_POLICY_UNVERIFIED",
                "Verify current owner/admin access, exact feature ref and protections. A private plan-disabled fallback requires supported unprotected branch evidence, exact classic-plan evidence and separate operation assent. Other unknown or constrained refs remain blocked; never retry an uncertain write.") from None

    @network_operation("publication.proposed")
    def proposed(self, approved=None):
        now = self.clock()
        if approved is None:
            issued, expires, nonce = now, min(now + 300, self.personal.plan["window"]["expires_at"]), secrets.token_hex(16)
        else:
            match = TOKEN.fullmatch(approved or "")
            require(match is not None, "Use the separate exact publication approval")
            issued, expires, nonce = int(match[1]), int(match[2]), match[3]
        require(0 <= issued <= now < expires and 0 < expires - issued <= 300
                and expires <= self.personal.plan["window"]["expires_at"], "Original publication window is expired or invalid")
        bind_consent({"runtime_limits": self.service.limits.values(), "expires_at": expires}, now)
        with self.service.bounded():
            capture = {} if self.c.episode else None
            original_observation, review_binding = self.local(_history_capture=capture) if capture is not None else self.local()
            old = self.remote()
            if old is not None:
                require(self.port._value("--no-replace-objects", "merge-base", old, self.c.revision()) == old,
                        "Unknown or non-fast-forward feature ancestry; no fetch/force fallback")
            state = self.c.memory.inspect()
            row = self.c.record()
            review = self.c.worker(row["code_review"])
            view = {"mode": "PERSONAL_PUBLICATION", "repository": self.personal.plan["repository"],
                "account_id": self.personal.plan["owner"]["account_id"], "issue": self.personal.plan["issue"],
                "issue_id": self.personal.plan["issue_id"], "original_digest": self.personal.plan["original_digest"],
                "original_observation": original_observation,
                "canonical_review_binding": review_binding,
                "setup_approval": self.personal.intent["approval"], "checkpoint": state["local_head"],
                "generation": state["state"]["generation"], "source_ref": self.target.ref,
                "revision": self.c.revision(), "tree": self.port._value("rev-parse", "HEAD^{tree}"),
                "expected_old": old, "absence": "VERIFIED" if old is None else "NOT_APPLICABLE",
                "review_request": row["code_review"], "review_receipt_digest": digest(review["observation"]["receipt"]),
                "worker_inventory": digest(self.c.workers.records()), "administration": digest(administration(self.personal.feature)),
                "governance": self.personal.plan["governance"], "governance_digest": self.personal.plan["governance_digest"],
                "project_check_dispositions": row["gates"], "project_policy_assent": POLICY_ASSENT,
                "credential_source": "STORED_GH_GITHUB_COM_NORMAL_OPERATOR", "credential_confinement": "OPERATOR_QUIESCENCE_ASSUMPTION",
                "credential_provenance": self.transport.credential_provenance,
                "administrative_quiescence_warrant": WARRANT, "operation": "PUSH", "force": False,
                "dispatch_seconds": self.service.limits.operation_timeout_seconds,
                "maximum_requests": self.service.limits.request_limit,
                "runtime_limits": self.service.limits.values(), "issued_at": issued, "expires_at": expires,
                "nonce": nonce, "product_acceptance": "NOT_ACCEPTED", "other_external_rights": "NOT_DELEGATED"}
            if self.service.personal_policy is not None:
                view.update(plan_policy=self.service.personal_policy, plan_disabled_rules_assent=PLAN_ASSENT)
            if capture is not None:
                from .personal_episode import same_observation
                from .personal_history import _reader_binding
                same_observation(capture["subject"], state)
                view.update(_reader_binding(capture))
            binding = self.transport.credential_binding
            token = ".".join(("publish2" if self.c.episode else "publish1", str(issued), str(expires), nonce, digest({"view": view, "private_credential": binding})))
            require(self.clock() < expires, "Publication window expired during observations")
            return view, token, binding

    @network_operation("publication.preview")
    def preview(self):
        if self.record() is not None:
            return {"status": "PUBLICATION_INTENT_EXISTS", "result": self.status(), "approval": None}
        view, token, _ = self.proposed()
        return {"status": "PUBLICATION_PROPOSED", "result": view, "approval": token}

    @measured("publication.live")
    def live(self, *, review=True, _capture=None):
        from .personal_read_frame import forbid_writes, publication_live
        if not review:
            forbid_writes()  # The per-object mutation fence is never framed.
        elif self.c.episode:
            return publication_live(self, _capture=_capture)
        return self._live_current(review=review)

    def _live_current(self, *, review=True):
        # One actual fresh observation per call, never retained across objects
        # or callbacks. c.live performs its full current M1/consent checks;
        # generation and review seals refer to that same observed checkpoint.
        capture = {} if self.c.episode else None
        observed = self.c.live(_history_capture=capture) if capture is not None else self.c.live()
        row = self.record(_observed=observed)
        require(row is not None, "Exact publication consent is missing")
        view = row["view"]
        if capture is not None:
            from .personal_history import _reader_binding
            require(row["schema_version"] == 2 and all(view.get(k) == v for k, v in _reader_binding(capture).items()),
                    "Legacy or changed accounting writer; observe original effect only")
        bind_consent(view, self.clock())
        require(view["issued_at"] <= self.clock() < view["expires_at"]
                and self.port._value("rev-parse", "HEAD") == view["revision"]
                and self.port._value("--no-replace-objects", "rev-parse", "HEAD^{tree}") == view["tree"]
                and self.port._value("symbolic-ref", "HEAD") == view["source_ref"]
                and not self.port._value("status", "--porcelain", "--untracked-files=all")
                and digest(administration(self.personal.feature)) == view["administration"]
                and digest(self.c.workers.records()) == view["worker_inventory"]
                and self.review_binding(_observed=observed) == view["canonical_review_binding"]
                and self.transport.credential_binding == row["credential_binding"], "Publication source, review, credential or finite consent changed")
        if review:
            self.c.verify_local_review()
        return row

    @measured("publication.write_authorized")
    def write_authorized(self):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        if self.c.episode:
            from .personal_read_frame import _identity, _inputs, _legacy_inputs
            from .personal_history_git import object_inventory, storage_context
            from .personal_episode import same_observation
            basis = self._write_basis
            require(self._dispatching and basis is not None and _identity(self.c) == basis["identity"]
                    and basis["service"] is self.service and basis["transport"] is self.transport
                    and self.service.target == self.target == basis["target"] and self.port.service is self.service,
                    "Exact invocation-local publication subject required")
            # Every operand is read now. No live/history/Guard/journal callback
            # or network request is hidden in these bounded input readers.
            require((*_inputs(self, basis["subject"], product=False), _legacy_inputs(self.c, basis["archive"][0])) == basis["inputs"],
                    "Current source, private evidence or credential changed")
            for remote, context, objects in basis["historical_objects"]:
                require(storage_context(self.c.memory, remote=remote) == context
                        and object_inventory(self.c.memory, [o[0] for o in objects], remote=remote) == objects
                        and storage_context(self.c.memory, remote=remote) == context,
                        "Actual historical object binding changed")
            observed = self.c.memory.inspect()  # One late actual canonical observation.
            same_observation(basis["subject"], observed)
            row = basis["inputs"][1]
            task = observed["tasks"][key(self.c.task_id)]
            item = self.guard._get(observed["state"], task, row["requirement"])
            permit = typed(Permit, row["reservation"]["permit"])
            active = self.guard._active(observed["state"], task, item, permit.token)
            action = observed["state"]["execution"]["actions"].get(row["action_id"])
            require(action is not None and action["status"] == "SUBMITTED" and action["operation"] == Operation.PUSH
                    and permit.decision.baseline.requirement_id == row["requirement"]
                    and active["context"] == row["reservation"]["context"] and active["action"] == row["reservation"]["action"]
                    and item["mode"] in ("normal", "running") and active["started"] <= self.guard._now() < active["deadline"]
                    and read_private(self.port._claim_path(row["action_id"])) == self.port._claim(row["action_id"], action),
                    "Current submitted intent, claim or original M2 reservation changed")
            # _request already owns this exact hazard; _check_stop here would
            # reject its own in-flight marker. Never remove or relabel it.
            require(self.service._live_unknown is True and read_private(self.service._hazard_path()) ==
                    {"status": "IN_FLIGHT_OR_UNKNOWN", "repository": self.target.node_id}, "Current request stop boundary changed")
            budget = self.service._budget.get()
            require(budget is basis["budget"] and budget.end <= basis["caps"][0]
                    and budget.request_seconds <= basis["caps"][1] and budget.maximum_calls <= basis["caps"][2],
                    "Original request/operation budget changed")
            self.c.episode_fence()
            now = self.guard._now()
            require(active["started"] <= now < active["deadline"] and row["view"]["issued_at"] <= now < row["view"]["expires_at"]
                    and self.transport.credential_binding == row["credential_binding"], "Publication consent or credential expired")
            budget.check()
            return True
        # Full genuine review is performed at both batch boundaries. Recheck
        # its sealed canonical assignments/approvals and every current source,
        # owner, credential and guard binding for each exact immutable object.
        row = self.live(review=False)
        require(self._dispatching and row["requirement"] is not None and row["reservation"] is not None,
                "Only the fresh one-use publication dispatch can mutate")
        _, _, item = self.guard._snapshot(self.c.task_id, row["requirement"])
        action = self.journal.inspect()["state"]["execution"]["actions"].get(row["action_id"])
        require(item["active"] is not None and item["active"]["id"] == row["reservation"]["permit"]["token"]
                and self.clock() < item["active"]["deadline"] and action is not None and action["status"] == "SUBMITTED",
                "Current M2 reservation and canonical SUBMITTED intent required")
        return True

    def validate_dispatch(self):
        capture = {} if self.c.episode and self._dispatching else None
        self.live(_capture=capture) if capture is not None else self.live()
        self.c.workers.fence()
        self.c.original_approval()
        p = self.personal.plan
        expected_checkout = dict(p["checkout"])
        if not p["feature"]["prepare"]:
            expected_checkout["head"] = self.c.revision()
        require(local_checkout(Path(p["checkout"]["path"]), p["checkout"]["remote"]) == expected_checkout
                and digest(governance(Path(p["checkout"]["path"]))) == p["governance_digest"]
                and digest(governance(self.personal.feature)) == p["governance_digest"],
                "Original source or governance changed")
        prerequisites = None
        if self.c.track is None:
            require(not p["native_prerequisites"], "Native prerequisites need independent acceptance before publication")
        else:
            # Full current M4 admission/preflight is bound into the approved raw
            # maps for EVERY selected original. Reobserve those exact maps below
            # and the actual prerequisite receipts here, without another whole
            # repository inventory inside the unchanged CAS request budget.
            prerequisites = self.c.track.publication_prerequisites()
        expected_original = self.record()["view"]["original_observation"]
        require((self.current_original(expected=expected_original) if capture is not None else self.current_original())
                == expected_original, "Original-ticket scope or native evidence changed")
        require([enrollment_rules(self.read, p["repository"], p["owner"], item["ref"].removeprefix("refs/heads/"),
                    **({"expected": item} if capture is not None else {}))
                for item in p["branch_rules"]] == p["branch_rules"], "Original branch requirements changed")
        require(self.remote() == self.record()["view"]["expected_old"], "Remote authority or exact ref changed before CAS")
        if capture is not None:
            from .personal_read_frame import _inputs, _legacy_inputs
            from .personal_episode import same_observation
            require((*_inputs(self, capture["subject"], product=False), _legacy_inputs(self.c, capture["archive"][0])) == capture["inputs"],
                    "Publication subject changed after closing proof")
            actual = self.c.memory.inspect()
            same_observation(capture["subject"], actual)
            if self._write_basis is not None:
                same_observation(self._write_basis["subject"], actual)
                require(capture["inputs"] == self._write_basis["inputs"]
                        and capture["identity"] == self._write_basis["identity"]
                        and capture["historical_objects"] == self._write_basis["historical_objects"],
                        "Post-upload validation cannot adopt changed inputs")
            else:
                budget = self.service._budget.get()
                require(budget is not None, "Original publication budget required")
                capture.update(subject=actual, service=self.service, transport=self.transport, target=self.target,
                    budget=budget, caps=(budget.end, budget.request_seconds, budget.maximum_calls), prerequisites=prerequisites)
                self._write_basis = capture

    @measured("publication.count_admission")
    def admit_objects(self, objects, budget, adapter):
        """Negative-only count envelope over the already completed closure."""
        basis = self._write_basis
        require(basis is not None and budget is basis["budget"], "Original qualified dispatch budget required")
        budget.check()
        remaining, count = budget.maximum_calls - budget.calls, len(objects)
        if count + 1 > remaining:
            raise PersonalBlocked("PUBLICATION_REQUEST_COUNT_INSUFFICIENT", "Object POSTs plus CAS exceed the original remaining budget; no upload started.")
        from .personal_authority import PersonalAuthority
        from .personal_episode import EpisodeState
        from .personal_runner import PersonalCoordinator
        from .personal_track import PersonalTrack
        from .personal_workers import PersonalWorkers
        from .codex_runtime import CodexExecRuntime
        track, p = self.c.track, self.personal
        row = basis["inputs"][1]
        refs = getattr(adapter, "_publication_expected_refs", None)
        links = [name for name in basis["inputs"][2] if track is not None and Path(name).parent == track.root / "links"]
        local_only = (type(self) is PersonalPublication and type(self.c) is PersonalCoordinator
            and type(p) is EpisodeState and type(track) is PersonalTrack
            and type(self.c.authority) is PersonalAuthority and type(self.c.workers) is PersonalWorkers
            and type(self.c.runtime) is CodexExecRuntime
            and p.plan["issue"] == 1 and not p.plan["native_prerequisites"] and basis["prerequisites"] == ()
            and track.index["first"] == str(p.root.directory) and track.link["parent"] is None
            and track.link["identity"] == p.root.intent["original"]["identity"]
            and links == [str(track.root / "links" / (digest(track.link["identity"]) + ".json"))]
            and getattr(self.c, "product", None) is None)
        modes = {"OBSERVED": 2, "PLAN_UNAVAILABLE": 5}
        tail = None
        if local_only and refs is not None and all(r["rules"] in modes for r in p.plan["branch_rules"]):
            graph = sum(max(1, sum(r.name.startswith(prefix) for r in refs)) for prefix in ("refs/heads/", "refs/tags/"))
            remote, inspect = (6, 3) if row["view"].get("plan_policy") is None else (11, 8)
            tail = (graph + len(row["view"]["original_observation"]) + len(self.original_bases())
                + sum(modes[r["rules"]] for r in p.plan["branch_rules"]) + remote * 2 + inspect + 2)
        if tail is None or count + tail > remaining:
            raise PersonalBlocked("PUBLICATION_REQUEST_COUNT_UNKNOWN", "The complete remaining read/CAS/settlement envelope is unproved within the original budget; no upload started.")
        return "COUNT_FEASIBLE"  # Never an authorization or wall-time guarantee.

    def rules(self):
        return Rules(permissions=(Permission(Operation.PUSH, Effect.ALLOW),), reviews=1,
                     branch_template=self.c.rules().branch_template,
                     checks=tuple(self.personal.plan["required_check_names"]))

    def proof(self, purpose, subject, kind, payload):
        from .personal_read_frame import forbid_writes
        forbid_writes()
        row = self.live()
        body = {"purpose": purpose, "subject": subject, "kind": kind, "payload": payload,
            "principal": "personal:operator", "approval": row["approval"], "generation": row["view"]["generation"]}
        self.validate_proof(body)
        create_private(self.evidence)
        identity = digest(body)
        path = self.evidence / (identity + ".json")
        if path.exists():
            require(read_private(path) == body, "Publication proof conflicts")
        else:
            require(len(list(self.evidence.glob("*.json"))) < 256, "Publication evidence bound exhausted")
            atomic(path, encode(body, LIMIT), replace=False)
        return Attestation("personal:operator", "personal-publication:" + identity, subject)

    def verify(self, evidence, *, purpose, subject):
        try:
            self.live()
            require(type(evidence) is Attestation and evidence.reference.startswith("personal-publication:"), "Unqualified publication proof")
            identity = evidence.reference.removeprefix("personal-publication:")
            require(re.fullmatch("[0-9a-f]{64}", identity) is not None, "Unsafe proof reference")
            body = read_private(self.evidence / (identity + ".json"))
            require(digest(body) == identity and body["purpose"] == purpose and body["subject"] == subject
                    and evidence == Attestation(body["principal"], "personal-publication:" + identity, subject), "Publication proof identity differs")
            self.validate_proof(body)
            return True
        except (ADPError, OSError, KeyError, ValueError, TypeError):
            return False

    def validate_proof(self, body):
        fields(body, "purpose subject kind payload principal approval generation")
        row = self.record()
        require(body["approval"] == row["approval"] and body["generation"] == row["view"]["generation"], "Publication proof belongs to another consent")
        purpose, subject, payload = body["purpose"], body["subject"], body["payload"]
        kind = body["kind"]
        if kind == "admission":
            require(purpose == "admission" and payload == data(self.specification)
                    and subject == self.guard.admission_subject(self.c.task_id, self.specification), "Unapproved publication requirement")
        elif kind == "source":
            source = typed(SourceClaim, payload["source"])
            snapshot = typed(RepositorySnapshot, payload["snapshot"])
            require(source.evidence is None and source.rules == self.rules()
                    and purpose == "policy/" + source.kind.lower()
                    and subject == PolicyProvider(None).source_subject(source, snapshot)
                    and (source.kind == SourceKind.OPERATOR and source.reference == "personal:exact-publication-policy"
                         and source.document_digest == digest(row["view"])
                         or source.kind == SourceKind.GOVERNANCE and any(d.reference == source.reference and d.digest == source.document_digest for d in snapshot.documents)),
                    "Publication policy does not match actual governance and exact operator assent")
        elif kind == "protection":
            protection = typed(Protection, payload["protection"])
            snapshot = typed(RepositorySnapshot, payload["snapshot"])
            require(purpose == "policy/protection" and protection.evidence is None
                    and protection.ref == self.target.ref and protection.revision == row["view"]["expected_old"]
                    and protection.known and protection.push_allowed and not protection.merge_allowed
                    and not protection.checks and not protection.unsupported
                    and subject == PolicyProvider(None).protection_subject(protection, snapshot), "Unqualified native feature protection")
        elif kind == "operation":
            plan = typed(Plan, payload)
            require(purpose == "policy/operation" and subject == PolicyProvider.authorization_subject(plan, Qualifications())
                    and plan.policy_effect == Effect.ALLOW and plan.request.operation == Operation.PUSH
                    and plan.task.repository_id == self.personal.repository_id and plan.task.task_id == self.c.task_id
                    and plan.task.revision == row["view"]["revision"] and plan.task.source_ref == self.target.ref
                    and plan.target_ref == self.target.ref and plan.expected_target == row["view"]["expected_old"], "Publication operation differs from exact consent")
        else:
            raise ADPError("Unsupported publication proof")
        require(body["principal"] == "personal:operator", "Unqualified publication principal")

    def initialize(self):
        row = self.live()
        task_key = key(self.c.task_id)
        state = self.c.memory.inspect()
        task = {"task_id": self.c.task_id, "identity": {"repository_id": self.personal.repository_id,
            "issue_id": self.personal.plan["issue_id"], "forge": "github"}, "workspace_key": digest(row["view"]["administration"]),
            "admission": digest({"original": self.personal.plan["original_digest"], "scope_review": self.c.record()["original_review"]}),
            "issue_digest": self.personal.plan["original_digest"], "revision": row["view"]["revision"], "source_ref": self.target.ref,
            "product_iteration": state["tasks"][task_key]["iteration"], "kind": "PRODUCT", "stage": "PUBLISH", "jobs": {}, "review": None}
        # Genuine personal worker evidence stays in its original ledger/M1
        # assignments. Never synthesize canonical M5 Reviewer/check jobs.
        def admit(execution, state, tasks):
            self.admit_task(execution, task_key, task)
        self.journal.change(admit)
        proof = self.proof("admission", self.guard.admission_subject(self.c.task_id, self.specification), "admission", data(self.specification))
        requirement = self.guard.register(self.c.task_id, self.specification, proof)
        row = self.record()
        require(row["requirement"] in (None, requirement), "Publication guard requirement changed")
        row["requirement"] = requirement
        self.save(row)
        state, task, item = self.guard._snapshot(self.c.task_id, requirement)
        if row["reservation"] is None:
            action = Action("personal:coordinator", ActionKind.CHECK, "Publish the exact independently reviewed feature", "Exact authenticated ref observed", seconds=min(consent_limits(row["view"]).operation_timeout_seconds, row["view"]["expires_at"] - self.clock()))
            row["reservation"] = {"context": self.guard._context(state, task), "sequence": item["sequence"], "action": data(action), "permit": None}
            self.save(row)
        reservation = row["reservation"]
        if reservation["permit"] is None:
            if item["active"] is not None:
                require(item["active"]["context"] == reservation["context"] and item["active"]["action"] == reservation["action"], "Unrelated publication guard reservation")
                permit = Permit(item["active"]["id"], self.guard.inspect(self.c.task_id, requirement))
            else:
                require(item["sequence"] == reservation["sequence"], "Publication guard history advanced")
                permit = self.guard.begin(self.c.task_id, requirement, typed(Action, reservation["action"]))
            row["reservation"]["permit"] = data(permit)
            self.save(row)
        return typed(Permit, self.record()["reservation"]["permit"])

    @measured("publication.provider")
    def provider(self, permit):
        row = self.live()
        old = self.remote()
        require(old == row["view"]["expected_old"], "Expected feature ref changed")
        adapter = GitHubPolicyAdapter(self.cfg, self.service, governance=tuple(d["path"] for d in self.personal.intent["governance"]))
        provider = PolicyProvider(adapter, authority=self, safety=ReservedSafety(self.guard, permit), clock=self.clock)
        snapshot = adapter.inspect()
        issued, expires = row["view"]["issued_at"], row["view"]["expires_at"]
        claims = [SourceClaim(SourceKind.OPERATOR, "personal:exact-publication-policy", digest(row["view"]), self.rules(), issued, expires)]
        claims += [SourceClaim(d.kind, d.reference, d.digest, self.rules(), issued, expires) for d in snapshot.documents]
        provider.sources = tuple(replace(source, evidence=self.proof("policy/" + source.kind.lower(), provider.source_subject(source, snapshot),
            "source", {"source": data(source), "snapshot": data(snapshot)})) for source in claims)
        reference = "personal:operator-plan-disabled-feature-policy" if row["view"].get("plan_policy") is not None else "personal:native-feature-policy"
        protection = Protection(self.target.ref, old, True, True, False, (), 1, (), (), reference, self.clock(), expires)
        provider.protections = (replace(protection, evidence=self.proof("policy/protection", provider.protection_subject(protection, snapshot),
            "protection", {"protection": data(protection), "snapshot": data(snapshot)})),)
        # These Task fields describe one canonical observation. Later policy
        # and dispatch fences still make their own independent observations.
        observed = self.c.memory.inspect()
        state = observed["state"]
        task = Task(self.personal.repository_id, self.c.task_id, self.target.branch.split("/")[-1], row["view"]["revision"], self.target.ref,
            row["requirement"], state["generation"], state["progress_guard"]["task_epochs"][key(self.c.task_id)],
            observed["tasks"][key(self.c.task_id)]["iteration"], self.c.source_authors())
        plan = provider.plan(task, Request(Operation.PUSH))
        if self.c.episode:
            require(digest(snapshot) == plan.snapshot_digest, "UNKNOWN: actual publication snapshot changed")
            adapter._publication_expected_refs = tuple(snapshot.remote_refs)
        authorization = Authorization(self.proof("policy/operation", PolicyProvider.authorization_subject(plan), "operation", data(plan)))
        require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Actual M3 refused publication")
        return provider, plan, authorization

    @measured("publication.reauthorize")
    def reauthorize(self, provider, plan):
        current = provider.plan(plan.task, plan.request)
        require(replace(current, safety=plan.safety) == plan, "Publication policy, repository, source or exact payload changed after reservation")
        authorization = Authorization(self.proof("policy/operation", PolicyProvider.authorization_subject(current), "operation", data(current)))
        require(provider.decide(current, authorization).effect == Effect.ALLOW, "Current checkpoint-bound M3 refused publication")
        return current, authorization

    def settle(self, observation):
        require(not self._dispatching, "Settlement cannot carry a mutation capability")
        row = self.live()
        require(self.remote() == row["view"]["revision"], "Current repository or branch role changed after publication")
        require(observation.status == "PRESENT" and observation.revision == row["view"]["revision"] and not self.service.unconfirmed_contexts(),
                "Publication outcome is uncertain; never retry the write")
        self.journal.change(lambda execution, state, tasks: execution["actions"][row["action_id"]].update(status="OBSERVED", observation=data(observation)))
        permit = typed(Permit, row["reservation"]["permit"])
        _, _, item = self.guard._snapshot(self.c.task_id, row["requirement"])
        if row["pending_observation"] is None:
            reference = "personal:published:" + row["action_id"]
            # Native ref presence is an observed effect, not a new independent
            # review of that effect. Keep every M2 criterion unresolved.
            measured = Observation(Outcome.PASS, (reference,), tuple(item["unresolved"]))
            row["pending_observation"] = data(measured)
            self.save(row)
        measured = typed(Observation, row["pending_observation"])
        if item["active"] is not None:
            decision = self.guard.observe(self.c.task_id, row["requirement"], permit, measured)
        else:
            require(item["last"] is not None and item["last"]["observation"] == row["pending_observation"], "Original publication accounting missing")
            decision = self.guard.inspect(self.c.task_id, row["requirement"])
        return {"status": "PUBLISHED_UNACCEPTED" if decision.kind == DecisionKind.ALLOW else "PUBLISHED_GUARD_STOPPED",
            "progress_guard": decision.kind, "independent_publication_progress": "NOT_CLAIMED", "repository_id": self.personal.repository_id,
            "ref": self.target.ref, "revision": observation.revision, "product_acceptance": "NOT_ACCEPTED", "other_external_rights": "NOT_DELEGATED"}

    @network_operation("publication.publish")
    def publish(self, *, reviewed, authorized, assume_quiescence, confirm_project_rules, accept_plan_unavailable=False):
        require(authorized is True and assume_quiescence is True and confirm_project_rules is True,
                "Separately confirm the exact publication, project rules and finite quiescence warrant")
        with invocation_lock(self.c.memory.control):
            existing = self.record()
            if existing is None:
                # The operator token seals this entire fresh view and actual
                # credential. A second pre-lock full proposal added no gate.
                view, token, binding = self.proposed(reviewed)
                require(token == reviewed, "Publication changed under invocation lock")
                require("plan_disabled_rules_assent" not in view or accept_plan_unavailable is True,
                        "PLAN_UNAVAILABLE: separately accept this exact publication's plan-disabled rules warrant")
                self.save({"schema_version": 2 if self.c.episode else 1, "view": view, "approval": reviewed, "credential_binding": binding,
                    "action_id": digest({"personal-publication": view}), "requirement": None, "reservation": None, "pending_observation": None})
            else:
                require(reviewed == existing["approval"], "Use the original publication intent; do not renew it")
                bind_consent(existing["view"])
                with self.service.bounded():
                    self.local()
                    self.remote()  # Observe current credentials without granting replay.
                self.live()
            permit = self.initialize()
            row = self.record()
            action = self.journal.inspect()["state"]["execution"]["actions"].get(row["action_id"])
            if action is not None:
                # Recovery is observation only, even PREPARED without a claim.
                with self.service.bounded():
                    return self.settle(self.port.observe(action))
            with self.service.bounded():
                provider, plan, authorization = self.provider(permit)
                action = {"task_key": key(self.c.task_id), "generation": row["view"]["generation"], "operation": Operation.PUSH,
                    "revision": plan.task.revision, "source_ref": plan.task.source_ref, "target": plan.target_ref,
                    "expected_target": plan.expected_target, "payload": data(plan.payload), "status": "PREPARED", "observation": None,
                    "plan_digest": digest(plan)}
                self.journal.change(lambda execution, state, tasks: execution["actions"].update({row["action_id"]: action}))
                dispatch = self.port.prepare_dispatch(row["action_id"], action)
                self.journal.change(lambda execution, state, tasks: execution["actions"][row["action_id"]].update(status="SUBMITTED"))
                plan, authorization = self.reauthorize(provider, plan)
            # The native port shares this outer operation's remaining budget.
            # Internal phases cannot renew it or the original M2 permit.
            self._dispatching = True
            try:
                admission = (lambda objects, budget: self.admit_objects(objects, budget, provider.adapter)) if self.c.episode else None
                result = self.port.submit(action, provider, plan, authorization, dispatch=dispatch, validate=self.validate_dispatch,
                    **({"admit_objects": admission} if admission is not None else {}))
            except OSError:
                result = None  # Observe only after clearing mutation authority.
            finally:
                self._dispatching = False
                self._write_basis = None
            with self.service.bounded():
                if result is None:
                    result = self.port.observe(action)
                return self.settle(result)

    @network_operation("publication.status")
    def status(self):
        row = self.record()
        if row is None:
            return {"status": "NOT_DELEGATED", "product_acceptance": "NOT_ACCEPTED"}
        bind_consent(row["view"])
        action = self.journal.inspect()["state"]["execution"]["actions"].get(row["action_id"])
        with self.service.bounded():
            self.c.check_administration(self.c.record())
            self.c.verify_local_review()
            self.remote()
            observation = self.port.observe(action) if action is not None else None
        guard = self.guard.inspect(self.c.task_id, row["requirement"]).kind if row["requirement"] is not None else None
        present = observation is not None and observation.status == "PRESENT"
        return {"status": ("PUBLICATION_PRESENT" if guard == DecisionKind.ALLOW else "PUBLICATION_PRESENT_GUARD_STOPPED") if present else "UNKNOWN_PUBLICATION",
            "canonical_status": action["status"] if action is not None else "NOT_SUBMITTED", "ref": self.target.ref,
            "revision": row["view"]["revision"], "product_acceptance": "NOT_ACCEPTED", "mutation_retry": "NOT_AUTHORIZED",
            "progress_guard": guard, "unconfirmed_transport": bool(self.service.unconfirmed_contexts()), "expires_at": row["view"]["expires_at"]}
