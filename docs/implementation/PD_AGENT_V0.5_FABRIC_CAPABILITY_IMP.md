# PD Agent v0.5 --- Fabric Agent Capability Foundation --- IMP

**Estado:** DRAFT FOR REPO AUDIT\
**Milestone:** PD Agent v0.5 --- Fabric Agent Capability Foundation\
**Área propietaria:** 04 --- Fabric Agent\
**DESIGN autoritativo:**
`docs/design/PD_AGENT_V0.5_FABRIC_CAPABILITY_DESIGN.md`\
**RFC autoritativo:** `docs/rfc/PD_AGENT_V0.5_FABRIC_CAPABILITY_RFC.md`

## 1. Objetivo de implementación

Construir y validar la primera capability representativa de trabajo
Fabric útil para un usuario:

> Dado un proyecto Fabric existente, válido y compilable, y una petición
> funcional en lenguaje natural, PD Agent debe poder implementar una
> feature Fabric server-observable no trivial, preservar contratos no
> relacionados, compilar, producir un JAR válido y demostrar el
> comportamiento solicitado en Minecraft real.

La implementación será incremental y auditada lote por lote.

No se autoriza implementar varios lotes importantes sin revisión de
ChatGPT.

## 2. Alcance

Incluido:

-   proyecto Fabric existente y compilable;
-   modificación de source existente;
-   creación de archivos nuevos;
-   feature multiarchivo;
-   resources/data cuando la tarea lo requiera;
-   API Minecraft/Fabric;
-   build;
-   diagnóstico/corrección de errores derivados de la feature;
-   artifact validation;
-   Minecraft runtime evidence;
-   benchmark/acceptance reproducible;
-   provider real en live validation.

Fuera:

-   creación de proyecto Fabric desde cero;
-   reparación general de proyectos previamente rotos;
-   Multi-Agent;
-   Model Router;
-   SaaS/UI/billing;
-   expansión multi-version;
-   expansión general del Brain;
-   rediseño general de Build & Debug;
-   rediseño general del Minecraft Test Harness.

## 3. Regla de auditoría previa

Antes de implementar cada lote:

1.  verificar `HEAD`, `origin/main` y working tree;
2.  auditar DESIGN + RFC + este IMP contra el repo real;
3.  comprobar rutas, módulos, contratos y tests afectados;
4.  si aparece discrepancia material, detener el lote;
5.  corregir documentación antes de seguir.

No inventar estado del repo.

## 4. Estrategia de implementación

v0.5 se divide en:

-   F0 --- Freeze técnico y baseline v0.5
-   F1 --- Proyecto base representativo pinned
-   F2 --- Dataset/acceptance contract v0.5
-   F3 --- Multi-file capability audit + mínimo runtime delta si hace
    falta
-   F4 --- Minecraft Harness extension mínima
-   F5 --- Acceptance adapters y functional evaluation
-   F6 --- Dataset oficial v0.5 con 3 tareas
-   F7 --- Offline validation completa
-   F8 --- Live smoke / readiness
-   F9 --- Matriz oficial v0.5
-   F10 --- Cierre documental y handoff a Dirección

Los lotes deben ejecutarse en ese orden salvo propuesta explícita de
cambio del IMP.

------------------------------------------------------------------------

# F0 --- Freeze técnico y baseline v0.5

## Objetivo

Congelar el estado técnico desde el que parte v0.5 y confirmar que v0.4
sigue íntegro.

## Trabajo

Auditar:

-   branch y SHA;
-   suite completa;
-   versiones actuales;
-   benchmark v0.4 PASS;
-   Fabric Agent Action Transition;
-   retained evidence;
-   mutation-target policy;
-   Brain OFF/ON;
-   Harness;
-   Gradle environment reproducible.

Congelar versiones iniciales:

-   Minecraft `1.21.11`
-   Fabric Loader `0.19.3`
-   Fabric Loom `1.13.3`
-   Yarn `1.21.11+build.6`
-   Java `21`
-   Gradle Wrapper compatible con proyecto base

## Archivos

Preferentemente solo documentación/validation metadata.

Posibles:

-   `docs/validation/PD_AGENT_V0.5_BASELINE.md`
-   validation script pequeño si hace falta.

## Tests

-   suite completa actual;
-   validaciones v0.4 relevantes;
-   no API.

## Acceptance

PASS si:

