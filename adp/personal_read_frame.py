"""Private synchronous publication/product reads; never an authority cache."""
from contextvars import ContextVar
from copy import deepcopy
import os
import hashlib
import re
import stat
import threading
from pathlib import Path

from .discovery_schema import digest
from .schema import require

_CURRENT = ContextVar("accounting_publication_read", default=None)


def consumed(path, raw=None, metadata=None):
    """Deny changed actual inputs; never return remembered bytes or authority."""
    frame = _CURRENT.get()
    if frame is None:
        return
    frame.context()
    path = Path(os.path.abspath(path))
    name = str(path)
    if name not in frame.readset and not any(path.is_relative_to(root) for root in frame.roots):
        return  # Current M1/control reads remain actual, outside private proofs.
    expected = frame.readset.get(name)  # Closed inventory proves omitted paths absent.
    if metadata is None:
        require(raw is None and expected is None, "Private proof presence changed during observation")
        return
    from .personal_storage import LIMIT
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid()
            and metadata.st_nlink == 1 and not metadata.st_mode & 0o077
            and len(raw) == metadata.st_size <= LIMIT and expected is not None
            and hashlib.sha256(raw).hexdigest() == expected,
            "Actual private proof differs from the sealed protected input")


def _private_inputs(c):
    """Closed, bounded private JSON inventory, including optional absence."""
    from .config import safe_path
    roots = {c.personal.state, c.personal.root.state, c.personal.directory,
             c.runtime.directory, c.authority.directory}
    if c.track is not None:
        roots.add(c.track.root)
    roots = {safe_path(p) for p in roots}
    roots = tuple(sorted((p for p in roots if not any(p != other and p.is_relative_to(other)
                          for other in roots)), key=str))
    files, total, entries = {}, 0, 0
    pending = [(root, 0) for root in reversed(roots)]
    while pending:
        directory, depth = pending.pop()
        require(depth <= 16, "Private observation traversal exceeds depth bound")
        info = safe_path(directory).stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and not info.st_mode & 0o022, "Unverified private input directory")
        children = []
        with os.scandir(directory) as scan:
            for entry in scan:
                entries += 1
                require(entries <= 4096, "Private observation traversal exceeds entry bound")
                path = safe_path(Path(entry.path))
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    children.append((path, depth + 1))
                elif entry.name.endswith(".json"):
                    files[str(path)] = _private_digest(path)
                    total += info.st_size
                    require(len(files) <= 1024 and total <= 8 * 1024 * 1024,
                            "Private observation inventory exceeds bound")
        pending.extend(sorted(children, key=lambda row: str(row[0]), reverse=True))
    for path in (c.personal.root.directory / "personal.json", Path(c.personal.plan["effects"]["marker"])):
        files[str(safe_path(path))] = _private_digest(path)
    return files, roots


def _private_digest(path):
    """Protected bounded byte observation, including honest absence."""
    from .config import safe_path
    from .personal_storage import LIMIT
    safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                and not info.st_mode & 0o077 and info.st_size <= LIMIT, "Unverified private observation input")
        raw = os.read(fd, LIMIT + 1)
        require(len(raw) == info.st_size and len(raw) <= LIMIT, "Private observation input was truncated or exceeds bound")
        return hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def _inputs(owner, observed, *, product):
    """Re-read fixed inputs without admission, authority or native callbacks."""
    from .execution_containment import admin_seal
    from .personal_enrollment import governance
    from .personal_history_product_git import administration
    from .personal_storage import read_private
    from .schema import key
    c = owner.c
    workers, files = c.workers.records(), {}
    require(len(workers) <= 16, "Bounded independent worker inputs required")
    for row in workers:
        identifier = row["request"]["id"]
        files[identifier] = (_private_digest(c.runtime._path(identifier)),
            _private_digest(c.runtime.directory / (identifier + ".stop.json")))
    for item in observed["state"]["progress_guard"]["requirements"].values():
        if key(c.task_id) in item["tasks"] and item["approval"] is not None:
            reference = item["approval"]["reference"]
            matched = re.fullmatch(r"personal:([0-9a-f]{64})", reference)
            require(matched is not None, "Unverified private progress reference")
            files[reference] = _private_digest(c.authority.directory / (matched[1] + ".json"))
    for name in ("adoption.json", "adoption-intent.json", "run.json", "product.json", "publication.json"):
        files[name] = _private_digest(c.personal.state / name)
    adoption = read_private(c.personal.state / "adoption.json", optional=True)
    if adoption is not None:
        require(type(adoption.get("manifest")) is list and len(adoption["manifest"]) == 2, "Exact retained candidate inputs required")
        for row in adoption["manifest"]:
            name = digest(row["path"]) + ".json"
            files["adoption-file:" + name] = _private_digest(c.personal.state / "adoption-files" / name)
    root = c.personal.feature
    consent = deepcopy(owner.active) if product else owner.record(_observed=observed)
    run = c.record()
    head = owner.port._value("rev-parse", "HEAD")
    tree = owner.port._value("--no-replace-objects", "rev-parse", "HEAD^{tree}")
    ref = owner.port._value("symbolic-ref", "HEAD")
    dirty = owner.port._value("status", "--porcelain", "--untracked-files=all")
    physical, admin, rules = administration(root), admin_seal(root), governance(root)
    view = consent["view"]
    require(head == view["revision"] == run["revision"] and tree == view["source_tree" if product else "tree"]
            and ref == view["source_ref"] == "refs/heads/" + c.personal.plan["feature"]["branch"]
            and not dirty and digest(physical) == view["administration"]
            and digest(rules) == c.personal.plan["governance_digest"]
            and owner.transport.credential_binding == consent["binding" if product else "credential_binding"],
            "Actual source, administration, governance or credential differs from approved consent")
    readset, roots = _private_inputs(c)
    sealed = digest({"consent": consent, "run": run,
        "workers": workers, "private": files,
        "head": head, "tree": tree, "ref": ref, "dirty": dirty,
        "physical": physical, "admin": admin, "governance": rules,
        "credential": owner.transport.credential_binding})
    return sealed, deepcopy(consent), readset, roots


