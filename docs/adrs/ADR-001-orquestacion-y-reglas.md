# ADR-001 — Orquestación y reglas fuera del modelo

**Estado:** definida por el SDD; pendiente aprobar las transiciones exactas de los estados de requisito.  
**Referencia:** A4, B1, B4.1 y B4.4.

## Contexto

Consentimiento, requisitos excluyentes, cobertura, plazos y corte del ranking son políticas definidas por personas con autoridad. Deben aplicarse de forma repetible a todos los CV de una misma versión de vacante. Interpretar texto libre y producir una ficha requiere inferencia, pero esa inferencia no debe convertirse en autoridad sobre reglas o estados.

## Decisión

El workflow conserva estados y temporizadores. El motor de reglas versionado ejecuta R1–R13, calcula experiencia efectiva, cobertura, ponderaciones y orden. Los agentes producen únicamente artefactos estructurados A1 que el workflow valida y acepta o bloquea. Cada resultado de regla registra versión, entrada pertinente, estado y motivo. El lote usa una instantánea de criterios hasta que R13 autorice reevaluación.

## Consecuencias

- Las decisiones deterministas se pueden reproducir y auditar sin depender de una nueva respuesta del modelo.
- Se requiere gobernar versiones, pruebas de regresión y excepciones del motor.
- RR. HH. debe definir la transición de `no_acreditado` y `por_confirmar`, hoy ambigua entre R3 y E5/S5.
