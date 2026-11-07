"""Closed bounded guard schema embedded only in explicitly upgraded v2 state."""
from __future__ import annotations

import hashlib

from .git import SHA
from .schema import KEY, encode, fields, integer, require, string
from .guard_types import (ActionKind, Classification, Limits,
                          Outcome, ProgressKind)

MAX_REQUIREMENTS = 16
MAX_ACCEPTANCE = 16
MAX_FACTS = 32
MAX_AUTHORS = 16
MAX_CAMPAIGN = 256
MAX_ACTION_SECONDS = 300
MAX_CAMPAIGN_SECONDS = 3600
MAX_SAMPLES = 10000
MAX_PAYLOAD = 1048576
COUNTERS = "failures corrections explorations reviews stalls"
MODES = {"normal", "forensic", "ready", "running", "operator", "unsafe"}


def digest(value: dict) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def requirement_id(contract: str, gate: str) -> str:
    string(contract)
    string(gate, 128)
    return digest({"contract": contract, "gate": gate})


def choice(value: object, allowed: object) -> None:
    require(isinstance(value, str) and value in allowed, "Invalid guard enum")


def strings(values: object, maximum: int, length: int = 256, *, nonempty: bool = False) -> None:
    require(type(values) is list and int(nonempty) <= len(values) <= maximum, "Invalid bounded guard list")
    for value in values:
        string(value, length)
    require(len(set(values)) == len(values), "Duplicate guard list entries")


def sha(value: object, *, nullable: bool = False) -> None:
    require(nullable and value is None or isinstance(value, str) and SHA.fullmatch(value), "Invalid guard revision")


def limits(value: dict) -> None:
    fields(value, COUNTERS)
    for name, default in vars(Limits()).items():
        integer(value[name], 1)
        require(value[name] <= default, "Guard thresholds cannot be relaxed")


def budget(value: dict, *, campaign: bool = False) -> None:
    integer(value["seconds"], 1)
    integer(value["samples"], 1)
    integer(value["payload_bytes"], 1)
    require(value["seconds"] <= (MAX_CAMPAIGN_SECONDS if campaign else MAX_ACTION_SECONDS)
            and value["samples"] <= MAX_SAMPLES and value["payload_bytes"] <= MAX_PAYLOAD,
            "Guard containment limits cannot be raised")


def action(value: dict) -> None:
    fields(value, "actor kind hypothesis exit_criteria seconds samples payload_bytes")
    string(value["actor"], 128)
    choice(value["kind"], set(ActionKind))
    string(value["hypothesis"], 512)
    if value["exit_criteria"] is not None:
        string(value["exit_criteria"], 512)
    budget(value)


def progress(value: dict) -> None:
    fields(value, "kind fact evidence parent_cause")
    choice(value["kind"], set(ProgressKind))
    string(value["fact"], 128)
    strings(value["evidence"], 4, nonempty=True)
    if value["parent_cause"] is not None:
        string(value["parent_cause"], 128)


def observation(value: dict) -> None:
    fields(value, "outcome evidence unresolved progress finding risk elapsed_seconds samples payload_bytes")
    choice(value["outcome"], set(Outcome))
    strings(value["evidence"], 4, nonempty=True)
    strings(value["unresolved"], MAX_ACCEPTANCE, 128)
    if value["progress"] is not None:
        progress(value["progress"])
    if value["finding"] is not None:
        string(value["finding"], 128)
    if value["risk"] is not None:
        choice(value["risk"], {"safety", "authority", "contamination", "containment"})
    for name in ("elapsed_seconds", "samples", "payload_bytes"):
        integer(value[name])


def plan(value: dict) -> None:
    fields(value, "action pass_means fail_means unknown_means stop_conditions seconds samples payload_bytes")
    for name in ("action", "pass_means", "fail_means", "unknown_means"):
        string(value[name], 512)
    strings(value["stop_conditions"], 4, nonempty=True)
    budget(value)


def report(value: dict) -> None:
    fields(value, "request_id classification evidence diagnosis plan")
    string(value["request_id"], 64)
    choice(value["classification"], set(Classification))
    strings(value["evidence"], 4, nonempty=True)
    string(value["diagnosis"], 512)
    if value["plan"] is not None:
        plan(value["plan"])


def campaign_spec(value: dict) -> None:
    fields(value, "inventory evidence_reference quarantined seconds samples payload_bytes")
    strings(value["inventory"], MAX_CAMPAIGN, 96, nonempty=True)
    string(value["evidence_reference"])
    strings(value["quarantined"], MAX_CAMPAIGN, 96)
    require(set(value["quarantined"]) <= set(value["inventory"]), "Quarantine must preserve original inventory")
    budget(value, campaign=True)


