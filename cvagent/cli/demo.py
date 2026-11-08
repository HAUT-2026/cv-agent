"""Command-line end-to-end demo using only Role 2–4 synthetic doubles."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from langgraph.types import Command

from ..domain.contracts import CaseState
from ..workflow.graph import build_graph, run_case, thread_config


def _print_snapshot(label: str, result: dict) -> None:
    payload = {
        "label": label,
        "estado": getattr(result.get("estado"), "value", result.get("estado")),
        "interrupciones": [item.value for item in result.get("__interrupt__", ())],
        "efectos": len(result.get("efectos_externos", [])),
    }
    print(json.dumps(payload, ensure_ascii=False, default=str, indent=2))


def main() -> None:
    now = datetime.now(timezone.utc)
    state = CaseState(
        correlation_id=str(uuid4()),
        vacante_id="vac-demo",
        vacante_version="v1",
        creado_en=now,
        actualizado_en=now,
    )
    graph = build_graph()
    config = thread_config(state.correlation_id)
    first = run_case(graph, state, config=config)
    _print_snapshot("pendiente de lista", first)
    second = graph.invoke(
        Command(
            resume={
                "decision": "aprobar",
                "aprobador": "recruiter-demo",
                "razon": "aprobación sintética",
            }
        ),
        config,
    )
    _print_snapshot("pendiente de mensaje", second)
    final = graph.invoke(
        Command(
            resume={
                "decision": "aprobar",
                "aprobador": "recruiter-demo",
                "razon": "aprobación sintética",
            }
        ),
        config,
    )
    _print_snapshot("cerrado", final)


if __name__ == "__main__":
    main()
