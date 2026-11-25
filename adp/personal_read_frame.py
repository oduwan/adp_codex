"""Private synchronous publication/product reads; never an authority cache."""
from contextvars import ContextVar
from contextlib import contextmanager
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
_BOUND_BYTES = ContextVar("accounting_actual_private_inputs", default=None)


def _monitored(frame, path):
    return str(path) in frame.readset or any(path.is_relative_to(root) for root in frame.roots)


def private_path(path):
    """Private-proof callers cannot silently follow an undeclared pointer."""
    frame = _BOUND_BYTES.get()
    if frame is not None:
        frame.context()
        require(_monitored(frame, Path(os.path.abspath(path))), "Private proof is outside the sealed inputs")


def present(path):
    """Compare the caller's actual existence observation, never synthesize it."""
    actual = path.exists()
    frame = _BOUND_BYTES.get()
    if frame is not None:
        frame.context()
        path = Path(os.path.abspath(path))
        if _monitored(frame, path):
            require(actual == (frame.readset.get(str(path)) is not None), "Private proof presence changed during observation")
    return actual


def json_names(directory, names):
    """Constrain actual selector names without returning remembered entries."""
    frame = _BOUND_BYTES.get()
    if frame is not None:
        frame.context()
        directory = Path(os.path.abspath(directory))
        if any(directory.is_relative_to(root) for root in frame.roots):
            expected = sorted(Path(p).name for p, value in frame.readset.items()
                if value is not None and Path(p).parent == directory and p.endswith(".json"))
            require(sorted(names) == expected, "Private proof inventory changed during observation")


def consumed(path, raw=None, metadata=None):
    """Deny changed actual inputs; never return remembered bytes or authority."""
    frame = _BOUND_BYTES.get()
    if frame is None:
        return
    frame.context()
    path = Path(os.path.abspath(path))
    name = str(path)
    if not _monitored(frame, path):
        return  # Current M1/control reads remain actual, outside private proofs.
    expected = frame.readset.get(name)  # Closed inventory proves omitted paths absent.
    if metadata is None:
        require(raw is None and expected is None, "Private proof presence changed during observation")
        return
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid()
            and metadata.st_nlink == 1 and not metadata.st_mode & 0o077
            and (frame.c.track is None or not path.is_relative_to(frame.c.track.root / "archive")
                 or stat.S_IMODE(metadata.st_mode) == 0o600)
            and len(raw) == metadata.st_size <= _private_limit(frame.c, path) and expected is not None
            and hashlib.sha256(raw).hexdigest() == expected,
            "Actual private proof differs from the sealed protected input")


def _private_limit(c, path):
    from .personal_storage import LIMIT
    from .ticket_preparation import MAX_ARTIFACT
    return MAX_ARTIFACT if c.track is not None and path.is_relative_to(c.track.root / "archive") else LIMIT


def ticket_bytes(path, limit):
    """Frame-only opened-byte fence for the existing immutable ticket reader."""
    frame = _BOUND_BYTES.get()
    if frame is None:
        return None
    from .config import safe_path
    frame.context()
    path = safe_path(path)
    require(str(path) in frame.readset or any(path.is_relative_to(root) for root in frame.roots),
            "Ticket proof is outside the sealed private inputs")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(fd)
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_size <= limit
                and metadata.st_uid == os.geteuid() and metadata.st_nlink == 1
                and stat.S_IMODE(metadata.st_mode) == 0o600, "Unsafe bounded ticket proof")
        raw = os.read(fd, limit + 1)
        consumed(path, raw, metadata)
        return raw
    finally:
        os.close(fd)


def _private_inputs(c):
    """Closed, bounded private JSON inventory, including optional absence."""
    from .config import safe_path
    from .personal_storage import private_directory
    from .ticket_preparation import MAX_ARCHIVE, MAX_ARTIFACTS
    for path in (c.personal.root.directory, c.personal.root.state, c.personal.directory, c.personal.state):
        private_directory(path)
    roots = {c.personal.state, c.personal.root.state, c.personal.directory,
             c.runtime.directory, c.authority.directory}
    if c.track is not None:
        require(c.track.archive.directory == c.track.root / "archive", "Selected ticket archive identity changed")
        roots.add(c.track.root)
    roots = {safe_path(p) for p in roots}
    roots = tuple(sorted((p for p in roots if not any(p != other and p.is_relative_to(other)
                          for other in roots)), key=str))
    files, total, entries, ticket_total, tickets = {}, 0, 0, 0, 0
    pending = [(root, 0) for root in reversed(roots)]
    while pending:
        directory, depth = pending.pop()
        require(depth <= 16, "Private observation traversal exceeds depth bound")
        info = safe_path(directory).stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and not info.st_mode & 0o022, "Unverified private input directory")
        if c.track is not None and directory == c.track.root / "archive":
            require(stat.S_IMODE(info.st_mode) == 0o700, "Private ticket archive requires mode-0700 directory")
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
                    ticket = c.track is not None and path.is_relative_to(c.track.root / "archive")
                    files[str(path)] = _private_digest(path, limit=_private_limit(c, path), exact_mode=0o600 if ticket else None)
                    if ticket:
                        ticket_total += info.st_size
                        tickets += 1
                    else:
                        total += info.st_size
                    require(len(files) <= 1024 and total <= 8 * 1024 * 1024
                            and ticket_total <= MAX_ARCHIVE and tickets <= MAX_ARTIFACTS,
                            "Private observation inventory exceeds bound")
        pending.extend(sorted(children, key=lambda row: str(row[0]), reverse=True))
    for path in (c.personal.root.directory / "personal.json", Path(c.personal.plan["effects"]["marker"])):
        files[str(safe_path(path))] = _private_digest(path)
    if c.track is not None:
        from .personal_enrollment import marker
        require(len(c.track.originals) <= 8, "Bounded original marker inventory required")
        for identity in c.track.originals:
            path = marker(c.personal.root.plan["checkout"], c.personal.repository_id, identity.issue_id)
            files[str(safe_path(path))] = _private_digest(path)
    return files, roots


