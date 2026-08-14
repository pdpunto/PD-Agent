# PD Agent v0.4 - Fabric Agent Action Transition RFC Delta

**Status:** READY FOR IMPLEMENTATION - audited against repository reality
**Milestone:** PD Agent v0.4 - Benchmark Foundation  
**Scope:** Delta sobre el runtime existente. No new provider contracts, no dataset changes, no Brain changes.

## 1. Problema

La smoke live de B001 mostro exploration drift:

- 25 agent steps consumidos;
- 24 tool calls;
- todas las herramientas fueron de exploracion;
- no hubo mutacion;
- no hubo build;
- el run termino en `LIMIT_REACHED`.

Esto ocurre con Brain OFF y Brain ON.

El runtime ya tiene estados de fase como:

- `PLANNING`
- `EDITING`
- `BUILDING`
- `DIAGNOSING`
- `CORRECTING`
- `VALIDATING_ARTIFACT`

El problema no es la existencia de fases, sino la ausencia de una politica de transicion efectiva cuando el provider solo devuelve inspeccion.

En el estado actual, `PLANNING` puede encadenar mas inspeccion y volver a pedir al provider sin una senal operacional clara de que debe pasar a una accion concreta.

## 2. Objetivo del delta

Introducir una politca provider-neutral de transicion de accion que:

1. permita investigacion suficiente;
2. evite exploracion indefinida;
3. haga visible budget y progreso;
4. empuje hacia una accion concreta cuando ya hay evidencia suficiente;
5. prefiera validar pronto con build;
6. permita seguir investigando si existe un blocker tecnico real;
7. no codifique conocimiento especifico de B001;
8. funcione igual con Brain OFF y Brain ON.

## 3. No objetivos

No implementar en este delta:

- planner complejo;
- multi-agent;
- nuevos providers;
- cambios al dataset o a acceptance;
- hardcode de B001;
- conocimiento especifico como `Registries.BLOCK`;
- aumento de `max_agent_steps`;
- RAG adicional;
- cambios en Brain contracts;
- cambios en security o tool contracts;
- forcing ciego de `write_file`.

## 4. Auditoria del repo real

La auditoria contra el repo real confirma que este delta cabe en el runtime actual sin un redesign:

- `RunState` ya persiste `agent_step_count`, `tool_call_count`, `logical_provider_request_count`, `build_attempt_count`, `changed_files`, `current_plan` y `termination_reason`.
- `ExecutionLimits` ya incluye `max_agent_steps`, `max_tool_calls`, `max_build_attempts`, `provider_retry_limit`, `process_timeout_seconds`, `max_tool_output_bytes` y `max_context_bytes`.
- `ContextRequest` ya transporta `limits`.
- `ContextManager.build_context(..., limits=...)` ya pasa esos limites al stack de contexto.
- `RunController` ya propaga `limits` desde benchmark/runtime hacia `AgentRuntime`.
- `AgentRuntime` ya tiene `_LoopTelemetry` para anti-loop de no-op tool calls y build failures.
- `RunContextSource` ya existe y puede representar el estado del run y la evidencia.

Por tanto, no hace falta un Design delta nuevo. El cambio es de policy, telemetry ligera y contexto operacional.

## 5. Concepto: Phase Action Policy

La propuesta es introducir una politica pequena y provider-neutral que se inyecte en cada request cognitiva.

La politica debe incluir, como minimo:

- fase actual;
- objetivo operativo de la fase;
- budget usado/maximo/restante;
- progreso observado;
- inspection streak;
- resumen corto de paths y tools recientes;
- regla explicita de escalacion cuando la investigacion ya consume demasiados pasos.

Ejemplo conceptual:

```text
Current phase: PLANNING

Goal:
Gather only enough evidence to choose and execute the next concrete action.

Budget:
agent_steps_used
agent_steps_max
agent_steps_remaining
tool_calls_used
tool_calls_max
tool_calls_remaining
build_attempts_used
build_attempts_max
build_attempts_remaining

Progress:
files_changed
build_attempted
consecutive_inspection_steps
recent_inspection_tools
recent_inspected_paths

Policy:
- Inspect only information directly required for the task.
- Do not repeat equivalent exploration without new evidence.
- Once evidence is sufficient, perform a concrete modification.
- Prefer an early build after a plausible implementation.
- Use actual build errors as evidence for subsequent correction.
- Exploration alone is not progress.
```

