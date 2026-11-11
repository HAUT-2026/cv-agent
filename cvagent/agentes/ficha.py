"""
De `FichaLLM` (lo que dijo el modelo) a `FichaCandidato` (lo que entra al estado).

No corrige al modelo: si afirma "cumple" con una cita inventada, la cita queda en
`citas_rechazadas` y la cobertura baja. Decidir si eso bloquea es trabajo del
AUDITOR, no del analista. Si esta función corrigiera, el auditor no tendría nada
independiente que verificar.
"""
from __future__ import annotations

from .criterios import Vacante
from .salida import (
    CitaVerificada, Cumplimiento, EvaluacionRequisito, FichaCandidato, FichaLLM,
    calcular_cobertura, calcular_fit, cumple_obligatorios,
)
from .texto import TextoCanonico, localizar_cita


def construir_ficha(ficha_llm: FichaLLM, tc: TextoCanonico, vacante: Vacante,
                    modelo: str, version_prompt: str) -> FichaCandidato:
    por_id = {r.id: r for r in vacante.requisitos}
    vistos: set[str] = set()
    desconocidos: list[str] = []
    evaluaciones: list[EvaluacionRequisito] = []

    for ev in ficha_llm.evaluaciones:
        req = por_id.get(ev.id_requisito)
        if req is None:
            desconocidos.append(ev.id_requisito)
            continue
        if ev.id_requisito in vistos:   # duplicado: se queda la primera evaluación
            continue
        vistos.add(ev.id_requisito)

        ok, rechazadas = [], []
        for cita in ev.citas:
            loc = localizar_cita(tc, cita)
            if loc is None:
                rechazadas.append(cita)
            else:
                ok.append(CitaVerificada(texto=loc.texto_real, inicio=loc.inicio, fin=loc.fin,
                                         campo=loc.campo, metodo=loc.metodo, similitud=loc.similitud))
        evaluaciones.append(EvaluacionRequisito(
            id_requisito=req.id, obligatorio=req.obligatorio, peso=req.peso,
            cumplimiento=ev.cumplimiento, citas=ok, citas_rechazadas=rechazadas))

    # Requisitos que el modelo no evaluó: se registran como sin evidencia (fail-closed)
    omitidos = [r.id for r in vacante.requisitos if r.id not in vistos]
    for rid in omitidos:
        r = por_id[rid]
        evaluaciones.append(EvaluacionRequisito(
            id_requisito=rid, obligatorio=r.obligatorio, peso=r.peso,
            cumplimiento=Cumplimiento.SIN_EVIDENCIA))

    orden = {r.id: i for i, r in enumerate(vacante.requisitos)}
    evaluaciones.sort(key=lambda e: orden[e.id_requisito])

    return FichaCandidato(
        id_cv=tc.id_cv, id_vacante=vacante.id_vacante, version_vacante=vacante.version,
        evaluaciones=evaluaciones,
        fit=calcular_fit(evaluaciones),
        cumple_obligatorios=cumple_obligatorios(evaluaciones),
        cobertura_evidencia=calcular_cobertura(evaluaciones),
        requisitos_omitidos=omitidos, requisitos_desconocidos=desconocidos,
        modelo=modelo, version_prompt=version_prompt,
    )
