"""Pruebas unitarias de las reglas R1 a R13 con datos sintéticos (no dependen del dataset de 40 CV)."""
import copy
import json
import random
from datetime import date

import pytest

from reglas import (armar_staging, cargar_indice, cargar_vacante, evaluar_caso, r1_consentimiento, r2_formato,
                    r3_requisitos_excluyentes, r4_cobertura, r5_empate, r6_tamano_lista, r7_anonimizar, r8_vigencia,
                    r9_retencion, r10_doble_aprobacion, r11_experiencia_efectiva, r12_deduplicar, r13_cambio_vacante)

HOY = date(2026, 11, 10)


def job(inicio, fin, tecnologias=("Java", "PostgreSQL", "API REST"), tipo="empleo", cargo="Dev"):
    return {"cargo": cargo, "organizacion": "Org", "tipo": tipo, "inicio": inicio, "fin": fin, "tecnologias": list(tecnologias)}


@pytest.fixture
def ficha():
    """Ficha de ejemplo que cumple todo: 48 meses de Java, inglés B2 certificado, título de sistemas."""
    return {"cv_id": "T-1", "persona": {"nombre": "Ana María Pérez Gómez", "sexo": "F", "documento_identidad": "CC 1.000.000.001",
                                       "email": "ana@correo-ejemplo.com", "telefono": "+57 300 111 2222", "ciudad": "Bogotá",
                                       "direccion": "Cra 7 # 10-20", "barrio": "Chapinero", "edad": 31, "foto": True,
                                       "estado_civil": "Soltera", "colegio": "Colegio San Carlos", "nacionalidad": "Colombiana"},
            "resumen": "Ana María Pérez es desarrolladora backend con 4 años de experiencia.",
            "experiencia": [job("2022-11", None)],
            "educacion": [{"titulo": "Ingeniería de Sistemas", "institucion": "Universidad Central Andina", "anio_fin": 2020, "nivel": "profesional"}],
            "habilidades": ["Java", "PostgreSQL", "API REST"],
            "idiomas": [{"idioma": "Inglés", "nivel": "B2", "acreditacion": "certificado"}],
            "declarado": {"anios_experiencia": 4},
            "consentimiento": {"registrado": True, "fecha": "2026-11-01"},
            "archivo": {"formato": "pdf", "caracteres_extraidos": 1200}, "fecha_recepcion": "2026-11-01"}


# ------------------------------------------------------------------ R1
def test_r1_con_consentimiento(ficha):
    assert r1_consentimiento(ficha)["procesar"] is True


@pytest.mark.parametrize("consent", [{"registrado": False}, {}, None])
def test_r1_sin_consentimiento_no_se_procesa(ficha, consent):
    ficha["consentimiento"] = consent
    r = r1_consentimiento(ficha)
    assert r["procesar"] is False and r["ruta"] == "en_espera_consentimiento"


# ------------------------------------------------------------------ R2
def test_r2_pdf_con_texto(ficha):
    assert r2_formato(ficha)["admitido"] is True


def test_r2_pdf_escaneado_va_a_carga_manual(ficha):
    ficha["archivo"]["caracteres_extraidos"] = 0
    r = r2_formato(ficha)
    assert r["ruta"] == "carga_manual" and r["motivo"] == "sin_capa_de_texto"


def test_r2_formato_no_admitido(ficha):
    ficha["archivo"]["formato"] = "jpg"
    assert r2_formato(ficha)["motivo"] == "formato_no_admitido"


def test_r2_docx_admitido(ficha):
    ficha["archivo"]["formato"] = "docx"
    assert r2_formato(ficha)["admitido"] is True


# ------------------------------------------------------------------ R3
def test_r3_todo_cumple(ficha, vacante_v1, dic):
    r = r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)
    assert r["ruta"] == "evaluable" and set(r["estados"].values()) == {"cumple"}
    assert r["vacante_version"] == 1


def test_r3_ingles_avanzado_sin_certificado_es_no_acreditado_no_incumplido(ficha, vacante_v1, dic):
    ficha["idiomas"] = [{"idioma": "Inglés", "nivel": "Avanzado", "acreditacion": "ninguna"}]
    r = r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)
    assert r["estados"]["REQ-05"] == "no_acreditado"
    assert r["ruta"] == "bandeja"          # revisión humana, NO descarte


def test_r3_ingles_a2_incumple_y_queda_visible_como_no_apto_declarado(ficha, vacante_v1, dic):
    ficha["idiomas"] = [{"idioma": "Inglés", "nivel": "A2", "acreditacion": "ninguna"}]
    r = r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)
    assert r["estados"]["REQ-05"] == "incumple" and r["ruta"] == "no_apto_declarado"


