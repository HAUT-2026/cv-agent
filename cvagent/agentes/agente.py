"""
Motor de agente: el ciclo razonar → actuar → observar.

    1. El LLM recibe la tarea y las herramientas de SU allowlist.
    2. Decide: llamar una herramienta, o entregar el resultado.
    3. Si llama una herramienta:
         - ¿está en su allowlist?  NO → se rechaza y se registra (no se ejecuta).
         - SÍ → se ejecuta y el resultado vuelve al LLM, que decide de nuevo.
    4. Entrega el resultado llamando `entregar_resultado`, cuyos parámetros son el
       esquema pydantic de salida. Si no valida, se le devuelve el error y corrige.
    5. Límite de pasos: si no entrega a tiempo, falla de forma explícita (fail-closed).

Toda llamada queda en la `traza`: es la materia prima del decision_log y la
evidencia de que la allowlist se cumple.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Generic, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .herramientas import REGISTRO, ContextoCaso
from .llm import ClienteLLM

T = TypeVar("T", bound=BaseModel)
HERRAMIENTA_FINAL = "entregar_resultado"


class AgenteSinResultado(RuntimeError):
    """El agente agotó sus pasos sin entregar un resultado válido."""


@dataclass
class EventoTraza:
    paso: int
    tipo: str            # llamada | rechazo | resultado_invalido | texto_sin_herramienta | entrega
    herramienta: Optional[str] = None
    argumentos: Any = None
    resultado: Any = None
    momento: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ResultadoAgente(Generic[T]):
    salida: T
    traza: list[EventoTraza]
    pasos: int


def esquema_plano(modelo: Type[BaseModel]) -> dict:
    """JSON Schema sin $ref/$defs: varios modelos locales no resuelven referencias."""
    raiz = modelo.model_json_schema()
    defs = raiz.pop("$defs", {})

    def resolver(nodo):
        if isinstance(nodo, dict):
            if "$ref" in nodo:
                return resolver(dict(defs[nodo["$ref"].split("/")[-1]]))
            return {k: resolver(v) for k, v in nodo.items() if k != "title"}
        if isinstance(nodo, list):
            return [resolver(x) for x in nodo]
        return nodo

    return resolver(raiz)


def _argumentos(llamada: dict) -> dict:
    """Ollama a veces manda los argumentos como dict y OpenAI como string JSON."""
    crudo = llamada.get("function", {}).get("arguments", {})
    if isinstance(crudo, dict):
        return crudo
    try:
        return json.loads(crudo or "{}")
    except json.JSONDecodeError as e:
        raise ValueError(f"argumentos no son JSON válido: {e}") from e


def ejecutar_agente(
    *,
    nombre: str,
    cliente: ClienteLLM,
    instrucciones: str,
    tarea: str,
    allowlist: list[str],
    contexto: ContextoCaso,
    esquema_salida: Type[T],
    max_pasos: int = 10,
    al_evento: Optional[Callable[[str, Any], None]] = None,
    validar_entrega: Optional[Callable[[Any, list], list[str]]] = None,
    max_rechazos_entrega: int = 2,
    registro: Optional[dict] = None,
    mensaje_rechazo: str = ("Entrega rechazada: decidiste sin revisar la evidencia disponible. "
                            "Lee los detalles, juzga con esa evidencia y vuelve a entregar."),
) -> ResultadoAgente[T]:
    """`al_evento(tipo, dato)` permite mostrar el progreso en vivo:
    tipo = "pensando" (dato = n.º de paso) o "evento" (dato = EventoTraza).

    `validar_entrega(salida, traza)` es una baranda propia de cada agente: revisa una entrega
    que ya cumple el esquema y devuelve los problemas (lista vacía = aceptada). Si hay problemas,
    la entrega se rechaza y el agente sigue trabajando. Se rechaza a lo sumo `max_rechazos_entrega`
    veces: después se acepta y el problema queda para el auditor (evita gastar todos los pasos).

    `registro` permite que cada agente tenga su propio juego de herramientas (el agendador no
    comparte registro con el analista: ni siquiera puede nombrar una herramienta que lea el CV)."""
    REG = registro if registro is not None else REGISTRO
    desconocidas = [h for h in allowlist if h not in REG]
    if desconocidas:
        raise ValueError(f"[{nombre}] allowlist con herramientas inexistentes: {desconocidas}")

    herramientas = [REG[h].definicion() for h in allowlist]
    herramientas.append({"type": "function", "function": {
        "name": HERRAMIENTA_FINAL,
        "description": "Entrega el resultado final. Llámala UNA vez, cuando tengas la evidencia.",
        "parameters": esquema_plano(esquema_salida)}})

    mensajes: list[dict] = [{"role": "system", "content": instrucciones},
                            {"role": "user", "content": tarea}]
    traza: list[EventoTraza] = []

    class _Traza(list):
        def append(self, ev):
            super().append(ev)
            if al_evento:
                al_evento("evento", ev)
    traza = _Traza()
    ya_hechas: dict[str, int] = {}   # firma de la llamada → paso en que se hizo
    rechazos_entrega = 0

    for paso in range(1, max_pasos + 1):
        if al_evento:
            al_evento("pensando", paso)
        msg = cliente.chat(mensajes, herramientas)
        llamadas = msg.get("tool_calls") or []

        if not llamadas:
            tipo = "corte_por_longitud" if msg.get("_corte_por_longitud") else "texto_sin_herramienta"
            traza.append(EventoTraza(paso, tipo, resultado=(msg.get("content") or "")[:300]))
            mensajes.append({"role": "assistant", "content": msg.get("content") or ""})
            mensajes.append({"role": "user", "content":
                             f"No respondas con texto. Usa las herramientas y entrega con `{HERRAMIENTA_FINAL}`."})
            continue

        mensajes.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": llamadas})

        for i, ll in enumerate(llamadas):
            nombre_h = ll.get("function", {}).get("name", "")
            id_ll = ll.get("id") or f"llamada_{paso}_{i}"
            try:
                args = _argumentos(ll)
            except ValueError as e:
                traza.append(EventoTraza(paso, "resultado_invalido", nombre_h, None, str(e)))
                mensajes.append({"role": "tool", "tool_call_id": id_ll, "content": json.dumps({"error": str(e)})})
                continue

            if nombre_h == HERRAMIENTA_FINAL and len(llamadas) > 1:
                # Entregar en el mismo turno en que se busca = decidir sin ver los resultados.
                traza.append(EventoTraza(paso, "entrega_prematura", nombre_h, args,
                                         "entregó junto con otras llamadas, sin ver sus resultados"))
                mensajes.append({"role": "tool", "tool_call_id": id_ll, "content": json.dumps(
                    {"error": "No entregues en el mismo turno en que usas herramientas: primero revisa "
                              "sus resultados y entrega en un turno aparte."}, ensure_ascii=False)})
                continue

            if nombre_h == HERRAMIENTA_FINAL:
                try:
                    salida = esquema_salida.model_validate(args)
                except ValidationError as e:
                    errores = [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()][:8]
                    traza.append(EventoTraza(paso, "resultado_invalido", nombre_h, args, errores))
                    mensajes.append({"role": "tool", "tool_call_id": id_ll, "content": json.dumps(
                        {"error": "El resultado no cumple el esquema. Corrige y vuelve a entregar.",
                         "detalles": errores}, ensure_ascii=False)})
                    continue
                if validar_entrega and rechazos_entrega < max_rechazos_entrega:
                    problemas = validar_entrega(salida, list(traza))
                    if problemas:
                        rechazos_entrega += 1
                        traza.append(EventoTraza(paso, "entrega_incompleta", nombre_h, args, problemas))
                        mensajes.append({"role": "tool", "tool_call_id": id_ll, "content": json.dumps(
                            {"error": mensaje_rechazo, "detalles": problemas}, ensure_ascii=False)})
                        continue
                traza.append(EventoTraza(paso, "entrega", nombre_h, args))
                return ResultadoAgente(salida, list(traza), paso)

            if nombre_h not in allowlist:
                # El corazón de la separación de agentes: no se ejecuta, se registra.
                traza.append(EventoTraza(paso, "rechazo", nombre_h, args, "herramienta fuera de la allowlist"))
                mensajes.append({"role": "tool", "tool_call_id": id_ll, "content": json.dumps(
                    {"error": f"La herramienta '{nombre_h}' no está permitida para el agente {nombre}."},
                    ensure_ascii=False)})
                continue

            firma = f"{nombre_h}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
            if firma in ya_hechas:
                # Freno de bucles: no se re-ejecuta; se le recuerda que ya lo hizo.
                traza.append(EventoTraza(paso, "repetida", nombre_h, args, f"igual a la del paso {ya_hechas[firma]}"))
                mensajes.append({"role": "tool", "tool_call_id": id_ll, "content": json.dumps(
                    {"aviso": f"Ya hiciste exactamente esta llamada en el paso {ya_hechas[firma]} y el "
                              "resultado no cambia. Haz algo distinto o entrega con entregar_resultado."},
                    ensure_ascii=False)})
                continue
            ya_hechas[firma] = paso
            resultado = REG[nombre_h].funcion(args, contexto)
            traza.append(EventoTraza(paso, "llamada", nombre_h, args, resultado))
            mensajes.append({"role": "tool", "tool_call_id": id_ll,
                             "content": json.dumps(resultado, ensure_ascii=False)})

    raise AgenteSinResultado(f"[{nombre}] no entregó un resultado válido en {max_pasos} pasos")
