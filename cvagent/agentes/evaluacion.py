"""
Banco de evaluación del Rol 3 contra `data/manifiesto.json` (ground truth del Rol 2).

Flujo de punta a punta que mide (el mismo del diseño):
    motor del Rol 2 (R12, R1, R2, R11/R3, R7) → ruta del motor
      └─ solo si es «evaluable»: sanitización + analista + auditor (Rol 3)
           auditor bloquea → «bandeja» · sin objeciones → «ranking»
El manifiesto separa `ruta_motor_reglas` (lo que devuelve el Rol 2) de `ruta_final`
(incluye lo que detectan la sanitización y el auditor del Rol 3).

El manifiesto NUNCA se le entrega a un agente: solo se usa aquí, para medir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .salida import Cumplimiento, FichaCandidato

# Vocabulario del analista → vocabulario del motor del Rol 2 (R3/S5). Pendiente unificar en el contrato v1.1.
A_ESTADO_MOTOR = {
    Cumplimiento.CUMPLE: "cumple",
    Cumplimiento.NO_CUMPLE: "incumple",
    Cumplimiento.SIN_EVIDENCIA: "no_acreditado",
    Cumplimiento.PARCIAL: "por_confirmar",
}


def ruta_final(ruta_motor: str, rol3_bloquea: bool) -> str:
    """Solo lo «evaluable» pasa por el Rol 3. Si la sanitización o el auditor bloquean,
    el caso va a la bandeja de revisión humana; si no, entra al ranking (R4-R6, Rol 2)."""
    if ruta_motor != "evaluable":
        return ruta_motor
    return "bandeja" if rol3_bloquea else "ranking"


def estados_del_analista(ficha: FichaCandidato) -> dict[str, str]:
    """Obligatorios del analista, en el vocabulario del motor, para compararlos con el manifiesto."""
    return {e.id_requisito: A_ESTADO_MOTOR[e.cumplimiento] for e in ficha.evaluaciones if e.obligatorio}


@dataclass
class Comparacion:
    cv_id: str
    ruta_motor_esperada: str
    ruta_motor: str
    ruta_final_esperada: str
    ruta_final: str
    estados_esperados: dict = field(default_factory=dict)
    estados_analista: dict = field(default_factory=dict)
    motivos: list[str] = field(default_factory=list)

    @property
    def acierta_ruta_final(self) -> bool:
        return self.ruta_final == self.ruta_final_esperada

    @property
    def acierta_motor(self) -> bool:
        return self.ruta_motor == self.ruta_motor_esperada

    @property
    def coincidencias_requisitos(self) -> tuple[int, int]:
        """(coinciden, comparados) entre el analista y el estado esperado por requisito."""
        comunes = [k for k in self.estados_esperados if k in self.estados_analista]
        return sum(self.estados_analista[k] == self.estados_esperados[k] for k in comunes), len(comunes)
