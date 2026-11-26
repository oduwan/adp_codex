"""Explicit two-file candidate copy; never a Developer success or acceptance."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from .config import safe_path
from .discovery_schema import digest, typed
from .execution_containment import admin_seal, source_seal
from .execution_memory import invocation_lock
from .git import git, value
from .guard_types import Permit, data
from .personal_history import archived
from .personal_recovery import grant, immutable
from .personal_storage import LIMIT, read_private
from .policy_types import Effect, Operation, Request
from .schema import fields, key, require
from .storage import atomic, locked, temporary_slot


def original_material(c, *, historical=False):
    require(c.episode, "Only the explicitly qualified same-Issue episode can adopt")
    m, archive, contexts = archived(c.personal.root, memory=c.memory, _child=c.personal)
    review = c.worker(c.record()["original_review"]) if historical else c.original_approval()
    if historical:
        from .personal_history import retained
        retained(c.runtime, review)
        task = c.memory.inspect()["tasks"][key(c.task_id)]
        job = task["assignments"][review["assignment"]["assignment_id"]]
        require(review["purpose"] == "original" and review["phase"] == "ACCOUNTED"
                and review["observation"]["result"]["outcome"] == "PASS" and review["observation"]["result"]["approved"] is True
                and review["observation"]["result"]["criteria"] == ["original"]
                and job["status"] == "accepted" and job["result"] == c.workers.result(review), "Historical scope judgment is not accepted")
    require(review["context"]["accounting_episode"]["adoption_scope"] == m["blueprint"]["material"]
            and review["observation"]["context_id"] not in contexts, "Fresh independent adoption-scope approval required")
    return m, archive, review


def adopted(c, *, historical=False):
    """Closed source-origin resolver; this deliberately creates no worker row."""
    receipt = read_private(c.personal.state / "adoption.json")
    fields(receipt, "schema_version kind episode archive original_request scope_review intent source manifest files")
    m, archive, review = original_material(c, historical=historical)
    intent = read_private(c.personal.state / "adoption-intent.json")
    require(receipt["schema_version"] == 1 and receipt["kind"] == "RETAINED_UNACCEPTED"
            and receipt["episode"] == c.personal.descriptor["episode"] and receipt["archive"] == digest(archive)
            and receipt["original_request"] == m["request"] and receipt["scope_review"] == digest(review)
            and receipt["intent"] == digest(intent) and receipt["manifest"] == m["blueprint"]["material"], "Retained candidate origin changed")
    # Authenticate historical approval without reusing it as future authority.
    from .personal_history import _historical_grant
    body = _historical_grant("adoption", digest(intent["payload"]), intent["submitted_at"],
                             intent["approval"], intent["grant"]["engine"])
    require(intent["grant"] == body and intent["payload"]["episode"] == receipt["episode"], "Candidate copy consent differs")
    for row in receipt["manifest"]:
        observed = read_private(c.personal.state / "adoption-files" / (digest(row["path"]) + ".json"))
        fields(observed, "file intent authorization")
        require(observed["file"] == row and observed["intent"] == digest(intent)
                and receipt["files"].get(row["path"]) == digest(observed), "Candidate copy lacks its exact durable per-file intent")
    return {"kind": "RETAINED_UNACCEPTED", "label": "adoption-" + digest(receipt),
            "authors": ["worker:" + m["request"]], "source": receipt["source"], "evidence": digest(receipt)}


class Adoption:
    def __init__(self, c):
        require(c.episode, "Select the explicitly activated accounting episode")
        self.c = c
        self.path = c.personal.state / "adoption-intent.json"

    def preview(self, reviewed=None):
        c = self.c
        c.fresh(); c.workers.fence()
        m, archive, review = original_material(c)
        row = c.record()
        require(row["phase"] == "DEVELOP" and row["developer"] is None and row["coordination"] is None
                and set(row["actions"]) == {"feature"} and not (c.personal.state / "adoption.json").exists()
                and not value(c.personal.feature, "status", "--porcelain", "--untracked-files=all"), "Select the pristine new child feature after scope review")
        payload = {"policy": "ACCOUNTING_EXPIRY_CONTINUATION", "episode": c.personal.descriptor["episode"],
            "archive": digest(archive), "scope_review": digest(review), "manifest": m["blueprint"]["material"],
            "checkpoint": c.memory.inspect()["local_head"], "source": source_seal(c.personal.feature),
            "outside": source_seal(c.personal.feature, tuple(r["path"] for r in m["blueprint"]["material"])),
            "admin": admin_seal(c.personal.feature), "preimage_modes": {r["path"]:
                stat.S_IMODE((c.personal.feature / r["path"]).lstat().st_mode) if r["before"] is not None else None
                for r in m["blueprint"]["material"]}}
        token, _ = grant("adoption", digest(payload), c.clock(), reviewed)
        return {"status": "CANDIDATE_ADOPTION_PROPOSED", "approval": token, "result": {
            "episode": payload["episode"], "files": payload["manifest"], "acceptance": "NOT_ACCEPTED",
            "effects": "Copy exact two candidate files only; no staging, commit, check or worker"}}, payload

    def fence(self, intent):
        c = self.c
        require(read_private(self.path) == intent, "Immutable candidate intent changed")
        grant("adoption", digest(intent["payload"]), c.clock(), intent["approval"])
        require(not (c.personal.root.state / "accounting-recovery" / "revoked" / (digest(intent["approval"]) + ".json")).exists(), "Candidate approval revoked")
        c.fresh(); c.workers.fence()
        m, archive, review = original_material(c)
        require(intent["payload"]["episode"] == c.personal.descriptor["episode"] and intent["payload"]["archive"] == digest(archive)
                and intent["payload"]["scope_review"] == digest(review) and intent["payload"]["manifest"] == m["blueprint"]["material"]
                and c.record()["developer"] is None and c.record()["phase"] in ("DEVELOP", "STAGE"), "Candidate subject changed")
        manifest = intent["payload"]["manifest"]
        ignored = [r["path"] for r in manifest]
        changed = False
        for row in manifest:
            target = safe_path(c.personal.feature / row["path"])
            record = read_private(c.personal.state / "adoption-files" / (digest(row["path"]) + ".json"), optional=True)
            temporary = safe_path(temporary_slot(target))
            if temporary.exists():
                info = temporary.lstat()
                raw = (c.personal.root.feature / row["path"]).read_bytes()
                require(record is not None and record["file"] == row and record["intent"] == digest(intent)
                        and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid()
                        and info.st_nlink == 1 and info.st_size <= len(raw) and raw.startswith(temporary.read_bytes()), "Unknown interrupted candidate copy slot")
                ignored.append(str(temporary.relative_to(c.personal.feature)))
                changed = True
            if target.exists():
                info = target.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                        and info.st_size <= 1048576 and not info.st_mode & 0o7022, "Unsafe candidate file")
                hashed = hashlib.sha256(target.read_bytes()).hexdigest()
                copied = record is not None and hashed == row["sha256"]
                require((copied and record["file"] == row and record["intent"] == digest(intent) and stat.S_IMODE(info.st_mode) in (0o600, row["mode"]))
                        or hashed == row["before"] and stat.S_IMODE(info.st_mode) == intent["payload"]["preimage_modes"][row["path"]],
                        "Candidate differs from exact base or submitted copy")
                changed |= copied
            else:
                require(row["before"] is None, "A tracked candidate preimage disappeared")
        require(admin_seal(c.personal.feature) == intent["payload"]["admin"]
                and source_seal(c.personal.feature, tuple(ignored)) == intent["payload"]["outside"]
                and (changed or source_seal(c.personal.feature) == intent["payload"]["source"]),
                "Foreign source/index/ref/admin changes cannot enter candidate adoption")
        grant("adoption", digest(intent["payload"]), c.clock(), intent["approval"])
        c.episode_fence()
        require(not (c.personal.root.state / "accounting-recovery" / "revoked" / (digest(intent["approval"]) + ".json")).exists()
                and intent["grant"]["issued_at"] <= c.clock() < intent["grant"]["expires_at"], "Candidate consent expired or revoked")

    def final_copy_fence(self, intent, permit):
        c = self.c
        state, task, item = c.guard._snapshot(c.task_id, permit.decision.baseline.requirement_id)
        active = c.guard._active(state, task, item, permit.token)
        c.memory._owner(state)
        c.episode_fence()
        require(not (c.personal.root.state / "accounting-recovery" / "revoked" / (digest(intent["approval"]) + ".json")).exists()
                and active["started"] <= c.clock() <= active["deadline"]
                and intent["grant"]["issued_at"] <= c.clock() < intent["grant"]["expires_at"], "Candidate copy lost original live grant/permit")

    def apply(self, *, reviewed, authorized):
        require(authorized is True, "Separately authorize this exact unaccepted candidate copy")
        c = self.c
        with invocation_lock(c.memory.control):
            intent = read_private(self.path, optional=True)
            if intent is None:
                _, payload = self.preview(reviewed)
                _, body = grant("adoption", digest(payload), c.clock(), reviewed)
                intent = {"approval": reviewed, "grant": body, "submitted_at": c.clock(), "payload": payload}
                immutable(self.path, intent)
            require(intent["approval"] == reviewed, "Candidate copy intent is one-use")
            if (c.personal.state / "adoption.json").exists():
                origin = adopted(c)
                return self.finish(intent, origin)
            self.fence(intent)
            permit = c.reserve("adoption:" + digest(intent))
            for row in intent["payload"]["manifest"]:
                self.copy(intent, row, permit)
            self.fence(intent)
            m, archive, review = original_material(c)
            receipt = {"schema_version": 1, "kind": "RETAINED_UNACCEPTED", "episode": c.personal.descriptor["episode"],
                "archive": digest(archive), "original_request": m["request"], "scope_review": digest(review),
                "intent": digest(intent), "source": source_seal(c.personal.feature), "manifest": m["blueprint"]["material"],
                "files": {r["path"]: digest(read_private(c.personal.state / "adoption-files" / (digest(r["path"]) + ".json")))
                          for r in m["blueprint"]["material"]}}
            immutable(c.personal.state / "adoption.json", receipt)
            return self.finish(intent, adopted(c))

    def copy(self, intent, row, permit):
        c = self.c
        self.fence(intent)
        source = safe_path(c.personal.root.feature / row["path"])
        raw = source.read_bytes()
        require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"], "Original candidate bytes changed")
        target = safe_path(c.personal.feature / row["path"])
        # No directory creation, deletions, rename, executable promotion or
        # symlink traversal. The approved two paths must have existing parents.
        require(target.parent.is_dir() and target.parent.stat().st_uid == os.getuid()
                and not target.parent.stat().st_mode & 0o022, "Candidate destination is not owned/protected")
        record_path = c.personal.state / "adoption-files" / (digest(row["path"]) + ".json")
        previous = read_private(record_path, optional=True)
        if target.exists():
            info = target.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                    and not info.st_mode & 0o7022 and info.st_size <= 1048576, "Unsafe candidate destination")
            current = hashlib.sha256(target.read_bytes()).hexdigest()
            if previous is not None and current == row["sha256"]:
                require(previous["intent"] == digest(intent) and previous["file"] == row, "Changed copy intent")
                if stat.S_IMODE(info.st_mode) != row["mode"]:
                    with locked(c.memory.control):
                        self.final_copy_fence(intent, permit)
                        os.chmod(target, row["mode"], follow_symlinks=False)
                return
            require(row["before"] is not None and current == row["before"], "Candidate preimage differs; do not overwrite")
        else:
            require(row["before"] is None, "Tracked candidate disappeared")
        provider, task = c.provider(c.personal.feature, permit)
        plan = provider.plan(task, Request(Operation.EDIT, summary=digest({"intent": digest(intent), "file": row}), paths=(row["path"],)))
        authorization = c.authority.authorize(plan)
        require(provider.decide(plan, authorization).effect == Effect.ALLOW, "M3 refused exact candidate path")
        if previous is None:
            immutable(record_path, {"intent": digest(intent), "file": row, "authorization": digest(data(plan))})
        else:
            require(previous["intent"] == digest(intent) and previous["file"] == row, "Per-file candidate intent changed")
        with locked(c.memory.control):
            self.fence(intent)
            require(provider.decide(plan, authorization).effect == Effect.ALLOW, "Exact copy lost current M3/M2 authority")
            self.final_copy_fence(intent, permit)
            atomic(target, raw)
            self.final_copy_fence(intent, permit)
            os.chmod(target, row["mode"], follow_symlinks=False)

    def finish(self, intent, origin):
        c = self.c
        self.fence(intent)
        row = c.record()
        if row["coordination"] is not None:
            require(row["coordination"]["label"] == "adoption:" + digest(intent), "Unrelated adoption reservation")
            c.conclude(typed(Permit, row["coordination"]["permit"]), "personal:retained-candidate:" + origin["evidence"], next_phase="STAGE")
        require(c.record()["phase"] == "STAGE", "Candidate accounting is incomplete")
        return {"status": "CANDIDATE_ADOPTED_UNACCEPTED", "origin": origin["evidence"], "developer": "NOT_RUN",
                "staging": "NOT_RUN", "commit": "NOT_RUN", "project_ci": "NOT_RUN", "acceptance": "NOT_ACCEPTED"}
