"""Rol 3 · agente agendador: plantilla + franjas, sin acceso al CV (sin red ni modelo)."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from cvagent.agentes.agendador import (ALLOWLIST, AgendaInvalida, AgendadorRol3, Calendario, Plantillas,
                                       agendar, info_de_vacante, ref_opaca, verificar_propuesta)
from cvagent.agentes.llm import ClienteLLM, ConfigLLM
from cvagent.domain.contracts import PropuestaAgenda
from rol3_comun import DATA, LLMFalso, datos, llamar

TZ = timezone(timedelta(hours=-5))
AHORA = datetime(2026, 11, 13, 9, 0, tzinfo=TZ)                      # viernes
INFO = info_de_vacante(json.loads((DATA / "vacantes" / "vacante_v1.json").read_text("utf-8")))
TOP = ["CV-002", "CV-001", "CV-003", "CV-005", "CV-006", "CV-007"]   # staging simulado
REFS = [ref_opaca(c, "VAC-001") for c in TOP]
CAL, PL = Calendario.cargar(), Plantillas.cargar()
CLIENTE = lambda falso: ClienteLLM(ConfigLLM("http://f/v1", "falso", reintentos=0), falso)  # noqa: E731


def libres(dur=60):
    return [f["id"] for f in CAL.franjas_libres(dur, AHORA)]


def entrega(pares, plantilla="tecnica_virtual"):
    return llamar("entregar_resultado", {"asignaciones": [
        {"candidato_ref": r, "plantilla_id": plantilla, "franja_id": f} for r, f in pares]})


# ------------------------------------------------------------------ calendario y plantillas
def test_franjas_respetan_festivo_anticipacion_almuerzo_y_ocupados():
    fr = CAL.franjas_libres(60, AHORA)
    assert fr and all(f["inicio"] >= AHORA + timedelta(hours=24) for f in fr)
    assert not any(f["inicio"].date().isoformat() == "2026-11-16" for f in fr)          # festivo
    assert all(f["inicio"].weekday() < 5 for f in fr)
    assert not any(f["inicio"].hour == 12 or (f["inicio"].hour == 11 and f["inicio"].minute == 30) for f in fr)
    assert "F-20261117-0900" not in libres()                                             # ENT-1 ocupado


def test_consultar_franjas_ofrece_franjas_sin_cruces():
    """12-nov: ofrecía 10:00, 10:30 y 11:00 de 60 min; «a cada uno la siguiente» se cruzaba
    (un LLM falso así terminó en fail-closed). Ahora cualquier elección distinta es válida."""
    from cvagent.agentes.agendador import ContextoAgenda, REGISTRO_AGENDA
    ctx = ContextoAgenda(INFO, REFS, "tecnica", CAL, PL, AHORA)
    fr = REGISTRO_AGENDA["consultar_franjas"].funcion({"duracion_min": 60}, ctx)["franjas"]
    ids = [f["id"] for f in fr]
    falso = LLMFalso([entrega(zip(REFS, ids[:6]))])
    assert len(agendar(REFS, INFO, CLIENTE(falso), ahora=AHORA).propuestas) == 6


def test_plantilla_deja_el_marcador_y_rechaza_variables_no_permitidas():
    v = {"cargo": "X", "fecha": "f", "hora_inicio": "1", "hora_fin": "2", "duracion_min": 60, "ciudad": "Bogotá"}
    texto = PL.renderizar("tecnica_virtual", v)
    assert "{{nombre_de_pila}}" in texto and "{cargo}" not in texto
    with pytest.raises(ValueError):
        PL.renderizar("tecnica_virtual", {**v, "salario": "10"})


def test_ref_opaca_es_estable_y_no_revela_el_cv():
    assert ref_opaca("CV-002", "VAC-001") == REFS[0] and "CV" not in REFS[0] and len(set(REFS)) == 6


# ------------------------------------------------------------------ sin LLM (determinista)
def test_agenda_simple_cumple_el_contrato_del_rol_1():
    r = agendar(REFS, INFO, None, ahora=AHORA)
    assert len(r.propuestas) == 6 and all(isinstance(p, PropuestaAgenda) for p in r.propuestas)
    assert [p.candidato_ref for p in r.propuestas] == REFS
    intervalos = sorted(tuple(datetime.fromisoformat(x) for x in p.franja.split("/")) for p in r.propuestas)
    assert all(a[1] <= b[0] for a, b in zip(intervalos, intervalos[1:]))                # sin cruces
    assert all(verificar_propuesta(p, INFO) == [] for p in r.propuestas)
    assert r.propuestas[0].auditoria.componente == "rol-3-agendador"


@pytest.mark.parametrize("cv_id", TOP)
def test_el_mensaje_no_contiene_nada_del_cv(cv_id):
    """Separación de agentes (ADR-002): ni nombre, ni contacto, ni cv_id llegan al mensaje."""
    textos = " ".join(p.texto_exacto for p in agendar(REFS, INFO, None, ahora=AHORA).propuestas)
    for valor in datos(cv_id)["persona"].values():
        if isinstance(valor, str) and len(valor) > 3:
            assert valor not in textos
    assert cv_id not in textos


def test_texto_ajustado_a_mano_ya_no_es_el_aprobado():
    p = agendar(REFS[:1], INFO, None, ahora=AHORA).propuestas[0]
    alterado = p.model_copy(update={"texto_exacto": p.texto_exacto + "\nPD: trae tu salario esperado."})
    assert verificar_propuesta(alterado, INFO) == ["el texto no es idéntico a la plantilla aprobada"]


# ------------------------------------------------------------------ con LLM falso
def test_agente_feliz_y_allowlist_propia():
    l = libres()
    falso = LLMFalso([llamar("ver_plantillas", {}), llamar("consultar_franjas", {"duracion_min": 60}),
                      entrega(zip(REFS[:2], [l[0], l[1]]))])
    r = agendar(REFS[:2], INFO, CLIENTE(falso), ahora=AHORA)
    ofrecidas = {t["function"]["name"] for t in falso.recibidos[0]["tools"]}
    assert ofrecidas == set(ALLOWLIST) | {"entregar_resultado"}
    assert "buscar_en_cv" not in ofrecidas and "frases_relacionadas" not in ofrecidas
    assert [p.candidato_ref for p in r.propuestas] == REFS[:2] and r.propuestas[0].auditoria.modelo_version == "falso@f"
    assert "CV-" not in json.dumps(falso.recibidos[0], ensure_ascii=False)              # tarea sin cv_id


def test_pedir_una_herramienta_del_cv_se_rechaza():
    l = libres()
    falso = LLMFalso([llamar("buscar_en_cv", {"texto": "Java"}), entrega(zip(REFS[:1], l[:1]))])
    r = agendar(REFS[:1], INFO, CLIENTE(falso), ahora=AHORA)
    assert r.agente.traza[0].tipo == "rechazo"


def test_baranda_rechaza_cruces_festivos_y_plantilla_equivocada_y_el_agente_corrige():
    l = libres()
    malo = llamar("entregar_resultado", {"asignaciones": [
        {"candidato_ref": REFS[0], "plantilla_id": "tecnica_virtual", "franja_id": l[0]},
        {"candidato_ref": REFS[1], "plantilla_id": "tecnica_virtual", "franja_id": l[0]},            # cruce
        {"candidato_ref": REFS[2], "plantilla_id": "tecnica_virtual", "franja_id": "F-20261116-0900"},  # festivo
        {"candidato_ref": REFS[3], "plantilla_id": "conversacion_inicial_virtual", "franja_id": l[3]}]})  # tipo
    falso = LLMFalso([malo, entrega(zip(REFS[:4], [l[0], l[1], l[3], l[5]]))])
    r = agendar(REFS[:4], INFO, CLIENTE(falso), ahora=AHORA)
    rechazo = next(t for t in r.agente.traza if t.tipo == "entrega_incompleta").resultado
    texto = " ".join(rechazo)
    assert "se cruza" in texto and "festivo" in texto and "no sirve para una entrevista 'tecnica'" in texto
    assert l[1] in texto                                         # el rechazo trae las opciones válidas
    assert len(r.propuestas) == 4


def test_falta_un_candidato_se_rechaza():
    l = libres()
    falso = LLMFalso([entrega(zip(REFS[:1], l[:1])), entrega(zip(REFS[:2], l[:2]))])
    r = agendar(REFS[:2], INFO, CLIENTE(falso), ahora=AHORA)
    assert any("falta asignarle" in p for p in next(t for t in r.agente.traza if t.tipo == "entrega_incompleta").resultado)


def test_corrida_real_vista_previa_por_candidato_agota_pasos_y_falla_cerrado():
    """12-nov con qwen2.5:7b: eligió bien plantilla y franjas, pero llamó vista_previa una vez por
    candidato en turnos separados y agotó los pasos. Ahora vista_previa no es herramienta del agente
    (se rechaza) y agotar los pasos es AgendaInvalida, no un traceback."""
    l = libres()
    guion = [llamar("ver_plantillas", {}), llamar("consultar_franjas", {"duracion_min": 60})] + \
            [llamar("vista_previa", {"franja_id": f, "plantilla_id": "tecnica_virtual"}) for f in l[:6]]
    falso = LLMFalso(guion)
    with pytest.raises(AgendaInvalida, match="no entregó"):
        agendar(REFS, INFO, CLIENTE(falso), ahora=AHORA)
    assert "vista_previa" not in ALLOWLIST


def test_agente_terco_falla_cerrado():
    """Tras 3 rechazos el motor acepta, pero agendar() vuelve a validar y no entrega nada:
    el caso queda para un humano (fail-closed), nunca un mensaje con una franja inválida."""
    malo = entrega([(REFS[0], "F-20261116-0900")])
    falso = LLMFalso([malo] * 4)
    with pytest.raises(AgendaInvalida):
        agendar(REFS[:1], INFO, CLIENTE(falso), ahora=AHORA)


# ------------------------------------------------------------------ adaptador para el grafo del Rol 1
def test_adaptador_cumple_agendadorport():
    state = SimpleNamespace(correlation_id=str(uuid.uuid4()))
    propuesta = SimpleNamespace(candidatos_ref=REFS[:3])
    ag = AgendadorRol3(INFO)
    p = ag.proponer(state, propuesta, now=AHORA)
    assert isinstance(p, PropuestaAgenda) and p.correlation_id == state.correlation_id
    assert p.candidato_ref == REFS[0] and len(ag.ultimas) == 3
