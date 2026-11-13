"""Adaptadores del portal sobre los puertos del Rol 1.

Qué es real y qué es provisional, para que nadie se confunda al leerlo:

    MotorReglasPort  → REAL. Usa `reglas/` del Rol 2 sin tocarlo: R1, R2, R3,
                       R11, R7 por caso y R4, R5, R6 en el lote.
    AnalistaPort     → PROVISIONAL. Ocupa el lugar del agente del Rol 3. No
                       hay modelo de lenguaje: localiza en el texto canónico
                       los términos del requisito y ancla la cita por posición.
    AuditorPort      → PROVISIONAL. Verificación determinista de citas,
                       cobertura e indicios de inyección. La parte que sí
                       necesita modelo (¿la cita respalda el valor afirmado?)
                       queda marcada y es del Rol 3.
    AgendadorPort    → PROVISIONAL. Plantilla fija, sin acceso al CV.

Los dos adaptadores provisionales existen para que el grafo del Rol 1 corra de
punta a punta hoy. Producen exactamente los contratos de
`cvagent.domain.contracts`, así que reemplazarlos es cambiar una línea en
`portal/lote.py`, no reescribir el portal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from cvagent.domain.contracts import (
    AuditMetadata,
    CaseState,
    CitationRef,
    FichaCandidato,
    PropuestaAgenda,
    PropuestaLista,
    Veredicto,
    VeredictoEstado,
)

from reglas import consultar_equivalencias
from reglas.diccionario import PESO_MINIMO_EQUIVALENCIA

VERSION_ADAPTADORES = "portal-1.0.0"

# Señales de instrucción dirigida al sistema dentro de un CV. El CV es dato,
# nunca instrucción: lo detectado aquí bloquea, no se obedece.
PATRONES_INYECCION: list[tuple[str, str]] = [
    # (nombre legible, patrón). El nombre es lo que lee una persona en la
    # bandeja; el patrón nunca se le muestra.
    ("anula_instrucciones_previas",
     r"ignor[ae]\s+(las\s+|todas\s+las\s+|tus\s+)?instrucciones"
     r"|(all\s+)?previous\s+instructions?\s+(are\s+void|ignored)"
     r"|ignore\s+(all\s+|the\s+)?(previous\s+|prior\s+)?instructions"),
    ("pide_omitir_requisitos",
     r"omitir\s+la\s+revisi[oó]n|disregard\s+the\s+(job\s+)?requirements"),
    ("suplanta_al_sistema",
     r"system\s*message|system\s*:|<\s*/?\s*(system|prompt|instruction)"
     r"|eres\s+un\s+(asistente|sistema|modelo)"
     r"|you\s+are\s+an?\s+(assistant|system|ai)|dear\s+ai\s+(reviewer|assistant)"),
    ("suplanta_aprobacion_humana",
     r"(nota|mensaje)\s+(de\s+)?(verificaci[oó]n\s+)?interna?\s+de\s+rr\.?\s*hh"
     r"|ya\s+fue\s+validado\s+por\s+el\s+equipo"),
    ("dicta_el_resultado",
     r"asignar\s+puntaje\s+m[aá]ximo"
     r"|califica(?:r|me|lo)?\s+con\s+(el\s+)?(m[aá]ximo|100|10/10)"
     r"|responde\s+(siempre\s+)?que\s+(cumple|aprueba)"
     r"|rank\s+this\s+candidate\s+first"
     r"|\"?(decision|decisi[oó]n)\"?\s*:\s*\"?(aprobado|approved)"),
    ("pide_ocultar_la_nota",
     r"(no\s+menciones?|do\s+not\s+mention)\s+(esta|this)\s+(nota|note)"),
]


# --------------------------------------------------------------------------
@dataclass
class ContextoCaso:
    """Todo lo que el portal sabe de un CV dentro de un lote.

    Existe porque `CaseState` no tiene dónde guardar el identificador del CV
    ni el texto canónico (es `extra="forbid"`). Ver el hallazgo H-1 en
    docs/rol-4-portal.md: mientras el contrato no lo incluya, la correlación
    vive aquí, fuera del estado del grafo.
    """

    cv_id: str
    candidato_ref: str
    ficha_json: dict
    texto: str
    procedencia: str
    resultado_reglas: dict
    citas: list[CitationRef] = field(default_factory=list)
    cobertura: float = 0.0
    puntaje: float = 0.0
    hallazgos: list[str] = field(default_factory=list)


@dataclass
class ContextoLote:
    vacante: dict
    diccionario: dict
    casos: dict[str, ContextoCaso] = field(default_factory=dict)   # correlation_id → caso

    def caso(self, correlation_id: str) -> ContextoCaso:
        try:
            return self.casos[correlation_id]
        except KeyError as exc:
            raise KeyError(f"correlation_id sin contexto en el portal: {correlation_id}") from exc


# --------------------------------------------------------------------------
def _obligatorios(vacante: dict) -> list[dict]:
    return [r for r in vacante["requisitos"] if r["tipo"] == "obligatorio"]


def _deseables(vacante: dict) -> list[dict]:
    return [r for r in vacante["requisitos"] if r["tipo"] == "deseable"]


def terminos_del_requisito(req: dict, diccionario: dict) -> list[str]:
    """Términos literales que, si aparecen en el CV, sustentan el requisito."""
    categoria = req.get("categoria")
    if categoria == "idioma":
        return [req["idioma"], "Ingles", "English"]
    if categoria == "educacion":
        return list(req.get("titulos_aceptados", []))
    concepto = req.get("concepto")
    if not concepto:
        return []
    # `consultar_equivalencias` recibe una lista de conceptos y devuelve filas
    # {requisito, equivalente, peso}. Solo acreditan las de peso suficiente.
    filas = consultar_equivalencias(diccionario, [concepto])
    equivalentes = [f["equivalente"] for f in filas
                    if f["peso"] >= PESO_MINIMO_EQUIVALENCIA]
    vistos, salida = set(), []
    for t in [concepto, *equivalentes]:
        if t and t.lower() not in vistos:
            vistos.add(t.lower())
            salida.append(t)
    return salida


def citar(texto: str, termino: str, *, correlation_id: str, fuente: str) -> CitationRef | None:
    """Ancla un término y devuelve una cita YA VERIFICADA, o None.

    El anclaje lo hace el código, nunca el modelo: se busca la aparición y se
    amplía a la línea completa, que es más informativa para quien revisa y casi
    siempre única. La cita se construye recortando el texto, así que el
    invariante `texto[inicio:fin] == cita` se cumple por construcción y
    `verify_against` lo confirma.
    """
    m = re.search(re.escape(termino), texto, re.IGNORECASE)
    if m is None:
        return None

    ini_linea = texto.rfind("\n", 0, m.start()) + 1
    fin_linea = texto.find("\n", m.end())
    fin_linea = len(texto) if fin_linea < 0 else fin_linea
    inicio, fin = ini_linea, fin_linea
    while inicio < fin and texto[inicio].isspace():
        inicio += 1
    while fin > inicio and texto[fin - 1].isspace():
        fin -= 1
    if fin - inicio < 3:                      # línea inservible: usa la coincidencia
        inicio, fin = m.start(), m.end()

    cita = CitationRef(
        correlation_id=correlation_id,
        fuente=fuente,
        cita=texto[inicio:fin],
        offset_inicio=inicio,
        offset_fin=fin,
    )
    return cita.verify_against(texto)


def detectar_inyeccion(texto: str) -> list[str]:
    """Nombres de las señales encontradas. El CV es dato, nunca instrucción."""
    return [nombre for nombre, patron in PATRONES_INYECCION
            if re.search(patron, texto, re.IGNORECASE)]


def _auditoria(componente: str, caso: ContextoCaso, vacante: dict, now: datetime,
               **extra: str) -> AuditMetadata:
    return AuditMetadata(
        componente=componente,
        fuente=[f"{caso.cv_id}:{caso.procedencia}"],
        versiones={
            "vacante": str(vacante["version"]),
            "reglas": "rol2-1.0.0",
            "adaptadores": VERSION_ADAPTADORES,
        },
        timestamp=now,
        **extra,
    )


# ============================================================== AnalistaPort
class PortalAnalista:
    """Doble del agente analista (Rol 3). Sin modelo de lenguaje.

    Reemplazarlo es implementar `crear_ficha` con el mismo contrato. La parte
    que el agente real NO debe cambiar es el anclaje: al modelo se le pide la
    subcadena literal y las posiciones las calcula `citar()`.
    """

    def __init__(self, contexto: ContextoLote):
        self.contexto = contexto

    def crear_ficha(self, state: CaseState, *, now: datetime) -> FichaCandidato:
        caso = self.contexto.caso(state.correlation_id)
        vacante = self.contexto.vacante
        fuente = f"{caso.cv_id}.{'pdf' if caso.procedencia == 'pdf' else 'json'}"

        citas: list[CitationRef] = []
        sustentados: set[str] = set()
        for req in _obligatorios(vacante):
            for termino in terminos_del_requisito(req, self.contexto.diccionario):
                cita = citar(caso.texto, termino, correlation_id=state.correlation_id, fuente=fuente)
                if cita is not None:
                    citas.append(cita)
                    sustentados.add(req["id"])
                    break

        deseables_vistos = []
        for req in _deseables(vacante):
            for termino in terminos_del_requisito(req, self.contexto.diccionario):
                if re.search(re.escape(termino), caso.texto, re.IGNORECASE):
                    deseables_vistos.append(req["id"])
                    break

        obligatorios = _obligatorios(vacante)
        caso.citas = citas
        caso.cobertura = round(len(sustentados) / max(1, len(obligatorios)), 6)
        caso.puntaje = _puntaje(caso, vacante, deseables_vistos)
        caso.hallazgos = [f"posible_inyeccion:{p}" for p in detectar_inyeccion(caso.texto)]

        if not citas:
            # FichaCandidato exige al menos una cita. Sin ninguna, el caso no
            # es evaluable y eso lo decide el grafo, no este adaptador.
            raise ValueError(f"{caso.cv_id}: ninguna cita verificable en el texto canónico")

        return FichaCandidato(
            correlation_id=state.correlation_id,
            candidato_ref=caso.candidato_ref,
            vacante_id=state.vacante_id,
            vacante_version=state.vacante_version,
            resumen=(f"{len(sustentados)} de {len(obligatorios)} requisitos obligatorios "
                     f"con evidencia citada; {len(deseables_vistos)} deseable(s) observado(s)."),
            citas=citas,
            creado_en=now,
            actualizado_en=now,
            auditoria=_auditoria("portal-analista-doble", caso, vacante, now,
                                 modelo_version="ninguno", prompt_version="ninguno",
                                 esquema_version="1.0.0"),
        )


def _puntaje(caso: ContextoCaso, vacante: dict, deseables_vistos: list[str]) -> float:
    """Puntaje determinista en [0, 1]. Fuera del modelo, como exige el SDD.

        0,50  obligatorios en estado «cumple» (R3)
        0,25  deseables observados con evidencia en el texto
        0,25  experiencia efectiva (R11) por encima del mínimo, saturando al doble

    El tercer componente existe porque sin él casi todos los evaluables empatan:
    pasar R3 es binario y los deseables se repiten mucho en el corpus. Los meses
    efectivos son la única señal continua disponible hoy, y vienen del motor del
    Rol 2, no de una estimación del portal.

    Los tres pesos son un SUPUESTO del Rol 4. La rúbrica real no está definida
    en el SDD: ver el hallazgo H-3 en docs/rol-4-portal.md.
    """
    estados = caso.resultado_reglas.get("estado_requisitos", {}) or {}
    obligatorios = _obligatorios(vacante)
    cumplen = sum(1 for r in obligatorios if estados.get(r["id"]) == "cumple")
    base = cumplen / max(1, len(obligatorios))

    deseables = _deseables(vacante)
    extra = len(deseables_vistos) / max(1, len(deseables))

    minimo_meses = max(
        (r.get("min_anios", 0) * 12 for r in obligatorios if r.get("categoria") == "experiencia"),
        default=0,
    ) or 36
    meses = caso.resultado_reglas.get("meses_efectivos") or 0
    experiencia = min(1.0, meses / (minimo_meses * 2))

    return round(0.50 * base + 0.25 * extra + 0.25 * experiencia, 6)


# =========================================================== MotorReglasPort
class PortalMotorReglas:
    """Traduce el resultado REAL del motor del Rol 2 al `Veredicto` del Rol 1.

    No reimplementa ninguna regla: `reglas.procesar_lote` ya corrió antes de
    que el grafo arrancara y su salida está en `caso.resultado_reglas`.
    """

    def __init__(self, contexto: ContextoLote):
        self.contexto = contexto

    def evaluar(self, ficha: FichaCandidato, *, now: datetime) -> Veredicto:
        caso = self.contexto.caso(ficha.correlation_id)
        estados = caso.resultado_reglas.get("estado_requisitos", {}) or {}
        obligatorios = _obligatorios(self.contexto.vacante)

        incumple = [r["id"] for r in obligatorios if estados.get(r["id"]) == "incumple"]
        dudosos = [r["id"] for r in obligatorios
                   if estados.get(r["id"]) in {"no_acreditado", "por_confirmar"}]

        if incumple:
            estado, razon = VeredictoEstado.BLOQUEADO, f"R3 incumplido: {', '.join(incumple)}"
        elif dudosos:
            # Ni cumple ni incumple: no se convierte en descarte automático.
            estado, razon = (VeredictoEstado.REQUIERE_REVISION,
                             f"R3 sin acreditar o por confirmar: {', '.join(dudosos)}")
        else:
            estado, razon = VeredictoEstado.APROBADO, "R3: todos los obligatorios cumplen"

        return Veredicto(
            correlation_id=ficha.correlation_id,
            candidato_ref=ficha.candidato_ref,
            estado=estado,
            razon=razon,
            cobertura=caso.cobertura,
            puntaje=caso.puntaje,
            citas=ficha.citas,
            auditoria=_auditoria("rol2-motor-reglas", caso, self.contexto.vacante, now),
        )

    def crear_propuesta_lista(self, ficha: FichaCandidato, veredicto: Veredicto, *,
                              now: datetime) -> PropuestaLista:
        """Propuesta de UN caso. El Top 5 del lote lo arma `reglas.armar_staging`.

        Ver el hallazgo H-2: el grafo del Rol 1 es por caso y R4/R5/R6 son de
        lote. Mientras eso no se concilie, esta propuesta es de un candidato y
        el ordenamiento real lo hace el portal con el motor del Rol 2.
        """
        caso = self.contexto.caso(ficha.correlation_id)
        return PropuestaLista(
            correlation_id=ficha.correlation_id,
            vacante_id=ficha.vacante_id,
            vacante_version=ficha.vacante_version,
            version=1,
            candidatos_ref=[ficha.candidato_ref],
            razones={ficha.candidato_ref: veredicto.razon},
            creada_en=now,
            auditoria=_auditoria("rol2-staging", caso, self.contexto.vacante, now),
        )


# =============================================================== AuditorPort
class PortalAuditor:
    """Doble del auditor (Rol 3). Puede bloquear; nunca aprobar.

    Verificación determinista: recorta cada cita por sus offsets y compara. Lo
    que sí necesita modelo —si la cita respalda semánticamente el valor
    afirmado— no se hace aquí y queda señalado en la razón.
    """

    def __init__(self, contexto: ContextoLote, *, umbral_cobertura: float = 0.70):
        self.contexto = contexto
        self.umbral = umbral_cobertura

    def auditar(self, ficha: FichaCandidato, veredicto: Veredicto) -> Veredicto:
        caso = self.contexto.caso(ficha.correlation_id)
        hallazgos: list[str] = []

        for cita in ficha.citas:
            if caso.texto[cita.offset_inicio:cita.offset_fin] != cita.cita:
                hallazgos.append(f"offset_invalido:{cita.fuente}")
            elif not cita.verificada:
                hallazgos.append(f"cita_no_verificada:{cita.fuente}")

        if caso.hallazgos:
            hallazgos.extend(caso.hallazgos)

        if veredicto.cobertura < self.umbral:
            hallazgos.append(f"cobertura_insuficiente:{veredicto.cobertura:.2f}<{self.umbral:.2f}")

        if not hallazgos:
            return veredicto

        bloqueante = any(h.startswith(("offset_invalido", "cita_no_verificada", "posible_inyeccion"))
                         for h in hallazgos)
        return veredicto.model_copy(update={
            "estado": VeredictoEstado.BLOQUEADO if bloqueante else VeredictoEstado.REQUIERE_REVISION,
            "razon": "Auditor: " + "; ".join(hallazgos),
        })


# ============================================================= AgendadorPort
PLANTILLA = (
    "Buen día.\n\n"
    "Gracias por postularse a la vacante {titulo}. Queremos invitarle a una "
    "entrevista en la franja {franja}.\n\n"
    "Por favor responda a este mensaje para confirmar o proponer otra hora.\n\n"
    "Equipo de selección"
)


class PortalAgendador:
    """Doble del agendador. No accede al CV: solo plantilla y franja."""

    def __init__(self, contexto: ContextoLote, *, plantilla_version: str = "portal-1"):
        self.contexto = contexto
        self.plantilla_version = plantilla_version

    def proponer(self, state: CaseState, propuesta: PropuestaLista, *,
                 now: datetime) -> PropuestaAgenda:
        caso = self.contexto.caso(state.correlation_id)
        candidato = propuesta.candidatos_ref[0]
        franja = _franja_habil(now)
        return PropuestaAgenda(
            correlation_id=state.correlation_id,
            vacante_id=state.vacante_id,
            candidato_ref=candidato,
            destinatario_ref=f"contacto_{candidato}",
            franja=franja,
            texto_exacto=PLANTILLA.format(
                titulo=self.contexto.vacante["titulo"], franja=franja),
            plantilla_version=self.plantilla_version,
            creada_en=now,
            auditoria=_auditoria("portal-agendador-doble", caso,
                                 self.contexto.vacante, now),
        )


def _franja_habil(now: datetime) -> str:
    """Franja determinista: siguiente día hábil a las 10:00 UTC, 30 minutos."""
    from datetime import timedelta

    d = now + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    ini = d.replace(hour=10, minute=0, second=0, microsecond=0)
    fin = ini + timedelta(minutes=30)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return f"{ini.strftime(fmt)}/{fin.strftime(fmt)}"


# --------------------------------------------------------------------------
def adaptadores_del_portal(contexto: ContextoLote):
    """Arma el `RoleAdapters` del Rol 1 con las piezas del portal."""
    from cvagent.integration.ports import RoleAdapters
    from cvagent.operations.core import SimulatedDeliveryGateway

    return RoleAdapters(
        analista=PortalAnalista(contexto),
        motor_reglas=PortalMotorReglas(contexto),
        auditor=PortalAuditor(contexto),
        agendador=PortalAgendador(contexto),
        envio=SimulatedDeliveryGateway(),
    )


__all__ = [
    "ContextoCaso", "ContextoLote", "PortalAgendador", "PortalAnalista",
    "PortalAuditor", "PortalMotorReglas", "VERSION_ADAPTADORES",
    "adaptadores_del_portal", "citar", "detectar_inyeccion",
    "terminos_del_requisito",
]
