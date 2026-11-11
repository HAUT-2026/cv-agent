"""
Sanitización del CV (Rol 3). Dos pasos:

1. Limpieza Unicode (en `cv_json`): NFC, sin caracteres de ancho cero ni de control.
   Corre ANTES de construir el texto canónico, así que no desplaza ningún offset.
2. `detectar_indicios_inyeccion`: busca patrones sospechosos sobre el texto
   canónico y devuelve indicios CON OFFSETS.

Qué NO hace: la anonimización de R7 (nombre, edad, género y sus proxies), que es
del Rol 2. Orden: validar JSON → R7 (Rol 2) → limpieza → texto canónico → indicios.

Política: un indicio NO detiene el flujo aquí. Se guarda en el estado y el auditor
lo convierte en hallazgo bloqueante. Así el caso trampa llega hasta el auditor y la
demo puede mostrar "el auditor lo bloqueó y por qué" (punto 3 de la sección 7).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .texto import TextoCanonico

_INVISIBLES = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ------------------------------------------------------------------ detección
@dataclass(frozen=True)
class IndicioInyeccion:
    patron: str        # nombre del patrón, no la regex
    inicio: int
    fin: int
    texto: str
    fuente: str = "texto_canonico"   # o "texto_oculto" (offsets relativos a ese campo)


# Español e inglés. Calibrado con 5 estilos (CV propio de desarrollo y el primer dataset del Rol 2).
# Prueba ciega con el dataset de 40 CV + 4 extras: detectó 4 de 5 inyecciones nuevas y 0 falsos
# positivos; la que faltaba (dirigida a la "AI reviewer", ignorar "requirements", ocultar la nota)
# agregó los patrones dirigido_al_sistema (saludo/rol de IA), "requirements" y ocultar_instruccion.
# Criterio de diseño: verbos en imperativo/infinitivo + objeto, para no disparar con CV legítimos
# ("Obtuve la máxima calificación", "Asigné tareas a 100 usuarios", "Marco de 100 indicadores").
_PATRONES: dict[str, re.Pattern] = {
    "ignorar_instrucciones": re.compile(
        r"\b(ignora\w*|ignore|olvida\w*|omit(e|ir|a)|disregard|forget|skip)\b.{0,40}?"
        r"\b(instruc\w*|criterio\w*|regla\w*|requisito\w*|revisi[oó]n\w*|prompt|instructions?|criteria|rules|"
        r"requirements?|guidelines?|policy|policies)\b"
        r"|\b(previous|prior|anteriores?)\s+(instructions?|instrucciones)\b"
        r"|\b(instructions?|instrucciones)\s+(are|is|son|quedan|est[aá]n)\s+(void|nul\w*|anulad\w*|invalid\w*|sin efecto)",
        re.I),
    "dirigido_al_sistema": re.compile(
        r"\b(nota|mensaje|instrucci[oó]n|aviso)\s+(para|al)\s+(el\s+)?(sistema|evaluador|modelo|ia|agente|reclutador autom)\w*"
        r"|\b(system|assistant|sistema)\s+(message|prompt|mensaje)\s*:"
        r"|(^|\n|\.\s)\s*(SYSTEM|SISTEMA)\s*:"
        r"|\b(dear|hello|hi|hola|estimad[oa]|querid[oa])\s+(ai|a\.i\.|ia|bot|llm|gpt|modelo|model|assistant|asistente)\b"
        r"|\b(ai|ia|llm|automated|autom[aá]tic[oa])\s+(reviewer|screener|evaluator|evaluador|revisor|reclutador)\b", re.I),
    "autoridad_falsa": re.compile(
        r"\b(verificaci[oó]n|validaci[oó]n|nota|aprobaci[oó]n)\s+(interna|oficial)\b"
        r"|\b(ya\s+fue|ha\s+sido|already(\s+been)?|has\s+been)\s+(validad\w*|aprobad\w*|verificad\w*|pre-?aprobad\w*|approved|validated|verified)\b",
        re.I),
    "pedir_puntaje": re.compile(
        r"\b(asigna|asignar|as[ií]gnale|otorga|otorgar|dale|m[aá]rcal[oa]|marcar(lo|la)?\s+como|"
        r"assign|give|rate|mark\s+(it|him|her|them|this|as))\b.{0,50}?"
        r"\b(m[aá]xim\w*|perfect\w*|100|10/10|highest|top|apto|aprobad\w*)\b"
        r"|\b(rank|place|put|pon|ubica|clasifica)\s+(this|the|me|him|her|a\s+este|este|esta|al)\s*"
        r"(candidate|applicant|profile|cv|candidat[oa]|perfil)?\b.{0,15}?\b(first|top|#?1|primer[oa]?|de\s+primer[oa])\b", re.I),
    "no_descartar": re.compile(
        r"\bno\s+(lo|la|los|las)?\s*descart\w*|\bdo\s+not\s+(reject|discard|filter)", re.I),
    "ocultar_instruccion": re.compile(
        r"\b(do\s+not|don'?t|never|no)\s+(mention|reveal|report|disclose|menciones|reveles|reportes|incluyas|mencionar)\b"
        r".{0,25}?\b(this|esta|este|la|the)\s+(note|instruction|message|nota|instrucci[oó]n|mensaje)\b", re.I),
    "salida_forzada": re.compile(
        r"\b(output|responde|devuelve|imprime|return|print)\s+(exactly|exactamente|solo|[uú]nicamente|only)\b"
        r"|\{\s*\"(decision|decisi[oó]n|score|puntaje|veredicto|verdict)\"\s*:", re.I),
    "extraer_criterios": re.compile(
        r"\b(enumera|revela|muestra|lista|dime|imprime|reveal|list|show|print|tell\s+me)\b.{0,25}?"
        r"\b(todos|todas|all|tus|your|the)\b.{0,20}?"
        r"\b(criterio\w*|umbral\w*|instruc\w*|prompt|pesos|reglas|criteria|thresholds?|instructions|weights|rules)\b",
        re.I),
    "rol_del_modelo": re.compile(
        r"\b(eres un|act[uú]a como|you are (a|an|now)|act as|system prompt|as an ai)\b", re.I),
    "marcadores_de_prompt": re.compile(r"(<\|.*?\|>|\[/?INST\]|###\s*(system|instruction)|</?system>)", re.I),
}

UMBRAL_REPETICION = 4  # misma palabra clave técnica 4 o más veces en habilidades


def _buscar(texto: str, fuente: str) -> list[IndicioInyeccion]:
    out = []
    for nombre, rx in _PATRONES.items():
        for m in rx.finditer(texto):
            out.append(IndicioInyeccion(nombre, m.start(), m.end(), m.group(0).strip(), fuente))
    return out


def detectar_indicios_inyeccion(tc: TextoCanonico, invisibles_quitados: int = 0,
                                texto_oculto: str | None = None) -> list[IndicioInyeccion]:
    indicios = _buscar(tc.texto, "texto_canonico")

    # Relleno de palabras clave: "Python Python Python..." para engañar al ranking
    habilidades = [tc.texto[s.inicio:s.fin].lower() for s in tc.segmentos if s.ruta.startswith("habilidades[")]
    for palabra, n in Counter(habilidades).items():
        if n >= UMBRAL_REPETICION:
            seg = next(s for s in tc.segmentos if tc.texto[s.inicio:s.fin].lower() == palabra)
            indicios.append(IndicioInyeccion("relleno_palabras_clave", seg.inicio, seg.fin, palabra))

    if invisibles_quitados >= 3:
        indicios.append(IndicioInyeccion("caracteres_invisibles", 0, 0, f"{invisibles_quitados} caracteres invisibles"))

    if texto_oculto and texto_oculto.strip():
        # Que exista texto oculto ya es un indicio, diga lo que diga (B7: texto oculto).
        indicios.append(IndicioInyeccion("texto_oculto", 0, len(texto_oculto), texto_oculto[:80], "texto_oculto"))
        indicios += _buscar(texto_oculto, "texto_oculto")

    return sorted(indicios, key=lambda i: (i.fuente != "texto_canonico", i.inicio))


# ----------------------------------------------------------------- proxies (R7)
# Provisional para el auditor: señales de atributos protegidos que sobrevivieron a la
# minimización. No bloquea por sí solo; la decisión es del auditor y de R7 (Rol 2).
_PROXIES: dict[str, re.Pattern] = {
    "maternidad_paternidad": re.compile(r"\b(licencia\s+de\s+)?(maternidad|paternidad|embaraz\w*|maternity|paternity|pregnan\w*)\b", re.I),
    "estado_civil": re.compile(r"\b(estado\s+civil|casad[oa]|solter[oa]|divorciad[oa]|viud[oa]|married|single|divorced)\b", re.I),
    "familia": re.compile(r"\b(padre|madre|father|mother)\s+de\s+\w+\s+hij\w*|\b(hijos|children)\b|cuidado\s+familiar", re.I),
    "edad": re.compile(r"\b\d{2}\s+años(\s+de\s+edad)?\s*[,.]|\bedad\b|\b\d{2}\s+years\s+old\b", re.I),
    "religion_origen": re.compile(r"\b(religi[oó]n|nacionalidad|nationality|religion)\b", re.I),
}


def detectar_proxies(tc: TextoCanonico) -> list[IndicioInyeccion]:
    out = []
    for nombre, rx in _PROXIES.items():
        for m in rx.finditer(tc.texto):
            out.append(IndicioInyeccion(nombre, m.start(), m.end(), m.group(0).strip(), "proxy_r7"))
    return sorted(out, key=lambda i: i.inicio)