def test_r3_kotlin_sobre_jvm_acredita_java_por_equivalencia(ficha, vacante_v1, dic):
    ficha["experiencia"] = [job("2022-11", None, tecnologias=("Kotlin sobre JVM", "PostgreSQL", "API REST"))]
    r = r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)
    assert r["estados"]["REQ-01"] == "cumple" and r["por_equivalencia"] == ["REQ-01"]


def test_r3_tecnologia_sin_entrada_en_diccionario_queda_por_confirmar_y_no_excluye(ficha, vacante_v1, dic):
    ficha["experiencia"] = [job("2022-11", None, tecnologias=("Scala", "PostgreSQL", "API REST"))]
    r = r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)
    assert r["estados"]["REQ-01"] == "por_confirmar" and r["ruta"] == "bandeja"


def test_r3_python_no_equivale_a_java(ficha, vacante_v1, dic):
    ficha["experiencia"] = [job("2020-01", None, tecnologias=("Python", "Django", "PostgreSQL", "API REST"))]
    assert r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)["estados"]["REQ-01"] == "incumple"


def test_r3_exactamente_36_meses_cumple_y_35_no(ficha, vacante_v1, dic):
    ficha["experiencia"] = [job("2023-11", None)]
    ficha["declarado"] = {"anios_experiencia": 3}
    assert r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)["estados"]["REQ-01"] == "cumple"
    ficha["experiencia"] = [job("2023-12", None)]
    ficha["declarado"] = {"anios_experiencia": 2}
    assert r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)["estados"]["REQ-01"] == "incumple"


def test_r3_sin_titulo_con_experiencia_equivalente_va_a_revision(ficha, vacante_v1, dic):
    ficha["educacion"] = [{"titulo": "Bachiller académico", "institucion": "Colegio", "anio_fin": 2010, "nivel": "bachiller"}]
    ficha["experiencia"] = [job("2020-11", None)]
    ficha["declarado"] = {"anios_experiencia": 6}
    assert r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)["estados"]["REQ-04"] == "por_confirmar"


def test_r3_sin_titulo_y_poca_experiencia_incumple(ficha, vacante_v1, dic):
    ficha["educacion"] = [{"titulo": "Bachiller académico", "institucion": "Colegio", "anio_fin": 2010, "nivel": "bachiller"}]
    assert r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)["estados"]["REQ-04"] == "incumple"


def test_r3_sin_base_de_datos_o_sin_rest_incumple(ficha, vacante_v1, dic):
    ficha["habilidades"], ficha["experiencia"] = ["Java"], [job("2022-11", None, tecnologias=("Java",))]
    r = r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)
    assert r["estados"]["REQ-02"] == "incumple" and r["estados"]["REQ-03"] == "incumple"


def test_r3_contradiccion_entre_declarado_y_calculado_pasa_a_revision(ficha, vacante_v1, dic):
    ficha["declarado"] = {"anios_experiencia": 7}      # declara 7 años y el calendario único da 4
    r = r3_requisitos_excluyentes(ficha, vacante_v1, dic, HOY)
    assert r["estados"]["REQ-01"] == "por_confirmar" and r["detalle"]["REQ-01"]["motivo"] == "contradiccion_experiencia"


def test_r3_la_vacante_v2_exige_5_anios(ficha, vacante_v2, dic):
    assert r3_requisitos_excluyentes(ficha, vacante_v2, dic, HOY)["estados"]["REQ-01"] == "incumple"


# ------------------------------------------------------------------ R4
@pytest.mark.parametrize("cob,contra,entra", [(0.69, False, False), (0.70, False, True), (0.95, False, True), (0.95, True, False)])
def test_r4_umbral_de_cobertura(cob, contra, entra):
    r = r4_cobertura(cob, contra)
    assert r["entra_top5_automatico"] is entra and r["ruta"] == ("ranking" if entra else "revision_humana")


# ------------------------------------------------------------------ R5
def test_r5_caso_e8_del_hito():
    assert r5_empate([0.9, 0.88, 0.86, 0.84, 0.781, 0.779])["empate"] is True


def test_r5_diferencia_exactamente_0_02_cuenta_como_empate():
    r = r5_empate([0.9, 0.9, 0.9, 0.9, 0.80, 0.78])
    assert r["empate"] is True and r["presentar"] == 6


