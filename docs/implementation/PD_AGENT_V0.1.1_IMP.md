# PD Agent v0.1.1 - Implementation Plan

**Estado:** Auditoria y alineacion documental  
**Base:** `8c5af965def541fe160b420b4e7d7bc076090e2c`

## L12 - Provider continuation metadata

Objetivo:

- introducir `ProviderContinuation` como contrato neutral minimo;
- transportar continuations entre `AgentResponse` y `AgentRequest`;
- permitir que `GeminiProvider` reemita `thought_signature` en el `Part`
  correcto;
- mantener `OpenAIProvider` provider-local, incluyendo el mapping opcional de
  reasoning stateless mediante `ProviderContinuation`;
- no cambiar `AgentRuntime` a provider-aware.

Archivos previstos:

- `src/pd_agent/core/contracts.py`
- `src/pd_agent/runtime/engine.py`
- `src/pd_agent/providers/gemini_provider.py`
- `src/pd_agent/providers/openai_provider.py` solo si hace falta para
  compatibilidad vacia
- tests unitarios de core/runtime/provider

## Diseno de implementacion

1. Crear un modelo neutral pequeno.
2. Añadirlo a `AgentResponse`.
3. Pasarlo por `AgentRuntime` sin interpretar.
4. Añadirlo a `AgentRequest`.
5. Usarlo solo dentro de `GeminiProvider`.
6. OpenAIProvider interpreta solo continuations con owner `openai` y mantiene
   `store=false`; el resto se ignora sin cruzar ownership.

### O1 - OpenAI reasoning continuation

Cuando `model_config.reasoning` esta activo, el adapter solicita el include
`reasoning.encrypted_content` sin duplicar includes existentes. Cada reasoning
output item se convierte en una `ProviderContinuation` con `position`,
identidad y payload JSON-safe opaco. En el request siguiente se reinyecta antes
de los function calls y outputs, respetando el orden de continuations.

El encrypted content no se incluye en metadata, eventos ni reporting. Las
continuations OpenAI malformadas, duplicadas o conflictivas terminan como error
de protocolo. La telemetria conserva usage anidado de cache/reasoning y expone
el numero de intentos fisicos y retries en metadata neutral.

## Reglas de construccion

- el payload debe ser JSON-safe;
- la asociacion debe ser inequívoca;
- el orden debe preservarse cuando el protocolo dependa de ello;
- si falta o esta corrupto, error explicito;
- no almacenar objetos SDK;
- no meter `thought_signature` en core;
- no redisenar `AgentMessage` ni `ToolExecutor`.

## Tests requeridos

CORE:

- construccion del nuevo contrato;
- serializacion JSON-safe;
- round-trip;
- payload invalido;
- compatibilidad con runs antiguos sin continuations.

RUNTIME:

- `AgentResponse -> AgentRuntime -> AgentRequest`;
- una continuation;
- multiples continuations;
- orden preservado;
- transport only.

GEMINI:

- una function call con signature;
- multiple function calls;
- calls paralelas;
- texto + calls;
- `FunctionCall.id` presente;
- `FunctionCall.id` ausente;
- replay exacto;
- falta signature;
- metadata corrupta.

OPENAI:

- regresion de comportamiento actual;
- campo vacio no rompe nada;
- reasoning medium e include encrypted content;
- extraction y replay de una/multiples continuations;
- rechazo de payload corrupto/conflictivo;
- physical attempts y retries;
- usage cached/reasoning tokens;
- no filtracion de encrypted content.

## Validacion

Cuando exista implementacion:

- ejecutar suite focalizada;
- ejecutar suite completa;
- revisar evidence y redaccion;
- dejar listo el lote Gemini live siguiente.

## Cierre

Si la implementacion confirma este alcance pequeno, se puede cerrar en un
solo lote. Si aparece necesidad de framework mayor, parar y re-auditar.
