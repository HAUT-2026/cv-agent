"""Rúbrica de puntaje del Rol 3 · PROVISIONAL, pendiente de aprobación de RR. HH.

Todas las decisiones del puntaje viven aquí, en un solo lugar y versionadas. Si el grupo o
RR. HH. cambian un peso o un umbral: se edita este archivo, se sube VERSION_RUBRICA y se
corren las pruebas (tests/test_rol3_puntaje.py). El motivo de cada decisión está en
docs/rol-3-puntaje.md (decisiones acordadas por Arley el 12-nov-2026 «por ahora»).

Base del SDD (docs/cvagent-arquitectura.md): 40 % competencias técnicas deseables, 30 %
profundidad de experiencia, 20 % resultados, 10 % competencias complementarias; valoraciones
0,25/0,50/0,75/1,00 con evidencia; «sin_evidencia es un estado, no cero implícito»; puntaje y
cobertura calculados por código, nunca por el LLM; cobertura < 0,70 → revisión humana (R4).
"""
from __future__ import annotations

VERSION_RUBRICA = "rubrica-provisional-v1"   # va al decision_log junto con vacante, prompt y modelo

# --------------------------------------------------------------------------- decisión 1
# Pesos del SDD. «resultados» no tiene ningún criterio en VAC-001 (el SDD dice: solo criterios
# definidos antes de la convocatoria), así que su 20 % se reparte en proporción entre las
# dimensiones que sí existen: 40/30/10 → 50 % / 37,5 % / 12,5 %.
PESOS_SDD = {"tecnicas": 0.40, "experiencia": 0.30, "resultados": 0.20, "complementarias": 0.10}

# Qué requisito de la vacante alimenta cada dimensión (los obligatorios NO puntúan: son la
# puerta de R3; el puntaje ordena a quienes ya la pasaron).
#   tecnicas        → deseables de categoría «habilidad»   (VAC-001: DES-01 a DES-04)
#   complementarias → deseables de categoría «experiencia» (VAC-001: DES-05, ONG o salud)
#   experiencia     → meses efectivos de R11 del motor del Rol 2 (requisito obligatorio de experiencia)
#   resultados      → ningún requisito en VAC-001
DIMENSION_DE_DESEABLE = {"habilidad": "tecnicas", "experiencia": "complementarias"}

# --------------------------------------------------------------------------- decisión 2
# Agregación: puntaje = Σ peso·valor de lo que tiene evidencia / Σ peso de TODO lo definido.
# Un deseable sin evidencia no suma, pero tampoco desaparece del denominador: si desapareciera,
# no tener evidencia subiría el puntaje (simulado: CV-022 con 0 deseables le ganaba a CV-016
# con 2). «sin_evidencia» se conserva como estado en la ficha y se ve en la cobertura.
AGREGACION = "sobre_total"

# --------------------------------------------------------------------------- decisión 3
# Valoración de cada estado del analista (escala del SDD). El 0,75 lo decide el CÓDIGO:
# un «cumple» cuyas citas salen todas de la lista de habilidades es evidencia débil.
VALOR = {"cumple": 1.00, "cumple_solo_lista": 0.75, "parcial": 0.50, "no_cumple": 0.25}
# «sin_evidencia» no tiene valor: no suma y baja la cobertura.

# --------------------------------------------------------------------------- decisión 4
# Profundidad de experiencia: meses de R11 frente al mínimo de la vacante (36 en VAC-001).
#   < 4/3 del mínimo (36–47 m) → 0,50 · < 2× (48–71 m) → 0,75 · ≥ 2× (72 m o más) → 1,00
TRAMOS_EXPERIENCIA = [(4 / 3, 0.50), (2.0, 0.75), (float("inf"), 1.00)]
# Si REQ-01 se acreditó por equivalencia (Kotlin por Java), se multiplica por el peso que el
# diccionario versionado del Rol 2 da a ese término (Kotlin: 0,9).

# --------------------------------------------------------------------------- R4
UMBRAL_COBERTURA = 0.70


def pesos_efectivos(dimensiones_presentes: set[str]) -> dict[str, float]:
    """Reparte proporcionalmente el peso de las dimensiones sin criterios (decisión 1)."""
    total = sum(PESOS_SDD[d] for d in dimensiones_presentes)
    return {d: PESOS_SDD[d] / total for d in dimensiones_presentes}


def valor_experiencia(meses: int, minimo_meses: int, factor_equivalencia: float = 1.0) -> float:
    for limite, valor in TRAMOS_EXPERIENCIA:
        if meses < limite * minimo_meses:
            return round(valor * factor_equivalencia, 4)
    return round(TRAMOS_EXPERIENCIA[-1][1] * factor_equivalencia, 4)
