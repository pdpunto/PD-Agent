# PD Agent v0.4 --- RFC Delta: Runtime Limits & Economic Telemetry v1.1

**Status:** PROPOSED\
**Milestone:** PD Agent v0.4 --- Benchmark Foundation\
**Scope:** Delta sobre la arquitectura existente. No billing, no SaaS, no credits, no Model Router.

## 1. Contexto y hallazgo clave

La auditoria contra el repo real confirmo una discrepancia de wiring:

- `BenchmarkConfig.execution_limits.max_agent_steps = 25` sigue siendo la configuracion declarada por benchmark;
- `BenchmarkExecutor` debe pasar explicitamente `config.execution_limits` al `RunController`;
- `RunController` tiene un default propio y, si no recibe limits, el runtime puede terminar usando `max_agent_steps = 40`.

Por tanto, este delta no cambia semantica de dataset ni acceptance. Corrige la propagacion de limites para que el runtime ejecute exactamente lo que declara el benchmark.

No hace falta un delta de diseno nuevo: los contratos existentes ya alcanzan para este cambio.

Ademas, la evidencia economica necesita distinguir de forma normativa:

- agent step;
- logical provider request;
- physical HTTP request;
- usage historico;
- pricing posterior.

## 2. Objetivos

1. Hacer que los limites declarados por el benchmark sean los limites realmente aplicados por el runtime.
2. Persistir accounting defendible de llamadas logicas al provider.
3. Conservar usage historico sin acoplarlo a precios.
4. Mantener trazabilidad suficiente para estimar costes posteriormente.
5. Mantener Brain OFF/ON, dataset, acceptance y repeticiones sin cambios.
6. Dejar v0.4 listo para decidir viabilidad de quota sin una nueva decision arquitectonica.
7. Introducir un Runtime Action Gate gradual, provider-neutral, que solo ajuste la exposicion de tools y la telemetry segura, sin modificar ToolExecutor, dataset ni semantics del benchmark.

## 3. No objetivos

No implementar:

- subscriptions;
- credits PD;
- Stripe;
- SaaS backend;
- auth;
- Model Router;
- LocalProvider;
- BYOK UX;
- precios comerciales;
- ejecucion multi-day;
- matriz oficial de 18 runs;
- pricing hardcodeado en AgentRuntime.

## 4. Definiciones normativas

### 4.1 Agent step

Paso del loop del agente contabilizado por `RunState.record_agent_step()` despues de un retorno exitoso de `provider.execute()`.

### 4.2 Logical provider request

Una invocacion de PD Agent a `ModelProvider.execute(AgentRequest)`.

Es la unidad que PD Agent puede observar de forma uniforme entre providers.

### 4.3 Physical provider request

Request real de transporte/API enviado al proveedor.

No debe inferirse automaticamente que:

`logical_provider_request_count == physical_provider_request_count`

Gemini puede realizar retries internos dentro del SDK. Solo se persistira un contador fisico cuando exista evidencia directa y fiable.

### 4.4 Usage historico

Usage devuelto realmente por el provider/adaptador. Debe persistirse independientemente de cualquier tabla de precios.

### 4.5 Pricing Snapshot

Contrato externo/versionado que transforma usage historico compatible en coste estimado. No forma parte del runtime del agente.

## 5. Runtime limits

`BenchmarkConfig.execution_limits` es autoridad para una ejecucion benchmark.

`BenchmarkExecutor` MUST propagar esos limites al `RunController`/runtime correspondiente.

La evidencia persistida MUST permitir comprobar que:

- limite declarado;
- limite aplicado;

son equivalentes.

Para v0.4, `max_agent_steps` permanece en **25** en la configuracion benchmark. El runtime no debe caer en el default 40 por omision de wiring.

Para Minecraft, el timeout del harness NO debe tener un default oculto independiente de 60s en el camino benchmark. Si `acceptance.spec.timeout_seconds` existe, ese valor manda. Si no existe, el valor efectivo debe derivarse de `BenchmarkConfig.execution_limits.process_timeout_seconds` de la configuracion concreta.

## 6. Provider request accounting

### 6.1 Autoridad normativa

La unica autoridad normativa de `logical_provider_request_count` es `AgentRuntime`.

`RunState` es la persistencia primaria de ese contador.

`MODEL_CALLED` es solo cross-check.

### 6.2 Semantica obligatoria

Cada benchmark run MUST persistir:

`logical_provider_request_count`

El contador se incrementa exactamente una vez por cada invocacion logica a `ModelProvider.execute()`, incluidos exitos y errores del provider.

Debe incluir llamadas que terminen en error del provider.

### 6.3 Physical requests

`physical_provider_request_count` MUST NOT ser fabricado a partir del contador logico.

Si el adapter puede observar requests fisicos de forma fiable, podra persistirse como campo opcional. Si no:

`physical_provider_request_count = unavailable/null`

### 6.4 Retries

Los retries observables por PD Agent SHOULD registrarse separadamente.

Retries internos opacos del SDK MUST declararse como no observables, no estimarse como hechos.

## 7. Usage telemetry

Por respuesta logica exitosa se conservara, cuando el provider lo exponga:

