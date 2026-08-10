# PD Agent v0.4 --- Benchmark Foundation --- RFC

**Status:** RFC\
**Version:** 1.2\
**Milestone:** PD Agent v0.4 --- Benchmark Foundation\
**Depends on:** `PD_AGENT_V0.4_BENCHMARK_FOUNDATION_DESIGN.md`\
**Baseline audited:** `18ba103a978c8199cf944fac1cb25091471e415d`

**Post-audit correction:** v1.2 alinea el boundary de seguridad con los componentes reales `SecurePathResolver` + `ToolExecutor`.

## 1. Propósito

Este RFC define cómo implementar técnicamente la Benchmark Foundation de
PD Agent v0.4 sin crear un runtime paralelo.

La arquitectura debe reutilizar el pipeline existente de PD Agent y
añadir únicamente la capa necesaria para:

`catalogar → preparar → ejecutar → observar → normalizar → repetir → agregar → comparar`

La primera comparación soportada será Brain OFF vs Brain ON.

## 2. Decisiones arquitectónicas

### D1 --- Benchmark como capa de orquestación

El benchmark no implementará su propio agente, build system, provider
layer, Brain ni Minecraft runner.

Usará las capacidades existentes de PD Agent.

### D2 --- Evidence existente sigue siendo autoridad primaria

`run.json`, `events.jsonl`, `final-report.json`, `evidence/`, `builds/`
y Minecraft evidence siguen siendo la evidencia operacional primaria.

Los archivos benchmark serán índices/resultados normalizados derivados y
deberán contener referencias hacia la evidencia original.

### D3 --- Contratos benchmark separados del RunState

No se inflará `RunState` con conceptos exclusivos de benchmarking.

Se crearán modelos benchmark propios que referencien
`underlying_run_id`.

Solo se extenderá reporting/provider persistence común cuando el dato
también sea útil fuera del benchmark y la auditoría de implementación
confirme que es la opción mínima correcta.

### D4 --- Dataset declarativo y versionado

Las tareas se definirán mediante manifests versionados en el
repositorio.

No se codificarán como `if task == ...` dentro del runner.

### D5 --- Ejecutor secuencial en v0.4

Las runs se ejecutarán secuencialmente.

No habrá paralelismo.

Esto reduce contaminación de:

-   Gradle;
-   Minecraft;
-   puertos;
-   provider rate limits;
-   caches;
-   logs.

### D6 --- Sin scoring compuesto

El agregador produce métricas descriptivas y comparaciones directas.

No existe `overall_score`.

## 3. Módulos conceptuales

Se propone un paquete:

`src/pd_agent/benchmark/`

con responsabilidades separadas.

### `models`

Contratos serializables:

-   `BenchmarkDataset`;
-   `BenchmarkTask`;
-   `BenchmarkConfig`;
-   `BenchmarkRun`;
-   `BenchmarkComparison`;
-   enums de estado/fallo;
-   métricas normalizadas.

### `catalog`

Carga y valida manifests de datasets/tasks.

Responsabilidades:

-   resolver dataset;
-   verificar IDs/versiones;
-   comprobar referencias a fixtures;
-   calcular/verificar identidad de task/fixture;
-   rechazar manifests inválidos.

### `workspace`

Prepara aislamiento por run.

Responsabilidades:

-   crear workspace nuevo;
-   copiar fixture;
-   excluir outputs no canónicos;
-   preparar harness cuando corresponda;
-   calcular hashes;
-   verificar que la fixture origen no cambia;
-   cleanup.

### `executor`

Orquesta una única `BenchmarkRun`.

Responsabilidades:

1.  recibir task + config + repetition index;
2.  preparar workspace;
3.  capturar environment/version identity;
4.  configurar Brain/provider/runtime;
5.  ejecutar PD Agent normal;
6.  ejecutar validaciones objetivas requeridas;
7.  recolectar referencias a evidence;
8.  clasificar execution status/outcome;
9.  persistir resultado benchmark.

No implementa lógica interna del agente.

### `collector`

Normaliza métricas desde fuentes existentes.

Lee, según aplique:

-   `RunState`;
-   `FinalReport`;
-   eventos;
-   KnowledgeTrace;
-   provider evidence;
-   build results;
-   artifact result;
-   MinecraftTestResult.

