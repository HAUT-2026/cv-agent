from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

from cvagent.audit import DecisionLog
from cvagent.clock import ManualClock
from cvagent.contracts import CaseState, EstadoAprobacion, EstadoCaso, EstadoSLA, TipoSLA
from cvagent.graph import build_graph, run_case, thread_config
from cvagent.registry import CaseRegistry
from cvagent.sla import SLAWatchdog, SLAWatchdogService, SLAPolicy


def _state() -> CaseState:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CaseState(
        correlation_id=str(uuid4()),
        vacante_id="vac-demo",
        vacante_version="v1",
        creado_en=now,
        actualizado_en=now,
    )


def _pending_list_case() -> tuple[CaseState, DecisionLog, SLAWatchdog]:
    state = _state()
    log = DecisionLog()
    graph = build_graph(decision_log=log)
    result = run_case(graph, state, config=thread_config(state.correlation_id))
    pending = CaseState.model_validate({key: value for key, value in result.items() if key != "__interrupt__"})
    return pending, log, SLAWatchdog(decision_log=log)


def test_decision_log_is_append_only_and_hash_chain_is_verifiable() -> None:
    state = _state()
    log = DecisionLog()
    log.append(
        correlation_id=state.correlation_id,
        tiempo=state.creado_en,
        componente="test",
        fuente=["synthetic"],
        versiones={"vacante": "v1"},
        razon="first",
        estado=EstadoCaso.RECIBIDO,
    )
    exposed = log.entries
    exposed[0].fuente.append("mutated-copy")
    assert log.verify_integrity() is True
    assert "mutated-copy" not in log.entries[0].fuente
    assert log.entries[0].hash_previo == "GENESIS"


def test_watchdog_emits_shortlist_reminder_escalation_and_expiry() -> None:
    pending, log, watchdog = _pending_list_case()
    now = pending.actualizado_en
    first = watchdog.inspect([pending], now=now + timedelta(hours=24))
    assert [event.estado for event in first.events] == [EstadoSLA.RECORDATORIO]
    assert first.states[0].estado_aprobacion_lista.value == "sin_respuesta"

    second = watchdog.inspect([first.states[0]], now=now + timedelta(hours=48))
    assert [event.estado for event in second.events] == [EstadoSLA.ESCALADO]
    third = watchdog.inspect([second.states[0]], now=now + timedelta(hours=72))
    assert [event.estado for event in third.events] == [EstadoSLA.VENCIDO]
    assert third.states[0].estado is EstadoCaso.VENCIDO_LISTA
    assert third.states[0].razon_parada.value == "sla_vencido"
    sla_entries = [entry for entry in log.entries if entry.componente == "sla-watchdog"]
    assert len(sla_entries) == 3
    assert all(entry.componente == "sla-watchdog" for entry in sla_entries)
    assert log.verify_integrity() is True


def test_watchdog_message_policy_has_four_and_eight_hour_stages_without_approval() -> None:
    state, log, watchdog = _pending_list_case()
    # Move the synthetic case to a message-pending snapshot without invoking
    # the sender; this is the operational state the Role 4 adapter exposes.
    message_state = CaseState.model_validate(
        {
            **state.model_dump(),
            "estado": EstadoCaso.PENDIENTE_APROBACION_MENSAJE,
            "sla_lista": None,
            "sla_mensaje": {
                "tipo": TipoSLA.MENSAJE,
                "estado": EstadoSLA.PENDIENTE,
                "pendiente_desde": state.actualizado_en,
                "observado_en": state.actualizado_en,
            },
        }
    )
    first = watchdog.inspect([message_state], now=state.actualizado_en + timedelta(hours=4))
    assert [event.estado for event in first.events] == [EstadoSLA.RECORDATORIO]
    assert first.states[0].estado is EstadoCaso.PENDIENTE_APROBACION_MENSAJE
    second = watchdog.inspect([first.states[0]], now=state.actualizado_en + timedelta(hours=8))
    assert [event.estado for event in second.events] == [EstadoSLA.ESCALADO]
    assert second.states[0].estado_aprobacion_mensaje.value == "sin_respuesta"
    assert all(entry.aprobador is None for entry in log.entries)


def test_manual_clock_proves_deadlines_in_seconds() -> None:
    initial = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = ManualClock(initial)
    state = _state()
    state = state.model_copy(update={"creado_en": initial, "actualizado_en": initial})
    log = DecisionLog()
    graph = build_graph(clock=clock, decision_log=log)
    result = run_case(graph, state, config=thread_config(state.correlation_id))
    pending = CaseState.model_validate({key: value for key, value in result.items() if key != "__interrupt__"})
    watchdog = SLAWatchdog(decision_log=log)
    watchdog.register_policy(
        SLAPolicy(
            tipo=TipoSLA.LISTA_CORTA,
            recordatorio=timedelta(seconds=2),
            escalamiento=timedelta(seconds=4),
            vencimiento=timedelta(seconds=6),
        )
    )
    clock.advance(seconds=2)
    report = watchdog.inspect([pending], now=clock.now())
    assert [event.estado for event in report.events] == [EstadoSLA.RECORDATORIO]


def test_sla_watchdog_service_inspects_registry_periodically() -> None:
    pending, log, watchdog = _pending_list_case()
    registry = CaseRegistry()
    registry.record(pending)
    reports = []
    completed = Event()
    current = [pending.actualizado_en + timedelta(hours=24)]

    def on_report(report) -> None:
        reports.append(report)
        if len(reports) >= 2:
            completed.set()

    service = SLAWatchdogService(
        watchdog=watchdog,
        registry=registry,
        interval=timedelta(milliseconds=1),
        clock=lambda: current[0],
        on_report=on_report,
    )
    service.start()
    assert completed.wait(timeout=2)
    service.stop()

    assert len(reports) >= 2
    assert registry.get(pending.correlation_id).estado_aprobacion_lista is EstadoAprobacion.SIN_RESPUESTA
    assert [event.estado for event in reports[0].events] == [EstadoSLA.RECORDATORIO]
    assert log.verify_integrity() is True
