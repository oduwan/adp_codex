"""Authenticate immutable accounting history without reviving old authority."""
from __future__ import annotations

from pathlib import Path

from .accounting_policy import POLICY, entry, fingerprint
from .codex_runtime import CodexExecRuntime
from .discovery_schema import digest
from .errors import ADPError
from .execution_containment import source_seal
from .execution_schema import worker_result
from .execution_types import RuntimeStatus
from .git import git, value
from .guard_types import data
from .personal_storage import LIMIT, load_state, read_private
from .schema import fields, key, require


def _historical_grant(stage, subject, now, token, engine):
    """Decode an H3-bound original ae1 value; never issue or renew consent."""
    fingerprint(engine); fingerprint(subject)
    require(type(token) is str, "Original historical consent is missing")
    parts = token.split(":")
    require(stage in ("guard", "result", "episode", "reconcile-guard", "reconcile-result", "adoption")
            and len(parts) == 6 and parts[:2] == ["ae1", stage], "Wrong historical consent purpose")
    try:
        issued, expires, nonce = int(parts[2]), int(parts[3]), parts[4]
    except ValueError:
        raise ADPError("Malformed original consent interval") from None
    require(type(now) is int and 0 <= issued <= now < expires and 0 < expires - issued <= 3600
            and len(nonce) == 32 and all(c in "0123456789abcdef" for c in nonce), "Malformed original consent interval")
    body = {"policy": POLICY, "stage": stage, "subject": subject, "engine": engine,
        "issued_at": issued, "expires_at": expires, "nonce": nonce}
    require(token == ":".join(("ae1", stage, str(issued), str(expires), nonce, digest(body))), "Original historical consent differs")
    return body


def _anchor(root, memory, descriptor, master, receipt):
    """Authenticate the existing H3 before interpreting a historical engine."""
    from .personal_episode import episode_directory
    from .personal_history_git import verify
    from .policy_schema import sha
    activation = read_private(episode_directory(root) / "activation.json")
    fields(activation, "schema_version descriptor checkpoint relation")
    fields(receipt, "schema_version policy master initial guard result consents observations recovery")
    fields(master, "schema_version policy engine request view blueprint state tasks guard_state result_state result_tasks administration")
    require(type(activation["schema_version"]) is int and activation["schema_version"] == 1
            and type(receipt["schema_version"]) is int and receipt["schema_version"] == 1 and receipt["policy"] == POLICY
            and type(master["schema_version"]) is int and master["schema_version"] == 1 and master["policy"] == POLICY,
            "Unsupported historical basis encoding")
    sha(activation["checkpoint"])
    current = memory.inspect(recovery=True)
    require(current["health"] in ("SYNCED", "RECOVERY_REQUIRED"), "Historical basis requires an observable canonical checkpoint")
    installed = memory._read_ref(activation["checkpoint"])
    relation = entry(installed[0])
    require(relation is not None and entry(current["state"]) is not None, "Existing canonical historical basis required")
    fixed = {k: v for k, v in relation.items() if k != "usage"}
    require(fixed == {k: v for k, v in entry(current["state"]).items() if k != "usage"}
            and activation == {"schema_version": 1, "descriptor": digest(descriptor),
                "checkpoint": activation["checkpoint"], "relation": digest(fixed)}
            and relation["repository_id"] == root.repository_id and relation["issue_id"] == root.plan["issue_id"]
            and relation["episode"] == descriptor["episode"] == digest(descriptor["base"])
            and relation["plan"] == digest(descriptor["plan"]) and relation["grant"] == digest(descriptor["approval"])
            and relation["archive"] == digest(receipt) == descriptor["base"]["archive"]
            and relation["blueprint"] == digest(master["blueprint"]) == descriptor["base"]["blueprint"]
            and receipt["master"] == digest(master) and receipt["result"] == relation["checkpoints"]["result"]
            and current["state"]["generation"] == installed[0]["generation"] == relation["generation"],
            "Historical Git basis, descriptor or canonical lineage differs")
    objects = verify(memory, [receipt["result"], activation["checkpoint"]],
        [(master["result_state"], master["result_tasks"]), installed])
    for remote, _, _ in objects:
        git(memory.pinned_local_remote if remote else memory.config.root, "--no-replace-objects", "merge-base", "--is-ancestor",
            activation["checkpoint"], current["remote_head" if remote else "local_head"])
    fingerprint(master["engine"])
    require(master["engine"] == descriptor["base"]["engine"], "Original descriptor and archive engines differ")
    return {"historical_basis": {"schema_version": 1, "checkpoint": activation["checkpoint"], "relation_digest": digest(fixed)},
        "historical_engine": master["engine"], "historical_objects": objects, "subject": current, "installed": installed}