-   v0.4 sigue verde;
-   no hay regresiones;
-   baseline reproducible;
-   versiones congeladas;
-   tracked tree limpio.

## Git

Commit sugerido:

`docs: freeze v0.5 technical baseline`

------------------------------------------------------------------------

# F1 --- Proyecto base representativo pinned

## Objetivo

Introducir un proyecto Fabric existente, convencional, reproducible y no
diseñado alrededor de las soluciones de benchmark.

## Decisión de producto

El proyecto base debe ser:

-   pequeño;
-   realista;
-   compilable;
-   Fabric convencional;
-   con source/resources normales;
-   con metadata/entrypoint real;
-   sin helpers que revelen soluciones;
-   pinned por revisión/hash.

Preferencia:

derivar de un template/proyecto Fabric representativo pinned,
conservando estructura real y eliminando solo elementos no necesarios
para reproducibilidad.

No descargar dinámicamente durante cada benchmark.

## Auditoría antes de incorporar

Comparar:

-   `tests/fixtures/l11_fabric_fixture`
-   `benchmarks/fixtures/*`
-   candidato representativo pinned

Determinar si se reutiliza algo o se incorpora base nuevo.

## Archivos previstos

Ejemplo:

-   `benchmarks/projects/v0_5_fabric_base/...`
-   `benchmarks/projects/v0_5_fabric_base/PROVENANCE.md`
-   manifest/metadata de identidad del proyecto

La ruta exacta debe adaptarse a convenciones reales del repo.

## Identity

Persistir al menos:

-   project revision/hash;
-   tree hash;
-   Minecraft;
-   Loader;
-   Loom;
-   mappings;
-   Java;
-   Gradle Wrapper.

## Validation

Sobre copia temporal:

1.  `ProjectInspector == READY`
2.  wrapper completo
3.  build baseline PASS
4.  artifact VALID
5.  runtime sanity si aplica
6.  source canónico no modificado

## Acceptance

El proyecto base debe compilar y poder ser usado por las tres tareas sin
contener implementación de ninguna de ellas.

## Git

Commit sugerido:

`test: add pinned representative Fabric base project`

------------------------------------------------------------------------

# F2 --- Dataset / acceptance contract v0.5

## Objetivo

Definir el contrato de task y acceptance para Existing Fabric Feature
Development antes de escribir las tareas definitivas.

## Trabajo

Extender/reutilizar modelos benchmark para representar:

-   requisito user-facing;
-   project base ref;
-   task-specific starting delta si aplica;
-   behavioral acceptance;
-   runtime observation contract;
-   preservation invariants;
-   evidence requirements.

No codificar solución.

## Regla de independencia

Acceptance no puede exigir:

-   nombre exacto de clase salvo requisito;
-   API exacta;
-   estructura interna exacta;
-   solución de referencia textual;
-   número exacto de archivos.

Sí puede exigir:

-   comportamiento observable;
-   invariantes de preservación;
-   build/artifact/runtime válidos.

## Failure mapping

Reutilizar taxonomía existente:

-   PASS → `COMPLETED + PASS`
-   FUNCTIONAL_FAIL → `COMPLETED + FAIL`
-   AGENT_FAIL → failure origin `AGENT` + código adecuado
-   BLOCKED → `BLOCKED`
-   INVALID → `INVALID`

No introducir enum nuevo sin necesidad.

## Archivos previstos

Posibles:

-   `src/pd_agent/benchmark/models.py`
-   `src/pd_agent/benchmark/catalog.py`
-   `src/pd_agent/benchmark/classifier.py`
-   tests asociados

Solo si el modelo actual no expresa el contrato.

## Tests

-   schema válido;
-   task sin solución hardcoded;
-   preservation invariants serializables;
-   runtime contract serializable;
-   backward compatibility v0.4.

## Acceptance

El modelo benchmark debe representar las tasks v0.5 sin alterar
semántica v0.4.

## Git

Commit sugerido:

`feat: define v0.5 feature-development benchmark contract`

------------------------------------------------------------------------

# F3 --- Multi-file capability audit + mínimo runtime delta

## Objetivo

Demostrar que el runtime puede implementar una feature coherente que
requiera más de un archivo antes del primer build.

## Auditoría crítica

El runtime actual tiende a:

-   inspeccionar;
-   primera mutación con progreso;
-   transición temprana hacia build.

Primero probar si una única provider response con múltiples tool calls
coherentes es suficiente.

