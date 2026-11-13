"""Pruebas del Rol 4: adaptadores, anclaje de citas y lote de punta a punta."""

from __future__ import annotations

from pathlib import Path

import pytest

from cvagent.domain.contracts import CitationRef, FichaCandidato, Veredicto
from portal import adaptadores, texto
from portal.lote import ServicioLote

DATA = Path(__file__).resolve().parent.parent / "data"
UUID_DEMO = "00000000-0000-4000-8000-000000000042"


# ----------------------------------------------------------------- anclaje
def test_p1_el_texto_canonico_se_carga_para_todo_el_corpus():
    faltan = []
    for ruta in sorted((DATA / "cvs_json").glob("*.json")):
        try:
            contenido, procedencia = texto.cargar_texto(ruta.stem, DATA)
        except texto.TextoNoDisponible:
            faltan.append(ruta.stem)
            continue
        assert contenido and procedencia in {"pdf", "gemelo_json"}
    assert not faltan, f"sin texto canónico: {faltan}"


def test_p2_anclar_rechaza_una_cita_que_no_esta():
    assert texto.anclar("Perfil backend con Java", "Python") is None


def test_p3_anclar_rechaza_una_cita_ambigua():
    """Una frase que aparece dos veces no identifica nada."""
    assert texto.anclar("Java y mas Java", "Java") is None


def test_p4_citar_devuelve_una_cita_ya_verificada():
    cuerpo = "PERFIL\nDesarrollador con 5 anios de experiencia en Java.\nIngles B2."
    cita = adaptadores.citar(cuerpo, "Java", correlation_id=UUID_DEMO, fuente="demo.txt")
    assert cita is not None
    assert cita.verificada is True
    assert cuerpo[cita.offset_inicio:cita.offset_fin] == cita.cita


def test_p5_la_cita_cumple_el_invariante_del_contrato():
    """offset_fin - offset_inicio == len(cita): lo exige `CitationRef`."""
    cuerpo = "Ingenieria de Sistemas - Universidad Nacional (2019)"
    cita = adaptadores.citar(cuerpo, "Ingenieria de Sistemas",
                             correlation_id=UUID_DEMO, fuente="demo.txt")
    assert cita.offset_fin - cita.offset_inicio == len(cita.cita)
    assert cita.verify_against(cuerpo).verificada is True


def test_p6_un_offset_corrido_hace_fallar_la_verificacion():
    cuerpo = "Ingles B2 certificado"
    cita = adaptadores.citar(cuerpo, "Ingles", correlation_id=UUID_DEMO, fuente="d.txt")
    corrida = CitationRef(
        correlation_id=cita.correlation_id, fuente=cita.fuente, cita=cita.cita,
        offset_inicio=cita.offset_inicio + 1, offset_fin=cita.offset_fin + 1,
    )
    with pytest.raises(ValueError):
        corrida.verify_against(cuerpo)


# --------------------------------------------------------------- inyección
def test_p7_los_cv_de_inyeccion_del_corpus_se_detectan():
    """INJ-03 esconde el texto en el PDF, no en el gemelo: ver H-4."""
    detectados = []
    for cv_id in ("INJ-01", "INJ-02", "INJ-04"):
        contenido, _ = texto.cargar_texto(cv_id, DATA)
        señales = adaptadores.detectar_inyeccion(contenido)
        assert señales, f"{cv_id} sin señal de inyección"
        detectados.append(cv_id)
    assert len(detectados) == 3


def test_p8_un_cv_normal_no_dispara_falsos_positivos():
    contenido, _ = texto.cargar_texto("CV-001", DATA)
    assert adaptadores.detectar_inyeccion(contenido) == []


# ------------------------------------------------------------------- lote
@pytest.fixture(scope="module")
def lote():
    servicio = ServicioLote(DATA)
    servicio.cargar()
    servicio.ejecutar()
    yield servicio
    servicio.cerrar()


def test_p9_el_lote_separa_las_rutas_del_motor_de_reglas():
    servicio = ServicioLote(DATA)
    resumen = servicio.cargar()
    assert resumen["cv_corpus"] == 40
    assert resumen["cv_inyeccion"] == 4
    assert resumen["rutas"]["evaluable"] > 0
    # El SDD lo exige: nada se descarta en silencio, todo tiene ruta.
    assert sum(resumen["rutas"].values()) == resumen["cv_totales"]
    servicio.cerrar()


def test_p10_cada_caso_produce_contratos_validos(lote):
    for correlation_id in lote.contexto.casos:
        resultado = lote.estado_casos.get(correlation_id)
        assert resultado is not None
        ficha = resultado["ficha"]
        FichaCandidato.model_validate(
            ficha if isinstance(ficha, dict) else ficha.model_dump())
        veredicto = resultado["veredicto"]
        Veredicto.model_validate(
            veredicto if isinstance(veredicto, dict) else veredicto.model_dump())


def test_p11_todas_las_citas_recortan_el_texto_canonico(lote):
    """Si esta prueba cae, el auditor no puede verificar nada."""
    for correlation_id, caso in lote.contexto.casos.items():
        for cita in caso.citas:
            assert caso.texto[cita.offset_inicio:cita.offset_fin] == cita.cita, (
                caso.cv_id, cita.fuente)
            assert cita.correlation_id == correlation_id


