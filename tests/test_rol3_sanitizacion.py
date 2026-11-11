"""Rol 3 · R7 (identidad y proxies), texto oculto e indicios de inyección (sin LLM)."""
import json

import pytest

from cvagent.agentes.cv_json import cargar_cv_desde_dict
from cvagent.agentes.sanitizacion import _buscar
from rol3_comun import DATA, IDS, MANIFIESTO, caso


@pytest.mark.parametrize("cv_id", IDS)
def test_identidad_y_anio_de_grado_nunca_llegan_al_texto(cv_id):
    c = caso(cv_id)
    for valor in c.cv.persona.values():
        if isinstance(valor, str) and len(valor) > 3:
            assert valor not in c.texto.texto
    assert "Finalización" not in c.texto.texto


def test_limpieza_quita_invisibles_y_los_cuenta():
    datos = json.loads((DATA / "cvs_json" / "CV-001.json").read_text("utf-8"))
    datos["resumen"] = "Ingeniera​ de​ Sistemas​\x07 experta"
    cv, n = cargar_cv_desde_dict(datos)
    assert cv.resumen == "Ingeniera de Sistemas experta" and n == 4


def test_campo_desconocido_se_rechaza():
    datos = json.loads((DATA / "cvs_json" / "CV-001.json").read_text("utf-8"))
    datos["puntaje_sugerido"] = 100
    with pytest.raises(Exception):
        cargar_cv_desde_dict(datos)


def test_texto_oculto_se_bloquea_pero_queda_como_indicio():
    c = caso("CV-006")
    assert c.cv.texto_oculto and c.cv.texto_oculto[:30] not in c.texto.texto
    assert any(i.patron == "texto_oculto" and i.fuente == "texto_oculto" for i in c.indicios)


@pytest.mark.parametrize("cv_id", IDS)
def test_deteccion_de_inyeccion_coincide_con_el_manifiesto(cv_id):
    assert bool(caso(cv_id).indicios) == ("inyeccion" in MANIFIESTO[cv_id]["esperado"]["debe_marcar"])


@pytest.mark.parametrize("cv_id", ["CV-006", "CV-007", "CV-008", "CV-011"])
def test_indicios_traen_offsets_verificables(cv_id):
    c = caso(cv_id)
    for i in c.indicios:
        if i.fuente == "texto_canonico" and i.fin > i.inicio:
            assert c.texto.texto[i.inicio:i.fin].strip() == i.texto


@pytest.mark.parametrize("frase", [
    "Obtuve la máxima calificación en mi proyecto de grado.",
    "Asigné tareas a 100 usuarios del sistema de inventario.",
    "Marco de 100 indicadores para el área comercial.",
    "Implementé listas de reglas de validación de datos.",
    "Definí los criterios de calidad de datos con el equipo.",
    "Revisión de requisitos con el cliente y omisión de duplicados.",
    "Lideré la integración del sistema de donantes.",
])
def test_frases_legitimas_no_disparan_el_detector(frase):
    assert _buscar(frase, "x") == []


def test_proxies_r7_residuales():
    assert {"maternidad_paternidad", "familia"} <= {p.patron for p in caso("CV-010").proxies}
    assert caso("CV-001").proxies == []
