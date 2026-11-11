# Rol 3 — Agentes del MVP de CVAgent
Paquete: `cvagent/agentes/` · Test runner: `uv run pytest tests/test_rol3_*.py`
Objetivo: agentes analista, auditor y agendador con salidas en esquemas estrictos, citas verificables por código y herramientas bajo allowlist, sin asumir lógica de negocio de otros roles.

## Specs

### S1 — Extracción y sanitización con offsets ✅
CV en JSON → texto canónico determinista; identidad y año de grado fuera (R7); `texto_oculto` bloqueado e indicio (E6); inyección y proxies con offsets.
Acceptance: 12/12 en detección contra el manifiesto; ningún valor de `persona` aparece en el texto.

### S2 — Citas verificables ✅
El LLM devuelve citas literales; el código calcula offsets exactos. Paráfrasis, invenciones y cifras alteradas se rechazan.
Acceptance: pruebas `test_rol3_citas.py`; compatible con `CitationRef.verify_against`.

### S3 — Motor de agentes y cliente agnóstico ✅
Razonar → actuar → observar; allowlist por agente; freno de repetidas; rechazo de entrega prematura; límite de pasos; traza. Proveedor configurable por `.env`.
Acceptance: pruebas `test_rol3_agente.py` con LLM falso.

### S4 — Agente analista ✅ (sin conectar al grafo)
Evidencia graduada, `frases_relacionadas` con equivalencias versionadas, citas obligatorias por esquema.
Acceptance: CV-007 con LLM real: decisión, fallidos e inyección iguales al manifiesto (`docs/rol-3-evaluacion.md`).

### S5 — Auditor determinista ✅
`auditor.py`: hallazgos con severidad y offset (inyección, citas no encontradas, cobertura < 0,70, idioma incoherente, cita con proxy, cita sin relación, evidencia solo de lista, calificadores débiles, estados incoherentes, proxies de R7). Bloquea, no aprueba.
Acceptance: `test_rol3_auditor.py` reproduce los errores reales medidos; sobre la ficha real de CV-007 (corrida 2) bloquea solo por inyección, sin falsos positivos.

### S6 — Auditor LLM ⏳ · S7 — Agendador ⏳

### S8 — Integración con el grafo ⏳
Bloqueado por la propuesta de contrato v1.1 (`docs/rol-3-propuesta-contratos.md`). Herramientas vía `OperationalControls.call_tool`.

## Reglas
- No modificar `cvagent/domain/contracts.py` ni módulos de otros roles; proponer cambios por documento.
- Datos sintéticos únicamente (`data/`). El manifiesto nunca se entrega a un agente.
- `.env` nunca se sube (contiene claves).