Debe preferir fuentes autoritativas definidas.

### `classifier`

Convierte estados/errores existentes en:

-   execution status;
-   task outcome;
-   failure origin;
-   failure code.

No usa juicio del LLM.

### `scheduler`

Genera el orden de repeticiones.

Para comparación OFF/ON:

-   intercala configuraciones;
-   evita ejecutar todos los casos de una configuración
    consecutivamente;
-   registra el orden final.

No ejecuta en paralelo.

### `aggregator`

Agrega `BenchmarkRun` persistidos.

Responsabilidades:

-   agrupar por task/config;
-   contar valid/pass/fail/blocked/invalid;
-   calcular success rate sobre valid runs;
-   medianas;
-   rangos;
-   usage;
-   coste cuando sea válido;
-   macro-agregado con igual peso por tarea;
-   detectar celdas incompletas/inconclusas.

### `storage`

Gestiona artifacts benchmark.

No sustituye `RunStorage`.

## 4. Layout de almacenamiento

Propuesta:

``` text
benchmark-runs/
  <benchmark-execution-id>/
    manifest.json
    schedule.json

    runs/
      <benchmark-run-id>/
        benchmark-run.json
        workspace-metadata.json

    comparison.json
    comparison.md
```

La evidencia operacional del agente permanece en el `RunStorage`
configurado para esa ejecución.

`benchmark-run.json` contiene `underlying_run_id` y referencias
explícitas.

No se copiarán innecesariamente todos los logs/evidence dentro de la
capa benchmark.

## 5. Identidades

### 5.1 Dataset identity

Formato lógico:

`dataset_id + dataset_version`

Ejemplo:

`pd-agent-fabric-brain / 0.4.1`

La representación textual exacta se fijará en implementación tras
auditar convenciones del repo.

### 5.2 Task identity

`task_id + task_version`

Una task version queda asociada a:

-   prompt exacto;
-   fixture identity;
-   acceptance contract.

### 5.3 Config identity

`BenchmarkConfig` se serializa de forma canónica excluyendo:

-   API keys;
-   secretos;
-   paths temporales;
-   IDs de run;
-   timestamps.

Se calcula:

`config_hash = SHA-256(canonical_json)`

### 5.4 Fixture identity

Debe basarse en contenido relevante, no solo nombre de directorio.

La implementación elegirá un hash determinista del árbol canónico
excluyendo:

-   `.git`;
-   `build`;
-   `.gradle`;
-   temporales;
-   outputs conocidos.

El algoritmo y exclusiones quedan registrados/versionados.

### 5.5 Benchmark run ID

Debe ser único por ejecución física.

No debe derivarse únicamente de task/config porque existen repeticiones.

## 6. Manifests

Se propone almacenamiento versionado bajo:

``` text
benchmarks/
  datasets/
  tasks/
  fixtures/
```

La auditoría Codex previa a implementación deberá validar la ubicación
exacta contra convenciones reales.

### Dataset manifest

Conceptualmente:

``` json
{
  "schema_version": 1,
  "id": "pd-agent-fabric-brain",
  "version": "0.4.1",
  "tasks": [
    {"id": "B001", "version": "1"},
    {"id": "B002", "version": "1"},
    {"id": "B003", "version": "1"}
  ]
}
```

### Task manifest

Conceptualmente:

``` json
{
  "schema_version": 1,
  "id": "B001",
  "version": "1",
  "description": "...",
  "prompt": "...",
  "fixture": "...",
  "validation": {
    "build": true,
    "artifact": true,
    "minecraft": true
  },
  "acceptance": {
    "type": "...",
    "spec": "..."
  },
  "environment": {
    "minecraft": "1.21.11"
  },
  "tags": ["fabric", "brain", "version-sensitive"]
}
```

No se aceptará código arbitrario embebido en manifests.

## 7. Flujo de una benchmark execution

### Fase A --- Preflight

1.  validar repo/commit esperado;
2.  validar dataset;
3.  validar tasks;
4.  validar fixtures;
5.  validar provider/model/config;
6.  comprobar credenciales sin persistirlas;
7.  comprobar Java/Python;
8.  comprobar requisitos de Minecraft Harness;
9.  crear execution ID;
10. persistir manifest efectivo.

