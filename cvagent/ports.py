"""Replaceable interfaces for Roles 2, 3 and 4.

The workflow owns transitions and approvals. These protocols only create or
inspect artifacts; they do not authorize external effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .contracts import (
    AuditMetadata,
    CaseState,
    FichaCandidato,
    PropuestaAgenda,
    PropuestaLista,
    Veredicto,
    VeredictoEstado,
)


class AnalistaPort(Protocol):
    def crear_ficha(self, state: CaseState, *, now: datetime) -> FichaCandidato:
        """Return a minimized ficha with verifiable citations."""


class MotorReglasPort(Protocol):
    def evaluar(self, ficha: FichaCandidato, *, now: datetime) -> Veredicto:
        """Return a deterministic, versioned rule result."""

    def crear_propuesta_lista(
        self, ficha: FichaCandidato, veredicto: Veredicto, *, now: datetime
    ) -> PropuestaLista:
        """Return a versioned shortlist proposal, never a final decision."""


class AuditorPort(Protocol):
    def auditar(self, ficha: FichaCandidato, veredicto: Veredicto) -> Veredicto:
        """Approve or block an artifact; cannot approve a human action."""


class AgendadorPort(Protocol):
    def proponer(
        self, state: CaseState, propuesta: PropuestaLista, *, now: datetime
    ) -> PropuestaAgenda:
        """Prepare a template-bound message without accessing raw CV content."""


class EnvioPort(Protocol):
    def enviar(self, propuesta: PropuestaAgenda, *, idempotency_key: str) -> str:
        """Perform one simulated/external effect under an idempotency key."""


@dataclass(frozen=True)
class RoleAdapters:
    """All Role 2–4 dependencies are explicit and easy to replace."""

    analista: AnalistaPort
    motor_reglas: MotorReglasPort
    auditor: AuditorPort
    agendador: AgendadorPort
    envio: EnvioPort


class SyntheticRole2Analyzer:
    """Synthetic Role 2 adapter; it contains no extraction or LLM logic."""

    def crear_ficha(self, state: CaseState, *, now: datetime) -> FichaCandidato:
        text = "Perfil sintético con experiencia declarada en Python."
        start = text.index("Python")
        correlation_id = state.correlation_id
        from .contracts import CitationRef

        citation = CitationRef(
            correlation_id=correlation_id,
            fuente="cv-sintetico.txt",
            cita="Python",
            offset_inicio=start,
            offset_fin=start + len("Python"),
        )
        return FichaCandidato(
            correlation_id=correlation_id,
            candidato_ref="cand_demo",
            vacante_id=state.vacante_id,
            vacante_version=state.vacante_version,
            resumen="Perfil sintético con evidencia de Python.",
            citas=[citation.verify_against(text)],
            creado_en=now,
            actualizado_en=now,
            auditoria=AuditMetadata(
                componente="rol-2-double-analista",
                fuente=["cv-sintetico.txt"],
                versiones={"vacante": state.vacante_version, "esquema": "1.0.0"},
                timestamp=now,
                modelo_version="double",
                prompt_version="double",
                esquema_version="1.0.0",
            ),
        )


class SyntheticRuleEngine:
    """Synthetic Role 3 adapter; real R1–R13 rules remain out of Role 1."""

    def evaluar(self, ficha: FichaCandidato, *, now: datetime) -> Veredicto:
        return Veredicto(
            correlation_id=ficha.correlation_id,
            candidato_ref=ficha.candidato_ref,
            estado=VeredictoEstado.APROBADO,
            razon="Resultado sintético para integración; no representa reglas R1–R13.",
            cobertura=0.9,
            puntaje=0.85,
            citas=ficha.citas,
            auditoria=AuditMetadata(
                componente="rol-3-double-reglas",
                fuente=["motor-reglas-sintetico"],
                versiones={"vacante": ficha.vacante_version, "reglas": "double"},
                timestamp=now,
            ),
        )

    def crear_propuesta_lista(
        self, ficha: FichaCandidato, veredicto: Veredicto, *, now: datetime
    ) -> PropuestaLista:
        return PropuestaLista(
            correlation_id=ficha.correlation_id,
            vacante_id=ficha.vacante_id,
            vacante_version=ficha.vacante_version,
            version=1,
            candidatos_ref=[ficha.candidato_ref],
            razones={ficha.candidato_ref: veredicto.razon},
            creada_en=now,
            auditoria=AuditMetadata(
                componente="rol-3-double-ranking",
                fuente=["veredicto-sintetico"],
                versiones={"vacante": ficha.vacante_version, "reglas": "double"},
                timestamp=now,
            ),
        )


class SyntheticAuditor:
    """Synthetic Role 3 auditor that passes already-valid synthetic evidence."""

    def auditar(self, ficha: FichaCandidato, veredicto: Veredicto) -> Veredicto:
        return veredicto


class SyntheticScheduler:
    """Synthetic Role 4 scheduler; the text is still approval-gated."""

    def proponer(
        self, state: CaseState, propuesta: PropuestaLista, *, now: datetime
    ) -> PropuestaAgenda:
        return PropuestaAgenda(
            correlation_id=state.correlation_id,
            vacante_id=state.vacante_id,
            candidato_ref=propuesta.candidatos_ref[0],
            destinatario_ref="recipient-demo",
            franja="2026-12-01T10:00:00Z/2026-12-01T10:30:00Z",
            texto_exacto="Mensaje sintético pendiente de aprobación humana.",
            plantilla_version="demo-1",
            creada_en=now,
            auditoria=AuditMetadata(
                componente="rol-4-double-agendador",
                fuente=["plantilla-sintetica"],
                versiones={"vacante": state.vacante_version, "plantilla": "demo-1"},
                timestamp=now,
            ),
        )


def synthetic_adapters() -> RoleAdapters:
    """Return explicit MVP doubles for all non-Role-1 responsibilities."""

    from .operations import SimulatedDeliveryGateway

    return RoleAdapters(
        analista=SyntheticRole2Analyzer(),
        motor_reglas=SyntheticRuleEngine(),
        auditor=SyntheticAuditor(),
        agendador=SyntheticScheduler(),
        envio=SimulatedDeliveryGateway(),
    )


__all__ = [
    "AgendadorPort",
    "AnalistaPort",
    "AuditorPort",
    "EnvioPort",
    "MotorReglasPort",
    "RoleAdapters",
    "SyntheticAuditor",
    "SyntheticRole2Analyzer",
    "SyntheticRuleEngine",
    "SyntheticScheduler",
    "synthetic_adapters",
]
