"""Rol 3 · vacante versionada y decisión provisional del banco de evaluación (sin LLM)."""
from cvagent.agentes.evaluacion import decision_provisional
from cvagent.agentes.salida import CitaVerificada, Cumplimiento, EvaluacionRequisito, FichaCandidato
from rol3_comun import VACANTE

EXP_OK = {"total_meses_sin_solapes": 40, "meses_que_no_cuentan": {}}


def _ficha(estados=None, cobertura=1.0):
    estados = estados or {}
    evs = []
    for r in VACANTE.requisitos:
        est = estados.get(r.id, Cumplimiento.CUMPLE)
        citas = [] if est == Cumplimiento.SIN_EVIDENCIA else [
            CitaVerificada(texto="x", inicio=0, fin=1, campo=None, metodo="exacta", similitud=1.0)]
        evs.append(EvaluacionRequisito(id_requisito=r.id, obligatorio=r.obligatorio, peso=r.peso,
                                       cumplimiento=est, citas=citas))
    return FichaCandidato(id_cv="CV-000", id_vacante="VAC-001", version_vacante=1, evaluaciones=evs, fit=1.0,
                          cumple_obligatorios=True, cobertura_evidencia=cobertura, modelo="t", version_prompt="t")


def test_vacante_se_convierte_sin_perder_criterios():
    assert len(VACANTE.requisitos) == 10 and sum(r.obligatorio for r in VACANTE.requisitos) == 5
    assert "T-SQL" in next(r for r in VACANTE.requisitos if r.id == "REQ-02").equivalencias
    assert next(r for r in VACANTE.requisitos if r.id == "REQ-05").nivel_minimo == "B2"


def test_apto_y_inyeccion():
    assert decision_provisional(_ficha(), VACANTE, EXP_OK, False)[0] == "apto"
    assert decision_provisional(_ficha(), VACANTE, EXP_OK, True)[0] == "revision_humana"


def test_sin_evidencia_en_obligatorio_es_revision_no_descarte():
    assert decision_provisional(_ficha({"REQ-02": Cumplimiento.SIN_EVIDENCIA}), VACANTE, EXP_OK, False)[0] == "revision_humana"


def test_anios_los_decide_el_calculo_no_el_llm():
    f = _ficha()
    assert decision_provisional(f, VACANTE, {"total_meses_sin_solapes": 25, "meses_que_no_cuentan": {"pasantia": 6}}, False)[0] == "no_apto"
    assert decision_provisional(f, VACANTE, {"total_meses_sin_solapes": 23, "meses_que_no_cuentan": {"voluntariado": 51}}, False)[0] == "revision_humana"


def test_titulo_con_nota_de_revision_y_idioma():
    assert decision_provisional(_ficha({"REQ-04": Cumplimiento.NO_CUMPLE}), VACANTE, EXP_OK, False)[0] == "revision_humana"
    assert decision_provisional(_ficha({"REQ-05": Cumplimiento.NO_CUMPLE}), VACANTE, EXP_OK, False)[0] == "no_apto"
