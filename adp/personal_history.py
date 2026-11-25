"""Authenticate immutable accounting history without reviving old authority."""
from __future__ import annotations

from pathlib import Path

from .accounting_policy import POLICY, entry
from .codex_runtime import CodexExecRuntime
from .discovery_schema import digest, typed
from .execution_containment import source_seal
from .execution_schema import worker_result
from .execution_types import RuntimeStatus, WorkerRequest
from .git import git, value
from .guard_types import data
from .personal_storage import LIMIT, load_state, read_private
from .schema import fields, key, require


def retained(runtime, row):
    """Read-only evidence proof, including during a pending canonical CAS."""
    identifier = row["request"]["id"]
    actual = runtime.observe(identifier)
    raw = read_private(runtime._path(identifier))
    stop = read_private(runtime.directory / (identifier + ".stop.json"))
    fields(stop, "request_digest pid status stopped cli_exit")
    worker_result(actual.result)
    require(actual.host == runtime.host == row["host"] and actual.request_digest == digest(row["request"])
            and data(actual) == row["observation"] and actual.status == RuntimeStatus.COMPLETED
            and actual.stopped is True and actual.context_id and raw["status"] == RuntimeStatus.COMPLETED
            and stop["request_digest"] == raw["request_digest"] == digest(row["request"])
            and type(stop["pid"]) is int and stop["pid"] > 0 and stop["pid"] == raw["pid"]
            and stop["status"] == "EXITED" and stop["stopped"] is True and type(stop["cli_exit"]) is int and stop["cli_exit"] == 0,
            "Original stopped runtime evidence differs")
    return {"worker": digest(row), "runtime": digest(raw), "stop": digest(stop)}


def archived(personal, *, memory=None, runtime=None, _child=None):
    return _archived_view(personal, memory=memory, runtime=runtime, _child=_child)[:3]


