# ADR-007 — Selección y cambios controlados del modelo

**Estado:** proceso propuesto; modelo y proveedor pendientes.  
**Referencia:** B5–B7.

## Contexto

El documento fija temperatura, límites de tokens y timeout, pero no identifica un modelo o proveedor. La hipótesis de variación de puntaje ≤ 0,02 con temperatura 0 debe probarse. El proveedor debe satisfacer condiciones de tratamiento de datos antes de usar CV reales.

## Decisión

Evaluar candidatos de modelo con el mismo corpus y rúbrica: exactitud de ficha, soporte de citas, consistencia, señales de sesgo, latencia p50/p95, costo y condiciones de privacidad. Fijar modelo, versión, prompt, esquema y parámetros por lote. Cualquier cambio exige regresión con los 40 CV ficticios, pruebas contrafactuales y validación en varias vacantes con revisión humana independiente.

## Consecuencias

- La elección se sustenta en evidencia comparable y no en preferencia de proveedor.
- El corpus inicial comprueba funcionalidad, pero no generalización ni ausencia de sesgo; hay que ampliar evaluación antes de producción.
- Una actualización del proveedor puede alterar resultados aunque la temperatura sea cero; detectar deriva y conservar versiones.
