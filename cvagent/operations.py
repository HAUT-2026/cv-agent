"""Operational controls, allowlists, retries and idempotent simulated effects."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from threading import RLock
import time
from typing import Callable, Generic, TypeVar

from .audit import DecisionLog
from .contracts import CaseState, RazónParada


class ToolNotAllowedError(PermissionError):
    """Raised when an agent attempts a tool outside its allowlist."""


class KillSwitchActiveError(RuntimeError):
    """Raised when a guarded external action is in a paused scope."""


class TransientOperationError(RuntimeError):
    """A retryable adapter failure."""


@dataclass(frozen=True)
class ToolCall:
    correlation_id: str
    agente: str
    herramienta: str
    permitida: bool
    razon: str


@dataclass(frozen=True)
class KillSwitch:
    alcance: str
    valor: str
    causa: str
    activado_en: float


class OperationalControls:
    """Gateway policy; credentials and tokens are intentionally not accepted."""

    def __init__(self, *, decision_log: DecisionLog | None = None) -> None:
        self._allowlist: dict[str, frozenset[str]] = {}
        self._calls: list[ToolCall] = []
        self._switches: list[KillSwitch] = []
        self._log = decision_log
        self._lock = RLock()

    def set_allowlist(self, agente: str, herramientas: set[str] | frozenset[str]) -> None:
        with self._lock:
            self._allowlist[agente] = frozenset(herramientas)

    @property
    def calls(self) -> tuple[ToolCall, ...]:
        with self._lock:
            return tuple(self._calls)

    @property
    def kill_switches(self) -> tuple[KillSwitch, ...]:
        with self._lock:
            return tuple(self._switches)

    def call_tool(
        self,
        *,
        correlation_id: str,
        agente: str,
        herramienta: str,
        vacante_id: str,
    ) -> None:
        """Authorize a call and record both success and rejection."""

        with self._lock:
            allowed = herramienta in self._allowlist.get(agente, frozenset())
            reason = "allowlist_match" if allowed else "tool_not_allowed"
            self._calls.append(ToolCall(correlation_id, agente, herramienta, allowed, reason))
            if not allowed:
                if self._log:
                    self._log.append(
                        correlation_id=correlation_id,
                        tiempo=time_now_utc(),
                        componente="tool-gateway",
                        fuente=["allowlist"],
                        versiones={"policy": "1.0.0"},
                        razon=RazónParada.HERRAMIENTA_NO_PERMITIDA.value,
                    )
                raise ToolNotAllowedError(
                    f"tool '{herramienta}' is not allowed for agent '{agente}'"
                )
            self._ensure_external_allowed_locked(
                correlation_id=correlation_id,
                vacante_id=vacante_id,
                agente=agente,
                herramienta=herramienta,
            )

    def activate_kill_switch(self, *, alcance: str, valor: str, causa: str) -> KillSwitch:
        if alcance not in {"vacante", "agente", "sistema"}:
            raise ValueError("kill switch alcance must be vacante, agente, or sistema")
        switch = KillSwitch(alcance, valor, causa, time_now_utc().timestamp())
        with self._lock:
            self._switches.append(switch)
        return switch

    def resume_kill_switch(self, *, alcance: str, valor: str, aprobador: str) -> None:
        """Explicitly remove a switch; expiration never performs this action."""

        if not aprobador:
            raise ValueError("an explicit approver is required to resume")
        with self._lock:
            self._switches = [
                switch
                for switch in self._switches
                if not (switch.alcance == alcance and switch.valor == valor)
            ]

    def is_blocked(self, *, vacante_id: str, agente: str) -> bool:
        with self._lock:
            return self._matching_switch_locked(vacante_id, agente) is not None

    def ensure_external_allowed(
        self, *, correlation_id: str, vacante_id: str, agente: str, herramienta: str
    ) -> None:
        with self._lock:
            self._ensure_external_allowed_locked(
                correlation_id=correlation_id,
                vacante_id=vacante_id,
                agente=agente,
                herramienta=herramienta,
            )

    def _ensure_external_allowed_locked(
        self, *, correlation_id: str, vacante_id: str, agente: str, herramienta: str
    ) -> None:
        switch = self._matching_switch_locked(vacante_id, agente)
        if switch is None:
            return
        if self._log:
            self._log.append(
                correlation_id=correlation_id,
                tiempo=time_now_utc(),
                componente="kill-switch",
                fuente=["operational-controls"],
                versiones={"policy": "1.0.0"},
                razon=RazónParada.KILL_SWITCH_ACTIVO.value,
            )
        raise KillSwitchActiveError(
            f"external tool '{herramienta}' blocked by {switch.alcance}:{switch.valor}"
        )

    def _matching_switch_locked(self, vacante_id: str, agente: str) -> KillSwitch | None:
        for switch in reversed(self._switches):
            if switch.alcance == "sistema":
                return switch
            if switch.alcance == "vacante" and switch.valor == vacante_id:
                return switch
            if switch.alcance == "agente" and switch.valor == agente:
                return switch
        return None


T = TypeVar("T")


class RetryExecutor(Generic[T]):
    """Finite exponential backoff with reconciliation before every attempt."""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_delay_seconds: float = 0.1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative")
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.sleep = sleep

    def run(
        self,
        *,
        idempotency_key: str,
        operation: Callable[[str], T],
        reconcile: Callable[[str], T | None],
    ) -> tuple[T, int]:
        for attempt in range(1, self.max_attempts + 1):
            existing = reconcile(idempotency_key)
            if existing is not None:
                return existing, attempt - 1
            try:
                return operation(idempotency_key), attempt
            except TransientOperationError:
                if attempt == self.max_attempts:
                    raise
                self.sleep(self.base_delay_seconds * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")


class SQLiteEffectStore:
    """Tiny local receipt store used only by simulated adapters and tests."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS effects (idempotency_key TEXT PRIMARY KEY, result_ref TEXT NOT NULL)"
        )
        self._connection.commit()
        self._lock = RLock()

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT result_ref FROM effects WHERE idempotency_key = ?", (key,)
            ).fetchone()
            return row[0] if row else None

    def put(self, key: str, result_ref: str) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT OR IGNORE INTO effects(idempotency_key, result_ref) VALUES (?, ?)",
                (key, result_ref),
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class SimulatedDeliveryGateway:
    """No-network delivery double with durable local idempotency receipts."""

    def __init__(self, store: SQLiteEffectStore | None = None) -> None:
        self.store = store or SQLiteEffectStore()
        self.calls = 0
        self.transient_failures_remaining = 0

    def enviar(self, propuesta, *, idempotency_key: str) -> str:
        existing = self.store.get(idempotency_key)
        if existing is not None:
            return existing
        self.calls += 1
        if self.transient_failures_remaining:
            self.transient_failures_remaining -= 1
            raise TransientOperationError("synthetic transient delivery failure")
        result_ref = f"simulated-delivery:{idempotency_key}"
        self.store.put(idempotency_key, result_ref)
        return result_ref


def time_now_utc():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


__all__ = [
    "KillSwitchActiveError",
    "OperationalControls",
    "RetryExecutor",
    "SQLiteEffectStore",
    "SimulatedDeliveryGateway",
    "ToolCall",
    "ToolNotAllowedError",
    "TransientOperationError",
]
