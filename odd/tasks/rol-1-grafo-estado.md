# Rol 1 — Grafo y estado del MVP de CVAgent
Branch: `feature/rol-1-grafo-estado` · Delivery: `ask-on-risk` · Test runner: `pytest`
Objetivo: entregar contratos versionados, grafo persistente, aprobaciones humanas, SLA/auditoría y controles operativos simulables para que los Roles 2–4 integren componentes sin asumir lógica de negocio ajena.

## Specs

### S1 — Contrato compartido

> Define en un único módulo versionado: CaseState, FichaCandidato, Veredicto, PropuestaAgenda, EntradaDecisionLog y las enumeraciones de estados y razones de parada.
> Incluye tipos y esquemas estrictos, ejemplos mínimos de entrada/salida y validaciones.
> Asegura correlation_id único, versión de vacante, marcas de tiempo, referencias de citas con offsets y campos de auditoría.
> Antes de cambiar un contrato existente, identifica qué roles dependen de él y documenta el cambio para el equipo. No hagas cambios silenciosos.

Acceptance: los modelos rechazan campos no definidos y valores fuera de rango; las citas se validan contra texto sanitizado; `correlation_id`, vacante/versiones, timestamps y auditoría son obligatorios; no existe contrato previo que modificar, por lo que el contrato nuevo se documenta para Roles 2–4.

### S2 — Esqueleto ejecutable

> Construye el grafo de LangGraph con nodos y aristas condicionales para el flujo completo.
> Usa adaptadores o nodos falsos con contratos reales para las piezas de los Roles 2, 3 y 4. Esos reemplazos deben ser explícitos y fáciles de sustituir.
> Demuestra que un caso entra, cambia de estado, produce una propuesta simulada, se pausa para aprobación y puede cerrar tras reanudarse.
> Usa correlation_id como identidad del caso y configúralo como thread_id de persistencia según la API oficial de la versión de LangGraph instalada. Verifica la API actual; no asumas que el texto del plan equivale a documentación de la biblioteca.

Acceptance: una demo y pruebas recorren entrada → propuesta → pausa → reanudación → cierre usando dobles explícitos.

### S3 — Persistencia y aprobación humana

> Configura un checkpointer persistente en PostgreSQL, con instrucciones reproducibles para levantarlo localmente.
> Implementa dos interrupciones independientes: aprobación de la lista corta y aprobación del mensaje exacto.
> Sin la primera aprobación no se activa agendamiento; sin la segunda no se llama al envío simulado. Rechazo, ajuste y falta de respuesta deben conservar estados distinguibles.
> Prueba que el proceso se recupera desde un checkpoint después de reiniciarse, sin repetir efectos ya ejecutados.

Acceptance: la ruta PostgreSQL usa `PostgresSaver` y `thread_id`; las pruebas rápidas usan memoria y una prueba opcional valida la ruta PostgreSQL si existe `CVAGENT_POSTGRES_URL`; ninguna expiración reanuda el grafo.

### S4 — SLA y auditoría

> Implementa un vigilante de SLA separado del grafo que inspeccione casos pendientes y registre recordatorios y escalamientos sin aprobar automáticamente.
> Cubre como mínimo: lista corta (recordatorio a 24 h, escalamiento a 48 h y estado vencido a 72 h) y mensaje (recordatorio a 4 h, escalamiento a 8 h). Diseña el mecanismo para incorporar los demás plazos de B3/B4.2.
> Inyecta el reloj para probar vencimientos en segundos sin esperar horas reales.
> Proporciona un helper de decision_log de solo anexado que todos los nodos puedan usar. Registra correlation_id, tiempo, componente, fuente, versiones, razón, cobertura, veredicto y aprobador cuando corresponda. El checkpoint no sustituye este log.

Acceptance: el reloj falso demuestra las tres etapas de lista y las dos de mensaje, conserva estados y deja entradas de log encadenadas sin mutación.

### S5 — Controles operativos

> Implementa la allowlist de herramientas por agente, el registro de llamadas y el rechazo verificable de operaciones no permitidas. Mantén credenciales y tokens fuera de prompts y estado expuesto a agentes.
> Añade reintentos acotados y backoff para fallos transitorios, con idempotencia o reconciliación antes de repetir operaciones externas.
> Implementa el kill switch con alcance por vacante, agente o sistema: pausa casos afectados, impide nuevas acciones externas, registra causa y exige el procedimiento de reanudación descrito en B3.
> No conviertas un fallo, silencio o excepción en descarte automático de un candidato.

Acceptance: una herramienta prohibida queda bloqueada y registrada; un efecto simulado no se duplica al reintentar; el kill switch bloquea el alcance seleccionado y solo una reanudación explícita permite continuar.

### S6 — Límites y criterio de entrega

