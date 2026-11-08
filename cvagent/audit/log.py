"""Append-only decision log with a verifiable hash chain."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from threading import RLock
from typing import Iterable

from ..domain.contracts import (
    CONTRACT_VERSION,
    EntradaDecisionLog,
    EstadoCaso,
    VeredictoEstado,
)


class DecisionLog:
    """In-memory MVP log; the public API exposes no mutation operation."""

    def __init__(self) -> None:
        self._entries: list[EntradaDecisionLog] = []
        self._lock = RLock()

    @property
    def entries(self) -> tuple[EntradaDecisionLog, ...]:
        with self._lock:
            return tuple(entry.model_copy(deep=True) for entry in self._entries)

    def append(
        self,
        *,
        correlation_id: str,
        tiempo: datetime,
        componente: str,
        fuente: Iterable[str],
        versiones: dict[str, str],
        razon: str,
        cobertura: float | None = None,
        veredicto: VeredictoEstado | None = None,
        aprobador: str | None = None,
        estado: EstadoCaso | None = None,
    ) -> EntradaDecisionLog:
        """Append one entry and calculate its chain hash atomically."""

        with self._lock:
            previous_hash = self._entries[-1].hash_entrada if self._entries else "GENESIS"
            body = {
                "correlation_id": correlation_id,
                "tiempo": tiempo.isoformat(),
                "componente": componente,
                "fuente": list(fuente),
                "versiones": versiones,
                "razon": razon,
                "cobertura": cobertura,
                "veredicto": veredicto.value if veredicto else None,
                "aprobador": aprobador,
                "estado": estado.value if estado else None,
                "hash_previo": previous_hash,
                "contrato_version": CONTRACT_VERSION,
            }
            serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
            entry_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            entry = EntradaDecisionLog(
                correlation_id=correlation_id,
                tiempo=tiempo,
                componente=componente,
                fuente=body["fuente"],
                versiones=versiones,
                razon=razon,
                cobertura=cobertura,
                veredicto=veredicto,
                aprobador=aprobador,
                estado=estado,
                hash_previo=previous_hash,
                hash_entrada=entry_hash,
            )
            self._entries.append(entry)
            return entry

    def verify_integrity(self) -> bool:
        """Verify ordering and every hash without exposing mutable internals."""

        with self._lock:
            previous_hash = "GENESIS"
            for entry in self._entries:
                if entry.hash_previo != previous_hash:
                    return False
                body = {
                    "correlation_id": entry.correlation_id,
                    "tiempo": entry.tiempo.isoformat(),
                    "componente": entry.componente,
                    "fuente": entry.fuente,
                    "versiones": entry.versiones,
                    "razon": entry.razon,
                    "cobertura": entry.cobertura,
                    "veredicto": entry.veredicto.value if entry.veredicto else None,
                    "aprobador": entry.aprobador,
                    "estado": entry.estado.value if entry.estado else None,
                    "hash_previo": entry.hash_previo,
                    "contrato_version": CONTRACT_VERSION,
                }
                serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
                expected_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
                if entry.hash_entrada != expected_hash:
                    return False
                previous_hash = entry.hash_entrada
            return True


__all__ = ["DecisionLog"]
