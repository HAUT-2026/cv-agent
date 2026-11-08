# ADR-002 — Separación de agentes y verificación de citas

**Estado:** definida por el SDD.  
**Referencia:** B1, B4.4, B6 y B7.

## Contexto

El CV es contenido externo no confiable. El analista puede producir una cita inexistente o seguir una instrucción incrustada. La redacción de invitaciones no requiere conocer el CV. Un único agente con todos los permisos concentraría datos, errores y capacidad de acción.

## Decisión

Usar un agente analista para ficha y valoración, un agente auditor con función de bloqueo y un agente agendador sin acceso al CV. Un verificador determinista comprueba la existencia literal de citas y offsets antes del auditor. Cada agente opera con esquema, contexto y allowlist propios; ninguno llama directamente a correo, ATS o calendario.

## Consecuencias

- Se reduce la concentración de permisos y se hacen visibles los desacuerdos entre propuesta y auditoría.
- Aumentan latencia, costo y complejidad de correlación; se deben medir en las metas de A6.
- La separación funcional no garantiza independencia estadística si analista y auditor comparten modelo o proveedor. El verificador por código y la revisión humana siguen siendo necesarios.
