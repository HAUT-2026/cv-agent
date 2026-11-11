"""Reglas de negocio R1 a R13 del Hito 2 (tabla B3), como funciones puras.

Una función pura recibe datos y devuelve un resultado: no lee archivos, no llama a la API
y no modifica sus argumentos. Cada función devuelve un dict con la clave "regla" y el
resultado, para que el motor lo escriba tal cual en el decision_log.

Principio del diseño (A5): ninguna excepción termina en descarte automático. Abstenerse no
es descartar: el caso pasa a revisión humana y sigue en cola.
"""
import copy
import json
from datetime import date, timedelta

from .comun import HOY_REF, idx_hoy, mes_idx, normalizar, seudonimizar
from .diccionario import acredita_concepto, clasificar_termino, termino_conocido

TIPOS_VALIDOS = ("empleo", "freelance")          # pasantías y voluntariado no cuentan (supuesto, ver README)
NIVELES_MCER = ["A1", "A2", "B1", "B2", "C1", "C2"]
NIVELES_ALTOS_DECLARADOS = {"avanzado", "fluido", "nativo", "bilingue"}
NIVELES_BAJOS_DECLARADOS = {"basico", "intermedio", "principiante"}


# ===================================================================== R1
def r1_consentimiento(ficha: dict) -> dict:
    """R1 · Sin consentimiento registrado no se procesa; el caso queda en espera (S2, E9)."""
    registrado = (ficha.get("consentimiento") or {}).get("registrado") is True
    return {"regla": "R1", "procesar": registrado,
            "ruta": "ok" if registrado else "en_espera_consentimiento"}


# ===================================================================== R2
def r2_formato(ficha: dict) -> dict:
    """R2 · Solo PDF o DOCX con capa de texto recuperable; si no, carga manual (S1, E1)."""
    arch = ficha.get("archivo") or {}
    formato_ok = str(arch.get("formato", "")).lower() in ("pdf", "docx")
    texto_ok = (arch.get("caracteres_extraidos") or 0) > 0
    ok = formato_ok and texto_ok
    motivo = None if ok else ("formato_no_admitido" if not formato_ok else "sin_capa_de_texto")
    return {"regla": "R2", "admitido": ok, "ruta": "ok" if ok else "carga_manual", "motivo": motivo}


# ===================================================================== R11
def r11_experiencia_efectiva(experiencia: list, hoy: date = HOY_REF, tipos_validos=TIPOS_VALIDOS) -> dict:
    """R11 · Se cuentan meses calendario únicos: los periodos solapados no se suman dos veces.

    Si las fechas no permiten un cálculo fiable (faltan, están invertidas o el propio CV
    declara fechas distintas para el mismo cargo) el resultado es no fiable y pasa a revisión humana.
    """
    ref = idx_hoy(hoy)
    intervalos, nominales, motivos = [], 0, []
    for e in experiencia:
        if e.get("tipo") not in tipos_validos:
            continue
        cargo = e.get("cargo", "?")
        try:
            ini = mes_idx(e["inicio"])
            fin = mes_idx(e["fin"]) if e.get("fin") else ref
        except (KeyError, ValueError, AttributeError):
            motivos.append(f"fechas ilegibles en «{cargo}»")
            continue
        if fin < ini:
            motivos.append(f"fecha de fin anterior al inicio en «{cargo}»")
            continue
        for alt in e.get("fechas_alternas", []):
            if (alt.get("inicio"), alt.get("fin")) != (e["inicio"], e.get("fin")):
                motivos.append(f"«{cargo}» declara {e['inicio']}→{e.get('fin') or 'actual'} y "
                               f"{alt.get('inicio')}→{alt.get('fin') or 'actual'} en {alt.get('fuente', 'otra sección')}")
        intervalos.append((ini, fin))
        nominales += fin - ini
    meses = _union_meses(intervalos)
    return {"regla": "R11", "meses_efectivos": meses, "meses_nominales": nominales,
            "solapamiento_meses": nominales - meses, "fiable": not motivos, "motivos": motivos,
            "ruta": "ok" if not motivos else "revision_humana"}