def test_r5_sin_empate():
    r = r5_empate([0.9, 0.9, 0.9, 0.9, 0.80, 0.77])
    assert r["empate"] is False and r["presentar"] == 5


def test_r5_menos_de_seis_candidatos_no_hay_empate():
    assert r5_empate([0.9, 0.8, 0.7])["empate"] is False


# ------------------------------------------------------------------ R6
def test_r6_nunca_completa_con_perfiles_no_evaluables():
    r = r6_tamano_lista(3, False)
    assert r["n_propuestos"] == 3 and "3 candidato" in r["aviso"]


def test_r6_maximo_cinco_y_seis_solo_por_r5():
    assert r6_tamano_lista(10, False)["n_propuestos"] == 5
    assert r6_tamano_lista(10, True)["n_propuestos"] == 6
    assert r6_tamano_lista(5, True)["n_propuestos"] == 5


# ------------------------------------------------------------------ R7
VALORES_SENSIBLES = ["Ana María", "Pérez", "Gómez", "CC 1.000.000.001", "ana@correo-ejemplo.com", "+57 300 111 2222",
                     "Cra 7 # 10-20", "Chapinero", "Soltera", "Colegio San Carlos", "Universidad Central Andina"]


def test_r7_no_queda_ningun_dato_sensible_ni_proxy(ficha):
    texto = json.dumps(r7_anonimizar(ficha)["ficha_anonima"], ensure_ascii=False)
    for v in VALORES_SENSIBLES:
        assert v not in texto, f"quedó «{v}» en la ficha anónima"


def test_r7_borra_el_nombre_del_texto_libre(ficha):
    assert "[NOMBRE]" in r7_anonimizar(ficha)["ficha_anonima"]["resumen"]


def test_r7_conserva_lo_que_se_evalua(ficha):
    a = r7_anonimizar(ficha)["ficha_anonima"]
    assert a["experiencia"] == ficha["experiencia"] and a["habilidades"] == ficha["habilidades"]


def test_r7_seudonimo_estable_y_distinto_por_persona(ficha):
    a = r7_anonimizar(ficha)["ficha_anonima"]["persona"]["id_seudonimo"]
    assert a == r7_anonimizar(ficha)["ficha_anonima"]["persona"]["id_seudonimo"]
    otra = copy.deepcopy(ficha)
    otra["persona"]["documento_identidad"] = "CC 1.000.000.002"
    assert a != r7_anonimizar(otra)["ficha_anonima"]["persona"]["id_seudonimo"]


def test_r7_no_modifica_la_ficha_original(ficha):
    antes = json.dumps(ficha, sort_keys=True)
    r7_anonimizar(ficha)
    assert json.dumps(ficha, sort_keys=True) == antes


def test_r7_reporta_los_campos_enmascarados(ficha):
    campos = r7_anonimizar(ficha)["campos_enmascarados"]
    assert {"nombre", "sexo", "edad", "foto", "direccion", "estado_civil", "educacion.institucion"} <= set(campos)


# ------------------------------------------------------------------ R8
def test_r8_version_vigente_y_obsoleta(data_dir):
    indice = cargar_indice(data_dir)
    assert r8_vigencia(indice, "VAC-001")["version_usada"] == 1
    r = r8_vigencia(indice, "VAC-001", version_usada=2)
    assert r["es_vigente"] is False and r["ruta"] == "bloquear_version_obsoleta"


def test_vacantes_versionadas_no_se_pisan(data_dir):
    assert cargar_vacante(data_dir, "VAC-001")["version"] == 1          # sin version → vigente
    assert cargar_vacante(data_dir, "VAC-001", 2)["requisitos"][0]["min_anios"] == 5
    assert cargar_vacante(data_dir, "VAC-001", 1)["requisitos"][0]["min_anios"] == 3
    with pytest.raises(KeyError):
        cargar_vacante(data_dir, "VAC-001", 9)


# ------------------------------------------------------------------ R9
def test_r9_solicitud_del_titular():
    assert r9_retencion(date(2026, 11, 1), HOY, solicitud_titular=True)["motivo"] == "solicitud_del_titular"


def test_r9_plazo_vencido_y_vigente():
    assert r9_retencion(date(2025, 11, 1), HOY)["eliminar"] is True
    assert r9_retencion(date(2026, 1, 1), HOY)["eliminar"] is False


