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
| 9 | `AgendadorPort.proponer` devuelve **una** `PropuestaAgenda` por lista | La lista aprobada tiene hasta 5 (o 6 por R5) candidatos; el doble agenda solo al primero. El agendador del Rol 3 agenda a todos sin cruces de franja y, para cumplir v1.0.0, devuelve la del primero y deja todas en `AgendadorRol3.ultimas` | Que `proponer` devuelva `list[PropuestaAgenda]` (una por candidato) y que la aprobación del mensaje sea por propuesta |
| 10 | Nombre de pila en el texto frente a la regla 4 de integración («no se agrega nombre real a estos modelos») | El SDD dice que el agendador redacta con «nombre de pila»; si el texto lo trae, `PropuestaAgenda.texto_exacto` tendría un nombre real | Lo que hace hoy el Rol 3: `{{nombre_de_pila}}` como **marcador** en `texto_exacto`; el reclutador aprueba la plantilla con marcador y el envío (Rol 4) lo reemplaza desde la bóveda de identidad. Si el grupo prefiere que el reclutador vea el nombre, hay que ajustar la regla 4 |

## Lo que el Rol 3 ya valida contra el dataset oficial del Rol 2 (sin LLM)
- Adaptador del JSON del equipo → texto canónico con la **R7 oficial** (`reglas.r7_anonimizar`); `texto_oculto` se bloquea y queda como indicio.
- Experiencia efectiva con la **R11 oficial**: **41/41** con el manifiesto.
- Ruta final de punta a punta (motor del Rol 2 + sanitización del Rol 3): **44/44**.
- Puntaje y cobertura para `armar_staging` (rúbrica provisional): Top solo con aptos, R5 y R4 se activan (`rol-3-puntaje.md`).
- Agendador: `PropuestaAgenda` válidas del contrato v1.0.0, sin cruces, texto idéntico a la plantilla (`rol-3-agendador.md`).
