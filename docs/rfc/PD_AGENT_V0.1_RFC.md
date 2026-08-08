# PD Agent v0.1 — RFC técnico

**Estado:** Aprobado para planificación de implementación  
**Versión:** 1.0  
**Fecha:** 2026-08-08  
**Depende de:** `docs/design/PD_AGENT_V0.1_DESIGN.md`, `docs/architecture/PD_AGENT_V0.1_ARCHITECTURE.md`

## 1. Propósito

Este RFC define cómo funcionará PD Agent v0.1. No define todavía el orden de implementación; eso corresponde al IMP.

Entrada: `Proyecto Fabric existente + tarea`.

Flujo: `inspeccionar → planificar → modificar → compilar → diagnosticar → corregir → repetir → validar`.

PASS: `BUILD SUCCESSFUL + JAR válido generado por el build + informe trazable`.

Un PASS no demuestra que Minecraft arranque ni que el mod funcione en runtime.

## 2. Alcance técnico

v0.1 implementará un único agente lógico, un runtime propio pequeño, provider abstraction, herramientas controladas, inspección Fabric/Gradle/Git, contexto técnico externo, build mediante Gradle Wrapper, bucle de reparación limitado, validación de artefacto y trazabilidad por run.

Fuera de alcance: creación de proyectos, Minecraft runtime/Test Harness, multiagente, `.Fuzzer`, otros loaders/plataformas, UI comercial, RAG/KB completa, memoria avanzada, benchmarks e integración PD-Ecosystem.

## 3. Principios e invariantes

1. El core no importa tipos de SDK de proveedores.
2. El LLM nunca accede directamente a filesystem, procesos o Git.
3. Toda acción con efectos pasa por `ToolExecutor` y políticas.
4. Toda ruta de proyecto se resuelve y valida contra `project_root`.
5. No existe shell libre en v0.1.
6. El build authority es el Gradle Wrapper incluido en el proyecto.
7. Git es observacional/no destructivo durante v0.1.
8. El Runtime, no el modelo, decide estados, límites y condición terminal.
9. Build success y artifact validation son comprobaciones separadas.
10. Cada run deja evidencia estructurada suficiente para reconstruir qué ocurrió.

## 4. Arquitectura lógica

```text
CLI
 │
 ▼
RunController
 │
 ├── ProjectInspector
 ├── ContextManager
 ├── AgentRuntime ───── ModelProvider ───── OpenAIProvider
 │       │
 │       └───────────── ToolExecutor ───── SecurityPolicy
 │                              │
 │                    ┌─────────┼─────────┐
 │                    │         │         │
 │                 Files      Git      Gradle
 │
 ├── ArtifactValidator
 └── RunReporter / EventLog
```

`RunController` ensambla una ejecución. `AgentRuntime` posee el loop cognitivo. Los subsistemas deterministas no se delegan al modelo cuando PD Agent puede comprobarlos directamente.

## 5. Modelo de ejecución

### 5.1 Estados

```text
INITIALIZING
INSPECTING
PLANNING
EDITING
BUILDING
DIAGNOSING
CORRECTING
VALIDATING_ARTIFACT
REPORTING
COMPLETED
FAILED
BLOCKED
LIMIT_REACHED
ABORTED
```

Los estados terminales son `COMPLETED`, `FAILED`, `BLOCKED`, `LIMIT_REACHED`, `ABORTED`.

### 5.2 Transiciones principales

- `INITIALIZING → INSPECTING`: configuración, root y políticas válidos.
- `INSPECTING → PLANNING`: proyecto compatible e inspección mínima completa.
- `PLANNING → EDITING`: el agente produce acciones válidas.
- `EDITING → BUILDING`: modificaciones solicitadas aplicadas o el agente decide probar el estado actual.
- `BUILDING → VALIDATING_ARTIFACT`: exit code 0.
- `BUILDING → DIAGNOSING`: build no exitoso y quedan intentos.
- `DIAGNOSING → CORRECTING → BUILDING`: diagnóstico produce corrección ejecutable.
- `VALIDATING_ARTIFACT → REPORTING`: artefacto válido.
- `REPORTING → COMPLETED`: informe persistido.
- Cualquier estado → terminal no exitoso cuando exista error irrecuperable, bloqueo, aborto o límite.

El Runtime no puede declarar `COMPLETED` basándose solo en texto del modelo.

