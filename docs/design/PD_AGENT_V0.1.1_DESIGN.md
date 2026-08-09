# PD Agent v0.1.1 - Real Provider Validation

**Estado:** Borrador de auditoria  
**Base:** `b96dae19524f8a520292702e3d8e880f39a72bfd`

## 1. Objetivo

Demostrar al menos un provider real E2E sin mocks, sin romper el core
provider-neutral.

## 2. Alcance

v0.1.1 solo endurece:

- carga segura de configuracion BYOK/entorno;
- redaccion de secretos en persistencia;
- continuation real de tool calls Responses API;
- harness live E2E controlado.

Decision de validacion:

- provider real seleccionado: `GeminiProvider`;
- modelo: `gemini-2.5-flash`;
- SDK oficial: `google-genai`;
- auth: `GEMINI_API_KEY`;
- Free Tier: solo fixture controlado/no confidencial durante v0.1.1.

OpenAIProvider permanece disponible. El live OpenAI adicional quedo bloqueado
por billing y ya no es el unico requisito de PASS.

No introduce router, RAG, multi-agent ni Minecraft runtime. Codex queda
descartado como ModelProvider para v0.1.1.

## 3. PASS esperado

PASS de v0.1.1 requiere:

- runtime real sobre fixture Fabric controlado;
- Gemini API real;
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

La lectura del repo confirma que:

- `ModelProvider` y `AgentRuntime` siguen provider-neutral;
- `AppConfig` ya tiene campo `provider`, pero el bootstrap actual solo crea
  `OpenAIProvider`;
- `RunStorage`/`Redactor` ya aceptan secrets configurables;
- `tool_calls` y `tool_results` neutrales sirven como base tambien para
  Gemini;
- no hay soporte Gemini aun en bootstrap/CLI;
- no hay cambio de core necesario para documentar la direccion, pero
  `GeminiProvider` quedara en G1.

## 5. Cierre de fase

Esta fase termina cuando RFC, IMP y tests del lote A/B/C reflejen esos
ajustes sin alterar el core provider-neutral.
