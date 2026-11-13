"""Orquestación del lote (Rol 4).

Une tres piezas que hoy no se hablaban:

  reglas/ (Rol 2)    aplica R12→R1→R2→R11/R3→R7 sobre los 40 CV, y al final
                     R4→R5→R6 para armar el staging del Top 5.
  cvagent/ (Rol 1)   corre un grafo durable POR CASO, con dos interrupciones
                     humanas y un decision_log encadenado.
  portal/            carga el texto canónico, construye fichas con citas
                     verificables y presenta todo a una persona.

El punto delicado está documentado como hallazgo H-2: el grafo es por caso y
R4/R5/R6 son de lote. Mientras eso no se concilie, el bucle del lote vive
aquí: cada caso corre hasta su interrupción de lista, el portal arma el Top 5
con el motor del Rol 2, y la decisión humana se reparte a cada hilo
(`aprobar` a los que entran, `rechazar` a los demás). Ningún caso queda sin
decisión registrada, que es lo que exige el SDD.
"""

from __future__ import annotations

import json
import os
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from langgraph.types import Command

from cvagent.audit.log import DecisionLog
from cvagent.domain.contracts import CaseState, EstadoCaso
from cvagent.workflow.graph import build_graph, run_case, thread_config
from cvagent.workflow.registry import CaseRegistry

from reglas import armar_staging, cargar_diccionario, cargar_vacante, procesar_lote
from reglas.comun import seudonimizar

from .adaptadores import ContextoCaso, ContextoLote, adaptadores_del_portal
from .texto import TextoNoDisponible, cargar_texto

RUTAS_EVALUABLES = {"evaluable"}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _interrupciones(resultado: dict) -> list[dict]:
    return [i.value for i in resultado.get("__interrupt__", ()) or ()]


