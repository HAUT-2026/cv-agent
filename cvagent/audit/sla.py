"""Standalone SLA watchdog; it observes and escalates but never approves."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from .log import DecisionLog
from ..domain.contracts import (
    CaseState,
    EstadoAprobacion,
    EstadoCaso,
    EstadoSLA,
    EstadoSLAInfo,
    RazónParada,
    TipoSLA,
)
from ..workflow.registry import CaseRegistry


@dataclass(frozen=True)
class SLAPolicy:
    tipo: TipoSLA
    recordatorio: timedelta
    escalamiento: timedelta
    vencimiento: timedelta | None = None


@dataclass(frozen=True)
class SLAEvent:
    correlation_id: str
    tipo: TipoSLA
    estado: EstadoSLA
    observado_en: datetime
    razon: str


@dataclass(frozen=True)
class SLAReport:
    events: tuple[SLAEvent, ...]
    states: tuple[CaseState, ...]


DEFAULT_POLICIES = {
    TipoSLA.LISTA_CORTA: SLAPolicy(
        tipo=TipoSLA.LISTA_CORTA,
        recordatorio=timedelta(hours=24),
        escalamiento=timedelta(hours=48),
        vencimiento=timedelta(hours=72),
    ),
    TipoSLA.MENSAJE: SLAPolicy(
        tipo=TipoSLA.MENSAJE,
        recordatorio=timedelta(hours=4),
        escalamiento=timedelta(hours=8),
    ),
}


class SLAWatchdog:
    """Inspect pending snapshots and append operational evidence."""

    def __init__(
        self,
        *,
        decision_log: DecisionLog,
        policies: dict[TipoSLA, SLAPolicy] | None = None,
    ) -> None:
        self.decision_log = decision_log
        self.policies = dict(policies or DEFAULT_POLICIES)
        self._emitted: set[tuple[str, TipoSLA, EstadoSLA]] = set()

    def register_policy(self, policy: SLAPolicy) -> None:
        """Add/replace a B3/B4.2-style deadline without changing graph code."""

        self.policies[policy.tipo] = policy

    def inspect(self, cases: Iterable[CaseState], *, now: datetime) -> SLAReport:
        if now.tzinfo is None:
            raise ValueError("SLA inspection time must be timezone-aware")
        events: list[SLAEvent] = []
        states: list[CaseState] = []
        for original in cases:
            state = original.model_copy(deep=True)
            if state.estado is EstadoCaso.PENDIENTE_APROBACION_LISTA and state.sla_lista:
                state, case_events = self._inspect_one(
                    state, TipoSLA.LISTA_CORTA, state.sla_lista, now
                )
            elif state.estado is EstadoCaso.PENDIENTE_APROBACION_MENSAJE and state.sla_mensaje:
                state, case_events = self._inspect_one(
                    state, TipoSLA.MENSAJE, state.sla_mensaje, now
                )
            else:
                case_events = []
            events.extend(case_events)
            states.append(state)
        return SLAReport(tuple(events), tuple(states))

    def inspect_registry(self, registry: CaseRegistry, *, now: datetime) -> SLAReport:
        report = self.inspect(registry.all(), now=now)
        for state in report.states:
            registry.record(state)
        return report

    def _inspect_one(
        self,
        state: CaseState,
        tipo: TipoSLA,
        info: EstadoSLAInfo,
        now: datetime,
    ) -> tuple[CaseState, list[SLAEvent]]:
        policy = self.policies.get(tipo)
        if policy is None:
            return state, []
        elapsed = now - info.pendiente_desde
        events: list[SLAEvent] = []
        current_info = info
        if elapsed >= policy.recordatorio:
            current_info = current_info.model_copy(
                update={
                    "estado": EstadoSLA.RECORDATORIO,
                    "observado_en": now,
                    "recordatorio_en": now,
                }
            )
            state = self._mark_no_response(state, tipo, current_info, now)
            event = self._emit(state, tipo, EstadoSLA.RECORDATORIO, now, "recordatorio")
            if event:
                events.append(event)
        if elapsed >= policy.escalamiento:
            current_info = current_info.model_copy(
                update={"estado": EstadoSLA.ESCALADO, "observado_en": now, "escalamiento_en": now}
            )
            state = self._update_sla_info(state, tipo, current_info, now)
            event = self._emit(state, tipo, EstadoSLA.ESCALADO, now, "escalamiento")
            if event:
                events.append(event)
        if policy.vencimiento is not None and elapsed >= policy.vencimiento:
            current_info = current_info.model_copy(
                update={"estado": EstadoSLA.VENCIDO, "observado_en": now, "vencimiento_en": now}
            )
            state = self._update_sla_info(state, tipo, current_info, now)
            expired_status = (
                EstadoCaso.VENCIDO_LISTA if tipo is TipoSLA.LISTA_CORTA else EstadoCaso.VENCIDO_MENSAJE
            )
            state = CaseState.model_validate(
                {
                    **state.model_dump(),
                    "estado": expired_status,
                    "razon_parada": RazónParada.SLA_VENCIDO,
                    "actualizado_en": now,
                }
            )
            event = self._emit(state, tipo, EstadoSLA.VENCIDO, now, "vencimiento")
            if event:
                events.append(event)
        return state, events

    def _mark_no_response(
        self, state: CaseState, tipo: TipoSLA, info: EstadoSLAInfo, now: datetime
    ) -> CaseState:
        changes = {"actualizado_en": now}
        if tipo is TipoSLA.LISTA_CORTA:
            changes.update(
                sla_lista=info,
                estado_aprobacion_lista=EstadoAprobacion.SIN_RESPUESTA,
            )
        else:
            changes.update(
                sla_mensaje=info,
                estado_aprobacion_mensaje=EstadoAprobacion.SIN_RESPUESTA,
            )
        return CaseState.model_validate({**state.model_dump(), **changes})

    def _update_sla_info(
        self, state: CaseState, tipo: TipoSLA, info: EstadoSLAInfo, now: datetime
    ) -> CaseState:
        field_name = "sla_lista" if tipo is TipoSLA.LISTA_CORTA else "sla_mensaje"
        return CaseState.model_validate(
            {**state.model_dump(), field_name: info, "actualizado_en": now}
        )

    def _emit(
        self,
        state: CaseState,
        tipo: TipoSLA,
        status: EstadoSLA,
        now: datetime,
        stage: str,
    ) -> SLAEvent | None:
        key = (state.correlation_id, tipo, status)
        if key in self._emitted:
            return None
        self._emitted.add(key)
        reason = f"sla_{stage}_{tipo.value}"
        self.decision_log.append(
            correlation_id=state.correlation_id,
            tiempo=now,
            componente="sla-watchdog",
            fuente=["sla-policy"],
            versiones={"sla": "1.0.0", "contrato": state.contrato_version},
            razon=reason,
            aprobador=None,
            estado=state.estado,
        )
        return SLAEvent(state.correlation_id, tipo, status, now, reason)


__all__ = [
    "DEFAULT_POLICIES",
    "SLAEvent",
    "SLAPolicy",
    "SLAReport",
    "SLAWatchdog",
]