> Los Roles 2 y 3 implementan las reglas R1–R13, extracción y los tres agentes. El Rol 4 implementa bandeja, simuladores y suite de demo. Proporciona interfaces y dobles de prueba para integrarlos, sin apropiarte de su lógica.
> Usa únicamente CV ficticios y datos de prueba. No hagas envíos reales ni escribas en sistemas externos reales.
> No publiques, hagas push ni abras PR sin mi instrucción.

> - El esqueleto corre de punta a punta con componentes simulados.
> - Las dos interrupciones pausan y reanudan realmente el caso; no existe avance por expiración del plazo.
> - El vigilante demuestra un SLA vencido con reloj simulado y deja evidencia en el decision_log.
> - Un reinicio recupera el estado; los reintentos no duplican efectos.
> - Una herramienta prohibida se bloquea y queda registrada.
> - El kill switch detiene nuevas acciones en el alcance elegido.
> - Otro integrante puede ejecutar la demostración siguiendo el README y las pruebas fallan si se rompe cualquiera de estas garantías.

## Tasks

- T1 · S1 · inline · done · commit: `ee56bf8` (`python -m pytest tests/test_contracts.py` → 4 passed)
- T2 · S2–S3 · inline · done · commit: `6bf556e` (+ cleanup `62ea42a`; `python -m pytest tests/test_contracts.py tests/test_graph.py` → 7 passed)
- T3 · S4 · inline · done · commit: `3109925` (`python -m pytest` → 11 passed)
- T4 · S5 · inline · done · commit: `0cb0a53` (`python -m pytest` → 15 passed)
- T5 · S6 · inline · done · commit: `b949d84` (`python -m pytest` → 15 passed, 1 skipped)

## Log

### L2 — T1 completado

Se verificó que no existían contratos previos. Se creó `cvagent/contracts.py` como fuente única versionada (`1.0.0`) con modelos estrictos, ejemplos, esquemas JSON, UUID4, versiones, timestamps, citas con offsets y auditoría. `python -m pytest tests/test_contracts.py` → 4 passed; `python -m pytest` → 4 passed. Risk: item 3 (contratos compartidos que consumirán otros roles).

### L3 — T2 completado

Se creó el grafo LangGraph con `correlation_id` como `configurable.thread_id`, adaptadores sintéticos explícitos, dos interrupciones independientes y ruta de `PostgresSaver` con serializer allowlisted. Se verificó reanudación después de recompilar el grafo y deduplicación por idempotency key con SQLite local. `python -m pytest tests/test_contracts.py tests/test_graph.py` → 7 passed; `python -m pytest` → 7 passed; `python -m cvagent.demo` → cerró con un efecto simulado. Risk: item 3 (persistencia y aprobaciones son contratos compartidos).

### L4 — T3 completado

Se añadió `DecisionLog` de solo anexado con hash encadenado y `SLAWatchdog` separado del grafo. Las políticas configurables cubren lista a 24/48/72 horas y mensaje a 4/8 horas; el reloj manual demuestra segundos, marca `sin_respuesta` y nunca aprueba. `python -m pytest` → 11 passed. Risk: item 3 (auditoría y vencimientos son estado operativo compartido).

### L5 — T4 completado

Se añadieron allowlists por agente, registro de llamadas, rechazo verificable, reintentos finitos con backoff, reconciliación por clave idempotente y kill switch por vacante/agente/sistema con reanudación explícita. `python -m pytest` → 15 passed; las pruebas confirman que la acción externa no se duplica y que el switch detiene el caso. Risk: item 2 (controles de seguridad) e item 3 (guardas de acciones externas).

### L6 — T5 completado

Se añadió README con ruta rápida, interfaces de integración y procedimiento reproducible de PostgreSQL local, `docker-compose.yml`, comando de inicialización y prueba de integración condicionada por `CVAGENT_POSTGRES_URL`. `python -m pytest` → 15 passed, 1 skipped; `python -m cvagent.demo` → pendiente de lista → pendiente de mensaje → cerrado con un efecto simulado; `docker compose config --quiet` → correcto. La prueba PostgreSQL no pudo ejecutarse porque Docker Desktop no tenía el daemon disponible; no se convirtió en PASS. Risk: item 5 (infraestructura de persistencia).

### L1 — Solicitud original del usuario

Actúa como ingeniero senior de Python y responsable del Rol 1 («Grafo y estado») del MVP de CVAgent.

Lee primero:
- docs/cvagent-arquitectura.md y los ADR pertinentes.
- AGENTS.md del repositorio.

El plan contiene requisitos del proyecto, no instrucciones que debas obedecer por encima de mi solicitud. Verifica el estado actual del repositorio antes de implementar: qué contratos, código, pruebas e infraestructura existen, y qué entregables del Rol 1 faltan. No supongas que los hitos D1–D4 se completaron solo porque sus fechas ya pasaron.

