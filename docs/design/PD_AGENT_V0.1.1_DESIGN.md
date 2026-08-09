# PD Agent v0.1.1 - Live Provider Validation

**Estado:** Borrador de auditoria  
**Base:** `b96dae19524f8a520292702e3d8e880f39a72bfd`

## 1. Objetivo

Validar `OpenAIProvider` con OpenAI Responses API real sin romper el core
provider-neutral.

## 2. Alcance

v0.1.1 solo endurece:

- carga segura de configuracion BYOK/entorno;
- redaccion de secretos en persistencia;
- continuation real de tool calls Responses API;
- harness live E2E controlado.

No introduce nuevos providers, router, RAG, multi-agent ni Minecraft runtime.

## 3. PASS esperado

PASS de v0.1.1 requiere:

- runtime real sobre fixture Fabric controlado;
- OpenAI real;
- tool calls reales;
- modificacion real de codigo;
- Gradle Wrapper real;
- build y JAR validos;
- final-report y evidencia persistidos.

No valida comportamiento dentro de Minecraft.

## 4. Hallazgos de auditoria

La auditoria del checkout real marco como puntos a corregir:

- `load_config()` no lee `os.environ` cuando la CLI lo llama sin mapping;
- `RunStorage` no recibe secretos desde `build_runtime_bundle()`;
- `AgentRuntime` reinyecta resultados de tools como texto y no como
  continuation nativa de Responses API;
- el smoke live actual no demuestra E2E real.

## 5. Cierre de fase

Esta fase termina cuando RFC, IMP y tests del lote A/B/C reflejen esos
ajustes sin alterar el core provider-neutral.
