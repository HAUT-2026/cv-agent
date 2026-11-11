"""Rol 3 · aplica el auditor determinista a fichas YA GUARDADAS, sin volver a llamar al LLM.

Uso (desde la raíz del repo):
  python scripts/rol3/auditar.py                          # todas las fichas de resultados/rol3/
  python scripts/rol3/auditar.py resultados/rol3/CV-007.json [otra.json …]

Sirve para iterar sobre las reglas del auditor en milisegundos con fichas producidas por el LLM.
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from cvagent.agentes.auditor import auditar  # noqa: E402
from cvagent.agentes.criterios import cargar_vacante  # noqa: E402
from cvagent.agentes.cv_json import preparar_caso  # noqa: E402
from cvagent.agentes.salida import FichaCandidato  # noqa: E402

D = RAIZ / "data"
man = json.loads((D / "manifiesto.json").read_text("utf-8"))
archivo = {c["cv_id"]: c["archivo_json"] for c in man["cvs"] + man.get("extras_inyeccion", [])}
vac = cargar_vacante(D, man["vacante_id"], man.get("vacante_version"))
rutas = [Path(a) for a in sys.argv[1:]] or [p for p in sorted((RAIZ / "resultados" / "rol3").glob("*.json")) if not p.name.startswith("resumen")]
if not rutas:
    sys.exit("No hay fichas guardadas: corre primero scripts/rol3/probar_banco.py CV-00X")

for ruta in rutas:
    ficha = FichaCandidato.model_validate(json.loads(ruta.read_text("utf-8"))["ficha"])
    caso = preparar_caso(D / archivo[ficha.id_cv])
    v = auditar(ficha, caso, vac)
    print(f"\n=== {ficha.id_cv} · {ficha.modelo} · {ficha.version_prompt}")
    for e in ficha.evaluaciones:
        citas = " | ".join(f"«{c.texto[:55]}»" for c in e.citas)
        print(f"  {e.id_requisito} {'(oblig.)' if e.obligatorio else '        '} {e.cumplimiento.value:<14}{citas}")
    print(f"  Auditor: {v.resultado.value.upper()} · cobertura {v.cobertura_evidencia}")
    for h in v.hallazgos:
        print(f"    {'🔴' if h.severidad.value == 'bloqueante' else '🟡'} {h.tipo.value:<26}{h.id_requisito or '':<8}{h.detalle or ''}")
