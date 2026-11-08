# CVAgent — Rol 1: grafo y estado

Este MVP contiene únicamente la franja de **Grafo y estado**. Usa CV sintéticos,
doubles explícitos para los Roles 2–4 y no realiza envíos ni escrituras en
sistemas externos reales.

## Ruta rápida

1. Instalar dependencias: `python -m pip install -e ".[dev]"`.
2. Ejecutar la demostración: `python -m cvagent.demo`.
3. Ejecutar pruebas: `python -m pytest`.

La demostración muestra el caso pendiente de aprobación de lista, el caso
pendiente de aprobación del mensaje exacto y el cierre con un efecto simulado.

## PostgreSQL local

La API oficial de LangGraph 1.x exige un checkpointer compilado y el mismo
`configurable.thread_id` al reanudar. CVAgent usa `correlation_id` como ese
`thread_id`. La factoría `cvagent.persistence.postgres_checkpointer` conserva
abierta la conexión durante toda la vida del grafo y configura `autocommit=True`
y `dict_row`, como requiere `PostgresSaver` cuando se construye con una conexión
manual.

```bash
docker compose up -d postgres
export CVAGENT_POSTGRES_URL='postgresql://cvagent:cvagent_local_only@localhost:54329/cvagent'
python -m cvagent.postgres_setup
python -m pytest -m integration
```

En PowerShell:

```powershell
docker compose up -d postgres
$env:CVAGENT_POSTGRES_URL = "postgresql://cvagent:cvagent_local_only@localhost:54329/cvagent"
python -m cvagent.postgres_setup
python -m pytest -m integration
```

Para detener el servicio local: `docker compose down`.

El test de integración se omite de forma explícita si no existe
`CVAGENT_POSTGRES_URL`; las pruebas unitarias no necesitan PostgreSQL.

## Interfaces para los otros roles

- `cvagent/contracts.py` es la única fuente de `CaseState`, `FichaCandidato`,
  `Veredicto`, `PropuestaAgenda`, `EntradaDecisionLog` y sus enums. Su versión
  actual es `1.0.0`.
- `cvagent.ports.RoleAdapters` recibe implementaciones de los Roles 2–4.
  `synthetic_adapters()` solo sirve para la demo y las pruebas.
- `build_graph(...)` permite inyectar adaptadores, checkpointer, reloj,
  `DecisionLog`, controles operativos y registro de snapshots.
- `thread_config(correlation_id)` devuelve la configuración de persistencia
  oficial: `{"configurable": {"thread_id": correlation_id}}`.
- La primera interrupción solicita `lista_corta`; la segunda solicita
  `mensaje_exacto`. `Command(resume={"decision": "aprobar"|"ajustar"|"rechazar", ...})`
  reanuda el mismo thread. El silencio conserva el interrupt: el watchdog no
  lo transforma en aprobación ni descarte.
- `SLAWatchdog` inspecciona `CaseRegistry` y registra recordatorio/escalamiento
  sin llamar al grafo. `register_policy()` permite añadir plazos adicionales.
- `OperationalControls` expone allowlist, registro de llamadas, reintentos,
  reconciliación por idempotency key y kill switch explícito.

## Alcance deliberadamente excluido

Los Roles 2 y 3 deben implementar extracción, minimización, reglas R1–R13,
valoraciones y agentes. El Rol 4 debe implementar su bandeja y simuladores. El
Rol 1 no selecciona proveedor LLM, no incorpora RAG, no usa datos personales
reales y no autoriza decisiones humanas.