## Regla

NO implementar un planner nuevo ni una fase compleja de batching de
entrada.

Orden de decisión:

### Opción A --- Sin runtime delta

Si el provider puede emitir:

-   `write_file`
-   `create_file`
-   `write_file`

en una misma respuesta y el runtime ejecuta el conjunto antes de build,
mantener arquitectura.

### Opción B --- Delta mínimo

Solo si pruebas offline muestran que la capability representativa no
puede realizar cambios multiarchivo coherentes de forma fiable por el
tránsito inmediato a build.

Delta permitido:

un mecanismo pequeño de `continue_editing` / mutation batch limitado y
provider-neutral.

Debe:

-   estar acotado;
-   respetar limits;
-   no reabrir exploración ilimitada;
-   no cambiar Action Gate thresholds;
-   no introducir planner complejo;
-   terminar en build temprano.

## Archivos previsibles si hace falta

-   `src/pd_agent/runtime/engine.py`
-   tests L9/context

## Tests obligatorios

1.  una response con múltiples mutations se ejecuta completa;
2.  source + new file antes de build;
3.  source + resource antes de build;
4.  retained evidence permanece coherente;
5.  mutation target policy preservada;
6.  Action Gate sin regresión;
7.  FILE_EXISTS recovery sin regresión;
8.  build llega después del conjunto coherente.

## Acceptance

Preferencia fuerte: **cerrar F3 sin cambio runtime** si la arquitectura
actual ya soporta el caso.

## Handoff

Si la única forma de hacer multiarchivo exige rediseño grande del loop,
volver a ChatGPT antes de implementar.

## Git

Si no hay cambios, no commit.

Si hay delta:

`feat: support bounded multi-file feature edits`

------------------------------------------------------------------------

# F4 --- Minecraft Harness extension mínima

## Objetivo

Permitir observar las familias v0.5 sin convertir el Harness en parte de
la solución.

## Auditoría

Probar qué puede observar el Harness actual:

-   mod load;
-   target entrypoint;
-   runtime invocation;
-   registry/state;
-   comportamiento server-side.

Clasificar cada familia candidata:

-   soportada por contrato actual;
-   requiere extensión mínima;
-   requiere rediseño material.

## Regla

Solo implementar extensión mínima.

No sustituir `MinecraftTestRunner`.

No crear un harness genérico nuevo.

## Forma preferida

Añadir observadores/acciones de runtime genéricos, por ejemplo
conceptualmente:

-   lookup de registry;
-   comprobación de presencia;
-   invocación server-side;
-   estado esperado;
-   resultado estructurado.

No hardcodear task IDs en el runner core.

Task-specific expectations deben venir del spec/acceptance.

## Archivos previsibles

Dependiendo de auditoría:

-   `src/pd_agent/minecraft/contracts.py`
-   `src/pd_agent/minecraft/runner.py`
-   fixture/harness Java existente
-   tests Minecraft Batch correspondientes

## Seguridad

Preservar:

-   target validation;
-   hash;
-   mod id;
-   versions;
-   confined paths;
-   timeout;
-   evidence files.

## Tests

-   harness actual sigue PASS;
-   nueva observación genérica;
-   target incorrecto rechazado;
-   feature FAIL funcional diferenciada de infra;
-   no helper solución dentro del target.

## Handoff 06

Si una familia exige rediseño material:

STOP.

Reportar a 06.

## Git

Commit sugerido:

`feat: extend Minecraft harness for v0.5 feature observation`

------------------------------------------------------------------------

# F5 --- Acceptance adapters + functional evaluation

## Objetivo

Conectar las tasks v0.5 con el Harness sin meter semántica específica en
Fabric Agent core.

## Ubicación

Preferencia:

benchmark/acceptance layer.

No runtime core.

## Responsabilidad

Por task:

-   construir runtime observation spec;
-   entregar expectations;
-   leer evidence;
-   producir PASS/FAIL funcional;
-   verificar invariantes de preservación.

## Prohibido

-   modificar el workspace para facilitar PASS;
-   generar solución;
-   decir al agente qué API usar;
-   hardcodear task-specific behavior en `AgentRuntime`.

## Archivos previstos

Posibles:

-   `src/pd_agent/benchmark/acceptance.py`
-   `src/pd_agent/benchmark/executor.py`
-   `src/pd_agent/minecraft/contracts.py`
-   tests benchmark/Minecraft