def _union_meses(intervalos: list) -> int:
    total, actual = 0, None
    for a, b in sorted(intervalos):
        if actual is None:
            actual = [a, b]
        elif a <= actual[1]:
            actual[1] = max(actual[1], b)
        else:
            total += actual[1] - actual[0]
            actual = [a, b]
    if actual:
        total += actual[1] - actual[0]
    return total


# ===================================================================== R3
def r3_requisitos_excluyentes(ficha: dict, vacante: dict, diccionario: dict, hoy: date = HOY_REF) -> dict:
    """R3 · Evalúa cada requisito obligatorio de la vacante vigente.

    Estados por requisito:
      cumple         acreditado en el CV
      incumple       el CV muestra que no lo cumple
      no_acreditado  declarado sin evidencia (E5: «inglés avanzado» sin certificado). Distinto de «incumple» (S5)
      por_confirmar  falta entrada en el diccionario, fechas no fiables o contradicción (S4, S6)

    Ruta resultante: algún incumple → no_apto_declarado (visible, NO se descarta);
    si no, algún no_acreditado/por_confirmar → bandeja (revisión humana); si no, evaluable.
    """
    estados, detalle, por_equivalencia = {}, {}, []
    for req in vacante["requisitos"]:
        if req.get("tipo") != "obligatorio":
            continue
        cat = req["categoria"]
        if cat == "experiencia":
            est, det = _req_experiencia(ficha, req, diccionario, hoy)
        elif cat == "habilidad":
            est, det = _req_habilidad(ficha, req, diccionario)
        elif cat == "educacion":
            est, det = _req_educacion(ficha, req, diccionario, hoy)
        elif cat == "idioma":
            est, det = _req_idioma(ficha, req)
        else:
            est, det = "por_confirmar", {"motivo": f"categoría sin regla: {cat}"}
        estados[req["id"]], detalle[req["id"]] = est, det
        if det.get("por_equivalencia"):
            por_equivalencia.append(req["id"])
    if "incumple" in estados.values():
        ruta = "no_apto_declarado"
    elif {"no_acreditado", "por_confirmar"} & set(estados.values()):
        ruta = "bandeja"
    else:
        ruta = "evaluable"
    return {"regla": "R3", "vacante_version": vacante["version"], "estados": estados, "detalle": detalle,
            "por_equivalencia": por_equivalencia, "ruta": ruta}


def _experiencias_por_relevancia(ficha: dict, diccionario: dict, concepto: str):
    relevantes, indeterminadas, validas = [], [], []
    for e in ficha.get("experiencia", []):
        if e.get("tipo") not in TIPOS_VALIDOS:
            continue
        validas.append(e)
        clases = []
        for t in e.get("tecnologias", []):
            c = clasificar_termino(diccionario, concepto, t)
            if c["estado"] == "sin_entrada" and termino_conocido(diccionario, t):
                continue  # p. ej. «PostgreSQL» no dice nada sobre el lenguaje: no es una tecnología desconocida
            clases.append(c)
        if any(c["estado"] == "acredita" for c in clases):
            relevantes.append(e)
        elif any(c["estado"] in ("sin_entrada", "debil") for c in clases):
            indeterminadas.append(e)
    return relevantes, indeterminadas, validas


def _req_experiencia(ficha, req, diccionario, hoy):
    concepto, minimo = req["concepto"], req["min_anios"] * 12
    rel, ind, todas = _experiencias_por_relevancia(ficha, diccionario, concepto)
    r_rel, r_ind, r_todas = (r11_experiencia_efectiva(x, hoy) for x in (rel, rel + ind, todas))
    det = {"meses_relevantes": r_rel["meses_efectivos"], "meses_requeridos": minimo,
           "meses_con_indeterminadas": r_ind["meses_efectivos"], "meses_totales": r_todas["meses_efectivos"]}
    if not (r_rel["fiable"] and r_todas["fiable"]):
        det["motivo"] = "fechas_no_fiables"
        det["detalle_r11"] = r_rel["motivos"] + r_todas["motivos"]
        return "por_confirmar", det
    declarado = ((ficha.get("declarado") or {}).get("anios_experiencia") or 0) * 12
    if declarado - r_todas["meses_efectivos"] >= 12:
        det["motivo"] = "contradiccion_experiencia"
        det["meses_declarados"] = int(declarado)
        det["meses_nominales"] = r_todas["meses_nominales"]
        return "por_confirmar", det
    if r_rel["meses_efectivos"] >= minimo:
        terminos = [t for e in rel for t in e.get("tecnologias", [])]
        det["por_equivalencia"] = acredita_concepto(diccionario, concepto, terminos)["por_equivalencia"]
        return "cumple", det
    if r_ind["meses_efectivos"] >= minimo:
        det["motivo"] = "tecnologia_sin_entrada_en_diccionario"
        return "por_confirmar", det
    det["motivo"] = "meses_insuficientes_o_sin_tecnologia_requerida"
    return "incumple", det


