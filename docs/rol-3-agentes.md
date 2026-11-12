# Rol 3 — Agentes (analista, auditor, agendador)

Estado: **analista y auditor determinista operativos como módulo** (`cvagent/agentes/`), integrados con el motor de reglas del Rol 2 (`reglas/`) y probados con LLM real. Banco sin LLM: **44/44** en ruta final de punta a punta. **Todavía no están conectados al grafo**: falta que `CaseState` referencie el CV (ver [propuesta de contrato](rol-3-propuesta-contratos.md)). El auditor LLM y el agendador están en construcción.

## Principio de diseño: «el código busca y verifica, el LLM juzga»

El modelo solo decide lo que el código no puede decidir: si una frase del CV demuestra un requisito. Todo lo verificable lo hace código determinista:

| Lo hace el código | Lo hace el LLM |
|---|---|
| Construir el texto canónico desde el JSON (sin identidad ni año de grado, R7) | Juzgar si la evidencia cumple, cumple en parte, no cumple o no existe |
| Recuperar frases candidatas por requisito (`frases_relacionadas`, con las equivalencias versionadas de la vacante) | Elegir las citas |
| Ubicar cada cita en el texto y calcular offsets exactos (compatibles con `CitationRef.verify_against`) | |
| Rechazar citas inexistentes, parafraseadas o con cifras alteradas | |
| Calcular experiencia efectiva (R11 oficial del Rol 2), cobertura y fit | |
| Detectar inyección y proxies de R7 | |
| Aplicar la allowlist, frenar bucles, rechazar entregas prematuras y validar el esquema | |

`frases_relacionadas` **no es RAG** (ADR-006): es recuperación léxica determinista dentro del mismo CV, por fragmento y offset, sin embeddings ni corpus externo.

## Módulos

| Módulo | Qué hace |
|---|---|
| `criterios.py` | `Vacante` y `Requisito` y `cargar_vacante(data_dir, vacante_id, version)`: lee la vacante versionada con `reglas.cargar_vacante` y toma las equivalencias del diccionario oficial por `concepto` |
| `cv_json.py` | CV en JSON (formato del Rol 2, esquema cerrado) → limpieza Unicode → **R7 oficial** (`reglas.r7_anonimizar`) → texto canónico. `persona`, institución y año de grado nunca entran; `texto_oculto` se bloquea y se reporta como indicio (E6) |
| `texto.py` | `TextoCanonico`, `localizar_cita` (campo completo → exacta → normalizada → aproximada ≥ 0,90; las cifras no se aproximan) |
| `sanitizacion.py` | Indicios de inyección (ES/EN) y proxies residuales de R7, con offsets |
| `salida.py` | `FichaLLM` (lo único que llena el modelo: estados y citas literales), `FichaCandidato`, `Veredicto`, `PropuestaAgenda` |
| `ficha.py` | `FichaLLM` → `FichaCandidato`: verifica cada cita y **no corrige al modelo** (las citas falsas quedan en `citas_rechazadas` para el auditor) |
| `llm.py` | Cliente **agnóstico del proveedor** (protocolo de chat de OpenAI con `tools`), configurado por `.env` |
| `herramientas.py` | `frases_relacionadas` (en educación e idioma devuelve todos los registros de esa sección), `buscar_en_cv`, `consultar_equivalencias`, `experiencia_por_cargo` (**R11 oficial**) y el registro central |
| `agente.py` | Motor razonar → actuar → observar: allowlist por agente, freno de llamadas repetidas, rechazo de entrega prematura, **`validar_entrega`** (baranda propia de cada agente: rechaza hasta 2 veces una entrega válida pero incompleta), límite de pasos (fail-closed) y traza |
| `analista.py` | Prompt `analista-v3.2` (v3.2: acreditación de idioma, E5), allowlist, `analizar_caso()` y la baranda `evidencia_sin_revisar`: rechaza un `sin_evidencia` en un requisito que no buscó si `frases_relacionadas` sí tiene frases, y el rechazo **incluye esas frases** como observación (B2) |
| `auditor.py` | Auditor **determinista**: `auditar(ficha, caso, vacante)` → `Veredicto` (`bloquea` / `sin_objeciones`; **no aprueba**) con hallazgos de severidad y offset |
| `rubrica.py` | Rúbrica **provisional** del puntaje (pesos, valoraciones, tramos de experiencia, umbral R4), versionada con `VERSION_RUBRICA`. Detalle en [rol-3-puntaje.md](rol-3-puntaje.md) |
| `puntaje.py` | `calcular_puntaje(ficha, resultado_motor, vacante, diccionario, veredicto)` → `{puntaje, cobertura, contradiccion_material}` + desglose, en el formato de `armar_staging` del Rol 2 |
| `evaluacion.py` | `ruta_final(ruta_motor, rol3_bloquea)`, vocabulario de estados del analista → motor (`A_ESTADO_MOTOR`) y comparación contra `data/manifiesto.json` (solo para medir) |

