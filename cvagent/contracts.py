"""Versioned, strict contracts shared by CVAgent roles.

This is the single source of truth for the Role 1 domain boundary. Roles 2–4
may implement adapters around these models, but must not duplicate or widen
them silently. All identifiers used in the evaluation path are opaque
references; identity data and credentials are deliberately absent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CONTRACT_VERSION = "1.0.0"


class StrictModel(BaseModel):
    """Base model that rejects unknown fields and implicit type coercion."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
        validate_default=True,
    )


class EstadoCaso(str, Enum):
    RECIBIDO = "recibido"
    EVALUANDO = "evaluando"
    PROPUESTA_LISTA = "propuesta_lista"
    PENDIENTE_APROBACION_LISTA = "pendiente_aprobacion_lista"
    LISTA_APROBADA = "lista_aprobada"
    LISTA_AJUSTADA = "lista_ajustada"
    LISTA_RECHAZADA = "lista_rechazada"
    AGENDAMIENTO_PROPUESTO = "agendamiento_propuesto"
    PENDIENTE_APROBACION_MENSAJE = "pendiente_aprobacion_mensaje"
    MENSAJE_APROBADO = "mensaje_aprobado"
    MENSAJE_AJUSTADO = "mensaje_ajustado"
    MENSAJE_RECHAZADO = "mensaje_rechazado"
    ENVIANDO = "enviando"
    CERRADO = "cerrado"
    PENDIENTE_REVISION = "pendiente_revision"
    PAUSADO_KILL_SWITCH = "pausado_kill_switch"
    VENCIDO_LISTA = "vencido_lista"
    VENCIDO_MENSAJE = "vencido_mensaje"


