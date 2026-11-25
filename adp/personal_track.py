"""Explicit finite personal track composition, never a second task database.

The index contains immutable original/evidence links. Dispositions are derived
from actual M4 observations and canonical per-Issue M1/M2/effect histories.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

from .discovery import complete_snapshot
from .discovery_schema import digest, typed
from .discovery_types import Issue, Snapshot
from .execution_memory import invocation_lock
from .execution_types import RuntimeObservation, RuntimeStatus, WorkerRequest
from .git import git, value
from .guard_types import Outcome, data
from .personal_enrollment import PersonalChoices, apply_personal, plan_personal, selection
from .personal_storage import (LIMIT, PersonalBlocked, approval, create_private, load_state,
    read_private)
from .policy_schema import fingerprint, sha
from .schema import encode, fields, key, require
from .storage import atomic, locked
from .ticket_preparation import TicketArchive
from .personal_history_track import with_reads
from .runtime_limits import network_operation, read_operation

LINK = "track-link.json"


def immutable(path, body):
    create_private(path.parent)
    if path.exists():
        require(read_private(path) == body, "Immutable track evidence conflicts")
    else:
        atomic(path, encode(body, LIMIT), replace=False)


def content(path, body):
    reference = digest(body)
    immutable(path / (reference + ".json"), body)
    return reference


def same_observation(a, b):
    """Only the time of an otherwise identical GET observation may differ."""
    return replace(a, observed_at=0) == replace(b, observed_at=0)


class PersonalTrack:
    def __init__(self, coordinator):
        self.c, self.personal = coordinator, coordinator.personal
        self.link = read_private(self.personal.state / LINK)
        fields(self.link, "schema_version root index identity directory setup snapshot parent" +
               (" episode original_link" if coordinator.episode else ""))
        fingerprint(self.link["index"]); fingerprint(self.link["snapshot"])
        require(type(self.link["schema_version"]) is int and self.link["schema_version"] == (2 if coordinator.episode else 1)
                and self.link["directory"] == str(self.personal.directory)
                and self.link["setup"] == self.personal.intent["approval"]
                and self.link["identity"] == self.personal.intent["original"]["identity"], "Track link identity differs")
        self.root = Path(self.link["root"])
        self.index = read_private(self.root / "index.json")
        fields(self.index, "schema_version repository first originals")
        require(self.index["schema_version"] == 1 and type(self.index["schema_version"]) is int
                and digest(self.index) == self.link["index"]
                and self.index["repository"] == self.personal.plan["repository"]
                and type(self.index["originals"]) is list and 1 <= len(self.index["originals"]) <= 8,
                "Original finite track identity changed")
        first = load_state(Path(self.index["first"]))
        require(self.root == first.state / "track" and first.plan["repository"] == self.index["repository"],
                "Track evidence root differs from the original enrollment")
        require((self.root / "archive").is_dir(), "Retain the original archive; observation cannot recreate missing evidence")
        self.archive = TicketArchive(self.root / "archive", protected_roots=(self.personal.feature,
            Path(self.personal.plan["checkout"]["path"]), self.c.memory.path, Path(__file__).resolve().parents[1]))
        originals = [self.archive.original(r) for r in self.index["originals"]]
        require(len({o.issue.identity for o in originals}) == len(originals)
                and all(o.repository.id == self.personal.repository_id for o in originals)
                and any(data(o.issue.identity) == self.link["identity"] for o in originals), "Ambiguous track originals")
        self.originals = {o.issue.identity: o for o in originals}
        registration = read_private(self.root / "registration.json")
        fields(registration, "view approval")
        view = registration["view"]
        fields(view, "schema_version repository setup numbers snapshot checkpoint")
        binding = {**view, "snapshot": data(replace(typed(Snapshot, view["snapshot"]), observed_at=0))}
        require(type(view["schema_version"]) is int and view["schema_version"] == 1
                and registration["approval"] == "personal-track:" + digest(binding)
                and view["repository"] == self.index["repository"]
                and view["setup"] == first.intent["approval"]
                and sorted(view["numbers"]) == sorted(o.issue.number for o in originals)
                and read_private(first.state / LINK)["snapshot"] == digest(view["snapshot"]),
                "Retain the exact original track selection/approval evidence")

    @staticmethod
    @read_operation("track.registration", transport=lambda c, numbers: c.transport)
    def registration(c, numbers):
        require(type(numbers) is tuple and 1 <= len(numbers) <= 8 and len(set(numbers)) == len(numbers)
                and all(type(n) is int and n > 0 for n in numbers), "Select a finite original Issue inventory")
        c.live()
        require(c.record() is None, "Select the track before the first scope context; never adopt/reset executed work")
        require(c.personal.plan["checkout"]["ref"] == "refs/heads/" + c.personal.plan["repository"]["default_branch"]
                and c.personal.plan["feature"]["prepare"], "Track mode requires a clean default-branch source and isolated features")
        observation = c.fresh()
        PersonalTrack.native_base(c)
        snapshot = observation.snapshot
        require(complete_snapshot(snapshot), "Complete native discovery required")
        originals = [i for i in snapshot.issues if i.number in numbers]
        require(len(originals) == len(numbers) and c.personal.plan["issue"] in numbers
                and all(i.state == "open" for i in originals), "Observed open original Issues required")
        view = {"schema_version": 1, "repository": c.personal.plan["repository"], "setup": c.personal.intent["approval"],
            "numbers": sorted(numbers), "snapshot": data(snapshot), "checkpoint": c.memory.inspect()["local_head"]}
        binding = {**view, "snapshot": data(replace(snapshot, observed_at=0))}
        return view, "personal-track:" + digest(binding)

    @staticmethod
    def native_base(c):
        """Observe the actual default ref before a new original admission."""
        from .discovery_github import GitHubDiscoveryAdapter
        from .policy_schema import sha
        p = c.personal.plan
        parser = GitHubDiscoveryAdapter(p["repository"]["name"], c.transport, max_requests=1)
        parser._halt, parser._requests = False, 0
        response = parser._get("/repos/" + p["repository"]["name"] + "/branches/" + quote(p["repository"]["default_branch"], safe=""))
        row = response.body
        require(response.status == 200 and not parser._halt and type(row) is dict
                and row.get("name") == p["repository"]["default_branch"] and type(row.get("commit")) is dict,
                "UNKNOWN: native default source identity unavailable")
        sha(row["commit"].get("sha"))
        require(row["commit"]["sha"] == p["checkout"]["head"], "Current native base differs from original admission source")
        return row["commit"]["sha"]

    @classmethod
    @read_operation("track.register", transport=lambda cls, c, numbers, **k: c.transport)
    def register(cls, c, numbers, *, reviewed, authorized):
        require(authorized is True, "Separately approve original-track evidence writes")
        with invocation_lock(c.memory.control):
            path = c.personal.state / LINK
            if path.exists():
                track = cls(c)
                require(sorted(o.issue.number for o in track.originals.values()) == sorted(numbers), "Original track cannot be replaced")
                return track
            require(not c.episode, "Accounting episode must retain its original track attachment")
            view, token = cls.registration(c, numbers)
            require(token == reviewed, "Track original observation changed; review again")
            root = c.personal.state / "track"
            create_private(root)
            retained = read_private(root / "registration.json", optional=True)
            if retained is not None:
                expected = {**retained["view"], "snapshot": data(replace(typed(Snapshot, retained["view"]["snapshot"]), observed_at=0))}
                current = {**view, "snapshot": data(replace(typed(Snapshot, view["snapshot"]), observed_at=0))}
                require(retained["approval"] == reviewed and expected == current, "Original track registration changed")
                view = retained["view"]
            else:
                immutable(root / "registration.json", {"view": view, "approval": reviewed})
            archive = TicketArchive(root / "archive", protected_roots=(c.personal.feature,
                Path(c.personal.plan["checkout"]["path"]), c.memory.path, Path(__file__).resolve().parents[1]))
            snapshot = typed(Snapshot, view["snapshot"])
            references = [archive.frozen_reference(i.identity) or archive.freeze(snapshot, i.identity)
                for i in sorted(snapshot.issues, key=lambda i: i.number) if i.number in numbers]
            index = {"schema_version": 1, "repository": view["repository"], "first": str(c.personal.directory), "originals": references}
            immutable(root / "index.json", index)
            from .personal_track_preparation import unsigned_policy
            _, source, claims = unsigned_policy(c)
            immutable(root / "admissions" / (digest(c.personal.intent["original"]["identity"]) + ".json"),
                {"policy_snapshot": data(source), "policy_sources": [data(claim) for claim in claims], "completions": []})
            snapshot_reference = content(root / "observations", data(snapshot))
            link = {"schema_version": 1, "root": str(root), "index": digest(index),
                "identity": c.personal.intent["original"]["identity"], "directory": str(c.personal.directory),
                "setup": c.personal.intent["approval"], "snapshot": snapshot_reference, "parent": None}
            immutable(root / "links" / (digest(link["identity"]) + ".json"), link)
            immutable(path, link)
            c.track = cls(c)
            return c.track

    def links(self):
        from .personal_read_frame import json_names
        paths = sorted((self.root / "links").glob("*.json"))
        json_names(self.root / "links", [p.name for p in paths])
        require(1 <= len(paths) <= len(self.originals), "Track links exceed original finite inventory")
        rows = [read_private(p) for p in paths]
        effective_rows = []
        for p, row in zip(paths, rows):
            personal = load_state(Path(row["directory"]))
            require(p.stem == digest(row["identity"]) and row["index"] == self.link["index"]
                    and read_private(personal.state / LINK) == row and row["setup"] == personal.intent["approval"]
                    and row["identity"] == personal.intent["original"]["identity"], "Retain exact original enrollment links")
            from .personal_episode import effective
            current = effective(personal)
            effective_rows.append(read_private(current.state / LINK))
        require(len({digest(r["identity"]) for r in rows}) == len(rows), "Duplicate original task link")
        return effective_rows

    def admission_path(self):
        return (self.personal.state / "episode-admission.json" if self.c.episode else
                self.root / "admissions" / (digest(self.link["identity"]) + ".json"))

    def admission(self):
        return read_private(self.admission_path())

    def completion_path(self, identity):
        require(identity in self.originals, "Completion outside original track")
        return self.root / "accepted" / (digest(identity) + ".json")

    def seed(self):
        snapshot = typed(Snapshot, read_private(self.root / "observations" / (self.link["snapshot"] + ".json")))
        require(digest(snapshot) == self.link["snapshot"] and complete_snapshot(snapshot), "Original admission snapshot unavailable")
        return snapshot

    def original_issue(self, identity, observed):
        require(identity in self.originals and observed.identity == identity, "Wrong original Issue identity")
        expected = self.originals[identity].issue
        pointer = read_private(self.root / "links" / (digest(identity) + ".json"), optional=True)
        from .personal_episode import effective
        pointed = effective(load_state(Path(pointer["directory"]))) if pointer is not None else None
        known_report = read_private(pointed.state / "report.json", optional=True) if pointed is not None else None
        if observed == expected and (known_report is None or known_report["after"] is None):
            return True
        link = next((r for r in self.links() if r["identity"] == data(identity)), None)
        require(link is not None, "An unadmitted original Issue changed")
        personal = load_state(Path(link["directory"]))
        report = read_private(personal.state / "report.json", optional=True)
        if report is not None and report["after"] is not None:
            from .personal_product import PersonalProduct
            require(report["approval"] == PersonalProduct.token(report["view"], report["binding"])
                    and observed == typed(Issue, report["after"]), "Original source changed after the authorized own report")
            canonical = personal.memory().inspect()["state"]["execution"]
            action = canonical["actions"].get(report["action"])
            require(action is not None and action["operation"] == "REPORT" and action["status"] == "OBSERVED"
                    and action["payload"]["body"] == report["view"]["body"] and action["payload"]["target"] == observed.url
                    and canonical["publications"].get(report["action"], {}).get("reference") == report["observation"]["reference"],
                    "Own comment delta lacks its canonical exact report receipt")
            observed = typed(Issue, report["before"])
            if observed == expected:
                return True
        # Own native PR links are the accepted #41 relation-only reconciliation.
        product = read_private(personal.state / "product.json", optional=True)
        require(product is not None and product["pull"] is not None, "Original scope/version changed")
        from .personal_product_review import original_with_own_relation
        original_with_own_relation(data(expected), observed, product["pull"], self.index["repository"]["name"])
        return True

    def require_attachment(self):
        shared = read_private(self.root / "links" / (digest(self.link["identity"]) + ".json"), optional=True)
        admission = read_private(self.admission_path(), optional=True)
        require((shared == self.link if not self.c.episode else digest(shared) == self.link["original_link"]
                 and self.link["episode"] == self.personal.descriptor["episode"]
                 and admission == self.personal.descriptor["base"]["admission"])
                and admission is not None,
                "Complete the original next intent/track attachment before any execution")
        fields(admission, "policy_snapshot policy_sources completions")
        self.seed()  # Existence alone is not a qualified immutable snapshot.

    @with_reads
    def current(self):
        p = self.personal.plan
        observation, owner = selection(Path(p["checkout"]["path"]), p["checkout"]["remote"], self.personal.repository_id, self.c.transport)
        require(owner == p["owner"] and observation.repository == self.index["repository"]
                and complete_snapshot(observation.snapshot), "Current repository, ownership or native inventory is unknown")
        found = {i.identity: i for i in observation.snapshot.issues}
        require(self.originals.keys() <= found.keys(), "An original task is missing")
        for identity in self.originals:
            self.original_issue(identity, found[identity])
        return observation

    @with_reads
    def accepted(self, identity, *, transport=None, runtime=None):
        """Read historical facts without reviving an expired execution grant."""
        path = self.completion_path(identity)
        from .personal_read_frame import present
        if not present(path):
            return None
        receipt = read_private(path)
        fields(receipt, "schema_version identity directory setup checkpoint accepted_at original packet source tree merge actor pull merge_payload workers run product ci files acceptance" +
               (" lineage origin" if receipt["schema_version"] == 2 else ""))
        for field in ("checkpoint", "source", "tree", "merge"):
            sha(receipt[field])
        for field in ("run", "product"):
            fingerprint(receipt[field])
        require(type(receipt["workers"]) is dict and 1 <= len(receipt["workers"]) <= 7, "Bounded original worker inventory required")
        for identifier, hashed in receipt["workers"].items():
            fingerprint(identifier); fingerprint(hashed)
        personal = load_state(Path(receipt["directory"]))
        episode = personal.intent["kind"] == "ACCOUNTING_EPISODE"
        require(receipt["schema_version"] == (2 if episode else 1) and receipt["identity"] == data(identity)
                and receipt["setup"] == personal.intent["approval"] and receipt["original"] == data(self.originals[identity])
                and personal.plan["window"]["issued_at"] <= receipt["accepted_at"] < personal.plan["window"]["expires_at"]
                and receipt["acceptance"] == "OPERATOR_CONFIRMED_CURRENT_PROJECT_ACCEPTANCE",
                "Accepted original/window/project acceptance evidence differs")
        memory = personal.memory()
        now = memory.inspect()
        require(now["health"] == "SYNCED", "Historical M1 state is not synchronized")
        if any(action["operation"] == "REPORT" for action in now["state"]["execution"]["actions"].values()):
            require(present(personal.state / "report.json"), "Retain the private receipt for the known canonical report effect")
        git(memory.config.root, "merge-base", "--is-ancestor", receipt["checkpoint"], now["local_head"])
        state, tasks = memory._read_ref(receipt["checkpoint"])
        task_id = personal.task_id if episode else "personal:" + digest({"repository": personal.repository_id, "issue": personal.plan["issue_id"]})
        task = tasks[key(task_id)]
        require(state["generation"] == now["state"]["generation"] and task["source_revision"] == receipt["source"]
                and task == now["tasks"][key(task_id)]
                and now["state"]["owner"] in (None, state["owner"])
                and now["state"]["progress_guard"]["task_epochs"][key(task_id)] == state["progress_guard"]["task_epochs"][key(task_id)]
                and all(a["status"] == "accepted" for a in task["assignments"].values()),
                "Historical source, generation or assignments changed/incomplete")
        from .personal_episode import settled_guards
        require(settled_guards(personal, state),
                "Historical M2 has an unfinished/terminal reservation")
        for relative, hashed in receipt["files"].items():
            require(relative.startswith(("evidence/", "product-checks/")) and ".." not in Path(relative).parts
                    and digest(read_private(personal.state / relative)) == hashed, "Historical private check/policy proof missing")
        run = read_private(personal.state / "run.json")
        product_record = read_private(personal.state / "product.json")
        if digest(run) != receipt["run"]:
            # A REPORT is a new, independently authorized action after accepted
            # completion. Only its actual live submitted reservation may overlay
            # coordination; no source/worker/check/product change is ignored.
            report = getattr(self.c, "product", None)
            coordination = run.get("coordination")
            require(personal.directory == self.personal.directory and report is not None
                    and callable(getattr(report, "report_record", None)) and coordination is not None,
                    "Accepted run changed outside the exact REPORT reservation")
            intent = report.report_record()
            require(intent is not None and intent["view"]["operation"] == "REPORT"
                    and coordination["label"] == "personal-report:" + intent["action"]
                    and coordination["permit"] == intent["reservation"]
                    and coordination["requirement"] == intent["requirement"]
                    and report.write_authorized() is True, "Unqualified REPORT reservation overlay")
            run = {**run, "coordination": None}
        require(digest(run) == receipt["run"] and digest(product_record) == receipt["product"]
                and product_record["gates"][-1] == receipt["ci"], "Accepted product/source ledger changed")
        from .codex_runtime import CodexExecRuntime
        actual_runtime = runtime or CodexExecRuntime(personal.state / "runtime")
        require(type(actual_runtime) is CodexExecRuntime, "Historical genuine runtime evidence required")
        contexts = set()
        from .personal_workers import ROLES, PersonalWorkers
        from .execution_schema import worker_result
        workers = [read_private(personal.state / "workers" / (identifier + ".json")) for identifier in receipt["workers"]]
        require({path.stem for path in (personal.state / "workers").glob("*.json")} == set(receipt["workers"]),
                "Historical worker inventory changed")
        for worker in workers:
            request = typed(WorkerRequest, worker["request"])
            require(digest(worker) == receipt["workers"][request.id] and request.role == ROLES[worker["purpose"]][0],
                    "Historical role/request record differs")
            actual = actual_runtime.observe(request.id)
            assignment = task["assignments"].get(worker["assignment"]["assignment_id"])
            require(type(actual) is RuntimeObservation and data(actual) == worker["observation"]
                    and actual.status == RuntimeStatus.COMPLETED and actual.stopped is True
                    and actual.request_digest == digest(request) and actual.context_id is not None
                    and actual.context_id not in contexts and worker["phase"] == "ACCOUNTED"
                    and request.generation == state["generation"] and request.task_id == task_id
                    and assignment is not None and assignment["worker"] == "worker:" + request.id
                    and assignment["generation"] == request.generation and assignment["source_revision"] == request.revision
                    and assignment["result"] == PersonalWorkers.result(worker),
                    "Historical stopped independent worker/M1 evidence differs")
            worker_result(actual.result)
            require(worker["purpose"] != "develop" or actual.result.approved is False, "Developer cannot self-approve")
            contexts.add(actual.context_id)
        for purpose, field in (("original", "original_review"), ("code", "code_review"), ("product", "review")):
            identifier = product_record[field] if purpose == "product" else run[field]
            worker = next((w for w in workers if w["request"]["id"] == identifier), None)
            require(worker is not None and worker["purpose"] == purpose
                    and worker["observation"]["result"]["approved"] is True
                    and worker["observation"]["result"]["outcome"] == "PASS"
                    and worker["observation"]["result"]["criteria"] == [purpose]
                    and (purpose == "original" or worker["request"]["revision"] == receipt["source"]),
                    "Actual independent exact-source acceptance is missing")
        packet = self.archive.packet(receipt["packet"])
        require(packet.identity == identity and packet.original_issue_revision == self.originals[identity].issue.revision
                and packet.original_reference == self.archive.frozen_reference(identity)
                and packet.allowed_paths == tuple(personal.plan["paths"])
                and packet.checks == tuple(personal.plan["required_check_names"]), "Accepted immutable packet differs")
        gate = receipt["ci"]
        require(gate["status"] in ("PASS", "NOT_REQUIRED") and 0 <= receipt["accepted_at"] - gate["observed_at"] <= 300,
                "Actual project evidence was missing/stale at acceptance")
        if gate["status"] == "PASS":
            require(gate["qualified"] is True and gate["gate"]["request"]["revision"] == receipt["source"]
                    and gate["gate"]["request"]["repository_id"] == personal.repository_id,
                    "Accepted CI is not genuine exact-source evidence")
        else:
            require(gate["verified_absence"] is True and gate["revision"] == receipt["source"], "No-check status is not PASS/absence proof")
        from .personal_product import PersonalProduct
        from .personal_product_review import ProductCoordinator
        coordinator = ProductCoordinator(personal, None, None, runtime=actual_runtime, clock=self.c.clock)
        if episode:
            relation, old_contexts = personal.active()
            require(receipt["lineage"] == {k: v for k, v in relation.items() if k != "usage"}
                    and receipt["origin"] == coordinator.source_origin(historical=True) and not contexts & old_contexts,
                    "Qualified terminal lineage, retained source or independent successor evidence differs")
        product = PersonalProduct(coordinator, transport=transport)
        require(product.port._value("rev-parse", "HEAD") == receipt["source"]
                and product.port._value("rev-parse", "HEAD^{tree}") == receipt["tree"]
                and not product.port._value("status", "--porcelain", "--untracked-files=all"),
                "Historical accepted local source/ref is no longer exact and clean")
        with product.service.bounded():
            observed = product.forge.observe(digest(receipt), "MERGE", receipt["merge_payload"], attempted=True)
            item = product.pull(allow_merged=True)
            require(observed.status == "PRESENT" and observed.revision == receipt["merge"]
                    and item.get("merged_by", {}).get("id") == receipt["actor"], "Current exact merged result/actor changed")
        return receipt

    @with_reads
    def prerequisites(self, observation, *, transport=None, runtimes=None):
        require(complete_snapshot(observation.snapshot), "Native dependency coverage is unknown")
        issues = {i.identity: i for i in observation.snapshot.issues}
        selected = typed(Issue, self.personal.intent["original"])
        self.original_issue(selected.identity, issues[selected.identity])
        from .discovery import DependencyPlanner
        planned = DependencyPlanner(clock=self.c.clock).plan((observation.snapshot,))
        cyclic = {identity for component in planned.cycles for identity in component}
        native = {candidate.identity: candidate.prerequisites for candidate in planned.candidates}
        pending, done = [selected.identity], set()
        while pending:
            identity = pending.pop()
            if identity in done:
                continue
            require(identity in self.originals and identity in issues and identity not in cyclic,
                    "A native prerequisite is missing or cyclic")
            self.original_issue(identity, issues[identity])
            for edge in issues[identity].relations:
                if edge.kind != "BLOCKED_BY" or edge.confidence != "NATIVE":
                    continue
                matches = [i for i in issues if i.repository_id == identity.repository_id
                    and i.issue_id == edge.target.issue_id and issues[i].number == edge.target.number
                    and edge.target.repository == observation.repository["name"]]
                require(len(matches) == 1 and matches[0] != selected.identity and matches[0] in native[identity],
                        "Missing/ambiguous/cyclic native prerequisite")
                dependency = matches[0]
                require(self.accepted(dependency, transport=transport,
                    runtime=(runtimes or {}).get(dependency)) is not None, "Native prerequisite lacks actual accepted completion")
                pending.append(dependency)
            done.add(identity)
        return tuple(sorted(done - {selected.identity}))

    def publication_prerequisites(self):
        """Fresh receipt facts; the caller separately reobserves ALL raw originals.

        The immutable admission graph selects opaque IDs only. It is neither a
        current observation nor a cached READY/acceptance grant. Publication's
        exact complete raw-map comparison proves its native edges still agree
        with the full actual preflight, which already qualified this closure.
        """
        from .discovery import DependencyPlanner
        from .discovery_types import Identity
        snapshot = self.seed()
        planned = DependencyPlanner(clock=self.c.clock).plan((snapshot,))
        native = {candidate.identity: candidate.prerequisites for candidate in planned.candidates}
        issues = {issue.identity: issue for issue in snapshot.issues}
        cyclic = {identity for component in planned.cycles for identity in component}
        selected = typed(Identity, self.link["identity"])
        pending, done = [selected], set()
        while pending:
            identity = pending.pop()
            if identity in done:
                continue
            require(identity in self.originals and identity in issues and identity in native and identity not in cyclic,
                    "Original publication closure is missing or cyclic")
            edges = lambda issue: {r for r in issue.relations if r.kind == "BLOCKED_BY" and r.confidence == "NATIVE"}
            require(edges(issues[identity]) == edges(self.originals[identity].issue),
                    "Admission prerequisite identities differ from the frozen original")
            if identity != selected:
                require(self.accepted(identity) is not None, "Publication requires actual current accepted prerequisite evidence")
            pending.extend(native[identity])
            done.add(identity)
        return tuple(sorted(done - {selected}))

    @network_operation("track.completion_preview", service=lambda self, product, **k: product.service)
    def completion_preview(self, product):
        from .personal_episode import settled_guards
        c = product.c
        c.live(); c.fresh(); c.workers.fence(); c.original_approval(); c.verify_local_review()
        product.qualified(); product.verify_review()
        require(read_private(self.personal.state / "prepared-track.json", optional=True) is not None,
                "Accepted TicketPreparer packet is required")
        result = product.status()
        require(result["status"] in ("MERGED_DELEGATED_VERIFIED", "MERGED_EXTERNALLY_VERIFIED"),
                "Waiting/manual/unqualified merge cannot complete a dependency")
        current = c.memory.inspect()
        require(c.record()["coordination"] is None and all(w["phase"] == "ACCOUNTED" for w in c.workers.records())
                and all(a["status"] == "OBSERVED" for a in current["state"]["execution"]["actions"].values())
                and settled_guards(self.personal, current["state"])
                and not product.service.unconfirmed_contexts(), "Reconcile all original M1/M2/process/effect evidence")
        item = product.pull(allow_merged=True)
        view = {"repository": self.index["repository"], "identity": self.link["identity"],
            "source": c.revision(), "tree": product.port._value("rev-parse", "HEAD^{tree}"),
            "merge": result["revision"], "actor": item["merged_by"]["id"], "pull": result["pull"],
            "original": digest(self.originals[typed(Issue, self.personal.intent["original"]).identity]),
            "checkpoint": current["local_head"], "ci": product.validation_binding(), "review": product.record()["review"],
            "expires_at": self.personal.plan["window"]["expires_at"]}
        return {"status": "COMPLETION_PROPOSED", "result": view, "approval": "personal-completion:" + digest(view)}

    @network_operation("track.complete", service=lambda self, product, **k: product.service)
    def complete(self, product, *, reviewed, authorized, confirm_acceptance):
        require(not self.c.episode, "ACCOUNTING_WRITER_CUTOVER_PENDING: no new accounting acceptance")
        require(authorized is True and confirm_acceptance is True, "Separately confirm this original's actual project acceptance")
        identity = typed(Issue, self.personal.intent["original"]).identity
        with invocation_lock(self.c.memory.control):
            path = self.completion_path(identity)
            if path.exists():
                return self.accepted(identity, transport=product.transport, runtime=product.c.runtime)
            proposal = self.completion_preview(product)
            require(proposal["approval"] == reviewed, "Exact completion evidence changed")
            view, row = proposal["result"], product.record()
            intent = next((i for i in reversed(row["intents"]) if i["view"]["operation"] == "MERGE"), None)
            source = intent or next(i for i in row["intents"] if i["view"]["operation"] == "PR")
            v = source["view"]
            payload = {"pull": {k: row["pull"][k] for k in ("id", "number", "repository_id", "url")},
                "revision": view["source"], "head_ref": product.target.ref, "base_ref": v["facts"]["base_ref"],
                "expected_base": v["facts"]["base_sha"], "source_tree": view["tree"],
                "method": v["method"] if intent else "merge", "envelope": "HEAD_ATOMIC_BASE_OBSERVED"}
            files = {}
            for directory in ("evidence", "product-checks"):
                for file in (self.personal.state / directory).glob("*.json"):
                    files[directory + "/" + file.name] = digest(read_private(file))
            receipt = {"schema_version": 1, "identity": data(identity), "directory": str(self.personal.directory),
                "setup": self.personal.intent["approval"], "checkpoint": view["checkpoint"], "accepted_at": self.c.clock(),
                "original": data(self.originals[identity]), "packet": read_private(self.personal.state / "prepared-track.json")["packet"],
                "source": view["source"], "tree": view["tree"], "merge": view["merge"], "actor": view["actor"], "pull": row["pull"],
                "merge_payload": payload, "workers": {w["request"]["id"]: digest(w) for w in self.c.workers.records()},
                "run": digest(self.c.record()), "product": digest(row), "ci": row["gates"][-1],
                "files": files, "acceptance": "OPERATOR_CONFIRMED_CURRENT_PROJECT_ACCEPTANCE"}
            if self.c.episode:
                from .accounting_policy import entry
                receipt.update(schema_version=2, lineage={k: v for k, v in entry(self.c.memory.inspect()["state"]).items() if k != "usage"},
                               origin=self.c.source_origin())
            immutable(path, receipt)
            return self.accepted(identity, transport=product.transport, runtime=product.c.runtime)

    @read_operation("track.status", transport=lambda self, **k: k.get("transport") or self.c.transport)
    @with_reads
    def status(self, *, transport=None, runtimes=None):
        from .personal_episode import settled_guards
        from .discovery import DependencyPlanner, review_subject
        from .discovery_types import Identity, ReadinessReview, Status
        from .guard_types import Attestation
        observation = self.current()
        snapshot, completed, receipts = observation.snapshot, {}, {}
        links = self.links()
        active = []
        for link in links:
            identity = typed(Identity, link["identity"])
            accepted = self.accepted(identity, transport=transport, runtime=(runtimes or {}).get(identity))
            personal = load_state(Path(link["directory"]))
            state = personal.memory().inspect()
            require(state["health"] == "SYNCED", "Track M1 history is not synchronized")
            require(all(a["status"] == "OBSERVED" for a in state["state"]["execution"]["actions"].values())
                    and settled_guards(personal, state["state"])
                    and not list(personal.memory().control.glob("network-stop-*.json")),
                    "A previous window has an unfinished/uncertain effect or reservation")
            if accepted is not None:
                completed[identity] = accepted
            else:
                active.append(identity)
        require(len(active) <= 1, "Only one uncompleted original/window may be active")
        reviews = []
        for identity, accepted in sorted(completed.items()):
            original = self.originals[identity]
            review = ReadinessReview(identity, "Complete the unchanged original " + original.issue.url,
                ("original-ticket:" + original.issue.revision,), (accepted["packet"],),
                specification="KNOWN", policy="KNOWN", completed=True,
                observed_at=snapshot.observed_at, expires_at=snapshot.observed_at + 300)
            subject = review_subject((snapshot,), review)
            evidence = Attestation("personal:historical-disposition", "personal-completion:" + digest(accepted), subject)
            receipts[subject] = evidence
            reviews.append(replace(review, evidence=evidence))
        # A still-current prepared original may be READY observationally. This
        # rebinds only the time of identical GET content, retains its old expiry
        # and checks the actual live independent receipt; it grants no execution.
        for identity in active:
            link = next(r for r in links if r["identity"] == data(identity))
            personal = load_state(Path(link["directory"]))
            prepared = read_private(personal.state / "prepared-track.json", optional=True)
            if prepared is None:
                continue
            from .personal_runner import PersonalCoordinator
            current = PersonalCoordinator(personal, self.c.transport, self.c.ci_transport,
                runtime=(runtimes or {}).get(identity), clock=self.c.clock)
            if same_observation(current.track.seed(), snapshot):
                worker = current.original_approval()
                packet = self.archive.packet(prepared["packet"])
                require(prepared["worker"] == worker["request"]["id"] and packet.identity == identity,
                        "Actual current prepared scope provenance differs")
                review = ReadinessReview(identity, packet.goal,
                    tuple(clause.text for clause in packet.clauses if clause.kind == "ACCEPTANCE"),
                    ("personal:prepared-policy:" + packet.policy_digest,), specification="KNOWN", policy="KNOWN",
                    observed_at=snapshot.observed_at, expires_at=personal.plan["window"]["expires_at"])
                subject = review_subject((snapshot,), review)
                evidence = Attestation("worker:" + worker["request"]["id"], "personal-prepared:" + digest(prepared), subject)
                receipts[subject] = evidence
                reviews.append(replace(review, evidence=evidence))

        class HistoricalAuthority:
            def verify(self, evidence, *, purpose, subject):
                return purpose == "discovery/readiness" and receipts.get(subject) == evidence

        planned = DependencyPlanner(authority=HistoricalAuthority(), clock=self.c.clock).plan((snapshot,), reviews=tuple(reviews))
        by_identity = {candidate.identity: candidate for candidate in planned.candidates}
        eligible, rows = [], []
        for identity, original in sorted(self.originals.items(), key=lambda row: row[1].issue.number):
            candidate = by_identity[identity]
            blockers = [self.originals[dependency].issue.number if dependency in self.originals else "UNKNOWN"
                for dependency in candidate.prerequisites if by_identity[dependency].status != Status.DONE]
            status = str(candidate.status)
            if identity not in completed and blockers:
                # Display native blocking alongside, not instead of, actual M4
                # semantic readiness. No unreviewed task is called READY.
                status = "BLOCKED_DEPENDENCY"
            if (not active and not planned.cycles and identity not in completed and not blockers
                    and candidate.status == Status.NEEDS_SPEC and candidate.issue.state == "open"):
                eligible.append(identity)
            rows.append({"issue": original.issue.number, "identity": data(identity), "status": status,
                "m4_status": str(candidate.status), "native_blockers": blockers,
                "completion": "VERIFIED_HISTORICAL_ACCEPTANCE_CURRENT_MERGE" if identity in completed else "NOT_ACCEPTED"})
        next_identity = eligible[0] if len(eligible) == 1 else None
        return {"status": "COMPLETE" if len(completed) == len(self.originals) else "ACTIVE_ORIGINAL" if active
                else "NEXT_SCOPE_REQUIRED" if next_identity else "BLOCKED", "issues": rows,
            "next_issue": self.originals[next_identity].issue.number if next_identity else None,
            "next_admission": "NOT_AUTHORIZED", "native_observed_at": snapshot.observed_at,
            "genuine_runtime_qualification": "NOTRUN"}, observation, completed

    def next_record(self):
        row = read_private(self.personal.state / "next-intent.json", optional=True)
        if row is not None:
            fields(row, "view approval setup")
            view = row["view"]
            fields(view, "schema_version index parent parent_checkpoint parent_generation completions plan snapshot original governance")
            snapshot = typed(Snapshot, view["snapshot"])
            binding = {**view, "snapshot": data(replace(snapshot, observed_at=0))}
            require(type(view["schema_version"]) is int and view["schema_version"] == 1
                    and row["approval"] == "personal-next:" + digest(binding) and row["setup"] == approval(view["plan"])
                    and view["index"] == self.link["index"] and view["parent"] == self.link["identity"]
                    and complete_snapshot(snapshot), "Original next-intent schema/consent/observation changed")
            sha(view["parent_checkpoint"])
        return row

    def successor(self, view):
        """Inspect setup AND attachment, not merely personal.json presence."""
        plan = view["plan"]
        directory = Path(plan["effects"]["directory"])
        if not (directory / "personal.json").exists():
            return None, False
        child = load_state(directory)
        require(child.plan == plan and child.intent["approval"] == approval(plan), "Next enrollment differs from durable intent")
        expected = {"schema_version": 1, "root": str(self.root), "index": self.link["index"],
            "identity": view["original"]["identity"], "directory": str(directory), "setup": approval(plan),
            "snapshot": digest(view["snapshot"]), "parent": self.link["identity"]}
        local = read_private(child.state / LINK, optional=True)
        shared = read_private(self.root / "links" / (digest(expected["identity"]) + ".json"), optional=True)
        admission = read_private(self.root / "admissions" / (digest(expected["identity"]) + ".json"), optional=True)
        require(local in (None, expected) and shared in (None, expected), "Conflicting successor attachment; no adoption")
        attached = (local == shared == expected and admission is not None
            and (self.root / "observations" / (expected["snapshot"] + ".json")).exists())
        if not attached:
            require(not (child.state / "run.json").exists(), "Execution before full attachment requires explicit reconciliation")
        if child.intent["phase"] == "ENROLLED" and attached:
            state = child.memory().inspect()
            require(state["health"] == "SYNCED" and state["local_owner"] and state["state"]["generation"] == 1,
                    "Reconcile the original successor M1 owner/state; do not reenroll")
            from .personal_runner import PersonalCoordinator
            inspector = PersonalCoordinator(child, self.c.transport, self.c.ci_transport, clock=self.c.clock)
            inspector.track.require_attachment()
            return child, True
        return child, False

    @network_operation("track.next_preview", service=lambda self, product, choices, **k: product.service)
    @with_reads
    def next_preview(self, product, choices, *, approved=None):
        require(not self.c.episode, "ACCOUNTING_WRITER_CUTOVER_PENDING: NEXT requires historical reader binding")
        from .git import SHA
        require(type(choices) is PersonalChoices, "Typed explicit next choices required")
        retained = self.next_record()
        if retained is not None:
            plan = retained["view"]["plan"]
            require(retained["setup"] == approval(plan) and retained["view"]["index"] == self.link["index"]
                    and choices.issue == plan["issue"] and choices.directory == Path(plan["effects"]["directory"])
                    and tuple(plan["paths"]) == choices.paths and choices.branch in (None, plan["feature"]["branch"])
                    and choices.workspace in (None, Path(plan["feature"]["workspace"]))
                    and choices.commit_message in (None, plan["commit_message"]) and choices.commit_body == plan["commit_body"]
                    and set(plan["required_check_names"]) == set(choices.checks) |
                        {name for branch in plan["branch_rules"] for name in branch["required_check_contexts"]}
                    and choices.accept_native_job_records == plan["accept_native_job_records"]
                    and choices.seconds == plan["window"]["expires_at"] - plan["window"]["issued_at"],
                    "Retain the exact original next scope/choices; no replacement window")
            child, complete = self.successor(retained["view"])
            if complete:
                return {"status": "NEXT_ALREADY_ENROLLED", "result": {"plan": plan, "original": retained["view"]["original"],
                    "snapshot": retained["view"]["snapshot"], "completions": retained["view"]["completions"],
                    "recovery": "Reconnect to the original next directory/window; no new authority or budget."},
                    "approval": None, "setup_approval": None}
            require(self.c.clock() < plan["window"]["expires_at"], "The original next window expired; never renew this intent")
            _, observation, completed = self.status(transport=product.transport)
            require(same_observation(observation.snapshot, typed(Snapshot, retained["view"]["snapshot"]))
                    and {digest(i): digest(r) for i, r in completed.items()} == retained["view"]["completions"],
                    "Retained next intent no longer matches current native/acceptance evidence")
            return {"status": "NEXT_PROPOSED_RETAINED", "result": retained["view"],
                "approval": retained["approval"], "setup_approval": retained["setup"]}
        state, observation, completed = self.status(transport=product.transport)
        require(state["status"] == "NEXT_SCOPE_REQUIRED" and state["next_issue"] == choices.issue,
                "Exactly one independently eligible original needs a new explicit scope/window")
        p = self.personal.plan
        with product.service.bounded():
            facts = product.facts()
        base = facts["base_sha"]
        root = Path(p["checkout"]["path"])
        try:
            require(SHA.fullmatch(value(root, "rev-parse", "--verify", base + "^{commit}")), "Exact base is not a commit")
        except Exception as error:
            raise PersonalBlocked("NEXT_BASE_UNAVAILABLE", "Synchronize the project's owned source to its actual native default/base commit, then obtain a fresh next proposal; ADP does not fetch objects.") from error
        require(observation.checkout["head"] == base
                and observation.checkout["ref"] == facts["base_ref"]
                and not value(root, "status", "--porcelain", "--untracked-files=all"),
                "Select the clean current native default/base source; tree equivalence is insufficient")
        expected_directory = self.root / "windows" / digest(next(i for i, o in self.originals.items() if o.issue.number == choices.issue))
        require(choices.directory == expected_directory, "Next window has one immutable deterministic evidence destination")
        plan, original, docs = plan_personal(observation, p["owner"], choices, approved=approved,
            ci_transport=self.c.ci_transport, clock=self.c.clock)
        require(original == data(next(o.issue for o in self.originals.values() if o.issue.number == choices.issue)),
                "Next original version/scope changed")
        checkpoint = self.c.memory.inspect()
        view = {"schema_version": 1, "index": self.link["index"], "parent": self.link["identity"],
            "parent_checkpoint": checkpoint["local_head"], "parent_generation": checkpoint["state"]["generation"],
            "completions": {digest(i): digest(r) for i, r in completed.items()}, "plan": plan,
            "snapshot": data(observation.snapshot), "original": original, "governance": docs}
        # Actual observation time is retained, but it grants no scope/authority;
        # repeating the same complete GET contents cannot change the consent.
        binding = {**view, "snapshot": data(replace(observation.snapshot, observed_at=0))}
        return {"status": "NEXT_PROPOSED", "result": view,
            "approval": "personal-next:" + digest(binding), "setup_approval": approval(plan)}

    @network_operation("track.next", service=lambda self, product, choices, **k: product.service)
    @with_reads
    def next(self, product, choices, *, reviewed, setup_approval, authorized):
        require(not self.c.episode, "ACCOUNTING_WRITER_CUTOVER_PENDING: no accounting-parent handoff or enrollment")
        require(authorized is True and type(choices) is PersonalChoices,
                "Separately approve exactly this new original task, local setup and finite scope/window")
        path = self.personal.state / "next-intent.json"
        with locked(self.root):
            retained = self.next_record()
            if retained is None:
                proposal = self.next_preview(product, choices, approved=setup_approval)
                require(proposal["approval"] == reviewed, "Next source, original, policy, completion or window changed")
                retained = {"view": proposal["result"], "approval": reviewed, "setup": setup_approval}
                immutable(path, retained)  # before releasing old ownership or claiming another Issue
            require(retained["approval"] == reviewed and retained["setup"] == setup_approval
                    and retained["view"]["plan"]["effects"]["directory"] == str(choices.directory),
                    "Resume only the original next intent; no replacement window")
            view = retained["view"]
            self.successor(view)  # incomplete attachment cannot hide execution
            current, observation, completed = self.status(transport=product.transport)
            require(current["next_issue"] in (None, choices.issue)
                    and {digest(i): digest(r) for i, r in completed.items()} == view["completions"]
                    and same_observation(observation.snapshot, typed(Snapshot, view["snapshot"])),
                    "Original next-intent observations changed")
            with product.service.bounded():
                require(product.facts()["base_sha"] == view["plan"]["checkout"]["head"], "Current native base changed before next admission")
            parent = self.c.memory.inspect()
            require(parent["state"]["generation"] == view["parent_generation"], "Previous generation changed")
            if parent["local_owner"]:
                require(parent["local_head"] == view["parent_checkpoint"], "Previous window changed before release")
                _, token = self.c.invocation("handoff")
                self.c.run(reviewed=token, authorized=True, operation="handoff")
            else:
                require(parent["state"]["owner"] is None, "Previous owner is uncertain")
            plan = view["plan"]
            with product.service.bounded():
                require(product.facts()["base_sha"] == plan["checkout"]["head"], "Current native base changed after previous owner release")
            snapshot_reference = content(self.root / "observations", view["snapshot"])
            link = {"schema_version": 1, "root": str(self.root), "index": self.link["index"],
                "identity": view["original"]["identity"], "directory": plan["effects"]["directory"], "setup": setup_approval,
                "snapshot": snapshot_reference, "parent": self.link["identity"]}
            personal = apply_personal(plan, view["original"], view["governance"], approved=setup_approval,
                authorized=True, transport=self.c.transport, ci_transport=self.c.ci_transport, clock=self.c.clock,
                _track_link=link)
            from .personal_runner import PersonalCoordinator
            from .personal_track_preparation import unsigned_policy
            c = PersonalCoordinator(personal, self.c.transport, self.c.ci_transport, clock=self.c.clock)
            _, source, claims = unsigned_policy(c)
            summaries = [{"identity": r["identity"], "original": digest(r["original"]), "packet": r["packet"],
                "source": r["source"], "merge": r["merge"], "actor": r["actor"], "pull": r["pull"],
                "project_evidence": r["ci"], "accepted_at": r["accepted_at"]} for r in completed.values()]
            immutable(self.root / "admissions" / (digest(link["identity"]) + ".json"),
                {"policy_snapshot": data(source), "policy_sources": [data(claim) for claim in claims], "completions": summaries})
            immutable(personal.state / LINK, link)
            immutable(self.root / "links" / (digest(link["identity"]) + ".json"), link)
            return {"status": "NEXT_ENROLLED_SCOPE_REVIEW_REQUIRED", "issue": plan["issue"],
                "directory": str(personal.directory), "source": plan["checkout"]["head"],
                "scope": plan["paths"], "window": plan["window"], "execution": "NOT_STARTED",
                "runtime_qualification": "NOTRUN"}
