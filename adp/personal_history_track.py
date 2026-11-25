"""Exact later-window Git provenance; never renew historical authority."""
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from .discovery_schema import digest, typed
from .discovery_types import Identity
from .guard_types import data
from .personal_storage import PersonalBlocked, load_state, read_private
from .schema import key, require

READ_TRANSPORT = ContextVar("accounting_historical_read_transport", default=None)


class NativeReadOnly:
    """Narrow an existing M7 native port to observations, never forge effects."""
    def __init__(self, transport):
        self.transport = transport

    def request(self, method, path, body, *, seconds):
        require(method == "GET" and body is None, "Historical native observation permits GET only")
        return self.transport.request(method, path, body, seconds=seconds)

    @property
    def last_response(self):
        return self.transport.last_response

    @last_response.setter
    def last_response(self, value):
        self.transport.last_response = value

    def __getattr__(self, name):
        return getattr(self.transport, name)


def cli_port(personal, supplied=None):
    """Select the existing M7 supervised read port before effective resolution.

    This is called only for ordinary operator CLI workflows, never archival
    host observation. Construction performs no auth lookup or request. Actual
    reads retain native credential/process/route/deadline enforcement.
    """
    link = read_private(personal.state / "track-link.json", optional=True)
    if link is None:
        return None
    index = read_private(Path(link["root"]) / "index.json")
    root = load_state(Path(index["first"]))
    from .personal_episode import episode_directory
    if not episode_directory(root).exists() or len(list((Path(link["root"]) / "links").glob("*.json"))) <= 1:
        return None
    if supplied is None:
        from .network_git import GitHubTarget
        from .personal_product_http import PersonalProductTransport
        p = personal.plan
        target = GitHubTarget(personal.repository_id, p["repository"]["node_id"], p["repository"]["database_id"],
            *p["repository"]["name"].split("/"), p["feature"]["branch"])
        supplied = PersonalProductTransport(target, protected_roots=(personal.feature,
            Path(p["checkout"]["path"]), root.directory, Path(__file__).resolve().parents[1]))
    # The native port still verifies immutable repository/account identity on
    # each real read. This pin grants neither write nor merge authority.
    supplied.bind_repository(root.plan["repository"]["node_id"], root.plan["repository"]["database_id"])
    return NativeReadOnly(supplied)


def with_reads(method):
    """Carry only an already selected read transport; never discover credentials."""
    @wraps(method)
    def observed(self, *args, **kwargs):
        transport = kwargs.get("transport")
        if transport is None and args:
            transport = getattr(args[0], "transport", None)
        if transport is None:
            service = getattr(self.c.transport, "service", None)
            transport = getattr(service, "transport", None)
        if transport is None:
            return method(self, *args, **kwargs)
        token = READ_TRANSPORT.set(transport)
        try:
            return method(self, *args, **kwargs)
        finally:
            READ_TRANSPORT.reset(token)
    return observed


def later_windows(first):
    """Closed native 1→2→3 attachment/consent proof, without links/effective."""
    from .personal_runner import PersonalCoordinator
    from .personal_track import LINK
    link_root = Path(read_private(first.state / LINK)["root"])
    if len(list((link_root / "links").glob("*.json"))) <= 1:
        return []  # No later ref can be authorized by this empty projection.
    coordinator = PersonalCoordinator(first, None, None)
    track = coordinator.track
    require(track is not None, "Retain the original native track")
    by_number = {o.issue.number: identity for identity, o in track.originals.items()}
    require(set(by_number) == {1, 2, 3}, "Only the original three-Issue chain qualifies")
    predecessor = coordinator
    result = []
    for number in (2, 3):
        identity = by_number[number]
        link = read_private(track.root / "links" / (digest(identity) + ".json"), optional=True)
        if link is None:
            require(number == 3 or not (track.root / "links" / (digest(by_number[3]) + ".json")).exists(),
                    "Later Issue has no admitted predecessor")
            break
        directory = track.root / "windows" / digest(identity)
        personal = load_state(directory)
        require(personal.intent["kind"] == "PERSONAL" and link["schema_version"] == 1
                and link["directory"] == str(directory) and personal.intent["original"] == data(track.originals[identity].issue)
                and read_private(personal.state / LINK) == link, "Later original attachment changed")
        c = PersonalCoordinator(personal, None, None)
        c.track.require_attachment()
        intent = predecessor.track.next_record()
        require(intent is not None and intent["setup"] == personal.intent["approval"]
                and intent["view"]["plan"] == personal.plan
                and intent["view"]["original"] == personal.intent["original"]
                and intent["view"]["governance"] == personal.intent["governance"]
                and link == {"schema_version": 1, "root": str(track.root), "index": track.link["index"],
                    "identity": data(identity), "directory": str(directory), "setup": personal.intent["approval"],
                    "snapshot": digest(intent["view"]["snapshot"]), "parent": predecessor.track.link["identity"]},
                "Later window lacks exact predecessor operator consent")
        receipts = {digest(by_number[n]): read_private(track.completion_path(by_number[n])) for n in range(1, number)}
        require(intent["view"]["completions"] == {i: digest(r) for i, r in receipts.items()}
                and all(r["acceptance"] == "OPERATOR_CONFIRMED_CURRENT_PROJECT_ACCEPTANCE" for r in receipts.values()),
                "Later admission lost its accepted prerequisite evidence")
        previous = receipts[digest(by_number[number - 1])]
        require(personal.plan["checkout"]["head"] == previous["merge"], "Later base is not its accepted predecessor")
        result.append((identity, c))
        predecessor = c
    return result