Si falla aquí:

la ejecución se bloquea antes de producir resultados comparables.

### Fase B --- Schedule

Generar matriz:

`Task × Config × repetitions`

Para v0.4:

`3 × 2 × 3 = 18 valid runs objetivo`

El scheduler crea un orden intercalado reproducible y lo persiste en
`schedule.json`.

### Fase C --- Run preparation

Para cada run:

1.  generar benchmark run ID;
2.  crear workspace;
3.  copiar fixture;
4.  verificar fixture hash;
5.  preparar outputs;
6.  preparar caches según política;
7.  capturar environment snapshot.

### Fase D --- Agent execution

Crear el runtime normal con la configuración correspondiente.

Brain OFF:

-   Brain deshabilitado;
-   sin retrieval externo innecesario;
-   sin KnowledgeContextSource externo.

Brain ON:

-   pipeline Brain normal;
-   retrieval/selection/injection reales;
-   provenance preservada.

El executor obtiene el `underlying_run_id`.

### Fase E --- Objective validation

Según task:

1.  inspeccionar final runtime state;
2.  comprobar build;
3.  comprobar artifact;
4.  ejecutar Minecraft Test Harness si es obligatorio;
5.  aplicar acceptance contract.

El modelo no decide su propio PASS.

### Fase F --- Collection/classification

Collector normaliza métricas.

Classifier determina:

-   `COMPLETED/BLOCKED/INVALID`;
-   `PASS/FAIL/NOT_EVALUATED`;
-   failure origin/code.

### Fase G --- Persist

Guardar `benchmark-run.json`.

No alterar raw evidence.

### Fase H --- Completion policy

Si una celda no alcanza tres runs válidas por causas bloqueadas:

-   conservar las bloqueadas;
-   programar reemplazos hasta un límite configurable;
-   no reintentar indefinidamente.

Al agotarse el límite:

la celda queda incompleta.

### Fase I --- Aggregation

Cuando termina la ejecución:

-   generar `comparison.json`;
-   generar `comparison.md`;
-   no modificar runs individuales.

## 8. Fuentes autoritativas de métricas

Prioridad propuesta:

### Estado del agente

Autoridad:

`RunState` / `final-report.json`

Si divergen:

`INVALID` por inconsistencia de evidence, salvo que exista una regla
explícita de compatibilidad.

### Timeline y tools

Autoridad:

`events.jsonl`

De ahí se derivan:

-   tool names;
-   tool executions;
-   rejected tools;
-   secuencia temporal.

`RunState.tool_call_count` se usa como comprobación cruzada.

### Builds

Autoridad:

`RunState.build_results` + build logs/events.

### Artifact

Autoridad:

`ArtifactResult`.

### Knowledge

Autoridad:

`KnowledgeTrace` y evidence de knowledge/context.

Se separan:

-   retrieved IDs;
-   selected IDs;
-   injected/context IDs.

### Provider/model/usage

Autoridad:

metadata/usage producida por el provider y persistida en
evidence/reporting.

Si la implementación actual descarta datos necesarios, se extenderá
mínimamente la persistencia común.

### Minecraft

Autoridad:

`MinecraftTestResult` y evidence del harness.

## 9. Provider configuration

`BenchmarkConfig` debe registrar únicamente configuración no secreta que
pueda afectar resultados.

Ejemplos:

-   provider;
-   model;
-   timeout;
-   retry limit;
-   temperature si existe;
-   seed si existe;
-   max output/token config si existe;
-   execution limits.

Las API keys:

-   nunca se serializan;
-   nunca participan en hashes;
-   nunca aparecen en reports.

La configuración efectiva debe quedar congelada antes de la primera run.

## 10. Usage normalization

Se conservarán dos niveles:

### Raw provider usage

Representación sanitizada del provider cuando sea razonable.

### Common usage

Campos normalizados opcionales:

-   `input_tokens`;
-   `output_tokens`;
-   `total_tokens`.

Campos provider-specific podrán conservarse sin obligar a otros
providers a producirlos.

Ausencia de usage = `null`, nunca cero inventado.

