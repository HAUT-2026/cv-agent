# Rol 2 · Reglas y datos del caso

Contiene el motor de reglas R1 a R13 (funciones puras con pruebas), el dataset de 40 CV ficticios para la
vacante **Backend Java**, el repositorio de vacantes versionadas, el diccionario de equivalencias y el staging
determinista del Top 5. Todo se corre sin API ni red.

## Estructura

```
data/
  vacantes/            vacante_v1.json (vigente) · vacante_v2.json (borrador, E11) · indice.json
  diccionario_equivalencias.json
  cvs_pdf/             CV-001 ... CV-040   ← lo que leen los agentes
  cvs_json/            los mismos 40, estructurados (la «ficha de ejemplo»)
  extras_inyeccion/    INJ-01 ... INJ-04   ← 4 CV con prompt injection de estilos distintos (no cuentan en los 40)
  manifiesto.json      respuestas correctas ← SOLO para evaluar
  generar_dataset.py   fabrica todo lo anterior (determinista)
reglas/                reglas.py (R1–R13) · motor.py · diccionario.py · vacantes.py · comun.py
tests/                 test_reglas.py (unitarias) · test_dataset.py (40 CV contra el manifiesto)
```

## Cómo se usa

```
pip install -r requirements.txt
python -m pytest tests -q            # 132 pruebas
python data/generar_dataset.py       # solo si cambias algo; sale idéntico byte a byte en cada corrida
```

`generar_dataset.py` necesita `pdftoppm` (poppler) únicamente para fabricar el PDF escaneado del caso E1.
Si no lo tienes, no lo regeneres: los archivos ya están en el repo.

```python
from reglas import cargar_vacante, cargar_diccionario, procesar_lote, armar_staging
vacante = cargar_vacante("data", "VAC-001")                  # sin versión = la vigente (R8)
dic = cargar_diccionario("data/diccionario_equivalencias.json")
resultados = procesar_lote(fichas, vacante, dic)             # R12 → R1 → R2 → R11/R3 → R7
staging = armar_staging(evaluaciones, "VAC-001", 1)          # R4 → R5 → R6, orden determinista
```

## Mapa regla → código → qué prueba

| Regla | Función | Casos del dataset |
|---|---|---|
| R1 consentimiento | `r1_consentimiento` | CV-035 (E9) |
| R2 formato | `r2_formato` | CV-036, PDF escaneado con 0 caracteres (E1) |
| R3 requisitos excluyentes | `r3_requisitos_excluyentes` | CV-026 a 033 (incumplen), CV-039 (no acreditado, E5), CV-023/024 (por confirmar, S4) |
| R4 cobertura < 0,70 | `r4_cobertura` | prueba unitaria + staging (la cobertura la calcula el analista) |
| R5 empate en el corte | `r5_empate` | prueba unitaria con 0,781 vs 0,779 (E8) |
| R6 tamaño de lista | `r6_tamano_lista` | unitaria |
| R7 anonimización y proxies | `r7_anonimizar` | CV-005 y CV-017 (edad, estado civil, barrio, foto, colegio, sexo); par CV-006/CV-007 |
| R8 vigencia | `r8_vigencia`, `cargar_vacante` | v1 vigente, v2 borrador |
| R9 retención | `r9_retencion` | unitaria (plazo de 365 días es supuesto) |
| R10 doble aprobación | `r10_doble_aprobacion` | unitaria (la llama el workflow del Rol 1) |
| R11 experiencia efectiva | `r11_experiencia_efectiva` | CV-038 (E3), CV-037 (E2), CV-011 (justo 36 meses) |
| R12 deduplicación | `r12_deduplicar` | CV-034 es la versión anterior de CV-013 (E10) |
| R13 cambio de vacante | `r13_cambio_vacante` | vacante v2 (3 → 5 años) reevaluada sobre los 40 (E11) |

## Composición de los 40 (Hito 2, 7.5)

10 aptos · 15 parciales · 10 no aptos · 5 trampa. Los cinco trampa son **E1** (CV-036 escaneado), **E2** (CV-037
fechas contradictorias), **E3** (CV-038 empleos solapados), **E5** (CV-039 «inglés avanzado» sin certificado) y
**E6** (CV-040 texto oculto). Sus gemelos y pares: CV-008 es el **gemelo limpio** de CV-040; CV-006 y CV-007 son el
**par contrafactual** (cambian nombre y sexo; tras R7 quedan idénticos). E9 (CV-035) y E10 (CV-034) viven en el grupo
de no aptos porque no entran al ranking.

## Dos rutas por CV en el manifiesto

- `ruta_motor_reglas`: lo que debe devolver el motor del Rol 2.
- `ruta_final`: lo que debe verse de punta a punta. Difiere en los CV con inyección: las reglas los dejan pasar
  (`evaluable`) pero sanitización y auditor (Rol 3) deben mandarlos a `bandeja`.

Rutas posibles: `evaluable` (→ `ranking`), `bandeja`, `no_apto_declarado` (visible, **no se descarta**),
`duplicado`, `en_espera_consentimiento`, `carga_manual`. No existe la ruta «descartado».

## Qué le entrego a cada rol

| Rol | Recibe | No debe recibir |
|---|---|---|
| Rol 3 (agentes) | `data/cvs_pdf/`, `vacantes/`, `diccionario_equivalencias.json` | `manifiesto.json`: ajustar prompts mirando las respuestas es estudiar con el examen en la mano |
| Rol 4 (bandeja y pruebas) | todo, incluido `manifiesto.json` | |
| Rol 1 (grafo) | `reglas/` (importable como librería) y `data/cvs_json/` como ficha de ejemplo | |

Los `cvs_json` conservan el campo `texto_oculto` del CV-040 porque son los datos con los que se armó el PDF: son para
comparar la extracción, no para dárselos al modelo.

## Supuestos que hay que confirmar con el grupo

1. **Formato de la ficha.** La ficha es la de `data/cvs_json`. Cuando el Rol 3 publique su esquema real, solo hay que
   escribir una función que convierta una a otra; las reglas no cambian.
2. **R11:** cuentan empleo y freelance; **pasantías y voluntariado no**. Es lo más discutible del diseño.
3. **E3:** el Hito dice «siete años en cuatro»; aquí son 84 meses nominales en 48 reales, con declarado = 7 años.
   Una diferencia declarado − calculado ≥ 12 meses se trata como contradicción (S6) y va a la bandeja.
4. **R9:** el plazo de retención (365 días) es un supuesto; la política real no está definida.
5. **Pesos del diccionario:** Kotlin sobre JVM = 0,9 y acredita Java (umbral 0,8). Scala no tiene entrada → «por confirmar».
6. **REQ-04:** un título de otra área, o ninguno con ≥ 60 meses de experiencia relevante, va a revisión humana y no se descarta.
7. **R4 y R5** necesitan el puntaje y la cobertura del analista: aquí solo se aplican; no se calculan.

## Agregar candidatos

En `generar_dataset.py`, agrega un `S("CV-041", "parcial", meses=44, des=["spring"], ...)` a `SPECS` y vuelve a correr.
Para un caso de inyección nuevo, agrégalo a `EXTRAS`. El manifiesto se recalcula solo.
