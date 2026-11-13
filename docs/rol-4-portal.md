# Portal del Rol 4

Interfaz del reclutador, API REST y orquestación del lote. Consume los
contratos del Rol 1 (`cvagent/domain/contracts.py`, versión `1.0.0`) y el motor
de reglas del Rol 2 (`reglas/`) **sin modificar ninguno de los dos**.

## Qué se agregó

```
portal/
  texto.py          Texto canónico sanitizado y anclaje de citas
  adaptadores.py    AnalistaPort, MotorReglasPort, AuditorPort, AgendadorPort
  lote.py           Orquestación: reglas del Rol 2 + grafo del Rol 1
  api.py            API REST (FastAPI) y servido del frontend
  __main__.py       `python -m portal`
  web/              Frontend en HTML, CSS y JavaScript sin paso de compilación
docs/rol-4-portal.md
tests/test_portal.py
```

## Cómo se corre

```bash
pip install -e ".[portal]"
python -m portal                 # http://localhost:8000  ·  /docs para la API
python -m pytest tests -q        # el portal agrega 21 pruebas
```

Con `CVAGENT_POSTGRES_URL` definido, el portal usa `postgres_checkpointer`;
sin esa variable usa `InMemorySaver` **con el mismo `contract_serializer()`**,
para que el comportamiento de serialización sea idéntico en ambos modos.

## Qué es real y qué es provisional

| Componente | Estado | Dueño |
|---|---|---|
| Motor de reglas R1–R13 | Real | Rol 2, sin tocar |
| Grafo, estado, `decision_log`, SLA, tokens | Real | Rol 1, sin tocar |
| Portal, API, bandeja, evidencia | Real | Rol 4 |
| `PortalAnalista`, `PortalAuditor` | **Provisional** | hueco del Rol 3 |
| `PortalAgendador`, envío | **Provisional** | dobles del MVP |

Los adaptadores provisionales no usan modelo de lenguaje. Producen ya los
contratos definitivos, así que sustituirlos es cambiar una línea en
`adaptadores_del_portal()`.

## El anclaje de citas

`CitationRef` exige `offset_fin - offset_inicio == len(cita)` y
`verify_against()` recorta el texto y compara. El portal lo cumple por
construcción con una regla que conviene mantener cuando llegue el agente real:

> **Al modelo se le pide la subcadena literal; las posiciones las calcula el
> código.** Un modelo no cuenta caracteres, pero sí copia una frase.

`portal/texto.py::anclar()` devuelve `None` en dos casos, y ambos son hallazgos
para el auditor, no errores a corregir en silencio:

- la frase no está en el texto → el modelo la inventó;
- aparece más de una vez → la cita no identifica nada.

El texto canónico sale de `cvs_pdf/<cv_id>.pdf` cuando tiene capa de texto, y
del gemelo JSON cuando no. La procedencia viaja en `AuditMetadata.fuente`,
porque una ficha construida sobre el gemelo **no es la misma evidencia**: el
PDF contiene trampas que el gemelo no tiene.

## Las dos compuertas

El grafo del Rol 1 interrumpe dos veces por caso. El portal las expone así:

| Compuerta | Endpoint | Qué hace |
|---|---|---|
| `lista_corta` | `POST /api/decision/lista` | Decisión de lote repartida a cada hilo |
| `mensaje_exacto` | `POST /api/decision/mensaje` | Por candidato, antes de cualquier envío (R10) |

`POST /api/decision/mensaje` rechaza con 422 si el caso todavía espera la
primera compuerta: no se puede aprobar el mensaje saltándose la lista.

---

# Hallazgos de integración

Cinco cosas aparecieron al unir las tres partes. Ninguna se resolvió en
silencio; todas necesitan una decisión del grupo.

## H-1 · `CaseState` no tiene dónde guardar de qué CV se trata

`AnalistaPort.crear_ficha(state, now)` solo recibe el `CaseState`, y el
contrato es `extra="forbid"`: no admite `cv_id`, ni el texto canónico, ni una
referencia al documento. Hoy el portal mantiene la correlación fuera del
estado, en `ContextoLote.casos`.

**Funciona, pero rompe una propiedad que el Rol 1 buscaba a propósito**: el
estado persistido deja de ser suficiente para reconstruir el caso. Tras un
reinicio, el checkpoint sabe en qué nodo iba pero no sobre qué CV.

