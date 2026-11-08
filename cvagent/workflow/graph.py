"""Durable Role 1 LangGraph workflow with two human approval interrupts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..audit.log import DecisionLog
from .clock import Clock, SystemClock
from ..domain.contracts import (
    AprobacionHumana,
    CaseState,
    DecisionHumana,
    EfectoExterno,
    EstadoCaso,
    RazónParada,
    EstadoAprobacion,
    TipoAprobacion,
    EstadoSLA,
    EstadoSLAInfo,
    TipoSLA,
    VeredictoEstado,
)
from ..operations.core import OperationalControls, RetryExecutor
from .persistence import contract_serializer
from ..integration.ports import RoleAdapters, synthetic_adapters
from .registry import CaseRegistry


@dataclass
class GraphRuntime:
    adapters: RoleAdapters
    decision_log: DecisionLog
    controls: OperationalControls
    clock: Clock
    registry: CaseRegistry
    retry_executor: RetryExecutor[str]


def _state(value: Any) -> CaseState:
    return value if isinstance(value, CaseState) else CaseState.model_validate(value)


def _change(runtime: GraphRuntime, state: CaseState, **changes: Any) -> dict[str, Any]:
    next_state = CaseState.model_validate(
        {
            **state.model_dump(),
            **changes,
            "actualizado_en": runtime.clock.now(),
        }
    )
    runtime.registry.record(next_state)
    return next_state.model_dump()


def _log(
    runtime: GraphRuntime,
    state: CaseState,
    *,
    componente: str,
    razon: str,
    cobertura: float | None = None,
    veredicto: VeredictoEstado | None = None,
    aprobador: str | None = None,
) -> None:
    runtime.decision_log.append(
        correlation_id=state.correlation_id,
        tiempo=runtime.clock.now(),
        componente=componente,
        fuente=[componente],
        versiones={"vacante": state.vacante_version, "contrato": state.contrato_version},
        razon=razon,
        cobertura=cobertura,
        veredicto=veredicto,
        aprobador=aprobador,
        estado=state.estado,
    )


def _approval_payload(state: CaseState, kind: TipoAprobacion) -> dict[str, Any]:
    if kind is TipoAprobacion.LISTA_CORTA:
        return {
            "tipo": kind.value,
            "correlation_id": state.correlation_id,
            "estado": state.estado.value,
            "propuesta": state.propuesta_lista.model_dump(mode="json")
            if state.propuesta_lista
            else None,
            "allowed_decisions": [decision.value for decision in DecisionHumana],
        }
    return {
        "tipo": kind.value,
        "correlation_id": state.correlation_id,
        "estado": state.estado.value,
        "propuesta": state.propuesta_agenda.model_dump(mode="json")
        if state.propuesta_agenda
        else None,
        "allowed_decisions": [decision.value for decision in DecisionHumana],
    }


def _parse_approval(response: Any, kind: TipoAprobacion, state: CaseState, runtime: GraphRuntime):
    if not isinstance(response, dict):
        raise ValueError("human approval must be a JSON object")
    data = dict(response)
    try:
        data["decision"] = DecisionHumana(data["decision"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("human approval decision is invalid") from exc
    data["tipo"] = kind
    data.setdefault("timestamp", runtime.clock.now())
    approval = AprobacionHumana.model_validate(data)
    _log(
        runtime,
        state,
        componente="human-approval",
        razon=f"{kind.value}:{approval.decision.value}",
        aprobador=approval.aprobador,
    )
    return approval


def _receive(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    if runtime.controls.is_blocked(vacante_id=state.vacante_id, agente="workflow"):
        paused = _change(
            runtime,
            state,
            estado=EstadoCaso.PAUSADO_KILL_SWITCH,
            razon_parada=RazónParada.KILL_SWITCH_ACTIVO,
        )
        _log(runtime, _state(paused), componente="workflow", razon="kill_switch_at_entry")
        return paused
    _log(runtime, state, componente="workflow", razon="case_received")
    return _change(runtime, state, estado=EstadoCaso.EVALUANDO, razon_parada=None)


def _route_after_receive(state_value: Any) -> str:
    return "stop" if _state(state_value).estado is EstadoCaso.PAUSADO_KILL_SWITCH else "analyze"


def _analyze(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    ficha = runtime.adapters.analista.crear_ficha(state, now=runtime.clock.now())
    _log(runtime, state, componente="rol-2-adapter", razon="ficha_created")
    return _change(runtime, state, ficha=ficha, estado=EstadoCaso.EVALUANDO)


def _evaluate(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    if state.ficha is None:
        raise ValueError("cannot evaluate a case without a ficha")
    verdict = runtime.adapters.motor_reglas.evaluar(state.ficha, now=runtime.clock.now())
    _log(
        runtime,
        state,
        componente="rol-3-adapter",
        razon="verdict_created",
        cobertura=verdict.cobertura,
        veredicto=verdict.estado,
    )
    next_status = (
        EstadoCaso.EVALUANDO
        if verdict.estado is VeredictoEstado.APROBADO
        else EstadoCaso.PENDIENTE_REVISION
    )
    reason = None if next_status is EstadoCaso.EVALUANDO else RazónParada.REQUIERE_REVISION_HUMANA
    return _change(runtime, state, veredicto=verdict, estado=next_status, razon_parada=reason)


def _route_after_evaluation(state_value: Any) -> str:
    state = _state(state_value)
    return "audit" if state.veredicto and state.veredicto.estado is VeredictoEstado.APROBADO else "stop"


def _audit(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    if state.ficha is None or state.veredicto is None:
        raise ValueError("audit requires ficha and veredicto")
    verdict = runtime.adapters.auditor.auditar(state.ficha, state.veredicto)
    if verdict.estado is not VeredictoEstado.APROBADO:
        _log(runtime, state, componente="rol-3-adapter", razon="audit_blocked", veredicto=verdict.estado)
        return _change(
            runtime,
            state,
            veredicto=verdict,
            estado=EstadoCaso.PENDIENTE_REVISION,
            razon_parada=RazónParada.REQUIERE_REVISION_HUMANA,
        )
    _log(runtime, state, componente="rol-3-adapter", razon="audit_passed", veredicto=verdict.estado)
    return _change(runtime, state, veredicto=verdict)


def _route_after_audit(state_value: Any) -> str:
    state = _state(state_value)
    return "prepare_shortlist" if state.veredicto and state.veredicto.estado is VeredictoEstado.APROBADO else "stop"


def _prepare_shortlist(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    if state.ficha is None or state.veredicto is None:
        raise ValueError("shortlist requires ficha and veredicto")
    proposal = runtime.adapters.motor_reglas.crear_propuesta_lista(
        state.ficha, state.veredicto, now=runtime.clock.now()
    )
    pending = _change(
        runtime,
        state,
        propuesta_lista=proposal,
        estado_aprobacion_lista=EstadoAprobacion.PENDIENTE,
        sla_lista=EstadoSLAInfo(
            tipo=TipoSLA.LISTA_CORTA,
            estado=EstadoSLA.PENDIENTE,
            pendiente_desde=runtime.clock.now(),
            observado_en=runtime.clock.now(),
        ),
        estado=EstadoCaso.PENDIENTE_APROBACION_LISTA,
        razon_parada=RazónParada.APROBACION_LISTA_PENDIENTE,
    )
    _log(runtime, _state(pending), componente="workflow", razon="shortlist_ready")
    return pending


def _approve_shortlist(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    response = interrupt(_approval_payload(state, TipoAprobacion.LISTA_CORTA))
    approval = _parse_approval(response, TipoAprobacion.LISTA_CORTA, state, runtime)
    proposal = state.propuesta_lista
    if proposal is None:
        raise ValueError("shortlist approval requires a proposal")
    if approval.decision is DecisionHumana.APROBAR:
        return _change(
            runtime,
            state,
            aprobacion_lista=approval,
            estado_aprobacion_lista=EstadoAprobacion.APROBADA,
            estado=EstadoCaso.LISTA_APROBADA,
            razon_parada=None,
        )
    if approval.decision is DecisionHumana.AJUSTAR:
        adjusted = type(proposal).model_validate(
            {
                **proposal.model_dump(),
                "version": proposal.version + 1,
                "candidatos_ref": approval.candidatos_ref_ajustados,
                "razones": {
                    candidate: proposal.razones.get(candidate, "Ajuste humano registrado")
                    for candidate in approval.candidatos_ref_ajustados or []
                },
                "creada_en": runtime.clock.now(),
            }
        )
        return _change(
            runtime,
            state,
            propuesta_lista=adjusted,
            aprobacion_lista=approval,
            estado_aprobacion_lista=EstadoAprobacion.AJUSTADA,
            estado=EstadoCaso.LISTA_AJUSTADA,
            razon_parada=None,
        )
    return _change(
        runtime,
        state,
        aprobacion_lista=approval,
        estado_aprobacion_lista=EstadoAprobacion.RECHAZADA,
        estado=EstadoCaso.LISTA_RECHAZADA,
        razon_parada=RazónParada.LISTA_RECHAZADA,
    )


def _route_after_shortlist(state_value: Any) -> str:
    state = _state(state_value)
    return "schedule" if state.estado in {EstadoCaso.LISTA_APROBADA, EstadoCaso.LISTA_AJUSTADA} else "stop"


def _schedule(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    if state.propuesta_lista is None:
        raise ValueError("scheduling requires an approved shortlist")
    if runtime.controls.is_blocked(vacante_id=state.vacante_id, agente="agendador"):
        paused = _change(
            runtime,
            state,
            estado=EstadoCaso.PAUSADO_KILL_SWITCH,
            razon_parada=RazónParada.KILL_SWITCH_ACTIVO,
        )
        _log(runtime, _state(paused), componente="workflow", razon="scheduling_paused")
        return paused
    agenda = runtime.adapters.agendador.proponer(
        state, state.propuesta_lista, now=runtime.clock.now()
    )
    pending = _change(
        runtime,
        state,
        propuesta_agenda=agenda,
        estado_aprobacion_mensaje=EstadoAprobacion.PENDIENTE,
        sla_mensaje=EstadoSLAInfo(
            tipo=TipoSLA.MENSAJE,
            estado=EstadoSLA.PENDIENTE,
            pendiente_desde=runtime.clock.now(),
            observado_en=runtime.clock.now(),
        ),
        estado=EstadoCaso.PENDIENTE_APROBACION_MENSAJE,
        razon_parada=RazónParada.APROBACION_MENSAJE_PENDIENTE,
    )
    _log(runtime, _state(pending), componente="rol-4-adapter", razon="message_ready")
    return pending


def _approve_message(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    response = interrupt(_approval_payload(state, TipoAprobacion.MENSAJE_EXACTO))
    approval = _parse_approval(response, TipoAprobacion.MENSAJE_EXACTO, state, runtime)
    agenda = state.propuesta_agenda
    if agenda is None:
        raise ValueError("message approval requires an agenda proposal")
    if approval.decision is DecisionHumana.APROBAR:
        return _change(
            runtime,
            state,
            aprobacion_mensaje=approval,
            estado_aprobacion_mensaje=EstadoAprobacion.APROBADA,
            estado=EstadoCaso.MENSAJE_APROBADO,
            razon_parada=None,
        )
    if approval.decision is DecisionHumana.AJUSTAR:
        adjusted = type(agenda).model_validate(
            {
                **agenda.model_dump(),
                "texto_exacto": approval.texto_exacto_ajustado,
                "creada_en": runtime.clock.now(),
            }
        )
        return _change(
            runtime,
            state,
            propuesta_agenda=adjusted,
            aprobacion_mensaje=approval,
            estado_aprobacion_mensaje=EstadoAprobacion.AJUSTADA,
            estado=EstadoCaso.MENSAJE_AJUSTADO,
            razon_parada=None,
        )
    return _change(
        runtime,
        state,
        aprobacion_mensaje=approval,
        estado_aprobacion_mensaje=EstadoAprobacion.RECHAZADA,
        estado=EstadoCaso.MENSAJE_RECHAZADO,
        razon_parada=RazónParada.MENSAJE_RECHAZADO,
    )


def _route_after_message(state_value: Any) -> str:
    state = _state(state_value)
    return "external_guard" if state.estado in {EstadoCaso.MENSAJE_APROBADO, EstadoCaso.MENSAJE_AJUSTADO} else "stop"


def _external_guard(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    if runtime.controls.is_blocked(vacante_id=state.vacante_id, agente="envio"):
        paused = _change(
            runtime,
            state,
            estado=EstadoCaso.PAUSADO_KILL_SWITCH,
            razon_parada=RazónParada.KILL_SWITCH_ACTIVO,
        )
        _log(runtime, _state(paused), componente="workflow", razon="external_action_paused")
        return paused
    return _change(runtime, state, estado=EstadoCaso.ENVIANDO, razon_parada=None)


def _route_after_external_guard(state_value: Any) -> str:
    return "operational_resume" if _state(state_value).estado is EstadoCaso.PAUSADO_KILL_SWITCH else "send"


def _operational_resume(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    response = interrupt(
        {
            "tipo": "kill_switch",
            "correlation_id": state.correlation_id,
            "razon": RazónParada.KILL_SWITCH_ACTIVO.value,
            "instruccion": "reanudar solo después del procedimiento operativo explícito",
        }
    )
    if not isinstance(response, dict) or response.get("decision") != "reanudar":
        raise ValueError("kill switch resume requires decision=reanudar")
    if runtime.controls.is_blocked(vacante_id=state.vacante_id, agente="envio"):
        return state.model_dump()
    return _change(runtime, state, estado=EstadoCaso.ENVIANDO, razon_parada=None)


def _route_after_operational_resume(state_value: Any) -> str:
    return "send" if _state(state_value).estado is EstadoCaso.ENVIANDO else "stop"


def _send(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    if state.propuesta_agenda is None:
        raise ValueError("delivery requires an agenda proposal")
    runtime.controls.ensure_external_allowed(
        correlation_id=state.correlation_id,
        vacante_id=state.vacante_id,
        agente="envio",
        herramienta="simulated_delivery",
    )
    key = f"{state.correlation_id}:candidate-message:v1"
    result_ref, attempts = runtime.retry_executor.run(
        idempotency_key=key,
        operation=lambda idempotency_key: runtime.adapters.envio.enviar(
            state.propuesta_agenda, idempotency_key=idempotency_key
        ),
        reconcile=lambda idempotency_key: getattr(runtime.adapters.envio, "store", None)
        and runtime.adapters.envio.store.get(idempotency_key),
    )
    effect = EfectoExterno(
        idempotency_key=key,
        operacion="simulated_delivery",
        estado="completado",
        resultado_ref=result_ref,
        intentos=max(1, attempts),
        ejecutado_en=runtime.clock.now(),
    )
    effects = [*state.efectos_externos, effect]
    _log(runtime, state, componente="simulated-delivery", razon="external_effect_completed")
    return _change(runtime, state, efectos_externos=effects, estado=EstadoCaso.CERRADO)


def _stop(runtime: GraphRuntime, state_value: Any) -> dict[str, Any]:
    state = _state(state_value)
    _log(runtime, state, componente="workflow", razon="flow_stopped", aprobador=(
        state.aprobacion_lista.aprobador
        if state.aprobacion_lista and state.estado is EstadoCaso.LISTA_RECHAZADA
        else state.aprobacion_mensaje.aprobador
        if state.aprobacion_mensaje and state.estado is EstadoCaso.MENSAJE_RECHAZADO
        else None
    ))
    runtime.registry.record(state)
    return state.model_dump()


def build_graph(
    *,
    adapters: RoleAdapters | None = None,
    checkpointer: object | None = None,
    decision_log: DecisionLog | None = None,
    controls: OperationalControls | None = None,
    clock: Clock | None = None,
    registry: CaseRegistry | None = None,
    retry_executor: RetryExecutor[str] | None = None,
):
    """Build the graph; the caller owns the checkpointer context lifetime."""

    runtime = GraphRuntime(
        adapters=adapters or synthetic_adapters(),
        decision_log=decision_log or DecisionLog(),
        controls=controls or OperationalControls(),
        clock=clock or SystemClock(),
        registry=registry or CaseRegistry(),
        retry_executor=retry_executor or RetryExecutor(),
    )
    builder = StateGraph(CaseState)
    builder.add_node("receive", lambda state: _receive(runtime, state))
    builder.add_node("analyze", lambda state: _analyze(runtime, state))
    builder.add_node("evaluate", lambda state: _evaluate(runtime, state))
    builder.add_node("audit", lambda state: _audit(runtime, state))
    builder.add_node("prepare_shortlist", lambda state: _prepare_shortlist(runtime, state))
    builder.add_node("approve_shortlist", lambda state: _approve_shortlist(runtime, state))
    builder.add_node("schedule", lambda state: _schedule(runtime, state))
    builder.add_node("approve_message", lambda state: _approve_message(runtime, state))
    builder.add_node("external_guard", lambda state: _external_guard(runtime, state))
    builder.add_node("operational_resume", lambda state: _operational_resume(runtime, state))
    builder.add_node("send", lambda state: _send(runtime, state))
    builder.add_node("stop", lambda state: _stop(runtime, state))

    builder.add_edge(START, "receive")
    builder.add_conditional_edges(
        "receive", _route_after_receive, {"analyze": "analyze", "stop": "stop"}
    )
    builder.add_edge("analyze", "evaluate")
    builder.add_conditional_edges("evaluate", _route_after_evaluation, {"audit": "audit", "stop": "stop"})
    builder.add_conditional_edges("audit", _route_after_audit, {"prepare_shortlist": "prepare_shortlist", "stop": "stop"})
    builder.add_edge("prepare_shortlist", "approve_shortlist")
    builder.add_conditional_edges(
        "approve_shortlist",
        _route_after_shortlist,
        {"schedule": "schedule", "stop": "stop"},
    )
    builder.add_conditional_edges(
        "schedule",
        lambda state: "approve_message" if _state(state).estado is EstadoCaso.PENDIENTE_APROBACION_MENSAJE else "stop",
        {"approve_message": "approve_message", "stop": "stop"},
    )
    builder.add_conditional_edges(
        "approve_message",
        _route_after_message,
        {"external_guard": "external_guard", "stop": "stop"},
    )
    builder.add_conditional_edges(
        "external_guard",
        _route_after_external_guard,
        {"operational_resume": "operational_resume", "send": "send"},
    )
    builder.add_conditional_edges(
        "operational_resume",
        _route_after_operational_resume,
        {"send": "send", "stop": "stop"},
    )
    builder.add_edge("send", END)
    builder.add_edge("stop", END)
    if checkpointer is None:
        checkpointer = InMemorySaver(serde=contract_serializer())
    return builder.compile(checkpointer=checkpointer)


def thread_config(correlation_id: str) -> dict[str, dict[str, str]]:
    """Return the official LangGraph config shape for durable resumption."""

    CaseState(
        correlation_id=correlation_id,
        vacante_id="validation-only",
        vacante_version="validation-only",
        creado_en=SystemClock().now(),
        actualizado_en=SystemClock().now(),
    )
    return {"configurable": {"thread_id": correlation_id}}


def run_case(graph, state: CaseState, *, config: dict | None = None):
    """Invoke with Python objects so strict Pydantic contracts remain strict."""

    return graph.invoke(state.model_dump(), config or thread_config(state.correlation_id))


__all__ = ["build_graph", "run_case", "thread_config"]
