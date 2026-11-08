"""Small state registry used by the standalone SLA watcher."""

from __future__ import annotations

from threading import RLock

from ..domain.contracts import CaseState


class CaseRegistry:
    """Snapshot registry for operational inspection, not a graph replacement."""

    def __init__(self) -> None:
        self._states: dict[str, CaseState] = {}
        self._lock = RLock()

    def record(self, state: CaseState) -> None:
        with self._lock:
            self._states[state.correlation_id] = state.model_copy(deep=True)

    def get(self, correlation_id: str) -> CaseState | None:
        with self._lock:
            state = self._states.get(correlation_id)
            return state.model_copy(deep=True) if state else None

    def all(self) -> tuple[CaseState, ...]:
        with self._lock:
            return tuple(state.model_copy(deep=True) for state in self._states.values())
