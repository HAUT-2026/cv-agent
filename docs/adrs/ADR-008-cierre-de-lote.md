# ADR-008 — Cierre de lote y abstención ante incertidumbre

**Estado:** propuesta pendiente de aprobación operativa.  
**Referencia:** A6, B3/S15, B4.1 y B4.2.

## Contexto

El SDD impide publicar un Top 5 cuando falla una evaluación por timeout y el lote queda parcial. Otras excepciones tienen hasta 48 horas de resolución, mientras la propuesta se espera en cuatro horas. Sin una definición de «lote completo», el sistema puede omitir candidatos silenciosamente o quedar bloqueado sin diagnóstico.

## Decisión

Considerar un CV cerrado para el ranking solo si posee evaluación válida o resolución humana explícita, identificada y registrada. Un CV pendiente de inferencia, auditoría, consentimiento o revisión sin disposición mantiene el lote parcial. Staging se habilita únicamente con versión de vacante vigente y estado de cierre verificable de todos los casos incluidos en el corte. Mostrar al reclutador progreso, bloqueo y responsable.

## Consecuencias

- Una falla técnica no se convierte en exclusión de facto.
- La meta de cuatro horas puede incumplirse por excepciones legítimas. Separar métricas de procesamiento automático y de espera humana, y ajustar SLA o política de publicación con RR. HH. antes de producción.
- Se necesita una transición explícita y auditada para cada excepción; la mera expiración del plazo no cierra un CV.
