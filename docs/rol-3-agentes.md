# Rol 3 — Agentes (analista, auditor, agendador)

Estado: **analista y auditor determinista operativos como módulo** (`cvagent/agentes/`), probados con LLM real y con el dataset del Rol 2. **Todavía no están conectados al grafo**: falta que `CaseState` referencie el CV (ver [propuesta de contrato](rol-3-propuesta-contratos.md)). El auditor LLM y el agendador están en construcción.

## Principio de diseño: «el código busca y verifica, el LLM juzga»

El modelo solo decide lo que el código no puede decidir: si una frase del CV demuestra un requisito. Todo lo verificable lo hace código determinista:

| Lo hace el código | Lo hace el LLM |
|---|---|
| Construir el texto canónico desde el JSON (sin identidad ni año de grado, R7) | Juzgar si la evidencia cumple, cumple en parte, no cumple o no existe |
| Recuperar frases candidatas por requisito (`frases_relacionadas`, con las equivalencias versionadas de la vacante) | Elegir las citas |
| Ubicar cada cita en el texto y calcular offsets exactos (compatibles con `CitationRef.verify_against`) | |
| Rechazar citas inexistentes, parafraseadas o con cifras alteradas | |
| Calcular experiencia efectiva (provisional hasta R11 del Rol 2), cobertura y fit | |
| Detectar inyección y proxies de R7 | |
| Aplicar la allowlist, frenar bucles, rechazar entregas prematuras y validar el esquema | |

`frases_relacionadas` **no es RAG** (ADR-006): es recuperación léxica determinista dentro del mismo CV, por fragmento y offset, sin embeddings ni corpus externo.

## Módulos

| Módulo | Qué hace |
|---|---|
| `criterios.py` | `Vacante` y `Requisito` (con `equivalencias`, `titulos_aceptados`, `nota`) y `cargar_vacante(data/vacante_v1.json)` |
| `cv_json.py` | CV en JSON (formato del Rol 2) → limpieza Unicode → texto canónico. `persona` y `anio_fin` nunca entran; `texto_oculto` se bloquea y se reporta como indicio (E6) |
| `texto.py` | `TextoCanonico`, `localizar_cita` (campo completo → exacta → normalizada → aproximada ≥ 0,90; las cifras no se aproximan) |
| `sanitizacion.py` | Indicios de inyección (ES/EN) y proxies residuales de R7, con offsets |
| `salida.py` | `FichaLLM` (lo único que llena el modelo: estados y citas literales), `FichaCandidato`, `Veredicto`, `PropuestaAgenda` |
| `ficha.py` | `FichaLLM` → `FichaCandidato`: verifica cada cita y **no corrige al modelo** (las citas falsas quedan en `citas_rechazadas` para el auditor) |
| `llm.py` | Cliente **agnóstico del proveedor** (protocolo de chat de OpenAI con `tools`), configurado por `.env` |
| `herramientas.py` | `frases_relacionadas`, `buscar_en_cv`, `consultar_equivalencias`, `experiencia_por_cargo` y el registro central |
| `agente.py` | Motor razonar → actuar → observar: allowlist por agente, freno de llamadas repetidas, rechazo de entrega prematura, límite de pasos (fail-closed) y traza |
| `analista.py` | Prompt `analista-v3.1`, allowlist, `analizar_caso()` |
| `auditor.py` | Auditor **determinista**: `auditar(ficha, caso, vacante)` → `Veredicto` (`bloquea` / `sin_objeciones`; **no aprueba**) con hallazgos de severidad y offset |
| `evaluacion.py` | Comparación contra `data/manifiesto.json` (solo para medir) |

## Cómo correrlo

```bash
uv run pytest tests/test_rol3_*.py                       # 94 pruebas, sin LLM ni red
uv run python scripts/rol3/probar_banco.py --sin-llm     # 12 CV: experiencia (R11) e inyección contra el manifiesto
cp .env.example .env                                     # configurar el LLM (Ollama, OpenAI…)
uv run python scripts/rol3/probar_banco.py CV-007        # analista real sobre un CV
uv run python scripts/rol3/probar_banco.py todos         # banco completo (incluye el veredicto del auditor)
uv run python scripts/rol3/auditar.py                    # re-audita fichas guardadas en resultados/rol3/ sin llamar al LLM
```

## Auditor determinista

Independiente del analista (ADR-002): solo ve la ficha, el texto canónico, la vacante y los indicios de la sanitización. Bloquea, nunca aprueba.

| Hallazgo | Severidad | Origen (error real medido) |
|---|---|---|
| `indicio_inyeccion` (incluye `texto_oculto`) | 🔴 | CV-006, 007, 008, 011 |
| `cita_no_encontrada`, `afirmacion_sin_cita`, `requisito_desconocido` | 🔴 | LLM que inventa evidencia |
| `cobertura_insuficiente` (< 0,70, R4) | 🔴 | |
| `nivel_idioma_incoherente` (cumple con nivel < mínimo) | 🔴 | «Inglés (A2)» aceptado como B1 (v1) |
| `cita_con_proxy` (la evidencia contiene un proxy de R7) | 🔴 | CV-010 |
| `cita_sin_relacion` | 🔴 obligatorio / 🟡 deseable o experiencia | CV-007 corrida 1: REQ-01 y DES-04 |
| `evidencia_solo_lista` (cumple solo con la lista de habilidades) | 🟡 | CV-007 corrida 1: REQ-03 |
| `calificador_debil` (cumple con «básico», «en curso»…) | 🟡 | CV-007 corrida 1: DES-01 |
| `estado_incoherente` (estudios en curso marcados no_cumple) | 🟡 | CV propio de desarrollo |
| `nivel_idioma_incoherente` (no_cumple con nivel suficiente) | 🟡 | |
| `requisito_omitido` | 🟡 | |
| `senal_sesgo` (proxies de R7 en el CV) | 🟡 | CV-010 |

## Lo que falta

- **Integración al grafo** (`AnalistaPort`): depende de la propuesta de contrato v1.1 (referencia al CV, evaluaciones por requisito y hallazgos en `Veredicto`).
- **Auditor LLM**: lo semántico (SOAP ≠ REST; consumir ≠ diseñar).
- **Agendador**.
- Reemplazar las piezas provisionales cuando el Rol 2 las publique: R11 oficial y diccionario de equivalencias.
- Las llamadas a herramientas deberían pasar por `OperationalControls.call_tool` (gateway del Rol 1) en vez de la allowlist propia.

Evidencia y mediciones: [rol-3-evaluacion.md](rol-3-evaluacion.md).
