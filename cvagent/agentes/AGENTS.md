# AGENTS.md · Rol 3 (agentes analista y auditor)

Instrucciones para un asistente de IA que ayuda a una persona a **instalar, ejecutar, entender o modificar** el Rol 3 de CVAgent. Complementa el `AGENTS.md` de la raíz (contexto del proyecto y límites de autonomía). La guía para personas, con el mismo recorrido, está en [`docs/rol-3-ejecucion.md`](../../docs/rol-3-ejecucion.md). Si la persona prefiere leer, remítela a esa guía.

> Nota: el `AGENTS.md` de la raíz dice que «todavía no hay implementación». Quedó desactualizado: el Rol 1 (grafo), el Rol 2 (`reglas/`, `data/`) y este paquete ya tienen código y pruebas.

## 1. Qué es esto, en cinco líneas

- **Analista** (`analista.py`): un LLM con herramientas que juzga, requisito por requisito, la evidencia de un CV y entrega citas **literales**. No decide quién pasa ni calcula puntajes.
- **Auditor** (`auditor.py`): **código determinista, sin LLM**. Revisa la ficha del analista y devuelve `bloquea` o `sin_objeciones`. Puede bloquear; nunca aprueba.
- **Principio:** el código busca y verifica (texto canónico, offsets, experiencia R11, inyección); el LLM solo juzga.
- **Flujo:** motor del Rol 2 (`reglas/motor.py`) → solo lo `evaluable` pasa al Rol 3 → si la sanitización o el auditor bloquean, el caso va a `bandeja` (revisión humana); si no, a `ranking`.
- **Estado:** funciona como módulo y con scripts. **No está conectado al grafo** del Rol 1: depende del contrato v1.1 (`docs/rol-3-propuesta-contratos.md`).

## 2. Reglas que no debes romper al ayudar

1. **Nunca pidas ni aceptes una API key en el chat.** La clave va solo en el `.env` local de la persona. Si la pega en el chat, dile que la revoque y la regenere.
2. **`.env` y `resultados/` nunca se suben a git** (ya están en `.gitignore`). No sugieras `git add -A` sin revisar antes con `git status`.
3. **`data/manifiesto.json` es la hoja de respuestas.** Solo lo usan las pruebas y `probar_banco.py` para medir. Nunca lo pases a un prompt, a una herramienta del agente ni al contexto del analista.
4. **Solo datos sintéticos.** No ayudes a meter CV reales en `data/`, en pruebas ni en logs.
5. **No modifiques archivos de otros roles** (`cvagent/domain/contracts.py`, `cvagent/graph/`, `reglas/`, `data/`). Si algo de allí debe cambiar, ayuda a redactar una propuesta (como `docs/rol-3-propuesta-contratos.md`).
6. **Fail-closed:** ante errores, timeouts o dudas, el CV va a la bandeja humana. No propongas «arreglos» que descarten automáticamente.
7. **Si cambias código del Rol 3**, corre las pruebas (paso 4) antes de decir que funciona. Si cambias el prompt, sube `VERSION_PROMPT` en `analista.py`.

## 3. Recorrido guiado (lista de verificación)

Avanza **un paso a la vez**. Pide a la persona que te pegue la salida y compárala con el criterio de éxito antes de seguir. Primero pregunta su sistema operativo y si tiene Docker. Los comandos son para PowerShell: en macOS o Linux, cambia `${PWD}` por `$(pwd)`.

| # | Objetivo | Comando | Criterio de éxito |
|---|---|---|---|
| 1 | Herramientas | `git --version` · `docker --version` · (LLM) `ollama --version` | Las tres responden con una versión |
| 2 | Código | `git clone https://github.com/HAUT-2026/cv-agent.git`, `cd cv-agent` y, si el PR no está fusionado, `git checkout feature/rol-3-agentes` | `git branch` muestra la rama correcta y existe `cvagent/agentes/` |
| 3 | Docker encendido | `docker version` | Aparece el bloque `Server:` |
| 4 | Pruebas | Comando del paso 4 de la guía (pydantic, pytest y pypdf; lista explícita de archivos) | Termina en `434 passed` |
| 5 | Banco sin LLM | `... python scripts/rol3/probar_banco.py --sin-llm` | Última línea: `44/44 · ... 44/44 · Meses R11: 41/41` |
| 6a | Modelo | `ollama pull qwen2.5:7b` y `ollama show qwen2.5:7b` | `Capabilities` incluye `tools` |
| 6b | Ollama accesible desde Docker | `setx OLLAMA_HOST 0.0.0.0` y `setx OLLAMA_CONTEXT_LENGTH 8192`, reiniciar Ollama y probar `/api/tags` desde un contenedor | La respuesta lista `qwen2.5:7b` |
| 7 | `.env` | `Copy-Item .env.example .env` y editar | `LLM_BASE_URL=http://host.docker.internal:11434/v1`, `LLM_MODELO=qwen2.5:7b`, `LLM_MAX_TOKENS=2000`, `LLM_TIMEOUT=600` |
| 8 | Analista + auditor | `docker run --rm -it ... python -u scripts/rol3/probar_banco.py CV-001` | Muestra la ficha con citas, el veredicto del auditor y `Ruta final: ranking · esperada: ranking ✓` |
| 9 | Re-auditar | `... python scripts/rol3/auditar.py` | Imprime el veredicto de cada ficha de `resultados/rol3/` |

Los comandos completos y la explicación de cada parte están en `docs/rol-3-ejecucion.md`. Cópialos de allí, no los reconstruyas.

