# Rol 3 · Agentes: analista, auditor y agendador

Los tres agentes de CVAgent y las piezas deterministas que los rodean (sanitización, verificación de citas,
puntaje). Reciben solo los CV que el motor del Rol 2 deja como `evaluable` y deciden si van al `ranking` o a
la `bandeja` de revisión humana; el agendador propone la entrevista de la lista corta aprobada.

**Principio: el código busca y verifica; el LLM solo juzga.** Nada que pueda calcular el código lo decide el
modelo: las citas las ubica el código, el puntaje lo calcula el código y el auditor es determinista.
Funciona con cualquier proveedor compatible con el protocolo de OpenAI (Ollama local, OpenAI, Gemini…),
configurado por `.env`. Solo datos sintéticos.

> Guía paso a paso, con Docker y Ollama, salidas esperadas y solución de errores:
> **[docs/rol-3-ejecucion.md](docs/rol-3-ejecucion.md)**.
> Para asistentes de IA: [`cvagent/agentes/AGENTS.md`](cvagent/agentes/AGENTS.md).

## Los tres agentes

| Agente | Qué hace | ¿Usa LLM? | Puede |
| --- | --- | --- | --- |
| **Analista** | Evalúa cada requisito de la vacante contra el CV con herramientas (`buscar_en_cv`, `frases_relacionadas`, `consultar_equivalencias`, `experiencia_por_cargo`) y respalda cada juicio con una cita literal | Sí | Proponer `cumple` / `parcial` / `no_cumple` / `sin_evidencia` |
| **Auditor** | Revisa la ficha del analista: citas que no aparecen en el CV, obligatorios sin evidencia, evidencia ignorada, inyección | No (determinista) | **Bloquear, nunca aprobar** |
| **Agendador** | Elige plantilla y franja (`ver_plantillas`, `consultar_franjas`) para la lista corta aprobada; el texto lo arma el código con el marcador `{{nombre_de_pila}}` | Sí, acotado | Proponer; el mensaje lo aprueba una persona |

## Flujo

```
motor del Rol 2 (R12, R1, R2, R11/R3, R7)
  └─ solo «evaluable» ──► sanitización (inyección → bandeja)
                            └─► analista (LLM) ──► auditor ──► bloquea → bandeja
                                                         └─► sin objeciones → ranking
                                                               └─► puntaje (código) ──► armar_staging del Rol 2 (R4, R5, R6)
                                                                     └─► Top ──► aprobación humana ──► agendador ──► aprobación del mensaje
```

Estados del analista hacia el motor: `cumple→cumple`, `no_cumple→incumple`, `sin_evidencia→no_acreditado`,
`parcial→por_confirmar`.

## Qué contiene

| Carpeta | Contenido |
| --- | --- |
| `cvagent/agentes/` | `cv_json.py` (CV → texto canónico anónimo con R7 oficial), `texto.py` (verificación de citas: las cifras nunca se aproximan), `sanitizacion.py` (inyección y proxies), `criterios.py` (vacante versionada + equivalencias), `herramientas.py`, `agente.py` (ciclo razonar → actuar → observar, allowlist, barandas), `llm.py` (cliente agnóstico), `analista.py`, `auditor.py`, `ficha.py`, `salida.py`, `rubrica.py` + `puntaje.py`, `evaluacion.py`, `agendador.py` + `agenda/` |
| `scripts/rol3/` | `probar_banco.py` (banco de punta a punta contra el manifiesto, con o sin LLM), `agendar.py` (agenda el Top del staging) y `auditar.py` (re-audita fichas guardadas sin LLM) |
| `tests/` | `test_rol3_*.py` y `rol3_comun.py` (373 pruebas, con un LLM falso: no usan red ni modelo) |
| `docs/` | `rol-3-ejecucion.md` (guía), `rol-3-agentes.md` (diseño), `rol-3-evaluacion.md` (mediciones con LLM real), `rol-3-puntaje.md` (rúbrica provisional), `rol-3-agendador.md`, `rol-3-propuesta-contratos.md` (brechas del contrato v1.0.0) |

`.env` (claves del LLM) y `resultados/` (fichas generadas) no se suben a git. `data/manifiesto.json` es la
hoja de respuestas: solo la usa el banco para medir, nunca entra a un prompt ni a una herramienta.

