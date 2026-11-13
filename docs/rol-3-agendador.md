# Rol 3 · Agente agendador

> **Estado:** operativo como módulo (`cvagent/agentes/agendador.py`) con 19 pruebas. Plantillas y calendario son **sintéticos** (pendientes de RR. HH. y del Rol 4). Diseño acordado el 12-nov-2026.

## Qué hace (y qué no)

Para cada candidato de la **lista ya aprobada** por el reclutador, propone **una plantilla y una franja** de entrevista y deja el **texto exacto** listo para la segunda aprobación humana (R10, ADR-004). Implementa el contrato del Rol 1: `AgendadorPort.proponer(state, propuesta_lista, now)` → `PropuestaAgenda`.

| Sí | No |
|---|---|
| Elegir plantilla según el tipo de entrevista pedido y la modalidad de la vacante | Ver la hoja de vida, la ficha, el `cv_id` o el nombre del candidato |
| Elegir franjas libres para todo el panel, sin cruces entre candidatos | Escribir el mensaje: el texto lo arma el **código** desde la plantilla |
| Usar herramientas de solo lectura | Enviar, reservar o escribir en calendario, correo o ATS |

SDD: «Agente agendador: redactar borrador usando plantilla, cargo, nombre de pila y franjas. Sin acceso al CV ni a herramientas de escritura.» · «El workflow consulta free/busy; el agendador redacta desde plantilla sin acceso al CV.»

## Las tres decisiones

**A. Agente acotado.** El LLM decide (plantilla y franja de cada candidato) con dos herramientas de solo lectura: `ver_plantillas` y `consultar_franjas`. Su salida (`AgendaLLM`) **no tiene campo de texto**: solo `candidato_ref`, `plantilla_id` y `franja_id`. El texto lo construye `Plantillas.renderizar` con variables permitidas (`cargo`, `fecha`, `hora_inicio`, `hora_fin`, `duracion_min`, `ciudad`).
*Descartadas:* B (todo determinista: deja de ser agente) y C (el LLM redacta libre: podría prometer o filtrar cosas; el SDD exige plantilla).

**Marcador `{{nombre_de_pila}}`.** El texto aprobado lleva el marcador; el **envío (Rol 4)** lo reemplaza desde la bóveda de identidad después de la aprobación. Así ningún nombre real entra a `PropuestaAgenda` (regla 4 de integración del Rol 1). Tensión con el SDD documentada en `rol-3-propuesta-contratos.md` (brecha 10).

**Datos propios.** `cvagent/agentes/agenda/plantillas.json` (versionadas: `plantillas-v1`) y `calendario_simulado.json` (free/busy de un panel de 2 personas, 16 al 27 de nov de 2026, con el festivo del lunes 16). No se toca `data/` (Rol 2). La consulta de franjas está en la clase `Calendario`: el Rol 4 la reemplaza por el free/busy real con la misma interfaz.

## Barandas (código, no prompt)

| Regla | Qué pasa si el LLM la rompe |
|---|---|
| Cada candidato de la lista exactamente una vez; ninguno extra | Rechazo con el detalle |
| Plantilla existente, del **tipo pedido** y compatible con la **modalidad** | Rechazo con la lista de plantillas válidas |
| Franja libre para **todo el panel**, día hábil, no festivo, fuera del almuerzo y con ≥ **24 h** de anticipación | Rechazo con las franjas válidas aún sin usar |
| Sin cruces entre candidatos | Rechazo con las franjas válidas aún sin usar |
| Tras **3 rechazos** | `agendar()` vuelve a validar y lanza `AgendaInvalida`: **no sale nada**, el caso va a un humano (fail-closed) |
| Texto final = plantilla renderizada | `verificar_propuesta()`; sirve al workflow después de un «ajustar» del reclutador (SDD: «texto idéntico al aprobado») |

El rechazo trae las opciones válidas (la misma lección de B2 en el analista: **mostrar** la evidencia, no solo ordenar).
`consultar_franjas` ofrece **solo franjas que no se cruzan entre sí**: al probar con un LLM simulado que asignaba «a cada uno la siguiente», las franjas de 10:00, 10:30 y 11:00 de 60 min se pisaban y la agenda terminó en fail-closed.

## Corridas con el LLM real (qwen2.5:7b, 12-nov)

| Corrida | Qué pasó | Corrección |
|---|---|---|
| 1 | Plantilla correcta (`tecnica_virtual`, virtual en modalidad híbrida) y las 6 franjas **idénticas** a las de la asignación determinista, en orden y sin cruces. Pero llamó `vista_previa` **una vez por candidato**, en turnos separados, y agotó los 8 pasos sin entregar. El script además terminó en traceback | `vista_previa` deja de ser herramienta del agente (el texto lo arma el código: no aportaba a la decisión y daba una «tarea por candidato» que consumía turnos); el prompt pide entregar todas las asignaciones juntas; agotar los pasos es `AgendaInvalida` (fail-closed limpio), no un traceback |
| 2 | **3 pasos, 104 s, sin ningún rechazo**: `ver_plantillas` → `consultar_franjas` → una sola entrega con los 6 candidatos. Plantilla `tecnica_virtual` y franjas sin cruces (17-nov 11:00 y 14:00, 19-nov 10:00 y 11:00, 20-nov 11:00 y 13:00), idénticas a la asignación determinista; los 6 textos idénticos a la plantilla | — |

104 s es **por lista** (6 candidatos), no por CV: el agendador es mucho más barato que el analista (330 a 740 s por CV en el mismo equipo).

Misma lección que en el analista: con un modelo pequeño, lo que no aporta a la decisión se quita del entorno en lugar de pedirle por prompt que no lo use.

## Separación del CV (ADR-002)

- El agendador tiene **su propio registro de herramientas** (`REGISTRO_AGENDA`): ni siquiera puede nombrar `buscar_en_cv`; si lo pide, el motor lo rechaza y lo registra.
- Recibe solo **referencias opacas** `cand_…` (`ref_opaca(cv_id, vacante_id)` = hash); el `cv_id` se traduce fuera, en el workflow.
- Prueba: ningún valor de `persona` de los 6 CV del Top ni su `cv_id` aparece en los textos.

## Cómo probarlo

```bash
python -m pytest tests/test_rol3_agendador.py      # 19 pruebas, sin LLM
python scripts/rol3/agendar.py --sin-llm           # Top del staging simulado → agenda determinista
python scripts/rol3/agendar.py                     # el agente con el LLM de .env
python scripts/rol3/agendar.py --ahora 2026-11-20T09:00   # otra «fecha actual»
```

## Pendiente

- Aprobación de plantillas por RR. HH. (son sintéticas) y política de recordatorios (ADR-004).
- Contrato v1.1: una `PropuestaAgenda` por candidato (brecha 9) y decisión sobre el nombre de pila (brecha 10).
- Integración al grafo: `AgendadorRol3(info, cliente)` implementa `AgendadorPort`; como no necesita el CV, **no depende de la brecha 1** y es la primera pieza del Rol 3 que puede conectarse al grafo.
