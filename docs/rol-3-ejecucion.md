# Rol 3 · Guía paso a paso para ejecutarlo en tu máquina

Esta guía te lleva desde cero hasta ver a los agentes del Rol 3 (analista y auditor) evaluando hojas de vida. Son los mismos pasos que se siguieron al construirlo, incluidos los tropiezos, para que no tengas que descubrirlos.

> **Si eres una IA ayudando a alguien con esto**, lee además [`cvagent/agentes/AGENTS.md`](../cvagent/agentes/AGENTS.md): tiene el mismo recorrido en forma de lista de verificación y un árbol de errores.

## Mapa: qué vas a lograr

| Paso | Qué haces | ¿Necesita LLM? | Tiempo |
|---|---|---|---|
| 1-3 | Instalar lo básico, traer el código y comprobar Docker | No | 10-20 min (una vez) |
| 4 | Correr las **486 pruebas** (Rol 2 + Rol 3) | No | 1 min |
| 5 | Correr el **banco sin LLM**: los 44 CV por el motor de reglas y la sanitización | No | 1 min |
| 6-7 | Preparar Ollama y el archivo `.env` | Sí | 15-30 min (una vez; la descarga del modelo pesa 4,7 GB) |
| 8 | Ver al **analista** (LLM) y al **auditor** evaluar un CV | Sí | 3-5 min por CV en un portátil |
| 9 | Re-auditar fichas guardadas sin volver a llamar al LLM | No | segundos |

Los pasos 1 a 5 ya demuestran casi todo: el flujo de punta a punta, la detección de inyección y la verificación de citas. El LLM solo se necesita para ver al analista juzgar la evidencia.

**Cómo leer los comandos:** están escritos para **Windows con PowerShell**. Si usas macOS o Linux, cambia `${PWD}` por `$(pwd)`; en Linux, además, mira la nota del paso 6.

---

## Paso 1 · Instalar lo básico