def _archived_view(personal, *, memory=None, runtime=None, _child=None):
    """Require actual retained raw records, exact H0→H1→H2 and permanent parent.

    No owner, expiry or terminal latch is renewed. A released owner is allowed
    only for historical observation; callers still need current live authority
    for every future effect.
    """
    from .personal_recovery import Recovery, engine_digest, grant, submission_provenance
    if _child is None:
        root = load_state(personal.directory)
    else:
        from .personal_episode import EpisodeState, FILE
        require(type(_child) is EpisodeState and _child.root == personal
                and read_private(_child.directory / FILE) == _child.descriptor
                and read_private(personal.directory / "personal.json") == personal.intent
                and read_private(Path(personal.plan["effects"]["marker"])) == {"schema_version": 1,
                    "directory": str(personal.directory), "approval": personal.intent["approval"]}, "Exact protected observation subject changed")
        root = personal
    memory = memory or root.memory()
    directory = root.state / "accounting-recovery"
    master = read_private(directory / "intent.json")
    receipt = read_private(directory / "archive.json")
    fields(receipt, "schema_version policy master initial guard result consents observations recovery")
    require(receipt["schema_version"] == 1 and receipt["policy"] == POLICY
            and receipt["master"] == digest(master) and master["engine"] == engine_digest(), "Archived policy/source proof changed")
    expected = ((master["state"], master["tasks"]), (master["guard_state"], master["tasks"]),
                (master["result_state"], master["result_tasks"]))
    heads = [receipt[n] for n in ("initial", "guard", "result")]
    require(heads[0] == master["view"]["checkpoint"], "Original archival checkpoint changed")
    from .personal_history_git import verify
    verify(memory, heads, expected, engine=master["engine"], host=master["view"]["binding"]["host"])
    require(type(receipt["recovery"]) is dict and len(receipt["recovery"]) <= 6, "Bounded recovery provenance required")
    for relative, hashed in receipt["recovery"].items():
        require(type(relative) is str and ".." not in Path(relative).parts and len(Path(relative).parts) == 2
                and Path(relative).parts[0] in ("reconciliations", "submission-provenance")
                and digest(read_private(directory / relative)) == hashed, "Exact historical recovery provenance changed")
    for stage in ("guard", "result"):
        submission_provenance(directory, stage, read_private(directory / (stage + "-intent.json")), master)
    for stage, index in (("guard", 0), ("result", 1)):
        intent = read_private(directory / (stage + "-intent.json"))
        fields(intent, "approval grant submitted_at payload")
        payload = {"policy": POLICY, "stage": stage, "master": digest(master), "head": heads[index],
                   "target": digest(list(expected[index+1]))}
        token, body = grant(stage, digest(payload), intent["submitted_at"], intent["approval"])
        require(intent["grant"] == body and intent["payload"] == payload
                and digest(intent) == receipt["consents"][stage]
                and read_private(directory / (stage + "-submitted.json")) == {"subject": digest(payload)}, "Original purpose-bound archival consent differs")
        observed = read_private(directory / (stage + "-observed.json"))
        require(observed == {"checkpoint": heads[index+1], "master": digest(master)}
                and digest(observed) == receipt["observations"][stage], "Archived observed checkpoint differs")
    now = memory.inspect(recovery=True)
    git(memory.config.root, "merge-base", "--is-ancestor", heads[-1], now["local_head"])
    task_key = master["view"]["binding"]["task_key"]
    require(now["state"]["generation"] == master["state"]["generation"]
            and now["state"]["owner"] in (None, master["state"]["owner"])
            and now["tasks"][task_key] == master["result_tasks"][task_key], "Archived task/assignment/generation was overwritten")
    require(now["state"]["progress_guard"]["task_epochs"][task_key] == master["result_state"]["progress_guard"]["task_epochs"][task_key]
            and all(now["state"]["progress_guard"]["requirements"].get(k) == v for k, v in
                master["result_state"]["progress_guard"]["requirements"].items()), "Historical guard inventory/epoch changed")
    from .personal_runner import PersonalCoordinator
    actual_runtime = runtime or CodexExecRuntime(root.state / "runtime")
    require(type(actual_runtime) is CodexExecRuntime, "Original genuine runtime observation required")
    from types import SimpleNamespace
    from .personal_workers import PersonalWorkers
    # Read-only parser view: no authority, guard, runtime dispatcher or mutation
    # method. Constructing a live Coordinator/Track here duplicated all loading
    # and proof work inside each nested observation.
    c = SimpleNamespace(personal=root, task_id=master["tasks"][task_key]["id"], path=root.state / "run.json", episode=False)
    run, proof = PersonalCoordinator.record(c), master["view"]["binding"]["evidence"]
    rows = PersonalWorkers(c).records()
    def worker(identifier):
        found = [r for r in rows if r["request"]["id"] == identifier]
        require(len(found) == 1, "Exact historical worker is missing")
        return found[0]
    require(digest(root.intent) == proof["enrollment"] and digest(run) == proof["run"]
            and digest(rows) == proof["inventory"], "Original enrollment/worker history changed")
    contexts = set()
    for label, identifier in (("developer", master["request"]), ("original", run["original_review"])):
        row = worker(identifier)
        request = typed(WorkerRequest, row["request"])
        raw = read_private(actual_runtime._path(identifier))
        stop = read_private(actual_runtime.directory / (identifier + ".stop.json"))
        actual = actual_runtime.observe(identifier)
        worker_result(actual.result)
        require({"worker": digest(row), "runtime": digest(raw), "stop": digest(stop)} == proof[label]
                and actual.host == row["host"] == actual_runtime.host and actual.request_digest == digest(request)
                and actual.status == RuntimeStatus.COMPLETED and actual.stopped is True and actual.context_id
                and actual.context_id not in contexts and row["observation"] == data(actual)
                and stop["request_digest"] == digest(request) and stop["pid"] == raw["pid"]
                and stop["stopped"] is True and stop["status"] == "EXITED" and type(stop["cli_exit"]) is int and stop["cli_exit"] == 0,
                "Original raw runtime/stop/context proof differs")
        Recovery.measurements(row, master["state"]["progress_guard"]["requirements"][row["requirement"]]["active"]["action"] if label == "developer" else None)
        contexts.add(actual.context_id)
    old = now["state"]["progress_guard"]["requirements"][worker(master["request"])["requirement"]]
    require(old == master["guard_state"]["progress_guard"]["requirements"][worker(master["request"])["requirement"]], "Historical STOP_UNSAFE latch changed")
    from .personal_history_product_git import administration
    PersonalCoordinator.check_administration(c, run, _reader=administration)
    require(source_seal(root.feature) == proof["seals"]["feature"]
            and source_seal(root.feature, tuple(root.plan["paths"])) == proof["seals"]["outside"]
            and (now["state"]["owner"] is None or source_seal(Path(root.plan["checkout"]["path"])) == proof["seals"]["outer"]),
            "Original unaccepted source material changed")
    relation = entry(now["state"])
    if relation is not None:
        require(relation["archive"] == digest(receipt) and relation["parent_task"] == task_key
                and relation["parent_guard"] == digest(old) and relation["parent_task_digest"] == digest(now["tasks"][task_key]), "Canonical historical lineage differs")
    validate_administration(root, master, relation, now, child=_child)
    # These are the actual observation and authenticated original inventory
    # already used in THIS proof. They are never retained between callbacks.
    return master, receipt, contexts, now, rows


