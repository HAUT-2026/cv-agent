"""Rol 3 · texto canónico y localización determinista de citas (sin LLM)."""
import pytest

from cvagent.agentes.cv_json import cargar_cv_desde_dict, preparar_caso_desde_cv
from cvagent.agentes.texto import localizar_cita
from rol3_comun import IDS, caso, datos, segmento

RUTA = "experiencia[0].descripcion[0]"


def test_texto_canonico_es_determinista():
    assert caso("CV-001").texto.texto == caso("CV-001").texto.texto


@pytest.mark.parametrize("cv_id", IDS)
def test_cada_segmento_apunta_a_su_valor(cv_id):
    tc = caso(cv_id).texto
    for s in tc.segmentos:
        assert tc.texto[s.inicio:s.fin].strip(), s.ruta


def test_cita_exacta_con_offsets_y_campo():
    c = caso("CV-001")
    frase = segmento(c, RUTA)
    loc = localizar_cita(c.texto, frase)
    assert loc.metodo == "exacta" and c.texto.texto[loc.inicio:loc.fin] == frase
    assert loc.campo == RUTA and not loc.cruza_campos


def test_cita_normalizada_devuelve_el_texto_real():
    c = caso("CV-001")
    frase = segmento(c, RUTA).rstrip(".")
    loc = localizar_cita(c.texto, "  ".join(frase.upper().split()))   # mayúsculas y espacios dobles
    assert loc.metodo == "normalizada" and loc.texto_real == frase


def test_cita_aproximada_tolera_un_cambio_menor():
    c = caso("CV-001")
    frase = segmento(c, RUTA)
    pal = frase.split()
    alterada = " ".join(pal[:3] + ["la"] + pal[3:])                     # una palabra de más
    loc = localizar_cita(c.texto, alterada)
    assert loc is not None and loc.metodo == "aproximada" and loc.similitud >= 0.90


def test_cifras_alteradas_no_se_aceptan():
    c = caso("CV-001")
    periodo = segmento(c, "experiencia[1].periodo")                    # p. ej. «2020-11 a 2023-11»
    assert localizar_cita(c.texto, f"Periodo: {periodo}") is not None
    alterado = periodo[:-1] + ("9" if periodo[-1] != "9" else "8")
    assert localizar_cita(c.texto, f"Periodo: {alterado}") is None


def test_cita_inventada_o_parafraseada_es_evidencia_invalida():
    tc = caso("CV-001").texto
    assert localizar_cita(tc, "Lideró un equipo de 12 personas en Kubernetes") is None
    assert localizar_cita(tc, "Hizo cosas de backend con datos de la empresa") is None


def test_cita_corta_se_ubica_como_campo_completo():
    d = datos("CV-001")
    d["habilidades"].append("Go")
    c = preparar_caso_desde_cv(*cargar_cv_desde_dict(d))
    loc = localizar_cita(c.texto, "Go")
    assert loc is not None and loc.campo.startswith("habilidades[") and c.texto.texto[loc.inicio:loc.fin] == "Go"
    assert localizar_cita(c.texto, "Ze") is None
