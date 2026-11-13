"""Agente agendador (Rol 3) · borrador de invitación desde plantilla, SIN acceso al CV.

SDD: «Redactar borrador usando plantilla, cargo, nombre de pila y franjas. Sin acceso al CV ni a
herramientas de escritura». El workflow consulta free/busy; ningún mensaje sale sin aprobación
del texto exacto (R10, ADR-004). Contrato del Rol 1: `AgendadorPort.proponer` → `PropuestaAgenda`.

Diseño acordado con Arley (12-nov-2026), ver docs/rol-3-agendador.md:
  A. Agente ACOTADO: el LLM decide (qué plantilla y qué franja para cada candidato) usando
     herramientas de solo lectura (ver_plantillas, consultar_franjas); NUNCA escribe el mensaje: el texto lo arma el código con la
     plantilla aprobada. Una baranda rechaza elecciones inválidas mostrándole las válidas (B2).
  B. {{nombre_de_pila}} es un MARCADOR que el envío (Rol 4) llena desde la bóveda de identidad:
     ningún nombre real entra a PropuestaAgenda (regla 4 de integración del Rol 1).
  C. Plantillas y calendario simulado en cvagent/agentes/agenda/ (no se toca data/ del Rol 2).

El agendador solo ve referencias opacas (cand_…): ni cv_id, ni ficha, ni texto del CV.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from .agente import AgenteSinResultado, ResultadoAgente, ejecutar_agente
from .herramientas import Herramienta
from .llm import ClienteLLM

DIR_AGENDA = Path(__file__).resolve().parent / "agenda"
VERSION_PROMPT = "agendador-v1"
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre"]
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_PASO_MIN = 30


class AgendaInvalida(Exception):
    """La propuesta final no cumple las reglas: no se entrega nada (fail-closed → humano)."""


def ref_opaca(cv_id: str, vacante_id: str) -> str:
    """cand_… estable y opaco (el agendador nunca ve el cv_id)."""
    return "cand_" + hashlib.sha256(f"{vacante_id}:{cv_id}".encode()).hexdigest()[:12]


def info_de_vacante(vacante: dict) -> dict:
    """Lo único de la vacante que el agendador necesita: cargo, ciudad y modalidad."""
    ubic = vacante.get("ubicacion", "")
    m = re.search(r"modalidad\s+(\w+)", ubic, re.I)
    return {"vacante_id": vacante["vacante_id"], "version": str(vacante["version"]),
            "cargo": vacante["titulo"], "ciudad": ubic.split(",")[0].strip() or "la ciudad de la sede",
            "modalidad": (m.group(1).lower() if m else "presencial")}


# ---------------------------------------------------------------------------- calendario
class Calendario:
    """Free/busy simulado del panel. En producción: la consulta del workflow, misma interfaz."""

    def __init__(self, datos: dict):
        self.datos = datos
        self.version = datos["version"]
        h = int(datos["zona_horaria"][:3])
        self.tz = timezone(timedelta(hours=h))
        self.anticipacion = timedelta(hours=datos["anticipacion_minima_horas"])
        self.ocupado = [(self._dt(a), self._dt(b)) for bloques in datos["ocupado"].values() for a, b in bloques]

    @classmethod
    def cargar(cls, ruta: Path = DIR_AGENDA / "calendario_simulado.json") -> "Calendario":
        return cls(json.loads(Path(ruta).read_text("utf-8")))

    def _dt(self, s: str) -> datetime:
        return datetime.fromisoformat(s).replace(tzinfo=self.tz)

    def _hora(self, d: date, hhmm: str) -> datetime:
        return datetime.combine(d, datetime.strptime(hhmm, "%H:%M").time(), self.tz)

    @staticmethod
    def id_de(inicio: datetime) -> str:
        return inicio.strftime("F-%Y%m%d-%H%M")

    def franjas_libres(self, duracion_min: int, ahora: datetime, desde: Optional[date] = None) -> list[dict]:
        j = self.datos["jornada"]
        ini_r, fin_r = (date.fromisoformat(x) for x in self.datos["rango"])
        festivos = {date.fromisoformat(x) for x in self.datos["festivos"]}
        dur = timedelta(minutes=duracion_min)
        libres, d = [], max(ini_r, desde or ini_r)
        while d <= fin_r:
            if d.weekday() in self.datos["dias_habiles"] and d not in festivos:
                t, fin_j = self._hora(d, j["inicio"]), self._hora(d, j["fin"])
                alm = (self._hora(d, j["almuerzo"][0]), self._hora(d, j["almuerzo"][1]))
                while t + dur <= fin_j:
                    f = t + dur
                    if (t >= ahora + self.anticipacion and not (t < alm[1] and f > alm[0])
                            and not any(t < b and f > a for a, b in self.ocupado)):
                        libres.append({"id": self.id_de(t), "inicio": t, "fin": f})
                    t += timedelta(minutes=_PASO_MIN)
            d += timedelta(days=1)
        return libres

    def franja(self, franja_id: str, duracion_min: int, ahora: datetime) -> Optional[dict]:
        return next((f for f in self.franjas_libres(duracion_min, ahora) if f["id"] == franja_id), None)


# ---------------------------------------------------------------------------- plantillas
class Plantillas:
    def __init__(self, datos: dict):
        self.datos = datos
        self.version = datos["version"]
        self.por_id = {p["id"]: p for p in datos["plantillas"]}

    @classmethod
    def cargar(cls, ruta: Path = DIR_AGENDA / "plantillas.json") -> "Plantillas":
        return cls(json.loads(Path(ruta).read_text("utf-8")))

    def renderizar(self, plantilla_id: str, variables: dict) -> str:
        """Solo variables permitidas; {{marcadores}} quedan intactos para el envío."""
        texto = self.por_id[plantilla_id]["texto"]
        usadas = set(re.findall(r"(?<!\{)\{(\w+)\}(?!\})", texto))
        no_permitidas = (set(variables) | usadas) - set(self.datos["variables_permitidas"])
        if no_permitidas:
            raise ValueError(f"variables no permitidas: {sorted(no_permitidas)}")
        if usadas - set(variables):
            raise ValueError(f"faltan variables: {sorted(usadas - set(variables))}")
        return re.sub(r"(?<!\{)\{(\w+)\}(?!\})", lambda m: str(variables[m.group(1)]), texto)


def _fecha_legible(dt: datetime) -> str:
    return f"{_DIAS[dt.weekday()]} {dt.day} de {_MESES[dt.month - 1]} de {dt.year}"


def variables_de(info: dict, plantilla: dict, inicio: datetime, fin: datetime) -> dict:
    return {"cargo": info["cargo"], "fecha": _fecha_legible(inicio), "hora_inicio": inicio.strftime("%H:%M"),
            "hora_fin": fin.strftime("%H:%M"), "duracion_min": plantilla["duracion_min"], "ciudad": info["ciudad"]}


# ---------------------------------------------------------------------------- contexto y herramientas
@dataclass
class ContextoAgenda:
    info: dict                     # cargo, ciudad, modalidad (de la vacante; nada del CV)
    candidatos: list[str]          # referencias opacas cand_…
    tipo_entrevista: str           # lo pide el reclutador: "tecnica" | "inicial"
    calendario: Calendario
    plantillas: Plantillas
    ahora: datetime


def _ver_plantillas(args: dict, ctx: ContextoAgenda) -> dict:
    return {"modalidad_de_la_vacante": ctx.info["modalidad"], "tipo_pedido": ctx.tipo_entrevista,
            "plantillas": [{k: p[k] for k in ("id", "nombre", "tipo", "duracion_min", "modalidades")}
                           for p in ctx.plantillas.datos["plantillas"]]}


def _consultar_franjas(args: dict, ctx: ContextoAgenda) -> dict:
    try:
        dur = int(args.get("duracion_min", 60))
        desde = date.fromisoformat(args["desde"]) if args.get("desde") else None
    except (TypeError, ValueError):
        return {"error": "duracion_min debe ser un entero y desde una fecha AAAA-MM-DD"}
    # Solo franjas que NO se cruzan entre sí (12-nov): si se ofrecen 10:00, 10:30 y 11:00 de 60 min,
    # «a cada candidato la siguiente» produce cruces. Así, cualquier elección de franjas distintas
    # es válida (la baranda igual acepta cualquier franja libre).
    libres, fin_ult = [], None
    for f in ctx.calendario.franjas_libres(dur, ctx.ahora, desde):
        if fin_ult is None or f["inicio"] >= fin_ult:
            libres.append(f)
            fin_ult = f["fin"]
    return {"duracion_min": dur, "total_libres": len(libres),
            "franjas": [{"id": f["id"], "dia": _fecha_legible(f["inicio"]),
                         "de": f["inicio"].strftime("%H:%M"), "a": f["fin"].strftime("%H:%M")} for f in libres[:12]],
            "nota": "Libres para TODO el panel, en horario hábil, con 24 h de anticipación y sin cruces entre sí. "
                    + ("Hay más: usa 'desde' para ver días siguientes." if len(libres) > 12 else "")}


def vista_previa(plantilla_id: str, franja_id: str, ctx: ContextoAgenda) -> dict:
    """Texto que generaría una elección. NO es herramienta del agente (12-nov: con qwen2.5:7b la usó
    una vez por candidato, en turnos separados, y agotó los pasos sin entregar; no aporta a la
    decisión porque el texto lo arma el código). Queda para el workflow y la bandeja."""
    p = ctx.plantillas.por_id.get(plantilla_id)
    if not p:
        return {"error": f"plantilla desconocida; existen: {sorted(ctx.plantillas.por_id)}"}
    f = ctx.calendario.franja(franja_id, p["duracion_min"], ctx.ahora)
    if not f:
        return {"error": "franja no libre o inexistente para esa duración"}
    return {"texto": ctx.plantillas.renderizar(p["id"], variables_de(ctx.info, p, f["inicio"], f["fin"]))}


REGISTRO_AGENDA: dict[str, Herramienta] = {h.nombre: h for h in (
    Herramienta("ver_plantillas", "Lista las plantillas de mensaje aprobadas (id, tipo, duración, modalidades).",
                {"type": "object", "properties": {}, "additionalProperties": False}, _ver_plantillas),
    Herramienta("consultar_franjas", "Franjas libres del panel entrevistador para una duración (minutos). "
                "Solo lectura; no reserva nada.",
                {"type": "object", "properties": {"duracion_min": {"type": "integer"},
                                                  "desde": {"type": "string", "description": "AAAA-MM-DD, opcional"}},
                 "required": ["duracion_min"], "additionalProperties": False}, _consultar_franjas),
)}
ALLOWLIST = list(REGISTRO_AGENDA)


# ---------------------------------------------------------------------------- salida del LLM
class Asignacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidato_ref: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")
    plantilla_id: str
    franja_id: str = Field(pattern=r"^F-\d{8}-\d{4}$")


class AgendaLLM(BaseModel):
    """Lo ÚNICO que decide el LLM. No hay campo de texto: el mensaje lo arma el código."""
    model_config = ConfigDict(extra="forbid")
    asignaciones: list[Asignacion] = Field(min_length=1)


def problemas_de_agenda(salida: AgendaLLM, ctx: ContextoAgenda) -> list[str]:
    """Baranda: cada problema trae la observación necesaria para corregir (como B2)."""
    problemas, usadas = [], []
    refs = [a.candidato_ref for a in salida.asignaciones]
    for r in sorted(set(ctx.candidatos) - set(refs)):
        problemas.append(f"{r}: falta asignarle entrevista.")
    for r in sorted(set(refs) - set(ctx.candidatos)):
        problemas.append(f"{r}: no está en la lista aprobada; quítalo.")
    for r in sorted({r for r in refs if refs.count(r) > 1}):
        problemas.append(f"{r}: aparece más de una vez; una sola franja por candidato.")
    for a in salida.asignaciones:
        p = ctx.plantillas.por_id.get(a.plantilla_id)
        if not p:
            problemas.append(f"{a.candidato_ref}: plantilla '{a.plantilla_id}' no existe; válidas: "
                             f"{sorted(ctx.plantillas.por_id)}.")
            continue
        if p["tipo"] != ctx.tipo_entrevista or ctx.info["modalidad"] not in p["modalidades"]:
            validas = [x["id"] for x in ctx.plantillas.datos["plantillas"]
                       if x["tipo"] == ctx.tipo_entrevista and ctx.info["modalidad"] in x["modalidades"]]
            problemas.append(f"{a.candidato_ref}: '{a.plantilla_id}' no sirve para una entrevista "
                             f"'{ctx.tipo_entrevista}' en modalidad '{ctx.info['modalidad']}'; válidas: {validas}.")
            continue
        f = ctx.calendario.franja(a.franja_id, p["duracion_min"], ctx.ahora)
        cruce = f and next((u for u in usadas if f["inicio"] < u[2] and f["fin"] > u[1]), None)
        if f and not cruce:
            usadas.append((a.candidato_ref, f["inicio"], f["fin"]))
            continue
        libres = [x["id"] for x in ctx.calendario.franjas_libres(p["duracion_min"], ctx.ahora)
                  if not any(x["inicio"] < u[2] and x["fin"] > u[1] for u in usadas)][:8]
        motivo = (f"se cruza con la de {cruce[0]}" if cruce else
                  "no está libre para todo el panel, es festivo/fin de semana, fuera de jornada o con menos de 24 h")
        problemas.append(f"{a.candidato_ref}: la franja {a.franja_id} {motivo}. Franjas válidas de "
                         f"{p['duracion_min']} min aún sin usar: {libres}.")
    return problemas


INSTRUCCIONES = """Eres el agente AGENDADOR de un proceso de selección. Propones, para cada candidato
de una lista ya aprobada por el reclutador, UNA plantilla de mensaje y UNA franja de entrevista.

