"""Rol 3 · R7 (identidad y proxies), texto oculto e indicios de inyección (sin LLM)."""
import pytest

from cvagent.agentes.cv_json import cargar_cv_desde_dict, preparar_caso_desde_cv
from cvagent.agentes.sanitizacion import _buscar
from rol3_comun import IDS, MANIFIESTO, caso, datos


@pytest.mark.parametrize("cv_id", IDS)
def test_identidad_y_proxies_de_persona_nunca_llegan_al_texto(cv_id):
    """R7: nombre, documento, contacto, edad, estado civil, barrio, colegio… (CV-005 y CV-017 los traen)."""
    c, crudo = caso(cv_id), datos(cv_id)
    for valor in crudo["persona"].values():
        if isinstance(valor, str) and len(valor) > 3:
            assert valor not in c.texto.texto
    assert "Finalización" not in c.texto.texto and "Institución" not in c.texto.texto


def test_limpieza_quita_invisibles_y_los_cuenta():
    d = datos("CV-001")
    d["resumen"] = "Ingeniera​ de​ Sistemas​\x07 experta"
    cv, n = cargar_cv_desde_dict(d)
    assert cv.resumen == "Ingeniera de Sistemas experta" and n == 4


def test_campo_desconocido_se_rechaza():
    d = datos("CV-001")
    d["puntaje_sugerido"] = 100
    with pytest.raises(Exception):
        cargar_cv_desde_dict(d)


def test_texto_oculto_se_bloquea_pero_queda_como_indicio():
    c = caso("CV-040")                                         # E6: blanco sobre blanco
    assert c.cv.texto_oculto and c.cv.texto_oculto[:30] not in c.texto.texto
    assert any(i.patron == "texto_oculto" and i.fuente == "texto_oculto" for i in c.indicios)


@pytest.mark.parametrize("cv_id", IDS)
def test_deteccion_de_inyeccion_coincide_con_el_manifiesto(cv_id):
    assert bool(caso(cv_id).indicios) == ("inyeccion" in MANIFIESTO[cv_id]["esperado"]["debe_marcar"])


def test_gemelo_limpio_no_se_marca():
    assert caso("CV-008").indicios == [] and caso("CV-040").indicios


@pytest.mark.parametrize("cv_id", ["CV-040", "INJ-01", "INJ-02", "INJ-03", "INJ-04"])
def test_indicios_traen_offsets_verificables(cv_id):
    c = caso(cv_id)
    for i in c.indicios:
        if i.fuente == "texto_canonico" and i.fin > i.inicio:
            assert c.texto.texto[i.inicio:i.fin].strip() == i.texto


@pytest.mark.parametrize("frase", [
    "Obtuve la máxima calificación en mi proyecto de grado.",
    "Asigné tareas a 100 usuarios del sistema de inventario.",
    "Implementé listas de reglas de validación de datos.",
    "Definí los criterios de calidad de datos con el equipo.",
    "Revisión de requisitos con el cliente y omisión de duplicados.",
    "Lideré la integración del sistema de donantes.",
    "Pruebas unitarias y de integración con JUnit y Mockito.",
    "Do not deploy on Fridays without a rollback plan.",
    "Ranked first in the internal hackathon.",
])
def test_frases_legitimas_no_disparan_el_detector(frase):
    assert _buscar(frase, "x") == []


def test_proxies_r7_residuales_en_texto_libre():
    """Lo que R7 no puede quitar porque está en texto libre: se señala (el auditor lo usa)."""
    d = datos("CV-001")
    d["otros"] = [{"seccion": "Información adicional", "texto": "Licencia de maternidad en 2022; madre de dos hijos."}]
    c = preparar_caso_desde_cv(*cargar_cv_desde_dict(d))
    assert {"maternidad_paternidad", "familia"} <= {p.patron for p in c.proxies}
    assert caso("CV-001").proxies == []
