"""Checkpointer factories for the official LangGraph persistence API."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


def contract_serializer():
    """Create a strict serializer allowlisting Role 1 contract types."""

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    names = [
        "AprobacionHumana",
        "AuditMetadata",
        "CaseState",
        "CitationRef",
        "DecisionHumana",
        "EfectoExterno",
        "EstadoCaso",
        "EstadoSLA",
        "EstadoSLAInfo",
        "FichaCandidato",
        "PropuestaAgenda",
        "PropuestaLista",
        "RazónParada",
        "TipoAprobacion",
        "TipoSLA",
        "Veredicto",
        "VeredictoEstado",
    ]
    return JsonPlusSerializer(
        allowed_msgpack_modules=[("cvagent.contracts", name) for name in names]
    )


@contextmanager
def postgres_checkpointer(
    database_url: str, *, initialize: bool = False
) -> Iterator[object]:
    """Yield a PostgresSaver that remains open for the graph lifetime.

    LangGraph 1.x requires the same ``configurable.thread_id`` on initial and
    resumed invocations. ``initialize=True`` calls ``setup()`` exactly when a
    local database is being prepared; production migrations should be managed
    separately.
    """

    if not database_url:
        raise ValueError("database_url is required")
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import connect
    from psycopg.rows import dict_row

    connection = connect(database_url, autocommit=True, row_factory=dict_row)
    checkpointer = PostgresSaver(connection, serde=contract_serializer())
    try:
        if initialize:
            checkpointer.setup()
        yield checkpointer
    finally:
        connection.close()


def setup_postgres(database_url: str) -> None:
    """Create LangGraph checkpoint tables for local development."""

    with postgres_checkpointer(database_url, initialize=True):
        return


__all__ = ["contract_serializer", "postgres_checkpointer", "setup_postgres"]