def context(value: dict, repository_id: str | None = None) -> None:
    fields(value, "repository_id task_key revision iteration generation task_epoch")
    string(value["repository_id"])
    if repository_id is not None:
        require(value["repository_id"] == repository_id, "Guard context repository identity mismatch")
    require(isinstance(value["task_key"], str) and KEY.fullmatch(value["task_key"]), "Invalid guard task key")
    sha(value["revision"], nullable=True)
    integer(value["iteration"], 1)
    integer(value["generation"], 1)
    integer(value["task_epoch"], 1)


def record(value: dict, identifier: str, repository_id: str | None = None) -> None:
    fields(value, "contract gate acceptance dependencies limits tasks sequence mode counters authors seen_facts cause unresolved pending_dependencies last last_event active forensic_round request plan approval campaign campaign_runs reason")
    require(requirement_id(value["contract"], value["gate"]) == identifier, "Guard requirement identity mismatch")
    strings(value["acceptance"], MAX_ACCEPTANCE, 128, nonempty=True)
    strings(value["dependencies"], MAX_ACCEPTANCE, 128)
    limits(value["limits"])
    strings(value["tasks"], 64, 64, nonempty=True)
    require(all(KEY.fullmatch(k) for k in value["tasks"]), "Invalid guard task binding")
    integer(value["sequence"])
    choice(value["mode"], MODES)
    string(value["reason"], 512)
    fields(value["counters"], COUNTERS)
    for counter in value["counters"].values():
        integer(counter)
    if value["mode"] == "normal":
        require(all(value["counters"][name] <= threshold if name == "explorations"
                    else value["counters"][name] < threshold for name, threshold in value["limits"].items()),
                "A stalled guard cannot claim a normal mode")
    strings(value["authors"], MAX_AUTHORS, 128)
    strings(value["seen_facts"], MAX_FACTS, 64)
    require(all(KEY.fullmatch(f) for f in value["seen_facts"]), "Invalid progress fact digest")
    if value["cause"] is not None:
        string(value["cause"], 128)
    strings(value["unresolved"], MAX_ACCEPTANCE, 128)
    strings(value["pending_dependencies"], MAX_ACCEPTANCE, 128)
    require(set(value["unresolved"]) <= set(value["acceptance"])
            and set(value["pending_dependencies"]) <= set(value["dependencies"]), "Guard baseline drift")
    integer(value["forensic_round"])
    require(value["forensic_round"] <= 2, "Forensic reassessment bound exceeded")
    integer(value["campaign_runs"])
    require(value["campaign_runs"] <= 1, "Repeated census without progress")
    if value["last_event"] is not None:
        choice(value["last_event"], {"attempt", "campaign"})
    if value["last"] is not None:
        fields(value["last"], "context action observation counters")
        context(value["last"]["context"], repository_id)
        action(value["last"]["action"])
        observation(value["last"]["observation"])
        fields(value["last"]["counters"], COUNTERS)
        for counter in value["last"]["counters"].values():
            integer(counter)
    if value["active"] is not None:
        active = value["active"]
        fields(active, "id context action bounded started deadline")
        string(active["id"], 64)
        context(active["context"], repository_id)
        action(active["action"])
        require(type(active["bounded"]) is bool, "Invalid bounded action flag")
        integer(active["started"])
        integer(active["deadline"])
        require(active["deadline"] == active["started"] + active["action"]["seconds"], "Action deadline changed")
    if value["request"] is not None:
        request = value["request"]
        fields(request, "id round context baseline excluded_authors evidence contract gate unresolved counters hypothesis outcome observation_context cause reason")
        string(request["id"], 64)
        integer(request["round"], 1)
        require(request["round"] == value["forensic_round"], "Forensic request round mismatch")
        context(request["context"], repository_id)
        string(request["baseline"], 64)
        strings(request["excluded_authors"], MAX_AUTHORS, 128)
        strings(request["evidence"], 4, nonempty=True)
        require(request["contract"] == value["contract"] and request["gate"] == value["gate"], "Forensic contract drift")
        strings(request["unresolved"], MAX_ACCEPTANCE, 128)
        fields(request["counters"], COUNTERS)
        for counter in request["counters"].values():
            integer(counter)
        context(request["observation_context"], repository_id)
        if request["hypothesis"] is not None:
            string(request["hypothesis"], 512)
        if request["outcome"] is not None:
            choice(request["outcome"], set(Outcome))
        if request["cause"] is not None:
            string(request["cause"], 128)
        string(request["reason"], 512)
    if value["plan"] is not None:
        fields(value["plan"], "report reviewer reference")
        report(value["plan"]["report"])
        string(value["plan"]["reviewer"], 128)
        string(value["plan"]["reference"])
    if value["approval"] is not None:
        fields(value["approval"], "context reviewer reference subject")
        context(value["approval"]["context"], repository_id)
        string(value["approval"]["reviewer"], 128)
        string(value["approval"]["reference"])
        string(value["approval"]["subject"], 64)
    if value["campaign"] is not None:
        campaign = value["campaign"]
        fields(campaign, "id context spec results started deadline last_time samples payload_bytes stopped active_case interruption")
        string(campaign["id"], 64)
        context(campaign["context"], repository_id)
        campaign_spec(campaign["spec"])
        results = campaign["results"]
        require(type(results) is list and len(results) == len(campaign["spec"]["inventory"]), "Campaign denominator changed")
        for outcome in results:
            if outcome is not None:
                choice(outcome, set(Outcome) - {Outcome.UNKNOWN})
        for name in ("started", "deadline", "last_time", "samples", "payload_bytes"):
            integer(campaign[name])
        require(campaign["samples"] <= campaign["spec"]["samples"] + 1
                and campaign["payload_bytes"] <= campaign["spec"]["payload_bytes"] + 1,
                "Campaign overflow counters must remain bounded")
        require(campaign["deadline"] == campaign["started"] + campaign["spec"]["seconds"], "Campaign deadline changed")
        if campaign["stopped"] is not None:
            string(campaign["stopped"], 128)
        if campaign["active_case"] is not None:
            case = campaign["active_case"]
            fields(case, "id case_id index started")
            string(case["id"], 64)
            integer(case["index"])
            integer(case["started"])
            require(case["index"] < len(results) and results[case["index"]] is None
                    and case["index"] == results.index(None)
                    and case["case_id"] == campaign["spec"]["inventory"][case["index"]],
                    "Invalid or reordered in-flight campaign case")
        if campaign["interruption"] is not None:
            fields(campaign["interruption"], "case_id evidence")
            require(campaign["interruption"]["case_id"] in campaign["spec"]["inventory"], "Invalid interrupted case")
            string(campaign["interruption"]["evidence"])
    if value["mode"] in ("ready", "running"):
        require(value["request"] is not None and value["plan"] is not None
                and value["plan"]["report"]["plan"] is not None,
                "Ready/running guard requires an independent finite review plan")
    if value["mode"] == "ready":
        require(value["active"] is None, "Ready guard already has an active attempt")
    if value["mode"] == "running":
        require(value["active"] is not None and value["active"]["bounded"], "Running guard requires its bounded reservation")
    if value["active"] is not None and value["active"]["bounded"]:
        require(value["mode"] == "running", "Bounded reservation has an inconsistent mode")
    if value["mode"] in ("unsafe", "operator"):
        require(value["active"] is None, "Terminal guard cannot retain an actionable reservation")
        require(value["campaign"] is None or value["campaign"]["active_case"] is None,
                "Terminal guard cannot retain an actionable campaign case")
    if value["mode"] == "normal":
        require(value["request"] is None and value["plan"] is None, "Normal guard cannot carry an unresolved forensic plan")
    if value["plan"] is not None:
        require(value["request"] is not None and value["plan"]["report"]["request_id"] == value["request"]["id"],
                "Forensic plan/request mismatch")
    if value["last_event"] == "attempt":
        require(value["last"] is not None, "Latest attempt observation is missing")
    if value["last_event"] == "campaign":
        require(value["campaign"] is not None and any(outcome is not None for outcome in value["campaign"]["results"]),
                "Latest campaign observation is missing")
    encode(value)


def guard_schema(value: dict, repository_id: str | None = None) -> None:
    fields(value, "schema_version requirements task_epochs")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "Unsupported guard schema")
    epochs = value["task_epochs"]
    require(type(epochs) is dict and len(epochs) <= 64, "Invalid guard task incarnations")
    for task_key, epoch in epochs.items():
        require(isinstance(task_key, str) and KEY.fullmatch(task_key), "Invalid guard incarnation key")
        integer(epoch, 1)
    requirements = value["requirements"]
    require(type(requirements) is dict and len(requirements) <= MAX_REQUIREMENTS, "Guard requirement bound exceeded")
    for identifier, requirement in requirements.items():
        require(isinstance(identifier, str) and KEY.fullmatch(identifier), "Invalid requirement ID")
        record(requirement, identifier, repository_id)
