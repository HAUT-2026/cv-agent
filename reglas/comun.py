"""Utilidades compartidas por las reglas. Sin dependencias externas."""
from datetime import date
import hashlib
import unicodedata

# Fecha de referencia para "Actualidad". Se pasa siempre como parámetro para que las pruebas sean reproducibles.
HOY_REF = date(2026, 11, 10)


def mes_idx(texto: str) -> int:
    """'2023-05' -> índice de mes absoluto (año*12+mes). Lanza ValueError si el formato no es válido."""
    anio, mes = texto.split("-")
    anio, mes = int(anio), int(mes)
    if not 1 <= mes <= 12:
        raise ValueError(f"mes inválido: {texto}")
    return anio * 12 + mes


def idx_hoy(hoy: date) -> int:
    return hoy.year * 12 + hoy.month


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y sin espacios sobrantes: 'Inglés ' -> 'ingles'."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return " ".join(t.lower().split())


def seudonimizar(valor: str, sal: str = "cvagent-sal-demo") -> str:
    """ID seudonimizado (R12/R7): el modelo nunca ve el documento real. La sal real va en .env, no en el repo."""
    return hashlib.sha256((sal + normalizar(valor)).encode()).hexdigest()[:12]
