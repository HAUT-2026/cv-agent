"""
Cliente LLM agnóstico del proveedor.

Habla el protocolo de chat de OpenAI (`/v1/chat/completions` con `tools`), que hoy
exponen OpenAI, Ollama, Gemini, DeepSeek, Groq, LM Studio, vLLM y otros. Cambiar de
modelo es cambiar el `.env`, no el código:

    LLM_BASE_URL   p. ej. http://host.docker.internal:11434/v1   (Ollama)
                         https://api.openai.com/v1                (OpenAI)
    LLM_MODELO     p. ej. qwen2.5:7b
    LLM_API_KEY    Ollama no la valida; para APIs pagas es obligatoria
    LLM_TEMPERATURA  por defecto 0 (lo más reproducible posible)
    LLM_TIMEOUT      segundos por llamada; por defecto 300 (los modelos locales son lentos)
    LLM_MAX_TOKENS   tope de tokens de salida por llamada; por defecto 1500. Evita que un
                     modelo pequeño entre en bucle repitiendo texto hasta llenar el contexto

Sin dependencias externas: usa urllib de la librería estándar. El transporte se
puede inyectar, así las pruebas no necesitan red ni modelo.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

Transporte = Callable[[str, dict, dict, float], dict]


class ErrorLLM(RuntimeError):
    """Fallo de comunicación con el proveedor (después de los reintentos)."""


@dataclass(frozen=True)
class ConfigLLM:
    base_url: str
    modelo: str
    api_key: str = "sin-clave"
    temperatura: float = 0.0
    timeout: float = 300.0
    reintentos: int = 2
    max_tokens: int = 1500

    @property
    def etiqueta(self) -> str:
        """Lo que va al decision_log: qué modelo decidió."""
        host = self.base_url.split("//")[-1].split("/")[0]
        return f"{self.modelo}@{host}"

    @classmethod
    def desde_entorno(cls) -> "ConfigLLM":
        faltan = [v for v in ("LLM_BASE_URL", "LLM_MODELO") if not os.environ.get(v)]
        if faltan:
            raise ErrorLLM(f"Faltan variables de entorno: {', '.join(faltan)}. Revisa tu .env")
        return cls(
            base_url=os.environ["LLM_BASE_URL"].rstrip("/"),
            modelo=os.environ["LLM_MODELO"],
            api_key=os.environ.get("LLM_API_KEY", "sin-clave"),
            temperatura=float(os.environ.get("LLM_TEMPERATURA", "0")),
            timeout=float(os.environ.get("LLM_TIMEOUT", "300")),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "1500")),
        )


def _transporte_http(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@dataclass
class Uso:
    llamadas: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    segundos: float = 0.0


@dataclass
class ClienteLLM:
    config: ConfigLLM
    transporte: Transporte = field(default=_transporte_http)
    uso: Uso = field(default_factory=Uso)

    def chat(self, mensajes: list[dict], herramientas: Optional[list[dict]] = None) -> dict:
        """Envía la conversación y devuelve el `message` de la primera opción."""
        payload: dict = {
            "model": self.config.modelo,
            "messages": mensajes,
            "temperature": self.config.temperatura,
            "max_tokens": self.config.max_tokens,
        }
        if herramientas:
            payload["tools"] = herramientas
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.config.api_key}"}
        url = f"{self.config.base_url}/chat/completions"

        ultimo_error: Optional[Exception] = None
        for intento in range(self.config.reintentos + 1):
            t0 = time.monotonic()
            try:
                resp = self.transporte(url, payload, headers, self.config.timeout)
            except urllib.error.HTTPError as e:
                cuerpo = e.read().decode("utf-8", "replace")[:500] if hasattr(e, "read") else ""
                if 400 <= e.code < 500 and e.code != 429:
                    # error del pedido (modelo inexistente, clave inválida...): reintentar no sirve
                    raise ErrorLLM(f"HTTP {e.code} del proveedor: {cuerpo}") from e
                ultimo_error = e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                razon = getattr(e, "reason", e)
                if isinstance(e, TimeoutError) or isinstance(razon, TimeoutError) or "timed out" in str(razon):
                    # Lentitud, no falla de red: reenviar lo mismo solo gasta otro timeout entero.
                    raise ErrorLLM(f"{self.config.etiqueta} tardó más de {self.config.timeout:.0f} s en una "
                                   "sola respuesta. Posible bucle de generación o modelo demasiado lento "
                                   "para esta máquina; revisa LLM_MAX_TOKENS / LLM_TIMEOUT.") from e
                ultimo_error = e
            else:
                self._contabilizar(resp, time.monotonic() - t0)
                try:
                    opcion = resp["choices"][0]
                    msg = dict(opcion["message"])
                except (KeyError, IndexError, TypeError) as e:
                    raise ErrorLLM(f"Respuesta con forma inesperada: {str(resp)[:300]}") from e
                # "length" = se cortó por max_tokens: el agente lo verá y la traza lo registra
                msg["_corte_por_longitud"] = opcion.get("finish_reason") == "length"
                return msg
            if intento < self.config.reintentos:
                time.sleep(2 ** intento)  # 1 s, 2 s...
        raise ErrorLLM(f"Sin respuesta de {self.config.etiqueta} tras "
                       f"{self.config.reintentos + 1} intentos: {ultimo_error}")

    def _contabilizar(self, resp: dict, segundos: float) -> None:
        u = resp.get("usage") or {}
        self.uso.llamadas += 1
        self.uso.tokens_entrada += int(u.get("prompt_tokens", 0) or 0)
        self.uso.tokens_salida += int(u.get("completion_tokens", 0) or 0)
        self.uso.segundos += segundos