## 6. RunController y RunState

Cada ejecución crea un `run_id` único y un `RunState` mutable controlado por el Runtime.

Campos mínimos conceptuales:

```text
run_id
project_root
task
state
started_at
project_snapshot
current_plan
changed_files
tool_call_count
agent_step_count
build_attempt_count
build_results
artifact_result
last_error
termination_reason
```

`RunState` es memoria de trabajo de una ejecución, no memoria persistente entre proyectos/runs.

## 7. Project Inspector

`ProjectInspector.inspect(project_root) -> ProjectSnapshot` será determinista.

Debe detectar como mínimo:

- existencia del Gradle Wrapper apropiado al SO;
- `settings.gradle`/`.kts` y `build.gradle`/`.kts` cuando existan;
- `gradle.properties`;
- uno o más `fabric.mod.json` relevantes;
- source/resource roots observables;
- mixin configs referenciadas;
- mod id, versión, environment, entrypoints y dependencias disponibles en metadata;
- versiones/configuración de Minecraft, Loader, Fabric API, Loom y mappings cuando puedan extraerse sin ejecutar código arbitrario;
- estado Git si el proyecto pertenece a un repositorio;
- archivos relevantes para formar contexto inicial.

No se asume una única plantilla Fabric ni que todo proyecto sea monomódulo. Si no puede determinarse de forma segura qué subproyecto contiene el mod objetivo, el run pasa a `BLOCKED` con evidencia, salvo que la tarea/contexto permita resolverlo sin ambigüedad.

## 8. Provider contract

Interfaz conceptual:

```text
ModelProvider.execute(request: AgentRequest) -> AgentResponse
```

Tipos internos mínimos:

```text
AgentRequest {
  messages
  tools
  model_config
}

AgentResponse {
  assistant_message
  tool_calls[]
  usage?
  provider_metadata?
}

ToolCall {
  call_id
  tool_name
  arguments
}
```

El adaptador convierte entre estos contratos y el SDK/API concreto. Ningún objeto específico de OpenAI atraviesa el boundary hacia `runtime`, `tools`, `project` o `reporting`.

### 8.1 OpenAIProvider

Será el único provider obligatorio de v0.1. Usará la API moderna de OpenAI con tool/function calling y API key obtenida desde configuración segura/entorno, nunca incrustada en proyecto, prompts o logs.

El modelo concreto será configuración, no una constante arquitectónica.

### 8.2 Errores de provider

Se normalizan al menos en:

```text
ProviderAuthenticationError
ProviderRateLimitError
ProviderTimeoutError
ProviderProtocolError
ProviderUnavailableError
```

Los reintentos de transporte/provider son distintos de los intentos de build y estarán limitados.

## 9. Agent Runtime y protocolo de turnos

Cada step del agente recibe contexto suficiente y las definiciones de herramientas permitidas. El modelo puede devolver texto, tool calls o ambos.

Protocolo:

1. Runtime construye `AgentRequest` desde `RunState` + contexto relevante.
2. Provider devuelve `AgentResponse`.
3. Runtime valida forma y límites.
4. Cada `ToolCall` pasa a `ToolExecutor`.
5. `ToolResult` se registra y vuelve al contexto del siguiente step.
6. El Runtime decide la siguiente fase según resultados deterministas y estado.

No se exige al modelo producir un plan formal complejo. `current_plan` puede ser una representación textual/estructurada mínima útil para trazabilidad.

## 10. Tool contract

Contrato conceptual:

```text
Tool {
  name
  description
  input_schema
  execute(context, arguments) -> ToolResult
}

ToolResult {
  call_id
  tool_name
  status
  output
  error?
  metadata?
}
```

`ToolExecutor` realiza: validación de schema → autorización → ejecución → truncado/redacción → registro de evento → devolución.

### 10.1 Herramientas v0.1

Mínimo:

- `list_directory(path)`
- `read_file(path, range?)`
- `search_text(query, paths?, limits?)`
- `write_file(path, content)`
- `create_file(path, content)`
- `delete_file(path)`
- `inspect_git_status()`
- `inspect_git_diff(paths?)`
- `run_gradle(task="build")`
- `provide_context(query?)` o equivalente de lectura de `ContextSource`

No habrá `exec_shell(command)` genérico.