- provider;
- model;
- input tokens;
- cached input tokens;
- output tokens;
- reasoning/thinking tokens;
- total tokens;
- timestamp o correlacion con evento;
- duracion observable;
- success/error;
- rate-limit/error kind;
- retry observable;
- identidad del benchmark run/attempt.

Los campos no disponibles MUST permanecer ausentes/null; no se estiman.

## 8. Persistencia por benchmark run

`BenchmarkCollection`/evidencia equivalente debe permitir derivar:

- logical provider requests;
- tool calls;
- tool names;
- builds;
- Minecraft executions;
- duracion;
- PASS/FAIL;
- termination reason;
- Brain OFF/ON;
- retrieved/selected/injected;
- usage agregado;
- retries/rate-limits observables.

`cost` seguira siendo `null/unavailable` mientras no exista un `PricingSnapshot` compatible.

## 9. Agregacion

Por `Task x Config`, la agregacion debe conservar:

- valid repetitions;
- PASS count/rate;
- usage agregado;
- logical provider request statistics;
- duracion;
- failure categories.

La introduccion de costes se hara posteriormente a partir de usage + PricingSnapshot.

## 10. PricingSnapshot - contrato conceptual

Campos minimos:

- `snapshot_id`
- `version`
- `provider`
- `model`
- `currency`
- `effective_at`
- `provenance`
- rate de input
- rate de cached input, cuando aplique
- rate de output
- otros componentes unicamente cuando sean conocidos y facturables

`EstimatedCost` minimo:

- `pricing_snapshot_id`
- referencia/identidad del usage
- componentes calculados
- total
- currency
- estado `ESTIMATED | UNAVAILABLE`

Reglas:

1. Usage historico nunca depende del pricing.
2. Pricing nunca se hardcodea en AgentRuntime.
3. Sin usage suficiente o snapshot compatible: `UNAVAILABLE`.
4. Historicos deben poder recalcularse con snapshots distintos.

## 11. Expected Cost per Successful Task

La metrica economica futura debe representar conceptualmente:

`coste total atribuible a intentos validos de resolver la task / numero de PASS`

No se excluiran automaticamente intentos validos fallidos, porque consumen recursos reales.

`INVALID`, fallos de infraestructura, runs censurados/inconclusos y replacements deben clasificarse explicitamente antes de decidir su tratamiento economico.

No se implementa esta formula en este delta.

## 12. Pacing

El pacer benchmark-local existente se mantiene como mecanismo de proteccion de RPM.

Requisitos:

- pacing compartido por provider/model dentro de la ejecucion;
- reloj monotono;
- minimo configurable;
- accounting de requests logicas;
- no alterar Brain OFF/ON;
- no confundir budget logico con cuota fisica garantizada.

El pacing controla la cadencia; el Runtime Action Gate controla que categorias de tools se exponen en cada request segun el drift de exploracion. La evidencia persistida debe incluir la fase, el estado del gate y los nombres de tools ofrecidas, sin persistir prompts completos ni contenido completo de Brain.

Persistencia cross-session y multi-day quedan fuera de este lote.

## 13. Resume / multi-day

La auditoria confirma que actualmente existen identidades y schedule persistido, pero no un protocolo formal suficiente de resume cross-session.

No se implementa ahora.

Si tras la smoke corregida la cuota diaria sigue siendo insuficiente, se abrira un delta posterior especifico que preserve exactamente schedule, repetition, attempt, replacement policy y evidencia.

## 14. Errores y clasificacion

- Error provider/rate-limit: debe conservarse en evidencia y termination reason.
- Falta de usage: no invalida automaticamente el run tecnico.
- Falta de pricing: produce coste `UNAVAILABLE`, no coste cero.
- Physical request count no observable: `UNAVAILABLE`, no aproximacion presentada como real.

## 15. Compatibilidad

No cambia:

- `PD_AGENT_BENCHMARK_DATASET_V0.4_2`;
- B001/B002/B003;
- Brain OFF/ON;
- 3 valid repetitions;
- acceptance;
- `max_agent_steps=25` en benchmark config;
- arquitectura `AgentRuntime -> ModelProvider`.

## 16. Criterios de aceptacion del delta

PASS unicamente si existe evidencia de que:

1. el runtime recibe y aplica `max_agent_steps=25`;
2. una smoke que agota pasos no supera 25 logical provider requests por run, salvo llamadas explicitamente documentadas fuera de ese loop;
3. `logical_provider_request_count` queda persistido con autoridad en `AgentRuntime`/`RunState`;
4. usage existente sigue persistido sin regresion;
5. Brain OFF conserva 0 contexto externo;
6. Brain ON conserva retrieval/selection/injection y provenance;
7. pacing sigue evitando 429 en la smoke de validacion;
8. suite completa PASS;
9. commit + push;
10. `HEAD == origin/main` y working tree limpio.

## 17. Gate posterior

Este RFC no autoriza las 18 runs.

El estado `READY_FOR_LIVE_BENCHMARK` solo podra concederse despues de una nueva smoke OFF/ON con los limites corregidos y un recalculo del presupuesto de requests/cuota basado en evidencia nueva.
