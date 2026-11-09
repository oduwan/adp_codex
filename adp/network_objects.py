"""Bounded, byte-preserving Git Data payloads; no ref or network operations."""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .errors import ADPError
from .git import git, value
from .schema import require

MAX_OBJECTS = 512
MAX_OBJECT_BYTES = 1048576
MAX_TOTAL_BYTES = 8 * 1048576
MAX_COMMITS = 16
MAX_DEPTH = 32
OID = re.compile(r"[0-9a-f]{40}\Z")


def oid(value: object) -> str:
    require(type(value) is str and OID.fullmatch(value) is not None and value != "0" * 40,
            "UNSUPPORTED_ATOMIC_REF: exact SHA1 object required")
    return value


def object_oid(kind: str, raw: bytes) -> str:
    return hashlib.sha1(kind.encode() + b" " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


@dataclass(frozen=True)
class ObjectPayload:
    oid: str
    kind: str
    payload: dict


def _actor(raw: bytes) -> dict:
    match = re.fullmatch(rb"([^<>\n]+) <([^<>\s]+)> ([0-9]+) \+0000", raw)
    require(match is not None, "UNSUPPORTED_ATOMIC_REF: canonical UTC actor required")
    name, email, seconds = match.groups()
    require(name.strip() == name and not any(c < 32 for c in name + email),
            "UNSUPPORTED_ATOMIC_REF: actor contains unsupported bytes")
    try:
        stamp = datetime.fromtimestamp(int(seconds), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        require(len(stamp) == 20, "UNSUPPORTED_ATOMIC_REF: actor date outside supported range")
        return {"name": name.decode("utf-8"), "email": email.decode("utf-8"), "date": stamp}
    except (ValueError, OverflowError, UnicodeError) as exc:
        raise ADPError("UNSUPPORTED_ATOMIC_REF: actor is not representable") from exc


def commit_payload(raw: bytes) -> dict:
    """Reject every byte which cannot be represented without a new commit ID."""
    try:
        headers, message = raw.split(b"\n\n", 1)
        lines = headers.split(b"\n")
        require(len(lines) >= 3 and lines[0].startswith(b"tree "), "UNSUPPORTED_ATOMIC_REF: commit headers")
        tree = oid(lines[0][5:].decode("ascii"))
        parents = []
        position = 1
        while position < len(lines) and lines[position].startswith(b"parent "):
            parents.append(oid(lines[position][7:].decode("ascii")))
            position += 1
        require(len(parents) <= 2 and len(set(parents)) == len(parents), "UNSUPPORTED_ATOMIC_REF: parent list")
        require(len(lines) == position + 2 and lines[position].startswith(b"author ")
                and lines[position + 1].startswith(b"committer "),
                "UNSUPPORTED_ATOMIC_REF: signature, encoding or extra commit header")
        author = _actor(lines[position][7:])
        committer = _actor(lines[position + 1][10:])
        text = message.decode("utf-8", "strict")
        require(message and all(c >= 32 or c in (9, 10) for c in message),
                "UNSUPPORTED_ATOMIC_REF: noncanonical commit message")
        def actor_bytes(actor):
            seconds = int(datetime.strptime(actor["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
            return f"{actor['name']} <{actor['email']}> {seconds} +0000".encode()
        rebuilt = (b"tree " + tree.encode() + b"\n" + b"".join(b"parent " + p.encode() + b"\n" for p in parents)
                   + b"author " + actor_bytes(author) + b"\ncommitter " + actor_bytes(committer) + b"\n\n" + text.encode())
        require(rebuilt == raw, "UNSUPPORTED_ATOMIC_REF: commit would be rewritten")
        return {"tree": tree, "parents": parents, "author": author, "committer": committer, "message": text}
    except (ValueError, UnicodeError, IndexError) as exc:
        raise ADPError("UNSUPPORTED_ATOMIC_REF: malformed commit object") from exc


def tree_payload(raw: bytes) -> dict:
    entries, position, seen = [], 0, set()
    modes = {b"100644": ("100644", "blob"), b"100755": ("100755", "blob"),
             b"120000": ("120000", "blob"), b"40000": ("040000", "tree")}
    while position < len(raw):
        try:
            end = raw.index(b"\0", position)
            mode, name = raw[position:end].split(b" ", 1)
            sha = raw[end + 1:end + 21]
            require(len(sha) == 20 and mode in modes, "UNSUPPORTED_ATOMIC_REF: tree entry type")
            path = name.decode("utf-8", "strict")
            require(path and path not in (".", "..") and path.casefold() != ".git"
                    and all(c >= 32 and c != 127 for c in name) and not any(c in path for c in ("/", "\\", ":"))
                    and path not in seen, "UNSUPPORTED_ATOMIC_REF: tree path")
            seen.add(path)
            entries.append({"path": path, "mode": modes[mode][0], "type": modes[mode][1], "sha": sha.hex()})
            position = end + 21
        except (ValueError, UnicodeError) as exc:
            raise ADPError("UNSUPPORTED_ATOMIC_REF: malformed tree") from exc
    # Git's canonical ordering treats directory names as ending in '/'.
    ordered = sorted(entries, key=lambda e: e["path"].encode() + (b"/" if e["type"] == "tree" else b""))
    rebuilt = b"".join(e["mode"].lstrip("0").encode() + b" " + e["path"].encode() + b"\0" + bytes.fromhex(e["sha"]) for e in ordered)
    require(rebuilt == raw, "UNSUPPORTED_ATOMIC_REF: noncanonical tree order")
    return {"tree": entries}


def closure(root: Path, revision: str, known_commit: Callable[[str], bool]) -> tuple[ObjectPayload, ...]:
    """Preflight the entire missing closure before any object POST is possible."""
    oid(revision)
    require(value(root, "rev-parse", "--show-object-format") == "sha1", "UNSUPPORTED_ATOMIC_REF: SHA1 repository required")
    result, visited, commits, total = [], set(), 0, 0
    def visit(sha, kind, depth):
        nonlocal commits, total
        oid(sha)
        if sha in visited:
            return
        require(depth <= MAX_DEPTH and len(visited) < MAX_OBJECTS, "UNSUPPORTED_ATOMIC_REF: object closure bounds")
        visited.add(sha)
        if kind == "commit" and known_commit(sha):
            return
        size = int(value(root, "--no-replace-objects", "cat-file", "-s", sha))
        require(size <= MAX_OBJECT_BYTES and total + size <= MAX_TOTAL_BYTES, "UNSUPPORTED_ATOMIC_REF: object byte bound")
        raw = git(root, "--no-replace-objects", "cat-file", kind, sha, limit=MAX_OBJECT_BYTES)
        require(object_oid(kind, raw) == sha, "UNSUPPORTED_ATOMIC_REF: object identity changed")
        total += len(raw)
        if kind == "commit":
            commits += 1
            require(commits <= MAX_COMMITS, "UNSUPPORTED_ATOMIC_REF: commit closure bound")
            payload = commit_payload(raw)
            for parent in payload["parents"]:
                visit(parent, "commit", depth + 1)
            visit(payload["tree"], "tree", depth + 1)
        elif kind == "tree":
            payload = tree_payload(raw)
            for entry in payload["tree"]:
                visit(entry["sha"], entry["type"], depth + 1)
        else:
            require(kind == "blob", "UNSUPPORTED_ATOMIC_REF: unsupported object")
            payload = {"content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"}
        result.append(ObjectPayload(sha, kind, payload))
    visit(revision, "commit", 0)
    return tuple(result)