## Cómo probarlo

Sin LLM ni red (Docker; en macOS o Linux, cambia `${PWD}` por `$(pwd)`):

```bash
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic pytest && python -m pytest tests/test_rol3_agendador.py tests/test_rol3_agente.py tests/test_rol3_analista.py tests/test_rol3_auditor.py tests/test_rol3_citas.py tests/test_rol3_evaluacion.py tests/test_rol3_ficha.py tests/test_rol3_puntaje.py tests/test_rol3_sanitizacion.py"
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic && python scripts/rol3/probar_banco.py --sin-llm"
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic && python scripts/rol3/agendar.py --sin-llm"
```

La primera debe terminar con `373 passed`. La segunda pasa los 44 CV por el motor del Rol 2 y la
sanitización del Rol 3 y debe terminar con `Ruta final de punta a punta (Rol 2 + Rol 3): 44/44`, seguido
del Top simulado con la rúbrica provisional. La tercera agenda ese Top sin LLM.

Con LLM (Ollama con `qwen2.5:7b` y un `.env`; pasos 6 a 8b de la [guía](docs/rol-3-ejecucion.md)):

```bash
docker run --rm -it -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic && python -u scripts/rol3/probar_banco.py CV-001 CV-040"
docker run --rm -it -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic && python -u scripts/rol3/agendar.py"
```

## Resultados medidos

Detalle y salidas completas en [`docs/rol-3-evaluacion.md`](docs/rol-3-evaluacion.md),
[`docs/rol-3-puntaje.md`](docs/rol-3-puntaje.md) y [`docs/rol-3-agendador.md`](docs/rol-3-agendador.md).

| Qué | Resultado |
| --- | --- |
| Ruta final de punta a punta (motor + sanitización), sin LLM | 44/44 |
| Detector de inyección, prueba ciega sobre trampas nuevas | 4/5 antes de ajustar (falló INJ-04, en inglés); 44/44 después. Es una capa, no la única defensa |
| `frases_relacionadas`, deseables contra el manifiesto | 13/28 → 28/28 con evidencia fuerte (ajustado con este dataset; no prueba generalización) |
| Analista con LLM real, 4 CV (CV-001, CV-014 Kotlin, CV-040 texto oculto, INJ-04) | Ruta final 4/4, obligatorios 20/20, no obedeció ninguna inyección; el auditor bloqueó las dos inyecciones |
| Baranda B2 (el rechazo le muestra la evidencia al analista) | Deseables de CV-001: sin baranda 5 × `sin_evidencia` → con B2, DES-03 y DES-04 `cumple` con las frases fuertes |
| Puntaje (staging simulado) | Top 6 = CV-002, 001, 003, 005, 006, 007, todos aptos; R5 activo; par contrafactual CV-006 = CV-007; CV-040 = su gemelo limpio CV-008 |
| Agendador con LLM real | 3 pasos, 104 s, 0 rechazos; franjas idénticas a la versión determinista |
| Tiempo del analista | 330–740 s por CV con `qwen2.5:7b` en una GTX 1650: no cumple la meta de 2 min/CV del SDD con el modelo local (ADR-007) |

## Decisiones provisionales

- **Rúbrica de puntaje provisional** (`rubrica-provisional-v1`, `docs/rol-3-puntaje.md`), pendiente de RR. HH. y
  del grupo. El portal del Rol 4 usa otra (hallazgo H-3): hay que reconciliarlas.
- **Plantillas del agendador** propias en `cvagent/agentes/agenda/`, pendientes de aprobación de RR. HH.
- **Contrato v1.1**: las brechas entre los modelos propios del Rol 3 y el contrato v1.0.0 del Rol 1 están en
  `docs/rol-3-propuesta-contratos.md`.

## Estado de la integración

Los tres agentes funcionan con LLM real a través de los scripts de `scripts/rol3/`. El agendador ya implementa
el puerto del Rol 1 (`AgendadorRol3`). El portal del Rol 4 todavía usa dobles sin LLM para el analista, el
auditor y el agendador; la conexión con los agentes reales está en curso en la rama
`feature/rol-3-integracion-portal`.
