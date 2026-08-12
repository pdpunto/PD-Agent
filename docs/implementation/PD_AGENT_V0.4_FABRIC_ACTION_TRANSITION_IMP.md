# PD Agent v0.4 - Fabric Agent Action Transition IMP Delta

**Status:** DRAFT - pending repository audit  
**Version:** 1.0  
**Milestone:** PD Agent v0.4 - Benchmark Foundation  
**Depends on:** RFC Delta Fabric Action Transition  
**Audited baseline before planning:** `b95411714180c09e9a334c0767d00dca4a0b4da2`

## 1. Objetivo

Implementar exclusivamente el RFC delta de Action Transition con el cambio minimo necesario.

No autoriza implementacion inmediata.

No hace falta un Design delta adicional para este lote: la forma correcta es extender runtime/context/telemetry sobre contratos ya existentes.

## 2. Reglas de implementacion

1. No crear un runtime benchmark paralelo.
2. Reutilizar `RunStorage`, runtime, providers, build runner, artifact validator, Brain y Minecraft harness.
3. Mantener v0.1-v0.4 compatibles donde aplique.
4. Cada lote debe tener tests propios antes de avanzar.
5. No ejecutar la matriz oficial de 18 runs hasta cerrar foundation.
6. No modificar un task despues de observar resultados sin versionarla.
7. No introducir UI, cloud, multi-agent, nuevos providers ni capacidades no requeridas.
8. No introducir scoring compuesto.
9. Commit y push solo cuando el lote este verificado.
10. Working tree limpio al cerrar cada hito.

## 3. Auditoria del repo real

La auditoria del repo real confirma estos puntos de partida:

- `AgentRuntime` ya tiene `_LoopTelemetry`.
- `RunState` ya persiste los contadores que necesitamos para budget y accounting.
- `ContextRequest` ya incluye `limits`.
- `ContextManager.build_context(..., limits=...)` ya transporta limites al stack de contexto.
- `RunController` ya pasa `limits` a `AgentRuntime`.
- `BenchmarkExecutor` ya propaga `config.execution_limits` al `RunController`.
- `RunContextSource` ya existe y es el lugar natural para budget/progress visible en contexto.

Por tanto, el delta es de policy, telemetry ligera y contexto operacional. No requiere arquitectura nueva.

## 4. Archivos/modulos previsibles

### Implementacion probable

- `src/pd_agent/runtime/engine.py`
- `src/pd_agent/context/sources.py`
- `src/pd_agent/context/models.py` solo si se decide formalizar alguna pieza auxiliar
- `tests/unit/test_l9_runtime.py`
- `tests/unit/test_l7_context_system.py`
- `tests/unit/test_benchmark_executor.py` solo si se necesita reforzar el contrato de limits propagados

### No tocar salvo evidencia posterior

- providers;
- Brain retrieval;
- benchmark datasets;
- ToolExecutor/security;
- acceptance definitions;
- `max_agent_steps`;
- `run_v0_4.py` salvo que el audit final lo exija por otra causa.

## 5. Lotes

### A1 - Operational context / budget visibility

Objetivo:

Hacer visible al modelo el estado operacional.

Implementar, segun auditoria real:

- phase actual;
- steps used/max/remaining;
- tool calls used/max/remaining;
- build attempts used/max/remaining;
- files changed;
- resumen reciente de exploracion.

Preferencia:

- `RunContextSource`, o
- una fuente de contexto pequena si resulta mas limpio.

No provider-specific.

Tests:

- calculo remaining correcto;
- limites en cero;
- representacion determinista;
- no secretos;
- contexto bounded.

### A2 - Exploration progress telemetry

Objetivo:

Seguir exploracion consecutiva sin introducir planner.

Implementar:

- inspection-only classification;
- streak;
- recent paths/tools acotados;
- reset en progreso real.

Auditar si vive mejor en:

- `_LoopTelemetry`;
- `RunState`;
- estructura runtime auxiliar.

Preferencia:

- estado efimero runtime si no hace falta persistencia contractual.

Tests:

- read/list/search incrementan;
- write changed resetea;
- create/delete changed resetean;
- build resetea;
- distintas exploration tools siguen contando como streak;
- diagnosis puede inspeccionar sin falso positivo prematuro.

### A3 - Phase Action Policy

Objetivo:

Inyectar policy operacional explicita en cada request.

Implementar un builder/provider-neutral pequeno.

No meter un string gigante directamente dentro de Gemini/OpenAI adapters.

