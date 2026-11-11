"""Repositorio de vacantes versionadas (B5 del Hito 2).

Estructura en disco:
  data/vacantes/indice.json     {"VAC-001": {"vigente": 1, "versiones": [1, 2]}}
  data/vacantes/vacante_v1.json
  data/vacantes/vacante_v2.json

Las versiones nunca se sobreescriben: un cambio es un archivo nuevo (R13) y el índice se
actualiza solo cuando el hiring manager y RR. HH. aprueban.
"""
import json
import os


def _leer(ruta: str) -> dict:
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


def cargar_indice(base_dir: str) -> dict:
    return _leer(os.path.join(base_dir, "vacantes", "indice.json"))


def cargar_vacante(base_dir: str, vacante_id: str, version: int | None = None) -> dict:
    """Sin `version` devuelve la vigente (R8). Con `version` devuelve esa versión exacta."""
    indice = cargar_indice(base_dir)
    if vacante_id not in indice:
        raise KeyError(f"vacante desconocida: {vacante_id}")
    version = version if version is not None else indice[vacante_id]["vigente"]
    if version not in indice[vacante_id]["versiones"]:
        raise KeyError(f"{vacante_id} no tiene versión {version}")
    return _leer(os.path.join(base_dir, "vacantes", f"vacante_v{version}.json"))
