# PD Agent v0.1.1 - RFC tecnico

**Estado:** Borrador de auditoria  
**Base:** `b96dae19524f8a520292702e3d8e880f39a72bfd`

## 1. Propósito

Definir el endurecimiento minimo para validar proveedor OpenAI real sobre
fixture Fabric controlado.

## 2. Contratos a revisar

- carga de configuracion desde entorno/secret store;
- redaccion de secretos en artefactos persistidos;
- continuation de tool calls con Responses API;
- harness live E2E sobre runtime real;
- evidencias y PASS trazable.

## 3. Principios

- core provider-neutral se mantiene;
- OpenAI sigue siendo unico provider;
- `store=false` salvo incompatibilidad demostrada;
- turnos manuales reenviarán `tool_calls` + `tool_results` neutrales para continuar `function_call` + `function_call_output`;
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

Lote C:

- harness live E2E real.

## 5. Aceptacion

No hay PASS de v0.1.1 sin:

- Responses API real;
- tool calls reales;
- build real sobre fixture controlado;
- JAR valido;
- evidence segura;
- final-report trazable.