class ServicioLote:
    """Estado vivo de un lote. Una instancia por proceso del portal."""

    def __init__(self, base_dir: str | Path = "data", *, database_url: str | None = None):
        self.base_dir = Path(base_dir)
        self.database_url = database_url or os.environ.get("CVAGENT_POSTGRES_URL") or None
        self._stack = ExitStack()
        self.decision_log = DecisionLog()
        self.registry = CaseRegistry()
        self.contexto: ContextoLote | None = None
        self.grafo = None
        self.estado_casos: dict[str, dict] = {}       # correlation_id → último resultado
        self.interrupciones: dict[str, dict] = {}     # correlation_id → payload pendiente
        self.staging: dict | None = None
        self.decision_lista: dict | None = None

    # ------------------------------------------------------------- carga
    def cargar(self, vacante_id: str = "VAC-001", version: int | None = None,
               *, incluir_inyeccion: bool = True) -> dict:
        """Lee la vacante vigente, los CV y corre el motor de reglas del Rol 2.

        `incluir_inyeccion` añade los INJ-01..04 de `data/extras_inyeccion/`.
        No cuentan entre los 40 del manifiesto, pero sin ellos el auditor no
        tiene nada que bloquear y la demostración no prueba su utilidad.
        """
        vacante = cargar_vacante(str(self.base_dir), vacante_id, version)
        diccionario = cargar_diccionario(str(self.base_dir / "diccionario_equivalencias.json"))

        rutas_cv = sorted((self.base_dir / "cvs_json").glob("*.json"))
        n_corpus = len(rutas_cv)
        if incluir_inyeccion:
            rutas_cv += sorted((self.base_dir / "extras_inyeccion" / "cvs_json").glob("*.json"))
        fichas = [json.loads(p.read_text(encoding="utf-8")) for p in rutas_cv]
        resultados = procesar_lote(fichas, vacante, diccionario)

        contexto = ContextoLote(vacante=vacante, diccionario=diccionario)
        rutas: dict[str, int] = {}
        sin_texto: list[str] = []

        for ficha in fichas:
            cv_id = ficha["cv_id"]
            resultado = resultados[cv_id]
            ruta = resultado.get("ruta") or "sin_ruta"
            rutas[ruta] = rutas.get(ruta, 0) + 1
            if ruta not in RUTAS_EVALUABLES:
                continue
            try:
                texto, procedencia = cargar_texto(cv_id, self.base_dir)
            except TextoNoDisponible:
                sin_texto.append(cv_id)
                continue
            correlation_id = str(uuid4())
            contexto.casos[correlation_id] = ContextoCaso(
                cv_id=cv_id,
                # R7: el grafo y el modelo solo ven una referencia opaca.
                candidato_ref=f"cand_{seudonimizar(cv_id)}",
                ficha_json=ficha,
                texto=texto,
                procedencia=procedencia,
                resultado_reglas=resultado,
            )

        self.contexto = contexto
        self.estado_casos.clear()
        self.interrupciones.clear()
        self.staging = None
        self.decision_lista = None
        self._construir_grafo()

        return {
            "vacante_id": vacante["vacante_id"],
            "vacante_version": vacante["version"],
            "titulo": vacante["titulo"],
            "cv_totales": len(fichas),
            "cv_corpus": n_corpus,
            "cv_inyeccion": len(fichas) - n_corpus,
            "evaluables": len(contexto.casos),
            "rutas": rutas,
            "sin_texto": sin_texto,
        }

    def _construir_grafo(self) -> None:
        checkpointer = None
        if self.database_url:
            from cvagent.workflow.persistence import postgres_checkpointer
            checkpointer = self._stack.enter_context(
                postgres_checkpointer(self.database_url, initialize=True))
        else:
            from langgraph.checkpoint.memory import InMemorySaver
            from cvagent.workflow.persistence import contract_serializer
            # El mismo serializador estricto que usa el checkpointer de Postgres:
            # sin esto, los enums del contrato vuelven como str y LangGraph avisa
            # de tipos no registrados en cada reanudación.
            checkpointer = InMemorySaver(serde=contract_serializer())
        self.grafo = build_graph(
            adapters=adaptadores_del_portal(self.contexto),
            checkpointer=checkpointer,
            decision_log=self.decision_log,
            registry=self.registry,
        )

    # --------------------------------------------------------- ejecución
    def ejecutar(self) -> dict:
        """Corre cada caso hasta su primera interrupción. Nunca decide nada."""
        if self.contexto is None:
            raise RuntimeError("no hay lote cargado")
        vacante = self.contexto.vacante
        errores: list[dict] = []

        for correlation_id, caso in self.contexto.casos.items():
            estado = CaseState(
                correlation_id=correlation_id,
                vacante_id=vacante["vacante_id"],
                vacante_version=str(vacante["version"]),
                creado_en=_ahora(),
                actualizado_en=_ahora(),
            )
            config = thread_config(correlation_id)
            try:
                resultado = run_case(self.grafo, estado, config=config)
            except Exception as exc:  # noqa: BLE001  un caso roto no tumba el lote
                errores.append({"cv_id": caso.cv_id, "error": str(exc)})
                continue
            self.estado_casos[correlation_id] = resultado
            pendientes = _interrupciones(resultado)
            if pendientes:
                self.interrupciones[correlation_id] = pendientes[0]

        self.staging = self._armar_staging()
        return {
            "casos_corridos": len(self.estado_casos),
            "con_interrupcion": len(self.interrupciones),
            "errores": errores,
            "staging": self.staging,
        }

    def _armar_staging(self) -> dict:
        """R4 → R5 → R6 sobre el lote, con el motor del Rol 2 sin modificar."""
        evaluaciones = []
        for correlation_id, caso in self.contexto.casos.items():
            if correlation_id not in self.estado_casos:
                continue
            veredicto = self.estado_casos[correlation_id].get("veredicto")
            bloqueado = _campo(veredicto, "estado") == "bloqueado"
            evaluaciones.append({
                "cv_id": caso.cv_id,
                "puntaje": caso.puntaje,
                "cobertura": caso.cobertura,
                # Un veredicto bloqueado es, para R4, una contradicción material:
                # no entra al Top 5 automático y va a revisión humana.
                "contradiccion_material": bloqueado,
            })
        return armar_staging(
            evaluaciones,
            self.contexto.vacante["vacante_id"],
            self.contexto.vacante["version"],
        )

    # ---------------------------------------------------------- decisión
    def _correlation_de(self, cv_id: str) -> str | None:
        for cid, caso in self.contexto.casos.items():
            if caso.cv_id == cv_id:
                return cid
        return None

    def decidir_lista(self, *, decision: str, aprobador: str, razon: str,
                      cv_ids_aprobados: list[str] | None = None) -> dict:
        """Reparte UNA decisión humana de lote a cada hilo del grafo.

        `aprobar`  → los del Top 5 siguen; el resto recibe `rechazar` con razón.
        `ajustar`  → igual, pero el Top 5 lo define `cv_ids_aprobados`.
        `rechazar` → todos los hilos reciben `rechazar`.
        """
        if self.staging is None:
            raise RuntimeError("no hay staging: ejecute el lote primero")
        if decision not in {"aprobar", "ajustar", "rechazar"}:
            raise ValueError(f"decisión inválida: {decision}")

        propuestos = [t["cv_id"] for t in self.staging["top"]]
        if decision == "rechazar":
            aprobados = []
        elif decision == "ajustar":
            aprobados = list(cv_ids_aprobados or [])
            if not aprobados:
                raise ValueError("ajustar exige al menos un candidato")
            desconocidos = [c for c in aprobados if self._correlation_de(c) is None]
            if desconocidos:
                raise ValueError(f"candidatos fuera del lote: {', '.join(desconocidos)}")
        else:
            aprobados = propuestos

        reanudados, resultados = [], {}
        for correlation_id, caso in self.contexto.casos.items():
            if correlation_id not in self.interrupciones:
                continue
            entra = caso.cv_id in aprobados
            respuesta = {
                "decision": "aprobar" if entra else "rechazar",
                "aprobador": aprobador,
                "razon": razon if entra else f"{razon} · fuera de la lista aprobada",
            }
            if entra and decision == "ajustar":
                respuesta["decision"] = "ajustar"
                respuesta["candidatos_ref_ajustados"] = [caso.candidato_ref]
            config = thread_config(correlation_id)
            resultado = self.grafo.invoke(Command(resume=respuesta), config)
            self.estado_casos[correlation_id] = resultado
            pendientes = _interrupciones(resultado)
            if pendientes:
                self.interrupciones[correlation_id] = pendientes[0]
            else:
                self.interrupciones.pop(correlation_id, None)
            reanudados.append(caso.cv_id)
            resultados[caso.cv_id] = _resumen_caso(resultado)

        self.decision_lista = {
            "decision": decision, "aprobador": aprobador, "razon": razon,
            "aprobados": aprobados, "propuestos": propuestos,
            "momento": _ahora().isoformat(timespec="seconds"),
        }
        return {"reanudados": reanudados, "aprobados": aprobados, "casos": resultados}

    def decidir_mensaje(self, *, cv_id: str, decision: str, aprobador: str, razon: str,
                        texto_exacto: str | None = None) -> dict:
        """Segunda compuerta: aprobar el texto exacto antes de cualquier envío."""
        correlation_id = self._correlation_de(cv_id)
        if correlation_id is None:
            raise ValueError(f"cv_id fuera del lote: {cv_id}")
        pendiente = self.interrupciones.get(correlation_id)
        if pendiente is None:
            raise ValueError(f"{cv_id} no tiene aprobación pendiente")
        if pendiente.get("tipo") != "mensaje_exacto":
            raise ValueError(
                f"{cv_id} está esperando «{pendiente.get('tipo')}», no la aprobación "
                "del mensaje. Resuelva primero la compuerta de la lista corta.")
        respuesta: dict = {"decision": decision, "aprobador": aprobador, "razon": razon}
        if decision == "ajustar":
            if not texto_exacto:
                raise ValueError("ajustar el mensaje exige el texto exacto")
            respuesta["texto_exacto_ajustado"] = texto_exacto
        config = thread_config(correlation_id)
        resultado = self.grafo.invoke(Command(resume=respuesta), config)
        self.estado_casos[correlation_id] = resultado
        pendientes = _interrupciones(resultado)
        if pendientes:
            self.interrupciones[correlation_id] = pendientes[0]
        else:
            self.interrupciones.pop(correlation_id, None)
        return _resumen_caso(resultado)

    # ------------------------------------------------------------ vistas
    def detenidos(self) -> list[dict]:
        """Casos que el grafo paró ANTES de la compuerta humana.

        Es el hallazgo H-5: un veredicto bloqueado enruta a `stop`, así que el
        caso no genera interrupción y nadie lo vería. El SDD exige que una
        excepción cree revisión humana y no un descarte automático, así que el
        portal los presenta aparte en lugar de dejarlos desaparecer.
        """
        salida = []
        for correlation_id, caso in self.contexto.casos.items():
            resultado = self.estado_casos.get(correlation_id)
            if resultado is None or correlation_id in self.interrupciones:
                continue
            veredicto = resultado.get("veredicto")
            salida.append({
                "cv_id": caso.cv_id,
                "candidato_ref": caso.candidato_ref,
                "estado_caso": _valor(resultado.get("estado")),
                "razon_parada": _valor(resultado.get("razon_parada")),
                "veredicto": {
                    "estado": _campo(veredicto, "estado"),
                    "razon": _campo(veredicto, "razon"),
                } if veredicto is not None else None,
            })
        return sorted(salida, key=lambda c: c["cv_id"])

    def resumen(self) -> dict:
        if self.contexto is None:
            return {"cargado": False}
        por_estado: dict[str, int] = {}
        for resultado in self.estado_casos.values():
            clave = _valor(resultado.get("estado")) or "desconocido"
            por_estado[clave] = por_estado.get(clave, 0) + 1
        return {
            "cargado": True,
            "vacante_id": self.contexto.vacante["vacante_id"],
            "vacante_version": self.contexto.vacante["version"],
            "titulo": self.contexto.vacante["titulo"],
            "evaluables": len(self.contexto.casos),
            "corridos": len(self.estado_casos),
            "pendientes_aprobacion": len(self.interrupciones),
            "detenidos_sin_compuerta": len(self.detenidos()),
            "por_estado": por_estado,
            "staging": self.staging,
            "decision_lista": self.decision_lista,
            "cadena_integra": self.decision_log.verify_integrity(),
            "entradas_log": len(self.decision_log.entries),
            "checkpointer": "postgres" if self.database_url else "memoria",
        }

    def candidatos(self) -> list[dict]:
        """Lo que la bandeja necesita para mostrar la lista con su evidencia."""
        if self.contexto is None:
            return []
        posiciones = {t["cv_id"]: t["posicion"] for t in (self.staging or {}).get("top", [])}
        salida = []
        for correlation_id, caso in self.contexto.casos.items():
            resultado = self.estado_casos.get(correlation_id, {})
            veredicto = resultado.get("veredicto")
            salida.append({
                "cv_id": caso.cv_id,
                "correlation_id": correlation_id,
                "candidato_ref": caso.candidato_ref,
                "posicion": posiciones.get(caso.cv_id),
                "en_top": caso.cv_id in posiciones,
                "puntaje": caso.puntaje,
                "cobertura": caso.cobertura,
                "procedencia": caso.procedencia,
                "estado_caso": _valor(resultado.get("estado")),
                "razon_parada": _valor(resultado.get("razon_parada")),
                "veredicto": {
                    "estado": _campo(veredicto, "estado"),
                    "razon": _campo(veredicto, "razon"),
                } if veredicto is not None else None,
                "estado_requisitos": caso.resultado_reglas.get("estado_requisitos", {}),
                "meses_efectivos": caso.resultado_reglas.get("meses_efectivos"),
                "citas": [c.model_dump(mode="json") for c in caso.citas],
                "interrupcion": self.interrupciones.get(correlation_id),
            })
        salida.sort(key=lambda c: (c["posicion"] is None, c["posicion"] or 0, c["cv_id"]))
        return salida

    def texto_de(self, cv_id: str) -> dict:
        cid = self._correlation_de(cv_id)
        if cid is None:
            raise ValueError(f"cv_id fuera del lote: {cv_id}")
        caso = self.contexto.casos[cid]
        return {"cv_id": cv_id, "procedencia": caso.procedencia, "texto": caso.texto,
                "citas": [c.model_dump(mode="json") for c in caso.citas]}

    def evidencia(self) -> dict:
        return {
            "integra": self.decision_log.verify_integrity(),
            "entradas": [e.model_dump(mode="json") for e in self.decision_log.entries],
        }

    def cerrar(self) -> None:
        self._stack.close()


def _valor(x):
    """Desenvuelve un Enum. Los valores que vuelven del checkpointer ya son str."""
    return getattr(x, "value", x)


def _campo(obj, nombre):
    """Lee un campo de un contrato que puede venir como objeto o como dict.

    Al reanudar, LangGraph devuelve el estado deserializado: unas veces trae
    los modelos Pydantic y otras sus diccionarios. Leer con getattr a secas
    devolvía None en silencio y la bandeja mostraba veredictos vacíos.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return _valor(obj.get(nombre))
    return _valor(getattr(obj, nombre, None))


def _resumen_caso(resultado: dict) -> dict:
    return {
        "estado": _valor(resultado.get("estado")),
        "razon_parada": _valor(resultado.get("razon_parada")),
        "interrupciones": _interrupciones(resultado),
        "efectos_externos": len(resultado.get("efectos_externos", []) or []),
    }


__all__ = ["ServicioLote", "EstadoCaso"]