`delete_file` existe porque ciertas tareas legítimas pueden requerirlo, pero solo dentro del root, sujeto a política y trazabilidad. No puede borrar `.git`, wrapper, root del proyecto ni rutas protegidas definidas por política.

## 11. Filesystem boundary

Todas las herramientas de archivos operan sobre paths relativos a `project_root`.

Algoritmo obligatorio antes de acceso:

1. rechazar entradas inválidas/nulas;
2. combinar con `project_root`;
3. resolver/canonicalizar;
4. verificar que el target permanece dentro del root autorizado;
5. comprobar symlinks/junctions cuando puedan escapar del root;
6. aplicar política de ruta protegida;
7. ejecutar.

No se envían secretos conocidos al modelo. Los lectores aplicarán límites de tamaño y los logs redactarán valores sensibles configurados.

## 12. Command/Process policy

v0.1 no expone comandos arbitrarios al modelo.

Los procesos permitidos nacen de herramientas especializadas. `run_gradle` construye internamente el comando usando `gradlew`/`gradlew.bat`; el modelo no proporciona un executable.

Cada proceso tendrá:

```text
cwd = project_root o subproyecto validado
timeout
stdout capture
stderr capture
output byte limit
exit_code
duration
```

Al exceder timeout, PD Agent termina el proceso/hijos de forma controlada y registra el resultado como fallo de herramienta/build.

## 13. Gradle Build Runner

`run_gradle("build")` ejecutará exclusivamente el Wrapper del proyecto.

Selección:

- Windows: `gradlew.bat`.
- POSIX: `./gradlew`.

No se sustituye silenciosamente por una instalación global de `gradle`. Si falta Wrapper, el proyecto no satisface el contrato normal de v0.1 y el run termina `BLOCKED` con motivo explícito.

`BuildResult` mínimo:

```text
attempt
command_display
cwd
started_at
duration
exit_code
stdout_log
stderr_log
success
```

`success = (exit_code == 0)`. La presencia literal de `BUILD SUCCESSFUL` se conserva como evidencia/reporting, pero no sustituye al exit code.

## 14. Bucle build → diagnóstico → corrección

Tras un build fallido:

1. persistir `BuildResult` y logs;
2. extraer una vista acotada/relevante del error para contexto;
3. incrementar `build_attempt_count`;
4. si se alcanzó límite → `LIMIT_REACHED`;
5. si no, `DIAGNOSING`;
6. el agente puede leer código/configuración y solicitar correcciones;
7. volver a `BUILDING`.

El agente no debe modificar archivos si no dispone de evidencia suficiente; puede inspeccionar antes de corregir.

Un error repetido idéntico puede activar una protección anti-loop para terminar antes del máximo cuando no exista progreso observable. La regla exacta se parametriza en implementación, pero debe quedar registrada como `termination_reason`.

## 15. Git boundary

Git no es requisito para que un proyecto Fabric compile, pero si existe repositorio se captura baseline.

Operaciones permitidas v0.1:

```text
git status --porcelain
git diff
git diff --cached
git rev-parse ...
```

El parser de estado utilizará formato porcelain estable para scripts.

No se permiten automáticamente:

```text
git add
git commit
git push
git pull
git checkout
git switch
git reset
git restore
git clean
git stash
```

El informe distinguirá cambios preexistentes del baseline y cambios observados durante el run en la medida que Git permita hacerlo sin modificar el repositorio.

## 16. Context system

Contrato:

```text
ContextSource.get(request) -> ContextItems
```

Fuentes v0.1:

- `ProjectContextSource`: archivos/metadatos del proyecto;
- `RunContextSource`: tool results, build logs y cambios del run;
- `ExternalContextSource`: contexto técnico proporcionado explícitamente a PD Agent.

`ContextManager` selecciona/limita contenido antes de enviarlo al provider. No existe vector DB, embeddings ni RAG obligatorio.

El contrato permite que en v0.2 Minecraft Brain implemente otro `ContextSource` sin cambiar `AgentRuntime`.

## 17. Trazabilidad y persistencia

Cada run persiste fuera del árbol modificable del proyecto siempre que la configuración lo permita, para evitar contaminar el mod.

Estructura lógica:

```text
runs/<run_id>/
├── run.json
├── events.jsonl
├── builds/
│   ├── 001.stdout.log
│   ├── 001.stderr.log
│   └── ...
├── final-report.json
└── final-report.md
```

