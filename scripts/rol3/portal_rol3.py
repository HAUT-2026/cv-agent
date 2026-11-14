"""Rol 3 · Abre el portal del Rol 4 con los agentes REALES del Rol 3 (analista, auditor, agendador).

No modifica `portal/`: crea una subclase de `ServicioLote` que solo cambia los adaptadores del grafo
y la pone en lugar del servicio del portal antes de arrancar el servidor; además añade a la página
`cvagent/agentes/portal_ui/` (tabla de candidatos con filtros y desplazamiento, y el estado del
sistema veraz). `python -m portal` sigue abriendo el portal original con sus dobles.

Uso (raíz del repo, en Docker; luego abrir http://localhost:8000):
  docker run --rm -it -p 8000:8000 -v "${PWD}:/app" -w /app python:3.12-slim sh -c
      "pip install -q -e '.[portal]' && python scripts/rol3/portal_rol3.py"
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import uvicorn  # noqa: E402

import portal.api as api  # noqa: E402
from cvagent.agentes.portal_rol3 import VERSION_INTEGRACION, adaptadores_rol3  # noqa: E402
from cvagent.workflow.graph import build_graph  # noqa: E402
from portal.lote import ServicioLote  # noqa: E402


class ServicioLoteRol3(ServicioLote):
    """Igual que el del portal; solo cambia de dónde salen los adaptadores del grafo."""

    def _construir_grafo(self) -> None:
        if self.database_url:
            from cvagent.workflow.persistence import postgres_checkpointer
            checkpointer = self._stack.enter_context(postgres_checkpointer(self.database_url, initialize=True))
        else:
            from langgraph.checkpoint.memory import InMemorySaver
            from cvagent.workflow.persistence import contract_serializer
            checkpointer = InMemorySaver(serde=contract_serializer())
        self.grafo = build_graph(adapters=adaptadores_rol3(self.contexto), checkpointer=checkpointer,
                                 decision_log=self.decision_log, registry=self.registry)


UI_ROL3 = RAIZ / "cvagent" / "agentes" / "portal_ui"


def instalar_ui_rol3() -> None:
    """La página del portal + las mejoras del Rol 3 (tabla con filtros y estado del sistema veraz).

    Se reemplaza solo la ruta «/» de ESTA aplicación en memoria para entregar el index.html del Rol 4
    con dos líneas añadidas; portal/web/ no se toca. Si el index cambia y no se puede insertar, se
    entrega tal cual y se avisa en la consola."""
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles

    api.app.router.routes[:] = [r for r in api.app.router.routes if getattr(r, "path", None) != "/"]

    @api.app.get("/", include_in_schema=False)
    def inicio_rol3():
        html = (api.WEB / "index.html").read_text("utf-8")
        extra_css = '<link rel="stylesheet" href="/rol3-ui/rol3.css">'
        extra_js = '<script src="/rol3-ui/rol3.js" defer></script>'
        if "</head>" in html and "</body>" in html:
            html = html.replace("</head>", f"  {extra_css}\n</head>", 1).replace("</body>", f"  {extra_js}\n</body>", 1)
        else:
            print("  Aviso: el index.html del portal cambió; se entrega sin las mejoras del Rol 3.")
        return HTMLResponse(html)

    api.app.mount("/rol3-ui", StaticFiles(directory=UI_ROL3), name="rol3-ui")


def instalar_api_rol3() -> None:
    """Rutas propias del Rol 3 (solo lectura). El portal no muestra la agenda una vez aprobada: el
    mensaje sale de la bandeja y solo queda la huella en Evidencia."""
    from portal.lote import _campo, _valor

    @api.app.get("/api/rol3/agenda", tags=["rol 3"])
    def agenda_rol3():
        """Entrevistas propuestas por el agendador del Rol 3, con su estado en el grafo."""
        s = api.servicio
        if s.contexto is None:
            return []
        salida = []
        for cid, caso in s.contexto.casos.items():
            res = s.estado_casos.get(cid) or {}
            p = res.get("propuesta_agenda")
            if p is None:
                continue
            inicio, _, fin = (_campo(p, "franja") or "").partition("/")
            estado = _valor(res.get("estado"))
            salida.append({
                "cv_id": caso.cv_id, "candidato_ref": caso.candidato_ref, "inicio": inicio, "fin": fin,
                "plantilla": _campo(p, "plantilla_version"), "texto_exacto": _campo(p, "texto_exacto"),
                "estado_caso": estado,
                "enviado": len(res.get("efectos_externos") or []) > 0,
                "modelo": _campo(_campo(p, "auditoria"), "modelo_version"),
            })
        return sorted(salida, key=lambda x: x["inicio"])


def main() -> None:
    api.servicio = ServicioLoteRol3(api.DATA)
    instalar_api_rol3()
    instalar_ui_rol3()
    puerto = int(os.environ.get("PUERTO", "8000"))
    print(f"\n  CVAgent · Portal con los agentes del Rol 3 ({VERSION_INTEGRACION})\n"
          f"  Abrir: http://localhost:{puerto}   (API: /docs)\n  (Ctrl+C para detener)\n")
    # 0.0.0.0 para que el navegador del host lo alcance a través de Docker (-p 8000:8000)
    uvicorn.run(api.app, host="0.0.0.0", port=puerto)


if __name__ == "__main__":
    main()
