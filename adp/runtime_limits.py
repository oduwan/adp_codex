"""One optional operator JSON resource profile; no execution authority.

Configuration failure falls back here only. Product/authority exceptions and
cancellation are never caught by the execution scopes below.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from functools import wraps
import math
import os
from pathlib import Path
import time
from types import MappingProxyType


@dataclass(frozen=True)
class Parameter:
    minimum: int
    default: int
    maximum: int


PARAMETERS = MappingProxyType({
    "request_timeout_seconds": Parameter(3, 10, 30),
    "operation_timeout_seconds": Parameter(40, 120, 300),
    "request_limit": Parameter(64, 128, 256),
})


def _reason(name, value):
    spec = PARAMETERS[name]
    if type(value) is not int:
        return "expected an integer, excluding boolean"
    if not spec.minimum <= value <= spec.maximum:
        return "outside permitted range"
    return None


@dataclass(frozen=True)
class RuntimeLimits:
    request_timeout_seconds: int = PARAMETERS["request_timeout_seconds"].default
    operation_timeout_seconds: int = PARAMETERS["operation_timeout_seconds"].default
    request_limit: int = PARAMETERS["request_limit"].default

    def __post_init__(self):
        for name in PARAMETERS:
            reason = _reason(name, getattr(self, name))
            if reason:
                raise ValueError(name + ": " + reason)

    def values(self):
        return asdict(self)


DEFAULTS = RuntimeLimits()
# Only for immutable pre-extension consent. Never a configuration fallback.
LEGACY = RuntimeLimits(5, 45, 128)


@dataclass(frozen=True)
class Diagnostic:
    kind: str
    parameter: str | None = None
    rejected: str | None = None
    reason: str | None = None
    fallback: int | None = None
    error_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RuntimeSettings:
    limits: RuntimeLimits = DEFAULTS
    diagnostics: tuple[Diagnostic, ...] = ()
    loading_seconds: float = 0.0


def _error(exc):
    # Private only. Preserve the underlying error without unbounded payloads.
    chain = []
    for _ in range(3):
        try:
            message = str(exc)[:512]
        except Exception:
            message = "unprintable loading error"
        chain.append(type(exc).__name__ + ": " + message)
        exc = exc.__cause__
        if exc is None:
            break
    return " <- ".join(chain)


def load_runtime_limits(path=None):
    """Single external loading/validation entry; returns a frozen snapshot.

    Diagnostics may contain rejected configuration/private paths. They are not
    logged to product output, portable memory, Worker prompts or GitHub.
    """
    started = time.monotonic()
    diagnostics, values = [], DEFAULTS.values()
    try:
        from .config import load_json
        if path is None:
            selected = os.environ.get("ADP_RUNTIME_LIMITS_FILE")
            if selected is None:
                directory = os.environ.get("XDG_CONFIG_HOME")
                if not directory:
                    import pwd  # Only needed for the owning-home fallback.
                    directory = str(Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config")
                selected = str(Path(directory) / "adp-codex" / "runtime-limits.json")
            path = Path(selected)
        payload = load_json(Path(path), protected=True)
        if set(payload) - set(PARAMETERS):
            raise ValueError("unknown runtime configuration keys")
        for name, value in payload.items():
            reason = _reason(name, value)
            if reason:
                diagnostics.append(Diagnostic("INVALID_VALUE", name, repr(value)[:512], reason, values[name]))
            else:
                values[name] = value
        limits = RuntimeLimits(**values)
    except FileNotFoundError as exc:
        limits = DEFAULTS
        diagnostics = [Diagnostic("MISSING_FILE", error_type=type(exc).__name__, error=_error(exc))]
    except Exception as exc:
        limits = DEFAULTS
        diagnostics = [Diagnostic("CONFIGURATION_FAILURE", error_type=type(exc).__name__, error=_error(exc))]
    elapsed = time.monotonic() - started
    current = current_budget()
    if current is not None:
        row = current.work.setdefault("configuration.load", {"calls": 0, "seconds": 0.0})
        row["calls"] += 1; row["seconds"] += elapsed
    return RuntimeSettings(limits, tuple(diagnostics), elapsed)


def request_allowance(seconds):
    """Validate a derived allowance, whose remainder may be below the minimum."""
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= PARAMETERS["request_timeout_seconds"].maximum):
        raise ValueError("Invalid bounded request allowance")
    return seconds


_CURRENT = ContextVar("adp_runtime_operation", default=None)
_CONSENT_CAPS = ContextVar("adp_runtime_consent_caps", default=())


def settings_for(owner=None, settings=None):
    candidate = settings or getattr(owner, "runtime_settings", None)
    current = _CURRENT.get()
    candidate = candidate or (current.settings if current is not None else None)
    if candidate is None:
        return load_runtime_limits()
    if type(candidate) is not RuntimeSettings or type(candidate.limits) is not RuntimeLimits:
        raise TypeError("Use the validated runtime settings snapshot")
    return candidate


@dataclass
class Budget:
    end: float
    calls: int = 0
    settings: RuntimeSettings = field(default_factory=RuntimeSettings)
    started: float = field(default_factory=time.monotonic)
    name: str = "network"
    request_seconds: float | None = None
    maximum_calls: int | None = None
    latencies: list = field(default_factory=list)
    work: dict = field(default_factory=dict)
    execution_seconds: float = 0.0
    execution_depth: int = 0
    transport_calls: int = 0

    def __post_init__(self):
        if self.request_seconds is None:
            self.request_seconds = self.settings.limits.request_timeout_seconds
        if self.maximum_calls is None:
            self.maximum_calls = self.settings.limits.request_limit

    def check(self):
        from .schema import require
        require(time.monotonic() < self.end and self.calls <= self.maximum_calls,
                "Network operation exhausted its fixed budget")

    def request_deadline(self, seconds=None):
        self.calls += 1
        self.check()
        allowance = self.request_seconds if seconds is None else min(self.request_seconds, request_allowance(seconds))
        return min(self.end, time.monotonic() + allowance)

    def tighten(self, limits=None, seconds=None):
        from .schema import require
        if limits is not None:
            require(type(limits) is RuntimeLimits, "Validated runtime limits required")
            self.end = min(self.end, self.started + limits.operation_timeout_seconds)
            self.request_seconds = min(self.request_seconds, limits.request_timeout_seconds)
            self.maximum_calls = min(self.maximum_calls, limits.request_limit)
        if seconds is not None:
            require(type(seconds) in (int, float) and math.isfinite(seconds) and seconds > 0,
                    "Original runtime allowance is expired")
            self.end = min(self.end, time.monotonic() + seconds)
        self.check()

    def summary(self, outcome):
        elapsed = time.monotonic() - self.started
        return {"name": self.name, "outcome": outcome, "wall_seconds": elapsed,
                "request_attempts": self.calls, "transport_calls": self.transport_calls,
                "request_latencies_seconds": tuple(self.latencies),
                "configuration_loading_seconds": self.work.get("configuration.load", {}).get("seconds", 0.0),
                "profile_initial_loading_seconds": self.settings.loading_seconds,
                "configuration_events": tuple(d.kind for d in self.settings.diagnostics),
                "substantive_execution_seconds": self.execution_seconds,
                "orchestration_seconds": max(0.0, elapsed - self.execution_seconds),
                "work": {name: dict(row) for name, row in self.work.items()}}


def current_budget():
    return _CURRENT.get()


def measurements_for(owner):
    """Private per-client bounded evidence, never source/authority state."""
    history = getattr(owner, "runtime_measurements", None)
    if history is None:
        history = deque(maxlen=64)
        owner.runtime_measurements = history
    return history


@contextmanager
def operation_scope(settings, *, name="network", seconds=None, budget=None, measurements=None):
    parent = _CURRENT.get()
    current = budget or parent
    root = current is None
    if root:
        started = time.monotonic()
        current = Budget(started + settings.limits.operation_timeout_seconds,
                         settings=settings, started=started, name=name)
    current.tighten(settings.limits, seconds)
    for profile in _CONSENT_CAPS.get():
        current.tighten(profile)
    token = _CURRENT.set(current)
    outcome = "ERROR"
    try:
        yield current
        current.check()
        outcome = "RETURNED"
    finally:
        _CURRENT.reset(token)
        if root and measurements is not None:
            measurements.append(current.summary(outcome))


def network_operation(name, *, service=lambda self, *a, **k: self.service,
                      enabled=lambda self, *a, **k: True):
    """One synchronous outer budget; contains no operation exception fallback."""
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            if not enabled(self, *args, **kwargs):
                return function(self, *args, **kwargs)
            selected = service(self, *args, **kwargs)
            with selected.bounded(name=name):
                return function(self, *args, **kwargs)
        return wrapped
    return decorate


def read_operation(name, *, transport=lambda self, *a, **k: self.transport):
    """Aggregate GET inventory scope; fixtures need no HTTP implementation."""
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            with operation_scope(settings_for(transport(self, *args, **kwargs)), name=name,
                                 measurements=measurements_for(self)):
                return function(self, *args, **kwargs)
        return wrapped
    return decorate


def http_request(function):
    """Existing urllib ports share resource accounting, never route authority."""
    @wraps(function)
    def wrapped(self, *args, seconds=None, **kwargs):
        with operation_scope(self.runtime_settings, name="http.request", measurements=measurements_for(self)) as budget:
            deadline = budget.request_deadline(seconds)
            started = time.monotonic()
            budget.transport_calls += 1
            try:
                result = function(self, *args, seconds=deadline - time.monotonic(), **kwargs)
                from .schema import require
                require(time.monotonic() < deadline, "Network request exhausted its fixed budget")
                return result
            finally:
                budget.latencies.append(time.monotonic() - started)
    return wrapped


def consent_limits(view):
    """Private consent is authority data: malformed data never defaults."""
    from .schema import require
    raw = view.get("runtime_limits")
    if raw is None and "runtime_limits" not in view:
        return LEGACY
    require(type(raw) is dict and set(raw) == set(PARAMETERS), "Invalid exact runtime consent")
    require(all(_reason(name, value) is None for name, value in raw.items()), "Invalid exact runtime consent")
    return RuntimeLimits(**raw)


def bind_consent(view, now=None):
    profile = consent_limits(view)
    current = current_budget()
    if current is not None:
        current.tighten(profile, view["expires_at"] - now if now is not None else None)
    return profile


@contextmanager
def consent_scope(view):
    """Resource caps only: no clock, counter, cached approval or Worker budget."""
    profile = consent_limits(view)
    token = _CONSENT_CAPS.set((*_CONSENT_CAPS.get(), profile))
    try:
        bind_consent(view)
        yield
    finally:
        _CONSENT_CAPS.reset(token)


@contextmanager
def work_span(name, *, execution=False):
    current = current_budget()
    if current is None:
        yield
        return
    started = time.monotonic()
    top = execution and current.execution_depth == 0
    if execution:
        current.execution_depth += 1
    try:
        yield
    finally:
        elapsed = time.monotonic() - started
        row = current.work.setdefault(name, {"calls": 0, "seconds": 0.0})
        row["calls"] += 1
        row["seconds"] += elapsed
        if execution:
            current.execution_depth -= 1
        if top:
            current.execution_seconds += elapsed


def measured(name, *, execution=False):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with work_span(name, execution=execution):
                return function(*args, **kwargs)
        return wrapped
    return decorate