def _reader_binding(capture):
    """Project a successfully consumed cold proof into an existing consent."""
    from .personal_read_frame import reader_engine
    from .policy_schema import sha
    basis = capture["historical_basis"]
    fields(basis, "schema_version checkpoint relation_digest")
    require(type(basis["schema_version"]) is int and basis["schema_version"] == 1, "Unsupported historical basis")
    sha(basis["checkpoint"]); fingerprint(basis["relation_digest"]); fingerprint(capture["historical_engine"])
    return {"historical_basis": dict(basis), "historical_engine": capture["historical_engine"], "reader_engine": reader_engine(capture)}


def current_history(memory, master, receipt, now, *, basis=None):
    """Fresh canonical lineage; never authenticate historical bytes twice."""
    require(now["health"] in ("SYNCED", "RECOVERY_REQUIRED"), "Canonical history is unavailable")
    task_key = master["view"]["binding"]["task_key"]
    require(now["state"]["generation"] == master["state"]["generation"]
            and now["state"]["owner"] in (None, master["state"]["owner"])
            and now["tasks"][task_key] == master["result_tasks"][task_key], "Archived task/assignment/generation was overwritten")
    require(now["state"]["progress_guard"]["task_epochs"][task_key] == master["result_state"]["progress_guard"]["task_epochs"][task_key]
            and all(now["state"]["progress_guard"]["requirements"].get(k) == v for k, v in
                master["result_state"]["progress_guard"]["requirements"].items()), "Historical guard inventory/epoch changed")
    relation = entry(now["state"])
    if relation is not None:
        old = master["result_state"]["progress_guard"]["requirements"].get(relation["parent_requirement"])
        require(old is not None and relation["archive"] == digest(receipt) and relation["parent_task"] == task_key
                and relation["parent_guard"] == digest(old) and relation["parent_task_digest"] == digest(now["tasks"][task_key]),
                "Canonical historical lineage differs")
    if basis is not None:
        require(relation is not None and digest({k: v for k, v in relation.items() if k != "usage"}) == basis["relation_digest"],
                "Canonical H3 relation changed")
        for root, head in ((memory.config.root, now["local_head"]), (memory.pinned_local_remote, now["remote_head"])):
            git(root, "--no-replace-objects", "merge-base", "--is-ancestor", basis["checkpoint"], head)
    else:
        git(memory.config.root, "--no-replace-objects", "merge-base", "--is-ancestor", receipt["result"], now["local_head"])


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


