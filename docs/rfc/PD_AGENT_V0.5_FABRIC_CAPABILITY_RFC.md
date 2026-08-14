# PD Agent v0.5 --- Fabric Agent Capability Foundation --- RFC

**Estado:** DRAFT FOR IMP\
**Milestone:** PD Agent v0.5 --- Fabric Agent Capability Foundation\
**Área propietaria:** 04 --- Fabric Agent\
**DESIGN autoritativo:**
`docs/design/PD_AGENT_V0.5_FABRIC_CAPABILITY_DESIGN.md`

## 1. Propósito

Este RFC define cómo implementar la capability **Existing Fabric Feature
Development** de PD Agent v0.5.

El sistema debe poder recibir un proyecto Fabric existente, válido y
compilable, junto con una petición funcional en lenguaje natural, y
ejecutar de forma controlada:

inspección → selección del target → modificación multiarchivo → build →
diagnóstico/corrección → artifact → Minecraft runtime → evidencia
funcional.

El RFC no autoriza creación de proyectos desde cero ni reparación
general de proyectos rotos.

## 2. Principios arquitectónicos

v0.5 mantiene:

-   single-agent;
-   runtime Python propio;
-   core provider-neutral;
-   tools controladas;
-   filesystem confinado;
-   `SecurePathResolver`;
-   `ToolExecutor` como frontera;
-   Gradle Wrapper como única autoridad de build;
-   Minecraft Test Harness como autoridad de runtime evidence;
-   Brain opcional y separado del estado factual del proyecto;
-   reporting/evidence persistido;
-   benchmark infrastructure reutilizable;
-   Action Transition / Action Gate;
-   retained inspection evidence;
-   mutation-target preservation policy.

No se introduce Multi-Agent ni Model Router.

## 3. Flujo autoritativo v0.5

El flujo operativo es:

1.  validar precondiciones;
2.  preparar workspace;
3.  inspeccionar proyecto;
4.  construir contexto factual;
5.  planificar mínimo;
6.  inspeccionar archivos relevantes;
7.  retener evidencia necesaria;
8.  seleccionar target de mutación;
9.  modificar/crear archivos;
10. ejecutar build;
11. si falla por cambios del agente:
    -   diagnosticar;
    -   inspección dirigida;
    -   corregir;
    -   rebuild;
12. validar artifact;
13. ejecutar Minecraft Test Harness;
14. evaluar comportamiento;
15. persistir evidencia;
16. clasificar PASS / functional FAIL / agent failure / infra BLOCKED /
    INVALID.

## 4. Precondition contract

Antes de ejecutar la tarea funcional, el proyecto debe cumplir:

-   path existente;
-   directorio accesible;
-   `ProjectInspector.status == READY`;
-   Gradle Wrapper presente;
-   metadata Fabric válida;
-   target subproject resoluble;
-   baseline build válido;
-   baseline artifact válido cuando el caso lo requiera;
-   versiones soportadas/pinned;
-   workspace confinado;
-   entorno Gradle reproducible.

Si falla una precondición estructural antes de la tarea:

-   no se convierte en reparación implícita;
-   el caso se detiene como precondition/infra failure;
-   si la causa pertenece a build/debug general, se deriva a 05.

## 5. Project capability contract

### 5.1 Proyecto existente

v0.5 opera sobre proyectos existentes.

No crea:

-   Gradle Wrapper desde cero;
-   `settings.gradle*` inicial;
-   `build.gradle*` inicial;
-   estructura base Fabric completa;
-   `fabric.mod.json` inicial;
-   template de proyecto.

Puede modificar esos archivos si la feature lo requiere y existe
evidencia.

### 5.2 Proyecto representativo

El proyecto base de aceptación debe:

-   ser convencional;
-   estar pinned;
-   compilar antes de la tarea;
-   no contener helpers que revelen la solución;
-   conservar metadata/entrypoints reales;
-   permitir validación reproducible.

La selección concreta del proyecto base se cerrará en el lote de
dataset/acceptance, no en runtime.

## 6. ProjectInspector

`ProjectInspector` continúa siendo la autoridad inicial para:

-   estructura Fabric;
-   Gradle Wrapper;
-   manifests;
-   mixins;
-   source/resource roots;
-   módulos;
-   target subproject;
-   versiones detectables;
-   Git observacional.

v0.5 no requiere ejecutar Gradle durante inspection.

Si el proyecto tiene múltiples módulos Fabric ambiguos:

-   se mantiene `BLOCKED`;
-   no se añade heurística agresiva.

## 7. Context model v0.5

El contexto de cada provider request se compone de:

1.  task original;
2.  `ProjectSnapshot`;
3.  `RunState`;
4.  budget/progress;
5.  Action Transition policy;
6.  recent inspected paths;
7.  retained file evidence;
8.  pending tool results;
9.  build/diagnostic evidence;
10. Brain knowledge cuando esté habilitado;
11. external context explícito legítimo.