## 6. Progress model

Cuenta como progreso operacional:

- mutacion real de archivo;
- creacion o eliminacion real;
- build ejecutado;
- cambio de fase;
- build error nuevo o diferente durante reparacion;
- artifact validation;
- blocker explicito verificable.

No cuenta como progreso por si solo:

- texto distinto del assistant;
- otra lectura de archivo;
- otra busqueda;
- otra lista de directorio;
- repetir exploracion equivalente.

## 7. Inspection step

Definir `inspection-only step` como un agent step donde:

- todas las tool calls ejecutadas son de inspeccion;
- no existe mutacion;
- no se ejecuta build;
- no aparece progreso operacional.

Las tools inicialmente clasificadas como inspeccion son:

- `list_directory`
- `read_file`
- `search_text`

La clasificacion debe vivir en una autoridad centralizada del runtime, no en nombres de task.

## 8. Exploration telemetry

La politica necesita telemetria ligera por run, idealmente basada en runtime state ya existente:

- `consecutive_inspection_steps`
- `recent_inspection_tools`
- `recent_inspected_paths`
- `last_progress_step`
- `action_pressure_level`

La recomendacion es mantener esta telemetria en runtime efimero, probablemente junto a `_LoopTelemetry` o en una estructura paralela pequena, y resetearla cuando haya progreso real.

No hace falta introducir un subsistema persistente grande si la informacion puede derivarse con limpieza en runtime.

## 9. Action escalation

No forzar escritura tras un numero rigido de reads.

Usar escalado gradual:

Nivel normal:

- politica general visible;
- budget visible;
- resumen de exploracion visible.

Tras varias inspecciones consecutivas sin progreso:

```text
ACTION REQUIRED:
Investigation has consumed several consecutive steps.
Use the evidence already gathered to perform a concrete action or attempt
a build, unless a specific unresolved blocker requires further inspection.
```

La implementacion exacta del umbral pertenece al IMP interno, pero la logica debe ser conservadora y no romper tareas complejas.

## 10. Budget visibility

Cada request debe mostrar:

- usados;
- maximo;
- restantes.

Como minimo:

- agent steps;
- tool calls;
- build attempts.

La fuente del budget no debe inventarse en el provider. Debe venir del runtime y del `ExecutionLimits` ya existentes.

## 11. Exploration history summary

Para evitar depender del historial completo del provider, el runtime debe exponer un resumen compacto de:

- tools de inspeccion recientes;
- paths ya inspeccionados;
- consultas recientes cuando tenga sentido;
- numero de inspection-only steps;
- files changed;
- builds realizados.

Debe ser acotado y determinista.

## 12. Phase semantics

### PLANNING

Objetivo:

Obtener evidencia suficiente para elegir una accion.

Salida esperada:

- mutacion;
- o decision explicita de probar build;
- o blocker verificable.

No debe convertirse en exploracion abierta.

### EDITING

Objetivo:

Realizar cambios concretos.

### BUILDING

Runtime determinista.

### DIAGNOSING

Inspeccion permitida si esta dirigida por un error real de build.

### CORRECTING

Aplicar una correccion concreta y volver a build.

La policy debe tratar `DIAGNOSING` distinto de `PLANNING`: un build error nuevo justifica mas inspeccion.

## 13. Runtime authority

Se mantiene el invariante existente:

- el Runtime decide estados y limites;
- el modelo decide el contenido tecnico de la solucion;
- el provider solo transporta mensajes y tool protocol.

No se introduce un planner que controle todo el proceso.

## 14. Anti-loop

Hay protecciones actuales contra:

- repeated no-op tool result;
- repeated build failure.

Este delta añade una defensa distinta:

- exploration stall detection.

Debe detectar drift incluso cuando las tools no sean identicas. Ejemplo:

