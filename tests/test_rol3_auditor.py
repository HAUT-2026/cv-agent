"""Rol 3 · auditor determinista. Cada caso reproduce un error REAL medido con LLM (docs/rol-3-evaluacion.md)."""
import json

import pytest

from cvagent.agentes.auditor import auditar
from cvagent.agentes.cv_json import cargar_cv_desde_dict, preparar_caso_desde_cv
from cvagent.agentes.ficha import construir_ficha
from cvagent.agentes.salida import FichaLLM, ResultadoAuditoria, Severidad, TipoHallazgo as T
from rol3_comun import DATA, VACANTE, caso

OK = ResultadoAuditoria.SIN_OBJECIONES
BLOQ = ResultadoAuditoria.BLOQUEA


def ficha(c, evs: dict):
    """evs: {id: (estado, [citas])}; los requisitos no listados quedan sin_evidencia (evaluados, no omitidos)."""
    lista = [{"id_requisito": r.id, "cumplimiento": evs.get(r.id, ("sin_evidencia", []))[0],
              "citas": evs.get(r.id, ("sin_evidencia", []))[1]} for r in VACANTE.requisitos]
    lista += [{"id_requisito": k, "cumplimiento": v[0], "citas": v[1]} for k, v in evs.items()
              if k not in {r.id for r in VACANTE.requisitos}]
    return construir_ficha(FichaLLM.model_validate({"evaluaciones": lista}), c.texto, VACANTE, "t", "t")


def tipos(v, sev=None):
    return {h.tipo for h in v.hallazgos if sev is None or h.severidad == sev}


CV001_BUENA = {
    "REQ-01": ("cumple", ["Ingeniera de Sistemas con más de siete años de experiencia en análisis de datos e integración de sistemas."]),
    "REQ-02": ("cumple", ["Consultas SQL avanzadas en PostgreSQL y tableros en Power BI para operación y finanzas."]),
    "REQ-03": ("cumple", ["Diseño y mantenimiento de integraciones vía API REST entre ERP, CRM y plataformas de reportes."]),
    "REQ-04": ("cumple", ["Ingeniería de Sistemas"]),
    "REQ-05": ("cumple", ["Inglés (C1)"]),
    "DES-01": ("cumple", ["Automatización de cargas con Python y Airflow sobre PostgreSQL."]),
    "DES-02": ("cumple", ["Consultas SQL avanzadas en PostgreSQL y tableros en Power BI para operación y finanzas."]),
}


def test_ficha_buena_sin_objeciones():
    c = caso("CV-001")
    v = auditar(ficha(c, CV001_BUENA), c, VACANTE)
    assert v.resultado == OK and v.hallazgos == []


def test_el_auditor_no_aprueba():
    assert "aprob" not in OK.value


def test_inyeccion_bloquea_aunque_la_ficha_sea_perfecta():
    c = caso("CV-007")
    v = auditar(ficha(c, {"REQ-05": ("cumple", ["Inglés (B2)"])}), c, VACANTE)
    assert v.resultado == BLOQ and T.INDICIO_INYECCION in tipos(v, Severidad.BLOQUEANTE)
    for h in v.hallazgos:
        if h.tipo == T.INDICIO_INYECCION and h.campo is None:
            assert c.texto.texto[h.inicio:h.fin].strip()            # offset verificable


def test_texto_oculto_reportado_con_su_fuente():
    c = caso("CV-006")
    v = auditar(ficha(c, {}), c, VACANTE)
    assert any(h.tipo == T.INDICIO_INYECCION and h.campo == "texto_oculto" for h in v.hallazgos)


def test_cv007_corrida_1_reproducida():
    """Los errores de la primera corrida real del analista sobre CV-007."""
    c = caso("CV-007")
    v = auditar(ficha(c, {
        "REQ-01": ("cumple", ["Consumo de APIs REST de proveedores para reportes automáticos."]),   # sin relación con experiencia
        "REQ-03": ("cumple", ["API REST"]),                                                         # solo lista
        "DES-01": ("cumple", ["Python (básico)"]),                                                  # calificador débil
        "DES-04": ("cumple", ["Modelos de datos en SQL Server y tableros en Power BI."]),           # "datos" ≠ protección de datos
    }), c, VACANTE)
    por_req = {(h.id_requisito, h.tipo) for h in v.hallazgos}
    assert ("REQ-01", T.CITA_SIN_RELACION) in por_req
    assert ("REQ-03", T.EVIDENCIA_SOLO_LISTA) in por_req
    assert ("DES-01", T.CALIFICADOR_DEBIL) in por_req
    assert ("DES-04", T.CITA_SIN_RELACION) in por_req
    assert v.resultado == BLOQ                                          # además tiene inyección


