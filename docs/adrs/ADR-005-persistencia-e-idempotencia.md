# ADR-005 — Persistencia transaccional y efectos externos idempotentes

**Estado:** propuesta técnica.  
**Referencia:** B3, B4.2, B5 y B7.

## Contexto

Los lotes de hasta 200 CV requieren ejecución duradera. Una API puede completar el envío o la escritura y agotar el tiempo de respuesta antes de devolver un acuse. Un reintento ciego podría duplicar invitaciones o eventos. También debe conservarse una traza de decisiones con integridad verificable y política de supresión.

## Decisión

Persistir casos, lotes, temporizadores y aprobaciones en almacenamiento transaccional. Custodiar originales en almacenamiento de objetos protegido. Registrar eventos de decisión como anexos con hash encadenado y minimizar sus datos identificables. Usar cola o patrón *outbox* para efectos externos, claves de idempotencia por operación y reconciliación del estado remoto antes de repetir una llamada incierta.

## Consecuencias

- El workflow puede recuperarse tras reinicios sin depender del contexto de un modelo.
- Correo, ATS y calendario pueden reintentarse sin duplicar efectos cuando sus adaptadores cumplen el contrato.
- Se añade complejidad de consistencia, reconciliación y retención. La tecnología concreta de base de datos queda pendiente de infraestructura, volumen y objetivos de disponibilidad.
