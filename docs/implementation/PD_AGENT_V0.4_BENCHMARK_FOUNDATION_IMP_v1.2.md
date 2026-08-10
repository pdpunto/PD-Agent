# PD Agent v0.4 --- Benchmark Foundation --- IMP

**Status:** Implementation Plan\
**Version:** 1.2\
**Milestone:** PD Agent v0.4 --- Benchmark Foundation\
**Depends on:** DESIGN v1.0 + RFC v1.0\
**Audited baseline before planning:**
`18ba103a978c8199cf944fac1cb25091471e415d`

## 1. Objetivo

Construir PD Agent v0.4 de forma incremental, verificable y reversible.

Este IMP no autoriza implementación inmediata.

Antes de modificar código, Codex debe auditar DESIGN + RFC + IMP contra
el repositorio real y devolver discrepancias. Si existen discrepancias
materiales, los documentos se corrigen antes de implementar.

## 2. Reglas de implementación

1.  No crear un runtime benchmark paralelo.
2.  Reutilizar `RunStorage`, runtime, providers, build, artifact
    validator, Brain y Minecraft Harness.
3.  Mantener v0.1--v0.3 compatibles.
4.  Cada lote debe tener tests propios antes de avanzar.
5.  No ejecutar la comparación real Brain OFF/ON hasta que foundation +
    dataset estén cerrados.
6.  No modificar una task después de observar resultados sin
    versionarla.
7.  No introducir UI, cloud, multi-agent, nuevos providers ni
    capacidades no requeridas.
8.  No introducir scoring compuesto.
9.  Commit + push tras hitos definidos.
10. Working tree limpio al cerrar cada hito.

## 3. Archivos/módulos previstos

La auditoría Codex puede proponer ajustes de rutas antes de implementar.

Propuesta:

``` text
src/pd_agent/benchmark/
  __init__.py
  models.py
  catalog.py
  workspace.py
  storage.py
  collector.py
  classifier.py
  scheduler.py
  executor.py
  aggregator.py

benchmarks/
  datasets/
    pd-agent-fabric-brain-0.4.1.json
  tasks/
    B001-v1.json
    B002-v1.json
    B003-v1.json
  fixtures/
    ...

tests/unit/
  test_benchmark_models.py
  test_benchmark_catalog.py
  test_benchmark_workspace.py
  test_benchmark_classifier.py
  test_benchmark_collector.py
  test_benchmark_scheduler.py
  test_benchmark_aggregator.py
  test_benchmark_executor.py

scripts/benchmark/
  run_v0_4.py

docs/design/
  PD_AGENT_V0.4_BENCHMARK_FOUNDATION_DESIGN.md

docs/rfc/
  PD_AGENT_V0.4_BENCHMARK_FOUNDATION_RFC.md

docs/implementation/
  PD_AGENT_V0.4_BENCHMARK_FOUNDATION_IMP.md

docs/validation/
  PD_AGENT_V0.4_VALIDATION.md
```

No crear archivos vacíos solo para cumplir esta lista.

## 4. Lote 0 --- Auditoría documental contra repo

### Objetivo

Validar que DESIGN/RFC/IMP son compatibles con el estado real del
repositorio.

### Codex debe comprobar

-   rutas reales;
-   package conventions;
-   CLI/bootstrap;
-   RunController;
-   RunStorage;
-   RunState;
-   FinalReport;
-   provider metadata/usage;
-   Brain ON/OFF construction;
-   KnowledgeTrace;
-   fixture copy/reset;
-   Gradle cache;
-   MinecraftTestRunner;
-   pass policy;
-   tests existentes;
-   validation runners;
-   nombres y tipos de errores;
-   serialización existente.

### Resultado

Informe de:

-   compatible;
-   discrepancia menor;
-   discrepancia material;
-   cambios documentales necesarios.

### Prohibido

Modificar código.

### Gate

No comenzar Lote 1 hasta que ChatGPT revise y acepte la auditoría.

Durante la auditoría previa pueden existir como untracked únicamente los documentos v0.4 entregados para revisión (`DESIGN`, `RFC`, `IMP`) si su contenido coincide exactamente con la especificación auditada. Eso no se considera contaminación de implementación. Cualquier otro cambio o archivo inesperado sí bloquea el inicio.