## Cómo correrlo

Guía completa, con Docker, Ollama, salidas esperadas y solución de errores: **[rol-3-ejecucion.md](rol-3-ejecucion.md)**. En resumen:

```bash
python -m pytest tests/test_rol3_*.py                 # 354 pruebas, sin LLM ni red (solo pydantic + pytest)
python scripts/rol3/probar_banco.py --sin-llm         # 44 CV: motor Rol 2 + sanitización → ruta final 44/44
cp .env.example .env                                  # configurar el LLM (Ollama, OpenAI…)
python scripts/rol3/probar_banco.py CV-001            # analista real + auditor sobre un CV
python scripts/rol3/probar_banco.py todos             # banco completo (horas en hardware local)
python scripts/rol3/auditar.py                        # re-audita las fichas de resultados/rol3/ sin llamar al LLM
```

## Auditor determinista

Independiente del analista (ADR-002): solo ve la ficha, el texto canónico, la vacante y los indicios de la sanitización. Bloquea, nunca aprueba.

| Hallazgo | Severidad | Origen (error real medido o caso del dataset) |
|---|---|---|
| `indicio_inyeccion` (incluye `texto_oculto`) | 🔴 | CV-040 (texto oculto), INJ-01 a INJ-04 |
| `cita_no_encontrada`, `afirmacion_sin_cita`, `requisito_desconocido` | 🔴 | LLM que inventa evidencia u obedece la inyección |
| `obligatorio_sin_evidencia` (R4: criterio crítico sin evidencia) | 🔴 | Analista «perezoso» que marca todo `sin_evidencia` (cobertura 1,0 por vacío) |
| `cobertura_insuficiente` (< 0,70, R4) | 🔴 | |
| `nivel_idioma_incoherente`: `cumple` con nivel bajo el mínimo o **sin acreditación** cuando la vacante la exige | 🔴 | «Inglés (A2)» aceptado como B1 (v1); CV-029 (A2); CV-039 («Avanzado» sin certificado, E5) |
| `cita_con_proxy` (la evidencia contiene un proxy de R7) | 🔴 | Licencia de maternidad o familia en texto libre |
| `cita_sin_relacion` | 🔴 obligatorio / 🟡 deseable o experiencia | Corrida 1 de CV-007 (dataset previo): REQ-01 y DES-04 |
| `evidencia_solo_lista` (`cumple` solo con la lista de habilidades) | 🟡 | Corrida 1: REQ-03 |
| `calificador_debil` (`cumple` con «básico», «en curso»…) | 🟡 | Corrida 1: DES-01 |
| `estado_incoherente` (estudios en curso marcados `no_cumple`) | 🟡 | |
| `nivel_idioma_incoherente` (`no_cumple` con nivel suficiente) | 🟡 | |
| `evidencia_ignorada` (`sin_evidencia`, pero `frases_relacionadas` encuentra frases; red de seguridad de la baranda del analista) | 🟡 | CV-001, corrida del 11-nov: DES-01 a 04 sin buscar |
| `requisito_omitido` | 🟡 (y 🔴 `obligatorio_sin_evidencia` si es obligatorio) | |
| `senal_sesgo` (proxies de R7 en el CV) | 🟡 | |

## Lo que falta

- **Integración al grafo** (`AnalistaPort`): depende de la propuesta de contrato v1.1 (referencia al CV, evaluaciones por requisito y hallazgos en `Veredicto`).
- **Auditor LLM**: lo semántico (SOAP ≠ REST; consumir ≠ diseñar).
- **Agendador**.
- **Puntaje y cobertura:** hechos con rúbrica **provisional** (`rol-3-puntaje.md`); falta la aprobación de RR. HH. y del grupo.
- Las llamadas a herramientas deberían pasar por `OperationalControls.call_tool` (gateway del Rol 1) en vez de la allowlist propia.

Evidencia y mediciones: [rol-3-evaluacion.md](rol-3-evaluacion.md).
