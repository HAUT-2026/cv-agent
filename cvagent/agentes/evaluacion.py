"""
Banco de evaluación contra el manifiesto del equipo (ground truth del Rol 2).

IMPORTANTE: la "decisión provisional" de aquí NO es la decisión del sistema. La
oficial sale del motor de reglas (Rol 2) + auditor (Rol 3) + humano. Esta
heurística existe solo para poder medir el analista contra el manifiesto mientras
esas piezas no existen, y sigue los principios del repo: nunca descartar por falta
de evidencia, y ante duda, revisión humana (fail-closed).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .criterios import Vacante
from .salida import Cumplimiento, FichaCandidato


@dataclass
class Comparacion:
    cv_id: str
    decision_esperada: str
    decision_provisional: str
    fallidos_esperados: list[str]
    fallidos_analista: list[str]          # obligatorios que el analista marcó no_cumple
    meses_esperados: int
    meses_calculados: int
    debe_marcar: list[str]
    marcas: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)

    @property
    def acierta_decision(self) -> bool:
        return self.decision_esperada == self.decision_provisional

    @property
    def acierta_fallidos(self) -> bool:
        return sorted(self.fallidos_esperados) == sorted(self.fallidos_analista)

    @property
    def acierta_meses(self) -> bool:
        return self.meses_esperados == self.meses_calculados

    @property
    def acierta_marcas(self) -> bool:
        return ("inyeccion" in self.debe_marcar) == ("inyeccion" in self.marcas)


def decision_provisional(ficha: FichaCandidato, vacante: Vacante, experiencia: dict,
                         auditor_bloquea: bool) -> tuple[str, list[str]]:
    """apto | no_apto | revision_humana, con los motivos. Ver advertencia del módulo.
    Si el auditor bloquea, el caso va a revisión humana (salvo que ya sea no_apto)."""
    reqs = {r.id: r for r in vacante.requisitos}
    motivos: list[str] = []
    no_apto, revision = False, auditor_bloquea
    if auditor_bloquea:
        motivos.append("el auditor bloquea → revisión humana")

    for e in ficha.evaluaciones:
        r = reqs[e.id_requisito]
        if not r.obligatorio:
            continue
        estado = e.cumplimiento
        # Años: decide el cálculo determinista (R11), no el juicio del LLM
        if r.anios_minimos is not None:
            meses, minimo = experiencia["total_meses_sin_solapes"], int(r.anios_minimos * 12)
            if meses >= minimo:
                estado = Cumplimiento.CUMPLE
            else:
                otros = sum(experiencia.get("meses_que_no_cuentan", {}).get(t, 0)
                            for t in ("pasantia", "voluntariado"))
                if meses + otros >= minimo:
                    motivos.append(f"{r.id}: {meses} meses; alcanza solo contando pasantía/voluntariado → revisión")
                    revision = True
                    continue
                estado = Cumplimiento.NO_CUMPLE
        if estado == Cumplimiento.NO_CUMPLE:
            if r.nota and "revisión humana" in r.nota.lower():
                motivos.append(f"{r.id}: no_cumple, pero la vacante exige revisión humana en este caso")
                revision = True
            else:
                motivos.append(f"{r.id}: no_cumple (oblig.)")
                no_apto = True
        elif estado in (Cumplimiento.SIN_EVIDENCIA, Cumplimiento.PARCIAL):
            motivos.append(f"{r.id}: {estado.value} (oblig.) → revisión (R3/R4: falta de evidencia no es incumplimiento)")
            revision = True

    if ficha.cobertura_evidencia < 0.70:
        motivos.append(f"cobertura {ficha.cobertura_evidencia:.2f} < 0,70 (R4) → revisión")
        revision = True
    if no_apto:
        return "no_apto", motivos
    return ("revision_humana" if revision else "apto"), motivos


def fallidos_del_analista(ficha: FichaCandidato) -> list[str]:
    return [e.id_requisito for e in ficha.evaluaciones
            if e.obligatorio and e.cumplimiento == Cumplimiento.NO_CUMPLE]
