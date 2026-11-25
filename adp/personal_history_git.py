"""Bounded immutable archival/activation witnesses; never caches authority.

Every use checks the actual storage/rewrite context and complete retained
object closure. Raw receipts, current canonical/source state and permissions
are deliberately outside this optimization and remain freshly authenticated.
"""
from __future__ import annotations

import hashlib
import os

from .config import safe_path
from .git import git, value
from .policy_schema import sha
from .schema import require

def storage_context(memory, *, remote=False):
    if remote:
        memory.verify_pinned_remote()
        common = root = safe_path(memory.pinned_local_remote)
        require(value(root, "rev-parse", "--is-bare-repository") == "true", "Pinned historical store must be bare")
    else:
        common, root = safe_path(memory.common), memory.config.root
    info = common.stat()
    require(info.st_uid == os.getuid() and not info.st_mode & 0o022, "Unprotected canonical Git administration")
    for leaf in ("info/grafts", "shallow", "objects/info/alternates", "objects/info/http-alternates"):
        path = safe_path(common / leaf)
        require(not path.exists(), "Unsupported historical Git rewrite/alternate/shallow context")
    require(not value(root, "for-each-ref", "--format=%(refname)", "refs/replace"), "Historical replacement refs are unsupported")
    configuration = git(root, "config", "--null", "--list", limit=65536)
    require(not any(b"partialclone" in row.lower().partition(b"\n")[0]
                    or row.lower().partition(b"\n")[0].endswith(b".promisor") for row in configuration.split(b"\0")),
            "Historical observation cannot fetch promisor objects")
    return (str(common), info.st_dev, info.st_ino, info.st_uid, info.st_mode, hashlib.sha256(configuration).hexdigest())


def object_inventory(memory, identifiers, *, remote=False):
    require(1 <= len(identifiers) <= 32, "Bounded historical object closure required")
    identifiers = tuple(sorted(identifiers))
    for identifier in identifiers: sha(identifier)
    root = memory.pinned_local_remote if remote else memory.config.root
    raw = git(root, "cat-file", "--batch", input=("\n".join(identifiers) + "\n").encode("ascii"), limit=32 * (65536 + 256))
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


def verify(memory, heads, expected):
    """Verify actual encodings; return operation-local byte witnesses, not authority."""
    require(1 <= len(heads) == len(expected) <= 4 and len(set(heads)) == len(heads), "Bounded exact historical checkpoints required")
    for head in heads: sha(head)
    contexts = tuple((remote, storage_context(memory, remote=remote))
        for remote in ((False, True) if getattr(memory, "pinned_local_remote", None) is not None else (False,)))
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
    witnesses = tuple((remote, context, object_inventory(memory, objects, remote=remote)) for remote, context in contexts)
    require(all(storage_context(memory, remote=remote) == context for remote, context in contexts), "Historical Git storage changed during observation")
    return witnesses


def combine(first, second):
    """Deduplicate actual immutable operands within ONE cold observation."""
    require(tuple(r[0] for r in first) == tuple(r[0] for r in second), "Historical store roles differ")
    result = []
    for a, b in zip(first, second):
        require(a[:2] == b[:2], "Historical storage changed between proof groups")
        rows = tuple(sorted(set(a[2] + b[2])))
        require(len({r[0] for r in rows}) == len(rows), "Conflicting immutable object witnesses")
        result.extend(((a[0], a[1], rows),) if len(rows) <= 32 else (a, b))
    return tuple(result)
