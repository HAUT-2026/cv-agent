# ADR-006 — Criterios estructurados sin RAG ni base vectorial en v1

**Estado:** definida por el SDD.  
**Referencia:** B2, B4.4 y B7.

## Contexto

La vacante, política aplicable, rúbrica y equivalencias son fuentes estructuradas, acotadas y versionadas. El auditor puede recuperar la sección exacta del CV mediante `correlation_id` y offset. Una búsqueda semántica introduciría otra capa de selección de fuentes y de control de versiones sin necesidad demostrada.

## Decisión

Consultar los datos por API y entregar a cada turno solo los criterios y equivalencias pertinentes. Recuperar evidencia del CV por fragmento y offset. No incorporar RAG ni base vectorial en v1.

## Consecuencias

- Se simplifican despliegue, procedencia y auditoría de fuentes.
- No hay búsqueda semántica sobre manuales extensos. Si la política se convierte en un corpus grande, reevaluar RAG con fuentes aprobadas, vigencia y verificación de citas.
