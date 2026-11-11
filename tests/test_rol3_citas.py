"""Rol 3 · texto canónico y localización determinista de citas (sin LLM)."""
from cvagent.agentes.texto import localizar_cita
from rol3_comun import caso

FRASE = "Consultas SQL avanzadas en PostgreSQL y tableros en Power BI"


def test_texto_canonico_es_determinista():
    assert caso("CV-001").texto.texto == caso("CV-001").texto.texto


def test_cita_exacta_con_offsets_y_campo():
    tc = caso("CV-001").texto
    c = localizar_cita(tc, FRASE)
    assert c.metodo == "exacta" and tc.texto[c.inicio:c.fin] == FRASE
    assert c.campo == "experiencia[1].descripcion[0]" and not c.cruza_campos


def test_cita_normalizada_devuelve_el_texto_real():
    c = localizar_cita(caso("CV-001").texto, "CONSULTAS SQL   AVANZADAS EN POSTGRESQL")
    assert c.metodo == "normalizada" and c.texto_real == "Consultas SQL avanzadas en PostgreSQL"


def test_cita_aproximada_tolera_un_cambio_menor():
    c = localizar_cita(caso("CV-001").texto, "Consultas SQL avanzadas en PostgreSQL y los tableros en Power BI")
    assert c is not None and c.metodo == "aproximada" and c.similitud >= 0.90


def test_cifras_alteradas_no_se_aceptan():
    tc = caso("CV-001").texto
    assert localizar_cita(tc, "Periodo: 2019-09 a 2023-02") is not None
    assert localizar_cita(tc, "Periodo: 2019-09 a 2023-12") is None


def test_cita_inventada_o_parafraseada_es_evidencia_invalida():
    tc = caso("CV-001").texto
    assert localizar_cita(tc, "Lideró un equipo de 12 personas en Kubernetes") is None
    assert localizar_cita(tc, "Hizo reportes con datos de la empresa") is None


def test_cita_corta_se_ubica_como_campo_completo():
    tc = caso("CV-012").texto
    c = localizar_cita(tc, "R")
    assert c is not None and c.campo.startswith("habilidades[") and tc.texto[c.inicio:c.fin] == "R"
    assert localizar_cita(tc, "Ze") is None
