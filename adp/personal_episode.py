"""One append-only same-Issue accounting episode, behind separate consent.

The old enrollment and terminal task remain literal historical records. This
module creates no feature, copies no product source and dispatches no worker.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
import secrets

from .accounting_policy import CAPS, POLICY, ROLES, child_id, entry, install
from .discovery_schema import digest
from .execution_memory import invocation_lock
from .git import value
from .guard_schema import requirement_id
from .guard_types import data
from .personal_ci import native_inventory, prescribed_checks
from .personal_enrollment import selection
from .personal_history import archived, _archived_view
from .personal_recovery import Recovery, engine_digest, grant, immutable, journal_purpose
from .personal_storage import (PersonalState, ROLE_LIMITS, approval, create_private, load_state,
                               private_directory, read_private, validate_plan)
from .schema import bundle, encode, fields, key, require
from .storage import locked

NAME = "accounting-expiry-1"
FILE = "episode.json"


def episode_directory(root):
    return root.directory / "episodes" / NAME


def make_plan(root, base):
    """Lossless closed delta from the accepted original enrollment contract."""
    p, choices = deepcopy(root.plan), base["choices"]
    directory = episode_directory(root)
    p["feature"] = {"workspace": choices["workspace"], "branch": choices["branch"], "prepare": True,
                    "preparation": "AFTER_INDEPENDENT_POLICY_REVIEW"}
    p.update(paths=choices["paths"], commit_message=choices["commit_message"], commit_body=choices["commit_body"],
        checks=base["checks"], required_check_names=sorted(choices["checks"]), unresolved_check_names=[],
        check_identity_status="OBSERVED", check_requirements="PRESENT", window=base["window"],
        discovery_digest=base["discovery_digest"])
    p["effects"].update(directory=str(directory), private=str(directory / "private"))
    return p


def plan_valid(root, plan, directory):
    """Reuse accepted validation for all unchanged fields; qualify the two deltas."""
    require(directory == episode_directory(root) and plan["effects"] == {
        **root.plan["effects"], "directory": str(directory), "private": str(directory / "private")}, "Episode must reuse original canonical M1")
    shadow = deepcopy(plan)
    # validate_plan's original per-window constants/destinations still apply to
    # normal enrollments. The episode's smaller caps and shared memory are
    # checked explicitly, never installed as a replacement root enrollment.
    shadow["window"].update(ROLE_LIMITS)
    shadow["effects"].update(coordination=str(directory / "coordination"), coordination_remote=str(directory / "coordination.git"),
                            memory=str(directory / "memory"))
    validate_plan(shadow, directory)
    for name in ROLES:
        require(type(plan["window"][name]) is int and 0 <= plan["window"][name] <= CAPS[name], "Episode cap exceeds approved policy")
    require(plan["window"]["scope_reviewers"] == 1 and plan["window"]["forensic_reviewers"] == 0
            and all(plan["window"][n] == 1 for n in ("maximum_tasks", "maximum_rounds", "maximum_parallel")), "Only one finite non-forensic episode")


@dataclass(frozen=True)
class EpisodeState(PersonalState):
    root: PersonalState
    descriptor: dict

    def memory(self):
        memory = self.root.memory()
        # Keep the exact accepted Memory type (including validation's strict
        # trusted-type gate). No state, owner or observation is memoized.
        memory._accounting_reads = True
        return memory

    @property
    def task_id(self):
        parent = "personal:" + digest({"repository": self.repository_id, "issue": self.plan["issue_id"]})
        return child_id(parent, self.descriptor["episode"])

    def active(self, *, memory=None, runtime=None, allow_expired=True, now=None):
        return self._active_view(memory=memory, runtime=runtime, allow_expired=allow_expired, now=now)[:2]

    def _active_view(self, *, memory=None, runtime=None, allow_expired=True, now=None, _capture=None):
        from .personal_read_frame import active
        framed = active(self, memory, runtime, _capture=_capture)
        if framed is not None:
            if not allow_expired:
                require(type(now) is int and self.plan["window"]["issued_at"] <= now < self.plan["window"]["expires_at"],
                        "Episode window expired")
            return framed
        # Closed plans were validated on load. Re-read their exact protected
        # identities here; do not recursively reload the same root/plan/track
        # through every nested authority proof. No positive result is cached.
        for path in (self.root.directory, self.root.state, self.directory, self.state):
            private_directory(path)
        require(read_private(self.directory / FILE) == self.descriptor
                and read_private(self.root.directory / "personal.json") == self.root.intent
                and read_private(Path(self.root.plan["effects"]["marker"])) == {"schema_version": 1,
                    "directory": str(self.root.directory), "approval": self.root.intent["approval"]}, "Episode/original enrollment changed")
        memory = memory or self.memory()
        capture = _capture if _capture is not None else {}
        m, archive, contexts, observed, workers = _archived_view(self.root, memory=memory, runtime=runtime,
            _child=self, _capture=capture)
        if _capture is not None:
            _capture["archive"] = (m, archive, contexts, observed, workers)
        relation = entry(observed["state"])
        require(relation is not None and relation == expected_relation(self.root, m, archive, self.descriptor,
                usage=relation["usage"], _workers=workers), "Exact canonical episode relation is missing")
        original_link = read_private(self.root.state / "track-link.json")
        require(read_private(self.state / "track-link.json") == {**original_link, "schema_version": 2,
            "directory": str(self.directory), "setup": self.intent["approval"], "snapshot": digest(self.descriptor["base"]["snapshot"]),
            "episode": self.descriptor["episode"], "original_link": digest(original_link)}
            and read_private(self.state / "episode-admission.json") == self.descriptor["base"]["admission"], "Episode track attachment changed")
        activation = read_private(self.directory / "activation.json", optional=True)
        require(activation is not None, "Exact episode activation is missing")
        fields(activation, "schema_version descriptor checkpoint relation")
        require(activation == {"schema_version": 1, "descriptor": digest(self.descriptor),
            "checkpoint": activation["checkpoint"], "relation": digest({k: v for k, v in relation.items() if k != "usage"})},
            "Episode activation is not bound to its exact canonical relation")
        target = episode_intent(self.root, self.descriptor, m, archive, _workers=workers)
        require(read_private(self.directory / "intent.json") == target, "Retain the exact one-use episode intent")
        require(activation["checkpoint"] == capture["historical_basis"]["checkpoint"]
                and capture["installed"] == (target["state"], target["tasks"]), "Installed historical basis differs from exact episode intent")
        if not allow_expired:
            from .personal_read_frame import present
            require(not present(self.root.state / "accounting-recovery" / "revoked" / (digest(self.intent["approval"]) + ".json")), "Episode approval revoked")
            require(type(now) is int and self.plan["window"]["issued_at"] <= now < self.plan["window"]["expires_at"], "Episode window expired")
            require(all(identifier == relation["parent_requirement"] or item["mode"] == "normal"
                        for identifier, item in observed["state"]["progress_guard"]["requirements"].items()),
                    "Only the qualified historical terminal is permitted; another guard stop blocks execution")
        return relation, contexts, observed

    def live(self, now, *, owner=False):
        self.active(allow_expired=False, now=now)
        if owner:
            observed = self.memory().inspect()
            require(observed["health"] == "SYNCED" and observed["local_owner"], "Original owner required")
        return self


def load_episode(directory):
    private_directory(directory)
    d = read_private(directory / FILE)
    fields(d, "schema_version kind root base episode plan original governance approval")
    require(d["schema_version"] == 1 and type(d["schema_version"]) is int and d["kind"] == "ACCOUNTING_EPISODE", "Unsupported episode descriptor")
    require(directory.name == NAME and directory.parent.name == "episodes"
            and d["root"] == str(directory.parent.parent), "Episode must belong to its fixed original ancestor")
    require(not (directory.parent.parent / FILE).exists(), "Original root cannot recursively select another episode")
    root = load_state(directory.parent.parent)
    base = d["base"]
    fields(base, "schema_version policy root archive blueprint choices window checks discovery_digest snapshot admission engine")
    require(base["schema_version"] == 1 and base["policy"] == POLICY and base["root"] == digest(root.intent)
            and d["episode"] == digest(base)
            and d["original"] == root.intent["original"] and d["governance"] == root.intent["governance"]
            and d["plan"] == make_plan(root, base), "Episode immutable identity or original scope changed")
    plan_valid(root, d["plan"], directory)
    # Verify the original finite consent at its real issuance time. This is
    # historical authentication only, never a grant to execute after expiry.
    if (directory / "activation.json").exists():
        from .personal_history import _anchor, _historical_grant
        recovery = root.state / "accounting-recovery"
        proof = _anchor(root, root.memory(), d, read_private(recovery / "intent.json"), read_private(recovery / "archive.json"))
        _historical_grant("episode", digest(base), base["window"]["issued_at"], d["approval"], proof["historical_engine"])
    else:
        require(base["engine"] == engine_digest(), "Unactivated episode requires current-engine consent")
        token, _ = grant("episode", digest(base), base["window"]["issued_at"], d["approval"], window=base["window"])
        require(token == d["approval"], "Episode consent differs")
    intent = {"schema_version": 1, "kind": "ACCOUNTING_EPISODE", "phase": "ENROLLED", "plan": d["plan"],
              "original": d["original"], "governance": d["governance"], "approval": d["approval"]}
    return EpisodeState(directory, intent, root, d)


def expected_relation(root, m, archive, descriptor, *, usage=None, _workers=None):
    parent = m["view"]["binding"]["task_key"]
    parent_id = m["tasks"][parent]["id"]
    child = child_id(parent_id, descriptor["episode"])
    workers = _workers if _workers is not None else [read_private(p) for p in (root.state / "workers").glob("*.json")]
    from .personal_workers import ROLES as WORKER_ROLES
    used = dict.fromkeys(ROLES, 0)
    for row in workers:
        used[WORKER_ROLES[row["purpose"]][1]] += 1
        used["worker_seconds"] += row["observation"]["elapsed_seconds"]
    used.update(maximum_tasks=1, maximum_rounds=1, maximum_parallel=1)
    requirement = requirement_id(parent_id, "product")
    return {"schema_version": 1, "policy": POLICY, "episode": descriptor["episode"], "repository_id": root.repository_id,
        "issue_id": root.plan["issue_id"], "issue_revision": root.intent["original"]["revision"],
        "parent_id": parent_id, "child_id": child, "parent_task": parent, "child_task": key(child),
        "parent_requirement": requirement, "child_requirement": requirement_id(child, "product"),
        "checkpoints": {k: archive[n] for k, n in (("initial", "initial"), ("guard", "guard"), ("result", "result"))},
        "parent_guard": digest(m["guard_state"]["progress_guard"]["requirements"][requirement]),
        "parent_task_digest": digest(m["result_tasks"][parent]), "archive": digest(archive), "blueprint": digest(m["blueprint"]),
        "plan": digest(descriptor["plan"]), "grant": digest(descriptor["approval"]), "host": m["view"]["binding"]["host"],
        "generation": m["state"]["generation"], "window": {n: descriptor["plan"]["window"][n] for n in ("issued_at", "expires_at")},
        "allocations": {"previous": {n: root.plan["window"][n] for n in ROLES}, "previous_used": used,
                        "current": {n: descriptor["plan"]["window"][n] for n in ROLES}},
        "usage": usage or {"requests": {}, "observations": 0, "checks": 0, "check_ids": [], "seconds": 0, "samples": 0, "payload_bytes": 0}}


class Continuation:
    def __init__(self, coordinator):
        self.c = coordinator
        self.recovery = Recovery(coordinator)
        self.root = coordinator.personal
        self.directory = episode_directory(self.root)

    def base(self, m, archive, reviewed=None):
        self.recovery.validate_evidence(m)
        return self.describe(m, archive, reviewed)

    def describe(self, m, archive, reviewed=None):
        """Read-only complete projection; no grant is persisted or exercised."""
        choices = m["blueprint"]["choices"]
        now = self.c.clock()
        if reviewed:
            parts = reviewed.split(":")
            require(len(parts) == 6 and parts[:2] == ["ae1", "episode"], "Wrong episode approval")
            issued, expires, nonce = int(parts[2]), int(parts[3]), parts[4]
        else:
            issued, expires, nonce = now, now + choices["seconds"], secrets.token_hex(16)
        window = {**{n: choices.get(n, CAPS[n]) for n in ROLES}, "issued_at": issued, "expires_at": expires, "nonce": nonce}
        window.update(scope_reviewers=1, forensic_reviewers=0)
        require(expires - issued == choices["seconds"], "Episode window changed")
        observed, owner = selection(Path(self.root.plan["checkout"]["path"]), self.root.plan["checkout"]["remote"], self.root.repository_id, self.c.transport)
        checks = qualified_checks(self.root, choices, self.c.ci_transport)
        base = {"schema_version": 1, "policy": POLICY, "root": digest(self.root.intent), "archive": digest(archive),
            "blueprint": digest(m["blueprint"]), "choices": choices, "window": window, "checks": checks,
            "discovery_digest": observed.facts["discovery_digest"], "snapshot": data(replace(observed.snapshot, observed_at=issued)),
            "admission": None, "engine": engine_digest()}
        # Resolve the policy snapshot against the actual current refs BEFORE the
        # new scope Reviewer. Claims bind this new window, not the expired one.
        plan = make_plan(self.root, base)
        temporary = PersonalState(self.directory, {**self.root.intent, "plan": plan, "approval": "unactivated"})
        from .personal_runner import PersonalCoordinator
        from .personal_track_preparation import unsigned_policy
        c = PersonalCoordinator.__new__(PersonalCoordinator)
        c.personal = temporary
        from .policy_schema import validate_rules
        validate_rules(c.rules())  # Existing capability envelope, before B.
        _, snapshot, claims = unsigned_policy(c)
        base["admission"] = {"policy_snapshot": data(snapshot), "policy_sources": [data(claim) for claim in claims], "completions": []}
        # The plan is unchanged by admission; its hash in operator claims must
        # not include admission or episode identity (acyclic derivation).
        plan_valid(self.root, plan, self.directory)
        token, proof = grant("episode", digest(base), now, reviewed, window=window)
        descriptor = {"schema_version": 1, "kind": "ACCOUNTING_EPISODE", "root": str(self.root.directory), "base": base,
            "episode": digest(base), "plan": plan, "original": self.root.intent["original"], "governance": self.root.intent["governance"], "approval": token}
        return descriptor

    def preview(self, reviewed=None):
        require(not (self.directory / FILE).exists(), "The sole episode already has immutable intent; observe/reconcile it")
        m, archive, _ = archived(self.root, memory=self.c.memory, runtime=self.c.runtime)
        canon = self.recovery.canonical(m)
        require(canon["step"] == 2 and canon["pending"] is None and not self.c.memory._inbox(), "Complete exact historical disposition first")
        d = self.base(m, archive, reviewed)
        preflight(self.c, m, archive=archive, descriptor=d)
        return {"status": "CONTINUATION_PROPOSED", "approval": d["approval"], "result": {
            "policy": POLICY, "episode": d["episode"], "issue": 1, "window": d["plan"]["window"],
            "historical_terminal": "PERMANENT_STOP_UNSAFE", "product_acceptance": "NOT_ACCEPTED",
            "source": "UNACCEPTED_CANDIDATE_ONLY", "effects": "Canonical episode and private intent only; no worker or source mutation"}}, d

    def apply(self, *, reviewed, authorized):
        require(authorized is True, "Separately authorize this one finite same-Issue episode")
        with invocation_lock(self.c.memory.control):
            if (self.directory / FILE).exists():
                require(read_private(self.directory / FILE)["approval"] == reviewed, "The one-use episode cannot be replaced")
                return self.status()
            _, d = self.preview(reviewed)
            m, archive, _ = archived(self.root, memory=self.c.memory, runtime=self.c.runtime)
            intent = self.intent(d, m, archive)
            self.consent(d)
            immutable(self.directory / FILE, d)
            self.consent(d)
            immutable(self.directory / "intent.json", intent)
            self.seed(d)
            self._write(d, intent)
            return self.activate(d, intent)

    def intent(self, d, m, archive):
        return episode_intent(self.root, d, m, archive)

    def seed(self, d, *, reconciliation=None):
        from .personal_track import LINK, content
        c = self.c
        run = {"schema_version": 1, "approval": d["approval"], "generation": c.record()["generation"], "phase": "SCOPE",
            "revision": self.root.plan["checkout"]["head"], "original_review": None, "developer": None, "candidate": None,
            "code_review": None, "actions": {}, "coordination": None, "gates": [], "feedback": [], "observations": 0, "feature_administration": None}
        self.consent(d, reconciliation)
        immutable(self.directory / "private" / "run.json", run)
        self.consent(d, reconciliation)
        snapshot = content(c.track.root / "observations", d["base"]["snapshot"])
        admission = self.directory / "private" / "episode-admission.json"
        self.consent(d, reconciliation)
        immutable(admission, d["base"]["admission"])
        link = {**c.track.link, "schema_version": 2, "directory": str(self.directory), "setup": d["approval"],
                "snapshot": snapshot, "episode": d["episode"], "original_link": digest(c.track.link)}
        self.consent(d, reconciliation)
        immutable(self.directory / "private" / LINK, link)

    def consent(self, d, reconciliation=None):
        require(self.c.clock() >= d["plan"]["window"]["issued_at"], "Original episode cannot be backdated")
        if reconciliation is not None:
            self.recovery.live_grant("reconcile-episode", reconciliation[0], reconciliation[1])
            return
        _, body = grant("episode", digest(d["base"]), self.c.clock(), d["approval"])
        require(not (self.recovery.root / "revoked" / (digest(d["approval"]) + ".json")).exists()
                and body["issued_at"] <= self.c.clock() < body["expires_at"], "Episode consent expired or revoked")

    def fence(self, d, intent, *, reconciliation=None):
        if reconciliation is None:
            grant("episode", digest(d["base"]), self.c.clock(), d["approval"])
            require(not (self.recovery.root / "revoked" / (digest(d["approval"]) + ".json")).exists(), "Episode revoked")
        else:
            payload, reviewed = reconciliation
            self.recovery.live_grant("reconcile-episode", payload, reviewed)
            require(payload["descriptor"] == digest(d) and payload["intent"] == digest(intent), "Episode reconciliation subject differs")
        require(read_private(self.directory / FILE) == d and read_private(self.directory / "intent.json") == intent, "Episode intent changed")
        self.recovery.validate_evidence(self.recovery.master())
        observed = self.c.memory.inspect(recovery=True)
        self.c.memory._owner(observed["state"])
        pending = self.c.memory._recovery_document(protected=True)
        current = self.c.memory._read_ref(observed["local_head"])
        m = self.recovery.master()
        require(observed["state"]["owner"] == m["state"]["owner"] and observed["state"]["generation"] == m["state"]["generation"]
                and current in ((m["result_state"], m["result_tasks"]), (intent["state"], intent["tasks"]))
                and observed["remote_head"] in (intent["base"], observed["local_head"])
                and not self.c.memory._inbox(), "Episode canonical baseline changed")
        if pending:
            require(pending == {"schema_version": 2, "base": intent["base"], "state": intent["state"], "tasks": intent["tasks"],
                "policy_fence": journal_purpose("episode", intent)}, "Foreign pending checkpoint")
        if current == (m["result_state"], m["result_tasks"]):
            require(observed["local_head"] == intent["base"], "Episode expected H2 changed")
        else:
            require(value(self.c.memory.config.root, "rev-parse", observed["local_head"] + "^") == intent["base"], "Episode must be the exact direct successor")
        destination = Path(d["plan"]["feature"]["workspace"])
        private_directory(destination, missing=True)
        require(not destination.exists(), "Unactivated episode cannot adopt an existing feature destination")
        self.consent(d, reconciliation)

    def _write(self, d, intent, *, reconciliation=None):
        with locked(self.c.memory.control):
            self.fence(d, intent, reconciliation=reconciliation)
            head, state, tasks = self.c.memory._start()
            require(head == intent["base"], "Expected H2 changed inside canonical lock")
            target = deepcopy(intent["state"]); target["revision"] -= 1
            self.c.memory._checkpoint(head, target, deepcopy(intent["tasks"]), _fence=lambda: self.fence(d, intent, reconciliation=reconciliation),
                _purpose=journal_purpose("episode", intent))

    def activate(self, d, intent):
        with locked(self.c.memory.control):
            self.fence(d, intent)
            head, state, tasks = self.c.memory._start()
            require((state, tasks) == (intent["state"], intent["tasks"]), "Observe exact H3 before activation")
            self.consent(d)
            immutable(self.directory / "activation.json", {"schema_version": 1, "descriptor": digest(d), "checkpoint": head,
                "relation": digest({k: v for k, v in entry(state).items() if k != "usage"})})
        return self.status()

    def reconcile_preview(self, reviewed=None):
        d = read_private(self.directory / FILE)
        m, archive, _ = archived(self.root, memory=self.c.memory, runtime=self.c.runtime)
        intent = self.intent(d, m, archive)
        retained = read_private(self.directory / "intent.json", optional=True)
        require(retained in (None, intent), "Episode intent differs from its immutable descriptor")
        observed = self.c.memory.inspect(recovery=True)
        payload = {"descriptor": digest(d), "intent": digest(intent), "head": observed["local_head"],
            "remote": observed["remote_head"], "pending": self.c.memory._recovery_document(protected=True)}
        token, _ = self.recovery.live_grant("reconcile-episode", payload, reviewed)
        return {"status": "CONTINUATION_RECONCILIATION_PROPOSED", "approval": token,
            "result": {"episode": d["episode"], "window": "UNCHANGED", "activation": "ONLY_WHILE_ORIGINAL_APPROVAL_IS_LIVE"}}, payload, d, intent

    def reconcile(self, *, reviewed, authorized):
        require(authorized is True, "Approve recovery of the same episode intent; no renewed window")
        with invocation_lock(self.c.memory.control):
            _, payload, d, intent = self.reconcile_preview(reviewed)
            if (self.directory / "activation.json").exists():
                return self.status()
            self.recovery.live_grant("reconcile-episode", payload, reviewed)
            immutable(self.directory / "intent.json", intent)
            self.seed(d, reconciliation=(payload, reviewed))
            directory = self.recovery.root / "reconciliations"
            require(not directory.exists() or len(list(directory.glob("*.json"))) < 4
                    or (directory / (digest(reviewed) + ".json")).exists(), "Finite reconciliation grants exhausted")
            immutable(directory / (digest(reviewed) + ".json"), {"approval": reviewed, "payload": payload})
            fence = lambda: self.fence(d, intent, reconciliation=(payload, reviewed))
            fence()
            if self.c.memory._recovery_document(protected=True) is not None:
                self.c.memory.recover(before_effects=fence, expected_remote=payload["remote"], _fence=fence,
                    _purpose=journal_purpose("episode", intent))
            elif self.c.memory.inspect()["local_head"] == intent["base"]:
                self._write(d, intent, reconciliation=(payload, reviewed))
            if self.c.clock() >= d["plan"]["window"]["expires_at"] or (self.recovery.root / "revoked" / (digest(d["approval"]) + ".json")).exists():
                return {"status": "BLOCKED_WINDOW_EXPIRED_OR_REVOKED", "slot": "CONSUMED", "activation": "NOT_PERMITTED"}
            return self.activate(d, intent)

    def status(self):
        personal = load_episode(self.directory)
        if not (self.directory / "activation.json").exists():
            return {"status": "CONTINUATION_RECONCILIATION_REQUIRED" if self.c.clock() < personal.plan["window"]["expires_at"] else
                    "BLOCKED_WINDOW_EXPIRED", "execution": "NOT_DELEGATED", "slot": "CONSUMED"}
        relation, _ = personal.active(memory=self.c.memory, runtime=self.c.runtime)
        revoked = (self.recovery.root / "revoked" / (digest(personal.intent["approval"]) + ".json")).exists()
        run = read_private(personal.state / "run.json")
        phase = "CONTINUATION_SCOPE_REVIEW_REQUIRED" if run["phase"] == "SCOPE" else "CONTINUATION_ACTIVATED"
        return {"status": "BLOCKED_APPROVAL_REVOKED" if revoked else phase if self.c.clock() < personal.plan["window"]["expires_at"] else
            "BLOCKED_WINDOW_EXPIRED", "episode": relation["episode"], "directory": str(self.directory),
            "allocations": relation["allocations"], "usage": relation["usage"], "product_acceptance": "NOT_REOBSERVED",
            "historical_terminal": "PERMANENT_UNKNOWN_STOP_UNSAFE", "phase": run["phase"],
            "execution": "NOT_STARTED" if not relation["usage"]["requests"] else "NO_BACKGROUND_EXECUTION_CLAIM"}


def qualified_checks(root, choices, transport):
    require(transport is not None, "Actual prescribed native project check identities are required")
    p = root.plan
    inventory = native_inventory(p["repository"]["name"], root.repository_id, p["checkout"]["ref"], p["checkout"]["head"], transport)
    require(set(choices["checks"]) <= set(inventory), "Prescribed project check identities are unavailable")
    return [data(c) for c in prescribed_checks(tuple(sorted(choices["checks"])), inventory,
        accept_native_job_records=p["accept_native_job_records"])]


def episode_intent(root, descriptor, master, archive, *, _workers=None):
    relation = expected_relation(root, master, archive, descriptor, _workers=_workers)
    state, tasks = deepcopy(master["result_state"]), deepcopy(master["result_tasks"])
    install(state, tasks, relation)
    state["revision"] += 1; state["task_keys"] = sorted(tasks)
    bundle(state, tasks, root.repository_id)
    return {"descriptor": digest(descriptor), "base": archive["result"], "state": state, "tasks": tasks}


def same_observation(proven, current, *, recovery=False):
    """Fresh final M1 read must match the exact subject just proved locally.

    Only a lock-held existing checkpoint fence may inspect its own pending
    transaction. Normal authority continues to require synchronized ownership.
    No positive decision or observation is reused across calls.
    """
    require(proven["health"] == current["health"] and current["health"] in
            (("SYNCED", "RECOVERY_REQUIRED") if recovery else ("SYNCED",))
            and proven["local_owner"] is True and current["local_owner"] is True,
            "Canonical proof lost synchronized ownership")
    names = ("local_head", "remote_head", "state", "tasks", "local_owner", "inbox_count")
    if recovery:
        names += ("recovery_slots", "recovery_journal")
    require(all(proven[n] == current[n] for n in names), "Canonical subject advanced during archival proof; obtain a fresh proof")


def blueprint_ready(c, choices):
    """Dry validation before the first irreversible B write; no new authority."""
    root = c.personal
    private_directory(episode_directory(root), missing=True)
    require(not episode_directory(root).exists(), "The one-use episode slot already exists")
    from .personal_recovery import material
    require(all(any(row["path"] == p or row["path"].startswith(p + "/") for p in choices["paths"])
                for row in material(c)), "Child scope must cover both retained unaccepted files")
    from .git import git
    for row in material(c):
        parent = Path(row["path"]).parent.as_posix()
        require(parent == "." or git(Path(root.plan["checkout"]["path"]), "cat-file", "-t",
            root.plan["checkout"]["head"] + ":" + parent).strip() == b"tree", "Candidate parent must exist in the exact base; directory creation is not delegated")
    checks = qualified_checks(root, choices, c.ci_transport)
    window = {**CAPS, **{n: choices[n] for n in choices if n in CAPS}, "issued_at": c.clock(),
              "expires_at": c.clock() + choices["seconds"], "nonce": "0" * 32, "forensic_reviewers": 0}
    base = {"choices": choices, "checks": checks, "window": window, "discovery_digest": root.plan["discovery_digest"]}
    plan_valid(root, make_plan(root, base), episode_directory(root))


def preflight(c, master, *, archive=None, descriptor=None):
    """Bound the complete future Scope prompt and both durable C records.

    The B preview uses fixed-size placeholder checkpoint hashes only for byte
    qualification. They are never receipts, persisted evidence or authority.
    Actual C preview repeats this with its real immutable predecessor.
    """
    from copy import copy
    from types import SimpleNamespace
    from .discovery_schema import typed
    from .discovery_types import Snapshot
    from .personal_storage import LIMIT
    from .personal_runner import PersonalCoordinator
    from .personal_workers import prompt
    archive = archive or {"initial": master["view"]["checkpoint"], "guard": "0" * 40, "result": "0" * 40}
    d = descriptor or Continuation(c).describe(master, archive)
    plan_valid(c.personal, d["plan"], episode_directory(c.personal))
    intent = episode_intent(c.personal, d, master, archive)
    p = EpisodeState(episode_directory(c.personal), {"schema_version": 1, "kind": "ACCOUNTING_EPISODE",
        "phase": "ENROLLED", "plan": d["plan"], "original": d["original"], "governance": d["governance"], "approval": d["approval"]}, c.personal, d)
    prospective = SimpleNamespace(personal=p, episode=True, record=lambda: None,
        revision=lambda: p.plan["checkout"]["head"], accounting_material=lambda: master["blueprint"]["material"])
    track = copy(c.track)
    track.c, track.personal = prospective, p
    track.link = {**track.link, "directory": str(p.directory), "setup": d["approval"]}
    track.seed = lambda: typed(Snapshot, d["base"]["snapshot"])
    track.admission = lambda: d["base"]["admission"]
    prospective.track = track
    context = PersonalCoordinator.context(prospective, "original")
    bound_projection(d, intent, context)
    return context


def bound_projection(descriptor, intent, context):
    from .execution_privacy import credential_shaped
    from .personal_storage import LIMIT
    from .personal_workers import prompt
    encode(descriptor, LIMIT)
    encode(intent, LIMIT)
    # Reserve only byte-width growth of future real UTC fields; execution and
    # accepted prompt limits remain unchanged. Actual C projection is rechecked.
    require(len(prompt("original", context).encode()) + 128 <= 32768 and not credential_shaped(context),
            "Complete continuation Scope context exceeds the existing worker limit or contains sensitive material")


def effective(personal):
    """One qualified resolver for all track consumers; pending never falls back."""
    if isinstance(personal, EpisodeState):
        personal.active()
        return personal
    destination = episode_directory(personal)
    if destination.exists():
        child = load_episode(destination)
        child.active()
        return child
    return personal


def settled_guards(personal, state):
    relation = entry(state)
    if relation is None:
        return all(g["active"] is None and g["mode"] == "normal" for g in state["progress_guard"]["requirements"].values())
    require(isinstance(personal, EpisodeState), "Historical terminal needs its qualified episode")
    actual, _ = personal.active()
    require({k: v for k, v in actual.items() if k != "usage"} == {k: v for k, v in relation.items() if k != "usage"}, "Historical episode relation differs")
    return all(g["active"] is None and (digest(g) == relation["parent_guard"] if identifier == relation["parent_requirement"]
                else g["mode"] == "normal") for identifier, g in state["progress_guard"]["requirements"].items())
