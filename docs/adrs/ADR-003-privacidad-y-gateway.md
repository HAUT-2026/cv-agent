# ADR-003 — Aislamiento de identidad y gateway de herramientas

**Estado:** definida en principio por el SDD; diseño físico y contratos de tratamiento pendientes.  
**Referencia:** R7–R9, B2, B5 y B6.

## Contexto

El sistema debe volver a contactar a un candidato, pero el cálculo del puntaje no puede recibir atributos personales protegidos ni datos sensibles no pertinentes. Tres agentes usan herramientas distintas, y las APIs tienen dueños diferentes. La identidad y el texto del CV permanecen vinculables durante el proceso, por lo que la minimización es seudonimización operativa.

## Decisión

Separar el almacén de identidad y originales del texto de evaluación. Entregar a inferencia solo el texto sanitizado y minimizado, criterios pertinentes y un identificador de caso. El gateway autoriza cada llamada según agente, `correlation_id`, vacante, herramienta y permiso, con token breve y registro central. Los secretos permanecen en un gestor de secretos, fuera de prompts y salidas.

## Consecuencias

- Disminuye la exposición de datos y se puede demostrar qué herramienta vio cada agente.
- La reidentificación, los respaldos y la supresión requieren procedimientos explícitos; ocultar campos en la interfaz no basta.
- Un servidor MCP no aporta valor necesario en v1: cada agente utiliza pocas herramientas de solo lectura y contrato estable. Reevaluar si aparecen herramientas dinámicas o nuevos sistemas.