def _private_digest(path, *, limit=None, exact_mode=None):
    """Protected bounded byte observation, including honest absence."""
    from .config import safe_path
    from .personal_storage import LIMIT
    limit = LIMIT if limit is None else limit
    safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                and not info.st_mode & 0o077 and info.st_size <= limit
                and (exact_mode is None or stat.S_IMODE(info.st_mode) == exact_mode), "Unverified private observation input")
        raw = os.read(fd, limit + 1)
        require(len(raw) == info.st_size and len(raw) <= limit, "Private observation input was truncated or exceeds bound")
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
    require(_CURRENT.get() is None and _BOUND_BYTES.get() is None,
            "Accounting publication observation cannot admit, write or execute effects")


def _legacy_inputs(c, master):
    """Actual old source and administration; no duplicated admission rules."""
    from .execution_containment import source_seal
    from .personal_recovery import administration_snapshot
    from .personal_recovery import engine_digest
    from .personal_history_product_git import administration
    from .personal_storage import read_private
    root = c.personal.root
    require(engine_digest() == master["engine"], "Approved recovery source changed during observation")
    sources = {"feature": source_seal(root.feature),
        "outside": source_seal(root.feature, tuple(root.plan["paths"])),
        "outer": source_seal(Path(root.plan["checkout"]["path"]))}
    require(sources == {name: master["view"]["binding"]["evidence"]["seals"][name] for name in sources},
            "Original unaccepted source changed during observation")
    physical = {"feature": administration(root.feature), "checkout": administration(Path(root.plan["checkout"]["path"]))}
    run = read_private(root.state / "run.json")
    require(physical["checkout"] == root.plan["administration"]
            and (run["feature_administration"] is None or physical["feature"] == run["feature_administration"]),
            "Original physical administration changed during observation")
    return {"sources": sources, "physical": physical, "engine": master["engine"], "administration": administration_snapshot(root)}


def _identity(c):
    p, r, m = c.personal, c.runtime, c.memory
    return (os.getpid(), threading.get_ident(), id(c), id(p), id(p.root), id(m), id(r),
            c.task_id, p.repository_id, digest(p.intent), digest(p.descriptor), digest(p.root.intent),
            str(m.config.root), str(m.common), str(m.control), r.host, str(r.directory),
            str(p.directory), str(p.state), str(p.root.directory), str(p.root.state),
            id(c.authority), str(c.authority.directory), id(c.workers), str(c.workers.directory),
            id(c.track), str(c.track.root) if c.track is not None else None,
            id(c.track.archive) if c.track is not None else None,
            str(c.track.archive.directory) if c.track is not None else None,
            tuple(sorted(digest(i) for i in c.track.originals)) if c.track is not None else ())


class _Read:
    def __init__(self, owner, *, product=False):
        forbid_writes()
        c = owner.c
        self.owner, self.product = owner, product
        self.consent = deepcopy(owner.active) if product else None
        self.c, self.identity, self.closed = c, _identity(c), False
        self.readset, self.roots = _private_inputs(c)
        capture = {}
        with self.binding():
            # Actual proof executes without factual shortcuts. Only its real
            # consumed bytes are bound to the pre-observed protected inputs.
            self.active = deepcopy(c.personal._active_view(memory=c.memory, allow_expired=False,
                now=c.clock(), _capture=capture))
            self.archive = deepcopy(capture["archive"])
            self.administration = deepcopy(capture["historical_administration"])
            self.current()  # Full proof must end at this exact live subject.

    @contextmanager
    def binding(self):
        token = _BOUND_BYTES.set(self)
        try:
            self.context()
            yield
        finally:
            _BOUND_BYTES.reset(token)

    def inputs(self):
        with self.binding():
            result = _inputs(self.owner, self.active[2], product=self.product)
            require((result[2], result[3]) == (self.readset, self.roots),
                    "Private receipt or evidence changed after its actual proof")
            legacy = _legacy_inputs(self.c, self.archive[0])
            require(legacy["administration"] == self.administration,
                    "Actual historical administration differs from its full proof")
            return (*result, legacy)

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
            with self.binding():
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
    inputs = first.inputs()
    result = first.run()  # Every original semantic predicate executes once.
    # The shortcut is unavailable here. No semantic body follows this truly
    # closing full raw/host/source/lineage proof.
    closing = _Read(owner, product=product)
    require(closing.identity == first.identity and closing.active == first.active
            and closing.archive == first.archive and closing.consent == first.consent
            and closing.administration == first.administration,
            "Accounting evidence changed during final publication read")
    final_inputs = closing.inputs()
    closing.closed = True
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
