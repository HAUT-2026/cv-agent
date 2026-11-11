"""
Auditor del Rol 3 — capa DETERMINISTA (sin LLM).

Revisa la ficha del analista contra el CV y la vacante y produce un `Veredicto`
con hallazgos explicables, cada uno con severidad y, cuando aplica, el offset de la
evidencia. Reglas derivadas de lo medido con LLM real (docs/rol-3-evaluacion.md).

Principios:
- El auditor puede BLOQUEAR, no aprobar (AGENTS.md): el resultado es `bloquea` o
  `sin_objeciones`; la aprobación es siempre humana.
- No usa el razonamiento del analista: solo su ficha, el texto canónico, la vacante
  y los indicios de la sanitización (independencia, ADR-002).
- Todo hallazgo lo genera el código; el texto de `detalle` también.
- Lo semántico fino (SOAP ≠ REST; consumir ≠ diseñar) queda para la capa LLM.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .criterios import TipoRequisito, Vacante
from .herramientas import relacion_con_requisito
from .salida import (Cumplimiento, FichaCandidato, Hallazgo, ResultadoAuditoria, Severidad,
                     TipoHallazgo, Veredicto)

UMBRAL_COBERTURA = 0.70   # R4
CAPA = "determinista"

B, A = Severidad.BLOQUEANTE, Severidad.ADVERTENCIA

_CALIFICADORES = re.compile(
    r"\b(b[aá]sic[oa]s?|basic|en\s+curso|in\s+progress|nociones|principiante|beginner|introductori[oa]|"
    r"elemental|familiarizad[oa])\b", re.I)
_EN_CURSO = re.compile(r"\b(en\s+curso|in\s+progress|cursando|sin\s+terminar|incomplet[oa])\b", re.I)

_NIVELES = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6, "nativo": 7, "nativa": 7,
            "native": 7, "bilingue": 7, "bilingual": 7}
_RX_NIVEL = re.compile(r"\b(a1|a2|b1|b2|c1|c2|nativ[oa]|native|biling[uü]e|bilingual)\b", re.I)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _nivel(texto: str) -> Optional[int]:
    m = _RX_NIVEL.search(_norm(texto))
    return _NIVELES.get(m.group(1).lower().replace("ü", "u")) if m else None


def _h(tipo, sev, rid=None, inicio=None, fin=None, campo=None, detalle=None) -> Hallazgo:
    return Hallazgo(tipo=tipo, severidad=sev, id_requisito=rid, inicio=inicio, fin=fin,
                    campo=campo, detalle=(detalle[:240] if detalle else None))


def auditar(ficha: FichaCandidato, caso, vacante: Vacante,
            umbral_cobertura: float = UMBRAL_COBERTURA) -> Veredicto:
    """`caso` es un `cv_json.Caso` (texto canónico, indicios y proxies del mismo CV)."""
    if ficha.id_cv != caso.texto.id_cv:
        raise ValueError(f"la ficha es de {ficha.id_cv} pero el caso es de {caso.texto.id_cv}")
    reqs = {r.id: r for r in vacante.requisitos}
    hallazgos: list[Hallazgo] = []

    # 1) Inyección: un hallazgo por patrón y fuente (los offsets del primero)
    vistos = set()
    for i in caso.indicios:
        clave = (i.patron, i.fuente)
        if clave in vistos:
            continue
        vistos.add(clave)
        hallazgos.append(_h(TipoHallazgo.INDICIO_INYECCION, B, inicio=i.inicio, fin=i.fin,
                            campo="texto_oculto" if i.fuente == "texto_oculto" else None,
                            detalle=f"{i.patron}: «{i.texto[:120]}»"))

    # 2) Requisitos inventados u omitidos
    for rid in ficha.requisitos_desconocidos:
        hallazgos.append(_h(TipoHallazgo.REQUISITO_DESCONOCIDO, B, rid,
                            detalle=f"el analista evaluó {rid}, que no existe en {vacante.id_vacante} v{vacante.version}"))
    for rid in ficha.requisitos_omitidos:
        hallazgos.append(_h(TipoHallazgo.REQUISITO_OMITIDO, A, rid,
                            detalle="no evaluado por el analista; quedó como sin_evidencia"))

    # 3) Por requisito
    proxies = [(p.inicio, p.fin, p.patron) for p in caso.proxies]
    for ev in ficha.evaluaciones:
        r = reqs.get(ev.id_requisito)
        if r is None:
            continue
        afirma = ev.cumplimiento in (Cumplimiento.CUMPLE, Cumplimiento.PARCIAL, Cumplimiento.NO_CUMPLE)

        for cita in ev.citas_rechazadas:
            hallazgos.append(_h(TipoHallazgo.CITA_NO_ENCONTRADA, B, r.id,
                                detalle=f"«{cita[:150]}» no aparece en el CV"))
        if afirma and not ev.citas:
            hallazgos.append(_h(TipoHallazgo.AFIRMACION_SIN_CITA, B, r.id,
                                detalle=f"'{ev.cumplimiento.value}' sin ninguna cita verificada"))
            continue

        # 3a) Cita con proxy de R7: la evidencia usada expone un atributo protegido
        for c in ev.citas:
            for (pi, pf, patron) in proxies:
                if c.inicio < pf and pi < c.fin:
                    hallazgos.append(_h(TipoHallazgo.CITA_CON_PROXY, B, r.id, c.inicio, c.fin, c.campo,
                                        f"la evidencia contiene un proxy de R7 ({patron})"))
                    break

        # 3b) Relación: alguna cita debe compartir términos con el requisito o sus equivalencias.
        #     Los años de experiencia los decide el cálculo (R11), así que REQ de tipo experiencia
        #     se revisa igual, pero como advertencia.
        if afirma and ev.citas and not any(relacion_con_requisito(c.texto, r) for c in ev.citas):
            sev = B if (r.obligatorio and r.tipo != TipoRequisito.EXPERIENCIA) else A
            c = ev.citas[0]
            hallazgos.append(_h(TipoHallazgo.CITA_SIN_RELACION, sev, r.id, c.inicio, c.fin, c.campo,
                                f"«{c.texto[:120]}» no se relaciona con «{r.descripcion[:80]}»"))

        if ev.cumplimiento == Cumplimiento.CUMPLE:
            # 3c) Solo de la lista de habilidades: el prompt dice que eso es evidencia débil (parcial)
            if ev.citas and all((c.campo or "").startswith("habilidades[") for c in ev.citas):
                c = ev.citas[0]
                hallazgos.append(_h(TipoHallazgo.EVIDENCIA_SOLO_LISTA, A, r.id, c.inicio, c.fin, c.campo,
                                    "'cumple' respaldado solo por la lista de habilidades (evidencia débil → parcial)"))
            # 3d) Calificador débil
            for c in ev.citas:
                m = _CALIFICADORES.search(c.texto)
                if m:
                    hallazgos.append(_h(TipoHallazgo.CALIFICADOR_DEBIL, A, r.id, c.inicio, c.fin, c.campo,
                                        f"'cumple' con «{m.group(0)}» en la evidencia"))
                    break

        # 3e) Estudios en curso marcados no_cumple (debería ser parcial / revisión)
        if (ev.cumplimiento == Cumplimiento.NO_CUMPLE and r.tipo == TipoRequisito.EDUCACION
                and any(_EN_CURSO.search(c.texto) for c in ev.citas)):
            c = next(c for c in ev.citas if _EN_CURSO.search(c.texto))
            hallazgos.append(_h(TipoHallazgo.ESTADO_INCOHERENTE, A, r.id, c.inicio, c.fin, c.campo,
                                "estudios en curso marcados no_cumple (evidencia graduada: parcial)"))

        # 3f) Nivel de idioma: lo citado contra el mínimo de la vacante
        if r.tipo == TipoRequisito.IDIOMA and r.nivel_minimo and ev.citas:
            minimo = _nivel(r.nivel_minimo)
            niveles = [(n, c) for c in ev.citas if (n := _nivel(c.texto)) is not None]
            if minimo and niveles:
                mejor, c = max(niveles, key=lambda x: x[0])
                if ev.cumplimiento == Cumplimiento.CUMPLE and mejor < minimo:
                    hallazgos.append(_h(TipoHallazgo.NIVEL_IDIOMA_INCOHERENTE, B, r.id, c.inicio, c.fin, c.campo,
                                        f"'cumple' con «{c.texto}», por debajo del mínimo {r.nivel_minimo}"))
                elif ev.cumplimiento == Cumplimiento.NO_CUMPLE and mejor >= minimo:
                    hallazgos.append(_h(TipoHallazgo.NIVEL_IDIOMA_INCOHERENTE, A, r.id, c.inicio, c.fin, c.campo,
                                        f"'no_cumple' con «{c.texto}», que alcanza el mínimo {r.nivel_minimo}"))

    # 4) Cobertura (R4)
    if ficha.cobertura_evidencia < umbral_cobertura:
        hallazgos.append(_h(TipoHallazgo.COBERTURA_INSUFICIENTE, B,
                            detalle=f"cobertura {ficha.cobertura_evidencia:.2f} < {umbral_cobertura:.2f} (R4)"))

    # 5) Proxies de R7 que sobrevivieron a la minimización (señal para el humano)
    vistos = set()
    for (pi, pf, patron) in proxies:
        if patron in vistos:
            continue
        vistos.add(patron)
        hallazgos.append(_h(TipoHallazgo.SENAL_SESGO, A, inicio=pi, fin=pf,
                            detalle=f"proxy de R7 en el CV ({patron}): no debe influir en la evaluación"))

    bloquea = any(h.severidad == B for h in hallazgos)
    return Veredicto(id_cv=ficha.id_cv,
                     resultado=ResultadoAuditoria.BLOQUEA if bloquea else ResultadoAuditoria.SIN_OBJECIONES,
                     hallazgos=hallazgos, cobertura_evidencia=ficha.cobertura_evidencia,
                     capas_ejecutadas=[CAPA])
