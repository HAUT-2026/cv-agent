"""Rol 3 · agendador sobre el Top del staging (demo de punta a punta).

Uso (desde la raíz del repo):
  python scripts/rol3/agendar.py --sin-llm        # asignación determinista, en segundos
  python scripts/rol3/agendar.py                  # agente agendador con el LLM de .env
  python scripts/rol3/agendar.py --ahora 2026-11-20T09:00   # otra «fecha actual» (cambia las franjas)

El Top sale del staging SIMULADO (analista léxico + puntaje provisional + armar_staging del Rol 2),
como en probar_banco.py --sin-llm. Este script hace de «workflow»: traduce cv_id → referencia
opaca; el agendador solo recibe las referencias, nunca el CV ni el cv_id.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from reglas import cargar_diccionario, cargar_vacante as cargar_vacante_rol2  # noqa: E402
from reglas.motor import armar_staging, procesar_lote  # noqa: E402

from cvagent.agentes.agendador import (AgendaInvalida, agendar, info_de_vacante, ref_opaca,  # noqa: E402
                                       verificar_propuesta)
from cvagent.agentes.criterios import cargar_vacante  # noqa: E402
from cvagent.agentes.cv_json import preparar_caso  # noqa: E402
from cvagent.agentes.evaluacion import ficha_lexica, ruta_final  # noqa: E402
from cvagent.agentes.puntaje import calcular_puntaje  # noqa: E402


def _cargar_env(ruta: Path) -> None:
    if ruta.exists():
        for linea in ruta.read_text("utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_cargar_env(RAIZ / ".env")
args = sys.argv[1:]
sin_llm = "--sin-llm" in args
tz = timezone(timedelta(hours=-5))
ahora = datetime(2026, 11, 13, 9, 0, tzinfo=tz)
if "--ahora" in args:
    ahora = datetime.fromisoformat(args[args.index("--ahora") + 1]).replace(tzinfo=tz)

D = RAIZ / "data"
man = json.loads((D / "manifiesto.json").read_text("utf-8"))
v2 = cargar_vacante_rol2(str(D), man["vacante_id"], man.get("vacante_version"))
dic = cargar_diccionario(str(D / "diccionario_equivalencias.json"))
vac = cargar_vacante(D, man["vacante_id"], man.get("vacante_version"))
info = info_de_vacante(v2)

# 1) Top del staging simulado (igual que probar_banco.py --sin-llm)
cvs = {c["cv_id"]: c for c in man["cvs"]}
motor = procesar_lote([json.loads((D / c["archivo_json"]).read_text("utf-8")) for c in cvs.values()], v2, dic)
puntajes = []
for cv_id, c in cvs.items():
    if motor[cv_id]["ruta"] != "evaluable":
        continue
    caso = preparar_caso(D / c["archivo_json"])
    if ruta_final("evaluable", bool(caso.indicios)) != "ranking":
        continue
    evs, construir = ficha_lexica(caso, vac)
    puntajes.append(calcular_puntaje(construir(evs), motor[cv_id], vac, dic, None, caso.texto.texto))
st = armar_staging([p.para_staging() for p in puntajes], vac.id_vacante, vac.version)
top = [t["cv_id"] for t in st["top"]]
refs = {cv: ref_opaca(cv, vac.id_vacante) for cv in top}
print(f"Top (staging {st['staging_id']}): {', '.join(top)}")
print(f"El agendador recibe solo: {', '.join(refs.values())}")
print(f"Fecha y hora «actual»: {ahora:%Y-%m-%d %H:%M} · cargo: {info['cargo']} · modalidad: {info['modalidad']}\n")

# 2) Agendador
cliente = None
if not sin_llm:
    from cvagent.agentes.llm import ClienteLLM, ConfigLLM
    cliente = ClienteLLM(ConfigLLM.desde_entorno())


def en_vivo(tipo, dato):
    if tipo == "pensando":
        print(f"  paso {dato}: esperando al modelo…", flush=True)
    else:
        print(f"    {dato.tipo} {dato.herramienta or ''} "
              f"{json.dumps(dato.argumentos, ensure_ascii=False)[:90] if dato.argumentos else ''}", flush=True)
        if dato.tipo == "entrega_incompleta":
            for p in dato.resultado:
                print(f"      ✗ {p[:150]}")


try:
    r = agendar(list(refs.values()), info, cliente, ahora=ahora, al_evento=None if sin_llm else en_vivo)
except AgendaInvalida as e:
    print("✗ El agendador no logró una agenda válida → el caso pasa a un humano (fail-closed):")
    for p in e.args[0]:
        print(f"  - {p}")
    sys.exit(1)

modo = "determinista (sin LLM)" if sin_llm else f"{r.agente.pasos} pasos · {r.segundos:.0f} s"
print(f"\nPropuestas ({modo}) · pendientes de APROBACIÓN del reclutador (R10):")
de_ref = {v: k for k, v in refs.items()}
for p in r.propuestas:
    ini, fin = p.franja.split("/")
    ok = verificar_propuesta(p, info)
    print(f"  {de_ref[p.candidato_ref]} → {p.candidato_ref} · {ini[:16].replace('T', ' ')}–{fin[11:16]} · "
          f"{p.plantilla_version} · texto {'✓ idéntico a la plantilla' if not ok else '✗ ' + '; '.join(ok)}")
print("\nEjemplo de texto exacto a aprobar (el envío reemplaza {{nombre_de_pila}} desde la bóveda de identidad):")
print("  " + r.propuestas[0].texto_exacto.replace("\n", "\n  "))
