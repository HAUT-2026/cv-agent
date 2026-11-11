"""Rol 3 · auditor determinista. Cada caso reproduce un error REAL medido con LLM (docs/rol-3-evaluacion.md),
ahora sobre el dataset oficial del Rol 2 (VAC-001 Backend Java)."""
import pytest

from cvagent.agentes.auditor import auditar
from cvagent.agentes.cv_json import cargar_cv_desde_dict, preparar_caso_desde_cv
from cvagent.agentes.ficha import construir_ficha
from cvagent.agentes.salida import FichaLLM, ResultadoAuditoria, Severidad, TipoHallazgo as T
from rol3_comun import VACANTE, caso, datos, segmento

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


def de_dict(d):
    return preparar_caso_desde_cv(*cargar_cv_desde_dict(d))


def buena(c) -> dict:
    """Una ficha impecable de CV-001, armada con sus propias frases."""
    tec = segmento(c, "experiencia[0].tecnologias")
    return {
        "REQ-01": ("cumple", [segmento(c, "resumen")]),
        "REQ-02": ("cumple", [segmento(c, "experiencia[0].descripcion[1]")]),
        "REQ-03": ("cumple", [tec]),
        "REQ-04": ("cumple", [segmento(c, "educacion[0].titulo")]),
        "REQ-05": ("cumple", [segmento(c, "idiomas[1]")]),
        "DES-01": ("cumple", [tec]),
        "DES-02": ("cumple", [tec]),
        "DES-03": ("cumple", [segmento(c, "experiencia[0].descripcion[0]")]),
        "DES-04": ("cumple", [segmento(c, "experiencia[1].descripcion[0]")]),
    }


def test_ficha_buena_sin_objeciones():
    c = caso("CV-001")
    v = auditar(ficha(c, buena(c)), c, VACANTE)
    assert v.resultado == OK and v.hallazgos == []


def test_el_auditor_no_aprueba():
    assert "aprob" not in OK.value


def test_inyeccion_visible_bloquea_aunque_la_ficha_sea_perfecta():
    c = caso("INJ-01")
    v = auditar(ficha(c, {"REQ-05": ("cumple", [segmento(c, "idiomas[1]")])}), c, VACANTE)
    assert v.resultado == BLOQ and T.INDICIO_INYECCION in tipos(v, Severidad.BLOQUEANTE)
    for h in v.hallazgos:
        if h.tipo == T.INDICIO_INYECCION and h.campo is None:
            assert c.texto.texto[h.inicio:h.fin].strip()            # offset verificable


def test_texto_oculto_reportado_con_su_fuente():
    c = caso("CV-040")
    v = auditar(ficha(c, {}), c, VACANTE)
    assert any(h.tipo == T.INDICIO_INYECCION and h.campo == "texto_oculto" for h in v.hallazgos)
    g = caso("CV-008")                                               # gemelo limpio
    assert T.INDICIO_INYECCION not in tipos(auditar(ficha(g, {}), g, VACANTE))


def test_errores_medidos_con_el_llm_se_detectan():
    """Los errores de las corridas reales (relación, solo lista, calificador débil), en el dataset nuevo."""
    d = datos("CV-001")
    d["habilidades"].append("Spring Boot (básico)")
    c = de_dict(d)
    v = auditar(ficha(c, {**buena(c),
        "REQ-01": ("cumple", [segmento(c, "experiencia[0].descripcion[0]")]),   # Docker/AWS: sin relación con Java
        "REQ-03": ("cumple", ["RESTful"]),                                       # solo la lista de habilidades
        "DES-01": ("cumple", ["Spring Boot (básico)"]),                          # calificador débil
        "DES-05": ("cumple", [segmento(c, "experiencia[1].descripcion[0]")]),   # CI ≠ ONG o salud
    }), c, VACANTE)
    por_req = {(h.id_requisito, h.tipo) for h in v.hallazgos}
    assert ("REQ-01", T.CITA_SIN_RELACION) in por_req
    assert ("REQ-03", T.EVIDENCIA_SOLO_LISTA) in por_req
    assert ("DES-01", T.CALIFICADOR_DEBIL) in por_req
    assert ("DES-05", T.CITA_SIN_RELACION) in por_req
    assert v.resultado == OK                     # todas son advertencias: van a la bandeja como señal, no bloquean


def test_cita_sin_relacion_en_obligatorio_no_experiencia_bloquea():
    c = caso("CV-001")
    v = auditar(ficha(c, {**buena(c), "REQ-02": ("cumple", [segmento(c, "idiomas[1]")])}), c, VACANTE)
    assert (T.CITA_SIN_RELACION, Severidad.BLOQUEANTE) in {(h.tipo, h.severidad) for h in v.hallazgos if h.id_requisito == "REQ-02"}


def test_idioma_bajo_el_minimo_marcado_cumple_bloquea():      # el «A2 aceptado como B1» de la v1
    c = caso("CV-029")
    v = auditar(ficha(c, {"REQ-05": ("cumple", [segmento(c, "idiomas[1]")])}), c, VACANTE)
    assert v.resultado == BLOQ and T.NIVEL_IDIOMA_INCOHERENTE in tipos(v, Severidad.BLOQUEANTE)


