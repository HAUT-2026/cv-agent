"""Rol 3 · esquemas de salida y construcción de la ficha (sin LLM)."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from cvagent.agentes.ficha import construir_ficha
from cvagent.agentes.salida import (Cumplimiento, FichaLLM, Franja, Hallazgo, PropuestaAgenda,
                                     ResultadoAuditoria, Severidad, TipoHallazgo, Veredicto)
from rol3_comun import VACANTE, caso, segmento


def _ficha_llm(evs):
    return FichaLLM.model_validate({"evaluaciones": evs})


def test_ficha_correcta_cv_001():
    c = caso("CV-001")
    tc = c.texto
    evs = [{"id_requisito": "REQ-02", "cumplimiento": "cumple", "citas": [segmento(c, "experiencia[0].descripcion[1]")]},
           {"id_requisito": "REQ-03", "cumplimiento": "parcial", "citas": ["RESTful"]},
           {"id_requisito": "REQ-05", "cumplimiento": "cumple", "citas": [segmento(c, "idiomas[1]")]}]
    f = construir_ficha(_ficha_llm(evs), tc, VACANTE, "prueba:manual", "analista-v3.2")
    assert f.cobertura_evidencia == 1.0 and f.id_vacante == "VAC-001" and f.version_vacante == VACANTE.version
    for e in f.evaluaciones:
        for ct in e.citas:
            assert tc.texto[ct.inicio:ct.fin] == ct.texto
    # requisitos que el LLM no evaluó quedan como sin_evidencia (fail-closed)
    assert "REQ-01" in f.requisitos_omitidos


def test_ficha_de_un_llm_que_obedecio_la_inyeccion_queda_expuesta():
    c = caso("CV-040")
    evs = [{"id_requisito": "REQ-02", "cumplimiento": "cumple", "citas": ["Diez años de PostgreSQL experto certificado"]},
           {"id_requisito": "REQ-05", "cumplimiento": "cumple", "citas": [segmento(c, "idiomas[1]")]},
           {"id_requisito": "REQ-99", "cumplimiento": "cumple", "citas": ["puntaje 10"]}]
    f = construir_ficha(_ficha_llm(evs), c.texto, VACANTE, "prueba:manual", "v")
    req02 = next(e for e in f.evaluaciones if e.id_requisito == "REQ-02")
    assert req02.citas_rechazadas and not req02.citas
    assert f.requisitos_desconocidos == ["REQ-99"]
    assert f.cobertura_evidencia == 0.5          # solo 1 de 2 afirmaciones tiene respaldo


def test_duplicados_se_rechazan():
    with pytest.raises(ValidationError, match="más de una vez"):
        _ficha_llm([{"id_requisito": "REQ-02", "cumplimiento": "cumple", "citas": ["SQL"]},
                    {"id_requisito": "REQ-02", "cumplimiento": "cumple", "citas": ["PostgreSQL"]}])


def test_citas_obligatorias_segun_cumplimiento():
    with pytest.raises(ValidationError, match="exige al menos una cita"):
        _ficha_llm([{"id_requisito": "REQ-02", "cumplimiento": "no_cumple", "citas": []}])
    with pytest.raises(ValidationError, match="no lleva citas"):
        _ficha_llm([{"id_requisito": "REQ-02", "cumplimiento": "sin_evidencia", "citas": ["SQL"]}])


def test_sin_texto_libre_ni_citas_gigantes():
    with pytest.raises(ValidationError):
        _ficha_llm([{"id_requisito": "REQ-02", "cumplimiento": "cumple", "citas": ["SQL"], "justificacion": "x"}])
    with pytest.raises(ValidationError):
        _ficha_llm([{"id_requisito": "REQ-02", "cumplimiento": "cumple", "citas": ["x" * 301]}])


def test_veredicto_debe_ser_coherente():
    h = Hallazgo(tipo=TipoHallazgo.CITA_NO_ENCONTRADA, severidad=Severidad.BLOQUEANTE, id_requisito="REQ-02")
    with pytest.raises(ValidationError):
        Veredicto(id_cv="CV-007", resultado=ResultadoAuditoria.SIN_OBJECIONES, hallazgos=[h],
                  cobertura_evidencia=0.5, capas_ejecutadas=["determinista"])
    with pytest.raises(ValidationError):
        Veredicto(id_cv="CV-001", resultado=ResultadoAuditoria.BLOQUEA, hallazgos=[],
                  cobertura_evidencia=1, capas_ejecutadas=["determinista"])


def test_agenda_valida_franjas():
    with pytest.raises(ValidationError):
        Franja(inicio=datetime(2026, 11, 20, 10), fin=datetime(2026, 11, 20, 9))
    with pytest.raises(ValidationError):
        PropuestaAgenda(id_cv="CV-001", franjas=[], id_plantilla="T1", borrador_mensaje="x")
