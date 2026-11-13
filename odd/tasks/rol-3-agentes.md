# Rol 3 — Agentes del MVP de CVAgent
Paquete: `cvagent/agentes/` · Test runner: `python -m pytest tests/test_rol3_*.py` (354) · Guía: `docs/rol-3-ejecucion.md`
Objetivo: agentes analista, auditor y agendador con salidas en esquemas estrictos, citas verificables por código y herramientas bajo allowlist, sin asumir lógica de negocio de otros roles.

## Specs

### S1 — Extracción y sanitización con offsets ✅
CV en JSON → texto canónico determinista; identidad y año de grado fuera (R7); `texto_oculto` bloqueado e indicio (E6); inyección y proxies con offsets.
Acceptance: ruta final 44/44 contra el manifiesto (4/5 en prueba ciega antes de ajustar patrones); R7 oficial del Rol 2; ningún valor de `persona` aparece en el texto.

### S2 — Citas verificables ✅
El LLM devuelve citas literales; el código calcula offsets exactos. Paráfrasis, invenciones y cifras alteradas se rechazan.
Acceptance: pruebas `test_rol3_citas.py`; compatible con `CitationRef.verify_against`.

### S3 — Motor de agentes y cliente agnóstico ✅
Razonar → actuar → observar; allowlist por agente; freno de repetidas; rechazo de entrega prematura; límite de pasos; traza. Proveedor configurable por `.env`.
Acceptance: pruebas `test_rol3_agente.py` con LLM falso.

### S4 — Agente analista ✅ (sin conectar al grafo)
Evidencia graduada, `frases_relacionadas` con equivalencias versionadas, citas obligatorias por esquema.
Acceptance: CV-007 (dataset previo) con LLM real: decisión, fallidos e inyección iguales al manifiesto; `experiencia_por_cargo` con R11 oficial 41/41 (`docs/rol-3-evaluacion.md`).

### S5 — Auditor determinista ✅
`auditor.py`: hallazgos con severidad y offset (inyección, citas no encontradas, obligatorio sin evidencia y cobertura < 0,70 (R4), idioma bajo el mínimo o sin acreditar (E5), idioma incoherente, cita con proxy, cita sin relación, evidencia solo de lista, calificadores débiles, estados incoherentes, proxies de R7). Bloquea, no aprueba.
Acceptance: `test_rol3_auditor.py` reproduce los errores reales medidos; sobre la ficha real de CV-007 (corrida 2) bloquea solo por inyección, sin falsos positivos.

### S6 — Auditor LLM ⏳ · S7 — Agendador ⏳

### S9 — Puntaje y cobertura para `armar_staging` ✅ (rúbrica provisional)
`rubrica.py` + `puntaje.py` → `[{cv_id, puntaje, cobertura, contradiccion_material}]` para el motor del Rol 2. Acceptance: Top solo aptos, R5 y R4 se activan, par contrafactual con el mismo puntaje, CV-040 = CV-008 (`tests/test_rol3_puntaje.py`, 19). Pendiente: aprobación de RR. HH. y del grupo (`docs/rol-3-puntaje.md`).

### S10 — Ejecución reproducible por el equipo ✅
`docs/rol-3-ejecucion.md` (personas, paso a paso con Docker y Ollama) y `cvagent/agentes/AGENTS.md` (asistentes de IA: lista de verificación y árbol de errores).

### S8 — Integración con el grafo ⏳
Bloqueado por la propuesta de contrato v1.1 (`docs/rol-3-propuesta-contratos.md`). Herramientas vía `OperationalControls.call_tool`.

## Reglas
- No modificar `cvagent/domain/contracts.py` ni módulos de otros roles; proponer cambios por documento.
- Datos sintéticos únicamente (`data/`). El manifiesto nunca se entrega a un agente.
- `.env` nunca se sube (contiene claves).
