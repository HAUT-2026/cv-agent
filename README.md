# CVAgent

Agente de preselección de hojas de vida. El trabajo se reparte en cuatro roles; cada uno tiene su sección.

## Tabla de contenidos

- **[Rol 1 · Grafo y estado](#rol-1)**
  - [Ruta rápida](#ruta-rapida)
  - [LangGraph Studio en desarrollo](#langgraph-studio-en-desarrollo)
  - [PostgreSQL local](#postgresql-local)
  - [Interfaces para los otros roles](#interfaces-para-los-otros-roles)
  - [Organización del paquete](#organizacion-del-paquete)
  - [Alcance deliberadamente excluido](#alcance-deliberadamente-excluido)
- **[Rol 2 · Reglas y datos del caso](#rol-2)**
  - [Qué contiene](#rol-2-que-contiene)
  - [Cómo probarlo](#rol-2-como-probarlo)
  - [Documentación completa del Rol 2 (`README_ROL2.md`)](README_ROL2.md)
- **Rol 3 · Agentes** (pendiente)
- **[Rol 4 · Portal, bandeja y evidencia](#rol-4)**
  - [Ruta rápida](#rol-4-ruta-rapida)
  - [Qué contiene](#rol-4-que-contiene)
  - [Hallazgos de integración](#rol-4-hallazgos)
  - [Documentación completa del Rol 4 (`docs/rol-4-portal.md`)](docs/rol-4-portal.md)

---

<a id="rol-1"></a>

# CVAgent — Rol 1: grafo y estado

Este MVP contiene únicamente la franja de **Grafo y estado**. Usa CV sintéticos,
doubles explícitos para los Roles 2–4 y no realiza envíos ni escrituras en
sistemas externos reales.

<a id="ruta-rapida"></a>

## Ruta rápida

1. Instalar UV siguiendo la documentación oficial.
2. Crear el entorno y sincronizar dependencias: `uv venv` y `uv sync`.
3. Ejecutar la demostración: `uv run python -m cvagent.demo`.
4. Ejecutar pruebas: `uv run pytest`.

La demostración muestra el caso pendiente de aprobación de lista, el caso
pendiente de aprobación del mensaje exacto y el cierre con un efecto simulado.

## LangGraph Studio en desarrollo

El grafo se exporta desde `cvagent/langgraph_app.py` y se registra como `cvagent`
en `langgraph.json`. Para iniciarlo:

```bash
uv run langgraph dev
```

El CLI imprime las URLs de la API y de Studio. El servidor `dev` usa persistencia
en memoria; la configuración de PostgreSQL del apartado siguiente sirve para
las pruebas locales del checkpointer del proyecto.

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
uv run python -m cvagent.postgres_setup
uv run pytest -m integration
```

En PowerShell:

```powershell
docker compose up -d postgres
$env:CVAGENT_POSTGRES_URL = "postgresql://cvagent:cvagent_local_only@localhost:54329/cvagent"
uv run python -m cvagent.postgres_setup
uv run pytest -m integration
```

Para detener el servicio local: `docker compose down`.

El test de integración se omite de forma explícita si no existe
`CVAGENT_POSTGRES_URL`; las pruebas unitarias no necesitan PostgreSQL.

## Interfaces para los otros roles

- `cvagent/domain/contracts.py` es la única fuente de `CaseState`, `FichaCandidato`,
  `Veredicto`, `PropuestaAgenda`, `EntradaDecisionLog` y sus enums. Su versión
  actual es `1.0.0`; `cvagent.contracts` es una fachada compatible.
- `cvagent.integration.ports.RoleAdapters` recibe implementaciones de los Roles 2–4;
  `cvagent.ports` es una fachada compatible.
  `synthetic_adapters()` solo sirve para la demo y las pruebas.
- `cvagent.workflow.graph.build_graph(...)` permite inyectar adaptadores, checkpointer, reloj,
  `DecisionLog`, controles operativos y registro de snapshots.
- `thread_config(correlation_id)` devuelve la configuración de persistencia
  oficial: `{"configurable": {"thread_id": correlation_id}}`.
- La primera interrupción solicita `lista_corta`; la segunda solicita
  `mensaje_exacto`. `Command(resume={"decision": "aprobar"|"ajustar"|"rechazar", ...})`
  reanuda el mismo thread. El silencio conserva el interrupt: el watchdog no
  lo transforma en aprobación ni descarte.
- `SLAWatchdog` inspecciona `CaseRegistry` y registra recordatorio/escalamiento
  sin llamar al grafo. `register_policy()` permite añadir plazos adicionales.
- `SLAWatchdogService` ejecuta esas inspecciones periódicamente en un proceso
  desacoplado del grafo; `start()` y `stop()` controlan su ciclo de vida y
  `run_once()` permite una ejecución operativa puntual.
- `OperationalControls` expone allowlist, registro de llamadas, reintentos,
  reconciliación por idempotency key, kill switch explícito y tokens opacos
  ligados a agente/caso/vacante con TTL predeterminado de 15 minutos. Las
  validaciones registran ausencia, invalidez y vencimiento sin guardar el token.

## Organización del paquete

La implementación está agrupada dentro de `cvagent/`:

```text
cvagent/
├── domain/       # contratos versionados
├── workflow/     # grafo, persistencia, reloj y registro de casos
├── audit/        # decision_log y SLA watchdog
├── operations/   # allowlist, reintentos e idempotencia
├── integration/  # puertos y dobles de Roles 2–4
└── cli/          # demo y preparación de PostgreSQL
```

Los módulos planos como `cvagent.contracts` y `cvagent.graph` son fachadas de
compatibilidad; el código fuente vive en esos subpaquetes.

## Alcance deliberadamente excluido

Los Roles 2 y 3 deben implementar extracción, minimización, reglas R1–R13,
valoraciones y agentes. El Rol 4 debe implementar su bandeja y simuladores. El
Rol 1 no selecciona proveedor LLM, no incorpora RAG, no usa datos personales
reales y no autoriza decisiones humanas.

---

<a id="rol-2"></a>

# CVAgent — Rol 2: reglas y datos del caso

Motor de reglas R1 a R13 como funciones puras, dataset de 40 CV ficticios para la
vacante **Backend Java**, repositorio de vacantes versionadas, diccionario de
equivalencias y staging determinista del Top 5. Corre sin API ni red.

> Documentación completa, con el mapa regla → código → casos de prueba y los
> supuestos pendientes de confirmar: **[README_ROL2.md](README_ROL2.md)**.

<a id="rol-2-que-contiene"></a>

## Qué contiene

| Carpeta   | Contenido                                                                                                                                                                                            |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reglas/` | `reglas.py` (R1–R13), `motor.py` (encadena las reglas y arma el staging), `diccionario.py`, `vacantes.py`, `comun.py`                                                                                |
| `data/`   | `vacantes/` (v1 vigente, v2 borrador), `diccionario_equivalencias.json`, `cvs_pdf/` y `cvs_json/` (40 CV), `extras_inyeccion/` (4 CV con prompt injection), `manifiesto.json` y `generar_dataset.py` |
| `tests/`  | `test_reglas.py`, `test_dataset.py` y `conftest.py` (132 pruebas)                                                                                                                                    |

`data/manifiesto.json` contiene las respuestas correctas: es solo para evaluar y
no se le entrega a los agentes del Rol 3.

<a id="rol-2-como-probarlo"></a>

## Cómo probarlo

```bash
uv run --with pypdf python -m pytest tests/test_reglas.py tests/test_dataset.py -q
```

Debe terminar con `132 passed`. `pypdf` se agrega solo para esa ejecución, porque
algunas pruebas leen el texto de los PDF.


---

<a id="rol-4"></a>

# CVAgent — Rol 4: portal, bandeja y evidencia

Interfaz web del reclutador, API REST y orquestación del lote. Consume los
contratos del Rol 1 y el motor de reglas del Rol 2 **sin modificar ninguno de
los dos**: es la primera pieza que hace correr las tres partes juntas.

<a id="rol-4-ruta-rapida"></a>

## Ruta rápida

```bash
pip install -e ".[portal]"     # o: uv sync --extra portal
python -m portal               # http://localhost:8000
```

En la vista **Lote**: «Cargar lote» aplica el motor del Rol 2 a los 44 CV
(40 del corpus más los 4 de inyección) y «Ejecutar pipeline» corre el grafo del
Rol 1 caso por caso hasta la primera compuerta humana. La aprobación se hace en
**Bandeja** y todo queda en **Evidencia**.

Las pruebas del portal corren con las demás: `python -m pytest tests -q`.

<a id="rol-4-que-contiene"></a>

## Qué contiene

| Módulo | Responsabilidad |
|---|---|
| `portal/texto.py` | Texto canónico sanitizado (PDF o gemelo JSON) y anclaje de citas por posición |
| `portal/adaptadores.py` | Los cuatro puertos del Rol 1. El motor de reglas es **real**; analista y auditor son dobles sin modelo de lenguaje |
| `portal/lote.py` | Une el lote del Rol 2 con el grafo por caso del Rol 1 y reparte la decisión humana |
| `portal/api.py` | API REST documentada en `/docs` |
| `portal/web/` | Frontend en HTML, CSS y JavaScript, sin paso de compilación |

La regla que sostiene toda la evidencia: **al modelo se le pide la subcadena
literal del CV; las posiciones las calcula el código.** Un modelo no cuenta
caracteres, pero sí copia una frase. `test_p11` verifica el invariante sobre el
corpus completo y la bandeja marca en rojo cualquier cita que no recorte.

<a id="rol-4-hallazgos"></a>

## Hallazgos de integración

Cinco cosas aparecieron al unir las tres partes. Ninguna se resolvió en
silencio; el detalle y la propuesta de cada una están en
[`docs/rol-4-portal.md`](docs/rol-4-portal.md).

| # | Hallazgo | Decide |
|---|---|---|
| H-1 | `CaseState` no tiene dónde guardar de qué CV se trata, así que la correlación vive fuera del estado del grafo | Rol 1 |
| H-2 | El grafo es por caso y R4/R5/R6 son de lote: hay dos nociones distintas de «lista corta» | Rol 1 y Rol 2 |
| H-3 | La rúbrica de puntaje no está definida en el SDD; los pesos actuales son un supuesto del Rol 4 | Hiring manager |
| H-4 | INJ-03 esconde la inyección en el PDF: una sanitización que trabaje sobre el JSON no la ve | Rol 3 |
| H-5 | Un veredicto bloqueado enruta a `stop` y no genera interrupción, así que nadie lo ve | Rol 1 |