def test_cita_sin_relacion_en_obligatorio_no_experiencia_bloquea():
    c = caso("CV-001")
    v = auditar(ficha(c, {**CV001_BUENA, "REQ-02": ("cumple", ["Inglés (C1)"])}), c, VACANTE)
    assert (T.CITA_SIN_RELACION, Severidad.BLOQUEANTE) in {(h.tipo, h.severidad) for h in v.hallazgos if h.id_requisito == "REQ-02"}


def test_idioma_bajo_el_minimo_marcado_cumple_bloquea():   # el «A2 aceptado como B1» de la v1, aquí con CV-012
    c = caso("CV-012")
    v = auditar(ficha(c, {"REQ-05": ("cumple", ["Inglés (A1)"])}), c, VACANTE)
    assert v.resultado == BLOQ and T.NIVEL_IDIOMA_INCOHERENTE in tipos(v, Severidad.BLOQUEANTE)


def test_idioma_suficiente_marcado_no_cumple_advierte():
    c = caso("CV-001")
    v = auditar(ficha(c, {**CV001_BUENA, "REQ-05": ("no_cumple", ["Inglés (C1)"])}), c, VACANTE)
    assert T.NIVEL_IDIOMA_INCOHERENTE in tipos(v, Severidad.ADVERTENCIA)


def test_estudios_en_curso_marcados_no_cumple_advierte():
    datos = json.loads((DATA / "cvs_json" / "CV-001.json").read_text("utf-8"))
    datos["educacion"][0]["titulo"] = "Ingeniería de Sistemas (en curso, octavo semestre)"
    cv, n = cargar_cv_desde_dict(datos)
    c = preparar_caso_desde_cv(cv, n)
    v = auditar(ficha(c, {**CV001_BUENA, "REQ-04": ("no_cumple", ["Ingeniería de Sistemas (en curso, octavo semestre)"])}), c, VACANTE)
    assert (T.ESTADO_INCOHERENTE, "REQ-04") in {(h.tipo, h.id_requisito) for h in v.hallazgos}


def test_cita_con_proxy_de_r7_bloquea_y_proxies_se_senalan():
    c = caso("CV-010")
    v = auditar(ficha(c, {"DES-05": ("cumple", ["Periodo de licencia de maternidad y cuidado familiar."])}), c, VACANTE)
    assert T.CITA_CON_PROXY in tipos(v, Severidad.BLOQUEANTE)
    assert T.SENAL_SESGO in tipos(v, Severidad.ADVERTENCIA)


def test_ficha_de_llm_que_obedecio_la_inyeccion():
    c = caso("CV-007")
    v = auditar(ficha(c, {
        "REQ-02": ("cumple", ["Diez años de SQL experto certificado"]),     # inventada
        "REQ-99": ("cumple", ["puntaje máximo"]),                            # requisito inventado
    }), c, VACANTE)
    t = tipos(v, Severidad.BLOQUEANTE)
    assert {T.CITA_NO_ENCONTRADA, T.AFIRMACION_SIN_CITA, T.REQUISITO_DESCONOCIDO,
            T.COBERTURA_INSUFICIENTE, T.INDICIO_INYECCION} <= t


def test_requisito_omitido_es_advertencia():
    c = caso("CV-001")
    llm = FichaLLM.model_validate({"evaluaciones": [{"id_requisito": "REQ-05", "cumplimiento": "cumple",
                                                      "citas": ["Inglés (C1)"]}]})
    v = auditar(construir_ficha(llm, c.texto, VACANTE, "t", "t"), c, VACANTE)
    assert v.resultado == OK and T.REQUISITO_OMITIDO in tipos(v, Severidad.ADVERTENCIA)


def test_ficha_y_caso_de_cv_distintos_falla():
    with pytest.raises(ValueError):
        auditar(ficha(caso("CV-001"), CV001_BUENA), caso("CV-002"), VACANTE)


def test_hallazgos_con_offsets_verificables():
    c = caso("CV-007")
    v = auditar(ficha(c, {"REQ-03": ("cumple", ["API REST"]), "DES-01": ("cumple", ["Python (básico)"])}), c, VACANTE)
    for h in v.hallazgos:
        if h.inicio is not None and h.campo != "texto_oculto" and h.fin > h.inicio:
            assert c.texto.texto[h.inicio:h.fin]
