"""Rol 3 · mide cuántas citas del Rol 3 se pueden re-anclar en el texto canónico del portal (Rol 4).

Solo lee: no modifica nada ni llama a ningún LLM. Sirve para decidir cómo integrar los agentes del
Rol 3 al portal antes de escribir el adaptador.

Por qué hace falta: el Rol 3 cita sobre su texto canónico (construido desde el JSON); el portal
exige que cada cita cumpla `texto_portal[inicio:fin] == cita` sobre SU texto (extraído del PDF con
pdfplumber). Son textos distintos, así que cada cita del Rol 3 hay que volver a ubicarla.

Estrategias que se miden, de la más estricta a la más flexible:
  exacta    `portal.texto.anclar`: la frase aparece una sola vez, tal cual
  ampliada  `portal.texto.anclar_ampliando`: si se repite, se toma su línea completa
  espacios  la frase con cualquier espacio en blanco entre palabras (el PDF parte líneas)

Fuentes de citas:
  léxica    `ficha_lexica` (analista simulado) sobre todos los evaluables
  LLM       fichas guardadas en resultados/rol3/<cv>.json (generadas antes con el LLM real)

Uso (raíz del repo, en Docker):
  docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh -c
      "pip install -q -e '.[portal]' && python scripts/rol3/medir_reanclaje.py"
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from reglas import cargar_diccionario, procesar_lote  # noqa: E402
from reglas import cargar_vacante as cargar_vacante_rol2  # noqa: E402

from cvagent.agentes.criterios import cargar_vacante  # noqa: E402
from cvagent.agentes.cv_json import preparar_caso  # noqa: E402
from cvagent.agentes.evaluacion import ficha_lexica  # noqa: E402
from portal.texto import TextoNoDisponible, anclar, anclar_ampliando, cargar_texto  # noqa: E402

D = RAIZ / "data"
CACHE = RAIZ / "resultados" / "rol3"


def rutas_json() -> dict[str, Path]:
    """Mismo orden y mismas carpetas que usa el portal (`ServicioLote.cargar`)."""
    rutas = sorted((D / "cvs_json").glob("*.json")) + sorted((D / "extras_inyeccion" / "cvs_json").glob("*.json"))
    return {p.stem: p for p in rutas}


def anclar_espacios(texto: str, cita: str):
    palabras = cita.split()
    if not palabras:
        return None
    patron = r"\s+".join(re.escape(p) for p in palabras)
    hallados = list(re.finditer(patron, texto))
    if len(hallados) != 1:
        return None
    return hallados[0].start(), hallados[0].end()


def estrategia(texto_portal: str, cita: str) -> str:
    if anclar(texto_portal, cita):
        return "exacta"
    if anclar_ampliando(texto_portal, cita):
        return "ampliada"
    if anclar_espacios(texto_portal, cita):
        return "espacios"
    return "falla"


def medir(nombre: str, fichas: dict[str, list[str]], textos: dict[str, str]) -> None:
    total = {"exacta": 0, "ampliada": 0, "espacios": 0, "falla": 0}
    sin_ninguna = []
    fallas = []
    for cv_id, citas in fichas.items():
        ancladas = 0
        for cita in citas:
            e = estrategia(textos[cv_id], cita)
            total[e] += 1
            if e != "falla":
                ancladas += 1
            else:
                fallas.append((cv_id, cita))
        if citas and ancladas == 0:
            sin_ninguna.append(cv_id)
    n = sum(total.values())
    print(f"\n== {nombre}: {len(fichas)} CV, {n} citas")
    for k, v in total.items():
        print(f"   {k:<9}{v:>4}  ({(v / n if n else 0):.0%})")
    print(f"   CV sin ninguna cita anclada: {len(sin_ninguna)} {sin_ninguna}")
    for cv_id, cita in fallas[:15]:
        print(f"   falla {cv_id}: {cita[:90]!r}")
    if len(fallas) > 15:
        print(f"   … y {len(fallas) - 15} fallas más")


def main() -> None:
    rutas = rutas_json()
    fichas_rol2 = [json.loads(p.read_text("utf-8")) for p in rutas.values()]
    vac_rol2 = cargar_vacante_rol2(str(D), "VAC-001", None)
    dic = cargar_diccionario(str(D / "diccionario_equivalencias.json"))
    resultados = procesar_lote(fichas_rol2, vac_rol2, dic)
    evaluables = [cv for cv in rutas if resultados[cv].get("ruta") == "evaluable"]
    vac = cargar_vacante(D, "VAC-001", vac_rol2["version"])

    textos, procedencias = {}, {}
    for cv_id in evaluables:
        try:
            textos[cv_id], procedencias[cv_id] = cargar_texto(cv_id, D)
        except TextoNoDisponible:
            print(f"{cv_id}: sin texto en el portal (no se mide)")
    print(f"Evaluables según el portal: {len(evaluables)} · procedencia: "
          f"{sum(p == 'pdf' for p in procedencias.values())} pdf, "
          f"{sum(p != 'pdf' for p in procedencias.values())} gemelo_json")

    lexicas = {}
    for cv_id in textos:
        caso = preparar_caso(rutas[cv_id])
        evs, construir = ficha_lexica(caso, vac)
        ficha = construir(evs)
        lexicas[cv_id] = [c.texto for e in ficha.evaluaciones for c in e.citas]
    medir("Analista léxico (simulado)", lexicas, textos)

    llm = {}
    for cv_id in textos:
        ruta = CACHE / f"{cv_id}.json"
        if ruta.exists():
            ficha = json.loads(ruta.read_text("utf-8"))["ficha"]
            llm[cv_id] = [c["texto"] for e in ficha["evaluaciones"] for c in e["citas"]]
    if llm:
        medir("Analista LLM (caché en resultados/rol3)", llm, textos)
    else:
        print("\n(no hay fichas de LLM en resultados/rol3)")


if __name__ == "__main__":
    main()
