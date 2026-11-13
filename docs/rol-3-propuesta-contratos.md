# Rol 3 → Rol 1: observaciones al contrato v1.0.0 (borrador)

**Estado:** propuesta para discutir con el Rol 1. Este documento no modifica `contracts.py`.
**Base revisada:** `HAUT-2026/cv-agent`, commit `68e4e2d` (`cvagent/domain/contracts.py`, `cvagent/integration/ports.py`).

El contrato v1.0.0 está muy bien resuelto (modelos estrictos, `CitationRef.verify_against`, decision_log con hash, gateway con tokens). El prototipo del Rol 3 ya es compatible con la verificación de citas: el agente devuelve la cita literal y el código calcula los offsets exactos sobre el texto sanitizado. Para conectar los agentes reales encontramos estas brechas:

| # | Brecha | Por qué afecta al Rol 3 | Propuesta (v1.1, compatible hacia atrás) |
|---|---|---|---|
| 1 | `CaseState` no referencia el CV ni el texto sanitizado | `AnalistaPort.crear_ficha(state)` no tiene de dónde leer el CV | Agregar `cv_ref: str` (u `texto_sanitizado_ref`) opaco, que resuelva un repositorio fuera del modelo |
| 2 | `FichaCandidato` no tiene evaluaciones por requisito: solo `resumen` + `citas` | El analista evalúa cada requisito (estado + citas); hoy no hay dónde ponerlo, y el motor de reglas y el auditor lo necesitan | Agregar `evaluaciones: list[EvaluacionRequisito]` con `requisito_id`, `estado` y `citas: list[CitationRef]` |
| 3 | Vocabulario de estados del requisito | El documento propone `cumple`, `no_cumple`, `no_acreditado` y `por_confirmar`; el prototipo usa `cumple`, `parcial`, `no_cumple` y `sin_evidencia` | Fijar un enum único en el contrato. Mapeo sugerido: `sin_evidencia` → `no_acreditado`; `parcial` → `por_confirmar` (o valoración 0,25-0,75 en deseables) |
| 4 | `Veredicto` solo tiene `razon: str` | El auditor produce varios hallazgos, cada uno con tipo, severidad y offset; un texto libre no es auditable | Agregar `hallazgos: list[Hallazgo]` (tipo enum, severidad, requisito_id, `CitationRef` opcional) |
| 5 | Rótulos de los dobles | `SyntheticRole2Analyzer` es del Rol 3 (agentes) y `SyntheticRuleEngine` («Role 3 adapter») es del Rol 2 (reglas) según el plan | Renombrar o corregir los docstrings |
| 6 | Gateway | El motor de agentes del Rol 3 ya aplica allowlist por agente y registra cada llamada (incluidos los rechazos) | Que el motor del Rol 3 llame las herramientas a través de `OperationalControls.call_tool` con el token del agente/caso, para no duplicar el gateway |
| 7 | Versiones en `AuditMetadata` | El analista ya reporta `modelo` (`modelo@host`) y `version_prompt` (`analista-v3.1`) | Sin cambio: se mapean a `modelo_version` y `prompt_version` |
| 8 | Ubicación del Rol 3 | — | El Rol 3 vive en el subpaquete `cvagent/agentes/` (sin tocar módulos de otros roles) |

## Lo que el Rol 3 ya valida contra el dataset del Rol 2 (sin LLM)
- Adaptador del JSON del equipo → texto canónico; `persona` y el año de grado nunca entran (R7); `texto_oculto` se bloquea y queda como indicio.
- Experiencia efectiva provisional (empleo + freelance, sin solapes, `[inicio, fin)`): **12/12 coinciden con el manifiesto**.
- Detección de inyección: **12/12** (4 de 4 trampas, 0 falsos positivos).
- Proxies de R7 residuales marcados en CV-010.