def forbid_writes():
    require(_CURRENT.get() is None, "Accounting publication observation cannot admit, write or execute effects")


def _identity(c):
    p, r, m = c.personal, c.runtime, c.memory
    return (os.getpid(), threading.get_ident(), id(c), id(p), id(p.root), id(m), id(r),
            c.task_id, p.repository_id, digest(p.intent), digest(p.descriptor), digest(p.root.intent),
            str(m.config.root), str(m.common), str(m.control), r.host, str(r.directory),
            str(p.directory), str(p.state), str(p.root.directory), str(p.root.state),
            id(c.authority), str(c.authority.directory), id(c.workers), str(c.workers.directory),
            id(c.track), str(c.track.root) if c.track is not None else None)


class _Read:
    def __init__(self, owner, *, product=False):
        forbid_writes()
        c = owner.c
        self.owner, self.product = owner, product
        self.consent = deepcopy(owner.active) if product else None
        self.c, self.identity, self.closed = c, _identity(c), False
        capture = {}
        self.active = deepcopy(c.personal._active_view(memory=c.memory, allow_expired=False,
            now=c.clock(), _capture=capture))
        self.archive = deepcopy(capture["archive"])
        self.current()  # Full proof must end at this exact live subject.

    def context(self):
        require(not self.closed and self.owner.c is self.c and _identity(self.c) == self.identity
                and (not self.product or self.owner.active == self.consent),
                "Accounting publication read context changed")

    def current(self):
        self.context()
        from .personal_episode import same_observation
        actual = self.c.memory.inspect()
        same_observation(self.active[2], actual)
        self.c.episode_fence()
        return actual

    def run(self):
        forbid_writes()
        token = _CURRENT.set(self)
        try:
            self.current()
            result = self.owner._live_current(**({"genuine": False} if self.product else {"review": True}))
            self.current()
            return deepcopy(result)  # Product.active['view'] is otherwise a mutable alias.
        finally:
            _CURRENT.reset(token)
            self.closed = True


def active(personal, memory, runtime):
    frame = _CURRENT.get()
    if frame is None or personal is not frame.c.personal or memory is not frame.c.memory or runtime is not None:
        return None  # Independent/mismatched subjects retain the full proof.
    actual = frame.current()
    relation, contexts, _ = deepcopy(frame.active)
    return relation, contexts, actual


def archive(personal, memory, runtime, child):
    frame = _CURRENT.get()
    if (frame is None or personal is not frame.c.personal.root or child is not frame.c.personal
            or memory is not frame.c.memory or runtime is not None):
        return None
    actual = frame.current()
    master, receipt, contexts, _, workers = deepcopy(frame.archive)
    return master, receipt, contexts, actual, workers


def _live(owner, *, product=False):
    c = owner.c
    forbid_writes()
    first = _Read(owner, product=product)
    inputs = _inputs(owner, first.active[2], product=product)
    first.readset, first.roots = deepcopy(inputs[2]), inputs[3]
    result = first.run()  # Every original semantic predicate executes once.
    # The shortcut is unavailable here. No semantic body follows this truly
    # closing full raw/host/source/lineage proof.
    closing = _Read(owner, product=product)
    require(closing.identity == first.identity and closing.active == first.active
            and closing.archive == first.archive and closing.consent == first.consent,
            "Accounting evidence changed during final publication read")
    closing.closed = True
    final_inputs = _inputs(owner, closing.active[2], product=product)
    require(final_inputs == inputs,
            "Source, review, receipt, credential or consent changed during observation")
    actual_consent = final_inputs[1]
    require(result == (actual_consent["view"] if product else actual_consent),
            "Semantic result differs from the actual sealed consent")
    # current() normally rejects a closed frame; this last fence is explicitly
    # fresh and does not reopen one or return a cached owner/clock verdict.
    from .personal_episode import same_observation
    same_observation(closing.active[2], c.memory.inspect())
    c.episode_fence()
    now = c.clock()
    view = actual_consent["view"]
    require(type(now) is int and view["issued_at"] <= now < view["expires_at"],
            "Operation consent expired during final observation")
    return result


def publication_live(publication):
    """One publication read, never inherited by a later callback or effect."""
    return _live(publication)


def product_live(product):
    """Only the local non-genuine product read; never its native/write fence."""
    return _live(product, product=True)
