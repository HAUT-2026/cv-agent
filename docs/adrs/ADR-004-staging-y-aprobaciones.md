# ADR-004 — Staging versionado y doble aprobación humana

**Estado:** definida por el SDD; política de recordatorios pendiente.  
**Referencia:** R10, B1, B4.1 y B4.4.

## Contexto

La lista corta y el mensaje pueden afectar a personas y comprometer a la organización. El agente no tiene autoridad para descartar definitivamente ni comunicarse con candidatos. El reclutador debe poder ajustar la propuesta sin borrar la evidencia de lo que el sistema presentó.

## Decisión

El motor deja una versión inmutable del ranking y sus razones en staging. El reclutador aprueba o crea una nueva versión con ajustes, autor, fecha y motivo. Después del agendamiento propuesto, aprueba el texto y destinatario exactos del mensaje. Solo entonces el workflow ejecuta correo, calendario y escritura en ATS. El silencio mantiene el caso pendiente y activa los plazos de escalamiento.

## Consecuencias

- Cada efecto externo puede vincularse con una autorización concreta.
- La aprobación humana puede convertirse en cuello de botella; medir tiempo de revisión y cambios reales frente a aprobaciones sin ajustes.
- Solicitudes de consentimiento y recordatorios son también comunicaciones: protección de datos y RR. HH. deben aprobar el tratamiento y el mecanismo de autorización previo a su envío.