## 5. Lote 1 --- Core benchmark models + serialization

### Objetivo

Crear contratos estables y serializables sin ejecutar todavía ningún
benchmark real.

### Implementar

-   enums:
    -   `BenchmarkExecutionStatus`;
    -   `BenchmarkTaskOutcome`;
    -   `BenchmarkFailureOrigin`;
    -   códigos de fallo necesarios;
-   `BenchmarkDataset`;
-   `BenchmarkTask`;
-   `BenchmarkConfig`;
-   `BenchmarkRun`;
-   `BenchmarkComparison`;
-   estructuras de métricas;
-   `schema_version`;
-   canonical serialization;
-   config hashing.

### Requisitos

-   secretos excluidos;
-   timestamps/paths temporales excluidos de config identity;
-   round-trip JSON;
-   unknown/incompatible schema rechazado;
-   tipos inmutables cuando sea razonable.

### Tests

-   serialization round-trip;
-   stable hash;
-   secret exclusion;
-   semantic config change alters hash;
-   runtime-only value does not alter hash;
-   enum validation;
-   schema rejection.

### Aceptación

Suite nueva PASS + suite existente relevante PASS.

### Commit

Sí.

Commit sugerido:

`feat: add benchmark core models`

Push obligatorio.

## 6. Lote 2 --- Catalog + task/dataset identity

### Objetivo

Cargar datasets/tasks declarativos y verificar identidad.

### Implementar

-   loader de dataset;
-   loader de task;
-   manifest validation;
-   duplicate ID/version detection;
-   fixture reference validation;
-   canonical fixture hashing;
-   exclusiones deterministas;
-   task identity;
-   dataset identity.

### Restricciones

-   manifests sin código arbitrario;
-   paths resueltos bajo benchmark roots autorizados;
-   fixture hash reproducible.

### Tests

-   valid manifests;
-   invalid schema;
-   missing task;
-   duplicate task;
-   missing fixture;
-   path escape;
-   fixture hash stable;
-   ignored build/cache directories do not alter canonical hash;
-   source change alters hash.

### Aceptación

Catálogo puede cargar un dataset mínimo de test y detectar drift.

### Commit

Puede agruparse con Lote 3 si ambos son pequeños y coherentes; de lo
contrario commit propio.

## 7. Lote 3 --- Workspace isolation

### Objetivo

Garantizar que cada run parte de fixture limpia y no contamina otras
runs.

### Implementar

-   workspace creation;
-   canonical fixture copy;
-   ignored directories;
-   metadata;
-   before/after source fixture verification;
-   per-run output roots;
-   cleanup policy;
-   harness workspace separation cuando aplique.

### Política

La fixture canónica nunca se modifica.

Cada intento físico obtiene workspace nuevo.

### Tests

-   two workspaces independent;
-   mutation in A not visible in B;
-   canonical fixture unchanged;
-   generated build output excluded from source identity;
-   cleanup removes disposable workspace;
-   keep-evidence/debug option, si se justifica, no cambia semántica.

### Aceptación

Aislamiento reproducible demostrado.

### Commit

Sí tras Lotes 2--3.

Commit sugerido:

`feat: add benchmark catalog and workspace isolation`

Push obligatorio.

## 8. Lote 4 --- Collector + provider/knowledge metrics

### Objetivo

Normalizar evidencia existente sin duplicar el runtime.

### Implementar

Collector capaz de extraer:

-   run ID;
-   task;
-   final state;
-   termination reason;
-   build attempts;
-   final build;
-   artifact;
-   tool-call count;
-   tool names;
-   agent steps;
-   duration;
-   provider;
-   model;
-   effective public config;
-   usage;
-   Brain enabled;
-   retrieved;
-   selected;
-   injected;
-   provenance refs;
-   environment/version identity;
-   Minecraft result cuando exista.

### Extensión mínima permitida

Si provider/model/usage se pierden antes de llegar a evidencia durable,
extender únicamente el punto común mínimo necesario.

No rediseñar provider contracts salvo necesidad demostrada.

### Reglas

-   `null` si no existe;
-   no inventar cero;
-   retrieval/selected/injected separados;
-   cross-check de datos duplicados.

### Tests

