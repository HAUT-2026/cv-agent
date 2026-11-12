"""Rol 3 · banco de evaluación de punta a punta contra data/manifiesto.json.

Flujo: motor del Rol 2 (R12, R1, R2, R11/R3, R7) → solo los «evaluables» pasan al Rol 3
(sanitización + analista + auditor) → ruta final (ranking | bandeja | rutas del motor).

Uso (desde la raíz del repo):
  python scripts/rol3/probar_banco.py --sin-llm   # 40 CV + 4 extras: motor + sanitización, en segundos
  python scripts/rol3/probar_banco.py CV-001      # además, analista (LLM de .env) y auditor sobre un CV
  python scripts/rol3/probar_banco.py todos       # todos los evaluables con LLM (lento en hardware local)

El manifiesto NUNCA se le entrega al agente. Resultados en resultados/rol3/ (ignorado por git).
"""
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from reglas import cargar_diccionario, cargar_vacante as cargar_vacante_rol2  # noqa: E402
from reglas.motor import armar_staging, evaluar_caso, procesar_lote  # noqa: E402

from cvagent.agentes.auditor import auditar  # noqa: E402
from cvagent.agentes.criterios import cargar_vacante  # noqa: E402
from cvagent.agentes.cv_json import preparar_caso  # noqa: E402
from cvagent.agentes.evaluacion import Comparacion, estados_del_analista, ficha_lexica, ruta_final  # noqa: E402
from cvagent.agentes.puntaje import calcular_puntaje  # noqa: E402
from cvagent.agentes.rubrica import VERSION_RUBRICA  # noqa: E402