def validate_administration(root, master, relation, observed, *, child=None):
    from .personal_recovery import administration_snapshot
    actual, before = administration_snapshot(root), master["administration"]
    if relation is None:
        require(actual == before, "Historical administration changed before episode installation")
        return
    from .personal_episode import episode_directory, load_episode
    child = child or load_episode(episode_directory(root))
    run = read_private(child.state / "run.json")
    require(actual["feature"] == before["feature"] and actual["outside"]["config"] == before["outside"]["config"]
            and actual["outside"]["ref"] == before["outside"]["ref"], "Original Git config/index/ref identity changed")
    target = "refs/heads/" + child.plan["feature"]["branch"]
    old_refs, new_refs = before["refs"], actual["refs"]
    changed = {name for name in old_refs.keys() | new_refs.keys() if old_refs.get(name) != new_refs.get(name)}
    allowed = {target}
    from .personal_history_track import later_windows, scope_proof, exact_ref, accepted_merge
    later = later_windows(child)
    for identity, coordinator in later:
        ref = "refs/heads/" + coordinator.personal.plan["feature"]["branch"]
        if ref in new_refs or ref in old_refs:
            scope_proof(coordinator)
            exact_ref(coordinator, new_refs)
        allowed.add(ref)
    if observed["state"]["owner"] is None and actual["outside"] != before["outside"]:
        # Historical observation after handoff may see the operator's normal
        # synchronization to the *already accepted* merge. This grants no effect.
        receipt = read_private(root.state / "track" / "accepted" / (digest(root.intent["original"]["identity"]) + ".json"))
        require(receipt["schema_version"] == 2 and receipt["directory"] == str(child.directory)
                and receipt["lineage"] == {k: v for k, v in relation.items() if k != "usage"}
                and not value(Path(root.plan["checkout"]["path"]), "status", "--porcelain", "--untracked-files=all"), "Unqualified historical default source change")
        merged = receipt["merge"]
        if actual["outside"]["head"] != merged:
            for identity, coordinator in later:
                candidate = read_private(coordinator.track.completion_path(identity), optional=True)
                if candidate is not None:
                    current = accepted_merge(coordinator, identity)
                    git(Path(root.plan["checkout"]["path"]), "merge-base", "--is-ancestor", merged, current)
                    merged = current
                if merged == actual["outside"]["head"]:
                    break
        require(actual["outside"]["head"] == merged, "Default source lacks exact accepted later completion")
        allowed |= {before["outside"]["ref"], "refs/remotes/" + root.plan["checkout"]["remote"] + "/" + root.plan["repository"]["default_branch"]}
        features = {target} | {"refs/heads/" + c.personal.plan["feature"]["branch"] for _, c in later}
        require(all(new_refs.get(n) == merged for n in changed - features), "Unrelated default/tracking ref change")
    else:
        require(actual["outside"] == before["outside"], "Original source/index changed before owner release")
    require(changed <= allowed, "Foreign Git ref drift is not an episode effect")
    if target not in new_refs:
        require(not run["actions"] or run["actions"].get("feature", {}).get("status") != "OBSERVED", "Observed child feature disappeared")
        return
    actions = run["actions"]
    feature = actions.get("feature")
    require(feature is not None and feature["operation"] == "BRANCH" and feature["target"] == target
            and feature["payload"]["start_revision"] == root.plan["checkout"]["head"], "Child ref lacks its original M7 CAS intent")
    from types import SimpleNamespace
    exact_ref(SimpleNamespace(personal=child, record=lambda: run), new_refs)
