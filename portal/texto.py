"""Texto canónico sanitizado y anclaje de citas (Rol 4).

El texto que devuelve este módulo es la ÚNICA referencia contra la que se
miden los offsets de `CitationRef`. Nadie lo vuelve a normalizar después:
`CitationRef.verify_against()` recorta por posición y compara carácter a
carácter, así que un `.lower()` posterior invalida todas las citas del caso.

Procedencia, en orden:
  1. `data/cvs_pdf/<cv_id>.pdf` extraído con pdfplumber — lo que leerá el
     agente real del Rol 3.
  2. Si el PDF no existe o no tiene capa de texto (caso E1, CV-036), se
     renderiza determinísticamente desde `data/cvs_json/<cv_id>.json`.

La procedencia queda registrada en `AuditMetadata.fuente`, porque una ficha
construida sobre el gemelo JSON no es la misma evidencia que una construida
sobre el PDF: el PDF contiene las trampas (texto oculto, fechas
contradictorias) que el gemelo no tiene.
"""

from __future__ import annotations

import json
from pathlib import Path


class TextoNoDisponible(RuntimeError):
    """El CV no tiene PDF legible ni gemelo JSON."""


def _normalizar(texto: str) -> str:
    """Única normalización permitida, y se aplica ANTES de medir offsets."""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    lineas = [linea.rstrip() for linea in texto.split("\n")]
    salida: list[str] = []
    for linea in lineas:
        if linea or (salida and salida[-1]):
            salida.append(linea)
    return "\n".join(salida).strip()


def _desde_pdf(ruta: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""
    try:
        with pdfplumber.open(ruta) as pdf:
            partes = [(pagina.extract_text() or "") for pagina in pdf.pages]
    except Exception:  # noqa: BLE001  un PDF ilegible es dato, no excepción
        return ""
    return _normalizar("\n\n".join(partes))


def _desde_json(ficha: dict) -> str:
    """Render determinista del gemelo JSON. Mismo orden en cada corrida."""
    p = ficha.get("persona", {})
    lineas = [p.get("nombre", ""), ""]
    if ficha.get("resumen"):
        lineas += ["PERFIL", ficha["resumen"], ""]

    if ficha.get("experiencia"):
        lineas.append("EXPERIENCIA")
        for e in ficha["experiencia"]:
            fin = e.get("fin") or "Actualidad"
            lineas.append(f"{e.get('cargo','')} - {e.get('organizacion','')} "
                          f"({e.get('inicio','')} - {fin}) [{e.get('tipo','')}]")
            for d in e.get("descripcion", []):
                lineas.append(f"  {d}")
            if e.get("tecnologias"):
                lineas.append("  Tecnologias: " + ", ".join(e["tecnologias"]))
        lineas.append("")

    if ficha.get("educacion"):
        lineas.append("EDUCACION")
        for ed in ficha["educacion"]:
            lineas.append(f"{ed.get('titulo','')} - {ed.get('institucion','')} "
                          f"({ed.get('anio_fin','')}) [{ed.get('nivel','')}]")
        lineas.append("")

    if ficha.get("habilidades"):
        lineas += ["HABILIDADES", ", ".join(ficha["habilidades"]), ""]

    if ficha.get("idiomas"):
        lineas.append("IDIOMAS")
        for i in ficha["idiomas"]:
            acre = i.get("acreditacion", "ninguna")
            detalle = f" ({i['detalle']})" if i.get("detalle") else ""
            lineas.append(f"{i.get('idioma','')}: {i.get('nivel','')} "
                          f"[acreditacion: {acre}]{detalle}")
        lineas.append("")

    otros = ficha.get("otros", [])
    if otros:
        lineas.append("INFORMACION ADICIONAL")
        for o in otros:
            if isinstance(o, dict):
                # Es exactamente donde se esconden las notas dirigidas al
                # sistema: tiene que llegar al texto canónico tal cual, para
                # que el auditor pueda verla y bloquear.
                if o.get("seccion"):
                    lineas.append(str(o["seccion"]))
                lineas.append(str(o.get("texto", "")))
            else:
                lineas.append(str(o))

    return _normalizar("\n".join(lineas))


def cargar_texto(cv_id: str, base_dir: str | Path = "data") -> tuple[str, str]:
    """Devuelve (texto_canonico, procedencia).

    procedencia ∈ {"pdf", "gemelo_json"} y viaja hasta `AuditMetadata.fuente`.
    """
    base = Path(base_dir)
    # Los CV de inyección viven en su propia carpeta y no cuentan entre los 40.
    carpetas = [base, base / "extras_inyeccion"]

    for carpeta in carpetas:
        pdf = carpeta / "cvs_pdf" / f"{cv_id}.pdf"
        if pdf.exists():
            texto = _desde_pdf(pdf)
            if texto:
                return texto, "pdf"

    gemelo = next((c / "cvs_json" / f"{cv_id}.json" for c in carpetas
                   if (c / "cvs_json" / f"{cv_id}.json").exists()), None)
    if gemelo is None:
        raise TextoNoDisponible(f"{cv_id}: sin PDF legible ni gemelo JSON")
    texto = _desde_json(json.loads(gemelo.read_text(encoding="utf-8")))
    if not texto:
        raise TextoNoDisponible(f"{cv_id}: el gemelo JSON no produjo texto")
    return texto, "gemelo_json"


def anclar(texto: str, cita: str) -> tuple[int, int] | None:
    """Ancla una subcadena literal y devuelve (inicio, fin), o None.

    Es la pieza que hace verificable la evidencia, y la razón por la que a un
    modelo se le pide la SUBCADENA EXACTA y nunca las posiciones: un modelo no
    cuenta caracteres, pero sí puede copiar una frase. Las posiciones las
    calcula este código.

    Devuelve None en dos casos, y los dos son hallazgos para el auditor:
      - la frase no está en el texto  → el modelo la inventó
      - aparece más de una vez        → la cita no identifica nada
    """
    if not cita:
        return None
    inicio = texto.find(cita)
    if inicio < 0:
        return None
    if texto.find(cita, inicio + 1) >= 0:
        return None
    return inicio, inicio + len(cita)


def anclar_ampliando(texto: str, cita: str, margen: int = 40) -> tuple[int, int] | None:
    """Como `anclar`, pero si la cita es ambigua la amplía con su contexto.

    Para frases cortas e inevitablemente repetidas ("Java", "B2") no sirve
    rechazar la cita: se toma la primera ocurrencia junto con el resto de su
    línea, que sí es única.
    """
    directo = anclar(texto, cita)
    if directo:
        return directo
    inicio = texto.find(cita)
    if inicio < 0:
        return None
    ini_linea = texto.rfind("\n", 0, inicio) + 1
    fin_linea = texto.find("\n", inicio)
    fin_linea = len(texto) if fin_linea < 0 else fin_linea
    linea = texto[ini_linea:fin_linea].strip()
    if linea and anclar(texto, linea):
        i = texto.find(linea)
        return i, i + len(linea)
    ventana = texto[max(0, inicio - margen):min(len(texto), inicio + len(cita) + margen)]
    anclado = anclar(texto, ventana)
    return anclado


__all__ = ["TextoNoDisponible", "anclar", "anclar_ampliando", "cargar_texto"]