La ruta exacta depende del repo real.

## Tests

-   adapter deterministic;
-   PASS real;
-   functional FAIL;
-   agent-caused non-evaluable failure;
-   harness infra BLOCKED;
-   preservation invariant violation;
-   evidence consistency.

## Acceptance

Un mismo runtime puede ejecutar tasks diferentes cambiando solo
task/acceptance data.

## Git

Commit sugerido:

`feat: evaluate v0.5 Fabric features at runtime`

------------------------------------------------------------------------

# F6 --- Dataset oficial v0.5

## Objetivo

Congelar mínimo 3 tasks representativas.

## Requisitos conjuntos

Las tres tasks deben cubrir:

-   source existente;
-   archivo nuevo;
-   multiarchivo;
-   API Fabric/Minecraft;
-   resource/data en al menos una;
-   runtime server-side;
-   preservation.

## Familias candidatas

### T1 --- Registro / contenido simple

Requisito user-facing que implique registrar contenido y comprobar su
presencia/propiedad en runtime.

### T2 --- Feature source + resource/data

Requisito que obligue a combinar código y recursos/data.

### T3 --- Comportamiento server-side

Requisito con lógica runtime observable y estado/resultado determinista.

No fijar implementación exacta desde este IMP.

## Diseño de prompts

Prompts:

-   conductuales;
-   naturales;
-   sin archivos/API solución;
-   sin helper names del Harness;
-   sin acceptance leakage.

## Fixture strategy

Cada task parte del mismo proyecto base pinned o de una variante mínima
derivada reproduciblemente.

No crear tres proyectos artificiales completamente distintos salvo
necesidad.

## Dataset identity

Congelar:

-   dataset id;
-   version;
-   task versions;
-   project hash;
-   acceptance hashes;
-   config hashes.

## Validation

-   lint/schema;
-   fixture contamination;
-   no hardcodes en runtime;
-   baseline build;
-   acceptance dry-run;
-   Harness preflight.

## Git

Commit sugerido:

`test: freeze v0.5 Fabric capability dataset`

------------------------------------------------------------------------

# F7 --- Offline validation completa

## Objetivo

Demostrar toda la capability sin provider real usando fakes controlados
y casos sintéticos/fixtures reales.

## Cobertura

### Runtime

-   multi-file mutations;
-   create + write;
-   build;
-   diagnose/correct;
-   artifact;
-   context bounds;
-   Action Gate;
-   retained evidence.

### Benchmark

-   3 tasks cargables;
-   scheduler;
-   configs;
-   replacements;
-   collector;
-   classifier;
-   aggregator.

### Minecraft

-   runtime adapter;
-   PASS;
-   functional FAIL;
-   harness crash;
-   infra error.

### Security

-   traversal;
-   protected paths;
-   target jar containment;
-   no shell;
-   secret redaction.

## Suite

Ejecutar:

-   compileall;
-   tests focalizados;
-   suite completa.

No API.

## Acceptance

Todo PASS antes de live.

## Git

Commit según fixes necesarios del lote.

------------------------------------------------------------------------

# F8 --- Live smoke / readiness

## Objetivo

Probar una task representativa con provider real antes de lanzar matriz.

## Regla de coste

No ejecutar matriz directamente.

Primero:

1.  precheck sin API;
2.  una smoke;
3.  revisar evidence;
4.  corregir solo si hay bug real;
5.  repetir de forma controlada si se autoriza.

## Selección

Elegir una task suficientemente representativa, no la más fácil.

Preferencia:

feature multiarchivo con runtime observation.

## Evidencia

Registrar:

-   provider/model;
-   task;
-   Brain mode;
-   steps;
-   tools;
-   retained evidence;
-   mutations;
-   builds;
-   artifact;
-   Minecraft;
-   functional result;
-   usage/coste si disponible.

## Readiness

GO si:

-   no regression;
-   modificación relevante;
-   build/harness infrastructure íntegra;
-   evidence consistente;
-   resultado evaluable.

No exigir necesariamente PASS funcional en la primera smoke para
demostrar readiness.

## Git

No modificar código durante smoke.

------------------------------------------------------------------------

# F9 --- Matriz oficial v0.5

## Objetivo

Ejecutar la validación live oficial del milestone.

## Matriz

El número exacto de configs/repeticiones se congela antes del
lanzamiento.

Propuesta inicial a validar contra coste:

-   3 tasks;
-   Brain OFF/ON solo si aporta valor experimental;
-   3 repeticiones válidas por cell.

No asumir automáticamente 18 runs si Brain comparison no es necesaria
para el criterio principal.

Antes de ejecutar, Dirección/04 debe congelar explícitamente:

-   provider/model;
-   configs;
-   repetitions;
-   replacement policy;
-   pacing;
-   request budget;
-   limits;
-   expected cost envelope.

## Regla

No cambiar dataset/config después de observar resultados oficiales salvo
invalidación formal y nueva versión.

## Criterio estadístico

Se definirá antes del launch.

Como mínimo:

-   cada task debe tener evidencia válida;
-   ninguna capability se declara demostrada solo por una run aislada;
-   invalid/blocked no cuentan como PASS;
-   failures deben separarse por origen.

## Resultado

Persistir:

-   execution root;
-   dataset/config identity;
-   run evidence;
-   aggregate;
-   summary;
-   comparison si aplica.

------------------------------------------------------------------------

# F10 --- Cierre v0.5

## Objetivo

Cerrar milestone solo con evidencia completa.

## Documentación

Actualizar:

-   validation report;
-   DESIGN/RFC/IMP status;
-   benchmark summary;
-   architecture docs si cambió algún boundary;
-   README si la capability afecta uso visible.

## Criterios de cierre

v0.5 queda:

**IMPLEMENTADO + LIVE VALIDATED + PASS**

solo si:

1.  3 tareas representativas congeladas;
2.  proyecto base pinned;
3.  suite offline PASS;
4.  provider real usado;
5.  mutaciones reales;
6.  feature multiarchivo demostrada;
7.  build real;
8.  artifact válido;
9.  Minecraft real;
10. comportamiento funcional observado;
11. evidencia persistida;
12. ausencia de hardcodes task-specific en runtime;
13. seguridad intacta;
14. benchmark reproducible;
15. commit + push;
16. HEAD == origin/main;
17. working tree tracked limpio.

## Handoff final

Al cerrar:

volver a **00 --- Dirección / Master Plan** con:

-   estado oficial;
-   capability demostrada;
-   métricas;
-   límites conocidos;
-   siguiente milestone candidato.

------------------------------------------------------------------------

# 5. Secuencia de commits recomendada

Como referencia:

1.  `docs: freeze v0.5 technical baseline`
2.  `test: add pinned representative Fabric base project`
3.  `feat: define v0.5 feature-development benchmark contract`
4.  opcional `feat: support bounded multi-file feature edits`
5.  `feat: extend Minecraft harness for v0.5 feature observation`
6.  `feat: evaluate v0.5 Fabric features at runtime`
7.  `test: freeze v0.5 Fabric capability dataset`
8.  fixes de offline validation si aparecen
9.  cierre documental final

No crear commits vacíos.

# 6. Rollback

Cada lote debe ser reversible por commit.

Si un lote introduce regresión:

-   no avanzar;
-   identificar commit;
-   corregir en nuevo commit o revertir de forma explícita;
-   no ocultar la regresión en lotes siguientes.

# 7. Handoffs obligatorios

## A 05 --- Build & Debug

Detener la parte afectada si:

-   baseline roto;
-   wrapper/dependencies/environment requieren reparación general;
-   repair loop actual es insuficiente estructuralmente.

## A 06 --- Minecraft Test Harness

Detener la parte afectada si:

-   observar las 3 tasks exige rediseño material del runner;
-   la extensión mínima no basta.

## A 03 --- Minecraft Brain

Solo si:

-   se demuestra gap concreto de knowledge;
-   es generalizable;
-   no es solución específica de task.

# 8. Criterio de aceptación del IMP

Este IMP está listo para implementación únicamente después de auditoría
Codex contra repo real que confirme:

-   rutas/módulos reales;
-   proyecto base strategy viable;
-   multi-file support viable;
-   no handoff inmediato 05;
-   Harness extensión mínima viable;
-   benchmark models suficientes o gap acotado;
-   lotes ejecutables en orden;
-   tests identificables;
-   no scope creep.

Resultado esperado de auditoría:

`V0_5_IMP_REPO_AUDIT_COMPLETE`

con:

`GO_FOR_IMPLEMENTATION`

o, si corresponde:

`IMP_REVISION_REQUIRED`

/ `HANDOFF_REQUIRED`.
