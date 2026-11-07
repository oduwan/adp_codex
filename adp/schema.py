"""Bounded v1 current-state schema. Unknown fields are refused."""
from __future__ import annotations

import hashlib
import json
import re

from .errors import ADPError
from .git import SHA

MAX_TASKS = 64
MAX_ASSIGNMENTS = 128
MAX_JSON = 65536
MAX_RESULT = 16384
MAX_JOURNAL = (MAX_TASKS + 1) * MAX_JSON
KEY = re.compile(r"[0-9a-f]{64}\Z")
JOB = re.compile(r"[1-9][0-9]{0,17}-[1-9][0-9]{0,17}\Z")
OUTCOMES = {"PASS", "FAIL", "ERROR", "SKIP", "UNKNOWN"}


def require(condition: object, message: str) -> None:
    if not condition:
        raise ADPError(message)


def fields(data: object, names: str) -> None:
    require(type(data) is dict and set(data) == set(names.split()), "Invalid schema fields")


def string(value: object, maximum: int = 256) -> None:
    require(isinstance(value, str) and 0 < len(value) <= maximum
            and all(ord(c) >= 32 and ord(c) != 127 for c in value), "Invalid bounded string")


def integer(value: object, minimum: int = 0) -> None:
    require(type(value) is int and minimum <= value < 10**18, "Invalid bounded integer")


def key(identifier: str) -> str:
    string(identifier)
    return hashlib.sha256(identifier.encode()).hexdigest()


def encode(data: dict, limit: int = MAX_JSON) -> bytes:
    raw = (json.dumps(data, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")) + "\n").encode()
    require(len(raw) <= limit, "JSON payload exceeds size limit")
    return raw


def decode(raw: bytes, limit: int = MAX_JSON) -> dict:
    require(len(raw) <= limit, "JSON payload exceeds size limit")
    def pairs(items: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for name, value in items:
            if name in result:
                raise ValueError("duplicate key")
            result[name] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ADPError("Malformed bounded JSON") from exc
    require(type(result) is dict, "JSON root must be an object")
    return result


def result_schema(result: object) -> None:
    fields(result, "outcome summary evidence")
    require(isinstance(result["outcome"], str) and result["outcome"] in OUTCOMES, "Invalid result outcome")
    string(result["summary"], 2048)
    require(type(result["evidence"]) is list and len(result["evidence"]) <= 8, "Invalid evidence list")
    for ref in result["evidence"]:
        string(ref, 512)


def bundle(state: dict, tasks: dict[str, dict], repository_id: str) -> None:
    require(type(tasks) is dict, "Invalid task collection")
    fields(state, "schema_version repository_id revision generation owner task_keys assignment_sequence")
    require(type(state["schema_version"]) is int and state["schema_version"] == 1, "Unsupported schema version")
    require(state["repository_id"] == repository_id, "Repository identity mismatch")
    integer(state["revision"], 1)
    integer(state["generation"])
    integer(state["assignment_sequence"])
    owner = state["owner"]
    if owner is not None:
        fields(owner, "id label token_hash")
        string(owner["id"], 64)
        string(owner["label"], 128)
        require(isinstance(owner["token_hash"], str) and KEY.fullmatch(owner["token_hash"]), "Invalid owner credential hash")
        require(state["generation"] > 0, "Owner requires a generation")
    keys = state["task_keys"]
    require(type(keys) is list and len(keys) <= MAX_TASKS
            and all(isinstance(k, str) and KEY.fullmatch(k) for k in keys), "Invalid task registry")
    require(keys == sorted(set(keys)) and set(keys) == set(tasks), "Task registry/tree mismatch")
    jobs: set[str] = set()
    for task_key, task in tasks.items():
        fields(task, "schema_version key id repository_id iteration phase source_revision assignments blockers last_published_iteration")
        require(type(task["schema_version"]) is int and task["schema_version"] == 1, "Unsupported task schema")
        require(task["key"] == task_key == key(task["id"]), "Task key/identity mismatch")
        require(task["repository_id"] == repository_id, "Task repository mismatch")
        integer(task["iteration"], 1)
        require(task["phase"] == "active", "Unsupported task phase")
        source = task["source_revision"]
        require(source is None or isinstance(source, str) and SHA.fullmatch(source), "Invalid exact source revision")
        require(task["last_published_iteration"] is None, "Product publication is unavailable in M1")
        require(type(task["blockers"]) is list and len(task["blockers"]) <= 8, "Invalid blocker list")
        for blocker in task["blockers"]:
            string(blocker, 512)
        assignments = task["assignments"]
        require(type(assignments) is dict and len(assignments) <= MAX_ASSIGNMENTS, "Invalid assignments")
        for job_id, job in assignments.items():
            require(isinstance(job_id, str) and JOB.fullmatch(job_id) and job_id not in jobs,
                    "Duplicate or invalid global assignment ID")
            jobs.add(job_id)
            fields(job, "generation worker source_revision status result")
            integer(job["generation"], 1)
            require(job["generation"] <= state["generation"], "Assignment from future generation")
            require(job_id.startswith(str(job["generation"]) + "-")
                    and int(job_id.split("-")[1]) <= state["assignment_sequence"], "Invalid assignment sequence")
            string(job["worker"], 128)
            require(isinstance(job["source_revision"], str) and SHA.fullmatch(job["source_revision"]), "Assignment requires exact revision")
            require(job["status"] in ("pending", "accepted", "incomplete"), "Invalid assignment status")
            if job["status"] == "accepted":
                result_schema(job["result"])
            else:
                require(job["result"] is None, "Unaccepted job cannot contain a result")
            if job["status"] == "pending":
                require(owner is not None and job["generation"] == state["generation"]
                        and job["source_revision"] == source, "Stale pending assignment")
        encode(task)
    require(len(jobs) <= MAX_ASSIGNMENTS, "Global assignment bound exceeded")
    encode(state)