### 7.1 Retained factual evidence

La evidencia retenida sigue siendo:

-   efímera por run;
-   bounded;
-   provider-neutral;
-   factual;
-   derivada de tools estructuradas;
-   sometida a `max_context_bytes`.

No se convierte en memoria persistente avanzada.

### 7.2 Brain separation

Brain ON añade knowledge externo version-sensitive.

Brain OFF no debe eliminar:

-   policy runtime;
-   retained evidence;
-   progress/budget;
-   other internal context.

La única diferencia funcional OFF/ON debe ser conocimiento Brain, no
wiring del runtime.

## 8. Mutation target selection

La policy v0.5 exige:

-   priorizar el archivo/símbolo implicado por la task;
-   preferir evidencia inspeccionada;
-   aplicar el cambio mínimo plausible;
-   preservar contenido no relacionado;
-   preservar metadata, entrypoints, config y contratos públicos salvo
    necesidad demostrada;
-   no modificar archivos no relacionados solo por presión de acción;
-   usar `write_file` para existing targets;
-   usar `create_file` solo para paths nuevos;
-   bajo incertidumbre, build/no-op es preferible a una mutación
    especulativa no respaldada.

## 9. Multi-file feature support

La capability debe soportar una feature que requiera más de un archivo.

No se introduce una tool nueva específica para "feature".

Se reutilizan:

-   `read_file`;
-   `search_text`;
-   `write_file`;
-   `create_file`;
-   `delete_file`.

El runtime debe poder:

-   modificar varios archivos existentes;
-   crear nuevas clases;
-   crear/modificar resources/data;
-   mantener contexto suficiente entre steps;
-   construir después del conjunto mínimo coherente de cambios.

## 10. Build strategy

`GradleBuildRunner` continúa ejecutando únicamente el Gradle Wrapper.

Build invocation permanece cerrada.

v0.5 usa el build como feedback operacional:

-   build exitoso → artifact validation;
-   build fallido → `DIAGNOSING`;
-   diagnóstico basado en stdout/stderr real;
-   corrección → rebuild.

No se añade shell libre.

## 11. Build & Debug boundary

Dentro de v0.5:

-   compilation errors causados por la implementación;
-   imports;
-   tipos;
-   símbolos/API;
-   integración simple;
-   correcciones derivadas del build real.

Fuera:

-   baseline Gradle roto;
-   wrapper corrupto;
-   dependency resolution general no reproducible;
-   migration general;
-   reparación de proyecto previamente roto;
-   diagnóstico ambiental general.

Si un caso requiere estas capacidades, v0.5 se detiene y genera handoff
a 05.

## 12. Artifact validation

`ArtifactValidator` sigue siendo obligatorio después del build.

Un build con exit code 0 no implica PASS.

Debe seguir validando, como mínimo:

-   candidate discovery;
-   JAR legible;
-   `fabric.mod.json`;
-   id/version;
-   freshness;
-   ambiguity;
-   metadata compatible.

v0.5 no introduce ejecución del JAR durante artifact validation.

## 13. Minecraft Test Harness contract

v0.5 reutiliza el Harness actual.

No se reescribe el runner.

El Harness debe recibir:

-   artifact target;
-   target mod id;
-   versiones;
-   test id;
-   timeout;
-   acceptance/runtime contract;
-   environment reproducible.

### 13.1 Extension rule

Solo se autoriza extensión mínima si una feature representativa no puede
observarse con el contrato actual.

Una extensión permitida debe:

-   observar comportamiento, no implementación;
-   estar separada del Fabric Agent;
-   no requerir helper artificial en el target que revele la solución;
-   no cambiar el target code para hacerlo testeable;
-   no introducir una ruta privilegiada al PASS;
-   reutilizar el lifecycle y evidence model existentes.

Si hace falta rediseñar materialmente el runner, se deriva a 06.

## 14. Runtime acceptance adapter

v0.5 puede necesitar una capa mínima entre una tarea de acceptance y el
Harness.

Responsabilidad permitida:

-   describir qué comportamiento observar;
-   preparar spec de runtime;
-   leer evidencia;
-   decidir functional PASS/FAIL.

Responsabilidad prohibida:

-   decir al agente cómo implementar;
-   inyectar código solución;
-   modificar el target para que pase;
-   usar paths/clases hardcoded en runtime general.

Los detalles específicos de cada tarea pertenecen al dataset/acceptance,
no al Fabric Agent core.

## 15. Feature observability

Las features v0.5 deben ser server-observable.

Una tarea debe poder validarse mediante uno o más de:

-   registro existente en runtime;
-   estado/propiedad observable;
-   ejecución de comportamiento server-side;
-   resultado determinista emitido por el Harness;
-   interacción reproducible con el mod cargado.