| Herramienta | Para qué | Cómo comprobar que quedó |
|---|---|---|
| [Git](https://git-scm.com/downloads) | Traer el código | `git --version` |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Correr Python sin instalarlo ni ensuciar tu equipo | `docker --version` |
| [Ollama](https://ollama.com/download) *(solo para los pasos 6-8)* | Correr el LLM en tu máquina, gratis y sin enviar datos afuera | `ollama --version` |

**Hardware para el LLM local:** 16 GB de RAM recomendados. La GPU es opcional: con una GTX 1650 de 4 GB, el modelo corre 42 % en GPU y 58 % en CPU, y tarda unos 4 minutos por CV. Sin GPU funciona, pero más lento.

> **¿Por qué Docker y no Python directo?** Porque así todos usan la misma versión (3.12) sin instalar nada más. Si ya tienes Python 3.11+ y prefieres no usar Docker, mira el [anexo](#anexo-sin-docker).

## Paso 2 · Traer el código

```powershell
git clone https://github.com/HAUT-2026/cv-agent.git
cd cv-agent
git checkout feature/rol-3-agentes     # solo mientras el PR del Rol 3 no esté en main
```

**Qué esperar:** `Switched to a new branch 'feature/rol-3-agentes'`. Si dice `pathspec ... did not match`, corre `git fetch origin` y repite el checkout. Si el PR ya se fusionó, quédate en `main`.

Todos los comandos siguientes se corren **desde la carpeta `cv-agent`**.

## Paso 3 · Comprobar que Docker está encendido

```powershell
docker version
```

**Qué esperar:** dos bloques, `Client:` y `Server:`. Si solo sale `Client:` y luego un error como `error during connect ... dockerDesktopLinuxEngine`, **Docker Desktop no está abierto**: ábrelo, espera a que diga *Engine running* y repite.

## Paso 4 · Correr las pruebas (sin LLM, sin red)

```powershell
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic pytest pypdf && python -m pytest tests/test_reglas.py tests/test_dataset.py tests/test_rol3_agente.py tests/test_rol3_analista.py tests/test_rol3_auditor.py tests/test_rol3_citas.py tests/test_rol3_evaluacion.py tests/test_rol3_ficha.py tests/test_rol3_puntaje.py tests/test_rol3_sanitizacion.py"
```

**Qué hace cada parte:**

| Parte | Significado |
|---|---|
| `docker run --rm` | Crea un contenedor temporal y lo borra al terminar |
| `-v "${PWD}:/app"` | Monta tu carpeta actual dentro del contenedor, en `/app` |
| `-w /app` | Hace que el contenedor trabaje en esa carpeta |
| `python:3.12-slim` | Imagen oficial y liviana de Python. La primera vez se descarga (~50 MB) |
| `pip install -q pydantic pytest pypdf` | Lo único que se necesita. `pypdf` es para las pruebas del Rol 2 que leen los PDF |
| `python -m pytest ...` | Corre las pruebas del Rol 2 (`test_reglas`, `test_dataset`) y las 7 del Rol 3 |

**Qué esperar:** filas de puntos y, al final, `486 passed`. Son 132 del Rol 2 y 354 del Rol 3. Un `F` es una prueba fallida y un `E` un error: copia el mensaje y repórtalo.

> No corras `pytest` a secas: también recogería las pruebas del Rol 1, que necesitan LangGraph (`pip install -e .`). Por eso se listan los archivos.

## Paso 5 · Banco de punta a punta sin LLM

```powershell
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic && python scripts/rol3/probar_banco.py --sin-llm"
```

Pasa los 40 CV del dataset y los 4 CV extra de inyección por el flujo real: primero el **motor de reglas del Rol 2** (duplicados, consentimiento, formato, requisitos excluyentes, experiencia efectiva y anonimización) y, si el CV queda «evaluable», por la **sanitización del Rol 3**. Luego compara cada resultado con las respuestas correctas de `data/manifiesto.json`.

**Qué esperar** (extracto):

```
CV      motor (esperado)                      ruta final (esperada)               meses    inyección
CV-001  evaluable (evaluable) ✓               ranking (ranking) ✓                 72       -
CV-026  no_apto_declarado (no_apto_declarado) ✓no_apto_declarado (no_apto_declarado) ✓14       -
CV-040  evaluable (evaluable) ✓               bandeja (bandeja) ✓                 56       ignorar_instrucciones, texto_oculto
INJ-04  evaluable (evaluable) ✓               bandeja (bandeja) ✓                 46       dirigido_al_sistema, ignorar_instrucciones, ocultar_instruccion, pedir_puntaje

Ruta del motor (Rol 2): 44/44 · Ruta final de punta a punta (Rol 2 + Rol 3): 44/44 · Meses R11: 41/41
```

**Cómo leerlo:**
- **motor**: la ruta que decide el Rol 2. Solo `evaluable` pasa a los agentes.
- **ruta final**: lo que ve el reclutador. `ranking` significa que el CV entra a la lista; `bandeja`, que va a revisión humana. CV-040 pasa las reglas, pero esconde texto blanco sobre blanco con una orden para la IA. El motor no puede verlo; la sanitización del Rol 3 sí, y lo manda a la bandeja.
- **meses**: la experiencia efectiva (R11), sin contar dos veces los empleos solapados.
- **inyección**: los patrones detectados, con su posición exacta en el texto para que el reclutador los vea resaltados.

Al final aparece el **staging simulado**: el Top 5 que saldría con la rúbrica provisional (`docs/rol-3-puntaje.md`), usando un analista *simulado* por reglas de palabras (no el LLM), y pasándolo por `armar_staging` del Rol 2:

```
pos  CV      puntaje  cobertura  grupo (manifiesto)
1    CV-002  0.9062   1.0        apto
...
6    CV-007  0.7812   0.875      apto
  R5: diferencia 5.º–6.º = 0.0 ≤ 0,02 → se presentan seis
  R4 → revisión humana (cobertura < 0,70 o contradicción), fuera del Top automático: CV-011 (0.5), …
```

Se espera que el Top tenga **solo aptos**, que se activen R5 (empate → seis) y R4 (los 13 «parciales» a revisión humana), y que CV-006 y CV-007 (par contrafactual mujer/hombre) tengan el mismo puntaje.

## Paso 6 · Preparar Ollama (solo para ver al LLM)

**6.1 Descargar el modelo.** En una terminal normal, fuera de Docker:

```powershell
ollama pull qwen2.5:7b
ollama show qwen2.5:7b
```

En `Capabilities` debe aparecer **`tools`**. Los agentes funcionan llamando herramientas: un modelo sin `tools` (por ejemplo `gemma3`) responde `HTTP 400 ... does not support tools`.

**6.2 Dos variables de entorno de Ollama.** Esto fue lo que más costó descubrir:

| Variable | Valor | Por qué |
|---|---|---|
| `OLLAMA_HOST` | `0.0.0.0` | Por defecto Ollama solo escucha a tu propio equipo, y el contenedor de Docker cuenta como «otra máquina». Sin esto, el error es `Connection refused` |
| `OLLAMA_CONTEXT_LENGTH` | `8192` | Las instrucciones, el CV y los resultados de las herramientas no caben en el contexto por defecto. Sin esto, el modelo «olvida» el principio y responde cosas sin sentido |

En PowerShell:

```powershell
setx OLLAMA_HOST 0.0.0.0
setx OLLAMA_CONTEXT_LENGTH 8192
```

Después **cierra Ollama por completo** (clic derecho en el ícono de la bandeja → *Quit Ollama*) y ábrelo de nuevo. `setx` solo afecta a los programas que se abren después de ejecutarlo.

> macOS: `launchctl setenv OLLAMA_HOST 0.0.0.0` y `launchctl setenv OLLAMA_CONTEXT_LENGTH 8192`, y luego reinicia la app. Linux (systemd): `sudo systemctl edit ollama`, agrega `Environment="OLLAMA_HOST=0.0.0.0"` y `Environment="OLLAMA_CONTEXT_LENGTH=8192"`, y reinicia con `sudo systemctl restart ollama`.

**6.3 Comprobar que el contenedor llega a Ollama:**

```powershell
docker run --rm python:3.12-slim python -c "import urllib.request as u; print(u.urlopen('http://host.docker.internal:11434/api/tags').read()[:120])"
```

**Qué esperar:** algo como `b'{"models":[{"name":"qwen2.5:7b",...`. Si sale `Connection refused`, revisa el paso 6.2 y que Ollama esté abierto.

> **Linux:** `host.docker.internal` no existe por defecto. Agrega `--add-host=host.docker.internal:host-gateway` a **todos** los `docker run` que usan el LLM.

## Paso 7 · Crear el archivo `.env`

El `.env` le dice al código qué LLM usar. **Nunca se sube a git**: puede contener claves, y ya está en `.gitignore`.

```powershell
Copy-Item .env.example .env
notepad .env
```

Para Ollama, con el código corriendo en Docker, deja estas líneas:

```ini
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODELO=qwen2.5:7b
LLM_API_KEY=ollama
LLM_TEMPERATURA=0
LLM_TIMEOUT=600
LLM_MAX_TOKENS=2000
```

| Línea | Por qué ese valor |
|---|---|
| `host.docker.internal` | Así se llama tu equipo visto desde el contenedor. Si corres Python sin Docker, usa `localhost` |
| `LLM_API_KEY=ollama` | Ollama no pide clave, pero el protocolo exige enviar una |
| `LLM_TIMEOUT=600` | En un portátil, una respuesta puede tardar varios minutos. Un timeout no se reintenta, para no duplicar la espera |
| `LLM_MAX_TOKENS=2000` | La ficha de 10 requisitos ocupa unos 1500 tokens. Con 1000, la respuesta se cortaba a la mitad |

**¿Otro proveedor?** El cliente habla el protocolo de OpenAI, así que sirve para OpenAI, Gemini, DeepSeek, Groq, LM Studio o vLLM. Solo cambias `LLM_BASE_URL`, `LLM_MODELO` y `LLM_API_KEY`. La clave va **solo** en tu `.env`: nunca en el chat, en el código ni en un commit.

## Paso 8 · Ver al analista y al auditor evaluar un CV

```powershell
docker run --rm -it -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic && python -u scripts/rol3/probar_banco.py CV-001"
```

Prueba también con `CV-040` (texto oculto), `INJ-04` (inyección en inglés) o `CV-014` (Kotlin, equivalente a Java). Puedes pasar varios separados por espacio.

**Qué vas a ver, en orden:**

1. **En vivo**, cada paso del agente: `paso 1: esperando al modelo…`, luego `llamada frases_relacionadas {"id_requisito": "REQ-02"} → 2 frases`, y así sucesivamente. En el primer turno, el agente pide evidencia con herramientas; en el segundo, juzga y entrega. Si aparece `entrega_incompleta`, es una baranda del motor funcionando, no un error: el modelo quiso entregar `sin_evidencia` en requisitos que no había buscado, el motor se lo rechazó con la lista de búsquedas pendientes, y el agente vuelve a buscar y a entregar.
2. **La ficha:** cada requisito con su estado (`cumple`, `parcial`, `no_cumple`, `sin_evidencia`) y las **citas literales** del CV. Al lado aparece `✓` o `✗ (esperado …)` frente al manifiesto. Una cita que el código no encuentra en el CV aparece como `✗ NO ENCONTRADA`: el modelo la inventó o la parafraseó.
3. **El auditor:** `SIN_OBJECIONES` o `BLOQUEA`, con hallazgos 🔴 (bloquean) y 🟡 (advierten).
4. **La ruta final** y si coincide con la esperada.
5. **El puntaje** (solo si va a ranking), con el valor de cada criterio, y al final el **staging** con los CV que corriste.

Todo queda guardado en `resultados/rol3/CV-001.json`: la ficha, el veredicto, los indicios y la traza completa del agente. Esa carpeta tampoco se sube a git.

**Cuánto tarda:** con `qwen2.5:7b` en un portátil, entre 3 y 5 minutos por CV. Si pides un CV que el motor saca del flujo (por ejemplo `CV-026`, no apto declarado), responde al instante. Es lo correcto: el analista nunca lo recibe.

> `todos` en lugar de un id corre los 44 CV. En un portátil eso son **horas**; úsalo con un proveedor rápido para la medición final (ADR-007).

## Paso 9 · Re-auditar sin volver a llamar al LLM

```powershell
docker run --rm -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q pydantic && python scripts/rol3/auditar.py"
```

Toma las fichas guardadas en `resultados/rol3/` y les aplica el auditor de nuevo, en milisegundos. Sirve para ajustar reglas del auditor sin esperar minutos por cada CV.

---

## Si algo falla

| Síntoma | Causa | Solución |
|---|---|---|
| `error during connect` / `cannot find the file specified` (Docker) | Docker Desktop cerrado | Ábrelo y espera a *Engine running* (paso 3) |
| `ModuleNotFoundError: No module named 'pydantic'` | Faltó el `pip install` dentro del comando | Copia el comando completo |
| `ModuleNotFoundError: No module named 'langgraph'` | Corriste `pytest` sin lista de archivos y recogió las pruebas del Rol 1 | Usa el comando del paso 4 |
| `Faltan variables de entorno: LLM_BASE_URL, LLM_MODELO` | No existe `.env`, no está en la raíz o tiene otro nombre (`.env.txt`) | Paso 7. En Windows, activa «Extensiones de nombre de archivo» para verlo |
| `Sin respuesta de ... Connection refused` | Ollama cerrado, `OLLAMA_HOST` sin configurar, o `localhost` dentro de Docker | Pasos 6.2, 6.3 y la línea `LLM_BASE_URL` |
| `HTTP 404 ... model "qwen2.5:7b" not found` | El modelo no se descargó o el nombre en `.env` no coincide | `ollama list` y paso 6.1 |
| `HTTP 400 ... does not support tools` | Modelo sin capacidad de herramientas | Usa `qwen2.5:7b` o revisa `Capabilities` en `ollama show` |
| `tardó más de 600 s` | El equipo va lento (por ejemplo, otras apps usan la GPU) | `ollama ps` muestra cuánto usa la GPU. Cierra programas o sube `LLM_TIMEOUT` |
| El modelo responde incoherencias o ignora los requisitos | Contexto corto | `OLLAMA_CONTEXT_LENGTH=8192` y reinicia Ollama |
| `AgenteSinResultado: ... no entregó un resultado válido en 15 pasos` | El modelo no logró entregar una ficha válida | Es **fail-closed**: el CV va a la bandeja, nunca se descarta. Reintenta o prueba un modelo mayor |
| `No hay fichas guardadas` (paso 9) | Aún no corriste el paso 8 | Corre el paso 8 primero |
| Una prueba sale con `F` | Cambió el código o los datos | Copia el error y avisa al grupo |

## Anexo · sin Docker

Con Python 3.11 o superior instalado:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install pydantic pytest pypdf
python -m pytest tests/test_reglas.py tests/test_dataset.py tests/test_rol3_agente.py tests/test_rol3_analista.py tests/test_rol3_auditor.py tests/test_rol3_citas.py tests/test_rol3_evaluacion.py tests/test_rol3_ficha.py tests/test_rol3_puntaje.py tests/test_rol3_sanitizacion.py
python scripts/rol3/probar_banco.py --sin-llm
```

En este caso, en `.env` usa `LLM_BASE_URL=http://localhost:11434/v1`, y `OLLAMA_HOST` no hace falta. Con [uv](https://docs.astral.sh/uv/): `uv run --with pypdf python -m pytest ...` y `uv run python scripts/rol3/probar_banco.py --sin-llm`.

## Para entender qué pasó por dentro

- Diseño, módulos y hallazgos del auditor: [rol-3-agentes.md](rol-3-agentes.md)
- Mediciones reales con el LLM y su evolución: [rol-3-evaluacion.md](rol-3-evaluacion.md)
- Cambios de contrato propuestos al Rol 1: [rol-3-propuesta-contratos.md](rol-3-propuesta-contratos.md)