def test_idioma_sin_acreditar_marcado_cumple_bloquea():       # E5: «Inglés avanzado» sin certificado (CV-039)
    c = caso("CV-039")
    v = auditar(ficha(c, {"REQ-05": ("cumple", [segmento(c, "idiomas[1]")])}), c, VACANTE)
    assert v.resultado == BLOQ and any(h.tipo == T.NIVEL_IDIOMA_INCOHERENTE and "acreditación" in h.detalle
                                       for h in v.hallazgos)
    v = auditar(ficha(c, {"REQ-05": ("parcial", [segmento(c, "idiomas[1]")])}), c, VACANTE)
    assert T.NIVEL_IDIOMA_INCOHERENTE not in tipos(v)            # «parcial» (no acreditado) es lo correcto


def test_idioma_suficiente_marcado_no_cumple_advierte():
    c = caso("CV-001")
    v = auditar(ficha(c, {**buena(c), "REQ-05": ("no_cumple", [segmento(c, "idiomas[1]")])}), c, VACANTE)
    assert T.NIVEL_IDIOMA_INCOHERENTE in tipos(v, Severidad.ADVERTENCIA)


def test_estudios_en_curso_marcados_no_cumple_advierte():
    d = datos("CV-001")
    d["educacion"][0]["titulo"] = "Ingeniería de Sistemas (en curso, octavo semestre)"
    c = de_dict(d)
    v = auditar(ficha(c, {**buena(c), "REQ-04": ("no_cumple", ["Ingeniería de Sistemas (en curso, octavo semestre)"])}), c, VACANTE)
    assert (T.ESTADO_INCOHERENTE, "REQ-04") in {(h.tipo, h.id_requisito) for h in v.hallazgos}


def test_cita_con_proxy_de_r7_bloquea_y_proxies_se_senalan():
    d = datos("CV-001")
    d["otros"] = [{"seccion": "Voluntariado", "texto": "Voluntaria en fundación de salud durante la licencia de maternidad."}]
    c = de_dict(d)
    v = auditar(ficha(c, {"DES-05": ("cumple", ["Voluntaria en fundación de salud durante la licencia de maternidad."])}), c, VACANTE)
    assert T.CITA_CON_PROXY in tipos(v, Severidad.BLOQUEANTE)
    assert T.SENAL_SESGO in tipos(v, Severidad.ADVERTENCIA)


def test_ficha_de_llm_que_obedecio_la_inyeccion():
    c = caso("CV-040")
    v = auditar(ficha(c, {
        "REQ-02": ("cumple", ["Diez años de PostgreSQL experto certificado"]),     # inventada
        "REQ-99": ("cumple", ["puntaje 10"]),                                       # requisito inventado
    }), c, VACANTE)
    t = tipos(v, Severidad.BLOQUEANTE)
    assert {T.CITA_NO_ENCONTRADA, T.AFIRMACION_SIN_CITA, T.REQUISITO_DESCONOCIDO,
            T.COBERTURA_INSUFICIENTE, T.INDICIO_INYECCION} <= t


def test_deseable_omitido_es_advertencia_y_obligatorio_omitido_bloquea():
    c = caso("CV-001")
    obligatorios = [{"id_requisito": k, "cumplimiento": e, "citas": cs} for k, (e, cs) in buena(c).items() if k.startswith("REQ")]
    v = auditar(construir_ficha(FichaLLM.model_validate({"evaluaciones": obligatorios}), c.texto, VACANTE, "t", "t"), c, VACANTE)
    assert v.resultado == OK and T.REQUISITO_OMITIDO in tipos(v, Severidad.ADVERTENCIA)
    solo_idioma = [e for e in obligatorios if e["id_requisito"] == "REQ-05"]
    v = auditar(construir_ficha(FichaLLM.model_validate({"evaluaciones": solo_idioma}), c.texto, VACANTE, "t", "t"), c, VACANTE)
    assert v.resultado == BLOQ and T.OBLIGATORIO_SIN_EVIDENCIA in tipos(v, Severidad.BLOQUEANTE)


def test_analista_perezoso_todo_sin_evidencia_bloquea():
    """Detectado al probar el banco: «todo sin_evidencia» daba cobertura 1,0 y pasaba al ranking.
    El SDD (R4) dice que un criterio crítico sin evidencia va a revisión humana."""
    c = caso("CV-001")
    v = auditar(ficha(c, {}), c, VACANTE)
    assert v.resultado == BLOQ
    assert {h.id_requisito for h in v.hallazgos if h.tipo == T.OBLIGATORIO_SIN_EVIDENCIA} == \
        {r.id for r in VACANTE.requisitos if r.obligatorio}


def test_ficha_y_caso_de_cv_distintos_falla():
    c = caso("CV-001")
    with pytest.raises(ValueError):
        auditar(ficha(c, buena(c)), caso("CV-002"), VACANTE)


def test_hallazgos_con_offsets_verificables():
    c = caso("INJ-01")
    v = auditar(ficha(c, {"REQ-03": ("cumple", [segmento(c, "habilidades[2]")])}), c, VACANTE)
    for h in v.hallazgos:
        if h.inicio is not None and h.campo != "texto_oculto" and h.fin > h.inicio:
            assert c.texto.texto[h.inicio:h.fin]