Eventos mínimos:

```text
RUN_STARTED
PROJECT_INSPECTED
STATE_CHANGED
MODEL_CALLED
MODEL_RESPONDED
TOOL_REQUESTED
TOOL_REJECTED
TOOL_EXECUTED
FILE_CHANGED
BUILD_STARTED
BUILD_FINISHED
ARTIFACT_VALIDATED
LIMIT_REACHED
RUN_FINISHED
```

Cada evento incluye `timestamp`, `run_id`, `event_type` y payload acotado. Nunca se registra la API key. Outputs grandes se almacenan en archivo y el evento referencia su ubicación.

## 18. Artifact validation

Solo se ejecuta tras build exitoso.

`ArtifactValidator.validate(snapshot, build_result) -> ArtifactResult` debe:

1. localizar candidatos JAR producidos por el proyecto/subproyecto relevante;
2. excluir artefactos auxiliares evidentes (`sources`, `javadoc`, `dev`, etc.) cuando no sean el output distribuible;
3. verificar existencia y tamaño > 0;
4. verificar que el archivo es un ZIP/JAR legible;
5. verificar que contiene `fabric.mod.json` en la raíz cuando el artefacto objetivo es un mod Fabric;
6. correlacionar metadata del JAR con el mod inspeccionado cuando sea posible;
7. registrar path, tamaño, timestamp y metadata identificativa.

Si el build termina 0 pero no existe artefacto válido, el run no es PASS: termina `FAILED` (artifact validation failure) y genera informe.

## 19. Resultado final y semántica PASS

`FinalReport` incluye como mínimo:

```text
run_id
project
requested_task
final_state
pass: bool
summary
initial_git_state?
files_changed
build_attempts
final_build
artifact?
limits_usage
warnings
termination_reason?
```

PASS solo cuando:

```text
final build exit_code == 0
AND artifact validation == valid
AND final report persisted
```

El reporte debe declarar explícitamente: `Minecraft runtime validation: NOT PERFORMED (v0.1)`.

## 20. Límites de ejecución

Configuración mínima:

```text
max_agent_steps
max_tool_calls
max_build_attempts
provider_retry_limit
process_timeout_seconds
max_tool_output_bytes
max_context_bytes
```

Los defaults exactos se fijarán en IMP/implementación y estarán centralizados, no dispersos por código.

Superar un límite produce `LIMIT_REACHED`, salvo límites locales recuperables (por ejemplo truncado de output) que produzcan un `ToolResult` explícito y permitan continuar.

## 21. Configuración y secretos

Configuración separada en:

- configuración de PD Agent;
- configuración del provider;
- límites/políticas;
- inputs del run.

La API key se obtiene de variable de entorno/configuración secreta del host. Nunca se escribe en el repositorio objetivo ni en los artefactos de run.

El modelo/provider se selecciona por configuración. El core no codifica un nombre de modelo concreto.

## 22. Errores normalizados

Familias mínimas:

```text
ConfigurationError
ProjectInspectionError
SecurityViolation
ToolValidationError
ToolExecutionError
ProviderError
BuildError
ArtifactValidationError
LimitReachedError
```

Los errores internos conservan causa técnica para diagnóstico, pero el Runtime los transforma en estado/resultado controlado. Ninguna excepción no gestionada debe considerarse un PASS.

## 23. Estructura modular objetivo

```text
src/pd_agent/
├── runtime/
│   ├── engine
│   ├── controller
│   ├── session
│   └── state
├── providers/
│   ├── base
│   └── openai
├── context/
│   ├── base
│   └── manager
├── project/
│   ├── inspector
│   └── fabric
├── tools/
│   ├── base
│   ├── executor
│   ├── filesystem
│   ├── search
│   ├── git
│   └── gradle
├── security/
│   ├── paths
│   ├── commands
│   └── secrets
├── artifacts/
│   └── jar
├── reporting/
│   ├── events
│   └── report
├── config/
└── cli/
```

Los nombres finales de archivos/clases pueden ajustarse en IMP tras auditoría del repo; las responsabilidades/boundaries no deben alterarse silenciosamente.

## 24. CLI mínima

La interfaz de v0.1 puede ser CLI. Contrato conceptual:

```text
pd-agent run --project <path> --task <text> [provider/model/config options]
```