def _terminos_del_cv(ficha: dict) -> list:
    t = list(ficha.get("habilidades", []))
    for e in ficha.get("experiencia", []):
        t += e.get("tecnologias", [])
    return t


def _req_habilidad(ficha, req, diccionario):
    r = acredita_concepto(diccionario, req["concepto"], _terminos_del_cv(ficha))
    return ("cumple" if r["acredita"] else "incumple"), {"terminos_usados": r["terminos_usados"],
                                                          "por_equivalencia": r["por_equivalencia"]}


def _req_educacion(ficha, req, diccionario, hoy):
    afines = [normalizar(p) for p in req.get("palabras_afines", [])]
    aceptados = {normalizar(t) for t in req.get("titulos_aceptados", [])}
    edu = ficha.get("educacion", [])
    profesionales = [e for e in edu if e.get("nivel") == "profesional"]
    for e in profesionales:
        n = normalizar(e["titulo"])
        if n in aceptados or any(p in n for p in afines):
            return "cumple", {"titulo": e["titulo"]}
    if profesionales:
        return "por_confirmar", {"motivo": "titulo_de_otra_area_afinidad_por_validar", "titulo": profesionales[0]["titulo"]}
    if any(e.get("nivel") == "tecnologo" and any(p in normalizar(e["titulo"]) for p in afines) for e in edu):
        return "por_confirmar", {"motivo": "tecnologo_afin_por_validar"}
    rel, _, _ = _experiencias_por_relevancia(ficha, diccionario, "Java")
    meses = r11_experiencia_efectiva(rel, hoy)["meses_efectivos"]
    if meses >= req.get("experiencia_equivalente_meses", 60):
        return "por_confirmar", {"motivo": "sin_titulo_experiencia_equivalente_por_validar", "meses_relevantes": meses}
    return "incumple", {"motivo": "sin_titulo_y_experiencia_insuficiente", "meses_relevantes": meses}


def _req_idioma(ficha, req):
    nombres = {"ingles", "english"} if normalizar(req["idioma"]) in ("ingles", "english") else {normalizar(req["idioma"])}
    minimo = NIVELES_MCER.index(req["nivel_minimo"])
    for i in ficha.get("idiomas", []):
        if normalizar(i["idioma"]) not in nombres:
            continue
        nivel_txt = str(i["nivel"]).strip()
        acreditado = normalizar(i.get("acreditacion", "ninguna")) in ("certificado", "prueba")
        if nivel_txt.upper() in NIVELES_MCER:
            alto = NIVELES_MCER.index(nivel_txt.upper()) >= minimo
        elif normalizar(nivel_txt) in NIVELES_ALTOS_DECLARADOS:
            alto = True
        elif normalizar(nivel_txt) in NIVELES_BAJOS_DECLARADOS:
            alto = False
        else:
            return "por_confirmar", {"motivo": "nivel_no_reconocido", "nivel": nivel_txt}
        if not alto:
            return "incumple", {"nivel": nivel_txt}
        if acreditado:
            return "cumple", {"nivel": nivel_txt, "acreditacion": i.get("acreditacion")}
        return "no_acreditado", {"nivel": nivel_txt, "motivo": "nivel_declarado_sin_certificado_ni_prueba"}
    return "incumple", {"motivo": "idioma_no_declarado"}


# ===================================================================== R4
def r4_cobertura(cobertura: float, contradiccion_material: bool = False, umbral: float = 0.70) -> dict:
    """R4 · Cobertura de evidencia < 0,70 o contradicción material → sin Top 5 automático, revisión humana (S10)."""
    entra = cobertura >= umbral and not contradiccion_material
    return {"regla": "R4", "entra_top5_automatico": entra, "ruta": "ranking" if entra else "revision_humana",
            "cobertura": cobertura, "umbral": umbral, "contradiccion_material": contradiccion_material}


