"""Utilidades compartidas por las pruebas del Rol 3. Todo sale de data/ (dataset oficial del Rol 2):
si el equipo regenera el dataset, las pruebas leen los valores nuevos en vez de tener frases fijas."""
import copy
import json
from pathlib import Path

from cvagent.agentes.criterios import cargar_vacante
from cvagent.agentes.cv_json import preparar_caso
from cvagent.agentes.herramientas import ContextoCaso

DATA = Path(__file__).resolve().parent.parent / "data"
_MAN = json.loads((DATA / "manifiesto.json").read_text("utf-8"))
VACANTE = cargar_vacante(DATA, _MAN["vacante_id"], _MAN.get("vacante_version"))
MANIFIESTO = {c["cv_id"]: c for c in _MAN["cvs"] + _MAN.get("extras_inyeccion", [])}
IDS = sorted(MANIFIESTO)                                   # 40 CV + INJ-01..04
CON_MESES = [i for i in IDS if MANIFIESTO[i]["esperado"]["meses_efectivos"] is not None]


def ruta_json(cv_id: str) -> Path:
    return DATA / MANIFIESTO[cv_id]["archivo_json"]


def datos(cv_id: str) -> dict:
    """El JSON crudo (con identidad): para pruebas que modifican el CV antes de cargarlo."""
    return json.loads(ruta_json(cv_id).read_text("utf-8"))


def caso(cv_id: str):
    return preparar_caso(ruta_json(cv_id))


def contexto(cv_id: str) -> ContextoCaso:
    c = caso(cv_id)
    return ContextoCaso(c.cv, c.texto, VACANTE)


def segmento(c, ruta: str) -> str:
    """Texto literal de un campo del texto canónico (p. ej. 'experiencia[0].descripcion[1]')."""
    s = next(s for s in c.texto.segmentos if s.ruta == ruta)
    return c.texto.texto[s.inicio:s.fin]


class LLMFalso:
    """Simula al proveedor: responde siguiendo un guion y guarda una foto de cada pedido."""
    def __init__(self, guion):
        self.guion, self.recibidos = list(guion), []

    def __call__(self, url, payload, headers, timeout):
        self.recibidos.append(copy.deepcopy(payload))
        return {"choices": [{"message": copy.deepcopy(self.guion.pop(0))}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def llamar(nombre, args, id_="x"):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": id_, "type": "function", "function": {"name": nombre, "arguments": json.dumps(args, ensure_ascii=False)}}]}
