"""Read-only proposal for one expired, stopped personal NOTRUN attempt.

This module cannot apply a disposition, issue consent, recover a checkpoint or
launch a worker. A proposal digest is evidence binding, never write authority.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .codex_runtime import CodexExecRuntime
from .discovery_schema import digest, typed
from .execution_containment import admin_seal, source_seal
from .execution_schema import fingerprint, sha
from .execution_types import Role, RuntimeStatus
from .git import git, value
from .guard import ProgressGuard
from .guard_types import Observation, Outcome, Permit, data
from .personal_storage import LIMIT, PersonalBlocked, assert_public, load_state, read_private
from .schema import bundle, encode, fields, key, require

EXPIRED_REASON = "An interrupted attempt exceeded containment; operator disposition required"


def _stopped(c, row):
    """Read actual retained records, including the separately bound stop file."""
    observed = c.workers.actual(row)
    runtime = read_private(c.runtime._path(row["request"]["id"]))
    encode(runtime, 32768)
    stop = read_private(c.runtime.directory / (row["request"]["id"] + ".stop.json"))
    encode(stop, 2048)
    fields(stop, "request_digest pid status stopped cli_exit")
    require(runtime["status"] == RuntimeStatus.COMPLETED and runtime["stopped"] is True
            and stop["request_digest"] == runtime["request_digest"] == digest(row["request"])
            and type(stop["pid"]) is int and stop["pid"] > 0 and stop["pid"] == runtime["pid"]
            and stop["status"] == "EXITED" and stop["stopped"] is True
            and type(stop["cli_exit"]) is int and stop["cli_exit"] == 0,
            "The original confirmed successful supervisor stop is unavailable")
    require(data(c.runtime._observation(row["request"]["id"], runtime)) == row["observation"] == data(observed),
            "Retained runtime and immutable worker observation differ")
    return {"worker": digest(row), "runtime": digest(runtime), "stop": digest(stop)}


def _seals(c, row, original):
    p = c.personal.plan
    outer, feature = Path(p["checkout"]["path"]), c.personal.feature
    c.check_administration(c.record())
    require(feature != outer and p["feature"]["prepare"], "Only the original isolated precommit attempt is supported")
    require(value(outer, "rev-parse", "HEAD") == value(feature, "rev-parse", "HEAD") == row["request"]["revision"] == p["checkout"]["head"]
            and value(outer, "symbolic-ref", "HEAD") == p["checkout"]["ref"]
            and value(feature, "symbolic-ref", "HEAD") == "refs/heads/" + p["feature"]["branch"]
            and not value(outer, "status", "--porcelain", "--untracked-files=all"), "Original source/ref/index changed")
    observed = {"feature": source_seal(feature), "outside": source_seal(feature, tuple(p["paths"])),
                "admin": admin_seal(feature), "outer": source_seal(outer), "outer_admin": admin_seal(outer)}
    require(observed["feature"] == row["result_source"] and observed["outside"] == row["outside"]
            and observed["admin"] == row["result_admin"] == row["admin"]
            and observed["outer"] == original["result_source"], "Retained source/admin/outside seals changed")
    return observed


def _terminal(state, tasks, requirement, assignment, result):
    """Predict the accepted abandon policy on copies, never canonical data."""
    terminal = deepcopy(state)
    item = terminal["progress_guard"]["requirements"][requirement]
    active = item["active"]
    measured = data(Observation(Outcome.UNKNOWN, (result["evidence"][0],), tuple(item["unresolved"])))
    ProgressGuard._account(item, active["action"], measured, False)
    item.update(last_event="attempt", last={"context": active["context"], "action": active["action"],
        "observation": measured, "counters": deepcopy(item["counters"])}, active=None)
    ProgressGuard._terminal(item, EXPIRED_REASON, unsafe=True)
    item["sequence"] += 1
    terminal["revision"] += 1
    accepted_state, accepted_tasks = deepcopy(terminal), deepcopy(tasks)
    job = accepted_tasks[assignment["task_key"]]["assignments"][assignment["assignment_id"]]
    job.update(status="accepted", result=result)
    accepted_state["revision"] += 1
    bundle(terminal, tasks, state["repository_id"])
    bundle(accepted_state, accepted_tasks, state["repository_id"])
    return terminal, accepted_state, accepted_tasks


def _proposal(c, request_id: str, *, checkpoint: str | None = None, expected: str | None = None) -> dict:
    """Observe only; expected binds a prior proposal, not an operator grant.

    Passing both the original checkpoint and proposal reference permits exact
    observation of guard-first/M1-second partial states. Unsupported variants
    fail closed. No operation here calls live(), save(), abandon() or accept().
    """
    fingerprint(request_id)
    require(type(c.runtime) is CodexExecRuntime, "The original supported runtime host is required")
    require((checkpoint is None) == (expected is None), "Reobservation needs both original checkpoint and reference")
    personal = load_state(c.personal.directory)
    require(personal.intent == c.personal.intent and personal.intent["phase"] == "ENROLLED", "Original enrollment changed")
    now = c.clock()
    p, run = personal.plan, c.record()
    require(type(now) is int and now >= p["window"]["expires_at"], "Archival proposal requires the expired original window")
    require(run is not None and run["phase"] == "DEVELOP" and run["coordination"] is None
            and run["developer"] is None and run["candidate"] is None and run["code_review"] is None
            and run["observations"] == 0 and not run["gates"] and not run["feedback"],
            "Only the original stopped precommit Developer attempt is supported")
    require(set(run["actions"]) == {"feature"}
            and all(a["status"] == "OBSERVED" and ("worktree" not in a or a["worktree"]["status"] == "OBSERVED")
                for a in run["actions"].values())
            and not any((personal.state / name).exists() for name in ("publication.json", "product.json")),
            "Unreconciled product or Git effects require separate disposition")
    row, original = c.worker(request_id), c.worker(run["original_review"])
    require(row["purpose"] == "develop" and row["phase"] == "STOPPED"
            and row["request"]["role"] == Role.DEVELOPER and row["request"]["workspace"] == str(personal.feature)
            and row["expires_at"] == p["window"]["expires_at"]
            and row["observation"]["result"]["outcome"] == Outcome.NOTRUN
            and row["observation"]["result"]["approved"] is False and row["observation"]["result"]["criteria"] == [],
            "Only the same stopped unapproved NOTRUN Developer can be proposed")
    observed = c.memory.inspect()
    require(observed["health"] == "SYNCED" and observed["local_owner"], "The original synchronized canonical owner is required")
    base = checkpoint or observed["local_head"]
    sha(base)
    git(c.memory.config.root, "merge-base", "--is-ancestor", base, observed["local_head"])
    state, tasks = c.memory._read_ref(base)
    task = tasks[key(c.task_id)]
    require(len(tasks) == 1 and len(task["assignments"]) == 2 and len(c.workers.records()) == 2,
            "Additional tasks/requests require separate archival design")
    job = task["assignments"][row["assignment"]["assignment_id"]]
    result = c.workers.result(row)
    envelope = {"schema_version": 1, **row["assignment"], "result": result}
    require(row["assignment"]["task_key"] == key(c.task_id)
            and job["worker"] == row["assignment"]["worker"] == "worker:" + request_id
            and job["generation"] == row["assignment"]["generation"] == row["request"]["generation"] == state["generation"] == run["generation"]
            and job["source_revision"] == row["assignment"]["source_revision"] == task["source_revision"] == row["request"]["revision"] == run["revision"]
            and job["status"] == "pending" and job["result"] is None,
            "Original M1 assignment/source/generation differs")
    item = state["progress_guard"]["requirements"][row["requirement"]]
    active = item["active"]
    permit = typed(Permit, row["permit"])
    require(item["mode"] == "normal" and active is not None and active["bounded"] is False
            and active["id"] == row["permit"]["token"] and item["campaign"] is None
            and active["context"] == row["guard_context"] == ProgressGuard._context(state, task)
            and active["action"]["actor"] == "worker:" + request_id
            and active["action"]["hypothesis"] == "worker:" + request_id
            and data(permit.decision.baseline) == data(c.guard._baseline(row["requirement"], state, task, item))
            and item["last"] is None and item["last_event"] is None and not any(item["counters"].values())
            and item["forensic_round"] == 0 and item["request"] is None and item["plan"] is None
            and not item["seen_facts"] and item["approval"] is None and item["campaign_runs"] == 0
            and active["started"] <= row["request"]["deadline"] <= active["deadline"] < now,
            "The exact expired original M2 reservation is required")
    require(original["purpose"] == "original" and original["phase"] == "ACCOUNTED"
            and original["observation"]["result"]["outcome"] == Outcome.PASS
            and original["observation"]["result"]["approved"] is True
            and original["observation"]["result"]["criteria"] == ["original"], "Historical original-scope evidence is missing")
    prior = task["assignments"][original["assignment"]["assignment_id"]]
    require(prior["status"] == "accepted" and prior["result"] == c.workers.result(original), "Historical scope assignment differs")
    evidence = {"developer": _stopped(c, row), "original": _stopped(c, original),
        "inventory": digest(c.workers.records()), "enrollment": digest(personal.intent), "run": digest(run),
        "seals": _seals(c, row, original),
        "track": {name: digest(read_private(personal.state / name, optional=True))
                  for name in ("track-link.json", "prepared-track.json")}}
    binding = {"schema_version": 1, "algorithm": "EXPIRED_NOTRUN_GUARD_FIRST_V1", "checkpoint": base,
        "repository_id": personal.repository_id, "task_key": key(c.task_id), "assignment": row["assignment"]["assignment_id"],
        "request": request_id, "request_digest": digest(row["request"]), "host": row["host"],
        "generation": state["generation"], "guard": digest(item),
        "window": {name: v for name, v in p["window"].items() if name != "nonce"}, "evidence": evidence}
    reference = "personal-archive-proposal:" + digest(binding)
    require(expected is None or expected == reference, "Archival proposal evidence changed; no prior reference is current")
    terminal, accepted_state, accepted_tasks = _terminal(state, tasks, row["requirement"], row["assignment"], result)
    current = (observed["state"], observed["tasks"])
    if current == (state, tasks):
        stage = "TERMINAL_GUARD_REQUIRED"
        steps = 0
    elif current == (terminal, tasks):
        stage = "M1_RECONCILIATION_REQUIRED"
        steps = 1
    elif current == (accepted_state, accepted_tasks):
        stage, steps = "TERMINAL_UNKNOWN_OBSERVED", 2
    else:
        raise PersonalBlocked("ARCHIVAL_STATE_CHANGED", "Preserve the exact checkpoint and effects for operator disposition.")
    require(int(value(c.memory.config.root, "rev-list", "--count", base + ".." + observed["local_head"])) == steps,
            "Canonical history contains unrelated changes")
    if steps:
        history = value(c.memory.config.root, "rev-list", "--parents", "--max-count=" + str(steps), observed["local_head"]).splitlines()
        require(all(len(line.split()) == 2 for line in history) and history[-1].split()[1] == base,
                "Archival history must contain only the exact linear checkpoints")
        if steps == 2:
            require(c.memory._read_ref(history[0].split()[1]) == (terminal, tasks),
                    "Guard-first disposition was not established by the intermediate checkpoint")
    inbox = c.memory._inbox()
    require(checkpoint is not None or not inbox, "Initial archival eligibility requires the original empty inbox")
    require(len(inbox) <= 1 and all(path.name == key(row["assignment"]["assignment_id"]) + ".json"
                                  and read_private(path) == envelope for path in inbox), "A conflicting or unrelated delivery exists")
    if stage == "TERMINAL_UNKNOWN_OBSERVED" and inbox:
        stage = "EXACT_ACCEPTED_INBOX_CLEANUP_REQUIRED"
    require(c.memory.inspect() == observed and load_state(personal.directory).intent == personal.intent
            and c.record() == run and digest(c.workers.records()) == evidence["inventory"]
            and _stopped(c, row) == evidence["developer"] and _stopped(c, original) == evidence["original"]
            and _seals(c, row, original) == evidence["seals"], "Evidence changed during read-only archival inspection")
    view = {"schema_version": 1, "status": "ARCHIVAL_PROPOSAL_ONLY", "mode": "READ_ONLY", "reference": reference,
        "checkpoint": base, "observed_checkpoint": observed["local_head"], "binding": binding, "stage": stage,
        "worker_outcome": "NOTRUN", "delivery_outcome": "UNKNOWN", "product_acceptance": "NOT_ACCEPTED",
        "abandon_evidence_reference": result["evidence"][0],
        "m2_disposition": {"outcome": "UNKNOWN", "decision": "STOP_UNSAFE", "reason": EXPIRED_REASON,
                           "meaning": "Overdue reservation accounting; no worker-process deadline breach is inferred"},
        "timeliness": "UNKNOWN: retained runtime/stop schemas have no absolute completion timestamp",
        "deadlines": {"request": row["request"]["deadline"], "reservation": active["deadline"], "window": p["window"]["expires_at"]},
        "budgets": {"worker": {n: row["request"][n] for n in ("seconds", "samples", "payload_bytes")},
                    "reservation": {n: active["action"][n] for n in ("seconds", "samples", "payload_bytes")},
                    "limits": item["limits"]},
        "counters": {"before": item["counters"], "after_abandon": terminal["progress_guard"]["requirements"][row["requirement"]]["counters"]},
        "execution_authority": "NOT_DELEGATED", "apply": "UNSUPPORTED_READ_ONLY_INTERFACE",
        "requirements": ["Separate exact operator approval of irreversible UNKNOWN/STOP_UNSAFE archival severity",
            "Durable immutable intent binding the full original request, receipts, seals, permit and checkpoint",
            "Expected baseline/permit revalidation inside the existing canonical mutation lock; not supplied by this preview",
            "Guard abandonment at actual current time FIRST; then exact M1 UNKNOWN delivery/accept or byte-equivalent cleanup",
            "Verify each canonical checkpoint after interruption; never blindly repeat, renew, dispatch or advance"],
        "fresh_window": "BLOCKED_OPERATOR_DESIGN_DECISION: retain old marker/history; no automatic same-Issue renewal or source adoption"}
    assert_public(view)
    encode(view, LIMIT)
    return view


def proposal(c, request_id: str, *, checkpoint: str | None = None, expected: str | None = None) -> dict:
    """Sanitized read-only boundary; malformed private data grants no effects."""
    from .errors import ADPError
    try:
        return _proposal(c, request_id, checkpoint=checkpoint, expected=expected)
    except PersonalBlocked:
        raise
    except (ADPError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise PersonalBlocked("ARCHIVAL_EVIDENCE_UNVERIFIED",
            "Retain the original request, stop proof, source seals and canonical checkpoint; no archival effect is authorized.",
            status="UNKNOWN") from exc
