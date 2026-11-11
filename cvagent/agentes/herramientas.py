"""
Herramientas que los agentes pueden llamar, y el registro central.

Cada herramienta declara nombre, descripción (la lee el LLM para decidir cuándo
usarla), parámetros en JSON Schema y la función que la ejecuta. Qué agente puede
usar cuál NO se decide aquí: lo decide la allowlist de cada agente en `agente.py`.
Así, "el auditor no puede llamar las herramientas del analista" es una regla
verificable en código, no una promesa del prompt.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable

from .criterios import Vacante
from .texto import TextoCanonico, localizar_cita


@dataclass
class ContextoCaso:
    """Lo que las herramientas pueden consultar. El LLM nunca lo ve directamente.
    `cv` es un `cv_json.CVJson` (el código acepta cualquier objeto con `.experiencia`)."""
    cv: Any
    tc: TextoCanonico
    vacante: Vacante


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict
    funcion: Callable[[dict, ContextoCaso], Any]

    def definicion(self) -> dict:
        """Formato `tools` del protocolo de OpenAI."""
        return {"type": "function", "function": {
            "name": self.nombre, "description": self.descripcion, "parameters": self.parametros}}


# --------------------------------------------------------------- analista
def _parece_requisito(texto: str, ctx: ContextoCaso):
    t = texto.lower().strip()
    if len(t) < 20:          # palabras sueltas ("MySQL") pueden ser evidencia legítima
        return None
    for r in ctx.vacante.requisitos:
        d = r.descripcion.lower()
        if t in d or d in t or SequenceMatcher(None, t, d).ratio() >= 0.75:
            return r
    return None


def _buscar_en_cv(args: dict, ctx: ContextoCaso) -> dict:
    texto = str(args.get("texto", ""))
    loc = localizar_cita(ctx.tc, texto)
    if loc is None:
        req = _parece_requisito(texto, ctx)
        if req is not None:
            # Error frecuente de modelos pequeños: buscar el REQUISITO en vez de la evidencia.
            return {"encontrada": False, "error_de_uso": True,
                    "aviso": (f"Buscaste el texto del requisito {req.id}, no una frase del CV. "
                              "Lee la hoja de vida, elige la frase que la persona escribió y que "
                              "demuestra (o no) ese requisito, y busca ESA frase. Si no hay ninguna "
                              "relacionada, el requisito es sin_evidencia.")}
    if loc is None:
        return {"encontrada": False,
                "aviso": "Ese texto NO aparece en la hoja de vida. No lo uses como cita. "
                         "Copia un fragmento literal del texto."}
    return {"encontrada": True, "texto_exacto_en_cv": loc.texto_real,
            "seccion": loc.campo, "metodo": loc.metodo}


# Respaldo provisional: la fuente principal son las equivalencias versionadas de la vacante.
# El diccionario oficial es del Rol 2; este bloque se elimina cuando exista.
_EQUIVALENCIAS: list[set[str]] = [
    {"postgresql", "postgres", "psql"},
    {"api rest", "apis rest", "restful", "rest api", "servicios rest"},
    {"kubernetes", "k8s"},
    {"aws", "amazon web services"},
    {"gcp", "google cloud", "google cloud platform"},
    {"javascript", "js"},
    {"ingeniería de sistemas", "ingeniería de software", "ingeniería informática",
     "ingeniería de computación"},
]


def _consultar_equivalencias(args: dict, ctx: ContextoCaso) -> dict:
    termino = str(args.get("termino", "")).strip()
    t = _norm(termino)
    # 1) Equivalencias OFICIALES y versionadas de la vacante (R8)
    for r in ctx.vacante.requisitos:
        grupo = r.equivalencias + r.titulos_aceptados
        if grupo and any(_norm(g) == t or (len(t) >= 3 and t in _norm(g)) for g in grupo):
            return {"termino": termino, "requisito": r.id, "equivalentes": r.equivalencias + r.titulos_aceptados,
                    "fuente": f"vacante {ctx.vacante.id_vacante} v{ctx.vacante.version}"}
    # 2) Respaldo provisional (se elimina cuando el Rol 2 publique su diccionario)
    for grupo in _EQUIVALENCIAS:
        if t in grupo:
            return {"termino": termino, "equivalentes": sorted(grupo - {t}), "fuente": "provisional"}
    return {"termino": termino, "equivalentes": [],
            "nota": "Sin equivalencias registradas: no asumas sinónimos."}


def _meses(aaaa_mm: str) -> int:
    a, m = aaaa_mm.split("-")
    return int(a) * 12 + int(m)


_CUENTAN = {"empleo", "freelance"}   # nota de REQ-01 en la vacante del equipo; ajustar a R11 oficial


def _union(intervalos: list[tuple[int, int]]) -> int:
    total, actual = 0, None
    for ini, fin in sorted(intervalos):
        if actual is None or ini > actual[1]:
            if actual:
                total += actual[1] - actual[0]
            actual = [ini, fin]
        else:
            actual[1] = max(actual[1], fin)
    return total + (actual[1] - actual[0] if actual else 0)


def _experiencia_por_cargo(args: dict, ctx: ContextoCaso, hoy: str = "2026-11") -> dict:
    """Provisional hasta tener R11 del Rol 2. Meses = fin − inicio (intervalo [inicio, fin)),
    'actual' = 2026-11, periodos solapados cuentan una vez. Coincide con el manifiesto del equipo."""
    cargos, cuentan, por_tipo = [], [], {}
    for i, e in enumerate(ctx.cv.experiencia):
        ini_s = getattr(e, "inicio", None) or e.fecha_inicio
        fin_s = getattr(e, "fin", None) if hasattr(e, "inicio") else e.fecha_fin
        tipo = getattr(getattr(e, "tipo", None), "value", None) or "empleo"
        ini, fin = _meses(ini_s), _meses(fin_s or hoy)
        cuenta = tipo in _CUENTAN
        cargos.append({"indice": i, "cargo": e.cargo, "tipo": tipo, "meses": fin - ini, "cuenta": cuenta})
        (cuentan if cuenta else por_tipo.setdefault(tipo, [])).append((ini, fin))
    total = _union(cuentan)
    return {"por_cargo": cargos, "total_meses_sin_solapes": total, "total_anios": round(total / 12, 2),
            "meses_que_no_cuentan": {t: _union(v) for t, v in por_tipo.items()},
            "nota": "Cuentan empleo y freelance sin solapes; pasantía, voluntariado y pausas no "
                    "(nota de la vacante). Cálculo provisional; el oficial es R11."}


# --------------------------------------------------------------- recuperación de evidencia
# "El código busca, el LLM juzga": a un modelo pequeño le cuesta ENCONTRAR la frase
# correcta, pero elige bien entre pocas candidatas. Coincidencia de términos, determinista.
_VACIAS = {"para", "como", "con", "del", "los", "las", "una", "uno", "por", "que", "sus", "desde",
           "sobre", "entre", "afines", "experiencia", "nivel", "minimo", "manejo", "conocimiento",
           # demasiado genéricas en esta vacante ("Analista de Datos e Integraciones"): sueltas
           # emparejan "modelos de datos" con "protección de datos". Como FRASE siguen contando
           # vía equivalencias ("protección de datos", "integración de sistemas").
           "datos", "sistemas", "otras", "otros", "herramientas", "efectiva", "roles", "similares"}
_RELACIONADOS = {
    "relacionales": {"sql", "postgresql", "postgres", "mysql", "oracle", "sqlserver", "mariadb"},
    "rest": {"api", "apis", "restful", "endpoints", "fastapi", "soap", "servicios"},
    "python": {"django", "fastapi", "flask", "pandas"},
    "docker": {"contenedores", "kubernetes", "k8s"},
    "nube": {"aws", "gcp", "azure", "cloud", "ecs", "lambda"},
    "ingles": {"english", "toefl", "ielts"},
    "ingenieria": {"ingeniero", "ingeniera", "sistemas", "software", "tecnologia", "tecnologo"},
    "backend": {"servidor", "servicios", "api", "apis"},
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _raiz(w: str) -> str:
    """Raíz simple: primeras 6 letras ("analisis"/"analista" → "analis",
    "integracion"/"integraciones" → "integr"). Suficiente para emparejar variantes."""
    return w[:6] if len(w) > 6 else w


def _terminos(texto: str) -> set[str]:
    return {_raiz(w) for w in re.findall(r"[a-z0-9+#]+", _norm(texto)) if len(w) >= 3 and w not in _VACIAS}


def _frases_del_cv(tc: TextoCanonico):
    for seg in tc.segmentos:
        valor = tc.texto[seg.inicio:seg.fin]
        for frase in re.split(r"(?<=[.!?])\s+", valor):
            if frase.strip():
                yield seg.ruta, frase.strip()


def claves_de_requisito(req) -> tuple[set[str], list[str]]:
    """Términos (con raíz) y frases de equivalencia de un requisito. La usan
    `frases_relacionadas` (para recuperar) y el auditor (para verificar relación)."""
    claves = _terminos(req.descripcion)
    for k, rel in _RELACIONADOS.items():
        if _raiz(k) in claves:
            claves |= {_raiz(x) for x in rel}
    frases_eq = [_norm(x) for x in req.equivalencias + req.titulos_aceptados]
    for x in frases_eq:
        claves |= _terminos(x)
    return claves, frases_eq


def relacion_con_requisito(texto: str, req) -> int:
    """Puntos de relación entre un texto y un requisito (0 = sin relación)."""
    claves, frases_eq = claves_de_requisito(req)
    fn = _norm(texto)
    puntos = len(claves & _terminos(texto))
    puntos += 2 * sum(1 for x in frases_eq if re.search(rf"(?<![a-z0-9]){re.escape(x)}(?![a-z0-9])", fn))
    return puntos


def _frases_relacionadas(args: dict, ctx: ContextoCaso) -> dict:
    rid = str(args.get("id_requisito", "")).strip()
    req = next((r for r in ctx.vacante.requisitos if r.id == rid), None)
    if req is None:
        return {"error": f"No existe el requisito {rid}. Usa los ids de la lista de la vacante."}
    claves, frases_eq = claves_de_requisito(req)
    puntuadas = []
    for i, (ruta, frase) in enumerate(_frases_del_cv(ctx.tc)):
        puntos = relacion_con_requisito(frase, req)
        if puntos:
            puntuadas.append((-puntos, i, ruta, frase))
    puntuadas.sort()
    frases = [{"texto": f, "seccion": r} for _, _, r, f in puntuadas[:5]]
    if not frases:
        return {"id_requisito": rid, "frases": [],
                "nota": "Ninguna frase del CV se relaciona con este requisito: probablemente sin_evidencia."}
    return {"id_requisito": rid, "frases": frases,
            "nota": "Frases literales del CV, de la más a la menos relacionada. Juzga tú si demuestran, "
                    "contradicen o no bastan para el requisito; cita las que uses tal cual."}


BUSCAR_EN_CV = Herramienta(
    "buscar_en_cv",
    "Verifica si un fragmento COPIADO DE LA HOJA DE VIDA aparece literalmente en ella. "
    "Pásale frases que leíste en el CV (p. ej. 'Diseñé el esquema en PostgreSQL'), "
    "NUNCA el texto del requisito. Úsala para confirmar cada cita antes de entregarla.",
    {"type": "object", "properties": {"texto": {"type": "string",
     "description": "Fragmento exacto que quieres citar"}}, "required": ["texto"]},
    _buscar_en_cv,
)
CONSULTAR_EQUIVALENCIAS = Herramienta(
    "consultar_equivalencias",
    "Devuelve los términos equivalentes de una tecnología o título (p. ej. Postgres = PostgreSQL).",
    {"type": "object", "properties": {"termino": {"type": "string"}}, "required": ["termino"]},
    _consultar_equivalencias,
)
EXPERIENCIA_POR_CARGO = Herramienta(
    "experiencia_por_cargo",
    "Calcula cuántos meses duró cada cargo según las fechas y el total sin solapes. "
    "Úsala para requisitos de años de experiencia en vez de confiar en lo que el candidato dice.",
    {"type": "object", "properties": {}},
    _experiencia_por_cargo,
)

FRASES_RELACIONADAS = Herramienta(
    "frases_relacionadas",
    "Devuelve las frases LITERALES del CV más relacionadas con un requisito (por su id, p. ej. "
    "'REQ-02'). Úsala primero para cada requisito: te da las candidatas a cita.",
    {"type": "object", "properties": {"id_requisito": {"type": "string"}}, "required": ["id_requisito"]},
    _frases_relacionadas,
)

# Registro central: toda herramienta existente está aquí; cada agente elige de este conjunto.
REGISTRO: dict[str, Herramienta] = {h.nombre: h for h in (
    FRASES_RELACIONADAS, BUSCAR_EN_CV, CONSULTAR_EQUIVALENCIAS, EXPERIENCIA_POR_CARGO,
)}