class EstadoAprobacion(str, Enum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    AJUSTADA = "ajustada"
    RECHAZADA = "rechazada"
    SIN_RESPUESTA = "sin_respuesta"


class TipoAprobacion(str, Enum):
    LISTA_CORTA = "lista_corta"
    MENSAJE_EXACTO = "mensaje_exacto"


class VeredictoEstado(str, Enum):
    APROBADO = "aprobado"
    BLOQUEADO = "bloqueado"
    REQUIERE_REVISION = "requiere_revision"
    NO_EVALUABLE = "no_evaluable"


class RazónParada(str, Enum):
    APROBACION_LISTA_PENDIENTE = "aprobacion_lista_pendiente"
    APROBACION_MENSAJE_PENDIENTE = "aprobacion_mensaje_pendiente"
    LISTA_RECHAZADA = "lista_rechazada"
    MENSAJE_RECHAZADO = "mensaje_rechazado"
    REQUIERE_REVISION_HUMANA = "requiere_revision_humana"
    FALLA_TRANSITORIA = "falla_transitoria"
    HERRAMIENTA_NO_PERMITIDA = "herramienta_no_permitida"
    KILL_SWITCH_ACTIVO = "kill_switch_activo"
    SLA_VENCIDO = "sla_vencido"
    DATOS_INVALIDOS = "datos_invalidos"


class EstadoSLA(str, Enum):
    PENDIENTE = "pendiente"
    RECORDATORIO = "recordatorio"
    ESCALADO = "escalado"
    VENCIDO = "vencido"
    ATENDIDO = "atendido"


class TipoSLA(str, Enum):
    LISTA_CORTA = "lista_corta"
    MENSAJE = "mensaje"


class DecisionHumana(str, Enum):
    APROBAR = "aprobar"
    AJUSTAR = "ajustar"
    RECHAZAR = "rechazar"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4_string(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("correlation_id must be a valid UUID4 string") from exc
    if parsed.version != 4:
        raise ValueError("correlation_id must use UUID version 4")
    return str(parsed)


class AuditMetadata(StrictModel):
    """Versions and provenance required to reconstruct a derived artifact."""

    contrato_version: str = CONTRACT_VERSION
    componente: str = Field(min_length=1)
    fuente: list[str] = Field(min_length=1)
    versiones: dict[str, str] = Field(min_length=1)
    timestamp: datetime
    modelo_version: str | None = None
    prompt_version: str | None = None
    esquema_version: str | None = None


class CitationRef(StrictModel):
    """Literal evidence reference into one sanitized case document."""

    correlation_id: str
    fuente: str = Field(min_length=1)
    cita: str = Field(min_length=1)
    offset_inicio: int = Field(ge=0)
    offset_fin: int = Field(ge=1)
    verificada: bool = False

    _validate_correlation_id = field_validator("correlation_id")(_uuid4_string)

    @model_validator(mode="after")
    def offsets_are_ordered(self) -> CitationRef:
        if self.offset_fin <= self.offset_inicio:
            raise ValueError("offset_fin must be greater than offset_inicio")
        if self.offset_fin - self.offset_inicio != len(self.cita):
            raise ValueError("citation offsets must span exactly the cited text")
        return self

    def verify_against(self, sanitized_text: str) -> CitationRef:
        """Return a verified copy only when the exact slice matches the quote."""

        observed = sanitized_text[self.offset_inicio : self.offset_fin]
        if observed != self.cita:
            raise ValueError("citation does not match sanitized text at the offsets")
        return self.model_copy(update={"verificada": True})


class FichaCandidato(StrictModel):
    """Minimized, derived candidate sheet; it is not verified identity data."""

    correlation_id: str
    candidato_ref: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")
    vacante_id: str = Field(min_length=1)
    vacante_version: str = Field(min_length=1)
    resumen: str = Field(min_length=1)
    citas: list[CitationRef] = Field(min_length=1)
    creado_en: datetime
    actualizado_en: datetime
    auditoria: AuditMetadata

    _validate_correlation_id = field_validator("correlation_id")(_uuid4_string)

    @model_validator(mode="after")
    def timestamps_are_coherent(self) -> FichaCandidato:
        if self.actualizado_en < self.creado_en:
            raise ValueError("actualizado_en cannot precede creado_en")
        if any(c.correlation_id != self.correlation_id for c in self.citas):
            raise ValueError("all citations must belong to the same correlation_id")
        return self


class Veredicto(StrictModel):
    """Rule/audit result. Score and coverage are bounded and code-verifiable."""

    correlation_id: str
    candidato_ref: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")
    estado: VeredictoEstado
    razon: str = Field(min_length=1)
    cobertura: float = Field(ge=0.0, le=1.0)
    puntaje: float | None = Field(default=None, ge=0.0, le=1.0)
    citas: list[CitationRef] = Field(default_factory=list)
    auditoria: AuditMetadata

    _validate_correlation_id = field_validator("correlation_id")(_uuid4_string)

    @model_validator(mode="after")
    def citation_ownership_is_consistent(self) -> Veredicto:
        if any(c.correlation_id != self.correlation_id for c in self.citas):
            raise ValueError("all verdict citations must belong to the same case")
        return self


class PropuestaLista(StrictModel):
    """Immutable-in-use ranking proposal; adjustment creates a new version."""

    correlation_id: str
    vacante_id: str = Field(min_length=1)
    vacante_version: str = Field(min_length=1)
    version: int = Field(ge=1)
    candidatos_ref: list[str] = Field(min_length=1, max_length=6)
    razones: dict[str, str] = Field(min_length=1)
    creada_en: datetime
    auditoria: AuditMetadata

    _validate_correlation_id = field_validator("correlation_id")(_uuid4_string)

    @field_validator("candidatos_ref")
    @classmethod
    def candidate_refs_are_opaque(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("shortlist candidate references must be unique")
        if any(not ref.startswith("cand_") for ref in value):
            raise ValueError("candidate references must be opaque cand_ references")
        return value


class PropuestaAgenda(StrictModel):
    """Scheduling/message proposal with no direct external side effect."""

    correlation_id: str
    vacante_id: str = Field(min_length=1)
    candidato_ref: str = Field(pattern=r"^cand_[A-Za-z0-9_-]+$")
    destinatario_ref: str = Field(min_length=1)
    franja: str = Field(min_length=1)
    texto_exacto: str = Field(min_length=1)
    plantilla_version: str = Field(min_length=1)
    creada_en: datetime
    auditoria: AuditMetadata

    _validate_correlation_id = field_validator("correlation_id")(_uuid4_string)


class AprobacionHumana(StrictModel):
    """Recorded human decision; a timeout is not an approval."""

    tipo: TipoAprobacion
    decision: DecisionHumana
    aprobador: str = Field(min_length=1)
    razon: str = Field(min_length=1)
    timestamp: datetime
    candidatos_ref_ajustados: list[str] | None = None
    texto_exacto_ajustado: str | None = None

    @model_validator(mode="after")
    def adjustment_has_payload(self) -> AprobacionHumana:
        if self.decision is DecisionHumana.AJUSTAR:
            if self.tipo is TipoAprobacion.LISTA_CORTA and not self.candidatos_ref_ajustados:
                raise ValueError("shortlist adjustments require candidate references")
            if self.tipo is TipoAprobacion.MENSAJE_EXACTO and not self.texto_exacto_ajustado:
                raise ValueError("message adjustments require exact text")
        return self


class EstadoSLAInfo(StrictModel):
    """Operational SLA observation; it cannot authorize graph progress."""

    tipo: TipoSLA
    estado: EstadoSLA
    pendiente_desde: datetime
    observado_en: datetime
    recordatorio_en: datetime | None = None
    escalamiento_en: datetime | None = None
    vencimiento_en: datetime | None = None


class EfectoExterno(StrictModel):
    """Receipt for a simulated/external operation, keyed for idempotency."""

    idempotency_key: str = Field(min_length=1)
    operacion: str = Field(min_length=1)
    estado: str = Field(min_length=1)
    resultado_ref: str | None = None
    intentos: int = Field(ge=1)
    ejecutado_en: datetime


class CaseState(StrictModel):
    """Persisted workflow state shared by the graph and integration adapters."""

    correlation_id: str
    vacante_id: str = Field(min_length=1)
    vacante_version: str = Field(min_length=1)
    estado: EstadoCaso = EstadoCaso.RECIBIDO
    razon_parada: RazónParada | None = None
    ficha: FichaCandidato | None = None
    veredicto: Veredicto | None = None
    propuesta_lista: PropuestaLista | None = None
    propuesta_agenda: PropuestaAgenda | None = None
    estado_aprobacion_lista: EstadoAprobacion = EstadoAprobacion.PENDIENTE
    estado_aprobacion_mensaje: EstadoAprobacion = EstadoAprobacion.PENDIENTE
    aprobacion_lista: AprobacionHumana | None = None
    aprobacion_mensaje: AprobacionHumana | None = None
    sla_lista: EstadoSLAInfo | None = None
    sla_mensaje: EstadoSLAInfo | None = None
    efectos_externos: list[EfectoExterno] = Field(default_factory=list)
    creado_en: datetime
    actualizado_en: datetime
    contrato_version: str = CONTRACT_VERSION

    _validate_correlation_id = field_validator("correlation_id")(_uuid4_string)

    @model_validator(mode="after")
    def timestamps_are_coherent(self) -> CaseState:
        if self.actualizado_en < self.creado_en:
            raise ValueError("actualizado_en cannot precede creado_en")
        return self


class EntradaDecisionLog(StrictModel):
    """Append-only audit entry. Hashes are populated by DecisionLog.append."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
        validate_default=True,
        frozen=True,
    )

    correlation_id: str
    tiempo: datetime
    componente: str = Field(min_length=1)
    fuente: list[str] = Field(min_length=1)
    versiones: dict[str, str] = Field(min_length=1)
    razon: str = Field(min_length=1)
    cobertura: float | None = Field(default=None, ge=0.0, le=1.0)
    veredicto: VeredictoEstado | None = None
    aprobador: str | None = None
    estado: EstadoCaso | None = None
    hash_previo: str = "GENESIS"
    hash_entrada: str = Field(min_length=64, max_length=64)

    _validate_correlation_id = field_validator("correlation_id")(_uuid4_string)


CONTRACT_EXAMPLES: dict[str, dict[str, Any]] = {
    "input": {
        "correlation_id": "00000000-0000-4000-8000-000000000001",
        "vacante_id": "vac-demo",
        "vacante_version": "2026-01",
    },
    "output": {
        "estado": EstadoCaso.PENDIENTE_APROBACION_LISTA.value,
        "razon_parada": RazónParada.APROBACION_LISTA_PENDIENTE.value,
        "contrato_version": CONTRACT_VERSION,
    },
}


def example_case_state() -> CaseState:
    """Build a minimal valid input example without real candidate data."""

    now = utc_now()
    return CaseState(
        correlation_id=CONTRACT_EXAMPLES["input"]["correlation_id"],
        vacante_id="vac-demo",
        vacante_version="2026-01",
        creado_en=now,
        actualizado_en=now,
    )


def contract_json_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schemas for the public Role 1 contracts."""

    return {
        name: model.model_json_schema()
        for name, model in {
            "CaseState": CaseState,
            "FichaCandidato": FichaCandidato,
            "Veredicto": Veredicto,
            "PropuestaAgenda": PropuestaAgenda,
            "EntradaDecisionLog": EntradaDecisionLog,
        }.items()
    }


__all__ = [
    "CONTRACT_VERSION",
    "CONTRACT_EXAMPLES",
    "AprobacionHumana",
    "AuditMetadata",
    "CaseState",
    "CitationRef",
    "DecisionHumana",
    "EfectoExterno",
    "EntradaDecisionLog",
    "EstadoAprobacion",
    "EstadoCaso",
    "EstadoSLA",
    "EstadoSLAInfo",
    "FichaCandidato",
    "PropuestaAgenda",
    "PropuestaLista",
    "RazónParada",
    "TipoAprobacion",
    "TipoSLA",
    "Veredicto",
    "VeredictoEstado",
    "contract_json_schemas",
    "example_case_state",
    "utc_now",
]
