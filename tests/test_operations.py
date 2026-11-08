from datetime import datetime, timezone

import pytest
from langgraph.types import Command

from cvagent.audit import DecisionLog
from cvagent.contracts import CaseState, EstadoCaso
from cvagent.graph import build_graph, run_case, thread_config
from cvagent.operations import (
    OperationalControls,
    RetryExecutor,
    SimulatedDeliveryGateway,
    ToolNotAllowedError,
    TransientOperationError,
)


def test_allowlist_rejects_and_logs_prohibited_tool() -> None:
    log = DecisionLog()
    controls = OperationalControls(decision_log=log)
    controls.set_allowlist("rol-2", {"read_sanitized_cv"})
    correlation_id = "00000000-0000-4000-8000-000000000001"

    controls.call_tool(
        correlation_id=correlation_id,
        agente="rol-2",
        herramienta="read_sanitized_cv",
        vacante_id="vac-demo",
    )
    with pytest.raises(ToolNotAllowedError):
        controls.call_tool(
            correlation_id=correlation_id,
            agente="rol-2",
            herramienta="send_email",
            vacante_id="vac-demo",
        )
    assert controls.calls[-1].permitida is False
    assert controls.calls[-1].razon == "tool_not_allowed"
    assert log.entries[-1].razon == "herramienta_no_permitida"


def test_retry_is_finite_and_reconciles_before_duplicate_effect() -> None:
    sleeps: list[float] = []
    executor = RetryExecutor[str](
        max_attempts=3,
        base_delay_seconds=0.5,
        sleep=sleeps.append,
    )
    attempts = 0

    def operation(_: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TransientOperationError("try again")
        return "receipt-1"

    result, used_attempts = executor.run(
        idempotency_key="op-1",
        operation=operation,
        reconcile=lambda _: None,
    )
    assert result == "receipt-1"
    assert used_attempts == 2
    assert sleeps == [0.5]

    reconciled, no_new_attempts = executor.run(
        idempotency_key="op-1",
        operation=lambda _: "must-not-run",
        reconcile=lambda _: "receipt-1",
    )
    assert reconciled == "receipt-1"
    assert no_new_attempts == 0


def test_kill_switch_pauses_and_explicit_resume_allows_message_delivery() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = CaseState(
        correlation_id="00000000-0000-4000-8000-000000000002",
        vacante_id="vac-demo",
        vacante_version="v1",
        creado_en=now,
        actualizado_en=now,
    )
    controls = OperationalControls()
    controls.activate_kill_switch(alcance="agente", valor="envio", causa="synthetic incident")
    sender = SimulatedDeliveryGateway()
    from cvagent.ports import RoleAdapters, synthetic_adapters

    doubles = synthetic_adapters()
    adapters = RoleAdapters(
        analista=doubles.analista,
        motor_reglas=doubles.motor_reglas,
        auditor=doubles.auditor,
        agendador=doubles.agendador,
        envio=sender,
    )
    graph = build_graph(adapters=adapters, controls=controls)
    config = thread_config(state.correlation_id)
    run_case(graph, state, config=config)
    graph.invoke(Command(resume={"decision": "aprobar", "aprobador": "r", "razon": "ok"}), config)
    paused = graph.invoke(
        Command(resume={"decision": "aprobar", "aprobador": "r", "razon": "ok"}), config
    )
    assert paused["estado"] is EstadoCaso.PAUSADO_KILL_SWITCH
    assert paused["__interrupt__"][0].value["tipo"] == "kill_switch"
    assert sender.calls == 0

    controls.resume_kill_switch(alcance="agente", valor="envio", aprobador="ops-lead")
    final = graph.invoke(Command(resume={"decision": "reanudar"}), config)
    assert final["estado"] is EstadoCaso.CERRADO
    assert sender.calls == 1


def test_vacancy_kill_switch_stops_case_at_entry() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = CaseState(
        correlation_id="00000000-0000-4000-8000-000000000003",
        vacante_id="vac-paused",
        vacante_version="v1",
        creado_en=now,
        actualizado_en=now,
    )
    controls = OperationalControls()
    controls.activate_kill_switch(alcance="vacante", valor="vac-paused", causa="synthetic incident")
    result = run_case(build_graph(controls=controls), state, config=thread_config(state.correlation_id))
    assert result["estado"] is EstadoCaso.PAUSADO_KILL_SWITCH
    assert result["propuesta_agenda"] is None