## 11. Cost model

Coste no forma parte del PASS.

Modelo conceptual:

``` text
PricingSnapshot
provider
model
effective_date/version
source/provenance
input_unit_price
output_unit_price
other applicable prices
```

Una run solo recibe `cost` si:

1.  existe usage suficiente;
2.  existe pricing snapshot compatible;
3.  el cálculo es determinista;
4.  queda registrada la identidad del pricing.

Si no:

`cost = null`.

v0.4 puede cerrar correctamente sin pricing para todos los providers.

## 12. Failure classifier

El classifier recibe evidencia estructurada, no texto libre como fuente
principal.

Ejemplos:

### Provider auth

ProviderError.kind = authentication

→ `BLOCKED` → `NOT_EVALUATED` → `PROVIDER` → `PROVIDER_AUTH`

### Rate limit agotado

→ `BLOCKED` → `NOT_EVALUATED` → `PROVIDER` → `PROVIDER_RATE_LIMIT`

### Código generado no compila

Provider y entorno funcionaron; build falla por cambios del agente.

→ `COMPLETED` → `FAIL` → `AGENT` → `AGENT_BUILD_FAILURE`

### JAR válido pero comportamiento Minecraft incorrecto

→ `COMPLETED` → `FAIL` → `AGENT` → `AGENT_FUNCTIONAL_FAILURE`

### Minecraft server no arranca por fallo del harness

→ `BLOCKED` → `NOT_EVALUATED` → `MINECRAFT_HARNESS` → código
correspondiente.

### Evidence contradictoria

→ `INVALID` → `NOT_EVALUATED` → `BENCHMARK_INFRA` →
`BENCHMARK_CONTAMINATION` o inconsistency code.

## 13. Acceptance contracts

El benchmark debe soportar validadores objetivos componibles.

Tipos mínimos conceptuales:

-   build required;
-   artifact required;
-   Minecraft test required;
-   fixture/source condition cuando sea imprescindible.

No se implementará un lenguaje de assertions general.

Para v0.4 bastan contratos explícitos y limitados.

Una task define qué comprobaciones son necesarias.

Todas deben pasar para `TaskOutcome.PASS`.

## 14. Política de caches

### Gradle

Debe existir política estable por benchmark execution.

No se compararán configuraciones con políticas de cache distintas.

El workspace siempre será nuevo aunque pueda existir un cache Gradle
controlado compartido.

### Brain

Para Brain ON debe definirse explícitamente si el benchmark mide:

-   cold retrieval;
-   warm cache.

v0.4 utilizará una única política consistente para todas las
repeticiones comparables.

Decisión propuesta: **cache de conocimiento preestablecida/controlada
por execution cuando sea necesario para evitar medir disponibilidad de
red como calidad del Brain**, conservando provenance y registrando el
estado de cache.

La auditoría Codex deberá confirmar la forma mínima compatible con
`FileKnowledgeCache` y v0.3.

Brain OFF no ejecutará retrieval.

### Minecraft

No se reutiliza world/runtime state entre runs.

## 15. Repeticiones y replacement runs

Config:

`target_valid_repetitions = 3`

También existirá un límite de intentos físicos por celda.

Conceptualmente:

`max_attempts_per_cell > target_valid_repetitions`

Una run bloqueada sigue persistida.

Una replacement run recibe nuevo benchmark run ID y nuevo
repetition/attempt identity.

El agregador distingue:

-   intentos físicos;
-   runs válidas utilizadas;
-   runs bloqueadas;
-   runs inválidas.

No existe cherry-picking manual.

## 16. Scheduling

El scheduler recibe:

-   tasks;
-   configs;
-   target repetitions;
-   optional scheduling seed.

Debe producir una secuencia donde las configuraciones estén
intercaladas.

La scheduling seed solo controla el orden del benchmark, no la
generación del LLM.

`schedule.json` permite reproducir el orden.

## 17. Aggregation schema

Por `task × config`:

``` text
attempted
valid
pass
fail
blocked
invalid
target_valid
complete

success_rate
duration_median
duration_min
duration_max
tool_calls_median/min/max
builds_median/min/max
agent_steps_median/min/max
tokens_median/min/max
cost_median/min/max (optional)
```