# ===================================================================== R5
def r5_empate(puntajes_desc: list, tolerancia: float = 0.02) -> dict:
    """R5 · Si la diferencia entre el 5.º y el 6.º es ≤ 0,02 se presentan seis y decide el reclutador (S7, E8).

    `puntajes_desc` debe venir ordenado de mayor a menor.
    """
    if len(puntajes_desc) < 6:
        return {"regla": "R5", "empate": False, "diferencia": None, "presentar": min(5, len(puntajes_desc))}
    dif = round(puntajes_desc[4] - puntajes_desc[5], 6)
    empate = dif <= tolerancia
    return {"regla": "R5", "empate": empate, "diferencia": dif, "presentar": 6 if empate else 5}


# ===================================================================== R6
def r6_tamano_lista(n_evaluables: int, empate_r5: bool) -> dict:
    """R6 · Hasta cinco candidatos; nunca se completa con perfiles no evaluables; seis solo por R5."""
    n = min(5, n_evaluables)
    if empate_r5 and n_evaluables >= 6:
        n = 6
    aviso = None if n_evaluables >= 5 else f"Solo hay {n_evaluables} candidato(s) con evaluación suficiente; decide el reclutador."
    return {"regla": "R6", "n_propuestos": n, "aviso": aviso}


# ===================================================================== R7
CAMPOS_PERSONA_SENSIBLES = ["nombre", "sexo", "edad", "fecha_nacimiento", "foto", "direccion", "barrio",
                            "nacionalidad", "documento_identidad", "email", "telefono", "estado_civil",
                            "colegio", "origen_etnico", "salud", "discapacidad", "religion",
                            "orientacion_politica", "vida_sexual", "afiliacion_sindical", "datos_biometricos"]


def r7_anonimizar(ficha: dict, sal: str = "cvagent-sal-demo") -> dict:
    """R7 · Enmascara datos personales y proxies ANTES de puntuar. El modelo recibe solo la ficha anónima.

    Se enmascaran los campos sensibles de `persona`, la institución y el año de grado (proxies de nivel
    socioeconómico y edad) y toda aparición del nombre en el texto libre. Se conserva un ID seudonimizado.
    """
    original = ficha.get("persona", {})
    nombre = original.get("nombre", "")
    enmascarados = sorted(c for c in CAMPOS_PERSONA_SENSIBLES if original.get(c) not in (None, "", False))
    anonima = copy.deepcopy(ficha)
    anonima["persona"] = {"id_seudonimo": seudonimizar(original.get("documento_identidad", nombre), sal),
                          "ciudad": original.get("ciudad")}
    for ed in anonima.get("educacion", []):
        if ed.get("institucion"):
            ed["institucion"] = "[INSTITUCION]"
            enmascarados.append("educacion.institucion")
        if ed.get("anio_fin") is not None:
            ed["anio_fin"] = None
            enmascarados.append("educacion.anio_fin")
    fragmentos = [p for p in nombre.split() if len(p) >= 3]
    anonima = _borrar_nombre(anonima, fragmentos)
    return {"regla": "R7", "ficha_anonima": anonima, "campos_enmascarados": sorted(set(enmascarados))}


def _borrar_nombre(obj, fragmentos):
    if isinstance(obj, str):
        for f in fragmentos:
            obj = obj.replace(f, "[NOMBRE]")
        return obj
    if isinstance(obj, list):
        return [_borrar_nombre(x, fragmentos) for x in obj]
    if isinstance(obj, dict):
        return {k: _borrar_nombre(v, fragmentos) for k, v in obj.items()}
    return obj


# ===================================================================== R8
def r8_vigencia(indice: dict, vacante_id: str, version_usada: int | None = None) -> dict:
    """R8 · Solo se usa la versión vigente de la vacante; la versión usada se registra en la decisión."""
    vigente = indice[vacante_id]["vigente"]
    usada = vigente if version_usada is None else version_usada
    return {"regla": "R8", "vacante_id": vacante_id, "version_vigente": vigente, "version_usada": usada,
            "es_vigente": usada == vigente, "ruta": "ok" if usada == vigente else "bloquear_version_obsoleta"}


