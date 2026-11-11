"""
Esquemas de SALIDA de los tres agentes (Rol 3).

Separación clave: el LLM llena un esquema PEQUEÑO, solo con enumeraciones y citas
literales (`FichaLLM`). El código lo convierte en el objeto del contrato
(`FichaCandidato`): ubica offsets y calcula el fit y la cobertura. Así:
  - lo que decide el modelo es poco y verificable,
  - lo numérico es determinista y se puede explicar línea por línea.

NOTA: los nombres deben coincidir con el archivo de contratos del Rol 1.
Si difieren, se ajusta aquí y no allá (regla del archivo sagrado).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ESTRICTO = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ enumeraciones
class Cumplimiento(str, Enum):
    CUMPLE = "cumple"
    PARCIAL = "parcial"
    NO_CUMPLE = "no_cumple"          # hay evidencia de que NO cumple
    SIN_EVIDENCIA = "sin_evidencia"  # el CV no dice nada: NO es lo mismo que no cumple


VALOR_CUMPLIMIENTO = {
    Cumplimiento.CUMPLE: 1.0,
    Cumplimiento.PARCIAL: 0.5,
    Cumplimiento.NO_CUMPLE: 0.0,
    Cumplimiento.SIN_EVIDENCIA: 0.0,
}


class ResultadoAuditoria(str, Enum):
    """El auditor puede bloquear, NO aprobar (AGENTS.md): sin objeciones ≠ aprobado.
    La aprobación es siempre humana."""
    SIN_OBJECIONES = "sin_objeciones"
    BLOQUEA = "bloquea"


class Severidad(str, Enum):
    BLOQUEANTE = "bloqueante"
    ADVERTENCIA = "advertencia"


class TipoHallazgo(str, Enum):
    # capa determinista (auditor.py)
    CITA_NO_ENCONTRADA = "cita_no_encontrada"            # el LLM citó algo que no está en el CV
    CITA_CRUZA_CAMPOS = "cita_cruza_campos"
    AFIRMACION_SIN_CITA = "afirmacion_sin_cita"          # afirma y ninguna cita sobrevivió a la verificación
    REQUISITO_OMITIDO = "requisito_omitido"
    REQUISITO_DESCONOCIDO = "requisito_desconocido"      # evaluó un id que no existe en la vacante
    COBERTURA_INSUFICIENTE = "cobertura_insuficiente"    # R4
    INDICIO_INYECCION = "indicio_inyeccion"
    CITA_SIN_RELACION = "cita_sin_relacion"              # la cita no comparte términos con el requisito
    EVIDENCIA_SOLO_LISTA = "evidencia_solo_lista"        # "cumple" respaldado solo por la lista de habilidades
    CALIFICADOR_DEBIL = "calificador_debil"              # "cumple" con "básico", "en curso"…
    ESTADO_INCOHERENTE = "estado_incoherente"            # p. ej. estudios "en curso" marcados no_cumple
    NIVEL_IDIOMA_INCOHERENTE = "nivel_idioma_incoherente"  # nivel citado vs. nivel mínimo
    CITA_CON_PROXY = "cita_con_proxy"                    # la evidencia usada contiene un proxy de R7
    # capa LLM (Parte 5)
    SENAL_SESGO = "senal_sesgo"
    INYECCION_SUTIL = "inyeccion_sutil"
    CITA_NO_SOPORTA = "cita_no_soporta"  # la cita existe pero no respalda la afirmación


# ------------------------------------------------------- lo que devuelve el LLM
class EvaluacionLLM(BaseModel):
    model_config = _ESTRICTO
    id_requisito: str
    cumplimiento: Cumplimiento
    citas: list[str] = Field(default_factory=list, max_length=3,
                             description="Fragmentos COPIADOS LITERALMENTE del CV")

    @model_validator(mode="after")
    def _citas_coherentes(self):
        for c in self.citas:
            if len(c) > 300:
                raise ValueError("una cita no puede superar 300 caracteres: citar no es copiar el CV")
        if self.cumplimiento == Cumplimiento.SIN_EVIDENCIA and self.citas:
            raise ValueError(f"{self.id_requisito}: sin_evidencia no lleva citas. Si hay una frase "
                             "relacionada en el CV, califica con ella (cumple, parcial o no_cumple)")
        if self.cumplimiento != Cumplimiento.SIN_EVIDENCIA and not self.citas:
            raise ValueError(f"{self.id_requisito}: '{self.cumplimiento.value}' exige al menos una cita "
                             "literal del CV. Si el CV no dice nada relacionado, usa sin_evidencia")
        return self


class FichaLLM(BaseModel):
    """Esquema que se le entrega al modelo como salida estructurada. Sin texto libre."""
    model_config = _ESTRICTO
    evaluaciones: list[EvaluacionLLM]

    @model_validator(mode="after")
    def _sin_duplicados(self):
        ids = [e.id_requisito for e in self.evaluaciones]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"requisitos evaluados más de una vez: {repetidos}. "
                             "Une sus citas en una sola evaluación por requisito")
        return self


# ----------------------------------------------- lo que viaja en el CaseState
class CitaVerificada(BaseModel):
    model_config = _ESTRICTO
    texto: str                 # texto real del CV en [inicio, fin)
    inicio: int = Field(ge=0)
    fin: int = Field(gt=0)
    campo: Optional[str]
    metodo: str                # exacta | normalizada | aproximada
    similitud: float


class EvaluacionRequisito(BaseModel):
    model_config = _ESTRICTO
    id_requisito: str
    obligatorio: bool
    peso: float
    cumplimiento: Cumplimiento
    citas: list[CitaVerificada] = Field(default_factory=list)
    citas_rechazadas: list[str] = Field(default_factory=list)  # pedidas por el LLM y no halladas


class FichaCandidato(BaseModel):
    """Salida del analista según el contrato del día 1."""
    model_config = _ESTRICTO
    id_cv: str
    id_vacante: str
    version_vacante: int
    evaluaciones: list[EvaluacionRequisito]
    fit: float = Field(ge=0, le=1)
    cumple_obligatorios: bool
    cobertura_evidencia: float = Field(ge=0, le=1)
    requisitos_omitidos: list[str] = Field(default_factory=list)      # el LLM no los evaluó
    requisitos_desconocidos: list[str] = Field(default_factory=list)  # el LLM inventó ids
    modelo: str                # proveedor:modelo, va al decision_log
    version_prompt: str


class Hallazgo(BaseModel):
    model_config = _ESTRICTO
    tipo: TipoHallazgo
    severidad: Severidad
    id_requisito: Optional[str] = None
    inicio: Optional[int] = None   # offset cuando aplica (en el texto canónico, salvo que `campo` diga otra fuente)
    fin: Optional[int] = None
    campo: Optional[str] = None    # ruta del campo, o "texto_oculto" si el offset es relativo a ese campo
    detalle: Optional[str] = Field(default=None, max_length=240)   # lo genera el CÓDIGO, nunca el LLM


class Veredicto(BaseModel):
    """Salida del auditor: pasa o bloquea, con hallazgos que apuntan a offsets."""
    model_config = _ESTRICTO
    id_cv: str
    resultado: ResultadoAuditoria
    hallazgos: list[Hallazgo] = Field(default_factory=list)
    cobertura_evidencia: float = Field(ge=0, le=1)
    capas_ejecutadas: list[str]    # ["determinista"] o ["determinista", "llm"]

    @model_validator(mode="after")
    def _coherencia(self):
        hay_bloqueante = any(h.severidad == Severidad.BLOQUEANTE for h in self.hallazgos)
        if hay_bloqueante and self.resultado != ResultadoAuditoria.BLOQUEA:
            raise ValueError("hay hallazgos bloqueantes pero el veredicto no bloquea")
        if not hay_bloqueante and self.resultado == ResultadoAuditoria.BLOQUEA:
            raise ValueError("bloquea sin ningún hallazgo bloqueante: el bloqueo debe ser explicable")
        return self


class Franja(BaseModel):
    model_config = _ESTRICTO
    inicio: datetime
    fin: datetime

    @model_validator(mode="after")
    def _orden(self):
        if self.fin <= self.inicio:
            raise ValueError("franja con fin anterior o igual al inicio")
        return self


class PropuestaAgenda(BaseModel):
    """Salida del agendador: franjas más mensaje construido sobre plantilla."""
    model_config = _ESTRICTO
    id_cv: str
    franjas: list[Franja] = Field(min_length=1, max_length=3)
    id_plantilla: str
    borrador_mensaje: str


# ----------------------------------------------------------- cálculos deterministas
def calcular_fit(evaluaciones: list[EvaluacionRequisito]) -> float:
    total = sum(e.peso for e in evaluaciones)
    if total == 0:
        return 0.0
    return round(sum(e.peso * VALOR_CUMPLIMIENTO[e.cumplimiento] for e in evaluaciones) / total, 4)


def calcular_cobertura(evaluaciones: list[EvaluacionRequisito]) -> float:
    """De lo que el analista AFIRMA (cumple o parcial), qué fracción tiene al menos
    una cita verificada. Si no afirma nada, la cobertura es 1 (no hay nada que respaldar)."""
    afirmadas = [e for e in evaluaciones if e.cumplimiento in (Cumplimiento.CUMPLE, Cumplimiento.PARCIAL)]
    if not afirmadas:
        return 1.0
    return round(sum(1 for e in afirmadas if e.citas) / len(afirmadas), 4)


def cumple_obligatorios(evaluaciones: list[EvaluacionRequisito]) -> bool:
    return all(e.cumplimiento in (Cumplimiento.CUMPLE, Cumplimiento.PARCIAL)
               for e in evaluaciones if e.obligatorio)
