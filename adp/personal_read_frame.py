"""Private synchronous publication/product reads; never an authority cache."""
from contextvars import ContextVar
from copy import deepcopy
import os
import hashlib
import re
import stat
import threading

from .discovery_schema import digest
from .schema import require

_CURRENT = ContextVar("accounting_publication_read", default=None)


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
    return digest({"consent": deepcopy(owner.active) if product else owner.record(_observed=observed), "run": c.record(),
        "workers": workers, "private": files,
        "head": owner.port._value("rev-parse", "HEAD"), "tree": owner.port._value("--no-replace-objects", "rev-parse", "HEAD^{tree}"),
        "ref": owner.port._value("symbolic-ref", "HEAD"), "dirty": owner.port._value("status", "--porcelain", "--untracked-files=all"),
        "physical": administration(root), "admin": admin_seal(root), "governance": governance(root),
        "credential": owner.transport.credential_binding})


def forbid_writes():
    require(_CURRENT.get() is None, "Accounting publication observation cannot admit, write or execute effects")


def _identity(c):
    p, r, m = c.personal, c.runtime, c.memory
    return (os.getpid(), threading.get_ident(), id(c), id(p), id(p.root), id(m), id(r),
            c.task_id, p.repository_id, digest(p.intent), digest(p.descriptor), digest(p.root.intent),
            str(m.config.root), str(m.common), str(m.control), r.host, str(r.directory))


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

    def current(self):
        require(not self.closed and self.owner.c is self.c and _identity(self.c) == self.identity
                and (not self.product or self.owner.active == self.consent),
                "Accounting publication read context changed")
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
    result = first.run()  # Every original semantic predicate executes once.
    # The shortcut is unavailable here. No semantic body follows this truly
    # closing full raw/host/source/lineage proof.
    closing = _Read(owner, product=product)
    require(closing.identity == first.identity and closing.active == first.active
            and closing.archive == first.archive and closing.consent == first.consent,
            "Accounting evidence changed during final publication read")
    closing.closed = True
    require(_inputs(owner, closing.active[2], product=product) == inputs,
            "Source, review, receipt, credential or consent changed during observation")
    # current() normally rejects a closed frame; this last fence is explicitly
    # fresh and does not reopen one or return a cached owner/clock verdict.
    from .personal_episode import same_observation
    same_observation(closing.active[2], c.memory.inspect())
    c.episode_fence()
    now = c.clock()
    view = result if product else result["view"]
    require(type(now) is int and view["issued_at"] <= now < view["expires_at"],
            "Operation consent expired during final observation")
    return result


def publication_live(publication):
    """One publication read, never inherited by a later callback or effect."""
    return _live(publication)


def product_live(product):
    """Only the local non-genuine product read; never its native/write fence."""
    return _live(product, product=True)
