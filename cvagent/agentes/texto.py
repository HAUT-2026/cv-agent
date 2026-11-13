"""
Texto canónico y localización de citas.

Como los CV llegan en JSON y no como documento, "el texto del CV" no existe hasta
que lo construimos (`cv_json.construir_texto_canonico`), de forma DETERMINISTA: el mismo
JSON produce siempre el mismo texto, carácter por carácter. Ese texto es:

  1. lo que ve el analista (y lo que cita),
  2. lo que el auditor usa para verificar cada cita por offset,
  3. lo que la bandeja (Rol 4) muestra con la cita resaltada.

Regla de oro: el LLM nunca calcula offsets. Devuelve la cita literal y
`localizar_cita` la ubica en el texto canónico.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional


UMBRAL_APROXIMADA = 0.90  # similitud mínima para aceptar una cita no literal
_NUMEROS = re.compile(r"\d+(?:[.,]\d+)?")


# ------------------------------------------------------------------ estructuras
@dataclass(frozen=True)
class Segmento:
    """Un campo del JSON dentro del texto canónico."""
    ruta: str          # p. ej. "experiencia[1].descripcion"
    inicio: int        # offset del VALOR (sin la etiqueta)
    fin: int


@dataclass
class TextoCanonico:
    id_cv: str
    texto: str
    segmentos: list[Segmento] = field(default_factory=list)

    def campo_en(self, offset: int) -> Optional[str]:
        for s in self.segmentos:
            if s.inicio <= offset < s.fin:
                return s.ruta
        return None  # cae en una etiqueta o separador


@dataclass(frozen=True)
class CitaLocalizada:
    cita_pedida: str           # lo que devolvió el LLM
    inicio: int
    fin: int
    texto_real: str            # texto[inicio:fin], lo que de verdad dice el CV
    campo: Optional[str]       # ruta del JSON donde empieza
    cruza_campos: bool         # empieza en un campo y termina en otro
    metodo: str                # "exacta" | "normalizada" | "aproximada"
    similitud: float


# ---------------------------------------------------------------- localización
def _normalizar_con_mapa(s: str) -> tuple[str, list[int]]:
    """Minúsculas, sin tildes y espacios colapsados, conservando para cada
    carácter normalizado su posición en el texto original."""
    out: list[str] = []
    mapa: list[int] = []
    prev_espacio = False
    for i, ch in enumerate(s):
        base = unicodedata.normalize("NFD", ch)
        base = "".join(b for b in base if unicodedata.category(b) != "Mn").lower()
        if not base:
            continue
        if base.isspace():
            if prev_espacio:
                continue
            base, prev_espacio = " ", True
        else:
            prev_espacio = False
        for b in base:
            out.append(b)
            mapa.append(i)
    return "".join(out), mapa


def _resultado(tc: TextoCanonico, cita: str, ini: int, fin: int,
               metodo: str, sim: float) -> CitaLocalizada:
    campo_ini = tc.campo_en(ini)
    campo_fin = tc.campo_en(max(ini, fin - 1))
    return CitaLocalizada(
        cita_pedida=cita, inicio=ini, fin=fin, texto_real=tc.texto[ini:fin],
        campo=campo_ini, cruza_campos=(campo_ini != campo_fin), metodo=metodo,
        similitud=round(sim, 3),
    )


def localizar_cita(tc: TextoCanonico, cita: str,
                   umbral: float = UMBRAL_APROXIMADA) -> Optional[CitaLocalizada]:
    """Devuelve dónde está la cita en el texto canónico, o None si no aparece.
    None significa EVIDENCIA INVÁLIDA: el auditor debe tratarla como cita inventada."""
    cita = cita.strip()
    if not cita:
        return None

    # 0) campo completo: "R", "SQL" o "Inglés (B2)" en la lista de habilidades o idiomas.
    #    Va primero para no confundir "R" con la primera R del texto (p. ej. dentro de "REST").
    for seg in tc.segmentos:
        if tc.texto[seg.inicio:seg.fin] == cita:
            return _resultado(tc, cita, seg.inicio, seg.fin, "exacta", 1.0)
    if len(cita) < 3:
        return None   # fragmentos tan cortos solo valen como campo completo

    # 1) exacta
    i = tc.texto.find(cita)
    if i != -1:
        return _resultado(tc, cita, i, i + len(cita), "exacta", 1.0)

    # 2) normalizada (mayúsculas, tildes, espacios)
    tn, mapa = _normalizar_con_mapa(tc.texto)
    cn, _ = _normalizar_con_mapa(cita)
    j = tn.find(cn)
    if j != -1:
        ini, fin = mapa[j], mapa[j + len(cn) - 1] + 1
        return _resultado(tc, cita, ini, fin, "normalizada", 1.0)

    # 3) aproximada: ventana deslizante del tamaño de la cita (texto corto, es barato)
    n = len(cn)
    mejor, mejor_j = 0.0, -1
    sm = SequenceMatcher(autojunk=False)
    sm.set_seq2(cn)
    for k in range(0, max(1, len(tn) - n + 1)):
        if k > 0 and tn[k - 1] != " ":
            continue  # solo ventanas que arrancan en inicio de palabra
        sm.set_seq1(tn[k:k + n])
        if sm.quick_ratio() < umbral:
            continue
        r = sm.ratio()
        if r > mejor:
            mejor, mejor_j = r, k
    if mejor >= umbral:
        # Ajuste de bordes: mirar un poco alrededor de la mejor ventana y recortar
        # a donde realmente empiezan y terminan los caracteres que coinciden.
        holgura = max(5, n // 5)
        r0 = max(0, mejor_j - holgura)
        region = tn[r0:mejor_j + n + holgura]
        bloques = [b for b in SequenceMatcher(None, region, cn, autojunk=False)
                   .get_matching_blocks() if b.size > 0]
        ini_n = r0 + bloques[0].a
        fin_n = r0 + bloques[-1].a + bloques[-1].size - 1
        res = _resultado(tc, cita, mapa[ini_n], mapa[fin_n] + 1, "aproximada", mejor)
        # Las cifras no admiten aproximación: "12" vs "2" se parecen 99 % como texto
        # pero cambian por completo el hecho (años, personas, ms...).
        if _NUMEROS.findall(cita) != _NUMEROS.findall(res.texto_real):
            return None
        return res

    return None