def _cargar_env(ruta: Path) -> None:
    """Lee .env sin dependencias (las variables ya definidas en el entorno ganan)."""
    if ruta.exists():
        for linea in ruta.read_text("utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_cargar_env(RAIZ / ".env")
D = RAIZ / "data"
SALIDA = RAIZ / "resultados" / "rol3"
man = json.loads((D / "manifiesto.json").read_text("utf-8"))
entradas = {c["cv_id"]: c for c in man["cvs"] + man.get("extras_inyeccion", [])}
vac_rol2 = cargar_vacante_rol2(str(D), man["vacante_id"], man.get("vacante_version"))
dic = cargar_diccionario(str(D / "diccionario_equivalencias.json"))
vac = cargar_vacante(D, man["vacante_id"], man.get("vacante_version"))
args = sys.argv[1:] or ["--sin-llm"]


def fichas_crudas(ids):
    return [json.loads((D / entradas[i]["archivo_json"]).read_text("utf-8")) for i in ids]


def rutas_del_motor() -> dict:
    """R12 sobre el lote de los 40 CV; los extras de inyección se evalúan uno a uno."""
    lote = [i for i in entradas if entradas[i].get("grupo") != "extra_inyeccion"]
    rutas = procesar_lote(fichas_crudas(lote), vac_rol2, dic)
    for i in entradas:
        if i not in rutas:
            rutas[i] = evaluar_caso(fichas_crudas([i])[0], vac_rol2, dic)
    return rutas


motor = rutas_del_motor()


def mostrar_staging(puntajes: list, titulo: str) -> None:
    """Puntaje/cobertura (Rol 3, rúbrica provisional) → armar_staging (Rol 2: R4, R5, R6)."""
    if not puntajes:
        return
    st = armar_staging([p.para_staging() for p in puntajes], vac.id_vacante, vac.version)
    por_id = {p.cv_id: p for p in puntajes}
    print(f"\n{'=' * 78}\n{titulo} · {VERSION_RUBRICA} (provisional, pendiente de RR. HH.)")
    print(f"{'pos':<5}{'CV':<8}{'puntaje':<9}{'cobertura':<11}grupo (manifiesto)")
    for t in st["top"]:
        print(f"{t['posicion']:<5}{t['cv_id']:<8}{t['puntaje']:<9}{t['cobertura']:<11}{entradas[t['cv_id']].get('grupo')}")
    if st["empate_r5"]:
        print(f"  R5: diferencia 5.º–6.º = {st['diferencia_5_6']} ≤ 0,02 → se presentan seis")
    if st["aviso_r6"]:
        print(f"  R6: {st['aviso_r6']}")
    rev = st["revision_humana_r4"]
    if rev:
        print(f"  R4 → revisión humana (cobertura < 0,70 o contradicción), fuera del Top automático: "
              + ", ".join(f"{i} ({por_id[i].cobertura})" for i in rev))
    print(f"  staging_id {st['staging_id']} (inmutable; mismo conjunto → mismo hash)")
print(f"Vacante {vac.id_vacante} v{vac.version}: {vac.cargo} · {len(vac.requisitos)} requisitos "
      f"({sum(r.obligatorio for r in vac.requisitos)} obligatorios)\n")

# ------------------------------------------------------------------ sin LLM
if args[0] == "--sin-llm":
    print(f"{'CV':<8}{'motor (esperado)':<38}{'ruta final (esperada)':<36}{'meses':<9}inyección")
    ok_m = ok_f = ok_meses = n_meses = 0
    simulados = []
    for cv_id, m in entradas.items():
        e = m["esperado"]
        rm = motor[cv_id]["ruta"]
        indicios = []
        if rm == "evaluable":
            indicios = preparar_caso(D / m["archivo_json"]).indicios
        rf = ruta_final(rm, bool(indicios))
        if rf == "ranking":
            c = preparar_caso(D / m["archivo_json"])
            evs, construir = ficha_lexica(c, vac)
            simulados.append(calcular_puntaje(construir(evs), motor[cv_id], vac, dic, None, c.texto.texto))
        ok_m += rm == e["ruta_motor_reglas"]
        ok_f += rf == e["ruta_final"]
        meses = motor[cv_id].get("meses_efectivos")
        if e["meses_efectivos"] is not None:
            n_meses += 1
            ok_meses += meses == e["meses_efectivos"]
        print(f"{cv_id:<8}{rm + ' (' + e['ruta_motor_reglas'] + ')' + (' ✓' if rm == e['ruta_motor_reglas'] else ' ✗'):<38}"
              f"{rf + ' (' + e['ruta_final'] + ')' + (' ✓' if rf == e['ruta_final'] else ' ✗'):<36}"
              f"{str(meses if meses is not None else '-'):<9}"
              f"{', '.join(sorted({i.patron for i in indicios})) or '-'}")
    n = len(entradas)
    print(f"\nRuta del motor (Rol 2): {ok_m}/{n} · Ruta final de punta a punta (Rol 2 + Rol 3): {ok_f}/{n} · "
          f"Meses R11: {ok_meses}/{n_meses}")
    mostrar_staging(simulados, "Staging SIMULADO (analista léxico, sin LLM; no reemplaza al analista)")
    sys.exit(0)

# ------------------------------------------------------------------ con LLM
from cvagent.agentes.analista import analizar_caso  # noqa: E402
from cvagent.agentes.llm import ClienteLLM, ConfigLLM  # noqa: E402

ids = list(entradas) if args[0] == "todos" else args
cliente = ClienteLLM(ConfigLLM.desde_entorno())
SALIDA.mkdir(parents=True, exist_ok=True)
comparaciones: list[Comparacion] = []
puntajes = []

for cv_id in ids:
    m, e = entradas[cv_id], entradas[cv_id]["esperado"]
    rm = motor[cv_id]["ruta"]
    comp = Comparacion(cv_id, e["ruta_motor_reglas"], rm, e["ruta_final"], rm, e.get("estado_requisitos") or {})
    print(f"\n=== {cv_id} · motor: {rm} · trampas: {', '.join(m['trampas']) or 'ninguna'}")
    if rm != "evaluable":
        print(f"  El motor del Rol 2 lo saca del flujo ({rm}): el analista no lo recibe.")
        comparaciones.append(comp)
        continue

    caso = preparar_caso(D / m["archivo_json"])
    T0 = time.monotonic()

    def en_vivo(tipo, dato, T0=T0):
        t = time.monotonic() - T0
        if tipo == "pensando":
            print(f"  [{t:5.0f} s] paso {dato}: esperando al modelo…", flush=True)
        else:
            extra = f"→ {len(dato.resultado['frases'])} frases" if isinstance(dato.resultado, dict) and "frases" in dato.resultado else ""
            print(f"  [{t:5.0f} s]   {dato.tipo} {dato.herramienta or ''} "
                  f"{json.dumps(dato.argumentos, ensure_ascii=False)[:60] if dato.argumentos else ''} {extra}", flush=True)

    try:
        r = analizar_caso(caso, vac, cliente, al_evento=en_vivo)
    except Exception as ex:  # un CV que falla no detiene el banco: queda en bandeja (fail-closed)
        print(f"  ✗ {type(ex).__name__}: {ex} → bandeja (fail-closed)")
        comp.ruta_final, comp.motivos = "bandeja", [f"{type(ex).__name__}: {ex}"]
        comparaciones.append(comp)
        continue

    v = auditar(r.ficha, caso, vac)
    comp.ruta_final = ruta_final(rm, v.resultado.value == "bloquea")
    comp.estados_analista = estados_del_analista(r.ficha)
    comparaciones.append(comp)

    f = r.ficha
    print(f"  Ficha: cobertura={f.cobertura_evidencia} · {r.agente.pasos} pasos · {r.segundos:.0f} s")
    for ev in f.evaluaciones:
        esperado = comp.estados_esperados.get(ev.id_requisito)
        marca = "" if esperado is None else (" ✓" if comp.estados_analista[ev.id_requisito] == esperado else f" ✗ (esperado {esperado})")
        print(f"    {ev.id_requisito} {'(oblig.)' if ev.obligatorio else '        '} {ev.cumplimiento.value:<14}{marca}")
        for c in ev.citas:
            print(f"        «{c.texto[:75]}»")
        for c in ev.citas_rechazadas:
            print(f"        ✗ NO ENCONTRADA «{c[:70]}»")
    print(f"  Auditor: {v.resultado.value.upper()}")
    for h in v.hallazgos:
        print(f"    {'🔴' if h.severidad.value == 'bloqueante' else '🟡'} {h.tipo.value:<26}{h.id_requisito or '':<8}{h.detalle or ''}")
    print(f"  Ruta final: {comp.ruta_final} · esperada: {comp.ruta_final_esperada} {'✓' if comp.acierta_ruta_final else '✗'}")
    pje = None
    if comp.ruta_final == "ranking":
        pje = calcular_puntaje(f, motor[cv_id], vac, dic, v, caso.texto.texto)
        puntajes.append(pje)
        print(f"  Puntaje {pje.puntaje} · cobertura {pje.cobertura}"
              + (" · contradicción material" if pje.contradiccion_material else "") + "   ("
              + ", ".join(f"{c.id}={'—' if c.valor is None else c.valor}" for c in pje.criterios) + ")")
    (SALIDA / f"{cv_id}.json").write_text(json.dumps({
        "ficha": f.model_dump(mode="json"), "veredicto": v.model_dump(mode="json"),
        "indicios": [asdict(i) for i in caso.indicios], "proxies": [asdict(p) for p in caso.proxies],
        "traza": [asdict(t) for t in r.agente.traza], "comparacion": asdict(comp),
        "puntaje": pje.a_dict() if pje else None,
    }, ensure_ascii=False, indent=2, default=str), "utf-8")

# ------------------------------------------------------------------ resumen
print("\n" + "=" * 78)
print(f"{'CV':<8}{'ruta final (esperada)':<40}{'requisitos analista = esperado'}")
coinc = comp_total = 0
for c in comparaciones:
    a, b = c.coincidencias_requisitos
    coinc, comp_total = coinc + a, comp_total + b
    print(f"{c.cv_id:<8}{c.ruta_final + ' (' + c.ruta_final_esperada + ')' + (' ✓' if c.acierta_ruta_final else ' ✗'):<40}"
          f"{f'{a}/{b}' if b else '-'}")
n = len(comparaciones)
print(f"\nRuta final: {sum(c.acierta_ruta_final for c in comparaciones)}/{n}"
      + (f" · Estados de requisitos (analista vs. esperado): {coinc}/{comp_total}" if comp_total else ""))
mostrar_staging(puntajes, "Staging con el analista LLM")
nombre = "resumen_todos.json" if args[0] == "todos" else f"resumen_{'_'.join(ids)}.json"
(SALIDA / nombre).write_text(json.dumps({"modelo": cliente.config.etiqueta,
                                         "resultados": [asdict(c) for c in comparaciones]},
                                        ensure_ascii=False, indent=2), "utf-8")
print(f"Guardado en resultados/rol3/{nombre}")
