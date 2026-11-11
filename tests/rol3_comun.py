"""Utilidades compartidas por las pruebas del Rol 3 (datos oficiales de data/)."""
import copy
import json
from pathlib import Path

from cvagent.agentes.criterios import cargar_vacante
from cvagent.agentes.cv_json import preparar_caso
from cvagent.agentes.herramientas import ContextoCaso

DATA = Path(__file__).resolve().parent.parent / "data"
VACANTE = cargar_vacante(DATA / "vacante_v1.json")
MANIFIESTO = {c["cv_id"]: c for c in json.loads((DATA / "manifiesto.json").read_text("utf-8"))["cvs"]}
IDS = sorted(MANIFIESTO)


def caso(cv_id: str):
    return preparar_caso(DATA / "cvs_json" / f"{cv_id}.json")


def contexto(cv_id: str) -> ContextoCaso:
    c = caso(cv_id)
    return ContextoCaso(c.cv, c.texto, VACANTE)


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
