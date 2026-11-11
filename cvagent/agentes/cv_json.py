"""
Adaptador de los CV en JSON del dataset del Rol 2 (`data/cvs_json/`).

Formato del CV: cv_id, idioma, formato, persona (identidad), resumen,
experiencia[] (cargo, organizacion, tipo, inicio, fin, descripcion: lista),
educacion[] (titulo, institucion, anio_fin), habilidades, idiomas, otros[] y
texto_oculto (lo que el extractor encontró oculto en el PDF).

Decisiones:
- `persona` NUNCA entra al texto canónico (R7, defensa en profundidad).
- `otros` es contenido visible: entra al texto y pasa por el detector.
- `texto_oculto` NO entra al texto que ve el analista ("bloquear fragmento", E6);
  se analiza aparte y queda como indicio con fuente "texto_oculto".
- El manifiesto (respuestas esperadas) solo lo usa el banco de evaluación; nunca
  llega a un agente.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .sanitizacion import IndicioInyeccion, detectar_indicios_inyeccion, detectar_proxies
from .texto import Segmento, TextoCanonico

_ESTRICTO = ConfigDict(extra="forbid", str_strip_whitespace=True)
_MES = r"^\d{4}-(0[1-9]|1[0-2])$"


class TipoExperiencia(str, Enum):
    EMPLEO = "empleo"
    FREELANCE = "freelance"
    PASANTIA = "pasantia"
    VOLUNTARIADO = "voluntariado"
    PAUSA = "pausa"


CUENTA_PARA_EXPERIENCIA = {TipoExperiencia.EMPLEO, TipoExperiencia.FREELANCE}  # nota de REQ-01 / R11


class ExperienciaJson(BaseModel):
    model_config = _ESTRICTO
    cargo: str = ""
    organizacion: str = ""
    tipo: TipoExperiencia
    inicio: str = Field(pattern=_MES)
    fin: Optional[str] = Field(default=None, pattern=_MES)
    descripcion: list[str] = Field(default_factory=list)


class EducacionJson(BaseModel):
    model_config = _ESTRICTO
    titulo: str
    institucion: str = ""
    anio_fin: Optional[int] = None


class IdiomaJson(BaseModel):
    model_config = _ESTRICTO
    idioma: str
    nivel: str


class OtroJson(BaseModel):
    model_config = _ESTRICTO
    seccion: str
    texto: str


class CVJson(BaseModel):
    model_config = _ESTRICTO
    cv_id: str = Field(pattern=r"^CV-\d{3,}$")
    idioma: str
    formato: str
    persona: dict                       # identidad: se valida que exista, nunca se usa
    resumen: str = ""
    experiencia: list[ExperienciaJson] = Field(default_factory=list)
    educacion: list[EducacionJson] = Field(default_factory=list)
    habilidades: list[str] = Field(default_factory=list)
    idiomas: list[IdiomaJson] = Field(default_factory=list)
    otros: Optional[list[OtroJson]] = None
    texto_oculto: Optional[str] = None
    archivo_pdf: Optional[str] = None


# ------------------------------------------------------------------- limpieza
_INVISIBLES = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _limpiar(obj, contador: list[int]):
    if isinstance(obj, str):
        contador[0] += len(_INVISIBLES.findall(obj)) + len(_CONTROL.findall(obj))
        s = unicodedata.normalize("NFC", obj)
        s = _CONTROL.sub(" ", _INVISIBLES.sub("", s))
        return re.sub(r"[ \t]+", " ", s).strip()
    if isinstance(obj, list):
        return [_limpiar(x, contador) for x in obj]
    if isinstance(obj, dict):
        return {k: _limpiar(v, contador) for k, v in obj.items()}
    return obj


def cargar_cv_desde_dict(datos: dict) -> tuple[CVJson, int]:
    """Limpia y valida. Devuelve también cuántos caracteres invisibles o de control se quitaron."""
    contador = [0]
    limpio = _limpiar(datos, contador)
    return CVJson.model_validate(limpio), contador[0]


def cargar_cv(ruta: Path) -> tuple[CVJson, int]:
    return cargar_cv_desde_dict(json.loads(Path(ruta).read_text("utf-8")))


# ------------------------------------------------------------- texto canónico
class _Constructor:
    def __init__(self, id_cv: str):
        self.partes, self.largo, self.segmentos, self.id_cv = [], 0, [], id_cv

    def _agregar(self, s: str):
        self.partes.append(s)
        self.largo += len(s)

    def titulo(self, t: str):
        self._agregar(f"## {t}\n")

    def campo(self, etiqueta: str, valor, ruta: str):
        if valor is None or str(valor).strip() == "":
            return
        if etiqueta == "-":
            self._agregar("- ")
        elif etiqueta:
            self._agregar(f"{etiqueta}: ")
        ini = self.largo
        self._agregar(str(valor))
        self.segmentos.append(Segmento(ruta, ini, self.largo))
        self._agregar("\n")

    def vacia(self):
        self._agregar("\n")


_NOMBRE_TIPO = {"empleo": "Empleo", "freelance": "Freelance", "pasantia": "Pasantía",
                "voluntariado": "Voluntariado", "pausa": "Pausa laboral"}


def construir_texto_canonico(cv: CVJson) -> TextoCanonico:
    c = _Constructor(cv.cv_id)
    if cv.resumen:
        c.titulo("Perfil")
        c.campo("", cv.resumen, "resumen")
        c.vacia()
    if cv.experiencia:
        c.titulo("Experiencia")
        for i, e in enumerate(cv.experiencia):
            c.campo("Cargo", e.cargo, f"experiencia[{i}].cargo")
            c.campo("Organización", e.organizacion, f"experiencia[{i}].organizacion")
            c.campo("Tipo", _NOMBRE_TIPO[e.tipo.value], f"experiencia[{i}].tipo")
            c.campo("Periodo", f"{e.inicio} a {e.fin or 'actual'}", f"experiencia[{i}].periodo")
            for j, d in enumerate(e.descripcion):
                c.campo("-", d, f"experiencia[{i}].descripcion[{j}]")
            c.vacia()
    if cv.educacion:
        c.titulo("Educación")
        for i, ed in enumerate(cv.educacion):
            c.campo("Título", ed.titulo, f"educacion[{i}].titulo")
            c.campo("Institución", ed.institucion, f"educacion[{i}].institucion")
            # anio_fin se omite a propósito: no evalúa ningún requisito y es proxy de edad (R7)
            c.vacia()
    if cv.habilidades:
        c.titulo("Habilidades")
        for i, h in enumerate(cv.habilidades):
            c.campo("-", h, f"habilidades[{i}]")
        c.vacia()
    if cv.idiomas:
        c.titulo("Idiomas")
        for i, idm in enumerate(cv.idiomas):
            c.campo("-", f"{idm.idioma} ({idm.nivel})", f"idiomas[{i}]")
        c.vacia()
    if cv.otros:
        c.titulo("Otros")
        for i, o in enumerate(cv.otros):
            c.campo(o.seccion, o.texto, f"otros[{i}].texto")
    return TextoCanonico(cv.cv_id, "".join(c.partes), c.segmentos)


@dataclass
class Caso:
    cv: CVJson
    texto: TextoCanonico
    indicios: list[IndicioInyeccion]
    proxies: list[IndicioInyeccion] = field(default_factory=list)


def preparar_caso(ruta_cv: Path) -> Caso:
    cv, invisibles = cargar_cv(ruta_cv)
    return preparar_caso_desde_cv(cv, invisibles)


def preparar_caso_desde_cv(cv: CVJson, invisibles: int = 0) -> Caso:
    tc = construir_texto_canonico(cv)
    indicios = detectar_indicios_inyeccion(tc, invisibles, texto_oculto=cv.texto_oculto)
    return Caso(cv, tc, indicios, detectar_proxies(tc))