No se exige GUI/client rendering en v0.5.

## 16. Benchmark dataset v0.5

Se reutiliza la infraestructura v0.4.

Se añadirá un dataset/catálogo v0.5 separado o versionado de forma
explícita.

Debe contener al menos 3 tasks de la misma familia.

Cada task define:

-   `task_id`;
-   version;
-   requisito user-facing;
-   fixture/project ref;
-   acceptance contract;
-   runtime validation contract;
-   target versions;
-   evidence requirements.

No se codifica la solución.

## 17. Variación mínima entre tasks

Las 3 tasks deben variar suficiente para evitar sobreajuste.

Conjuntamente deben cubrir:

-   editar source existente;
-   crear al menos un archivo nuevo;
-   feature multiarchivo;
-   usar API Minecraft/Fabric;
-   resource/data cuando sea razonable;
-   build;
-   Minecraft runtime;
-   preservación del proyecto.

No deben ser tres variantes superficiales del mismo literal/API.

## 18. Proyecto base pinned

El proyecto base debe tener identidad reproducible.

La identidad debe incluir al menos:

-   source revision/hash;
-   fixture/project hash;
-   Minecraft version;
-   Fabric Loader;
-   Loom;
-   mappings;
-   Gradle Wrapper version;
-   Java major.

No depender de `latest`.

Si se deriva de un template externo:

-   se incorpora una copia pinned al repo o mecanismo reproducible
    equivalente;
-   la procedencia se documenta;
-   no se descarga dinámicamente durante cada benchmark.

## 19. Version contract inicial

v0.5 no amplía soporte multi-version.

La combinación inicial debe mantenerse pinned a la línea ya validada por
el proyecto salvo auditoría contraria:

-   Minecraft 1.21.11;
-   Fabric Loader 0.19.3;
-   Fabric Loom 1.13.3;
-   Yarn 1.21.11+build.6;
-   Java 21;
-   Gradle Wrapper compatible con el proyecto base.

Las versiones definitivas se congelan al crear el fixture/proyecto base
y su validation document.

## 20. Brain contract v0.5

Brain no se expande automáticamente.

Se reutilizan:

-   retrieval;
-   selection;
-   injection;
-   provenance.

Si una task falla porque falta conocimiento externo concreto:

1.  demostrar gap;
2.  identificar fuente;
3.  documentar cambio;
4.  ampliar Brain solo si es necesario y generalizable.

Brain no puede contener soluciones específicas de las tasks.

## 21. Action Transition v0.5

Se mantienen:

-   budget/progress visibility;
-   exploration telemetry;
-   Action Gate;
-   mutation-tool selection;
-   recoverable `FILE_EXISTS`;
-   retained inspection evidence;
-   mutation-target policy.

No se ajustan thresholds por task sin un RFC delta.

La feature capability debe apoyarse en esta infraestructura, no
bypassarla.

## 22. State machine

No se introduce una state machine nueva.

Se reutilizan:

-   `PLANNING`;
-   `EDITING`;
-   `BUILDING`;
-   `DIAGNOSING`;
-   `CORRECTING`;
-   `VALIDATING_ARTIFACT`;
-   `REPORTING`;
-   terminal states.

La feature multiarchivo se representa dentro de `PLANNING/EDITING`, no
con estados por archivo.

## 23. Limits

Se reutiliza `ExecutionLimits`.

El dataset/config v0.5 puede fijar límites específicos, pero no
hardcodearlos en runtime.

Deben cubrir:

-   agent steps;
-   tool calls;
-   build attempts;
-   provider retry;
-   process timeout;
-   tool output;
-   context bytes.

Los límites exactos de live validation se congelan antes de las runs
oficiales.

## 24. Reporting

Cada run debe dejar trazabilidad suficiente:

-   run/config/task identity;
-   project baseline identity;
-   inspected files;
-   retained context metadata;
-   tool calls/results;
-   changed files;
-   build attempts;
-   diagnostics;
-   artifact;
-   Minecraft evidence;
-   functional result;
-   provider usage cuando esté disponible;
-   termination reason.

No persistir secretos.

## 25. Failure taxonomy

### PASS

Todos los criterios funcionales y técnicos se cumplen.

### FUNCTIONAL_FAIL

El run es evaluable, pero la feature no cumple el comportamiento
solicitado.

Ejemplos:

-   build PASS + Minecraft FAIL funcional;
-   implementación incorrecta pero cargable/evaluable.

### AGENT_FAIL

El agente impide completar la evaluación por sus propias acciones.

Ejemplos:

-   rompe entrypoint/config no relacionado;
-   deja proyecto sin compilar tras agotar correcciones;
-   destruye contrato necesario sin justificación.

### BLOCKED

Infra/precondition no permite evaluar de forma justa.

