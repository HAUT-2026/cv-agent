import glob
import json
import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)

from reglas import cargar_diccionario, cargar_vacante  # noqa: E402

DATA = os.environ.get("CVAGENT_DATA", os.path.join(RAIZ, "data"))


def _json(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def data_dir():
    return DATA


@pytest.fixture(scope="session")
def vacante_v1():
    return cargar_vacante(DATA, "VAC-001", 1)


@pytest.fixture(scope="session")
def vacante_v2():
    return cargar_vacante(DATA, "VAC-001", 2)


@pytest.fixture(scope="session")
def dic():
    return cargar_diccionario(os.path.join(DATA, "diccionario_equivalencias.json"))


@pytest.fixture(scope="session")
def manifiesto():
    return _json(os.path.join(DATA, "manifiesto.json"))


@pytest.fixture(scope="session")
def fichas():
    return {os.path.basename(f)[:-5]: _json(f) for f in sorted(glob.glob(os.path.join(DATA, "cvs_json", "CV-*.json")))}


@pytest.fixture(scope="session")
def fichas_extras():
    return {os.path.basename(f)[:-5]: _json(f) for f in sorted(glob.glob(os.path.join(DATA, "extras_inyeccion", "cvs_json", "INJ-*.json")))}