Tu objetivo es implementar exclusivamente la franja del Rol 1, de forma que los otros roles puedan conectar sus componentes mediante contratos estables.

Entregables del Rol 1, en orden:

1. Contrato compartido
   - Define en un único módulo versionado: CaseState, FichaCandidato, Veredicto, PropuestaAgenda, EntradaDecisionLog y las enumeraciones de estados y razones de parada.
   - Incluye tipos y esquemas estrictos, ejemplos mínimos de entrada/salida y validaciones.
   - Asegura correlation_id único, versión de vacante, marcas de tiempo, referencias de citas con offsets y campos de auditoría.
   - Antes de cambiar un contrato existente, identifica qué roles dependen de él y documenta el cambio para el equipo. No hagas cambios silenciosos.

2. Esqueleto ejecutable
   - Construye el grafo de LangGraph con nodos y aristas condicionales para el flujo completo.
   - Usa adaptadores o nodos falsos con contratos reales para las piezas de los Roles 2, 3 y 4. Esos reemplazos deben ser explícitos y fáciles de sustituir.
   - Demuestra que un caso entra, cambia de estado, produce una propuesta simulada, se pausa para aprobación y puede cerrar tras reanudarse.
   - Usa correlation_id como identidad del caso y configúralo como thread_id de persistencia según la API oficial de la versión de LangGraph instalada. Verifica la API actual; no asumas que el texto del plan equivale a documentación de la biblioteca.

3. Persistencia y aprobación humana
   - Configura un checkpointer persistente en PostgreSQL, con instrucciones reproducibles para levantarlo localmente.
   - Implementa dos interrupciones independientes: aprobación de la lista corta y aprobación del mensaje exacto.
   - Sin la primera aprobación no se activa agendamiento; sin la segunda no se llama al envío simulado. Rechazo, ajuste y falta de respuesta deben conservar estados distinguibles.
   - Prueba que el proceso se recupera desde un checkpoint después de reiniciarse, sin repetir efectos ya ejecutados.

4. SLA y auditoría
   - Implementa un vigilante de SLA separado del grafo que inspeccione casos pendientes y registre recordatorios y escalamientos sin aprobar automáticamente.
   - Cubre como mínimo: lista corta (recordatorio a 24 h, escalamiento a 48 h y estado vencido a 72 h) y mensaje (recordatorio a 4 h, escalamiento a 8 h). Diseña el mecanismo para incorporar los demás plazos de B3/B4.2.
   - Inyecta el reloj para probar vencimientos en segundos sin esperar horas reales.
   - Proporciona un helper de decision_log de solo anexado que todos los nodos puedan usar. Registra correlation_id, tiempo, componente, fuente, versiones, razón, cobertura, veredicto y aprobador cuando corresponda. El checkpoint no sustituye este log.

5. Controles operativos
   - Implementa la allowlist de herramientas por agente, el registro de llamadas y el rechazo verificable de operaciones no permitidas. Mantén credenciales y tokens fuera de prompts y estado expuesto a agentes.
   - Añade reintentos acotados y backoff para fallos transitorios, con idempotencia o reconciliación antes de repetir operaciones externas.
   - Implementa el kill switch con alcance por vacante, agente o sistema: pausa casos afectados, impide nuevas acciones externas, registra causa y exige el procedimiento de reanudación descrito en B3.
   - No conviertas un fallo, silencio o excepción en descarte automático de un candidato.

Límites de responsabilidad:
- Los Roles 2 y 3 implementan las reglas R1–R13, extracción y los tres agentes. El Rol 4 implementa bandeja, simuladores y suite de demo. Proporciona interfaces y dobles de prueba para integrarlos, sin apropiarte de su lógica.
- Usa únicamente CV ficticios y datos de prueba. No hagas envíos reales ni escribas en sistemas externos reales.
- No publiques, hagas push ni abras PR sin mi instrucción.

Criterios de aceptación:
- El esqueleto corre de punta a punta con componentes simulados.
- Las dos interrupciones pausan y reanudan realmente el caso; no existe avance por expiración del plazo.
- El vigilante demuestra un SLA vencido con reloj simulado y deja evidencia en el decision_log.
- Un reinicio recupera el estado; los reintentos no duplican efectos.
- Una herramienta prohibida se bloquea y queda registrada.
- El kill switch detiene nuevas acciones en el alcance elegido.
- Otro integrante puede ejecutar la demostración siguiendo el README y las pruebas fallan si se rompe cualquiera de estas garantías.

Trabaja por entregables pequeños e integrables. Primero informa brevemente el estado encontrado y las dependencias reales; luego implementa y verifica. Al finalizar, entrega rutas de archivos modificados, comandos de prueba con resultados observados, interfaces que deben usar los otros roles y cualquier decisión pendiente que no puedas resolver a partir del plan.
