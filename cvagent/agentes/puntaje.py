"""Puntaje y cobertura de un CV, calculados por CÓDIGO (nunca por el LLM).

Produce exactamente lo que espera `reglas.motor.armar_staging` del Rol 2:
    {cv_id, puntaje, cobertura, contradiccion_material}
más un desglose por criterio para el decision_log y la bandeja. Las reglas están en
`rubrica.py` y la explicación en docs/rol-3-puntaje.md.

Entradas:
  ficha            FichaCandidato del analista (estados y citas verificadas por requisito)
  resultado_motor  salida de reglas.motor.evaluar_caso/procesar_lote para ese CV (R11 y R3)
  vacante          Vacante (Rol 3) de la misma versión
  diccionario      diccionario de equivalencias del Rol 2 (pesos de equivalencia, p. ej. Kotlin 0,9)
  veredicto        opcional: Veredicto del auditor (para «contradicción material»)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Optional

from . import rubrica as R
from .criterios import Vacante
from .salida import Cumplimiento, FichaCandidato, Severidad, TipoHallazgo, Veredicto

# Advertencias del auditor que significan que la ficha se contradice a sí misma (R4: contradicción
# material → revisión humana, aunque la cobertura alcance).
_CONTRADICCIONES = {TipoHallazgo.ESTADO_INCOHERENTE, TipoHallazgo.NIVEL_IDIOMA_INCOHERENTE}


@dataclass
class Criterio:
    id: str                    # id del requisito o "R11" para la experiencia
    dimension: str
    peso: float                # peso efectivo dentro del puntaje total (suman 1)
    estado: str                # estado del analista, o "calculado" para R11
    valor: Optional[float]     # None = sin_evidencia (no suma, baja la cobertura)
    motivo: str


@dataclass
class Puntaje:
    cv_id: str
    puntaje: float
    cobertura: float
    contradiccion_material: bool
    criterios: list[Criterio] = field(default_factory=list)
    version_rubrica: str = R.VERSION_RUBRICA

    def para_staging(self) -> dict:
        """El formato exacto de reglas.motor.armar_staging."""
        return {"cv_id": self.cv_id, "puntaje": self.puntaje, "cobertura": self.cobertura,
                "contradiccion_material": self.contradiccion_material}

    def a_dict(self) -> dict:
        return asdict(self)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def factor_equivalencia(req_experiencia, texto_cv: str, diccionario: dict) -> float:
    """Peso del término equivalente con el que se acreditó la experiencia (Kotlin → 0,9).
    Si el CV menciona el término principal (peso 1,0), el factor es 1."""
    terminos = (diccionario or {}).get("equivalencias", {}).get(req_experiencia.concepto or "", [])
    tn = _norm(texto_cv)
    presentes = [t["peso"] for t in terminos
                 if re.search(rf"(?<![a-z0-9]){re.escape(_norm(t['termino']))}(?![a-z0-9])", tn)]
    return max(presentes) if presentes else 1.0


def calcular_puntaje(ficha: FichaCandidato, resultado_motor: dict, vacante: Vacante,
                     diccionario: Optional[dict] = None, veredicto: Optional[Veredicto] = None,
                     texto_cv: str = "") -> Puntaje:
    if ficha.id_cv != resultado_motor.get("cv_id", ficha.id_cv):
        raise ValueError(f"La ficha es de {ficha.id_cv} y el resultado del motor de {resultado_motor.get('cv_id')}")
    evals = {e.id_requisito: e for e in ficha.evaluaciones}
    deseables = [r for r in vacante.requisitos if not r.obligatorio]
    req_exp = next((r for r in vacante.requisitos
                    if r.obligatorio and getattr(r.tipo, "value", r.tipo) == "experiencia"), None)

    # Dimensiones que esta vacante sí define (decisión 1)
    por_dim: dict[str, list] = {}
    for r in deseables:
        dim = R.DIMENSION_DE_DESEABLE.get(getattr(r.tipo, "value", r.tipo))
        if dim:
            por_dim.setdefault(dim, []).append(r)
    presentes = set(por_dim) | ({"experiencia"} if req_exp else set())
    pesos = R.pesos_efectivos(presentes)

    criterios: list[Criterio] = []
    # Deseables: cada uno pesa lo mismo dentro de su dimensión
    for dim, reqs in por_dim.items():
        for r in reqs:
            w = pesos[dim] / len(reqs)
            ev = evals.get(r.id)
            estado = ev.cumplimiento.value if ev else "sin_evidencia"
            if ev is None or ev.cumplimiento == Cumplimiento.SIN_EVIDENCIA:
                criterios.append(Criterio(r.id, dim, w, estado, None, "sin evidencia en el CV: no suma"))
            elif ev.cumplimiento == Cumplimiento.CUMPLE and ev.citas and \
                    all((c.campo or "").startswith("habilidades[") for c in ev.citas):
                criterios.append(Criterio(r.id, dim, w, estado, R.VALOR["cumple_solo_lista"],
                                          "cumple, pero solo con la lista de habilidades (evidencia débil)"))
            else:
                criterios.append(Criterio(r.id, dim, w, estado, R.VALOR[estado], f"valoración de «{estado}»"))

    # Profundidad de experiencia: R11 del motor del Rol 2 (decisión 4)
    if req_exp:
        det = (resultado_motor.get("reglas", {}).get("R3", {}).get("detalle", {}).get(req_exp.id, {}))
        meses = det.get("meses_relevantes", resultado_motor.get("meses_efectivos"))
        minimo = int((req_exp.anios_minimos or 0) * 12) or 12
        if meses is None:
            criterios.append(Criterio("R11", "experiencia", pesos["experiencia"], "sin_dato", None,
                                      "el motor no reportó meses efectivos"))
        else:
            factor = factor_equivalencia(req_exp, texto_cv, diccionario) if det.get("por_equivalencia") else 1.0
            v = R.valor_experiencia(meses, minimo, factor)
            criterios.append(Criterio("R11", "experiencia", pesos["experiencia"], "calculado", v,
                                      f"{meses} meses efectivos (mínimo {minimo})"
                                      + (f" · por equivalencia ×{factor}" if factor != 1.0 else "")))

    # Agregación sobre el total (decisión 2) y cobertura ponderada (R4)
    puntaje = sum(c.peso * c.valor for c in criterios if c.valor is not None)
    cobertura = sum(c.peso for c in criterios if c.valor is not None)
    contradiccion = bool(veredicto and any(h.tipo in _CONTRADICCIONES and h.severidad == Severidad.ADVERTENCIA
                                           for h in veredicto.hallazgos))
    return Puntaje(ficha.id_cv, round(puntaje, 4), round(cobertura, 4), contradiccion, criterios)
