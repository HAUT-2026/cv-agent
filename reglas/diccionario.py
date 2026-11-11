"""Diccionario de equivalencias versionado (herramienta `consultar_equivalencias` del Hito 2, B7).

Estructura del archivo data/diccionario_equivalencias.json:
  version: str
  equivalencias: { concepto: [ {termino, peso}, ... ] }
  no_equivalentes: { concepto: [terminos conocidos que NO equivalen] }

Un término que no aparece ni en `equivalencias` ni en `no_equivalentes` del concepto es
"sin entrada" (S4 / E4): el requisito queda «por confirmar» y NO excluye.
"""
import json
from .comun import normalizar

PESO_MINIMO_EQUIVALENCIA = 0.8  # por debajo de este peso el término no acredita el requisito


def cargar_diccionario(ruta: str) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def consultar_equivalencias(diccionario: dict, conceptos: list) -> list:
    """Entrada: conceptos (requisito_ids). Salida: filas {requisito, equivalente, peso, version}."""
    filas = []
    for concepto in conceptos:
        for e in diccionario["equivalencias"].get(concepto, []):
            filas.append({"requisito": concepto, "equivalente": e["termino"], "peso": e["peso"],
                          "version": diccionario["version"]})
    return filas


def clasificar_termino(diccionario: dict, concepto: str, termino: str) -> dict:
    """Devuelve {estado: 'acredita'|'debil'|'no_equivale'|'sin_entrada', peso, termino_canonico}."""
    t = normalizar(termino)
    for e in diccionario["equivalencias"].get(concepto, []):
        if normalizar(e["termino"]) == t:
            estado = "acredita" if e["peso"] >= PESO_MINIMO_EQUIVALENCIA else "debil"
            return {"estado": estado, "peso": e["peso"], "termino_canonico": e["termino"]}
    for n in diccionario.get("no_equivalentes", {}).get(concepto, []):
        if normalizar(n) == t:
            return {"estado": "no_equivale", "peso": 0.0, "termino_canonico": n}
    return {"estado": "sin_entrada", "peso": None, "termino_canonico": None}


def termino_conocido(diccionario: dict, termino: str) -> bool:
    """¿El término aparece en algún concepto del diccionario? Sirve para no tratar «PostgreSQL» como una
    tecnología desconocida cuando se evalúa Java: solo lo realmente ausente es «sin entrada» (S4)."""
    t = normalizar(termino)
    for lista in diccionario["equivalencias"].values():
        if any(normalizar(e["termino"]) == t for e in lista):
            return True
    return any(normalizar(n) == t for lista in diccionario.get("no_equivalentes", {}).values() for n in lista)


def acredita_concepto(diccionario: dict, concepto: str, terminos: list) -> dict:
    """¿Alguno de los términos acredita el concepto? Devuelve {acredita, por_equivalencia, terminos_usados}."""
    usados, por_equiv = [], False
    for t in terminos:
        c = clasificar_termino(diccionario, concepto, t)
        if c["estado"] == "acredita":
            usados.append(c["termino_canonico"])
            if c["peso"] < 1.0:
                por_equiv = True
    exacto = any(clasificar_termino(diccionario, concepto, t)["peso"] == 1.0 for t in terminos)
    return {"acredita": bool(usados), "por_equivalencia": bool(usados) and not exacto and por_equiv,
            "terminos_usados": usados}
