"""API REST del portal (Rol 4).

Sirve el frontend y expone el lote sobre los contratos del Rol 1. No contiene
lógica de negocio: carga, delega en `ServicioLote` y devuelve.

Arrancar:  python -m portal
Documentación interactiva:  http://localhost:8000/docs
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .lote import ServicioLote

RAIZ = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"
DATA = RAIZ / "data"

app = FastAPI(
    title="CVAgent · Portal",
    version="1.0.0",
    description=(
        "Portal de selección asistida. Rol 4 sobre los contratos del Rol 1 "
        "(`cvagent.domain.contracts`) y el motor de reglas del Rol 2 (`reglas/`)."
    ),
)

servicio = ServicioLote(DATA)


# ------------------------------------------------------------------ cuerpos
class CargaLote(BaseModel):
    vacante_id: str = "VAC-001"
    version: int | None = Field(default=None, description="Sin versión usa la vigente (R8)")


class DecisionLista(BaseModel):
    decision: Literal["aprobar", "ajustar", "rechazar"]
    aprobador: str = Field(min_length=3)
    razon: str = Field(min_length=3)
    cv_ids_aprobados: list[str] | None = None


class DecisionMensaje(BaseModel):
    cv_id: str
    decision: Literal["aprobar", "ajustar", "rechazar"]
    aprobador: str = Field(min_length=3)
    razon: str = Field(min_length=3)
    texto_exacto: str | None = None


# ------------------------------------------------------------------- lote
@app.get("/api/estado", tags=["lote"])
def estado():
    return servicio.resumen()


@app.post("/api/lote/cargar", tags=["lote"])
def cargar(cuerpo: CargaLote):
    """Lee la vacante y los 40 CV y corre R12→R1→R2→R11/R3→R7 (Rol 2)."""
    try:
        return servicio.cargar(cuerpo.vacante_id, cuerpo.version)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/lote/ejecutar", tags=["lote"])
def ejecutar():
    """Corre el grafo del Rol 1 por caso hasta la aprobación de lista.

    El resultado es una PROPUESTA. Ningún caso avanza sin decisión humana.
    """
    try:
        return servicio.ejecutar()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/candidatos", tags=["lote"])
def candidatos():
    return servicio.candidatos()


@app.get("/api/detenidos", tags=["lote"])
def detenidos():
    """Casos que el grafo paró antes de la compuerta humana (hallazgo H-5)."""
    return servicio.detenidos()


@app.get("/api/candidatos/{cv_id}/texto", tags=["lote"])
def texto(cv_id: str):
    """Texto canónico y sus citas. Los offsets se miden contra este texto."""
    try:
        return servicio.texto_de(cv_id)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(404, str(exc)) from exc


# -------------------------------------------------------------- decisiones
@app.post("/api/decision/lista", tags=["decisiones"])
def decidir_lista(cuerpo: DecisionLista):
    """Primera compuerta humana: la lista corta.

    La decisión se reparte a cada hilo del grafo: `aprobar` a los que entran y
    `rechazar` a los demás, siempre con razón registrada. Ningún caso queda
    sin decisión y ningún silencio cuenta como aprobación.
    """
    try:
        return servicio.decidir_lista(
            decision=cuerpo.decision, aprobador=cuerpo.aprobador,
            razon=cuerpo.razon, cv_ids_aprobados=cuerpo.cv_ids_aprobados,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/decision/mensaje", tags=["decisiones"])
def decidir_mensaje(cuerpo: DecisionMensaje):
    """Segunda compuerta humana: el texto exacto, antes de cualquier envío (R10)."""
    try:
        return servicio.decidir_mensaje(
            cv_id=cuerpo.cv_id, decision=cuerpo.decision, aprobador=cuerpo.aprobador,
            razon=cuerpo.razon, texto_exacto=cuerpo.texto_exacto,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# --------------------------------------------------------------- evidencia
@app.get("/api/evidencia", tags=["evidencia"])
def evidencia():
    return servicio.evidencia()


@app.get("/api/evidencia/csv", tags=["evidencia"])
def evidencia_csv():
    entradas = servicio.evidencia()["entradas"]
    campos = ["tiempo", "correlation_id", "componente", "razon", "cobertura",
              "veredicto", "aprobador", "estado", "hash_previo", "hash_entrada"]
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=campos, extrasaction="ignore")
    escritor.writeheader()
    for e in entradas:
        escritor.writerow(e)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=decision_log.csv"},
    )


# ---------------------------------------------------------------- frontend
app.mount("/css", StaticFiles(directory=WEB / "css"), name="css")
app.mount("/js", StaticFiles(directory=WEB / "js"), name="js")
app.mount("/fuentes", StaticFiles(directory=WEB / "fuentes"), name="fuentes")


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(WEB / "index.html")
