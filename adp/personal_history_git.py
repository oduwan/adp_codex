"""Bounded immutable archival/activation witnesses; never caches authority.

Every use checks the actual storage/rewrite context and complete retained
object closure. Raw receipts, current canonical/source state and permissions
are deliberately outside this optimization and remain freshly authenticated.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import os

from .config import safe_path
from .discovery_schema import digest
from .git import git, value
from .policy_schema import sha
from .schema import require

_WITNESSES = OrderedDict()


def storage_context(memory):
    common = safe_path(memory.common)
    info = common.stat()
    require(info.st_uid == os.getuid() and not info.st_mode & 0o022, "Unprotected canonical Git administration")
    for leaf in ("info/grafts", "shallow", "objects/info/alternates", "objects/info/http-alternates"):
        path = safe_path(common / leaf)
        require(not path.exists(), "Unsupported historical Git rewrite/alternate/shallow context")
    require(not value(memory.config.root, "for-each-ref", "--format=%(refname)", "refs/replace"), "Historical replacement refs are unsupported")
    configuration = git(memory.config.root, "config", "--null", "--list", limit=65536)
    require(not any(b"partialclone" in row.lower().partition(b"\n")[0]
                    or row.lower().partition(b"\n")[0].endswith(b".promisor") for row in configuration.split(b"\0")),
            "Historical observation cannot fetch promisor objects")
    return (str(common), info.st_dev, info.st_ino, info.st_uid, info.st_mode, hashlib.sha256(configuration).hexdigest())


def object_inventory(memory, identifiers):
    require(1 <= len(identifiers) <= 32, "Bounded historical object closure required")
    identifiers = tuple(sorted(identifiers))
    for identifier in identifiers: sha(identifier)
    raw = git(memory.config.root, "cat-file", "--batch", input=("\n".join(identifiers) + "\n").encode("ascii"), limit=32 * (65536 + 256))
    rows = []
    cursor = 0
    for identifier in identifiers:
        newline = raw.find(b"\n", cursor)
        require(newline >= cursor, "Incomplete retained historical objects")
        values = raw[cursor:newline].decode("ascii", "strict").split()
        require(len(values) == 3 and values[0] == identifier and values[1] in ("commit", "tree", "blob")
                and values[2].isdigit() and 0 < int(values[2]) <= 65536, "Missing, malformed or oversized historical object")
        size = int(values[2]); cursor = newline + 1
        content = raw[cursor:cursor + size]
        require(len(content) == size and raw[cursor + size:cursor + size + 1] == b"\n", "Truncated historical object body")
        header = (values[1] + " " + str(size)).encode("ascii") + b"\0"
        actual = (hashlib.sha1 if len(identifier) == 40 else hashlib.sha256)(header + content).hexdigest()
        require(actual == identifier, "Historical object bytes do not match their immutable identity")
        rows.append((identifier, values[1], size))
        cursor += size + 1
    require(cursor == len(raw), "Unexpected historical object output")
    return tuple(rows)


def verify(memory, heads, expected, *, engine, host):
    """Cache only immutable encodings' digests and object type/size witnesses."""
    for head in heads: sha(head)
    context = storage_context(memory)  # Always actual; never a cached context.
    identity = (context, memory.config.identity, tuple(heads), digest(expected), engine, host)
    witness = _WITNESSES.get(identity)
    if witness is None:
        objects = set(heads)
        for index, head in enumerate(heads):
            require(memory._read_ref(head) == expected[index], "Archived canonical checkpoint differs")
            if index:
                require(value(memory.config.root, "rev-list", "--parents", "--max-count=1", head).split() == [head, heads[index-1]],
                        "Archival history is not exactly guard-first and linear")
            tree = value(memory.config.root, "rev-parse", head + "^{tree}")
            sha(tree); objects.add(tree)
            entries = git(memory.config.root, "ls-tree", "-r", "-t", "-z", head, limit=8192).split(b"\0")
            for row in filter(None, entries):
                metadata, path = row.split(b"\t", 1)
                mode, kind, identifier = metadata.decode("ascii").split()
                sha(identifier)
                require(kind in ("tree", "blob"), "Unsupported historical Git object")
                objects.add(identifier)
        witness = object_inventory(memory, objects)
        _WITNESSES[identity] = witness
        while len(_WITNESSES) > 4:
            _WITNESSES.popitem(last=False)
    else:
        # Missing/corrupt old commits/trees/blobs refuse on every hit. No
        # normalized differences or cached evidence/authority verdict exists.
        require(object_inventory(memory, [row[0] for row in witness]) == witness, "Retained historical object closure changed")
    return None