def scope_proof(c):
    """Historical stopped scope Reviewer, M1 assignment and exact original body."""
    from .personal_history import retained
    run = c.record()
    require(run is not None and run["original_review"] is not None, "Later ref has no independent original Reviewer")
    worker = c.worker(run["original_review"])
    retained(c.runtime, worker)
    require(worker["purpose"] == "original" and worker["phase"] == "ACCOUNTED"
            and worker["context"] == {**c.context("original"), "revision": c.personal.plan["checkout"]["head"]}
            and worker["observation"]["result"]["outcome"] == "PASS"
            and worker["observation"]["result"]["approved"] is True
            and worker["observation"]["result"]["criteria"] == ["original"], "Later scope judgment differs")
    observed = c.memory.inspect()
    task = observed["tasks"][key(c.task_id)]
    job = task["assignments"].get(worker["assignment"]["assignment_id"])
    require(observed["health"] == "SYNCED" and observed["state"]["progress_guard"]["schema_version"] == 1
            and job is not None and job["status"] == "accepted" and job["result"] == c.workers.result(worker)
            and job["worker"] == "worker:" + worker["request"]["id"]
            and job["generation"] == worker["request"]["generation"] == observed["state"]["generation"]
            and job["source_revision"] == worker["request"]["revision"] == c.personal.plan["checkout"]["head"],
            "Later scope lacks its actual canonical assignment")


def exact_ref(c, new_refs):
    from .config import Config
    from .git import value
    from .personal_history_product_git import HistoryReadPort, administration, observe
    p, run = c.personal.plan, c.record()
    target = "refs/heads/" + p["feature"]["branch"]
    feature = run["actions"].get("feature") if run else None
    require(feature is not None and feature["operation"] == "BRANCH" and feature["target"] == target
            and feature["payload"]["start_revision"] == p["checkout"]["head"], "Ref lacks its exact M7 feature intent")
    if target not in new_refs:
        require(feature["status"] != "OBSERVED", "Observed feature disappeared")
        return
    source = Path(p["checkout"]["path"]) if new_refs[target] == p["checkout"]["head"] else c.personal.feature
    port = HistoryReadPort(Config.discover(source, remote=p["checkout"]["remote"], repository_id=c.personal.repository_id),
        bound_git_directory=Path(administration(source)["directory"]["path"]))
    candidates = [feature] if new_refs[target] == p["checkout"]["head"] else [a for a in run["actions"].values()
        if a["operation"] == "COMMIT" and a["target"] == a["source_ref"] == target]
    matches = [a for a in candidates if (result := observe(port, a, new_refs[target])).status == "PRESENT" and result.revision == new_refs[target]
        and (a["observation"] is None or a["observation"] == data(result))]
    require(len(matches) == 1 and value(source, "merge-base", p["checkout"]["head"], new_refs[target]) == p["checkout"]["head"],
            "Current ref is not the exact native M7 effect with original ancestry")


def accepted_merge(c, identity):
    """Fresh native read is explicit; host-only observation cannot initialize it."""
    transport = READ_TRANSPORT.get()
    if transport is None:
        raise PersonalBlocked("HISTORICAL_NATIVE_READ_REQUIRED", "Use the enrolled read-only track status with an explicitly selected native read adapter; host-only archival observation cannot qualify a later merged base.")
    receipt = read_private(c.track.completion_path(identity))
    require(receipt["schema_version"] == 1 and c.personal.intent["kind"] == "PERSONAL"
            and c.memory.inspect()["state"]["progress_guard"]["schema_version"] == 1,
            "Later historical acceptance must retain the existing v1 rules")
    actual = c.track.accepted(identity, transport=transport, runtime=c.runtime)
    require(actual == receipt, "Later accepted completion changed")
    return actual["merge"]
