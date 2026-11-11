"""Rol 3 · banco de evaluación del analista contra data/manifiesto.json.

Uso (desde la raíz del repo):
  uv run python scripts/rol3/probar_banco.py --sin-llm   # parte determinista, 12 CV, segundos
  uv run python scripts/rol3/probar_banco.py CV-007      # analista real (LLM de .env) sobre un CV
  uv run python scripts/rol3/probar_banco.py todos       # banco completo con LLM

El manifiesto NUNCA se le entrega al agente. Resultados en resultados/rol3/ (ignorado por git).
La «decisión provisional» solo sirve para medir: la oficial es del motor de reglas (Rol 2),
el auditor y el humano.
"""
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from cvagent.agentes.auditor import auditar  # noqa: E402
from cvagent.agentes.criterios import cargar_vacante  # noqa: E402
from cvagent.agentes.cv_json import preparar_caso  # noqa: E402
from cvagent.agentes.evaluacion import Comparacion, decision_provisional, fallidos_del_analista  # noqa: E402
from cvagent.agentes.herramientas import REGISTRO, ContextoCaso  # noqa: E402


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
vac = cargar_vacante(D / "vacante_v1.json")
manifiesto = {c["cv_id"]: c for c in json.loads((D / "manifiesto.json").read_text("utf-8"))["cvs"]}
args = sys.argv[1:] or ["--sin-llm"]


def experiencia(caso):
    return REGISTRO["experiencia_por_cargo"].funcion({}, ContextoCaso(caso.cv, caso.texto, vac))


# ------------------------------------------------------------------ sin LLM
if args[0] == "--sin-llm":
    print(f"Vacante {vac.id_vacante} v{vac.version}: {vac.cargo} · {len(vac.requisitos)} requisitos "
          f"({sum(r.obligatorio for r in vac.requisitos)} obligatorios)\n")
    print(f"{'CV':<7}{'esperado':<16}{'meses':<13}{'inyección':<11}{'proxies R7':<14}trampas / patrones detectados")
    ok_m = ok_i = 0
    for cv_id, m in manifiesto.items():
        caso = preparar_caso(D / m["archivo_json"])
        exp = experiencia(caso)
        meses_ok = exp["total_meses_sin_solapes"] == m["esperado"]["meses_efectivos"]
        espera_iny = "inyeccion" in m["esperado"]["debe_marcar"]
        detecta = sorted({i.patron for i in caso.indicios})
        iny_ok = espera_iny == bool(detecta)
        ok_m += meses_ok
        ok_i += iny_ok
        prox = sorted({p.patron for p in caso.proxies})
        print(f"{cv_id:<7}{m['esperado']['decision']:<16}"
              f"{str(exp['total_meses_sin_solapes']) + '/' + str(m['esperado']['meses_efectivos']) + (' ✓' if meses_ok else ' ✗'):<13}"
              f"{('sí' if detecta else 'no') + (' ✓' if iny_ok else ' ✗'):<11}{len(prox) or '-':<14}"
              f"{', '.join(m['trampas']) or '-'}")
        if detecta:
            print(f"{'':<47}↳ {', '.join(detecta)}")
        if prox:
            print(f"{'':<47}↳ proxies: {', '.join(prox)}")
    n = len(manifiesto)
    print(f"\nMeses efectivos (R11 provisional): {ok_m}/{n} · Detección de inyección: {ok_i}/{n}")
    sys.exit(0)

# ------------------------------------------------------------------ con LLM
from cvagent.agentes.analista import analizar_texto  # noqa: E402
from cvagent.agentes.llm import ClienteLLM, ConfigLLM  # noqa: E402

ids = list(manifiesto) if args[0] == "todos" else args
cliente = ClienteLLM(ConfigLLM.desde_entorno())
SALIDA.mkdir(parents=True, exist_ok=True)
comparaciones: list[Comparacion] = []

