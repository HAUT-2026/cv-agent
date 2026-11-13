"""Rol 4 · Portal, bandeja y evidencia.

Consume los contratos del Rol 1 (`cvagent.domain.contracts`) y el motor de
reglas del Rol 2 (`reglas/`). Ver docs/rol-4-portal.md.
"""
from .lote import ServicioLote

__all__ = ["ServicioLote"]
