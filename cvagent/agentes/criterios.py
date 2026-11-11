"""
Criterios de la vacante (Rol 3): modelo de `Vacante` y `Requisito` que consumen los agentes,
y el cargador de la vacante versionada del dataset (`data/vacante_v1.json`).

No reemplaza ni modifica `cvagent.domain.contracts` (Rol 1): es la vista que necesitan
los agentes para evaluar requisitos con sus equivalencias versionadas (R8).
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ESTRICTO = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TipoRequisito(str, Enum):
    HABILIDAD = "habilidad"
    EXPERIENCIA = "experiencia"
    EDUCACION = "educacion"
    IDIOMA = "idioma"
    CERTIFICACION = "certificacion"
    CONOCIMIENTO = "conocimiento"


class Requisito(BaseModel):
    model_config = _ESTRICTO
    id: str = Field(pattern=r"^(REQ|DES)-\d{2,}$")   # REQ = obligatorio, DES = deseable (dataset del equipo)
    tipo: TipoRequisito
    descripcion: str
    obligatorio: bool
    anios_minimos: Optional[float] = None       # solo para tipo experiencia
    nivel_minimo: Optional[str] = None          # educación o idioma
    peso: float = Field(default=1.0, gt=0)      # para el fit del analista (rúbrica oficial pendiente de RR. HH.)
    equivalencias: list[str] = Field(default_factory=list)      # versionadas en la vacante (R8)
    titulos_aceptados: list[str] = Field(default_factory=list)
    nota: Optional[str] = None                                  # p. ej. qué cuenta como experiencia (R11)


class Vacante(BaseModel):
    model_config = _ESTRICTO
    id_vacante: str = Field(pattern=r"^VAC-\d{3,}$")
    version: int = Field(ge=1)                  # va al decision_log (B6)
    cargo: str
    area: str = ""
    descripcion: str
    requisitos: list[Requisito] = Field(min_length=1)
    top_n: int = Field(default=5, ge=1)         # tamaño de la lista corta

    @field_validator("requisitos")
    @classmethod
    def _ids_unicos(cls, v):
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("ids de requisito repetidos")
        return v


def cargar_vacante(ruta: Path) -> Vacante:
    """Convierte la vacante del dataset (formato del Rol 2) sin perder datos de criterio."""
    v = json.loads(Path(ruta).read_text("utf-8"))
    reqs = [Requisito(
        id=r["id"], tipo=TipoRequisito(r["categoria"]), descripcion=r["descripcion"],
        obligatorio=(r["tipo"] == "obligatorio"),
        anios_minimos=r.get("min_anios"), nivel_minimo=r.get("nivel_minimo"),
        equivalencias=r.get("equivalencias") or [], titulos_aceptados=r.get("titulos_aceptados") or [],
        nota=r.get("nota")) for r in v["requisitos"]]
    return Vacante(id_vacante=v["vacante_id"], version=v["version"], cargo=v["titulo"],
                   area=v.get("organizacion", ""), descripcion=v.get("mision", ""), requisitos=reqs)
