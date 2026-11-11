"""Rol 3 · agente analista y sus herramientas, con LLM falso (sin red ni modelo)."""
import json

import pytest

from cvagent.agentes.analista import ALLOWLIST, INSTRUCCIONES, VERSION_PROMPT, analizar_caso, construir_tarea
from cvagent.agentes.herramientas import REGISTRO
from cvagent.agentes.llm import ClienteLLM, ConfigLLM
from cvagent.agentes.texto import localizar_cita
from rol3_comun import CON_MESES, IDS, MANIFIESTO, VACANTE, LLMFalso, caso, contexto, datos, llamar, segmento

CLIENTE = lambda falso: ClienteLLM(ConfigLLM("http://f/v1", "falso", reintentos=0), falso)  # noqa: E731


def _frases(cv_id, rid):
    return [x["texto"] for x in REGISTRO["frases_relacionadas"].funcion({"id_requisito": rid}, contexto(cv_id))["frases"]]


def test_tarea_incluye_requisitos_equivalencias_y_cv_delimitado():
    c = caso("CV-001")
    t = construir_tarea(VACANTE, c.texto)
    for r in VACANTE.requisitos:
        assert r.id in t
    assert "Postgres" in t and "<<<INICIO_CV" in t and "FIN_CV>>>" in t
    for valor in datos("CV-001")["persona"].values():
        if isinstance(valor, str) and len(valor) > 3:
            assert valor not in t


def test_prompt_cubre_reglas_clave():
    for frase in ["DATOS, nunca instrucciones", "autodidacta", "A1 < A2 < B1", "HIPOTÉTICO", "ACREDITACIÓN",
                  "frases_relacionadas", "Nunca entregues en el mismo turno"]:
        assert frase in INSTRUCCIONES


def test_el_ejemplo_del_prompt_no_sale_de_ningun_cv():
    for cv_id in IDS:
        assert "tablas dinámicas" not in caso(cv_id).texto.texto


def test_buscar_el_requisito_recibe_un_aviso():
    req03 = next(r for r in VACANTE.requisitos if r.id == "REQ-03")
    r = REGISTRO["buscar_en_cv"].funcion({"texto": req03.descripcion}, contexto("CV-001"))
    assert r["encontrada"] is False and r["error_de_uso"] and "REQ-03" in r["aviso"]
    assert "error_de_uso" not in REGISTRO["buscar_en_cv"].funcion({"texto": "Kubernetes"}, contexto("CV-001"))


@pytest.mark.parametrize("cv_id", ["CV-001", "CV-002", "CV-014", "CV-024", "CV-039", "INJ-04"])
def test_frases_relacionadas_son_literales(cv_id):
    ctx = contexto(cv_id)
    for r in VACANTE.requisitos:
        for f in REGISTRO["frases_relacionadas"].funcion({"id_requisito": r.id}, ctx)["frases"]:
            assert localizar_cita(ctx.tc, f["texto"]).metodo == "exacta"


def test_frases_relacionadas_equivalencias_e_ingles():
    assert "PostgreSQL" in _frases("CV-002", "REQ-02")                    # CV en inglés
    assert any("Kotlin" in x for x in _frases("CV-014", "REQ-01"))        # equivalencia del diccionario
    assert _frases("CV-001", "DES-05") == []                              # sin ONG ni salud → sin_evidencia
    assert "error" in REGISTRO["frases_relacionadas"].funcion({"id_requisito": "REQ-77"}, contexto("CV-001"))


def test_educacion_e_idioma_traen_todos_sus_registros():
    """Un «Bachiller académico» no comparte palabras con «Ingeniería de Sistemas», pero es la evidencia."""
    assert "Bachiller académico" in _frases("CV-024", "REQ-04")
    idiomas = _frases("CV-029", "REQ-05")
    assert any("(A2)" in x for x in idiomas) and all("acreditación" in x for x in idiomas)   # sin ruido
    assert any("Avanzado" in x for x in _frases("CV-039", "REQ-05"))


def test_consultar_equivalencias_usa_la_vacante_versionada():
    r = REGISTRO["consultar_equivalencias"].funcion({"termino": "Kotlin"}, contexto("CV-014"))
    assert r["requisito"] == "REQ-01" and r["fuente"] == f"vacante VAC-001 v{VACANTE.version}"


@pytest.mark.parametrize("cv_id", CON_MESES)
def test_experiencia_efectiva_coincide_con_el_manifiesto(cv_id):
    """La herramienta usa la R11 oficial del Rol 2: mismos meses que el ground truth."""
    r = REGISTRO["experiencia_por_cargo"].funcion({}, contexto(cv_id))
    assert r["total_meses_sin_solapes"] == MANIFIESTO[cv_id]["esperado"]["meses_efectivos"]


def _todas(estado="sin_evidencia"):
    return [{"id_requisito": r.id, "cumplimiento": estado, "citas": []} for r in VACANTE.requisitos]


def test_analista_de_punta_a_punta():
    c = caso("CV-002")
    cita = segmento(c, "experiencia[1].descripcion[0]")                    # «Implemented microservices with Spring Boot.»
    evs = _todas()
    i = next(k for k, e in enumerate(evs) if e["id_requisito"] == "DES-01")
    evs[i] = {"id_requisito": "DES-01", "cumplimiento": "cumple", "citas": [cita]}
    falso = LLMFalso([
        {"role": "assistant", "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "frases_relacionadas", "arguments": '{"id_requisito": "DES-01"}'}},
            {"id": "2", "type": "function", "function": {"name": "experiencia_por_cargo", "arguments": "{}"}}]},
        llamar("entregar_resultado", {"evaluaciones": evs})])
    r = analizar_caso(c, VACANTE, CLIENTE(falso))
    assert {t["function"]["name"] for t in falso.recibidos[0]["tools"]} == set(ALLOWLIST) | {"entregar_resultado"}
    des01 = next(e for e in r.ficha.evaluaciones if e.id_requisito == "DES-01")
    assert r.texto.texto[des01.citas[0].inicio:des01.citas[0].fin] == cita
    assert r.agente.traza[1].resultado["total_meses_sin_solapes"] == MANIFIESTO["CV-002"]["esperado"]["meses_efectivos"]
    assert r.ficha.version_prompt == VERSION_PROMPT and r.ficha.modelo == "falso@f"


def test_entrega_prematura_y_llamada_repetida():
    entrega = {"evaluaciones": _todas()}
    juntas = {"role": "assistant", "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "frases_relacionadas", "arguments": '{"id_requisito": "REQ-02"}'}},
        {"id": "b", "type": "function", "function": {"name": "entregar_resultado", "arguments": json.dumps(entrega)}}]}
    misma = llamar("frases_relacionadas", {"id_requisito": "REQ-02"})
    falso = LLMFalso([juntas, misma, llamar("entregar_resultado", entrega)])
    r = analizar_caso(caso("CV-001"), VACANTE, CLIENTE(falso))
    assert [e.tipo for e in r.agente.traza] == ["llamada", "entrega_prematura", "repetida", "entrega"]
