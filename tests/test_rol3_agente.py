"""Rol 3 · cliente LLM y motor de agente, con un LLM falso (sin red ni modelo)."""
import json
import urllib.error

import pytest

from cvagent.agentes.agente import AgenteSinResultado, ejecutar_agente, esquema_plano
from cvagent.agentes.llm import ClienteLLM, ConfigLLM, ErrorLLM
from cvagent.agentes.salida import FichaLLM
from rol3_comun import LLMFalso, contexto, llamar

CONFIG = ConfigLLM(base_url="http://falso/v1", modelo="falso", reintentos=0)
CITA = "Consultas SQL avanzadas en PostgreSQL y tableros en Power BI"
FICHA_OK = {"evaluaciones": [{"id_requisito": "REQ-02", "cumplimiento": "cumple", "citas": [CITA]}]}


def correr(guion, allowlist=("buscar_en_cv",), max_pasos=6):
    falso = LLMFalso(guion)
    cliente = ClienteLLM(CONFIG, transporte=falso)
    res = ejecutar_agente(nombre="analista", cliente=cliente, instrucciones="sys", tarea="tarea",
                          allowlist=list(allowlist), contexto=contexto("CV-001"),
                          esquema_salida=FichaLLM, max_pasos=max_pasos)
    return res, falso, cliente


def test_usa_herramienta_observa_y_entrega():
    res, falso, cliente = correr([llamar("buscar_en_cv", {"texto": CITA}), llamar("entregar_resultado", FICHA_OK)])
    assert [e.tipo for e in res.traza] == ["llamada", "entrega"] and res.traza[0].resultado["encontrada"]
    assert {t["function"]["name"] for t in falso.recibidos[0]["tools"]} == {"buscar_en_cv", "entregar_resultado"}
    assert json.loads(falso.recibidos[1]["messages"][-1]["content"])["encontrada"] is True
    assert cliente.uso.llamadas == 2


def test_herramienta_fuera_de_allowlist_no_se_ejecuta():
    res, falso, _ = correr([llamar("experiencia_por_cargo", {}), llamar("entregar_resultado", FICHA_OK)])
    assert res.traza[0].tipo == "rechazo"
    assert "no está permitida" in json.loads(falso.recibidos[1]["messages"][-1]["content"])["error"]


def test_resultado_invalido_vuelve_para_corregir():
    malo = {"evaluaciones": [{"id_requisito": "REQ-02", "cumplimiento": "excelente", "citas": [CITA]}]}
    res, falso, _ = correr([llamar("entregar_resultado", malo), llamar("entregar_resultado", FICHA_OK)])
    assert [e.tipo for e in res.traza] == ["resultado_invalido", "entrega"]


def test_texto_libre_recibe_un_empujon():
    res, _, _ = correr([{"role": "assistant", "content": "Creo que cumple."}, llamar("entregar_resultado", FICHA_OK)])
    assert res.traza[0].tipo == "texto_sin_herramienta"


def test_sin_entrega_falla_explicitamente():
    with pytest.raises(AgenteSinResultado):
        correr([llamar("buscar_en_cv", {"texto": f"SQL {i}"}) for i in range(3)], max_pasos=3)


def test_allowlist_con_herramienta_inexistente():
    with pytest.raises(ValueError):
        correr([], allowlist=["borrar_base_de_datos"])


def test_argumentos_como_dict_estilo_ollama():
    res, _, _ = correr([{"role": "assistant", "tool_calls": [{"function": {"name": "entregar_resultado", "arguments": FICHA_OK}}]}])
    assert res.pasos == 1


def test_config_desde_entorno(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1/")
    monkeypatch.setenv("LLM_MODELO", "qwen2.5:7b")
    monkeypatch.setenv("LLM_MAX_TOKENS", "2000")
    c = ConfigLLM.desde_entorno()
    assert c.etiqueta == "qwen2.5:7b@host.docker.internal:11434" and c.max_tokens == 2000


def test_config_incompleta(monkeypatch):
    monkeypatch.delenv("LLM_MODELO", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://x/v1")
    with pytest.raises(ErrorLLM):
        ConfigLLM.desde_entorno()


def test_error_de_red_y_timeout():
    def caido(*a):
        raise urllib.error.URLError("conexión rechazada")
    with pytest.raises(ErrorLLM, match="Sin respuesta"):
        ClienteLLM(CONFIG, transporte=caido).chat([{"role": "user", "content": "hola"}])
    n = []
    def lento(*a):
        n.append(1)
        raise TimeoutError("timed out")
    with pytest.raises(ErrorLLM, match="tardó más de"):
        ClienteLLM(ConfigLLM("http://f/v1", "f", reintentos=2), transporte=lento).chat([{"role": "user", "content": "x"}])
    assert len(n) == 1          # un timeout no se reintenta


def test_tope_de_tokens_y_corte_por_longitud():
    def corta(url, payload, headers, timeout):
        assert payload["max_tokens"] == 1500
        return {"choices": [{"message": {"role": "assistant", "content": "bla"}, "finish_reason": "length"}]}
    assert ClienteLLM(CONFIG, transporte=corta).chat([{"role": "user", "content": "x"}])["_corte_por_longitud"]


def test_esquema_plano_sin_referencias():
    assert "$ref" not in json.dumps(esquema_plano(FichaLLM))