-   complete evidence;
-   missing usage;
-   missing provider metadata;
-   Brain OFF;
-   Brain ON;
-   tool names from events;
-   build count consistency;
-   evidence inconsistency detection.

### Aceptación

Una run existente/fixture de test puede transformarse en métricas
normalizadas.

### Commit

Sí.

Commit sugerido:

`feat: collect benchmark run metrics`

Push obligatorio.

## 9. Lote 5 --- Failure classifier

### Objetivo

Separar fallo del agente de bloqueos externos.

### Implementar

Clasificación determinista para:

-   provider auth;
-   rate limit;
-   timeout;
-   unavailable;
-   build environment;
-   agent build failure;
-   agent functional failure;
-   execution limit;
-   harness crash;
-   harness timeout;
-   harness infra error;
-   benchmark contamination/inconsistency;
-   unknown.

### Regla

El classifier no consulta a un LLM.

### Tests

Tabla exhaustiva:

`input evidence → execution status → outcome → origin → code`

Casos críticos:

-   generated code fails compilation = valid agent FAIL;
-   Gradle unavailable = BLOCKED;
-   provider auth = BLOCKED;
-   wrong Minecraft behavior = valid agent FAIL;
-   harness infrastructure broken = BLOCKED;
-   contradictory evidence = INVALID.

### Aceptación

Todos los casos del DESIGN tienen clasificación inequívoca o `UNKNOWN`
explícito.

### Commit

Puede agruparse con Lote 4 si la revisión demuestra alta cohesión; no
mezclar con executor.

## 10. Lote 6 --- Scheduler + repetition policy

### Objetivo

Generar orden reproducible e intercalado.

### Implementar

-   Task × Config × repetitions expansion;
-   scheduling seed;
-   OFF/ON interleaving;
-   attempt identity;
-   replacement scheduling;
-   `target_valid_repetitions`;
-   `max_attempts_per_cell`;
-   schedule persistence.

### Tests

-   expected matrix size;
-   deterministic same scheduling seed;
-   different scheduling seed may change order;
-   no systematic all-OFF-then-all-ON;
-   blocked attempt preserved;
-   replacement does not overwrite original;
-   attempt limit enforced.

### Aceptación

Para 3 × 2 × 3 produce 18 runs objetivo y un schedule auditable.

### Commit

No obligatorio separado; puede integrarse con aggregator si sigue siendo
pequeño.

## 11. Lote 7 --- Aggregator + comparison output

### Objetivo

Agregar runs sin reejecutarlas.

### Implementar

Por task/config:

-   attempted;
-   valid;
-   pass;
-   fail;
-   blocked;
-   invalid;
-   target valid;
-   complete;
-   success rate;
-   mediana/min/max:
    -   duration;
    -   tool calls;
    -   builds;
    -   agent steps;
    -   tokens;
    -   cost cuando exista.

Global:

-   macro success rate por task;
-   tasks incluidas;
-   incomplete cells;
-   comparison status.

### Reglas

-   blocked no entra en success denominator;
-   invalid no entra;
-   incomplete visible;
-   no overall score;
-   no winner universal;
-   JSON + Markdown.

### Tests

-   3/3;
-   2/3 incomplete;
-   blocked replacement;
-   all blocked;
-   mixed PASS/FAIL;
-   tie;
-   null usage;
-   null cost;
-   equal task weighting;
-   aggregation does not mutate raw runs.

### Aceptación

Comparación sintética completa e inconclusa generadas correctamente.

### Commit

Sí tras Lotes 6--7.

Commit sugerido:

`feat: add benchmark scheduling and aggregation`

Push obligatorio.

## 12. Lote 8 --- Single-run benchmark executor

### Objetivo

Conectar foundation al runtime real.

### Implementar

Pipeline:

`task + config` → workspace → runtime PD Agent → objective validation →
collector → classifier → BenchmarkRun persistido

### Requisitos

-   obtener `underlying_run_id`;
-   RunStorage normal;
-   `SecurePathResolver` y `ToolExecutor` normales del runtime;
-   Brain construction según config;
-   provider normal;
-   build normal;
-   artifact normal;
-   Minecraft runner normal;
-   no lógica específica B001 hardcodeada en executor.

### Brain OFF

Debe demostrar:

-   `brain_enabled=false`;
-   no external retrieval ejecutado para esa run;
-   injected external knowledge = 0.

