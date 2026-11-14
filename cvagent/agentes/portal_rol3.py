"""Rol 3 · Los agentes reales del Rol 3 dentro del portal del Rol 4, sin modificar `portal/`.

El portal arma el grafo del Rol 1 con `RoleAdapters`. Este módulo entrega los cuatro puertos con las
piezas del Rol 3 (el motor de reglas sigue siendo el del portal, que ya es real):

    AnalistaPort   AnalistaRol3   sanitización + ficha del Rol 3 + auditor + puntaje (rúbrica del Rol 3)
    AuditorPort    AuditorRol3    traduce el veredicto del auditor del Rol 3 al `Veredicto` del Rol 1
    AgendadorPort  AgendadorPortalRol3  plantillas y calendario del Rol 3, sin cruces de franja en el lote

Decisiones (13-nov, ver docs/rol-3-integracion-portal.md):
  * El LLM NUNCA lee el texto del portal: ese texto sale del PDF y trae nombre, correo, cédula,
    dirección y sexo. El analista trabaja sobre el texto canónico del Rol 3 (JSON + R7 oficial) y
    solo las CITAS se re-anclan sobre el texto del portal, que es donde la bandeja las resalta.
  * De dónde sale la ficha de cada CV, en orden: ficha del LLM real guardada en `resultados/rol3/`
    (si sigue siendo válida para el texto actual) → analista SIMULADO (`ficha_lexica`). El origen
    viaja en la razón del veredicto, así que la bandeja siempre dice cuál fue.
  * El puntaje lo calcula el código con la rúbrica PROVISIONAL del Rol 3 (H-3 sigue abierto).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..domain.contracts import (AuditMetadata, CitationRef, FichaCandidato as FichaContrato,
                                Veredicto as VeredictoContrato, VeredictoEstado)
from .auditor import auditar
from .criterios import Vacante, cargar_vacante
from .cv_json import Caso, preparar_caso
from .evaluacion import ficha_lexica
from .puntaje import calcular_puntaje
from .rubrica import VERSION_RUBRICA
from .salida import FichaCandidato as FichaRol3, ResultadoAuditoria, Severidad, Veredicto as VeredictoRol3

VERSION_INTEGRACION = "rol3-portal-1.0.0"
RAIZ = Path(__file__).resolve().parents[2]


# ============================================================ re-anclaje de citas
_SEPARADORES = re.compile(r"\s*(?:,|·|\(|\)|:|;|\n|\s-\s)\s*")


def _unica(texto: str, s: str) -> Optional[tuple[int, int]]:
    i = texto.find(s)
    return (i, i + len(s)) if s and i >= 0 and texto.find(s, i + 1) < 0 else None


def _linea_unica(texto: str, s: str) -> Optional[tuple[int, int]]:
    """Primera aparición de `s` cuya línea completa sea única en el texto."""
    i = texto.find(s) if s else -1
    while i >= 0:
        a = texto.rfind("\n", 0, i) + 1
        b = texto.find("\n", i)
        b = len(texto) if b < 0 else b
        linea = texto[a:b].strip()
        if len(linea) >= 3:
            r = _unica(texto, linea)
            if r:
                return r
        i = texto.find(s, i + 1)
    return None


def _ocurrencias(texto: str, s: str) -> list[int]:
    salida, i = [], texto.find(s)
    while i >= 0:
        salida.append(i)
        i = texto.find(s, i + 1)
    return salida


def reanclar(texto_portal: str, cita: str, terminos: list[str] = (), texto_rol3: str = "",
             inicio_rol3: Optional[int] = None) -> tuple[Optional[tuple[int, int]], str]:
    """Ubica en el texto del portal una cita que el Rol 3 verificó en SU texto. Devuelve
    ((inicio, fin), método) o (None, "falla"). Las posiciones las calcula el código, nunca el LLM.

    Métodos, en orden (medidos el 13-nov sobre los 28 evaluables: 199/200 citas):
      ocurrencia  la frase se repite igual en ambos textos: se toma la misma ocurrencia que citó el Rol 3
      exacta      la frase aparece una sola vez en el texto del portal
      linea       la línea que la contiene es única
      fragmento   el texto del Rol 3 y el PDF formatean distinto (listas, idiomas): se ancla el
                  fragmento de la cita que nombra el requisito (concepto o equivalencia)
    """
    if texto_rol3 and inicio_rol3 is not None:
        a, b = _ocurrencias(texto_rol3, cita), _ocurrencias(texto_portal, cita)
        if len(a) > 1 and len(a) == len(b) and inicio_rol3 in a:
            k = b[a.index(inicio_rol3)]
            return (k, k + len(cita)), "ocurrencia"
    for buscar, metodo in ((_unica, "exacta"), (_linea_unica, "linea")):
        r = buscar(texto_portal, cita)
        if r:
            return r, metodo
    terms = [t.lower() for t in terminos if t]
    fragmentos = {f.strip(" .") for f in _SEPARADORES.split(cita) if len(f.strip(" .")) >= 3}
    for f in sorted(fragmentos, key=lambda f: (not any(t in f.lower() for t in terms), -len(f))):
        r = _unica(texto_portal, f) or _linea_unica(texto_portal, f)
        if r:
            return r, "fragmento"
    return None, "falla"


def terminos_de(req) -> list[str]:
    return [t for t in [req.concepto, *req.equivalencias, *req.titulos_aceptados, *req.palabras_afines] if t]


# ============================================================ origen de la ficha
def ruta_cv_json(cv_id: str, data_dir: Path) -> Path:
    for carpeta in (data_dir / "cvs_json", data_dir / "extras_inyeccion" / "cvs_json"):
        if (carpeta / f"{cv_id}.json").exists():
            return carpeta / f"{cv_id}.json"
    raise FileNotFoundError(f"{cv_id}: no está en data/cvs_json ni en data/extras_inyeccion/cvs_json")


def ficha_en_cache(cv_id: str, caso: Caso, vacante: Vacante, cache_dir: Path) -> Optional[FichaRol3]:
    """Ficha del LLM real guardada por `probar_banco.py`, solo si sigue valiendo para el texto actual:
    misma vacante y versión, y cada cita igual al texto canónico en sus offsets. Si el dataset
    cambió después de generarla, se descarta (no se «adivina»)."""
    ruta = cache_dir / f"{cv_id}.json"
    if not ruta.exists():
        return None
    try:
        ficha = FichaRol3.model_validate(json.loads(ruta.read_text("utf-8"))["ficha"])
    except Exception:  # noqa: BLE001  archivo viejo o roto: no se usa
        return None
    if ficha.id_cv != cv_id or ficha.id_vacante != vacante.id_vacante or ficha.version_vacante != vacante.version:
        return None
    t = caso.texto.texto
    if any(t[c.inicio:c.fin] != c.texto for e in ficha.evaluaciones for c in e.citas):
        return None
    return ficha


@dataclass
class AnalisisRol3:
    """Todo lo que el Rol 3 produjo para un caso; queda en `ContextoCaso.rol3` para el auditor y la UI."""
    origen: str                       # "llm" | "simulado"
    etiqueta: str                     # lo que lee una persona en la bandeja
    ficha: FichaRol3
    veredicto: VeredictoRol3
    puntaje: dict
    citas_portal: list[dict] = field(default_factory=list)   # {id_requisito, cita_rol3, cita_portal, metodo}
    citas_no_ancladas: list[dict] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {"origen": self.origen, "etiqueta": self.etiqueta,
                "ficha": self.ficha.model_dump(mode="json"), "veredicto": self.veredicto.model_dump(mode="json"),
                "puntaje": self.puntaje, "citas_portal": self.citas_portal,
                "citas_no_ancladas": self.citas_no_ancladas}


def _auditoria(componente: str, caso, vacante: dict, now: datetime, **extra) -> AuditMetadata:
    return AuditMetadata(componente=componente, fuente=[f"{caso.cv_id}:{caso.procedencia}", f"{caso.cv_id}.json:r7"],
                         versiones={"vacante": str(vacante["version"]), "integracion": VERSION_INTEGRACION,
                                    "rubrica": VERSION_RUBRICA},
                         timestamp=now, **extra)


# ============================================================ AnalistaPort
class AnalistaRol3:
    def __init__(self, contexto, *, data_dir: Path = RAIZ / "data", cache_dir: Path = RAIZ / "resultados" / "rol3"):
        self.contexto = contexto
        self.data_dir = Path(data_dir)
        self.cache_dir = Path(cache_dir)
        self._vacante: Optional[Vacante] = None

    @property
    def vacante(self) -> Vacante:
        if self._vacante is None:
            v = self.contexto.vacante
            self._vacante = cargar_vacante(self.data_dir, v["vacante_id"], v["version"])
        return self._vacante

    def analizar(self, caso_portal) -> AnalisisRol3:
        cv_id = caso_portal.cv_id
        caso = preparar_caso(ruta_cv_json(cv_id, self.data_dir))
        vac = self.vacante
        ficha = ficha_en_cache(cv_id, caso, vac, self.cache_dir)
        if ficha is not None:
            origen, etiqueta = "llm", f"Analista LLM ({ficha.modelo.split('@')[0]})"
        else:
            evs, construir = ficha_lexica(caso, vac)
            ficha = construir(evs)
            origen, etiqueta = "simulado", "Analista léxico (sin LLM)"
        veredicto = auditar(ficha, caso, vac)
        pje = calcular_puntaje(ficha, caso_portal.resultado_reglas, vac, self.contexto.diccionario,
                               veredicto, caso.texto.texto)

        reqs = {r.id: r for r in vac.requisitos}
        ancladas, fallidas = [], []
        for ev in ficha.evaluaciones:
            for c in ev.citas:
                pos, metodo = reanclar(caso_portal.texto, c.texto, terminos_de(reqs[ev.id_requisito]),
                                       caso.texto.texto, c.inicio)
                fila = {"id_requisito": ev.id_requisito, "cumplimiento": ev.cumplimiento.value,
                        "cita_rol3": c.texto, "metodo": metodo}
                if pos is None:
                    fallidas.append(fila)
                else:
                    fila.update(inicio=pos[0], fin=pos[1], cita_portal=caso_portal.texto[pos[0]:pos[1]])
                    ancladas.append(fila)
        return AnalisisRol3(origen, etiqueta, ficha, veredicto, pje.a_dict(), ancladas, fallidas)

    def crear_ficha(self, state, *, now: datetime) -> FichaContrato:
        caso = self.contexto.caso(state.correlation_id)
        a = self.analizar(caso)
        caso.rol3 = a
        fuente = f"{caso.cv_id}.{'pdf' if caso.procedencia == 'pdf' else 'json'}"
        citas, vistas = [], set()
        for f in a.citas_portal:
            if (f["inicio"], f["fin"]) in vistas:      # varias evaluaciones pueden citar la misma línea
                continue
            vistas.add((f["inicio"], f["fin"]))
            citas.append(CitationRef(correlation_id=state.correlation_id, fuente=fuente, cita=f["cita_portal"],
                                     offset_inicio=f["inicio"], offset_fin=f["fin"]).verify_against(caso.texto))
        caso.citas = citas
        caso.puntaje = float(a.puntaje["puntaje"])
        caso.cobertura = float(a.puntaje["cobertura"])
        caso.hallazgos = [_texto_hallazgo(h) for h in a.veredicto.hallazgos]
        if not citas:
            # El contrato exige ≥ 1 cita. Medido el 13-nov: no ocurre con el dataset; si ocurre, el portal
            # registra el caso como error visible (no lo descarta en silencio).
            raise ValueError(f"{caso.cv_id}: ninguna cita del Rol 3 se pudo ubicar en el texto del portal")

        ob = [e for e in a.ficha.evaluaciones if e.obligatorio]
        cumplen = sum(e.cumplimiento.value == "cumple" for e in ob)
        resumen = (f"{a.etiqueta}. {cumplen}/{len(ob)} obligatorios cumplen; puntaje {caso.puntaje:.3f} "
                   f"({a.puntaje.get('version_rubrica', VERSION_RUBRICA)}, provisional); citas ubicadas en el "
                   f"texto del portal: {len(a.citas_portal)}/{len(a.citas_portal) + len(a.citas_no_ancladas)}.")
        return FichaContrato(
            correlation_id=state.correlation_id, candidato_ref=caso.candidato_ref, vacante_id=state.vacante_id,
            vacante_version=state.vacante_version, resumen=resumen, citas=citas, creado_en=now, actualizado_en=now,
            auditoria=_auditoria("rol-3-analista", caso, self.contexto.vacante, now,
                                 modelo_version=a.ficha.modelo, prompt_version=a.ficha.version_prompt,
                                 esquema_version="1.0.0"))


# Cómo se lee cada hallazgo en la bandeja (el tipo técnico sigue en el detalle del Rol 3)
LEGIBLE = {
    "indicio_inyeccion": "posible inyección de instrucciones",
    "cita_no_encontrada": "cita que no aparece en el CV",
    "cita_cruza_campos": "cita que mezcla dos campos del CV",
    "afirmacion_sin_cita": "afirmación sin cita",
    "requisito_omitido": "requisito sin evaluar",
    "requisito_desconocido": "requisito que no existe en la vacante",
    "cobertura_insuficiente": "cobertura de evidencia insuficiente",
    "obligatorio_sin_evidencia": "obligatorio sin evidencia",
    "evidencia_ignorada": "evidencia del CV no considerada",
    "cita_sin_relacion": "cita sin relación con el requisito",
    "evidencia_solo_lista": "evidencia solo en la lista de habilidades",
    "calificador_debil": "nivel declarado como básico o en curso",
    "estado_incoherente": "estado incoherente con la cita",
    "nivel_idioma_incoherente": "nivel de idioma incoherente con la cita",
    "cita_con_proxy": "cita con un dato sensible (R7)",
}


def _texto_hallazgo(h) -> str:
    """'bloqueo|advertencia: <qué> [en REQ-xx] [(«cita»)]'. La cita solo para inyección: es la prueba."""
    nivel = "bloqueo" if h.severidad == Severidad.BLOQUEANTE else "advertencia"
    texto = LEGIBLE.get(h.tipo.value, h.tipo.value.replace("_", " "))
    if h.id_requisito:
        texto = f"{h.id_requisito}, {texto}"
    if h.tipo.value == "indicio_inyeccion" and h.detalle:
        m = re.search(r"«([^»]+)»", h.detalle)
        if m:
            texto += f" («{m.group(1)}»)"
    return f"{nivel}: {texto}"


def _sin_repetir(it) -> list[str]:
    vistos, salida = set(), []
    for x in it:
        if x not in vistos:
            vistos.add(x)
            salida.append(x)
    return salida


# ============================================================ AuditorPort
class AuditorRol3:
    """Traduce el veredicto del auditor del Rol 3. Puede bloquear; NUNCA aprueba ni sube el estado
    que dejó el motor.

    Igual que en el banco del Rol 3 (`evaluacion.ruta_final`): solo un hallazgo bloqueante cambia la ruta.
    Las advertencias (p. ej. un deseable respaldado solo por la lista de habilidades) viajan en la
    razón para quien revisa, pero no sacan al candidato del flujo: en el grafo del Rol 1
    `requiere_revision` detiene el caso sin compuerta (H-5), y el 13-nov eso dejó a CV-001 en el Top
    sin mensaje que aprobar."""

    def __init__(self, contexto):
        self.contexto = contexto

    def auditar(self, ficha: FichaContrato, veredicto: VeredictoContrato) -> VeredictoContrato:
        caso = self.contexto.caso(ficha.correlation_id)
        a: Optional[AnalisisRol3] = getattr(caso, "rol3", None)
        if a is None:   # fail-closed: sin análisis del Rol 3 no hay aval
            return veredicto.model_copy(update={"estado": VeredictoEstado.REQUIERE_REVISION,
                                                "razon": "Auditor Rol 3: no hay análisis del Rol 3 para este caso"})
        bloqueantes = _sin_repetir(h.split(": ", 1)[1] for h in caso.hallazgos if h.startswith("bloqueo"))
        advertencias = _sin_repetir(h.split(": ", 1)[1] for h in caso.hallazgos if h.startswith("advertencia"))
        if a.citas_no_ancladas:
            n = len(a.citas_no_ancladas)
            advertencias.append("una cita no ubicada en el PDF" if n == 1 else f"{n} citas no ubicadas en el PDF")
        base = f"{a.etiqueta}. {veredicto.razon}."
        if a.veredicto.resultado == ResultadoAuditoria.BLOQUEA:
            return veredicto.model_copy(update={"estado": VeredictoEstado.BLOQUEADO,
                                                "razon": f"{base} El auditor bloquea: " + "; ".join(bloqueantes) + "."})
        extra = ("El auditor advierte: " + "; ".join(advertencias)) if advertencias else "El auditor no tiene observaciones"
        return veredicto.model_copy(update={"razon": f"{base} {extra}."})


# ============================================================ AgendadorPort
class AgendadorPortalRol3:
    """Agendador del Rol 3 (plantillas + calendario simulado propios, marcador {{nombre_de_pila}}).
    El portal lo llama una vez por candidato: un solo calendario por lote evita que dos candidatos
    reciban la misma franja. Sin cliente LLM usa la asignación determinista."""

    def __init__(self, contexto, cliente=None):
        from .agendador import Calendario, Plantillas, info_de_vacante
        self.contexto = contexto
        self.cliente = cliente
        self.info = info_de_vacante(contexto.vacante)
        self.calendario = Calendario.cargar()
        self.plantillas = Plantillas.cargar()

    def proponer(self, state, propuesta, *, now: datetime):
        from .agendador import agendar
        r = agendar(list(propuesta.candidatos_ref), self.info, self.cliente, ahora=now,
                    correlation_id=state.correlation_id, calendario=self.calendario, plantillas=self.plantillas)
        for p in r.propuestas:                     # reserva en el calendario del lote
            ini, fin = (datetime.fromisoformat(x) for x in p.franja.split("/"))
            self.calendario.ocupado.append((ini, fin))
        return r.propuestas[0]


# ============================================================ RoleAdapters
def adaptadores_rol3(contexto, *, cliente_agenda=None):
    """`RoleAdapters` del Rol 1 con los agentes del Rol 3 y el motor de reglas real del portal."""
    from cvagent.integration.ports import RoleAdapters
    from cvagent.operations.core import SimulatedDeliveryGateway
    from portal.adaptadores import PortalMotorReglas
    return RoleAdapters(analista=AnalistaRol3(contexto), motor_reglas=PortalMotorReglas(contexto),
                        auditor=AuditorRol3(contexto), agendador=AgendadorPortalRol3(contexto, cliente_agenda),
                        envio=SimulatedDeliveryGateway())


__all__ = ["AgendadorPortalRol3", "AnalisisRol3", "AnalistaRol3", "AuditorRol3", "VERSION_INTEGRACION",
           "adaptadores_rol3", "ficha_en_cache", "reanclar", "ruta_cv_json"]