Ejemplos:

-   environment no reproducible;
-   Harness infra failure;
-   unsupported baseline.

### INVALID

Evidencia inconsistente, contaminación, protocolo roto u otro resultado
no confiable.

## 26. Baseline preservation

Antes de cada run oficial:

-   workspace limpio derivado del proyecto base pinned;
-   baseline build conocido;
-   baseline artifact conocido;
-   baseline runtime sanity cuando aplique.

Después:

-   cambios solo en workspace;
-   proyecto fuente/fixture canónico intacto.

## 27. Acceptance independence

La acceptance debe validar comportamiento observable.

No debe exigir:

-   nombre concreto de clase salvo que sea parte del requisito;
-   estructura interna exacta;
-   API exacta;
-   número exacto de archivos;
-   solución de referencia textual.

Puede exigir invariantes del proyecto que un cambio correcto debe
preservar.

## 28. Provider configuration

El runtime sigue siendo provider-neutral.

Las runs live pueden elegir un provider/model real.

La identidad de config debe incluir:

-   provider;
-   model;
-   Brain mode;
-   limits relevantes;
-   prompt/policy version cuando aplique.

No cambiar provider entre runs para ocultar un fallo sin registrarlo
como nueva config.

## 29. Repeticiones y criterio estadístico

El cierre del milestone no dependerá de una única run.

La implementación del dataset debe soportar repeticiones por
task/config.

El número exacto y threshold se decidirá al congelar dataset/config en
IMP, siguiendo estos principios:

-   suficiente para detectar variabilidad;
-   coste razonable;
-   runs inválidas no cuentan como PASS;
-   BLOCKED infra no se interpreta como model failure;
-   replacements controlados cuando aplique;
-   no repetir selectivamente solo failures de una config.

## 30. Seguridad

No se modifica:

-   filesystem confinement;
-   protected paths;
-   no shell;
-   tool schema validation;
-   Action Gate enforcement;
-   secret redaction;
-   path containment;
-   artifact validation boundary;
-   Harness target validation.

Las features nuevas no justifican relajar boundaries.

## 31. Componentes previsibles

v0.5 puede requerir cambios en:

-   `src/pd_agent/runtime/engine.py` solo si aparece un gap real de
    feature orchestration;
-   context system solo si falta evidencia necesaria;
-   benchmark dataset/catalog;
-   benchmark acceptance/runtime adapters;
-   fixtures/project base;
-   Minecraft Harness con extensión mínima;
-   validation scripts/docs;
-   tests.

No se presupone modificación del core/provider.

## 32. Handoffs

### A 05 Build & Debug

Obligatorio si:

-   baseline no puede hacerse válido;
-   diagnóstico necesario excede errores derivados de la feature;
-   hace falta una nueva arquitectura de build repair.

### A 06 Minecraft Test Harness

Obligatorio si:

-   las 3 tareas no pueden observarse sin rediseñar materialmente el
    runner;
-   el Harness necesita nueva arquitectura, no una extensión mínima.

### A 03 Minecraft Brain

Solo si:

-   existe gap concreto de knowledge;
-   está demostrado;
-   es generalizable;
-   no es una solución hardcoded.

## 33. Plan de validación de RFC

Antes de IMP, Codex debe auditar este RFC contra el repo real y
responder:

1.  qué componentes pueden reutilizarse sin cambios;
2.  gaps obligatorios;
3.  si multiarchivo necesita cambios runtime;
4.  si Harness actual puede observar las familias candidatas;
5.  qué extensión mínima del Harness sería suficiente;
6.  cómo incorporar proyecto base pinned;
7.  cómo modelar acceptance sin filtrar solución;
8.  si existe dependencia real con 05;
9.  si las versiones pinned siguen siendo válidas;
10. qué módulos/files tocaría cada lote.

No implementar durante esa auditoría.

## 34. Criterio de cierre RFC

El RFC queda listo para IMP si:

-   no contradice el repo real;
-   Existing Fabric Feature Development sigue siendo el único incremento
    principal;
-   proyecto existente compilable sigue siendo precondición;
-   no aparece un bloqueo obligatorio de 05;
-   Harness puede reutilizarse o extenderse mínimamente;
-   3 tareas representativas son viables;
-   acceptance puede observar comportamiento sin revelar solución;
-   no se requiere expansión general de Brain;
-   seguridad permanece intacta.

## 35. Resultado arquitectónico esperado

Al cerrar v0.5, PD Agent debe demostrar arquitectónicamente:

> Una feature Fabric real puede desarrollarse sobre un proyecto
> existente mediante el mismo runtime single-agent, usando inspección
> factual, conocimiento externo cuando proceda, mutaciones controladas,
> build/reparación limitada, artifact validation y Minecraft runtime
> evidence, sin convertir el benchmark o Harness en parte de la
> solución.