### Brain ON

Debe demostrar:

-   pipeline real;
-   provenance;
-   métricas retrieved/selected/injected.

### Tests

Primero providers fake/deterministas.

Cubrir:

-   successful build-only test task;
-   failed agent task;
-   blocked provider;
-   OFF;
-   ON;
-   evidence correlation;
-   fixture isolation.

### Aceptación

Una task de prueba puede ejecutarse end-to-end sin provider live.

### Commit

Sí.

Commit sugerido:

`feat: execute isolated benchmark runs`

Push obligatorio.

## 13. Lote 9 --- Benchmark execution runner

### Objetivo

Ejecutar dataset completo según schedule.

### Implementar

Comando/script documentado que:

1.  carga dataset;
2.  carga configs;
3.  preflight;
4.  crea execution root;
5.  crea schedule;
6.  ejecuta secuencialmente;
7.  conserva blocked/invalid;
8.  crea replacements dentro del límite;
9.  agrega;
10. genera JSON/Markdown.

### CLI

Codex decidirá tras auditoría si:

-   extender `pd-agent benchmark ...`;
-   o usar `scripts/benchmark/run_v0_4.py`.

Preferencia: mínima integración que respete convenciones existentes.

### Tests

-   dry/synthetic execution;
-   interruption leaves prior evidence;
-   resume no requerido en v0.4 salvo que sea trivial;
-   failed cell does not erase other cells;
-   final comparison references all attempts.

### Aceptación

Dataset sintético ejecutable de principio a fin.

### Commit

Puede agruparse con Lote 8 si revisión lo justifica, pero se prefiere
hito separado si el diff crece.

## 14. Lote 10 --- Dataset real B001/B002/B003

### Objetivo

Congelar el dataset inicial antes de observar resultados comparativos.

### B001

Adaptar limpiamente la tarea de registry lookup de v0.3 a
manifest/fixture benchmark.

No depender del hardcode de `validate_v0_3.py`.

### B002

Crear una tarea distinta de cambio de API sensible a versión.

### B003

Crear una tarea multi-symbol/version-sensitive algo más compleja.

### Para B002/B003

Antes de ejecutar Brain OFF/ON, Codex debe entregar:

-   prompt;
-   fixture diff/base;
-   API/símbolos involucrados;
-   criterio objetivo;
-   harness assertion;
-   justificación de diferencia respecto a B001;
-   análisis de sesgo.

ChatGPT debe aprobar las tres tasks antes de ejecutar resultados
comparativos.

### Tests

Cada task debe demostrar que:

-   fixture baseline build/harness es válido;
-   acceptance detecta solución correcta;
-   acceptance rechaza comportamiento incorrecto;
-   reset produce hash original.

### Aceptación

Dataset `0.4.1` congelado y versionado.

### Commit

Sí.

Commit sugerido:

`test: add v0.4 benchmark dataset`

Push obligatorio.

## 15. Lote 11 --- Dry validation completa

### Objetivo

Validar foundation antes de gastar runs live.

### Ejecutar

-   suite unit benchmark;
-   integración fake provider;
-   workspace isolation;
-   classifier;
-   scheduler;
-   aggregation;
-   cada fixture;
-   build;
-   harness;
-   redaction;
-   evidence integrity.

### Gate

No ejecutar Brain OFF/ON live hasta PASS completo.

### Commit

Solo si requiere fixes.

## 16. Lote 12 --- Brain OFF vs Brain ON live benchmark

### Objetivo

Primera comparación real v0.4.

### Configuración

Dos configs idénticas salvo:

`brain_enabled=false` `brain_enabled=true`

Fijar y registrar:

-   provider;
-   model;
-   config;
-   PD Agent commit;
-   dataset version;
-   fixture hashes;
-   environment;
-   scheduling seed;
-   target repetitions = 3;
-   max attempts.

### Objetivo

18 runs válidas:

`3 tasks × 2 configs × 3`

Pueden existir más intentos físicos por blocked runs.

### Prohibido

-   editar tasks;
-   cambiar acceptance;
-   borrar runs desfavorables;
-   repetir manualmente solo los FAIL;
-   cambiar provider/model entre lados;
-   cambiar Brain tras observar resultado.

### Salida

