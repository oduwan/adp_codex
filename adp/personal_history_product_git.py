"""Private immutable Git facts, never cached permissions or observations.

Every use reads actual refs/context and object bytes. Unsupported optimization
envelopes use the original M7 observer. Normal and signed ports are unchanged.
"""
from collections import OrderedDict
import hashlib
import os
from pathlib import Path

from .config import safe_path
from .errors import ADPError
from .discovery_schema import digest
from .execution_ports import GitExecutionPort
from .execution_types import ExternalObservation
from .git import git, value
from .policy_schema import sha
from .schema import require

_FACTS = OrderedDict()


class _Unsupported(Exception):
    pass


def context_paths(root):
    raw = git(root, "rev-parse", "--path-format=absolute", "--show-toplevel", "--absolute-git-dir", "--git-common-dir")
    rows = raw.decode("utf-8", "strict").splitlines()
    if len(rows) != 3 or "\n" in str(root) or any("\r" in p or p != p.strip() for p in rows):
        return (value(root, "rev-parse", "--show-toplevel"), value(root, "rev-parse", "--absolute-git-dir"),
                value(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return tuple(rows)


def administration(root):
    from .personal_git import administration as native
    return native(root, _paths=context_paths)


class HistoryReadPort(GitExecutionPort):
    """Original read grammar, freshly pinned before EVERY actual command."""
    def _git(self, *args, **kwargs):
        if self.bound_git_directory is None:
            return super()._git(*args, **kwargs)
        require(tuple((safe_path(p).stat().st_dev, p.stat().st_ino) for p in
                    (self.root, self.bound_git_directory, self._bound_common)) == self._bound_identities,
                "Pinned product Git administration changed")
        expected = (str(self.bound_git_directory), str(self._bound_common))
        raw = git(self.root, "rev-parse", "--absolute-git-dir", "--path-format=absolute", "--git-common-dir")
        if any("\n" in p or "\r" in p or p != p.strip() for p in expected) or len(raw.decode("utf-8", "strict").splitlines()) != 2:
            return super()._git(*args, **kwargs)  # Original exact framing checks.
        require(raw == ("\n".join(expected) + "\n").encode(), "Pinned product Git administration changed")
        return git(self.root, "--git-dir", str(self.bound_git_directory), "--work-tree", str(self.root), *args, **kwargs)

    def submit(self, *args, **kwargs):
        raise ADPError("Historical product reader permits no Git mutation")


def _metadata(port, identifiers):
    raw = port._git("cat-file", "--batch-check", input=("\n".join(identifiers) + "\n").encode(), limit=8192)
    rows = raw.decode("ascii", "strict").splitlines()
    require(len(rows) == len(identifiers), "Incomplete product object inventory")
    for identifier, row in zip(identifiers, rows):
        parts = row.split()
        require(len(parts) == 3 and parts[0] == identifier and parts[1] in ("commit", "tree", "blob")
                and parts[2].isdigit(), "Missing or malformed product object")
        if int(parts[2]) > 65536:
            raise _Unsupported()


def _objects(port, pairs):
    require(1 <= len(pairs) <= 32, "Bounded product object closure required")
    for query, identifier in pairs:
        sha(identifier)
        require(query in (identifier, "HEAD"), "Unsupported immutable object query")
    raw = port._git("cat-file", "--batch", input=("\n".join(q for q, _ in pairs) + "\n").encode(), limit=32 * (65536 + 256))
    cursor, result = 0, {}
    for _, identifier in pairs:
        end = raw.find(b"\n", cursor)
        require(end >= cursor, "Truncated product object header")
        fields = raw[cursor:end].decode("ascii", "strict").split()
        require(len(fields) == 3 and fields[0] == identifier and fields[1] in ("commit", "tree", "blob")
                and fields[2].isdigit() and 0 <= int(fields[2]) <= 65536, "Changed or missing product object")
        size = int(fields[2]); cursor = end + 1
        body = raw[cursor:cursor + size]
        require(len(body) == size and raw[cursor + size:cursor + size + 1] == b"\n", "Truncated product object")
        header = (fields[1] + " " + str(size)).encode() + b"\0"
        hashed = (hashlib.sha1 if len(identifier) == 40 else hashlib.sha256)(header + body).hexdigest()
        require(hashed == identifier, "Product object bytes differ from immutable identity")
        result[identifier] = (fields[1], body)
        cursor += size + 1
    require(cursor == len(raw), "Unexpected product object output")
    return result


def _context(port):
    common = safe_path(port._bound_common)
    info = common.stat()
    require(info.st_uid == os.getuid() and not info.st_mode & 0o022, "Unprotected product Git administration")
    for leaf in ("info/grafts", "shallow", "objects/info/alternates", "objects/info/http-alternates"):
        if safe_path(common / leaf).exists():
            raise _Unsupported()
    if port._value("for-each-ref", "--format=%(refname)", "refs/replace"):
        raise _Unsupported()
    config = port._git("config", "--null", "--list", limit=65536)
    if any(b"partialclone" in row.lower().partition(b"\n")[0]
           or row.lower().partition(b"\n")[0].endswith(b".promisor") for row in config.split(b"\0")):
        raise _Unsupported()
    return (str(port.root), str(common), port._bound_identities, info.st_uid, info.st_mode, hashlib.sha256(config).hexdigest())


def _commit(body):
    header, separator, message = body.partition(b"\n\n")
    require(separator and header.startswith(b"tree "), "Malformed immutable product commit")
    rows = header.splitlines()
    if any(row.startswith(b"encoding ") and row[9:].lower() not in (b"utf-8", b"utf8") for row in rows):
        raise _Unsupported()
    tree = rows[0][5:].decode("ascii", "strict"); sha(tree)
    parents = [row[7:].decode("ascii", "strict") for row in rows if row.startswith(b"parent ")]
    for parent in parents: sha(parent)
    try:
        text = message.decode("utf-8", "strict").strip()
    except UnicodeError:
        raise _Unsupported() from None
    return tree, parents[0] if parents else None, text


def _witness(port, revision):
    _metadata(port, [revision])
    kind, raw = _objects(port, [(revision, revision)])[revision]
    require(kind == "commit", "Product source is not a commit")
    tree, parent, message = _commit(raw)
    rows = port._git("ls-tree", "-r", "-t", "-z", revision).split(b"\0")
    identifiers, index = {revision, tree}, []
    for row in filter(None, rows):
        metadata, path = row.split(b"\t", 1)
        mode, kind, identifier = metadata.split()
        identifier = identifier.decode("ascii");sha(identifier)
        if kind not in (b"tree", b"blob"):
            raise _Unsupported()  # Native gitlink semantics remain unchanged.
        identifiers.add(identifier)
        if kind == b"blob":index.append((path, mode + b" " + identifier.encode() + b" 0\t" + path + b"\0"))
    if len(identifiers) > 32:
        raise _Unsupported()
    identifiers = tuple(sorted(identifiers));_metadata(port, identifiers)
    _objects(port, [(i, i) for i in identifiers])
    return {"objects": identifiers, "parent": parent, "message": message,
            "index": hashlib.sha256(b"".join(row for _, row in sorted(index))).hexdigest()}


def observe(port, action, revision):
    if action["operation"] != "COMMIT":
        return port.observe(action)
    try:
        context = _context(port)
        identity = (context, revision, digest(action))
        fact = _FACTS.get(identity)
        if fact is None:
            actual = port.observe(action)
            if actual.status != "PRESENT" or actual.revision != revision:
                return actual
            fact = _witness(port, revision)
        # HEAD is resolved now, not inferred from the retained fact or a ref.
        objects = _objects(port, [("HEAD", revision), *((i, i) for i in fact["objects"] if i != revision)])
        require(objects[revision][0] == "commit", "Current product HEAD is not a commit")
        _, parent, message = _commit(objects[revision][1])
        payload = action["payload"]
        expected = (payload["subject"] + ("\n\n" + payload["body"] if payload["body"] else "")).strip()
        present = (port._value("symbolic-ref", "HEAD") == action["source_ref"] and parent == action["revision"]
                   and parent == fact["parent"] and message == fact["message"] == expected
                   and fact["index"] == payload["index_digest"])
        if not present:return ExternalObservation("UNKNOWN")
        _FACTS[identity] = fact
        _FACTS.move_to_end(identity)
        while len(_FACTS) > 8:_FACTS.popitem(last=False)
        return ExternalObservation("PRESENT", "commit:" + revision, revision)
    except _Unsupported:
        return port.observe(action)