def test_p12_el_candidato_llega_al_grafo_como_referencia_opaca(lote):
    """R7: ni el grafo ni el modelo ven nombre ni documento."""
    for caso in lote.contexto.casos.values():
        assert caso.candidato_ref.startswith("cand_")
        nombre = caso.ficha_json["persona"].get("nombre", "")
        if nombre:
            assert nombre not in caso.candidato_ref


def test_p13_el_auditor_bloquea_la_inyeccion(lote):
    bloqueados = {c["cv_id"] for c in lote.candidatos()
                  if (c["veredicto"] or {}).get("estado") == "bloqueado"}
    assert {"INJ-01", "INJ-02", "INJ-04"} <= bloqueados


def test_p14_el_staging_es_determinista(lote):
    primero = lote.staging["staging_id"]
    assert primero == lote._armar_staging()["staging_id"]
    assert len(lote.staging["top"]) <= 6          # R6, seis solo por R5


def test_p15_los_casos_evaluados_esperan_a_una_persona(lote):
    for payload in lote.interrupciones.values():
        assert payload["tipo"] == "lista_corta"
    # Los bloqueados por el auditor NO generan interrupción: el grafo los para.
    detenidos = {c["cv_id"] for c in lote.detenidos()}
    assert len(lote.interrupciones) + len(detenidos) == len(lote.estado_casos)


def test_p15b_un_caso_detenido_no_desaparece_y_trae_su_razon(lote):
    """H-5: el portal los presenta en vez de dejar que se pierdan."""
    detenidos = lote.detenidos()
    assert {"INJ-01", "INJ-02", "INJ-04"} <= {c["cv_id"] for c in detenidos}
    for caso in detenidos:
        assert caso["razon_parada"], f"{caso['cv_id']} detenido sin razón registrada"
        assert caso["veredicto"]["razon"]


# -------------------------------------------------------------- decisiones
def test_p16_el_ciclo_completo_cierra_y_deja_la_cadena_integra():
    servicio = ServicioLote(DATA)
    servicio.cargar()
    servicio.ejecutar()
    aprobados = servicio.decidir_lista(
        decision="aprobar", aprobador="prueba@grupo3", razon="Top revisado")["aprobados"]
    assert aprobados

    # Segunda compuerta por candidato aprobado.
    for cv_id in aprobados:
        servicio.decidir_mensaje(cv_id=cv_id, decision="aprobar",
                                 aprobador="prueba@grupo3", razon="Texto revisado")

    resumen = servicio.resumen()
    assert resumen["pendientes_aprobacion"] == 0
    assert resumen["por_estado"].get("cerrado") == len(aprobados)
    assert servicio.evidencia()["integra"] is True
    servicio.cerrar()


def test_p17_ningun_caso_queda_sin_decision_registrada():
    """Los que no entran al Top reciben `rechazar` con razón, no silencio."""
    servicio = ServicioLote(DATA)
    servicio.cargar()
    servicio.ejecutar()
    total = len(servicio.estado_casos)
    detenidos = len(servicio.detenidos())
    r = servicio.decidir_lista(decision="aprobar", aprobador="prueba@grupo3",
                               razon="Top revisado")
    # Cada caso que llegó a la compuerta recibe decisión; los detenidos por el
    # auditor ya tienen su razón de parada registrada.
    assert len(r["reanudados"]) == total - detenidos
    estados = servicio.resumen()["por_estado"]
    assert estados.get("lista_rechazada", 0) == len(r["reanudados"]) - len(r["aprobados"])
    servicio.cerrar()


def test_p18_ajustar_exige_candidatos_y_los_valida():
    servicio = ServicioLote(DATA)
    servicio.cargar()
    servicio.ejecutar()
    with pytest.raises(ValueError):
        servicio.decidir_lista(decision="ajustar", aprobador="p@g", razon="r",
                               cv_ids_aprobados=[])
    with pytest.raises(ValueError):
        servicio.decidir_lista(decision="ajustar", aprobador="p@g", razon="r",
                               cv_ids_aprobados=["CV-999"])
    servicio.cerrar()


def test_p19_no_se_salta_la_primera_compuerta():
    """Aprobar el mensaje antes que la lista debe fallar, no colarse."""
    servicio = ServicioLote(DATA)
    servicio.cargar()
    servicio.ejecutar()
    with pytest.raises(ValueError, match="lista corta"):
        servicio.decidir_mensaje(cv_id="CV-001", decision="aprobar",
                                 aprobador="p@g", razon="r")
    with pytest.raises(ValueError):
        servicio.decidir_mensaje(cv_id="CV-999", decision="aprobar",
                                 aprobador="p@g", razon="r")
    servicio.cerrar()


def test_p20_el_registro_encadena_cada_entrada(lote):
    entradas = lote.evidencia()["entradas"]
    assert len(entradas) > 1
    assert entradas[0]["hash_previo"] == "GENESIS"
    for previa, siguiente in zip(entradas, entradas[1:]):
        assert siguiente["hash_previo"] == previa["hash_entrada"]
