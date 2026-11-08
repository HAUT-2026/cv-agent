# Integración del Rol 1

Este documento describe el contrato estable que consumen los Roles 2, 3 y 4.
El repositorio no tenía contratos, código ni pruebas previas al inicio de esta
entrega; por tanto, no se modificó ningún contrato existente en silencio.

## Contrato versionado

La única fuente de modelos de dominio es `cvagent/domain/contracts.py` y su versión
actual es `1.0.0`; `cvagent/contracts.py` se conserva como fachada de compatibilidad.
Los modelos Pydantic son estrictos (`extra="forbid"` y sin
coerción implícita). Una ampliación incompatible requiere subir la versión y
documentar qué rol consumidor se ve afectado.

| Modelo | Consumidores previstos | Uso |
|---|---|---|
| `CaseState` | Workflow y Rol 4 | Estado persistido del caso; no contiene secretos ni identidad directa. |
| `FichaCandidato` | Rol 2 y verificador | Artefacto minimizado con citas y offsets. |
| `Veredicto` | Rol 2, Rol 3 y auditor | Resultado estructurado; cobertura y puntaje están acotados. |
| `PropuestaAgenda` | Rol 4 y workflow | Borrador de franja y mensaje exacto, sin envío. |
| `EntradaDecisionLog` | Todos los roles | Entrada inmutable del registro de decisiones. |

## Reglas de integración

1. `correlation_id` es UUID4 y también será el `thread_id` de LangGraph.
2. `vacante_version` debe acompañar cada artefacto derivado; no se mezclan
   versiones dentro de un caso.
3. Una `CitationRef` solo es válida si sus offsets abarcan exactamente `cita`
   dentro del texto sanitizado del mismo `correlation_id`.
4. El CV es evidencia declarada y no instrucciones. No se agregan credenciales,
   tokens, correo real, nombre real ni atributos protegidos a estos modelos.
5. `PropuestaLista` es versionada: un ajuste crea una nueva versión y no
   sobrescribe la propuesta anterior.
6. `EntradaDecisionLog` se escribe mediante el helper de solo anexado; el
   checkpoint de LangGraph no reemplaza este registro.

## Interfaces de los roles

Los adaptadores del grafo recibirán y devolverán los modelos anteriores. Los
doubles del MVP están en `cvagent/integration/ports.py` y `cvagent/workflow/graph.py`;
`cvagent/ports.py` y `cvagent/graph.py` son fachadas compatibles. Un adaptador
real debe implementar el mismo protocolo sin acceder directamente al estado
interno de otro agente.