- `list_directory A`
- `read_file B`
- `search_text C`
- `list_directory D`
- `read_file E`

puede ser un stall aunque los fingerprints no sean iguales.

Primera respuesta al stall:

- escalado de policy;
- no necesariamente terminar el run de inmediato.

Si persiste hasta una condicion severa definida por IMP, puede terminar con una razon explicita como:

`exploration stalled without operational progress`

## 15. Brain

Brain ON/OFF no cambia esta policy.

Knowledge retrieval puede aportar evidencia, pero no controla fases.

La Action Transition Policy debe aplicarse identicamente con Brain OFF y ON.

## 16. Provider neutrality

No introducir logica en:

- `GeminiProvider`;
- `OpenAIProvider`.

El provider solo transporta mensajes y continuations.

La policy pertenece al runtime/contexto provider-neutral.

## 17. Observabilidad

Persistir suficiente informacion para auditar:

- phase;
- steps used/remaining;
- inspection streak;
- escalation activa;
- progreso observado.

Preferir eventos y metadata existentes antes de crear un subsistema nuevo.

Si hace falta un evento nuevo, debe justificarse.

## 18. Compatibilidad

No cambia:

- Tool contract;
- ModelProvider boundary;
- Brain contracts;
- benchmark dataset;
- PASS semantics;
- security boundary;
- `max_agent_steps` en la configuracion benchmark.

## 19. Action Tool Selection Contract

Este contrato refina la seleccion de herramientas de mutacion para evitar
reintentos innecesarios cuando el archivo ya existe.

### write_file

Semantica visible:

- modificar o reemplazar el contenido de un archivo EXISTENTE;
- usarla para paths ya existentes;
- si el archivo fue leido u observado como existente, preferir `write_file`;
- no crea archivos nuevos.

### create_file

Semantica visible:

- crear exclusivamente un path NUEVO;
- el target no debe existir;
- nunca usarla para modificar o reemplazar un archivo existente;
- si el target existe, usar `write_file`.

### Observed path guidance

`recent_inspected_paths` constituye evidencia operacional de que esos paths han
sido observados dentro del workspace.

La policy debe decir explicitamente:

- un archivo observado como existente debe tratarse como existing target;
- no usar `create_file` sobre un existing observed file.

No convertir esto en una base de datos persistente compleja.

## 20. Retained Inspection Evidence

Este contrato a�ade una memoria de trabajo efimera, bounded y provider-neutral
para archivos leidos con exito. No es una base de datos, no es RAG y no
reconstruye el historial completo del run.

### 20.1 Modelo retenido

La evidencia retenida debe poder representarse como una estructura pequena
adjunta al runtime, idealmente cerca de `_LoopTelemetry` o como un helper
adyacente al runtime. La forma minima recomendada es una estructura interna con
campos:

- `path`;
- `kind = file`;
- `content` o `excerpt` bounded;
- `truncated`;
- `observed_step`;
- `bytes_total` opcional si aporta valor real.

No es necesario persistir todo en `RunState`.

### 20.2 Capture and rendering

La captura debe ocurrir cuando `read_file` devuelve `SUCCESS`. La fuente
estructurada ya existe en el resultado del tool:

- `path`;
- `content`;
- `truncated`;
- `bytes_total`.

El punto de captura recomendado en el repo real es `AgentRuntime._execute_tool_calls()`,
justo despues de recibir el `ToolResult` exitoso y antes de continuar con la
observacion de progreso.

La renderizacion recomendada debe entrar en contexto como una fuente pequena
de runtime, preferiblemente junto a `RunContextSource` dentro de
`ContextManager`. El runtime ya dispone de `ContextRequest.limits` y
`ContextManager.build_context(..., limits=...)`, asi que la fuente puede
combinarse con el budget visible sin tocar providers.

### 20.3 Limits and eviction

La evidencia retenida debe ser bounded y determinista. Recomendacion:

- max retained files: 8;
- max excerpt per file: 4096 bytes;
- max total retained evidence bytes: 24576 bytes;
- eviction: oldest-first por `observed_step`, con desempate estable por `path`;
- si el mismo `path` se vuelve a leer, actualizar la entrada existente y su
  recency, no crear duplicados infinitos.