for cv_id in ids:
    m = manifiesto[cv_id]
    caso = preparar_caso(D / m["archivo_json"])
    T0 = time.monotonic()
    print(f"\n=== {cv_id} ({m['perfil']}; trampas: {', '.join(m['trampas']) or 'ninguna'}) con {cliente.config.etiqueta}")

    def en_vivo(tipo, dato, T0=T0):
        t = time.monotonic() - T0
        if tipo == "pensando":
            print(f"  [{t:5.0f} s] paso {dato}: esperando al modelo…", flush=True)
        else:
            extra = ""
            if isinstance(dato.resultado, dict) and "frases" in dato.resultado:
                extra = f"→ {len(dato.resultado['frases'])} frases"
            print(f"  [{t:5.0f} s]   {dato.tipo} {dato.herramienta or ''} "
                  f"{json.dumps(dato.argumentos, ensure_ascii=False)[:60] if dato.argumentos else ''} {extra}", flush=True)

    try:
        r = analizar_texto(caso.cv, caso.texto, caso.indicios, vac, cliente, al_evento=en_vivo)
    except Exception as e:  # un CV que falla no detiene el banco: queda registrado (fail-closed)
        print(f"  ✗ {type(e).__name__}: {e}")
        comparaciones.append(Comparacion(cv_id, m["esperado"]["decision"], "error", m["esperado"]["requisitos_fallidos"],
                                         [], m["esperado"]["meses_efectivos"], -1, m["esperado"]["debe_marcar"],
                                         motivos=[f"{type(e).__name__}: {e}"]))
        continue

    exp = experiencia(caso)
    hay_iny = bool(caso.indicios)
    veredicto = auditar(r.ficha, caso, vac)
    dec, motivos = decision_provisional(r.ficha, vac, exp, veredicto.resultado.value == "bloquea")
    comp = Comparacion(cv_id, m["esperado"]["decision"], dec, m["esperado"]["requisitos_fallidos"],
                       fallidos_del_analista(r.ficha), m["esperado"]["meses_efectivos"],
                       exp["total_meses_sin_solapes"], m["esperado"]["debe_marcar"],
                       ["inyeccion"] if hay_iny else [], motivos)
    comparaciones.append(comp)

    f = r.ficha
    print(f"  Ficha: fit={f.fit} cobertura={f.cobertura_evidencia} · {r.agente.pasos} pasos · {r.segundos:.0f} s")
    for e in f.evaluaciones:
        print(f"    {e.id_requisito} {'(oblig.)' if e.obligatorio else '        '} {e.cumplimiento.value:<14}"
              f"{'«' + e.citas[0].texto[:70] + '»' if e.citas else ''}{' ✗' * len(e.citas_rechazadas)}")
        for extra in e.citas[1:]:
            print(f"    {'':<24}«{extra.texto[:70]}»")
    print(f"  Auditor: {veredicto.resultado.value.upper()}")
    for h in veredicto.hallazgos:
        print(f"    {'🔴' if h.severidad.value == 'bloqueante' else '🟡'} {h.tipo.value:<26}{h.id_requisito or '':<8}{h.detalle or ''}")
    print(f"  Decisión provisional: {dec}  ·  esperada: {comp.decision_esperada}  "
          f"{'✓' if comp.acierta_decision else '✗'}")
    print(f"  Obligatorios no_cumple (analista): {comp.fallidos_analista} · esperados: {comp.fallidos_esperados} "
          f"{'✓' if comp.acierta_fallidos else '✗'}")
    for mo in motivos:
        print(f"    · {mo}")
    (SALIDA / f"{cv_id}.json").write_text(json.dumps({
        "ficha": f.model_dump(mode="json"), "indicios": [asdict(i) for i in caso.indicios],
        "proxies": [asdict(p) for p in caso.proxies], "traza": [asdict(e) for e in r.agente.traza],
        "veredicto": veredicto.model_dump(mode="json"),
        "comparacion": {**asdict(comp), "acierta_decision": comp.acierta_decision,
                        "acierta_fallidos": comp.acierta_fallidos},
    }, ensure_ascii=False, indent=2, default=str), "utf-8")

# ------------------------------------------------------------------ resumen
validos = [c for c in comparaciones if c.decision_esperada != "duplicado"]
print("\n" + "=" * 78)
print(f"{'CV':<8}{'esperada':<17}{'provisional':<17}{'decisión':<10}{'fallidos':<10}inyección")
for c in comparaciones:
    if c.decision_esperada == "duplicado":
        print(f"{c.cv_id:<8}{'duplicado':<17}{'(R12: lo resuelve el workflow, no el analista)'}")
        continue
    print(f"{c.cv_id:<8}{c.decision_esperada:<17}{c.decision_provisional:<17}"
          f"{'✓' if c.acierta_decision else '✗':<10}{'✓' if c.acierta_fallidos else '✗':<10}"
          f"{'✓' if c.acierta_marcas else '✗'}")
if validos:
    n = len(validos)
    print(f"\nDecisión: {sum(c.acierta_decision for c in validos)}/{n} · "
          f"Fallidos del analista: {sum(c.acierta_fallidos for c in validos)}/{n} · "
          f"Inyección: {sum(c.acierta_marcas for c in validos)}/{n}")
    print("Nota: 'Ningún no_apto en el Top 5' y 'trampas a revisión' son los criterios de aceptación del repo (3.3).")
    resumen = [{**asdict(c), "acierta_decision": c.acierta_decision, "acierta_fallidos": c.acierta_fallidos}
               for c in comparaciones]
    nombre = "resumen_todos.json" if args[0] == "todos" else f"resumen_{'_'.join(ids)}.json"
    (SALIDA / nombre).write_text(json.dumps({"modelo": cliente.config.etiqueta, "resultados": resumen},
                                            ensure_ascii=False, indent=2), "utf-8")
    print(f"Guardado en resultados/rol3/{nombre}")