def test_r9_cinco_dias_habiles_sin_consentimiento():
    recibido = date(2026, 11, 2)    # lunes
    assert r9_retencion(recibido, date(2026, 11, 9), en_espera_consentimiento=True)["eliminar"] is False   # 5 días hábiles
    assert r9_retencion(recibido, date(2026, 11, 10), en_espera_consentimiento=True)["eliminar"] is True   # 6


# ------------------------------------------------------------------ R10
def test_r10_exige_aprobacion_de_lista_y_mensaje():
    ok = {"aprobado": True, "reclutador": "rec-1", "fecha": "2026-11-10T10:00"}
    assert r10_doble_aprobacion({"lista": ok, "mensaje": ok})["puede_enviar"] is True
    assert r10_doble_aprobacion({"lista": ok})["faltan_aprobaciones"] == ["mensaje"]
    assert r10_doble_aprobacion({})["puede_enviar"] is False


def test_r10_aprobacion_sin_reclutador_no_vale():
    mala = {"aprobado": True, "reclutador": "", "fecha": "2026-11-10"}
    assert r10_doble_aprobacion({"lista": mala, "mensaje": mala})["puede_enviar"] is False


# ------------------------------------------------------------------ R11
def test_r11_no_suma_dos_veces_los_solapes():
    r = r11_experiencia_efectiva([job("2020-01", "2022-01"), job("2021-01", "2023-01")], HOY)
    assert r["meses_efectivos"] == 36 and r["meses_nominales"] == 48 and r["solapamiento_meses"] == 12


def test_r11_caso_e3_siete_anios_en_cuatro():
    jobs = [job("2022-11", None), job("2023-05", "2025-05"), job("2024-05", "2025-05")]
    r = r11_experiencia_efectiva(jobs, HOY)
    assert r["meses_efectivos"] == 48 and r["meses_nominales"] == 84


def test_r11_periodos_separados_si_se_suman():
    assert r11_experiencia_efectiva([job("2020-01", "2021-01"), job("2022-01", "2023-01")], HOY)["meses_efectivos"] == 24


def test_r11_pasantia_y_voluntariado_no_cuentan():
    r = r11_experiencia_efectiva([job("2020-01", "2022-01", tipo="pasantia"), job("2019-01", "2023-01", tipo="voluntariado")], HOY)
    assert r["meses_efectivos"] == 0


def test_r11_fechas_contradictorias_no_son_fiables():
    j = job("2019-01", "2024-12")
    j["fechas_alternas"] = [{"fuente": "resumen", "inicio": "2021-01", "fin": "2024-12"}]
    r = r11_experiencia_efectiva([j], HOY)
    assert r["fiable"] is False and r["ruta"] == "revision_humana" and "resumen" in r["motivos"][0]


def test_r11_fechas_ilegibles_o_invertidas_no_son_fiables():
    assert r11_experiencia_efectiva([job("2020-13", "2021-01")], HOY)["fiable"] is False
    assert r11_experiencia_efectiva([job("2022-01", "2021-01")], HOY)["fiable"] is False
    assert r11_experiencia_efectiva([{"tipo": "empleo", "cargo": "x"}], HOY)["fiable"] is False


def test_r11_actualidad_usa_la_fecha_de_referencia():
    assert r11_experiencia_efectiva([job("2026-01", None)], date(2026, 11, 10))["meses_efectivos"] == 10


# ------------------------------------------------------------------ R12
def post(cv, doc, fecha, vac="VAC-001", email=None, tel=None):
    return {"cv_id": cv, "documento_identidad": doc, "email": email, "telefono": tel, "vacante_id": vac, "fecha_recepcion": fecha}


def test_r12_prevalece_la_mas_reciente():
    r = r12_deduplicar([post("A", "CC 1", "2026-10-05"), post("B", "CC 1", "2026-11-02"), post("C", "CC 2", "2026-11-01")])
    assert r["vigentes"] == ["B", "C"] and r["duplicados"] == [{"cv_id": "A", "duplicado_de": "B"}]


def test_r12_misma_persona_en_otra_vacante_no_es_duplicado():
    r = r12_deduplicar([post("A", "CC 1", "2026-10-05", vac="V1"), post("B", "CC 1", "2026-11-02", vac="V2")])
    assert r["duplicados"] == [] and r["vigentes"] == ["A", "B"]


def test_r12_el_documento_se_compara_normalizado():
    r = r12_deduplicar([post("A", "CC 1.012.345", "2026-10-05"), post("B", "cc 1.012.345 ", "2026-11-02")])
    assert len(r["duplicados"]) == 1


