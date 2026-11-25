"""Private synchronous publication/product reads; never an authority cache."""
from contextvars import ContextVar
from copy import deepcopy
import os
import threading

from .discovery_schema import digest
from .schema import require

_CURRENT = ContextVar("accounting_publication_read", default=None)


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
    before = first.run()
    # Construct with the shortcut unavailable: raw host/receipt/source/Git and
    # lineage proof is independently repeated, never checked from the frame.
    final = _Read(owner, product=product)
    require(final.identity == first.identity and final.active == first.active
            and final.archive == first.archive and final.consent == first.consent,
            "Accounting evidence changed during publication observation")
    after = final.run()  # Re-read actual publication/review/credential inputs too.
    require(after == before, "Publication subject changed during read-only observation")
    # The second local pass can itself race a retained-evidence change. Its
    # input proof is not a closing proof: independently authenticate AGAIN
    # after every framed body, with no body following this final capture.
    closing = _Read(owner, product=product)
    require(closing.identity == final.identity and closing.active == final.active
            and closing.archive == final.archive and closing.consent == final.consent,
            "Accounting evidence changed during final publication read")
    closing.closed = True
    # current() normally rejects a closed frame; this last fence is explicitly
    # fresh and does not reopen one or return a cached owner/clock verdict.
    from .personal_episode import same_observation
    same_observation(closing.active[2], c.memory.inspect())
    c.episode_fence()
    now = c.clock()
    view = after if product else after["view"]
    require(type(now) is int and view["issued_at"] <= now < view["expires_at"],
            "Operation consent expired during final observation")
    return after


def publication_live(publication):
    """One publication read, never inherited by a later callback or effect."""
    return _live(publication)


def product_live(product):
    """Only the local non-genuine product read; never its native/write fence."""
    return _live(product, product=True)