Debe cubrir:

- objetivo de fase;
- budget;
- progress;
- reglas de actuacion;
- escalation.

Tests:

- PLANNING policy;
- DIAGNOSING policy;
- escalation visible;
- Brain ON/OFF no altera policy base;
- no tokens B001-specific.

### A4 - Exploration escalation

Objetivo:

Evitar consumir todos los steps explorando.

Definir umbrales conservadores.

No usar un unico hard stop agresivo.

Propuesta inicial a auditar:

- despues de 4 inspection-only agent steps consecutivos: `action_required = true`;
- si persiste varios pasos adicionales sin progreso: escalation mas fuerte;
- guard terminal solo como ultima defensa.

Codex debe comprobar arquitectura y tests antes de fijar constantes.

No derivar umbrales de las cifras concretas de B001.

Los umbrales deben declararse como policy interna con nombres semanticos.

### A5 - Runtime integration

Modificar el flujo de `PLANNING`.

Actual:

```text
inspection-only
-> continue
```

Nuevo:

```text
inspection-only
-> update exploration telemetry
-> next provider request includes phase/budget/progress/policy
-> escalation if needed
```

El Runtime no debe:

- inventar edicion;
- ejecutar write sin tool call;
- adivinar solucion;
- saltar directamente a `BUILDING` arbitrariamente.

La accion sigue viniendo del modelo.

### A6 - Regression tests

Añadir tests, previsiblemente en:

- `tests/unit/test_l9_runtime.py`
- tests de contexto relacionadas

Casos obligatorios:

1. un read inicial permitido;
2. multiples inspecciones legitimas;
3. budget remaining visible;
4. exploration streak;
5. action escalation antes del limite;
6. read -> search -> read -> write;
7. mutacion reset;
8. build reset;
9. diagnosis despues de error build;
10. repeated no-op anterior sigue funcionando;
11. repeated build failure anterior sigue funcionando;
12. max step/tool/build limits siguen autoritativos;
13. provider fake recibe policy;
14. Brain OFF/ON misma policy base;
15. no strings B001/Registries.BLOCK/etc.

### A7 - Full offline validation

Ejecutar:

```text
python -m compileall src tests
python -m pytest -q
```

Todo debe PASS.

### A8 - Live smoke

Solo despues de aprobar codigo offline.

Reusar smoke B001.

Mismos parametros:

```text
provider = gemini
model = gemini-3.5-flash-lite
max_agent_steps = 25
```

Brain OFF y ON.

No ejecutar todavia las 18 runs.

No cambiar dataset.

No aumentar steps.

Critero:

- no consumir sistematicamente 25 steps exclusivamente en exploration;
- debe existir mutacion/build/progreso verificable antes del exhaustion;
- policy/budget visible en trace;
- si termina sin actuar, debe haber blocker explicito o exploration-stall reason util.

No exigir PASS funcional.

### A9 - Revision y handoff

Despues de smoke:

- revisar traces;
- comparar OFF/ON;
- confirmar ausencia de workaround;
- commit y push;
- volver al milestone de Benchmarks.

## 6. Auditoria tecnica contra el repo

### 6.1 `_LoopTelemetry`

Es un buen lugar para la telemetria efimera de exploration drift porque:

- ya vive en runtime;
- ya se resetea por run;
- ya modela anti-loop;
- no obliga a cambiar `RunState` si la senal solo se usa para policy.

Conclusión:

- si la informacion solo sirve para el loop actual, `_LoopTelemetry` es el sitio mas limpio;
- si se quiere exponer en evidencia durable, se debe materializar en evento o metadata, no en un parser de texto.

### 6.2 Budget sin modificar `RunState`

No parece necesario cambiar `RunState` para mostrar budget:

- `RunState` ya tiene los contadores;
- `ExecutionLimits` ya tiene los maximos;
- `RunContextSource` puede renderizar ambos.

Por tanto, el budget visible puede salir de runtime + context source sin tocar la persistencia primaria.

### 6.3 `RunContextSource` y `ExecutionLimits`

`ContextRequest.limits` ya existe.

`ContextManager.build_context(..., limits=...)` ya lo transporta.

`RunContextSource` no lo usa hoy, pero puede leerlo desde `request.limits` sin cambiar contratos.

### 6.4 Phase policy builder

La forma mas limpia es un builder pequeno en runtime que produzca un bloque de instrucciones por fase.

Debe depender de:

- `run_state`;
- `limits`;
- telemetria de exploration;
- estado de build/diagnosis.

No debe depender del provider.

### 6.5 Recent inspected paths

No hay que parsear texto del assistant.

La fuente correcta son los eventos y resultados estructurados ya emitidos:

- `TOOL_REQUESTED`;
- `TOOL_EXECUTED`;
- `TOOL_REJECTED`.

Los tool results ya llevan metadata util como `changed` y `path` en las tools de escritura/creacion/eliminacion, y las de lectura devuelven el path en el output estructurado.

### 6.6 Multiple tool calls por agent step

La semantica debe ser:

- `agent_step_count`: una vez por respuesta logica del provider;
- `tool_call_count`: una vez por tool call ejecutada;
- `inspection streak`: por agent step, no por tool call.

Esto evita infracontar una respuesta con varias lecturas.

### 6.7 DIAGNOSING

DIAGNOSING no debe quedar sobre-restringido.

Un build error nuevo justifica mas inspeccion.

La action policy debe permitir investigacion dirigida por error real antes de volver a corregir.

### 6.8 Anti-loop existente

La proteccion actual contra:

- repeated no-op tool calls;
- repeated build failure;

debe permanecer.

El nuevo stall detection no debe colisionar con ella.

### 6.9 Persistencia minima para traces

Preferir:

- metadata de evento;
- summary en `FinalReport`;
- `RunState` ya existente.

Solo crear un campo nuevo si no puede derivarse limpiamente.

## 7. Tests necesarios

Tests nuevos realmente necesarios:

- contexto muestra budget con valores correctos;
- `RunContextSource` incorpora limits si se decide exponerlos;
- inspection-only streak incrementa por step;
- change detection resetea streak;
- build reset limpia state de exploration;
- DIAGNOSING sigue pudiendo inspeccionar;
- no-op anti-loop sigue funcionando;
- repeated build failure sigue funcionando;
- provider fake recibe el bloque de policy;
- Brain OFF/ON mantienen la misma policy base;
- contexto y policy no contienen secretos.

Tests reutilizables:

- `tests/unit/test_l9_runtime.py` para el loop principal;
- `tests/unit/test_l7_context_system.py` para el bundle de contexto;
- `tests/unit/test_benchmark_executor.py` para la propagacion de limits;
- `tests/unit/test_benchmark_models.py` para serializacion de metrics si se toca evidencia.

## 8. Discrepancias detectadas

No hay una discrepancia arquitectonica mayor.

Las unicas diferencias relevantes son de alcance:

- el repo ya tiene parte del plumbing de budget;
- el repo ya tiene `_LoopTelemetry`;
- el repo ya propaga `ExecutionLimits` desde benchmark a runtime;
- falta la policy de transicion y la telemetria de exploration drift.

## 9. Arquitectura final propuesta

La division recomendada es:

- `policy`: runtime, preferiblemente `src/pd_agent/runtime/engine.py` o un helper pequeno al lado;
- `telemetry`: runtime efimero, inicialmente `_LoopTelemetry` o equivalente;
- `budget/progress`: `RunState` + `ExecutionLimits` + `RunContextSource`;
- `evidence durable`: `FinalReport`, `RunStorage`, events y metadata.

## 10. Archivos previsibles de implementacion

Con la auditoria actual, los archivos mas probables son:

- `src/pd_agent/runtime/engine.py`
- `src/pd_agent/context/sources.py`
- `tests/unit/test_l9_runtime.py`
- `tests/unit/test_l7_context_system.py`

Posiblemente:

- `src/pd_agent/context/models.py` si se formaliza algun campo auxiliar;
- `tests/unit/test_benchmark_executor.py` si se quiere reforzar el contrato de limits.

## 11. Confirmaciones de compatibilidad

Este delta no cambia:

- `B001` hardcoded;
- `max_agent_steps`;
- dataset;
- Brain contracts;
- providers;
- security boundary;
- acceptance semantics.

## 12. Cierre de auditoria

Resultado de la auditoria sobre el repo real:

- `_LoopTelemetry` es un lugar valido para el stall detector;
- budget puede calcularse sin modificar `RunState`;
- `RunContextSource` puede recibir `ExecutionLimits`;
- `ContextRequest` ya lo transporta;
- la policy de fase debe vivir en runtime, no en providers;
- los paths recientes se obtienen de eventos y tool results estructurados;
- el anti-loop actual no debe ser reemplazado, sino complementado.

Veredicto del documento:

`GO`