La CLI valida inputs, crea configuración y delega en `RunController`. No contiene lógica del agente, Fabric, Gradle ni providers.

## 25. Compatibilidad

Objetivo host inicial: Windows y POSIX donde Python y el proyecto Fabric puedan ejecutarse.

PD Agent no impone una versión global de Gradle: respeta Wrapper. Tampoco presupone Java concreto; el build del proyecto y sus mensajes determinan compatibilidad. El inspector puede reportar toolchains/versiones observadas.

La implementación de PD Agent usará Python 3.13+ como baseline propuesto por arquitectura, sujeto a auditoría de dependencias antes del IMP definitivo.

## 26. Seguridad: operaciones prohibidas en v0.1

Sin mecanismo explícito futuro de autorización, el agente no puede:

- escapar de `project_root` mediante herramientas de proyecto;
- ejecutar shell libre;
- descargar/ejecutar binarios arbitrarios;
- modificar configuración Git global;
- hacer operaciones Git destructivas o remotas;
- leer secretos arbitrarios del host;
- modificar `.git` directamente;
- iniciar Minecraft;
- declarar éxito sin evidencia determinista de build/JAR.

El acceso de red del provider no equivale a una herramienta web para el agente. Investigación/KB automatizada queda fuera de v0.1 salvo contexto externo proporcionado por una `ContextSource` controlada.

## 27. Observabilidad

La observabilidad v0.1 será local y estructurada, no un sistema de métricas distribuido.

Debe permitir responder después del run:

- qué pidió el usuario;
- qué proyecto se inspeccionó;
- qué decidió/solicitó el agente;
- qué herramientas se ejecutaron/rechazaron;
- qué archivos cambiaron;
- cuántos builds se intentaron;
- qué errores produjo cada build;
- qué JAR se validó;
- por qué terminó el run.

## 28. Criterios de aceptación del RFC

La implementación futura cumple este RFC cuando puede demostrar, con tests y ejecución real sobre al menos un proyecto Fabric existente de prueba:

1. provider desacoplado y OpenAI adapter funcional;
2. inspección mínima Fabric/Gradle/Git;
3. tool calls validadas y filesystem confinado;
4. modificación real de archivos por herramienta;
5. build exclusivamente mediante Wrapper;
6. captura de fallo y al menos un ciclo diagnóstico/corrección cuando sea necesario;
7. límites que detienen loops;
8. validación separada del JAR;
9. trazabilidad JSONL/reportes;
10. PASS únicamente con build 0 + JAR válido + informe;
11. ninguna ejecución Minecraft.

## 29. Decisiones explícitamente diferidas

Se difieren a versiones posteriores o documentos específicos:

- multiagente/orchestrator distribuido;
- RAG/vector DB/Minecraft Brain completo;
- memoria entre runs;
- sandbox de SO/containers;
- permisos interactivos avanzados;
- branch/worktree/commits automáticos;
- ejecución y observación de Minecraft;
- soporte Paper/NeoForge/Velocity;
- UI comercial;
- provider routing Auto/Hybrid;
- benchmarks y selección automática de modelo.

## 30. Referencias técnicas verificadas al redactar el RFC

- Fabric Documentation — Project Structure / `fabric.mod.json`: `https://docs.fabricmc.net/develop/getting-started/project-structure` y `https://docs.fabricmc.net/develop/loader/fabric-mod-json`.
- Gradle User Manual — Wrapper: `https://docs.gradle.org/current/userguide/gradle_wrapper.html`.
- Git documentation — `git status --porcelain`: `https://git-scm.com/docs/git-status`.
- OpenAI Platform documentation — Responses API / tool calling: `https://platform.openai.com/docs/`.

Estas referencias respaldan decisiones de integración; PD Agent mantiene contratos propios para evitar acoplamiento a versiones concretas de APIs externas.

## 31. Resultado arquitectónico

Con este RFC, PD Agent v0.1 queda definido como un runtime single-agent externo, controlado y trazable que modifica proyectos Fabric existentes mediante herramientas explícitas, usa un provider intercambiable para razonamiento, delega el build al Wrapper real del proyecto y solo declara PASS tras evidencia determinista de build y artefacto.

El siguiente documento es `IMP`, que debe convertir este RFC en lotes de implementación, dependencias, tests, criterios de aceptación, commits y rollback.
