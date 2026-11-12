# Rol 3 · Puntaje y cobertura (rúbrica provisional)

> **Estado: PROVISIONAL.** Las decisiones de este documento se tomaron el 12-nov-2026 para que el MVP tenga un Top 5 de punta a punta. **Están pendientes de aprobación de RR. HH. y del grupo** (el SDD exige que RR. HH. apruebe pesos, criterio crítico y umbral antes de datos reales). Cambiarlas cuesta poco: están todas en un solo archivo (ver «Cómo cambiar algo»).

## Qué resuelve

El motor del Rol 2 arma el Top 5 con `reglas.motor.armar_staging`, que aplica R4, R5 y R6 pero **no calcula puntajes**: recibe `[{cv_id, puntaje, cobertura, contradiccion_material}]`. El SDD pide que puntaje y cobertura se calculen **por código, nunca por el LLM**. Este módulo los calcula a partir de:

- la **ficha del analista** (estado y citas verificadas de cada requisito),
- el **resultado del motor del Rol 2** (meses efectivos de R11 y si REQ-01 se acreditó por equivalencia),
- el **diccionario de equivalencias** (peso de cada término equivalente),
- el **veredicto del auditor** (contradicciones).

```
analista (LLM) → ficha ─┐
motor Rol 2 (R11, R3) ──┼→ puntaje.calcular_puntaje() → {puntaje, cobertura, contradicción} → armar_staging (R4, R5, R6) → Top 5
auditor → veredicto ────┘
```

Archivos: `cvagent/agentes/rubrica.py` (todas las decisiones, versionadas: `VERSION_RUBRICA`), `cvagent/agentes/puntaje.py` (el cálculo), `tests/test_rol3_puntaje.py` (19 pruebas).

## Lo que dice el SDD (punto de partida)

- Rúbrica: **40 %** competencias técnicas deseables, **30 %** profundidad de experiencia, **20 %** resultados, **10 %** competencias complementarias. Solo criterios definidos antes de la convocatoria; sin «fit cultural».
- Valoraciones **0,25 / 0,50 / 0,75 / 1,00** cuando hay evidencia; **`sin_evidencia` es un estado, no cero implícito**.
- R4: cobertura ponderada < **0,70**, criterio crítico sin evidencia o contradicción material → revisión humana, fuera del Top 5 automático.
- R5: si 5.º y 6.º difieren ≤ **0,02** → se presentan seis. R6: hasta cinco, sin rellenar.

## Las cuatro decisiones

### 1. «Resultados» (20 %) se reparte en proporción

La vacante VAC-001 no define ningún criterio de resultados, y el SDD prohíbe inventar criterios. Su 20 % se reparte en proporción entre las dimensiones que sí existen:

| Dimensión | SDD | Efectivo en VAC-001 | Qué la alimenta |
|---|---|---|---|
| Competencias técnicas | 40 % | **50 %** | DES-01 a DES-04 (deseables de categoría *habilidad*), 12,5 % cada uno |
| Profundidad de experiencia | 30 % | **37,5 %** | Meses efectivos de R11 (motor del Rol 2) |
| Complementarias | 10 % | **12,5 %** | DES-05, ONG o salud (deseable de categoría *experiencia*) |
| Resultados | 20 % | — | Ningún criterio en la vacante |

*Alternativa descartada:* dejar ese 20 % siempre vacío; nadie llegaría a cobertura 1,0 y R4 dependería de algo que la vacante no pide.
Los **obligatorios no puntúan**: son la puerta (R3); el puntaje ordena a quienes ya la pasaron.

### 2. El puntaje se calcula sobre el total

`puntaje = Σ (peso × valor) de los criterios con evidencia ÷ Σ peso de todos los criterios definidos`

Un deseable `sin_evidencia` no suma, pero **sigue en el denominador**. Medido con los datos del equipo:

| | Sobre lo evidenciado (descartada) | **Sobre el total (elegida)** |
|---|---|---|
| CV-002, el único con los 5 deseables | 3.º | **1.º** |
| CV-022 (0 deseables) frente a CV-016 (2) | 0,75 > 0,70: **gana el que tiene menos** | 0,28 < 0,44 ✓ |

Con la otra fórmula, el deseable que falta desaparece del cálculo y **no tener evidencia premia**. Cómo se respeta «no es cero implícito»: el estado `sin_evidencia` se conserva en la ficha, nunca se registra una valoración 0, y la **cobertura** lo hace visible (y activa R4).