# ===================================================================== R9
def _dias_habiles(desde: date, hasta: date) -> int:
    d, n = desde, 0
    while d < hasta:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def r9_retencion(fecha_recepcion: date, hoy: date, plazo_dias: int = 365, solicitud_titular: bool = False,
                 en_espera_consentimiento: bool = False) -> dict:
    """R9 · Se eliminan el CV y la ficha vencido el plazo de retención, a solicitud del titular, o si
    pasan 5 días hábiles sin consentimiento (S2). El plazo real lo fija la política de retención:
    365 días es un SUPUESTO para el ejercicio. No se consideran festivos."""
    if solicitud_titular:
        motivo = "solicitud_del_titular"
    elif en_espera_consentimiento and _dias_habiles(fecha_recepcion, hoy) > 5:
        motivo = "consentimiento_no_recibido_en_5_dias_habiles"
    elif (hoy - fecha_recepcion).days > plazo_dias:
        motivo = "plazo_de_retencion_vencido"
    else:
        motivo = None
    return {"regla": "R9", "eliminar": motivo is not None, "motivo": motivo}


# ===================================================================== R10
def r10_doble_aprobacion(aprobaciones: dict) -> dict:
    """R10 · Nada sale al candidato sin aprobación registrada del reclutador (lista Y mensaje)."""
    def valida(a):
        return isinstance(a, dict) and a.get("aprobado") is True and bool(a.get("reclutador")) and bool(a.get("fecha"))
    faltan = [k for k in ("lista", "mensaje") if not valida(aprobaciones.get(k))]
    return {"regla": "R10", "puede_enviar": not faltan, "faltan_aprobaciones": faltan}


# ===================================================================== R12
def r12_deduplicar(postulaciones: list, sal: str = "cvagent-sal-demo") -> dict:
    """R12 · Dos postulaciones del mismo candidato a la misma vacante: prevalece la más reciente.

    La identidad se decide por documento de identidad seudonimizado (E10). Si no hay documento pero
    coincide correo o teléfono, hay duda → revisión humana. Cada postulación:
    {cv_id, documento_identidad, email, telefono, vacante_id, fecha_recepcion (ISO)}.
    """
    grupos, sin_doc = {}, []
    for p in postulaciones:
        if p.get("documento_identidad"):
            grupos.setdefault((seudonimizar(p["documento_identidad"], sal), p["vacante_id"]), []).append(p)
        else:
            sin_doc.append(p)
    vigentes, duplicados, dudas = [], [], []
    for (_, _), g in sorted(grupos.items()):
        g = sorted(g, key=lambda p: (p["fecha_recepcion"], p["cv_id"]))
        ganador = g[-1]
        vigentes.append(ganador["cv_id"])
        duplicados += [{"cv_id": p["cv_id"], "duplicado_de": ganador["cv_id"]} for p in g[:-1]]
    for p in sin_doc:
        coincide = [o["cv_id"] for o in postulaciones if o["cv_id"] != p["cv_id"] and o["vacante_id"] == p["vacante_id"]
                    and ((p.get("email") and o.get("email") == p["email"]) or (p.get("telefono") and o.get("telefono") == p["telefono"]))]
        if coincide:
            dudas.append({"cv_id": p["cv_id"], "posible_duplicado_de": coincide})
        else:
            vigentes.append(p["cv_id"])
    return {"regla": "R12", "vigentes": sorted(vigentes), "duplicados": duplicados, "dudas": dudas}


# ===================================================================== R13
def r13_cambio_vacante(version_vigente: int, version_nueva: int, aprobacion_hiring_manager: bool,
                       aprobacion_rrhh: bool, cvs_evaluados: list) -> dict:
    """R13 · Cuando cambian los criterios con evaluaciones en curso se congela el ranking. Solo con la
    aprobación del hiring manager Y de RR. HH. se reevalúan todos los CV contra la versión nueva;
    sin aprobación sigue vigente la versión anterior (S9, E11)."""
    if aprobacion_hiring_manager and aprobacion_rrhh:
        return {"regla": "R13", "ranking": "reevaluando", "version_vigente": version_nueva,
                "version_anterior": version_vigente, "reevaluar": sorted(cvs_evaluados)}
    return {"regla": "R13", "ranking": "congelado", "version_vigente": version_vigente,
            "version_anterior": None, "reevaluar": []}
