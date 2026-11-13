"""Rol 3 · puntaje y cobertura (rúbrica provisional) → staging del Rol 2. Sin LLM.

El «analista simulado» marca cumple todo requisito para el que frases_relacionadas encuentra
evidencia (acierta 28/28 deseables del manifiesto) y lo cita literal; así se prueba el cálculo
y el Top 5 de punta a punta sin depender de un modelo."""
import json

import pytest

from cvagent.agentes import rubrica as R
from cvagent.agentes.auditor import auditar
from cvagent.agentes.evaluacion import ficha_lexica
from cvagent.agentes.herramientas import REGISTRO
from cvagent.agentes.puntaje import calcular_puntaje
from reglas import cargar_diccionario, cargar_vacante as cargar_vacante_rol2
from reglas.motor import armar_staging, evaluar_caso, procesar_lote
from rol3_comun import DATA, IDS, MANIFIESTO, VACANTE, caso, contexto, ruta_json

DIC = cargar_diccionario(str(DATA / "diccionario_equivalencias.json"))
_V2 = cargar_vacante_rol2(str(DATA), "VAC-001", VACANTE.version)
_LOTE = [i for i in IDS if MANIFIESTO[i].get("grupo") != "extra_inyeccion"]
MOTOR = procesar_lote([json.loads(ruta_json(i).read_text("utf-8")) for i in _LOTE], _V2, DIC)
for _i in IDS:
    MOTOR.setdefault(_i, evaluar_caso(json.loads(ruta_json(_i).read_text("utf-8")), _V2, DIC))
EN_RANKING = [i for i in IDS if MANIFIESTO[i]["esperado"]["ruta_final"] == "ranking"]


def ficha_simulada(cv_id, cambios=None):
    c = caso(cv_id)
    evs, construir = ficha_lexica(c, VACANTE)
    for e in evs:
        if cambios and e["id_requisito"] in cambios:
            e["cumplimiento"], e["citas"] = cambios[e["id_requisito"]]
    return c, construir(evs)


def puntaje(cv_id, cambios=None, veredicto=False):
    c, f = ficha_simulada(cv_id, cambios)
    v = auditar(f, c, VACANTE) if veredicto else None
    return calcular_puntaje(f, MOTOR[cv_id], VACANTE, DIC, v, c.texto.texto)


# ------------------------------------------------------------------ la rúbrica
def test_resultados_se_reparte_en_proporcion():
    p = R.pesos_efectivos({"tecnicas", "experiencia", "complementarias"})
    assert p == pytest.approx({"tecnicas": 0.5, "experiencia": 0.375, "complementarias": 0.125})
    assert sum(c.peso for c in puntaje("CV-001").criterios) == pytest.approx(1.0)


@pytest.mark.parametrize("meses,valor", [(36, 0.5), (47, 0.5), (48, 0.75), (71, 0.75), (72, 1.0), (120, 1.0)])
def test_tramos_de_experiencia(meses, valor):
    assert R.valor_experiencia(meses, 36) == valor


def test_equivalencia_kotlin_multiplica_por_el_peso_del_diccionario():
    exp = next(c for c in puntaje("CV-014").criterios if c.id == "R11")
    assert exp.valor == pytest.approx(0.75 * 0.9) and "×0.9" in exp.motivo      # 48 meses, Kotlin


# ------------------------------------------------------------------ valoraciones y cobertura
def test_sin_evidencia_no_suma_pero_baja_la_cobertura():
    p = puntaje("CV-001")                                     # DES-05 sin evidencia
    des05 = next(c for c in p.criterios if c.id == "DES-05")
    assert des05.valor is None and p.cobertura == pytest.approx(1 - des05.peso)


def test_cumple_solo_con_la_lista_vale_075():
    p = puntaje("CV-001", {"DES-01": ("cumple", ["Spring Boot"])})     # «Spring Boot» de habilidades
    assert next(c for c in p.criterios if c.id == "DES-01").valor == 0.75


@pytest.mark.parametrize("estado,valor", [("parcial", 0.5), ("no_cumple", 0.25)])
def test_parcial_y_no_cumple(estado, valor):
    cita = REGISTRO["frases_relacionadas"].funcion({"id_requisito": "DES-03"}, contexto("CV-001"))["frases"][0]["texto"]
    p = puntaje("CV-001", {"DES-03": (estado, [cita])})
    assert next(c for c in p.criterios if c.id == "DES-03").valor == valor


def test_no_tener_evidencia_no_premia():
    """La razón de la decisión 2: con «sobre lo evidenciado», CV-022 (0 deseables) le ganaba a CV-016 (2)."""
    assert puntaje("CV-016").puntaje > puntaje("CV-022").puntaje


def test_contradiccion_material_viene_del_auditor():
    cita = REGISTRO["frases_relacionadas"].funcion({"id_requisito": "REQ-05"}, contexto("CV-001"))["frases"][0]["texto"]
    p = puntaje("CV-001", {"REQ-05": ("no_cumple", [cita])}, veredicto=True)   # C1 marcado no_cumple
    assert p.contradiccion_material


def test_ficha_y_motor_de_cv_distintos_falla():
    c, f = ficha_simulada("CV-001")
    with pytest.raises(ValueError):
        calcular_puntaje(f, MOTOR["CV-002"], VACANTE, DIC)


# ------------------------------------------------------------------ invariantes del SDD
def test_par_contrafactual_mismo_puntaje():
    """CV-006 (mujer) y CV-007 (hombre): idénticos salvo nombre y sexo. El SDD tolera ≤ 0,02."""
    assert puntaje("CV-006").puntaje == puntaje("CV-007").puntaje


def test_texto_oculto_conserva_el_puntaje_de_su_version_limpia():
    """El SDD: «el CV con texto oculto conserve el puntaje de su versión limpia» (CV-040 vs CV-008)."""
    assert puntaje("CV-040").puntaje == puntaje("CV-008").puntaje


def test_staging_top5_solo_aptos_con_empate_r5_y_parciales_a_revision():
    st = armar_staging([puntaje(i).para_staging() for i in EN_RANKING], "VAC-001", VACANTE.version)
    top = [t["cv_id"] for t in st["top"]]
    assert all(MANIFIESTO[i]["grupo"] == "apto" for i in top)          # ningún no apto ni parcial
    assert len(top) == 6 and st["empate_r5"]                           # 5.º y 6.º a ≤ 0,02 → seis (R5)
    assert top[0] == "CV-002"                                          # el único con los 5 deseables
    parciales = sorted(i for i in EN_RANKING if MANIFIESTO[i]["grupo"] == "parcial")
    assert st["revision_humana_r4"] == parciales                       # cobertura < 0,70 → humano (R4)


def test_staging_es_determinista():
    a = armar_staging([puntaje(i).para_staging() for i in EN_RANKING], "VAC-001", 1)
    b = armar_staging([puntaje(i).para_staging() for i in reversed(EN_RANKING)], "VAC-001", 1)
    assert a["staging_id"] == b["staging_id"]
