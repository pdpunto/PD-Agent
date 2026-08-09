# PD Agent v0.1.1 - RFC tecnico

**Estado:** Borrador de auditoria  
**Base:** `b96dae19524f8a520292702e3d8e880f39a72bfd`

## 1. Propósito

Definir el endurecimiento minimo para validar un provider real sobre fixture
Fabric controlado, manteniendo core provider-neutral.

## 2. Contratos a revisar

- carga de configuracion desde entorno/secret store;
- redaccion de secretos en artefactos persistidos;
- continuation de tool calls con Responses API;
- harness live E2E sobre runtime real;
- evidencias y PASS trazable.

## 3. Principios

- core provider-neutral se mantiene;
- OpenAIProvider permanece disponible;
- Gemini queda seleccionado como provider real para cerrar v0.1.1;
- `PD_AGENT_PROVIDER=gemini` y `PD_AGENT_MODEL=gemini-2.5-flash` son la
  configuracion objetivo;
- `GEMINI_API_KEY` se integra en el mismo circuito de redaccion de secretos;
- `store=false` sigue siendo la postura por defecto donde aplique;
- turnos manuales reenviarán `tool_calls` + `tool_results` neutrales para
  continuar `functionCall` + `functionResponse` cuando el SDK lo requiera;
- API key nunca persiste;
- Git y Gradle siguen con boundary existente;
- Minecraft runtime sigue fuera.

## 4. Cambios minimos esperados

Lote A:

- corregir carga BYOK/env;
- propagar secretos al reporting;
- fijar `store=false`.

Lote B:

- continuar tool calls con el protocolo real de Responses API.

Gemini boundary:

- `google-genai` solo dentro de `src/pd_agent/providers/gemini_provider.py`;
- `ModelProvider` y `AgentRuntime` siguen neutrales;
- `AgentRequest.messages` mapea a `contents`/history;
- `AgentRequest.tools` mapea a function declarations;
- `AgentRequest.tool_calls` conserva contexto previo de function calls;
- `AgentRequest.tool_results` mapea a function responses;
- `ToolCall.call_id` y `ToolResult.call_id` se preservan usando el `id` real
  del function call/function response del SDK;
- automatic function calling debe quedar desactivado o limitado para que PD
  Agent ejecute siempre las tools;
- timeout y retries deben mapearse a los controles del SDK sin crear un
  sistema paralelo;
- usage debe salir de `usage_metadata` del SDK a `AgentResponse.usage`.

Lote C:

- harness live E2E real.

## 5. Aceptacion

No hay PASS de v0.1.1 sin:

- Gemini API real;
- tool calls reales;
- build real sobre fixture controlado;
- JAR valido;
- evidence segura;
- final-report trazable.
