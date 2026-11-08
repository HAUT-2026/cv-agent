from datetime import datetime, timezone
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from cvagent.audit import DecisionLog
from cvagent.clock import ManualClock
from cvagent.contracts import CaseState, EstadoCaso
from cvagent.graph import build_graph, run_case, thread_config
from cvagent.operations import SQLiteEffectStore, SimulatedDeliveryGateway
from cvagent.ports import RoleAdapters, synthetic_adapters
from cvagent.registry import CaseRegistry


def initial_state() -> CaseState:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CaseState(
        correlation_id=str(uuid4()),
        vacante_id="vac-demo",
        vacante_version="v1",
        creado_en=now,
        actualizado_en=now,
    )


def approval(decision: str = "aprobar", **extra: str) -> dict[str, str]:
    return {"decision": decision, "aprobador": "recruiter-demo", "razon": "synthetic review", **extra}


def test_two_independent_approval_interrupts_gate_side_effects() -> None:
    state = initial_state()
    sender = SimulatedDeliveryGateway()
    doubles = synthetic_adapters()
    adapters = RoleAdapters(
        analista=doubles.analista,
        motor_reglas=doubles.motor_reglas,
        auditor=doubles.auditor,
        agendador=doubles.agendador,
        envio=sender,
    )
    graph = build_graph(adapters=adapters)
    config = thread_config(state.correlation_id)

    first = run_case(graph, state, config=config)
    assert first["estado"] is EstadoCaso.PENDIENTE_APROBACION_LISTA
    assert first["propuesta_agenda"] is None
    assert sender.calls == 0
    assert first["__interrupt__"][0].value["tipo"] == "lista_corta"

    second = graph.invoke(Command(resume=approval()), config)
    assert second["estado"] is EstadoCaso.PENDIENTE_APROBACION_MENSAJE
    assert second["__interrupt__"][0].value["tipo"] == "mensaje_exacto"
    assert sender.calls == 0

    final = graph.invoke(Command(resume=approval()), config)
    assert final["estado"] is EstadoCaso.CERRADO
    assert sender.calls == 1


def test_checkpoint_can_be_reused_by_a_rebuilt_graph_and_effect_is_idempotent(tmp_path) -> None:
    state = initial_state()
    checkpoint = InMemorySaver()
    effect_store = SQLiteEffectStore(str(tmp_path / "effects.sqlite"))
    sender = SimulatedDeliveryGateway(effect_store)
    doubles = synthetic_adapters()
    adapters = RoleAdapters(
        analista=doubles.analista,
        motor_reglas=doubles.motor_reglas,
        auditor=doubles.auditor,
        agendador=doubles.agendador,
        envio=sender,
    )
    config = thread_config(state.correlation_id)
    graph_before_restart = build_graph(adapters=adapters, checkpointer=checkpoint)
    run_case(graph_before_restart, state, config=config)

    # A new compiled graph represents a process restart; the checkpoint object
    # is the durable boundary in this fast test (Postgres is covered by the
    # optional integration test and README).
    graph_after_restart = build_graph(adapters=adapters, checkpointer=checkpoint)
    pending_message = graph_after_restart.invoke(Command(resume=approval()), config)
    assert pending_message["estado"] is EstadoCaso.PENDIENTE_APROBACION_MENSAJE

    final = graph_after_restart.invoke(Command(resume=approval()), config)
    assert final["estado"] is EstadoCaso.CERRADO
    assert sender.calls == 1
    assert effect_store.get(f"{state.correlation_id}:candidate-message:v1") is not None

    # Reconciliation returns the existing receipt instead of creating another
    # delivery, even when the adapter is called again after the restart.
    same_result = sender.enviar(
        final["propuesta_agenda"],
        idempotency_key=f"{state.correlation_id}:candidate-message:v1",
    )
    assert same_result.startswith("simulated-delivery:")
    assert sender.calls == 1
    effect_store.close()


def test_rejection_and_adjustment_remain_distinguishable() -> None:
    rejected = initial_state()
    rejected_graph = build_graph()
    rejected_config = thread_config(rejected.correlation_id)
    run_case(rejected_graph, rejected, config=rejected_config)
    rejected_result = rejected_graph.invoke(Command(resume=approval("rechazar")), rejected_config)
    assert rejected_result["estado"] is EstadoCaso.LISTA_RECHAZADA
    assert rejected_result["aprobacion_lista"]["decision"] is not None
    rejected_decision = rejected_result["aprobacion_lista"]["decision"]
    assert getattr(rejected_decision, "value", rejected_decision) == "rechazar"

    adjusted = initial_state()
    adjusted_graph = build_graph()
    adjusted_config = thread_config(adjusted.correlation_id)
    run_case(adjusted_graph, adjusted, config=adjusted_config)
    adjusted_result = adjusted_graph.invoke(
        Command(resume=approval("ajustar", candidatos_ref_ajustados=["cand_demo"])),
        adjusted_config,
    )
    assert adjusted_result["estado"] is EstadoCaso.PENDIENTE_APROBACION_MENSAJE
    adjusted_result = adjusted_graph.invoke(Command(resume=approval()), adjusted_config)
    assert adjusted_result["estado"] is EstadoCaso.CERRADO
    assert adjusted_result["propuesta_lista"]["version"] == 2
    adjusted_decision = adjusted_result["aprobacion_lista"]["decision"]
    assert getattr(adjusted_decision, "value", adjusted_decision) == "ajustar"