LÍMITES (no negociables):
- No ves hojas de vida ni nombres: solo referencias opacas (cand_…). No las interpretes.
- No escribes el mensaje: eliges plantilla_id y franja_id; el sistema arma el texto exacto, y un
  humano lo aprueba antes de cualquier envío. No envías ni reservas nada.

CÓMO TRABAJAR:
1. Llama ver_plantillas y elige la que corresponda al TIPO pedido y a la MODALIDAD de la vacante.
   En modalidad híbrida, prefiere la virtual para la primera entrevista.
2. Llama consultar_franjas con la duración de esa plantilla.
3. Asigna a cada candidato una franja DISTINTA, en el orden de la lista (el primero, la más temprana).
4. Entrega TODAS las asignaciones juntas, en una sola llamada a entregar_resultado, en un turno aparte. Si la entrega es rechazada, los detalles traen
   las franjas válidas: corrige solo lo indicado.
"""


def construir_tarea(ctx: ContextoAgenda) -> str:
    return (f"Cargo: {ctx.info['cargo']}\nModalidad de la vacante: {ctx.info['modalidad']}\n"
            f"Tipo de entrevista pedido por el reclutador: {ctx.tipo_entrevista}\n"
            f"Fecha y hora actuales: {ctx.ahora.strftime('%Y-%m-%d %H:%M')} (hora de Bogotá)\n"
            f"Candidatos, en el orden de la lista aprobada ({len(ctx.candidatos)}):\n"
            + "\n".join(f"- {c}" for c in ctx.candidatos))


# ---------------------------------------------------------------------------- propuestas (contrato Rol 1)
def construir_propuestas(salida: AgendaLLM, ctx: ContextoAgenda, *, correlation_id: str,
                         modelo: str) -> list:
    """AgendaLLM validada → PropuestaAgenda del contrato v1.0.0 del Rol 1 (una por candidato)."""
    from ..domain.contracts import AuditMetadata, PropuestaAgenda
    propuestas = []
    for a in salida.asignaciones:
        p = ctx.plantillas.por_id[a.plantilla_id]
        f = ctx.calendario.franja(a.franja_id, p["duracion_min"], ctx.ahora)
        propuestas.append(PropuestaAgenda(
            correlation_id=correlation_id, vacante_id=ctx.info["vacante_id"],
            candidato_ref=a.candidato_ref, destinatario_ref="dest_" + a.candidato_ref[5:],
            franja=f"{f['inicio'].isoformat()}/{f['fin'].isoformat()}",
            texto_exacto=ctx.plantillas.renderizar(p["id"], variables_de(ctx.info, p, f["inicio"], f["fin"])),
            plantilla_version=f"{ctx.plantillas.version}:{p['id']}", creada_en=ctx.ahora,
            auditoria=AuditMetadata(
                componente="rol-3-agendador", fuente=[ctx.plantillas.version, ctx.calendario.version],
                versiones={"vacante": ctx.info["version"], "plantilla": ctx.plantillas.version,
                           "prompt": VERSION_PROMPT},
                timestamp=ctx.ahora, modelo_version=modelo, prompt_version=VERSION_PROMPT)))
    return propuestas


def verificar_propuesta(propuesta, info: dict, plantillas: Optional[Plantillas] = None,
                        calendario: Optional[Calendario] = None) -> list[str]:
    """Para el workflow/Rol 4 antes de pedir aprobación o tras un ajuste: el texto debe ser
    EXACTAMENTE la plantilla con las variables de su franja (SDD: «texto idéntico al aprobado»)."""
    plantillas = plantillas or Plantillas.cargar()
    calendario = calendario or Calendario.cargar()
    version, _, pid = propuesta.plantilla_version.partition(":")
    if version != plantillas.version or pid not in plantillas.por_id:
        return [f"plantilla '{propuesta.plantilla_version}' no está aprobada en {plantillas.version}"]
    ini, fin = (datetime.fromisoformat(x) for x in propuesta.franja.split("/"))
    esperado = plantillas.renderizar(pid, variables_de(info, plantillas.por_id[pid], ini, fin))
    problemas = [] if propuesta.texto_exacto == esperado else ["el texto no es idéntico a la plantilla aprobada"]
    if re.search(r"(?<!\{)\{(?!\{)\w+\}", propuesta.texto_exacto):
        problemas.append("quedan variables sin llenar")
    return problemas


@dataclass
class ResultadoAgenda:
    propuestas: list
    agente: Optional[ResultadoAgente]
    segundos: float
    contexto: ContextoAgenda = field(repr=False, default=None)


def agendar(candidatos_ref: list[str], info: dict, cliente: Optional[ClienteLLM], *, ahora: datetime,
            tipo_entrevista: str = "tecnica", correlation_id: Optional[str] = None,
            calendario: Optional[Calendario] = None, plantillas: Optional[Plantillas] = None,
            al_evento: Optional[Callable] = None, max_pasos: int = 7) -> ResultadoAgenda:
    """Con `cliente=None` usa la asignación determinista (solo para demo y pruebas)."""
    ctx = ContextoAgenda(info, list(candidatos_ref), tipo_entrevista, calendario or Calendario.cargar(),
                         plantillas or Plantillas.cargar(), ahora)
    t0 = time.monotonic()
    if cliente is None:
        salida, agente, modelo = asignacion_simple(ctx), None, "simulado:determinista"
    else:
        try:
            agente = _ejecutar(ctx, cliente, al_evento, max_pasos)
        except AgenteSinResultado as e:   # agotó los pasos: nada sale, el caso va a un humano
            raise AgendaInvalida([str(e)]) from e
        salida, modelo = agente.salida, cliente.config.etiqueta
    problemas = problemas_de_agenda(salida, ctx)
    if problemas:   # la baranda cedió tras 3 rechazos: nada sale, el caso va a un humano
        raise AgendaInvalida(problemas)
    propuestas = construir_propuestas(salida, ctx, correlation_id=correlation_id or str(uuid.uuid4()),
                                      modelo=modelo)
    return ResultadoAgenda(propuestas, agente, time.monotonic() - t0, ctx)


def _ejecutar(ctx: ContextoAgenda, cliente: ClienteLLM, al_evento, max_pasos: int) -> ResultadoAgente:
    return ejecutar_agente(
            nombre="agendador", cliente=cliente, instrucciones=INSTRUCCIONES, tarea=construir_tarea(ctx),
            allowlist=ALLOWLIST, contexto=ctx, esquema_salida=AgendaLLM, max_pasos=max_pasos,
            al_evento=al_evento, registro=REGISTRO_AGENDA, max_rechazos_entrega=3,
            validar_entrega=lambda s, _t: problemas_de_agenda(s, ctx),
            mensaje_rechazo="Entrega rechazada: hay asignaciones que no cumplen las reglas de agenda. "
                            "Lee los detalles (traen las opciones válidas), corrige y vuelve a entregar.")


def asignacion_simple(ctx: ContextoAgenda) -> AgendaLLM:
    """Sin LLM: primera plantilla válida (virtual primero) y franjas libres en orden, sin cruces."""
    validas = [p for p in ctx.plantillas.datos["plantillas"]
               if p["tipo"] == ctx.tipo_entrevista and ctx.info["modalidad"] in p["modalidades"]]
    if not validas:
        raise AgendaInvalida([f"no hay plantilla '{ctx.tipo_entrevista}' para modalidad '{ctx.info['modalidad']}'"])
    p = sorted(validas, key=lambda x: "virtual" not in x["id"])[0]
    usadas, asign = [], []
    for c in ctx.candidatos:
        f = next((x for x in ctx.calendario.franjas_libres(p["duracion_min"], ctx.ahora)
                  if not any(x["inicio"] < u["fin"] and x["fin"] > u["inicio"] for u in usadas)), None)
        if f is None:
            raise AgendaInvalida([f"no quedan franjas libres para {c}"])
        usadas.append(f)
        asign.append(Asignacion(candidato_ref=c, plantilla_id=p["id"], franja_id=f["id"]))
    return AgendaLLM(asignaciones=asign)


class AgendadorRol3:
    """Adaptador para el grafo del Rol 1 (`AgendadorPort`). Brecha de contrato v1.0.0: `proponer`
    devuelve UNA PropuestaAgenda por lista; aquí se agenda a todos (sin cruces de franja) y se
    devuelve la del primero, dejando todas en `self.ultimas` (ver docs/rol-3-propuesta-contratos.md)."""

    def __init__(self, info: dict, cliente: Optional[ClienteLLM] = None, tipo_entrevista: str = "tecnica"):
        self.info, self.cliente, self.tipo = info, cliente, tipo_entrevista
        self.ultimas: list = []

    def proponer(self, state, propuesta, *, now: datetime):
        r = agendar(list(propuesta.candidatos_ref), self.info, self.cliente, ahora=now,
                    tipo_entrevista=self.tipo, correlation_id=state.correlation_id)
        self.ultimas = r.propuestas
        return r.propuestas[0]