Los limites reales deben respetar tambien `max_context_bytes`.

### 20.4 Persistence

La evidencia retenida debe vivir solo durante el run actual.

Debe:

- sobrevivir a varias provider requests;
- seguir visible aunque el `ToolResult` original ya no este en el historial
  inmediato;
- resetearse al comenzar un run nuevo;
- no requerir una tabla persistente nueva;
- no guardarse como memoria entre runs.

### 20.5 Action gate and Brain

La retencion de evidencia no debilita el Action Gate.

- inspection tools siguen cerrandose igual cuando corresponde;
- retained evidence sigue visible en ACTION_REQUIRED / FOCUSED_ACTION /
  ACTION_ONLY;
- el modelo puede hacer zero-tool call si la evidencia ya es suficiente;
- Brain OFF y Brain ON comparten la misma policy de retencion;
- Brain ON puede sumar conocimiento externo, pero no sustituye la evidencia
  factual observada del proyecto actual.

## 21. Mutation Target Policy

La policy de mutacion debe preferir el cambio minimo respaldado por la evidencia
ya inspeccionada.

Normativa:

- preferir editar el archivo o simbolo explicitamente implicado por la tarea;
- preferir archivos directamente soportados por evidencia inspeccionada;
- preservar estructura, declaraciones y contratos no relacionados salvo que la
  tarea o la evidencia verificada exijan cambiarlos;
- preservar metadata/configuracion/entrypoints salvo que esten realmente
  implicados;
- no modificar un archivo no relacionado solo para satisfacer action pressure;
- al reescribir un archivo existente, preservar el contenido y los contratos
  publicos no objetivo del cambio;
- bajo incertidumbre razonable, un build del estado actual es preferible a una
  mutacion especulativa no respaldada.

No escribir reglas especificas como "never edit fabric.mod.json". La regla debe
aplicar a cualquier manifest, config, Gradle file, source, JSON o metadata.

## 22. Criterio de aceptacion RFC

El fix queda aceptado cuando:

1. tests offline demuestran que `PLANNING` puede explorar de forma legitima;
2. budget y progreso llegan al provider;
3. exploration drift activa escalation;
4. progreso real resetea el stall;
5. diagnosis/build repair sigue funcionando;
6. no existe hardcode B001;
7. Brain OFF/ON usan la misma policy;
8. suite completa sigue PASS;
9. una smoke live B001 con `max_agent_steps = 25` deja de consumir sistematicamente todo el budget solo en exploration;
10. antes de agotar el budget aparece progreso operacional:

- mutacion real;
- build;
- o blocker explicito verificable.

B001 no tiene que dar PASS funcional.

## 23. Recoverable rejection contract

La distincion entre rejection fatal y recoverable debe ser estructurada, no por
parsing de texto.

Para v0.4, solo se autoriza recovery especifico de:

- `create_file` sobre un path que ya existe.

La normalizacion minima recomendada puede vivir en `ToolExecutor` y/o en la
metadata estructurada del `ToolResult`, por ejemplo con un
`rejection_code = "file_exists"`.

La tool sigue rechazando la operacion y no sobrescribe nada. El runtime puede
usar ese codigo para permitir una unica request de correccion en lugar de
terminar la run de inmediato.

Siguen siendo fatales:

- `SecurityViolation`;
- traversal;
- absolute/external path;
- protected mutation;
- schema invalido;
- unknown tool;
- otras validation failures que no tengan recovery explicito.

La policy de `action_only` no cambia sus thresholds. Si ocurre `FILE_EXISTS`:

- mantener `action_only` durante la oportunidad de recovery;
- `create_file` y `write_file` siguen ofrecidas;
- inspection tools siguen no disponibles;
- la primera rejection recuperable no cuenta como progreso;
- una mutacion valida posterior resetea la recovery y permite build;
- repetir `FILE_EXISTS` sin progreso termina de forma controlada con una razon
  explicita.

La razon recomendada es:

- `repeated recoverable tool rejection without operational progress`

No introducir heuristica por texto si puede evitarse.