### Macro comparison

Para success:

1.  calcular success rate por task/config;
2.  macro-promediar las tasks completas con peso igual;
3.  informar cuántas tasks entraron.

No se ocultarán tasks incompletas.

Para métricas de eficiencia se mostrarán agregados descriptivos,
evitando combinaciones que mezclen unidades o tareas de dificultad
diferente sin contexto.

## 18. Comparison status

El comparison report podrá distinguir al menos:

-   `COMPLETE`;
-   `INCOMPLETE`;
-   `INCONCLUSIVE`.

`COMPLETE` significa que existe la cantidad objetivo de runs válidas
para las celdas requeridas.

No significa que exista ganador.

`INCONCLUSIVE` puede usarse cuando la evidencia completa no distingue
claramente las configuraciones bajo las reglas descriptivas definidas.

El RFC no introduce tests estadísticos de significancia.

## 19. Output humano y machine-readable

### JSON

Fuente derivada para automatización futura.

Debe contener:

-   identidad;
-   configuración sanitizada;
-   resultados por task;
-   agregados;
-   refs de runs/evidence.

### Markdown

Resumen legible.

Debe evitar afirmaciones como:

"Brain ON es mejor"

salvo que se limite explícitamente al dataset/configuración observados.

Formato esperado:

> En `dataset X`, con `provider/model Y`, Brain ON obtuvo A y Brain OFF
> B.

No generalizar fuera de la evidencia.

## 20. CLI / entry point

v0.4 necesita una forma reproducible de lanzar benchmarks.

Forma conceptual:

``` text
pd-agent benchmark run ...
pd-agent benchmark compare ...
```

o entry point/script equivalente si extender la CLI principal introduce
acoplamiento innecesario.

La decisión exacta se tomará en IMP/auditoría contra la CLI existente.

Requisito:

-   una ejecución debe poder iniciarse mediante comando documentado;
-   dataset/config deben quedar explícitos;
-   no depender de edición manual de Python.

## 21. Dataset v0.4

### B001

Se puede derivar del escenario v0.3, eliminando hardcodes del validation
runner.

### B002 y B003

Deben definirse antes de ejecutar comparación real.

Codex deberá inspeccionar APIs/fixtures reales y proponer
implementaciones que cumplan el DESIGN:

-   distintas de B001;
-   version-sensitive;
-   automáticamente verificables;
-   pequeñas;
-   no diseñadas para favorecer Brain ON.

La selección definitiva deberá quedar documentada antes de observar
resultados OFF/ON.

## 22. Seguridad

Benchmark Foundation reutiliza el boundary de seguridad real del runtime mediante `SecurePathResolver` y `ToolExecutor`.

No introduce una capa de seguridad paralela ni una abstracción nueva.

No relaja:

-   path boundaries;
-   tool permissions;
-   redaction;
-   secret handling.

Los workspaces benchmark deben seguir bajo roots autorizados.

Evidence benchmark también debe pasar por sanitización/redaction cuando
contenga datos provenientes del provider/config.

## 23. Compatibilidad y schema evolution

Todos los manifests/resultados benchmark tendrán `schema_version`.

Cambios incompatibles de serialización requieren incremento de schema.

Dataset/task version y schema version son conceptos distintos:

-   schema version = formato;
-   task/dataset version = significado experimental.

Resultados antiguos nunca deben reinterpretarse silenciosamente bajo un
schema nuevo incompatible.

## 24. Validación interna de consistencia

Antes de aceptar una `BenchmarkRun` como válida se comprobará, cuando
aplique:

-   underlying run existe;
-   IDs coinciden;
-   final report existe;
-   build count coherente;
-   tool-call count razonablemente coherente con eventos;
-   artifact evidence existe;
-   harness evidence existe si requerido;
-   fixture hash coincide con el esperado;
-   config hash coincide;
-   no se modificó fixture canónica.

Inconsistencia material:

`ExecutionStatus.INVALID`.

## 25. Testing de v0.4

### Unit tests

Deben cubrir:

-   serialization/deserialization;
-   canonical config hashing;
-   fixture hashing;
-   manifest validation;
-   classifier;
-   collector;
-   aggregation;
-   scheduling;
-   incomplete cells;
-   blocked runs;
-   invalid runs;
-   no cost without pricing;
-   no usage fabrication;
-   Brain OFF knowledge counts;
-   redaction.

### Integration tests

Deben cubrir:

-   workspace isolation;
-   run correlation;
-   evidence collection;
-   build/artifact acceptance;
-   Minecraft acceptance donde sea viable;
-   OFF/ON configuration separation.

### Regression

Deben seguir pasando:

-   v0.1;
-   v0.1.1;
-   v0.2;
-   v0.3;
-   suite general.

## 26. Observabilidad del benchmark

Cada benchmark execution debe registrar suficiente información para
explicar:

-   qué iba a ejecutarse;
-   en qué orden;
-   qué realmente se ejecutó;
-   qué quedó bloqueado;
-   qué replacements se hicieron;
-   qué runs se agregaron;
-   por qué una comparación quedó completa/incompleta.

No hace falta un nuevo sistema complejo de logging.

JSON/Markdown + evidencia existente son suficientes.

## 27. Rollback conceptual

Benchmark Foundation debe ser aditiva.

No debe exigir migrar o invalidar runs normales existentes.

Si la implementación v0.4 se revierte:

-   runtime normal sigue funcionando;
-   v0.1--v0.3 no dependen del benchmark;
-   benchmark artifacts pueden permanecer como evidence histórica.

## 28. Riesgos técnicos

### R1 --- Duplicación de reporting

Mitigación: benchmark almacena referencias y métricas normalizadas; no
replica todo RunStorage.

### R2 --- Clasificación incorrecta de build failure

Mitigación: classifier usa evidencia de preflight/environment y
resultado real, con tests explícitos.

### R3 --- Cache sesga comparación

Mitigación: política única, persistida y auditable.

### R4 --- Fixture drift

Mitigación: hash canónico y workspace copy-on-run.

### R5 --- Provider drift

Mitigación: registrar provider/model/config y timestamps; no afirmar
reproducibilidad absoluta del servicio externo.

### R6 --- Dataset demasiado favorable al Brain

Mitigación: tres tareas distintas, selección previa y versionado
inmutable.

### R7 --- Benchmark demasiado grande

Mitigación: tres tasks, dos configs y tres runs válidas por celda.

## 29. Extensión futura

Sin cambiar los contratos principales debería ser posible crear:

``` text
Config A = Gemini + Brain ON
Config B = OpenAI + Brain ON

Config C = modelo local + Brain OFF

Config D = estrategia de contexto X
Config E = estrategia de contexto Y
```

El benchmark no necesita conocer semánticamente qué variable se está
comparando.

Solo ejecuta configuraciones explícitas y conserva su identidad.

## 30. Arquitectura final propuesta

``` text
Benchmark manifests
        │
        ▼
     Catalog
        │
        ▼
    Scheduler
        │
        ▼
 Benchmark Executor
        │
   ┌────┴──────────────┐
   ▼                   ▼
Workspace          PD Agent Runtime
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
         Provider    Tools      Brain
                       │
                       ▼
                    Build
                       │
                       ▼
                   Artifact
                       │
                       ▼
              Minecraft Harness
                       │
   ┌───────────────────┘
   ▼
RunStorage / raw evidence
   │
   ▼
Collector + Classifier
   │
   ▼
BenchmarkRun
   │
   ▼
Aggregator
   │
   ▼
BenchmarkComparison
(JSON + Markdown)
```

## 31. Decisión RFC

La implementación v0.4 deberá seguir estas reglas:

1.  benchmark es una capa aditiva;
2.  runtime actual permanece autoridad de ejecución;
3.  raw evidence no se reemplaza;
4.  manifests identifican experimentos;
5.  workspaces aíslan runs;
6.  classifier separa agent failure de infraestructura;
7.  collector normaliza sin inventar;
8.  scheduler controla repeticiones;
9.  aggregator describe, no fabrica un score;
10. Brain OFF/ON es la primera comparación, no una limitación
    arquitectónica.

El siguiente documento obligatorio es el **IMP**, que convertirá este
RFC en lotes concretos, archivos previstos, orden, tests, criterios de
aceptación, commits y rollback.
