"""Rol 3 · vacante versionada, ruta final y comparación con el manifiesto (sin LLM)."""
import pytest

from cvagent.agentes.evaluacion import A_ESTADO_MOTOR, Comparacion, estados_del_analista, ruta_final
from cvagent.agentes.salida import CitaVerificada, Cumplimiento, EvaluacionRequisito, FichaCandidato
from rol3_comun import IDS, MANIFIESTO, VACANTE


def _ficha(estados=None):
    estados = estados or {}
    evs = []
    for r in VACANTE.requisitos:
        est = estados.get(r.id, Cumplimiento.CUMPLE)
        citas = [] if est == Cumplimiento.SIN_EVIDENCIA else [
            CitaVerificada(texto="x", inicio=0, fin=1, campo=None, metodo="exacta", similitud=1.0)]
        evs.append(EvaluacionRequisito(id_requisito=r.id, obligatorio=r.obligatorio, peso=r.peso,
                                       cumplimiento=est, citas=citas))
    return FichaCandidato(id_cv="CV-000", id_vacante="VAC-001", version_vacante=1, evaluaciones=evs, fit=1.0,
                          cumple_obligatorios=True, cobertura_evidencia=1.0, modelo="t", version_prompt="t")


def test_vacante_versionada_y_diccionario_sin_perder_criterios():
    assert VACANTE.version == 1                                         # la v2 es borrador sin aprobar (R13)
    assert len(VACANTE.requisitos) == 10 and sum(r.obligatorio for r in VACANTE.requisitos) == 5
    req = {r.id: r for r in VACANTE.requisitos}
    assert "Postgres" in req["REQ-02"].equivalencias and "Kotlin" in req["REQ-01"].equivalencias
    assert req["REQ-05"].nivel_minimo == "B2" and req["REQ-01"].anios_minimos == 3
    assert "Ingeniería de Sistemas" in req["REQ-04"].titulos_aceptados


def test_ruta_final_solo_cambia_lo_evaluable():
    assert ruta_final("evaluable", False) == "ranking"
    assert ruta_final("evaluable", True) == "bandeja"
    for r in ["bandeja", "no_apto_declarado", "duplicado", "en_espera_consentimiento", "carga_manual"]:
        assert ruta_final(r, False) == r and ruta_final(r, True) == r     # el Rol 3 nunca saca de la bandeja


@pytest.mark.parametrize("cv_id", IDS)
def test_manifiesto_es_coherente_con_ruta_final(cv_id):
    e = MANIFIESTO[cv_id]["esperado"]
    marca = "inyeccion" in e["debe_marcar"]
    assert ruta_final(e["ruta_motor_reglas"], marca) == e["ruta_final"]


def test_vocabulario_del_motor_cubre_todos_los_estados():
    assert set(A_ESTADO_MOTOR) == set(Cumplimiento)
    assert set(A_ESTADO_MOTOR.values()) == {"cumple", "incumple", "no_acreditado", "por_confirmar"}


def test_estados_del_analista_solo_obligatorios():
    est = estados_del_analista(_ficha({"REQ-05": Cumplimiento.PARCIAL, "DES-01": Cumplimiento.NO_CUMPLE}))
    assert set(est) == {r.id for r in VACANTE.requisitos if r.obligatorio}
    assert est["REQ-05"] == "por_confirmar" and est["REQ-01"] == "cumple"


def test_comparacion_cuenta_aciertos():
    c = Comparacion("CV-001", "evaluable", "evaluable", "ranking", "ranking",
                    {"REQ-01": "cumple", "REQ-05": "cumple"}, {"REQ-01": "cumple", "REQ-05": "por_confirmar"})
    assert c.acierta_ruta_final and c.acierta_motor and c.coincidencias_requisitos == (1, 2)
