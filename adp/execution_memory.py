"""Conductor extension using the accepted M1 transaction, token and queue."""
from __future__ import annotations

import copy
import os
from contextlib import contextmanager

from .errors import AuthorityError
from .execution_schema import execution_schema
from .schema import require
from .storage import locked


@contextmanager
def invocation_lock(directory):
    import fcntl
    from .config import safe_path
    from .errors import Conflict
    path = safe_path(directory / "conductor-invocation.lock")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Conflict("Another Conductor invocation owns this local execution queue") from exc
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


class QueuedMemory:
    """Conductor-local observational serialization, without read-side writes.

    The accepted M1 inspector stays read-only and unchanged. During parallel
    execution, serialize its observations with the accepted mutation queue so
    a sibling cannot inspect an atomic writer's private temporary slot.
    """
    def __init__(self, memory):
        self._memory = memory

    def __getattr__(self, name):
        return getattr(self._memory, name)

    def inspect(self):
        from .storage import _MUTEX
        with _MUTEX:
            return self._memory.inspect()


class ExecutionJournal:
    def __init__(self, memory):
        self.memory = memory

    def upgrade(self, *, authorized=False):
        if not authorized:
            raise AuthorityError("Execution migration requires explicit memory-write authorization")
        with locked(self.memory.control):
            head, state, tasks = self.memory._start()
            if state["schema_version"] == 3:
                return self.memory.inspect()
            require(state["schema_version"] == 2, "Upgrade guard explicitly before enabling execution")
            state["schema_version"] = 3
            state["execution"] = {"schema_version": 1, "repository_id": self.memory.config.identity,
                                  "tasks": {}, "actions": {}, "publications": {}}
            return self.memory._checkpoint(head, state, tasks)

    def inspect(self):
        observed = self.memory.inspect()
        require(observed["health"] == "SYNCED", "Execution needs synchronized memory; use explicit recovery")
        require(observed["state"]["schema_version"] == 3, "Explicit execution upgrade is required")
        return observed

    def change(self, callback):
        with locked(self.memory.control):
            head, state, tasks = self.memory._start()
            require(state["schema_version"] == 3, "Explicit execution upgrade is required")
            before = copy.deepcopy(state["execution"])
            coordination = copy.deepcopy({k: v for k, v in state.items() if k != "execution"})
            original_tasks = copy.deepcopy(tasks)
            result = callback(state["execution"], state, tasks)
            require(coordination == {k: v for k, v in state.items() if k != "execution"}
                    and original_tasks == tasks, "Execution journal cannot mutate accepted task/guard/owner fields")
            execution_schema(state["execution"], self.memory.config.identity)
            if before != state["execution"]:
                self.memory._checkpoint(head, state, tasks)
            return result