-   raw benchmark runs;
-   raw PD Agent evidence;
-   comparison JSON;
-   comparison Markdown.

### Criterio

No importa quién gane.

Importa que la comparación sea válida.

## 17. Lote 13 --- Análisis y validación

### ChatGPT revisará

-   completitud;
-   blocked/invalid;
-   evidence refs;
-   OFF realmente OFF;
-   ON realmente ON;
-   fixture hashes;
-   config hashes;
-   runs válidas;
-   métricas;
-   ausencia de cherry-picking;
-   interpretación de resultados.

### Codex ejecutará regresión

-   v0.1;
-   v0.1.1;
-   v0.2;
-   v0.3;
-   suite completa;
-   v0.4 benchmark tests.

### Resultado esperado

No se exige Brain ON \> OFF.

Se exige infraestructura PASS.

## 18. Lote 14 --- Documentación final

Actualizar/crear:

-   validation v0.4;
-   benchmark usage;
-   dataset description;
-   interpretation limitations;
-   master/roadmap solo cuando Dirección cierre milestone.

Debe documentarse:

-   comando exacto;
-   environment;
-   dataset;
-   configs;
-   resultados;
-   blocked/invalid;
-   evidence locations;
-   commit validado.

## 19. Lote 15 --- Commit/push final

### Requisitos

-   tests PASS;
-   regressions PASS;
-   working tree limpio;
-   `HEAD == origin/main`;
-   docs coherentes;
-   evidence summary conservada.

Commit sugerido:

`docs: validate benchmark foundation v0.4`

Push obligatorio.

No cerrar milestone antes de confirmar SHA remoto.

## 20. Estrategia de commits

Mínimo recomendado:

1.  `feat: add benchmark core models`
2.  `feat: add benchmark catalog and workspace isolation`
3.  `feat: collect benchmark run metrics`
4.  `feat: add benchmark scheduling and aggregation`
5.  `feat: execute isolated benchmark runs`
6.  `test: add v0.4 benchmark dataset`
7.  fixes/validation si son necesarios
8.  `docs: validate benchmark foundation v0.4`

No hacer commits artificiales si un lote no produjo cambios.

No acumular toda v0.4 en un único commit.

## 21. Rollback

Cada lote debe ser aditivo.

Si un lote falla:

-   revertir su commit;
-   conservar runtime previo;
-   no alterar evidencia histórica;
-   no continuar al siguiente lote.

Cambios necesarios en componentes existentes deben ser pequeños y
cubiertos por regresión.

## 22. Criterios de aceptación de implementación

La implementación se considera completa cuando:

-   modelos benchmark estables;
-   manifests versionados;
-   fixture identity estable;
-   workspaces aislados;
-   collector funcional;
-   classifier funcional;
-   scheduler reproducible;
-   aggregator funcional;
-   executor usa runtime real;
-   Brain OFF no hace retrieval externo;
-   Brain ON conserva provenance;
-   dataset de 3 tasks congelado;
-   ejecución live completada;
-   resultados agregados;
-   evidence trazable;
-   regresiones PASS;
-   documentación final;
-   commit/push confirmados.

## 23. Orden obligatorio

``` text
Lote 0  Auditoría
   ↓
Lote 1  Models
   ↓
Lotes 2–3 Catalog + Isolation
   ↓
Lotes 4–5 Collector + Classifier
   ↓
Lotes 6–7 Scheduler + Aggregator
   ↓
Lotes 8–9 Executor + Runner
   ↓
Lote 10 Dataset
   ↓
Lote 11 Dry Validation
   ↓
Lote 12 Live OFF/ON
   ↓
Lote 13 Analysis + Regression
   ↓
Lote 14 Docs
   ↓
Lote 15 Final commit/push
```

No saltar directamente al benchmark live.

## 24. Gate inmediato

El siguiente paso tras aprobar este IMP es:

**Auditoría Codex de DESIGN + RFC + IMP contra el repo real.**

Codex NO debe implementar durante esa auditoría.

Si detecta una discrepancia material:

1.  detener implementación;
2.  presentar evidencia;
3.  proponer corrección;
4.  volver a ChatGPT;
5.  actualizar documentos;
6.  auditar de nuevo si procede;
7.  solo entonces comenzar Lote 1.