### 3. Valoraciones

| Estado del analista | Valor | Quién lo decide |
|---|---|---|
| `cumple` | 1,00 | analista |
| `cumple` con citas **solo** de la lista de habilidades | **0,75** | **código** (la sección de cada cita); el auditor lo marca 🟡 `evidencia_solo_lista` |
| `parcial` | 0,50 | analista |
| `no_cumple` (con cita) | 0,25 | analista |
| `sin_evidencia` | — no suma, baja la cobertura | analista (y la baranda B2 verifica que haya buscado) |

### 4. Profundidad de experiencia por tramos

Meses efectivos de **R11** (del motor del Rol 2) frente al mínimo de la vacante (36 meses en VAC-001):

| Meses | Relación con el mínimo | Valor |
|---|---|---|
| 36–47 | < 4/3 del mínimo | 0,50 |
| 48–71 | < 2× | 0,75 |
| 72 o más | ≥ 2× | 1,00 |

Si REQ-01 se acreditó **por equivalencia**, se multiplica por el peso del término en el diccionario versionado del Rol 2 (CV-014, Kotlin: 0,75 × 0,9 = 0,675).

### Cobertura y contradicción

- `cobertura = Σ peso de los criterios con evidencia` (la experiencia de R11 siempre la tiene).
- `contradiccion_material = True` si el auditor dejó advertencias de **estado incoherente** o **nivel de idioma incoherente** (la ficha se contradice a sí misma). R4 la manda a revisión humana aunque la cobertura alcance.

## Resultado con el dataset del equipo

`python scripts/rol3/probar_banco.py --sin-llm` (analista **simulado** léxico, solo para medir):

| Pos. | CV | Puntaje | Cobertura | Grupo |
|---|---|---|---|---|
| 1 | CV-002 | 0,906 | 1,000 | apto |
| 2 | CV-001 | 0,875 | 0,875 | apto |
| 3 | CV-003 | 0,875 | 0,875 | apto |
| 4–6 | CV-005, CV-006, CV-007 | 0,781 | 0,875 | apto |

- **Ningún no apto ni parcial en el Top** (lo exige el SDD).
- **R5 se activa**: 5.º y 6.º empatan → se presentan seis.
- **Par contrafactual** CV-006 (mujer) / CV-007 (hombre): **mismo puntaje** (el cálculo no ve identidad).
- **Texto oculto**: CV-040 conserva el puntaje de su versión limpia CV-008 (el SDD lo exige), aunque igual va a bandeja por la inyección.
- **Los 13 parciales van a revisión humana por R4** (cobertura 0,375 a 0,625: tienen 0 a 2 deseables). No es un descarte: salen del Top automático y el reclutador los ve aparte. **Es un tema para el grupo**: son 13 revisiones humanas por vacante con esta rúbrica.

> El analista simulado marca `cumple` todo requisito con evidencia léxica (acierta 28/28 deseables del manifiesto) y no juzga matices; con el LLM real los puntajes cambian (un `parcial` vale 0,5). La métrica de verdad es correr `probar_banco.py todos` con el modelo elegido (ADR-007).

## Cómo cambiar algo

1. Editar `cvagent/agentes/rubrica.py` (pesos en `PESOS_SDD`, mapeo en `DIMENSION_DE_DESEABLE`, valores en `VALOR`, tramos en `TRAMOS_EXPERIENCIA`, umbral en `UMBRAL_COBERTURA`).
2. Subir `VERSION_RUBRICA` (va al decision_log con vacante, prompt y modelo: una evaluación se reconstruye con esas versiones).
3. `python -m pytest tests/test_rol3_puntaje.py` y `python scripts/rol3/probar_banco.py --sin-llm` para ver el nuevo Top.
4. Actualizar este documento.

## Preguntas abiertas para RR. HH. y el grupo

1. ¿Se aprueban los pesos efectivos 50 / 37,5 / 12,5, o la vacante debe definir un criterio de «resultados»?
2. ¿13 parciales a revisión humana por vacante es aceptable, o se ajusta el umbral de cobertura / el reparto?
3. ¿Los tramos de experiencia (4/3 y 2× el mínimo) reflejan lo que valora el hiring manager?
4. ¿Pesos distintos por deseable (hoy los cuatro técnicos pesan igual)?
5. Conciliar con el Rol 1: `FichaCandidato` del contrato v1.0.0 no tiene evaluaciones por requisito (ver `rol-3-propuesta-contratos.md`).
