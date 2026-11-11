"""Motor de reglas (B1 del Hito 2, nivel 2 · regla fija).

Encadena las reglas en el orden del SDD (B4.1):
  R12 duplicados → R1 consentimiento → R2 formato → R11/R3 requisitos → R7 anonimización
y, al final del lote, R4 + R5 + R6 para armar el staging del Top 5.

Cada paso deja su resultado en `reglas`, listo para escribirse en el decision_log.
"""
import hashlib
import json
from datetime import date

from .comun import HOY_REF
from . import reglas as R


def evaluar_caso(ficha: dict, vacante: dict, diccionario: dict, hoy: date = HOY_REF) -> dict:
    """Aplica R1, R2, R3 (con R11) y R7 a un solo CV. Devuelve la ruta y el detalle de cada regla.

    ruta: en_espera_consentimiento | carga_manual | no_apto_declarado | bandeja | evaluable
    Solo `evaluable` pasa al agente analista, y siempre con la ficha anónima (R7).
    """
    resultado = {"cv_id": ficha["cv_id"], "vacante_id": vacante["vacante_id"], "vacante_version": vacante["version"],
                 "reglas": {}, "ruta": None, "estado_requisitos": {}, "meses_efectivos": None, "ficha_anonima": None}
    r1 = R.r1_consentimiento(ficha)
    resultado["reglas"]["R1"] = r1
    if not r1["procesar"]:
        resultado["ruta"] = r1["ruta"]
        return resultado
    r2 = R.r2_formato(ficha)
    resultado["reglas"]["R2"] = r2
    if not r2["admitido"]:
        resultado["ruta"] = r2["ruta"]
        return resultado
    todas = [e for e in ficha.get("experiencia", [])]
    r11 = R.r11_experiencia_efectiva(todas, hoy)
    resultado["reglas"]["R11"] = r11
    resultado["meses_efectivos"] = r11["meses_efectivos"]
    r3 = R.r3_requisitos_excluyentes(ficha, vacante, diccionario, hoy)
    resultado["reglas"]["R3"] = r3
    resultado["estado_requisitos"] = r3["estados"]
    resultado["ruta"] = r3["ruta"]
    if r3["ruta"] == "evaluable":
        r7 = R.r7_anonimizar(ficha)
        resultado["reglas"]["R7"] = {"regla": "R7", "campos_enmascarados": r7["campos_enmascarados"]}
        resultado["ficha_anonima"] = r7["ficha_anonima"]
    return resultado


def procesar_lote(fichas: list, vacante: dict, diccionario: dict, hoy: date = HOY_REF) -> dict:
    """Aplica R12 al lote completo y luego evalúa cada CV vigente. Devuelve {cv_id: resultado}."""
    postulaciones = [{"cv_id": f["cv_id"], "documento_identidad": f["persona"].get("documento_identidad"),
                      "email": f["persona"].get("email"), "telefono": f["persona"].get("telefono"),
                      "vacante_id": vacante["vacante_id"], "fecha_recepcion": f["fecha_recepcion"]} for f in fichas]
    r12 = R.r12_deduplicar(postulaciones)
    duplicados = {d["cv_id"]: d["duplicado_de"] for d in r12["duplicados"]}
    dudas = {d["cv_id"]: d["posible_duplicado_de"] for d in r12["dudas"]}
    salida = {}
    for f in fichas:
        if f["cv_id"] in duplicados:
            salida[f["cv_id"]] = {"cv_id": f["cv_id"], "ruta": "duplicado", "duplicado_de": duplicados[f["cv_id"]],
                                  "reglas": {"R12": r12}, "estado_requisitos": {}, "meses_efectivos": None}
        elif f["cv_id"] in dudas:
            salida[f["cv_id"]] = {"cv_id": f["cv_id"], "ruta": "bandeja", "motivo": "posible_duplicado",
                                  "reglas": {"R12": r12}, "estado_requisitos": {}, "meses_efectivos": None}
        else:
            salida[f["cv_id"]] = evaluar_caso(f, vacante, diccionario, hoy)
    return salida


def armar_staging(evaluaciones: list, vacante_id: str, vacante_version: int) -> dict:
    """Paso 9 del SDD: ordena y deja el Top 5 en staging inmutable y versionado.

    `evaluaciones`: [{cv_id, puntaje, cobertura, contradiccion_material}] que producen el analista y
    el auditor. Aquí no se calcula ningún puntaje: solo se aplican R4, R5 y R6.

    Orden determinista: puntaje descendente; si empatan exactamente, cv_id ascendente. El mismo
    conjunto de entrada, en cualquier orden, produce el mismo staging y el mismo hash.
    """
    elegibles, revision = [], []
    for e in evaluaciones:
        r4 = R.r4_cobertura(e["cobertura"], e.get("contradiccion_material", False))
        (elegibles if r4["entra_top5_automatico"] else revision).append(e)
    elegibles.sort(key=lambda e: (-round(e["puntaje"], 6), e["cv_id"]))
    r5 = R.r5_empate([e["puntaje"] for e in elegibles])
    r6 = R.r6_tamano_lista(len(elegibles), r5["empate"])
    top = [{"posicion": i + 1, "cv_id": e["cv_id"], "puntaje": e["puntaje"], "cobertura": e["cobertura"]}
           for i, e in enumerate(elegibles[:r6["n_propuestos"]])]
    cuerpo = {"vacante_id": vacante_id, "vacante_version": vacante_version, "top": top,
              "empate_r5": r5["empate"], "diferencia_5_6": r5["diferencia"], "aviso_r6": r6["aviso"],
              "revision_humana_r4": sorted(e["cv_id"] for e in revision)}
    canonico = json.dumps(cuerpo, sort_keys=True, ensure_ascii=False)
    return {**cuerpo, "staging_id": hashlib.sha256(canonico.encode()).hexdigest()[:16], "inmutable": True}