**Si la persona no puede o no quiere instalar Ollama:** los pasos 1-5 bastan para demostrar el flujo, la detección de inyección, la verificación de citas y el auditor (las pruebas usan un LLM falso). Para los pasos 8-9 puede usar un proveedor con API compatible con OpenAI, cambiando las tres líneas `LLM_*` en su `.env`.

## 4. Árbol de diagnóstico

```
¿Falla un comando docker?
├─ "error during connect" / sin bloque Server ........ Docker Desktop cerrado → abrirlo
└─ "No module named pydantic" ........................ falta el pip install del comando

¿Fallan las pruebas?
├─ "No module named langgraph" ....................... corrió pytest sin lista → usar la lista del paso 4
├─ FileNotFoundError en data/... ..................... no está en la raíz del repo o en la rama equivocada
└─ F en test_rol3_* .................................. leer la aserción; si cambió data/, el Rol 2 regeneró el dataset

¿Falla el LLM (paso 8)?
├─ "Faltan variables de entorno" ..................... falta .env en la raíz (ojo con .env.txt en Windows)
├─ "Connection refused" .............................. Ollama cerrado │ OLLAMA_HOST≠0.0.0.0 │ localhost dentro de Docker
│                                                      │ Linux: falta --add-host=host.docker.internal:host-gateway
├─ "HTTP 404 ... not found" .......................... modelo no descargado o nombre distinto en .env
├─ "HTTP 400 ... does not support tools" ............. modelo sin tools → qwen2.5:7b
├─ "tardó más de N s" ................................ hardware lento → ollama ps; subir LLM_TIMEOUT
├─ respuestas incoherentes o requisitos ignorados .... OLLAMA_CONTEXT_LENGTH sin configurar
├─ ficha cortada / _corte_por_longitud ............... LLM_MAX_TOKENS < 2000
└─ AgenteSinResultado ................................ el modelo no entregó un JSON válido en 15 pasos;
                                                       fail-closed (bandeja). Reintentar o usar un modelo mayor
```

## 5. Cómo leer los resultados (para explicarlos)

- **Estados del analista:** `cumple` (evidencia fuerte), `parcial` (débil: solo en la lista de habilidades, estudios en curso, idioma sin acreditar), `no_cumple` (el CV muestra que no alcanza), `sin_evidencia` (el CV no dice nada; no es lo mismo que no cumplir). Equivalen a los del motor así: `cumple→cumple`, `no_cumple→incumple`, `sin_evidencia→no_acreditado`, `parcial→por_confirmar` (`evaluacion.A_ESTADO_MOTOR`).
- **`✗ NO ENCONTRADA`:** el LLM citó algo que no está literalmente en el CV. El código lo rechaza y el auditor bloquea. Es la defensa contra alucinaciones.
- **🔴 y 🟡:** los 🔴 bloquean y mandan el caso a la bandeja; los 🟡 son señales para el reclutador. La lista completa está en `docs/rol-3-agentes.md`.
- **Coincidencia con el manifiesto:** un `✗` en un requisito no implica un error del código. Mide cuánto se parece el juicio del modelo al esperado; con un modelo de 7B hay variación entre corridas. La métrica que importa para el flujo es la **ruta final**.

## 6. Mapa del código (para preguntas o cambios)

| Si preguntan por… | Mira |
|---|---|
| Cómo se arma el texto que ve el LLM y qué se quita (R7) | `cv_json.py` (`preparar_caso`) |
| Cómo se verifica una cita | `texto.py` (`localizar_cita`: campo completo → exacta → normalizada → aproximada ≥ 0,90; las cifras nunca se aproximan) |
| Detección de inyección y proxies | `sanitizacion.py` (patrones en español e inglés, con offsets) |
| Herramientas del agente | `herramientas.py` (`frases_relacionadas`, `buscar_en_cv`, `consultar_equivalencias`, `experiencia_por_cargo` con R11 oficial) |
| El ciclo del agente | `agente.py` (allowlist, freno de repetidas, rechazo de entrega prematura, `validar_entrega`, límite de pasos, traza). En la traza, `entrega_incompleta` significa que el motor rechazó una entrega porque el modelo no había revisado evidencia disponible: es una baranda funcionando, no un error |
| Prompt y versión | `analista.py` (`INSTRUCCIONES`, `VERSION_PROMPT`) |
| Reglas del auditor | `auditor.py` (una sección numerada por tipo de hallazgo) |
| Cambiar de proveedor LLM | Solo `.env`. `llm.py` habla el protocolo de OpenAI sobre urllib, sin SDK |
| Ruta final y comparación | `evaluacion.py` y `scripts/rol3/probar_banco.py` |
| Pruebas | `tests/test_rol3_*.py`, con utilidades en `tests/rol3_comun.py`. Leen `data/`, sin frases fijas |

## 7. Si vas a modificar algo

1. Corre las pruebas (paso 4) **antes**, para tener una línea base.
2. Cambia el código del Rol 3 y agrega una prueba que reproduzca el caso, con datos de `data/` o una copia modificada en memoria (ver `datos()` en `tests/rol3_comun.py`). Nunca escribas en `data/`.
3. Corre las pruebas y el banco sin LLM: deben seguir en `434 passed` (o más) y `44/44`.
4. Si tocaste el prompt, sube `VERSION_PROMPT` y anota el cambio en el historial del encabezado de `analista.py`.
5. Para subir los cambios: rama propia, `git status` (que no aparezcan `.env` ni `resultados/`), commit y PR. Avisa al grupo de qué cambió.