def _archived_view(personal, *, memory=None, runtime=None, _child=None, _capture=None):
    """Require actual retained raw records, exact H0→H1→H2 and permanent parent.

    No owner, expiry or terminal latch is renewed. A released owner is allowed
    only for historical observation; callers still need current live authority
    for every future effect.
    """
    from .personal_read_frame import archive
    framed = archive(personal, memory, runtime, _child, _capture=_capture)
    if framed is not None:
        return framed
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
    anchored = None
    if _child is not None:
        anchored = _anchor(root, memory, _child.descriptor, master, receipt)
    else:
        from .personal_episode import episode_directory, load_episode
        if (episode_directory(root) / "activation.json").exists():
            _child = load_episode(episode_directory(root))
            anchored = _anchor(root, memory, _child.descriptor, master, receipt)
    fields(receipt, "schema_version policy master initial guard result consents observations recovery")
    require(receipt["schema_version"] == 1 and receipt["policy"] == POLICY
            and receipt["master"] == digest(master) and (anchored is not None or master["engine"] == engine_digest()), "Archived policy/source proof changed")
    expected = ((master["state"], master["tasks"]), (master["guard_state"], master["tasks"]),
                (master["result_state"], master["result_tasks"]))
    heads = [receipt[n] for n in ("initial", "guard", "result")]
    require(heads[0] == master["view"]["checkpoint"], "Original archival checkpoint changed")
    from .personal_history_git import verify
    objects = verify(memory, heads, expected)
    if _capture is not None and anchored is not None:
        from .personal_history_git import combine
        _capture.update(anchored)
        _capture["historical_objects"] = combine(anchored["historical_objects"], objects)
    require(type(receipt["recovery"]) is dict and len(receipt["recovery"]) <= 6, "Bounded recovery provenance required")
    for relative, hashed in receipt["recovery"].items():
        require(type(relative) is str and ".." not in Path(relative).parts and len(Path(relative).parts) == 2
                and Path(relative).parts[0] in ("reconciliations", "submission-provenance")
                and digest(read_private(directory / relative)) == hashed, "Exact historical recovery provenance changed")
    for stage in ("guard", "result"):
        original = read_private(directory / (stage + "-intent.json"))
        if anchored is None:
            submission_provenance(directory, stage, original, master)
        else:
            from .personal_recovery import _submission_record
            restored = _submission_record(directory, stage, original, master)
            if restored is not None:
                marker, record = restored
                _historical_grant("reconcile-" + stage, digest(record["payload"]), marker["prepared_at"], record["approval"], master["engine"])
    for stage, index in (("guard", 0), ("result", 1)):
        intent = read_private(directory / (stage + "-intent.json"))
        fields(intent, "approval grant submitted_at payload")
        payload = {"policy": POLICY, "stage": stage, "master": digest(master), "head": heads[index],
                   "target": digest(list(expected[index+1]))}
        body = (_historical_grant(stage, digest(payload), intent["submitted_at"], intent["approval"], master["engine"])
            if anchored is not None else grant(stage, digest(payload), intent["submitted_at"], intent["approval"])[1])
        require(intent["grant"] == body and intent["payload"] == payload
                and digest(intent) == receipt["consents"][stage]
                and read_private(directory / (stage + "-submitted.json")) == {"subject": digest(payload)}, "Original purpose-bound archival consent differs")
        observed = read_private(directory / (stage + "-observed.json"))
        require(observed == {"checkpoint": heads[index+1], "master": digest(master)}
                and digest(observed) == receipt["observations"][stage], "Archived observed checkpoint differs")
    now = memory.inspect(recovery=True)
    if anchored is not None:
        require(all(anchored["subject"][n] == now[n] for n in
            ("health", "local_head", "remote_head", "state", "tasks", "local_owner", "inbox_count",
             "recovery_slots", "recovery_journal")), "Canonical historical subject advanced")
    current_history(memory, master, receipt, now, basis=anchored["historical_basis"] if anchored else None)
    task_key = master["view"]["binding"]["task_key"]
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
        context = row["observation"]["context_id"]
        require(retained(actual_runtime, row) == proof[label] and context not in contexts,
                "Original raw runtime/stop/context proof differs")
        Recovery.measurements(row, master["state"]["progress_guard"]["requirements"][row["requirement"]]["active"]["action"] if label == "developer" else None)
        contexts.add(context)
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
    validate_administration(root, master, relation, now, child=_child, _capture=_capture)
    # These are the actual observation and authenticated original inventory
    # already used in THIS proof. They are never retained between callbacks.
    return master, receipt, contexts, now, rows


def validate_administration(root, master, relation, observed, *, child=None, _capture=None):
    from .personal_recovery import administration_snapshot
    actual, before = administration_snapshot(root), master["administration"]
    if _capture is not None:
        from copy import deepcopy
        _capture["historical_administration"] = deepcopy(actual)
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
