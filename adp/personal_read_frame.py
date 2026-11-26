"""Invocation-local historical facts; current state is never cached.

Personal storage is trusted against malicious same-UID changes during this
lexical invocation. Entry/restart authenticates the original bytes. Concurrent
canonical transitions and every live authority condition remain observable.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import os
import threading

from .schema import require
from .discovery_schema import digest

_CURRENT = ContextVar("accounting_historical_facts", default=None)
_READ_ONLY = ContextVar("accounting_read_only", default=False)


def _identity(c):
    from .codex_runtime import _host_identity
    return (os.getpid(), threading.get_ident(), id(c), id(c.personal), id(c.memory), id(c.runtime),
            c.task_id, c.personal.repository_id, c.runtime.host, str(c.runtime.directory),
            str(c.memory.config.root), str(c.memory.common), str(c.memory.control), _host_identity())


def protected_runtime(directory=None):
    """Authenticate actual personal receipt files, including newly made ones."""
    active = _CURRENT.get() is not None
    if active and directory is not None:
        import stat
        from .config import safe_path
        info = safe_path(directory).stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
                "Runtime evidence directory is not owned and protected")
    return active


def forbid_writes():
    require(not _READ_ONLY.get(), "Accounting observation cannot admit, write or execute effects")


@contextmanager
def qualification(c):
    if not getattr(c, "episode", False):
        yield
        return
    parent = _CURRENT.get()
    if parent is not None and parent["c"] is c:
        require(_identity(c) == parent["identity"], "Historical invocation identity changed")
        yield
        return
    scope = {"c": c, "identity": _identity(c), "capture": None}
    token = _CURRENT.set(scope)
    try:
        capture = {}
        c.personal._active_view(memory=c.memory, allow_expired=True, _capture=capture)
        from .personal_recovery import engine_digest
        master, receipt, contexts, _, workers = capture["archive"]
        scope["capture"] = {k: deepcopy(capture[k]) for k in ("historical_basis", "historical_engine", "installed")}
        scope["capture"]["archive"] = deepcopy((master, receipt, contexts, None, workers))
        scope["reader_engine"] = engine_digest()
        require(_identity(c) == scope["identity"], "Historical invocation identity changed at entry")
        yield
    finally:
        _CURRENT.reset(token)


def qualified(function):
    """Use the existing operation body with one lexical historical basis."""
    @wraps(function)
    def call(self, *args, **kwargs):
        with qualification(getattr(self, "c", self)):
            return function(self, *args, **kwargs)
    return call


def reader_engine(capture):
    scope = _CURRENT.get()
    if scope is not None and scope["capture"] is not None:
        require(_identity(scope["c"]) == scope["identity"], "Historical invocation identity changed")
        require(all(capture[k] == scope["capture"][k] for k in ("historical_basis", "historical_engine")),
                "Historical binding differs from this invocation")
        return scope["reader_engine"]
    from .personal_recovery import engine_digest
    return engine_digest()


def archive(personal, memory, runtime, child, *, _capture=None):
    scope = _CURRENT.get()
    if scope is None or scope["capture"] is None:
        return None
    c = scope["c"]
    if personal is not c.personal.root or child is not c.personal or memory is not c.memory or runtime is not None:
        return None
    require(_identity(c) == scope["identity"], "Historical invocation identity changed")
    capture = deepcopy(scope["capture"])
    master, receipt, contexts, _, workers = capture["archive"]
    actual = memory.inspect(recovery=True)
    from .personal_history import current_history
    current_history(memory, master, receipt, actual, basis=capture["historical_basis"])
    if _capture is not None:
        _capture.update(capture)
        _capture["subject"] = actual
        _capture["archive"] = (master, receipt, contexts, actual, workers)
        _capture["episode_intent"] = {"descriptor": digest(child.descriptor),
            "base": receipt["result"], "state": capture["installed"][0], "tasks": capture["installed"][1]}
    return master, receipt, contexts, actual, workers


def current_source(owner, consent, *, product=False):
    """Current source fence; no historical receipts or object-byte replay."""
    from .discovery_schema import digest
    from .execution_containment import admin_seal
    from .personal_enrollment import governance
    from .personal_history_product_git import administration
    view, c = consent["view"], owner.c
    root = c.personal.feature
    require(owner.port._value("rev-parse", "HEAD") == view["revision"] == c.revision()
            and owner.port._value("--no-replace-objects", "rev-parse", "HEAD^{tree}") == view["source_tree" if product else "tree"]
            and owner.port._value("symbolic-ref", "HEAD") == view["source_ref"] == "refs/heads/" + c.personal.plan["feature"]["branch"]
            and not owner.port._value("status", "--porcelain", "--untracked-files=all")
            and digest(administration(root)) == view["administration"]
            and digest(governance(root)) == c.personal.plan["governance_digest"]
            and owner.transport.credential_binding == consent["binding" if product else "credential_binding"],
            "Current source, administration, governance or credential differs from consent")
    administration_digest = admin_seal(root)
    for option in ("-v", "-f"):
        require(all(row.startswith(b"H ") for row in owner.port._git("ls-files", option, "-z").split(b"\0") if row),
                "Unsupported hidden index flags")
    return administration_digest


def historical_source(c, master, observed):
    """Fresh original source/admin at batch and pre-CAS boundaries only."""
    from pathlib import Path
    from .execution_containment import source_seal
    from .personal_history_product_git import administration
    from .personal_history import validate_administration
    from .personal_storage import read_private
    from .accounting_policy import entry
    root = c.personal.root
    require(master["engine"] == c.personal.descriptor["base"]["engine"], "Historical recovery source changed")
    seals = master["view"]["binding"]["evidence"]["seals"]
    require(source_seal(root.feature) == seals["feature"]
            and source_seal(root.feature, tuple(root.plan["paths"])) == seals["outside"]
            and source_seal(Path(root.plan["checkout"]["path"])) == seals["outer"], "Original unaccepted source changed")
    run = read_private(root.state / "run.json")
    require(administration(Path(root.plan["checkout"]["path"])) == root.plan["administration"]
            and (run["feature_administration"] is None or administration(root.feature) == run["feature_administration"]),
            "Original physical administration changed")
    validate_administration(root, master, entry(observed["state"]), observed, child=c.personal)


def _live(owner, *, product=False, _capture=None):
    with qualification(owner.c):
        token = _READ_ONLY.set(True)
        try:
            before = owner.c.memory.inspect()
            consent = deepcopy(owner.active) if product else owner.record(_observed=before)
            require(consent is not None, "Exact operation consent required")
            opening_source = current_source(owner, consent, product=product)
            result = owner._live_current(**({"genuine": False} if product else {"review": True}))
            closing_source = current_source(owner, owner.active if product else result, product=product)
            require(opening_source == closing_source, "Current Git administration changed during observation")
            from .personal_episode import same_observation
            closing = owner.c.memory.inspect()
            same_observation(before, closing)
            expected = owner.active["view"] if product else owner.record(_observed=closing)
            require(result == expected and consent == (owner.active if product else expected), "Current operation consent changed")
            if _capture is not None:
                scope = _CURRENT.get()
                _capture.update(deepcopy(scope["capture"]))
                actual = closing
                from .personal_history import current_history
                current_history(owner.c.memory, _capture["archive"][0], _capture["archive"][1], actual,
                                basis=_capture["historical_basis"])
                m, receipt, contexts, _, workers = _capture["archive"]
                _capture["archive"] = (m, receipt, contexts, actual, workers)
                _capture.update(subject=actual, identity=_identity(owner.c), consent=deepcopy(result), source_admin=closing_source)
            owner.c.episode_fence()
            view = expected if product else expected["view"]
            require(view["issued_at"] <= owner.c.clock() < view["expires_at"], "Operation consent expired during closing observation")
            return deepcopy(result)
        finally:
            _READ_ONLY.reset(token)


def publication_live(publication, *, _capture=None):
    return _live(publication, _capture=_capture)


def product_live(product):
    return _live(product, product=True)