def test_r12_sin_documento_pero_mismo_correo_es_duda_no_descarte():
    r = r12_deduplicar([post("A", None, "2026-10-05", email="x@y.com"), post("B", "CC 9", "2026-11-02", email="x@y.com")])
    assert r["dudas"] == [{"cv_id": "A", "posible_duplicado_de": ["B"]}] and r["duplicados"] == []


def test_r12_empate_exacto_de_fecha_es_determinista():
    r = r12_deduplicar([post("B", "CC 1", "2026-11-02"), post("A", "CC 1", "2026-11-02")])
    assert r["vigentes"] == ["B"]


# ------------------------------------------------------------------ R13
def test_r13_sin_aprobacion_se_congela_y_sigue_la_version_anterior():
    r = r13_cambio_vacante(1, 2, aprobacion_hiring_manager=True, aprobacion_rrhh=False, cvs_evaluados=["B", "A"])
    assert r["ranking"] == "congelado" and r["version_vigente"] == 1 and r["reevaluar"] == []


def test_r13_con_ambas_aprobaciones_se_reevalua_todo():
    r = r13_cambio_vacante(1, 2, True, True, ["B", "A"])
    assert r["ranking"] == "reevaluando" and r["version_vigente"] == 2 and r["reevaluar"] == ["A", "B"]


# ------------------------------------------------------------------ motor y staging
def test_motor_orden_de_las_reglas(ficha, vacante_v1, dic):
    ficha["consentimiento"] = {"registrado": False}
    ficha["archivo"]["caracteres_extraidos"] = 0
    assert evaluar_caso(ficha, vacante_v1, dic, HOY)["ruta"] == "en_espera_consentimiento"      # R1 antes que R2
    ficha["consentimiento"] = {"registrado": True}
    assert evaluar_caso(ficha, vacante_v1, dic, HOY)["ruta"] == "carga_manual"


def test_motor_solo_entrega_ficha_anonima_a_los_evaluables(ficha, vacante_v1, dic):
    r = evaluar_caso(ficha, vacante_v1, dic, HOY)
    assert r["ruta"] == "evaluable" and "nombre" not in r["ficha_anonima"]["persona"]
    ficha["idiomas"] = [{"idioma": "Inglés", "nivel": "A2", "acreditacion": "ninguna"}]
    assert evaluar_caso(ficha, vacante_v1, dic, HOY)["ficha_anonima"] is None


def evals(n=8, base=0.9):
    return [{"cv_id": f"CV-{i:03d}", "puntaje": round(base - 0.05 * i, 3), "cobertura": 0.9} for i in range(n)]


def test_staging_es_determinista_sin_importar_el_orden_de_entrada():
    datos = evals()
    a = armar_staging(datos, "VAC-001", 1)
    barajado = datos[:]
    random.Random(7).shuffle(barajado)
    assert armar_staging(barajado, "VAC-001", 1) == a and [t["cv_id"] for t in a["top"]] == [f"CV-{i:03d}" for i in range(5)]


def test_staging_desempate_exacto_por_cv_id():
    datos = [{"cv_id": c, "puntaje": 0.8, "cobertura": 0.9} for c in ("C", "A", "B")]
    assert [t["cv_id"] for t in armar_staging(datos, "V", 1)["top"]] == ["A", "B", "C"]


def test_staging_r4_saca_del_top_a_los_de_baja_cobertura():
    datos = evals() + [{"cv_id": "ZZZ", "puntaje": 0.99, "cobertura": 0.5}]
    s = armar_staging(datos, "VAC-001", 1)
    assert "ZZZ" not in [t["cv_id"] for t in s["top"]] and s["revision_humana_r4"] == ["ZZZ"]


def test_staging_r5_presenta_seis_si_hay_empate():
    datos = evals()
    for i, p in enumerate([0.95, 0.90, 0.85, 0.80, 0.781, 0.779, 0.60, 0.55]):   # E8 del Hito: 0,781 vs 0,779
        datos[i]["puntaje"] = p
    s = armar_staging(datos, "VAC-001", 1)
    assert s["empate_r5"] is True and len(s["top"]) == 6


def test_staging_r6_menos_de_cinco_no_se_completa():
    s = armar_staging(evals(3), "VAC-001", 1)
    assert len(s["top"]) == 3 and s["aviso_r6"]


def test_staging_queda_versionado_con_la_version_de_vacante():
    assert armar_staging(evals(), "VAC-001", 1)["staging_id"] != armar_staging(evals(), "VAC-001", 2)["staging_id"]
    assert armar_staging(evals(), "VAC-001", 1)["inmutable"] is True
