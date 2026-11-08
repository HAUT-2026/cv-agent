import os

import pytest
from langgraph.types import Command

from cvagent.contracts import CaseState, EstadoCaso
from cvagent.graph import build_graph, run_case, thread_config
from cvagent.persistence import postgres_checkpointer


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("CVAGENT_POSTGRES_URL"),
    reason="CVAGENT_POSTGRES_URL is not configured",
)
def test_postgres_checkpoint_survives_checkpointer_reopen() -> None:
    from datetime import datetime, timezone
    from uuid import uuid4

    now = datetime.now(timezone.utc)
    state = CaseState(
        correlation_id=str(uuid4()),
        vacante_id="vac-demo",
        vacante_version="v1",
        creado_en=now,
        actualizado_en=now,
    )
    config = thread_config(state.correlation_id)
    with postgres_checkpointer(os.environ["CVAGENT_POSTGRES_URL"], initialize=True) as saver:
        first_graph = build_graph(checkpointer=saver)
        first = run_case(first_graph, state, config=config)
        assert first["estado"] is EstadoCaso.PENDIENTE_APROBACION_LISTA

    with postgres_checkpointer(os.environ["CVAGENT_POSTGRES_URL"]) as saver:
        restarted_graph = build_graph(checkpointer=saver)
        resumed = restarted_graph.invoke(
            Command(
                resume={
                    "decision": "rechazar",
                    "aprobador": "recruiter-demo",
                    "razon": "synthetic rejection",
                }
            ),
            config,
        )
        assert resumed["estado"] is EstadoCaso.LISTA_RECHAZADA
