"""Exact, explicitly consented personal accounting-expiry transactions.

No worker, source edit, forge mutation or automatic continuation is reachable
from guard/result settlement. Private full evidence never becomes CLI output.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import secrets
import stat

from .accounting_policy import CAPS, POLICY, PURPOSES, ROLES, REASON, fingerprint
from .config import safe_path
from .discovery import complete_snapshot
from .discovery_schema import digest, typed
from .execution_containment import source_seal
from .execution_memory import invocation_lock
from .execution_types import WorkerRequest
from .git import git, value
from .guard_types import data
from .personal_archive import _seals, _stopped, _terminal, proposal
from .personal_enrollment import governance, selection
from .personal_storage import (LIMIT, PersonalBlocked, create_private, load_state, read_private)
from .policy_schema import branch, product_path
from .schema import bundle, encode, fields, key, require
from .storage import atomic, locked, sync_directory


def immutable(path, body):
    create_private(path.parent)
    if path.exists():
        require(read_private(path) == body, "Immutable recovery evidence conflicts")
    else:
        atomic(path, encode(body, LIMIT), replace=False)


def journal_purpose(stage, intent):
    require(stage in ("guard", "result", "episode"), "Unsupported recovery stage")
    return {"policy": POLICY, "stage": stage, "subject": digest(intent)}


def submission_provenance(directory, stage, original, master):
    """Authenticate a previously prepared marker restoration, never renew it."""
    require(stage in ("guard", "result"), "Unsupported archival stage")
    restored = read_private(directory / "submission-provenance" / (stage + ".json"), optional=True)
    if restored is None:
        return None
    fields(restored, "stage intent reconciliation prepared_at")
    key_ = restored["reconciliation"]
    require(type(key_) is str and len(key_) == 64 and all(c in "0123456789abcdef" for c in key_), "Invalid reconciliation identity")
    record = read_private(directory / "reconciliations" / (key_ + ".json"))
    fields(record, "approval payload")
    fields(record["payload"], "stage master intent canonical")
    grant("reconcile-" + stage, digest(record["payload"]), restored["prepared_at"], record["approval"])
    require(restored["stage"] == record["payload"]["stage"] == stage
            and restored["intent"] == record["payload"]["intent"] == digest(original)
            and record["payload"]["master"] == digest(master)
            and digest(record["approval"]) == key_, "Submission restoration authority differs")
    return restored


def engine_digest():
    root = Path(__file__).parent
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))})


def grant(stage, subject, now, reviewed=None, *, window=None):
    """A purpose-bound finite consent; never the original execution token."""
    require(type(now) is int and now >= 0, "Trusted current UTC clock required")
    if reviewed is not None:
        parts = reviewed.split(":")
        require(len(parts) == 6 and parts[:2] == ["ae1", stage], "Wrong recovery approval purpose")
        issued, expires, nonce = int(parts[2]), int(parts[3]), parts[4]
    elif window is not None:
        issued, expires, nonce = (window[n] for n in ("issued_at", "expires_at", "nonce"))
    else:
        issued, expires, nonce = now, now + 300, secrets.token_hex(16)
    require(0 <= issued <= now < expires and 0 < expires - issued <= 3600
            and len(nonce) == 32 and all(c in "0123456789abcdef" for c in nonce), "Recovery approval expired or malformed")
    body = {"policy": POLICY, "stage": stage, "subject": subject, "engine": engine_digest(),
            "issued_at": issued, "expires_at": expires, "nonce": nonce}
    token = ":".join(("ae1", stage, str(issued), str(expires), nonce, digest(body)))
    require(reviewed is None or reviewed == token, "Exact recovery source/evidence/approval changed")
    return token, body


def material(c):
    root, p = c.personal.feature, c.personal.plan
    changed = git(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "HEAD", "-z")
    changed += git(root, "ls-files", "--others", "--exclude-standard", "-z")
    paths = sorted({v.decode("utf-8", "strict") for v in changed.split(b"\0") if v})
    require(len(paths) == 2, "This policy supports exactly the original two candidate files")
    rows = []
    for relative in paths:
        product_path(relative)
        require(any(relative == a or relative.startswith(a + "/") for a in p["paths"]), "Candidate exceeds original admitted source")
        path = safe_path(root / relative)
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 1048576
                and info.st_uid == os.getuid() and not info.st_mode & 0o7022, "Candidate must be bounded owned non-special regular source")
        raw = path.read_bytes()
        index = value(root, "ls-files", "--stage", "--", relative)
        tracked = bool(index)
        require(not tracked or index.split()[0] in ("100644", "100755"), "Candidate base cannot be a symlink/special file")
        before = hashlib.sha256(git(root, "show", p["checkout"]["head"] + ":" + relative)).hexdigest() if tracked else None
        rows.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                     "mode": stat.S_IMODE(info.st_mode), "before": before})
    return rows


def administration_snapshot(personal):
    def one(root):
        return {"config": hashlib.sha256(git(root, "config", "--null", "--list")).hexdigest(),
                "index": hashlib.sha256(git(root, "ls-files", "--stage", "-z")).hexdigest(),
                "head": value(root, "rev-parse", "HEAD"), "ref": value(root, "symbolic-ref", "HEAD")}
    refs = dict(line.split(" ", 1) for line in value(personal.feature, "for-each-ref", "--format=%(refname) %(objectname)").splitlines())
    return {"feature": one(personal.feature), "outside": one(Path(personal.plan["checkout"]["path"])), "refs": refs}


def candidate_diff(personal):
    """Exact bounded product input only; no runtime/host/private receipt data."""
    from .execution_privacy import credential_shaped
    rows = material(type("Candidate", (), {"personal": personal})())
    diff = git(personal.feature, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--",
               *(row["path"] for row in rows), limit=12000).decode("utf-8", "strict")
    additions = [{"path": row["path"], "content": (personal.feature / row["path"]).read_text("utf-8")}
                 for row in rows if row["before"] is None]
    result = {"tracked_diff": diff, "additions": additions}
    encode(result, 14000)
    require(not credential_shaped(result), "Sensitive source cannot enter a Reviewer prompt")
    return result


class Recovery:
    def __init__(self, coordinator):
        self.c, self.personal = coordinator, coordinator.personal
        require(self.personal.intent["kind"] == "PERSONAL", "Select the original root recovery directory")
        self.root = self.personal.state / "accounting-recovery"
        self.master_path = self.root / "intent.json"

    def graph(self):
        c, p = self.c, self.personal.plan
        require(c.transport is not None and c.track is not None and c.track.link["parent"] is None
                and p["issue"] == 1 and c.track.index["first"] == str(self.personal.directory), "Only the original selected first-Issue track qualifies")
        observed, owner = selection(Path(p["checkout"]["path"]), p["checkout"]["remote"], self.personal.repository_id, c.transport)
        require(complete_snapshot(observed.snapshot) and owner == p["owner"] and observed.checkout == p["checkout"]
                and observed.repository == p["repository"] and observed.facts["branch_rules"] == p["branch_rules"]
                and digest(governance(Path(p["checkout"]["path"]))) == p["governance_digest"], "Original source/permissions/governance are not current")
        originals = {o.issue.number: o.issue for o in c.track.originals.values()}
        current = {i.number: i for i in observed.snapshot.issues if i.number in originals}
        require(set(originals) == {1, 2, 3} and current == originals, "Original Issue revision/native inventory changed")
        edges = {(i.number, r.target.number) for i in current.values() for r in i.relations
                 if r.kind == "BLOCKED_BY" and r.confidence == "NATIVE"}
        require(edges == {(2, 1), (3, 2)}, "The original verified three-Issue chain is required")
        return digest({str(n): data(i) for n, i in sorted(current.items())})

    def blueprint(self, choices):
        p = self.personal.plan
        fields(choices, "branch workspace paths checks commit_message commit_body seconds developers candidate_reviewers code_reviewers maximum_check_observations worker_seconds")
        branch(choices["branch"])
        require(choices["branch"] not in (p["feature"]["branch"], p["repository"]["default_branch"]), "Use a distinct child feature")
        workspace = safe_path(Path(choices["workspace"]))
        from .personal_storage import private_directory
        private_directory(workspace, missing=True)
        require(workspace.is_absolute() and not workspace.exists()
                and all(not workspace.is_relative_to(q) and not q.is_relative_to(workspace) for q in
                        (self.personal.directory, self.personal.feature, Path(p["checkout"]["path"]), Path(__file__).resolve().parents[1])),
                "Select a new disjoint owned child feature destination")
        require(not value(Path(p["checkout"]["path"]), "for-each-ref", "--format=%(refname)", "refs/heads/" + choices["branch"]), "Child feature already exists")
        require(type(choices["paths"]) is list and choices["paths"] and set(choices["paths"]) <= set(p["paths"])
                and type(choices["checks"]) is list and set(p["required_check_names"]) <= set(choices["checks"])
                and "tests" in choices["checks"], "Preserve original scope and prescribed project tests")
        require(type(choices["seconds"]) is int and 60 <= choices["seconds"] <= 3600, "Select one finite child window")
        for n in ("developers", "candidate_reviewers", "code_reviewers", "maximum_check_observations", "worker_seconds"):
            require(type(choices[n]) is int and 0 <= choices[n] <= CAPS[n], "Child resource allocation exceeds policy")
        require(choices["candidate_reviewers"] >= 1 and choices["code_reviewers"] == 2
                and choices["maximum_check_observations"] >= 2 and choices["worker_seconds"] >= 1,
                "Fresh staged/code/product review and actual check capacity are mandatory")
        require(type(choices["commit_message"]) is str and choices["commit_message"].strip()
                and len(choices["commit_message"]) <= 256 and type(choices["commit_body"]) is str
                and len(choices["commit_body"]) <= 2048, "Select bounded real project commit operands")
        from .personal_episode import blueprint_ready
        blueprint_ready(self.c, choices)
        candidate_diff(self.personal)
        return {"schema_version": 1, "policy": POLICY, "choices": choices, "graph": self.graph(),
                "material": material(self.c), "engine": engine_digest(), "new_scope_reviewers": 1, "new_forensics": 0}

    @staticmethod
    def measurements(row, action=None):
        observed, request = row["observation"], typed(WorkerRequest, row["request"])
        for measured, cap in (("elapsed_seconds", "seconds"), ("samples", "samples"), ("payload_bytes", "payload_bytes")):
            value_ = observed[measured]
            require(type(value_) is int and 0 <= value_ <= getattr(request, cap)
                    and (action is None or value_ <= action[cap]), "A non-accounting resource hazard cannot continue")

    def build(self, request, choices):
        c = self.c
        from .personal_history_git import storage_context
        storage_context(c.memory)
        view = proposal(c, request)
        require(view["stage"] == "TERMINAL_GUARD_REQUIRED", "Only the original untouched stopped attempt can be prepared")
        row, original = c.worker(request), c.worker(c.record()["original_review"])
        state, tasks = c.memory._read_ref(view["checkpoint"])
        require(len(state["progress_guard"]["requirements"]) == 3 and all(
            g["mode"] == "normal" and (g["active"] is None or identifier == row["requirement"])
            and g["limits"] == self.personal.plan["guard"]["limits"]
            and g["forensic_round"] == 0 and g["campaign_runs"] == 0 and g["campaign"] is None
            and g["cause"] is None and g["request"] is None and g["plan"] is None
            and (g["last"] is None or g["last"]["observation"]["risk"] is None)
            and (identifier == row["requirement"] or g["sequence"] == 2 and g["last"] is not None
                 and g["last_event"] == "attempt" and g["last"]["observation"]["outcome"] == "PASS")
            for identifier, g in state["progress_guard"]["requirements"].items()), "A separate historical hazard cannot qualify")
        self.measurements(row, state["progress_guard"]["requirements"][row["requirement"]]["active"]["action"])
        self.measurements(original)
        require(not (c.personal.state / "accounting-recovery" / "archive.json").exists()
                and state["progress_guard"]["schema_version"] == 1, "Only one original accounting incident")
        guard_state, result_state, result_tasks = _terminal(state, tasks, row["requirement"], row["assignment"], c.workers.result(row))
        master = {"schema_version": 1, "policy": POLICY, "engine": engine_digest(), "request": request,
            "view": view, "blueprint": self.blueprint(choices), "state": state, "tasks": tasks,
            "guard_state": guard_state, "result_state": result_state, "result_tasks": result_tasks,
            "administration": administration_snapshot(self.personal)}
        encode(master, LIMIT)
        from .personal_episode import preflight
        preflight(c, master)
        return master

    def master(self):
        m = read_private(self.master_path)
        fields(m, "schema_version policy engine request view blueprint state tasks guard_state result_state result_tasks administration")
        require(m["schema_version"] == 1 and m["policy"] == POLICY and m["engine"] == engine_digest(), "Recovery source algorithm changed; retain original evidence")
        for stage in ("guard", "result"):
            intent = read_private(self.root / (stage + "-intent.json"), optional=True)
            if intent is not None:
                require(intent["payload"]["master"] == digest(m), "The immutable recovery master changed")
        return m

    def validate_evidence(self, m, *, remote=True):
        """No locks/writers/live authority here; safe inside canonical fencing."""
        c, view = self.c, m["view"]
        require(type(c.clock()) is int and c.clock() >= self.personal.plan["window"]["expires_at"], "Original expiry cannot be backdated")
        for stage in ("guard", "result"):
            intent = read_private(self.root / (stage + "-intent.json"), optional=True)
            require(intent is None or type(intent["submitted_at"]) is int and intent["submitted_at"] <= c.clock(),
                    "Current UTC precedes a retained original submission")
        require(load_state(self.personal.directory).intent == self.personal.intent
                and digest(c.record()) == view["binding"]["evidence"]["run"]
                and digest(c.workers.records()) == view["binding"]["evidence"]["inventory"], "Original private history changed")
        row, original = c.worker(m["request"]), c.worker(c.record()["original_review"])
        from .personal_history import retained
        require(retained(c.runtime, row) == view["binding"]["evidence"]["developer"]
                and retained(c.runtime, original) == view["binding"]["evidence"]["original"]
                and _seals(c, row, original) == view["binding"]["evidence"]["seals"], "Original host/receipt/source provenance changed")
        self.measurements(row, m["state"]["progress_guard"]["requirements"][row["requirement"]]["active"]["action"])
        self.measurements(original)
        require((not remote or self.graph() == m["blueprint"]["graph"]) and material(c) == m["blueprint"]["material"], "Original graph/material changed")
        require(administration_snapshot(self.personal) == m["administration"], "Original Git administration content changed")
        require(m["engine"] == engine_digest(), "Recovery engine changed")
        return row

    def canonical(self, m):
        memory = self.c.memory
        observed = memory.inspect(recovery=True)
        require(observed["local_owner"] and observed["state"]["owner"] == m["state"]["owner"]
                and observed["state"]["generation"] == m["state"]["generation"], "Original canonical owner/generation changed")
        h0 = m["view"]["checkpoint"]
        expected = [(m["state"], m["tasks"]), (m["guard_state"], m["tasks"]), (m["result_state"], m["result_tasks"])]
        head = observed["local_head"]
        parents = value(memory.config.root, "rev-list", "--parents", "--max-count=3", head).splitlines()
        state_tasks = memory._read_ref(head)
        require(state_tasks in expected, "Unrelated canonical state cannot be archived")
        step = expected.index(state_tasks)
        chain = [head]
        cursor = head
        for i in range(step, 0, -1):
            parts = value(memory.config.root, "rev-list", "--parents", "--max-count=1", cursor).split()
            require(len(parts) == 2 and memory._read_ref(parts[1]) == expected[i-1], "Exact guard-first intermediate history required")
            cursor = parts[1]; chain.append(cursor)
        require(cursor == h0 and len(parents) >= 1, "Original canonical ancestor differs")
        pending = memory._recovery_document(protected=True)
        if pending is not None:
            require(step < 2 or pending["base"] == chain[1], "Unexpected pending archival stage")
            targets = [(m["guard_state"], m["tasks"]), (m["result_state"], m["result_tasks"])]
            target = next((i+1 for i, t in enumerate(targets) if (pending["state"], pending["tasks"]) == t), None)
            require(target is not None and (step == target-1 and pending["base"] == head
                    or step == target and value(memory.config.root, "rev-parse", head + "^") == pending["base"]), "Pending checkpoint is not the exact authorized transaction")
            stage = "guard" if target == 1 else "result"
            require(pending.get("policy_fence") == journal_purpose(stage, read_private(self.root / (stage + "-intent.json"))),
                    "Pending archival journal lost its original purpose")
            require(observed["remote_head"] in (pending["base"], head) and observed["remote_head"] is not None, "Uncertain/foreign remote checkpoint")
        else:
            from .storage import temporary_slot
            row = self.c.worker(m["request"])
            allowed_slot = str(temporary_slot(memory.path / "inbox" / (key(row["assignment"]["assignment_id"]) + ".json")).relative_to(memory.path))
            require(observed["remote_head"] == head and (observed["health"] == "SYNCED" or
                step > 0 and observed["recovery_slots"] == [allowed_slot]
                and value(memory.path, "diff", "--name-only", "HEAD") == ""), "Dirty/unpublished canonical state requires exact journal recovery")
        row = self.c.worker(m["request"])
        envelope = {"schema_version": 1, **row["assignment"], "result": self.c.workers.result(row)}
        inbox = [p for p in memory._inbox() if str(p.relative_to(memory.path)) not in observed["recovery_slots"]]
        require((step > 0 or not inbox) and len(inbox) <= 1 and all(
            p.name == key(row["assignment"]["assignment_id"]) + ".json" and read_private(p) == envelope for p in inbox),
            "Conflicting or unrelated immutable deliveries block archival mutation")
        return {"step": step, "head": head, "remote": observed["remote_head"], "chain": list(reversed(chain)), "pending": pending,
                "slots": observed["recovery_slots"]}

    def live_grant(self, stage, payload, reviewed):
        token, body = grant(stage, digest(payload), self.c.clock(), reviewed)
        require(not (self.root / "revoked" / (digest(token) + ".json")).exists(), "This exact approval was revoked")
        require(body["issued_at"] <= self.c.clock() < body["expires_at"], "Recovery consent expired during verification")
        return token, body

    def subject(self, stage, m, canon):
        require(stage in ("guard", "result"), "Use the separately approved continuation/adoption protocol")
        required = 0 if stage == "guard" else 1
        require(canon["step"] == required and canon["pending"] is None, "Observe/reconcile the original stage before another write")
        return {"policy": POLICY, "stage": stage, "master": digest(m), "head": canon["head"],
                "target": digest([m["guard_state"], m["tasks"]] if stage == "guard" else [m["result_state"], m["result_tasks"]])}

    def summary(self, stage, m, approval=None, status=None):
        return {"schema_version": 1, "policy": POLICY, "stage": stage, "status": status or "RECOVERY_PROPOSED",
            "approval": approval, "binding": "accounting-recovery:" + digest(m), "original_issue": 1,
            "worker_outcome": "NOTRUN", "delivery_outcome": "UNKNOWN", "product_acceptance": "NOT_ACCEPTED",
            "timeliness": "UNKNOWN", "historical_terminal": "UNKNOWN/STOP_UNSAFE_OVERDUE_ACCOUNTING",
            "candidate_material": m["blueprint"]["material"], "choices": m["blueprint"]["choices"],
            "execution": "NOT_DELEGATED", "next_requires_separate_approval": True}

    def preview(self, stage, *, request=None, choices=None, reviewed=None):
        m = self.master() if self.master_path.exists() else self.build(request, choices)
        self.validate_evidence(m)
        canon = self.canonical(m)
        payload = self.subject(stage, m, canon)
        token, _ = self.live_grant(stage, payload, reviewed)
        return self.summary(stage, m, token), m, payload

    def _fence(self, stage, m, payload, reviewed, intent):
        require(read_private(self.master_path) == m and read_private(self.root / (stage + "-intent.json")) == intent,
                "Immutable archival evidence changed inside the canonical lock")
        self.live_grant(stage, payload, reviewed)
        self.validate_evidence(m)
        self.c.memory._owner(m["state"])
        current = self.canonical(m)
        required = 0 if stage == "guard" else 1
        require(current["step"] in (required, required+1), "Canonical stage changed")
        if current["pending"] is None:
            require(current["head"] == payload["head"] if current["step"] == required else
                    value(self.c.memory.config.root, "rev-parse", current["head"] + "^") == payload["head"],
                    "Expected checkpoint changed inside canonical lock")
        else:
            require(current["pending"]["base"] == payload["head"], "Pending parent differs from original consent")
        self.live_grant(stage, payload, reviewed)  # Last, after potentially blocking evidence/network reads.

    def apply(self, stage, *, reviewed, authorized, acknowledge, request=None, choices=None):
        require(stage in ("guard", "result"), "Unsupported archival stage")
        require(authorized is True and acknowledge is True, "Separately authorize this exact archival effect and overdue-accounting severity")
        with invocation_lock(self.c.memory.control):
            existing = read_private(self.root / (stage + "-intent.json"), optional=True)
            if existing is not None:
                require(existing["approval"] == reviewed, "Do not replace the original one-use stage intent")
                return self.status()
            view, m, payload = self.preview(stage, request=request, choices=choices, reviewed=reviewed)
            self.live_grant(stage, payload, reviewed)
            immutable(self.master_path, m)
            _, proof = self.live_grant(stage, payload, reviewed)
            intent = {"approval": reviewed, "grant": proof, "submitted_at": self.c.clock(), "payload": payload}
            immutable(self.root / (stage + "-intent.json"), intent)
            self.live_grant(stage, payload, reviewed)
            immutable(self.root / (stage + "-submitted.json"), {"subject": digest(payload)})
            self._perform(stage, m, payload, lambda: self._fence(stage, m, payload, reviewed, intent))
            return self.finish(stage, m)

    def _perform(self, stage, m, payload, fence):
        memory = self.c.memory
        with locked(memory.control):
            fence()
            head, state, tasks = memory._start()
            require(head == payload["head"], "Exact effect baseline changed")
            if stage == "guard":
                row = self.c.worker(m["request"])
                item = state["progress_guard"]["requirements"][row["requirement"]]
                self.c.guard._abandon_transition(state, tasks[key(self.c.task_id)], item, row["requirement"], m["view"]["abandon_evidence_reference"])
                item["sequence"] += 1
            else:
                row = self.c.worker(m["request"])
                envelope = {"schema_version": 1, **row["assignment"], "result": self.c.workers.result(row)}
                inbox = memory.path / "inbox" / (key(row["assignment"]["assignment_id"]) + ".json")
                if inbox.exists(): require(read_private(inbox) == envelope, "Conflicting original inbox")
                else:
                    fence()
                    memory._deliver(envelope, state, tasks)
                memory._accept_result(envelope, state, tasks)
            memory._checkpoint(head, state, tasks, _fence=fence,
                _purpose=journal_purpose(stage, read_private(self.root / (stage + "-intent.json"))))
            if stage == "result":
                fence()
                inbox.unlink(); sync_directory(inbox.parent)

    def finish(self, stage, m):
        canon = self.canonical(m)
        require(canon["pending"] is None and canon["step"] == (1 if stage == "guard" else 2), "The exact stage is not published")
        immutable(self.root / (stage + "-observed.json"), {"checkpoint": canon["head"], "master": digest(m)})
        if stage == "result":
            require(not self.c.memory._inbox(), "Identical accepted inbox cleanup remains")
            immutable(self.root / "archive.json", {"schema_version": 1, "policy": POLICY, "master": digest(m),
                "initial": m["view"]["checkpoint"], "guard": canon["chain"][1], "result": canon["head"],
                "consents": {s: digest(read_private(self.root / (s + "-intent.json"))) for s in ("guard", "result")},
                "observations": {s: digest(read_private(self.root / (s + "-observed.json"))) for s in ("guard", "result")},
                "recovery": {str(p.relative_to(self.root)): digest(read_private(p)) for directory in
                             (self.root / "reconciliations", self.root / "submission-provenance") for p in sorted(directory.glob("*.json"))}})
        return self.summary(stage, m, status="ARCHIVAL_GUARD_OBSERVED" if stage == "guard" else "ARCHIVED_UNKNOWN_NOT_ACCEPTED")

    def status(self):
        m = self.master()
        self.validate_evidence(m, remote=False)
        canon = self.canonical(m)
        stage = "result" if canon["step"] == 2 or (self.root / "result-intent.json").exists() else "guard"
        return {**self.summary(stage, m, status="RECOVERY_RECONCILIATION_REQUIRED" if canon["pending"] is not None
            or not (self.root / (stage + "-observed.json")).exists() else "ARCHIVED_UNKNOWN_NOT_ACCEPTED" if canon["step"] == 2 else "ARCHIVAL_GUARD_OBSERVED"),
            "canonical_step": canon["step"], "pending": canon["pending"] is not None}

    def reconcile_preview(self, stage, reviewed=None):
        require(stage in ("guard", "result"), "Unsupported archival stage")
        m = self.master(); intent = read_private(self.root / (stage + "-intent.json"))
        self.validate_evidence(m); canon = self.canonical(m)
        payload = {"stage": stage, "master": digest(m), "intent": digest(intent), "canonical": canon}
        token, _ = self.live_grant("reconcile-" + stage, payload, reviewed)
        return self.summary(stage, m, token, "RECOVERY_RECONCILIATION_PROPOSED"), payload

    def reconcile(self, stage, *, reviewed, authorized):
        require(authorized is True, "Separately approve exact-stage recovery, not a replacement attempt")
        with invocation_lock(self.c.memory.control):
            _, payload = self.reconcile_preview(stage, reviewed)
            m = self.master(); original = read_private(self.root / (stage + "-intent.json"))
            completed = self.canonical(m)
            if completed["pending"] is None and (self.root / (stage + "-submitted.json")).exists() and (self.root / (stage + "-observed.json")).exists() \
                    and completed["step"] >= (1 if stage == "guard" else 2) and (stage == "guard" or (self.root / "archive.json").exists()):
                return self.status()  # Observation only; no new recovery grant consumption.
            def fence():
                require(read_private(self.master_path) == m and read_private(self.root / (stage + "-intent.json")) == original,
                        "Original archival intent or master changed during reconciliation")
                require(read_private(self.root / "reconciliations" / (digest(reviewed) + ".json")) == {"approval": reviewed, "payload": payload},
                        "Immutable reconciliation evidence changed")
                self.live_grant("reconcile-" + stage, payload, reviewed)
                self.validate_evidence(m)
                self.c.memory._owner(m["state"])
                canon = self.canonical(m)
                required = 0 if stage == "guard" else 1
                require(canon["step"] in (required, required+1)
                        and (canon["pending"] is None or canon["pending"]["base"] == original["payload"]["head"])
                        and canon["remote"] in (payload["canonical"]["remote"], canon["head"]), "Recovery effect or remote changed")
                self.live_grant("reconcile-" + stage, payload, reviewed)
            directory = self.root / "reconciliations"
            require(not directory.exists() or len(list(directory.glob("*.json"))) < 4
                    or (directory / (digest(reviewed) + ".json")).exists(), "Finite archival reconciliation grants exhausted")
            immutable(directory / (digest(reviewed) + ".json"), {"approval": reviewed, "payload": payload})
            if not (self.root / (stage + "-submitted.json")).exists():
                self.live_grant("reconcile-" + stage, payload, reviewed)
                # Record actual reconstruction authority/time BEFORE restoring
                # the exact original marker; never invent an old submission time.
                if submission_provenance(self.root, stage, original, m) is None:
                    immutable(self.root / "submission-provenance" / (stage + ".json"), {
                        "stage": stage, "intent": digest(original), "reconciliation": digest(reviewed), "prepared_at": self.c.clock()})
                self.live_grant("reconcile-" + stage, payload, reviewed)
                immutable(self.root / (stage + "-submitted.json"), {"subject": digest(original["payload"])})
            canon = self.canonical(m)
            if canon["pending"] is not None or canon["slots"]:
                self.c.memory.recover(before_effects=fence, expected_remote=canon["remote"], _fence=fence,
                    _purpose=journal_purpose(stage, original))
                canon = self.canonical(m)
            if canon["step"] == (0 if stage == "guard" else 1):
                require(canon["head"] == original["payload"]["head"], "Absent effect is not its exact original baseline")
                self._perform(stage, m, original["payload"], fence)
            else:
                require(canon["step"] == (1 if stage == "guard" else 2), "No observed transaction to reconcile; do not retry an absent submission")
            if stage == "result":
                with locked(self.c.memory.control):
                    self.live_grant("reconcile-" + stage, payload, reviewed)
                    require(self.canonical(m)["step"] == 2, "Accepted cleanup checkpoint changed")
                    self.c.memory._start()
                    row = self.c.worker(m["request"])
                    envelope = {"schema_version": 1, **row["assignment"], "result": self.c.workers.result(row)}
                    for path in self.c.memory._inbox():
                        require(path.name == key(row["assignment"]["assignment_id"]) + ".json" and read_private(path) == envelope, "Unrelated inbox blocks cleanup")
                        path.unlink(); sync_directory(path.parent)
            return self.finish(stage, m)

    def revoke(self, reviewed, *, authorized):
        require(authorized is True and type(reviewed) is str and reviewed.startswith("ae1:"), "Explicit exact approval revocation required")
        with invocation_lock(self.c.memory.control):
            self.c.memory._owner(self.c.memory.inspect(recovery=True)["state"])
            immutable(self.root / "revoked" / (digest(reviewed) + ".json"), {"approval_digest": digest(reviewed)})
        return {"status": "RECOVERY_APPROVAL_REVOKED", "rollback": "NOT_PERFORMED", "worker_stop": "NOT_INFERRED"}