*Propuesta:* agregar a `CaseState` un `candidato_ref` opaco y un
`documento_ref` (identificador del documento sanitizado, no su contenido).
Ninguno de los dos es dato personal, así que no rompe la minimización. Decide
el Rol 1, porque sube la versión del contrato.

## H-2 · El grafo es por caso y R4/R5/R6 son de lote

`PropuestaLista` se construye dentro del grafo con un solo candidato
(`candidatos_ref=[ficha.candidato_ref]`), mientras que `reglas.armar_staging`
ordena el lote completo y aplica cobertura mínima, empate en el corte y tamaño
de lista. Son dos nociones distintas de «lista corta».

Hoy el bucle del lote vive en `portal/lote.py`: cada caso corre hasta su
interrupción, el portal arma el Top con el motor del Rol 2, y la decisión
humana **se reparte a cada hilo** (`aprobar` a los que entran, `rechazar` con
razón a los demás). Ningún caso queda sin decisión registrada.

*Lo que falta decidir:* si el lote debe ser un grafo propio con un nodo de
cierre, o si el orquestador externo es la respuesta definitiva. Afecta
directamente la decisión abierta nº 3 de `AGENTS.md`.

## H-3 · La rúbrica de puntaje no está definida en ningún lado

`armar_staging` dice explícitamente que no calcula puntajes, y el SDD exige que
el puntaje se calcule fuera del modelo, pero nadie define **cómo**. El portal
usa, como supuesto propio y documentado:

```
0,50  obligatorios en estado «cumple» (R3)
0,25  deseables observados con evidencia en el texto
0,25  experiencia efectiva (R11), saturando al doble del mínimo exigido
```

El tercer componente existe por una razón empírica: sin él, 24 de 28
evaluables empataban en el mismo puntaje y R5 se disparaba de forma espuria.
Pasar R3 es binario y los deseables se repiten mucho en el corpus; los meses
efectivos son la única señal continua disponible hoy.

*Los tres pesos son un supuesto del Rol 4 y deben discutirse con el hiring
manager.* Cambiarlos cambia el Top 5.

## H-4 · INJ-03 solo es detectable con extracción de PDF

Tres de los cuatro CV de inyección llevan la instrucción en campos que el
gemelo JSON conserva (`otros[].texto`, descripciones de experiencia). INJ-03 la
esconde en el PDF con texto no visible, así que **no aparece en el gemelo**.

El portal lee el PDF cuando existe, de modo que en el repositorio completo
INJ-03 sí se detecta; pero cualquier prueba que use solo los JSON lo deja
pasar. `tests/test_portal.py::test_p7` verifica los tres detectables desde el
gemelo y documenta la excepción.

*Consecuencia para el Rol 3:* la sanitización tiene que correr sobre el texto
extraído del PDF, no sobre la ficha estructurada. Si el extractor real trabaja
desde el JSON, esta trampa queda sin cubrir.

## H-5 · Un veredicto bloqueado se parece a un descarte automático

`_route_after_audit` envía a `stop` cualquier caso cuyo veredicto no sea
aprobado. El caso queda en `pendiente_revision` con
`razon_parada=requiere_revision_humana`, que es correcto, **pero no genera
interrupción**: no aparece en ninguna bandeja y nadie lo ve.

`AGENTS.md` es explícito: *«Una excepción, silencio, fallo de herramienta o
incertidumbre detiene el avance y crea revisión humana; no se transforma en
descarte automático»*. Y el manifiesto marca `ruta_final: "bandeja"` para los
cuatro INJ.

Mientras tanto, el portal los expone en `GET /api/detenidos` y los muestra en
la bandeja bajo «Detenidos antes de la compuerta», con su razón de parada y el
veredicto del auditor. Es una mitigación del Rol 4, no una solución.

*Propuesta:* que el grafo tenga una tercera interrupción (`revision_humana`) o
que `stop` registre el caso en una cola de revisión explícita. Decide el Rol 1.

---

## Contrato con el Rol 3

Lo único que el portal exige del agente real:

```python
def analizar(texto_canonico: str, requisitos: dict) -> FichaCandidato
def auditar(ficha: FichaCandidato, veredicto: Veredicto) -> Veredicto
```

con el invariante `texto_canonico[c.offset_inicio:c.offset_fin] == c.cita` para
toda cita. `tests/test_portal.py::test_p11` lo verifica sobre el corpus
completo y la bandeja marca en rojo cualquier cita que no recorte.

No normalizar el texto canónico después de extraerlo. Si hace falta una versión
sin tildes para comparar, se produce aparte y se conserva el mapa de
posiciones.
