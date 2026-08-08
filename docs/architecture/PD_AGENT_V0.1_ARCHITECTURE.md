# PD Agent v0.1 — Arquitectura Base

**Estado:** Aprobada como base para RFC
**Versión:** 1.0
**Proyecto:** PD Agent
**Documento:** Arquitectura técnica previa al RFC — v0.1

## 1. Propósito

Este documento convierte el DESIGN aprobado de PD Agent v0.1 en una arquitectura técnica mínima, correcta y evolutiva.

No es todavía el RFC ni el plan de implementación.

- **DESIGN** = qué queremos.
- **Arquitectura / RFC** = cómo funcionará.
- **IMP** = cómo lo construiremos.

El objetivo sigue siendo:

`Proyecto Fabric existente + tarea`

→ `inspeccionar → planificar → modificar → compilar → diagnosticar → corregir → repetir → validar`

→ `BUILD SUCCESSFUL + JAR generado + informe trazable`

Un PASS de v0.1 valida modificación/build, no funcionamiento dentro de Minecraft.

## 2. Principios arquitectónicos

1. v0.1 será **single-agent**.
2. PD Agent tendrá un **runtime propio pequeño**, sin framework multiagente.
3. El core será **model-agnostic**.
4. El LLM será un componente de decisión, no tendrá acceso directo al sistema operativo.
5. Todas las acciones pasarán por herramientas controladas y políticas de seguridad.
6. El build se ejecutará usando el **Gradle Wrapper del proyecto**.
7. Git se usará desde v0.1 para baseline y trazabilidad sin operaciones destructivas automáticas.
8. La Knowledge Base completa queda fuera; v0.1 solo necesita una interfaz para contexto técnico externo.
9. No habrá memoria avanzada, base de datos, vector DB, message bus ni plugin framework en v0.1.
10. La arquitectura debe permitir evolucionar posteriormente hacia Minecraft Brain, providers adicionales y multiagente sin reescribir el núcleo.

## 3. Vista general

                    ┌────────────────────┐
                    │      PD Agent      │
                    │     CLI / API      │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Agent Runtime    │
                    │  Execution Loop    │
                    └─────────┬──────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │

┌────────▼───────┐ ┌────────▼───────┐ ┌──────▼─────────┐
│ LLM Provider │ │ Context Manager│ │ Tool Executor │
│ abstraction │ │ │ │ + Security │
└────────────────┘ └────────┬───────┘ └──────┬─────────┘
│ │
┌─────────▼──────┐ ┌─────▼─────────────┐
│ Project │ │ Project Tools │
│ Inspector │ │ Files / Search │
└────────────────┘ │ Git / Gradle │
└─────┬─────────────┘
│
Fabric Project

## 4. Agent Runtime

El `Agent Runtime` es el dueño de una ejecución completa.

Estados principales:

INITIALIZING
↓
INSPECTING
↓
PLANNING
↓
EDITING
↓
BUILDING
↓
┌───────────────┐
│ build failed? │
└──────┬────────┘
│ yes
↓
DIAGNOSING
↓
CORRECTING
↓
BUILDING
│
└──────── loop limitado

BUILDING
↓ success
VALIDATING_ARTIFACT
↓
REPORTING
↓
COMPLETED

Estados terminales adicionales:

FAILED
BLOCKED
LIMIT_REACHED
ABORTED

El Runtime controla el loop. El modelo propone decisiones y acciones; PD Agent valida y ejecuta.

## 5. Modelo single-agent

v0.1 tendrá una única sesión/agente lógico.

El mismo agente podrá:

`inspeccionar → razonar → pedir herramientas → analizar resultados → modificar → analizar build → corregir`

No existirán todavía `Manager Agent`, `Architect Agent`, `Developer Agent`, `Reviewer Agent` ni un orchestrator multiagente.

La futura capa multiagente podrá situarse encima del Runtime sin cambiar el contrato de herramientas.

## 6. Provider abstraction

El núcleo dependerá de un contrato propio, no de SDKs concretos.

Contrato conceptual:

ModelProvider
execute(AgentRequest) -> AgentResponse

Tipos conceptuales internos:

AgentRequest
AgentMessage
ToolDefinition
ToolCall
ToolResult
ModelUsage
AgentResponse

El core no conocerá directamente OpenAI, Anthropic, Qwen, Ollama, Gemini u otros proveedores.

### Provider inicial

v0.1 utilizará **OpenAI API** como primer adaptador funcional para demostrar el flujo completo.

Esto no crea dependencia arquitectónica: el adaptador quedará detrás de `ModelProvider`.

Agent Runtime
│
ModelProvider
│
OpenAIProvider ← v0.1
LocalProvider ← futuro
OtherProvider ← futuro

## 7. Tool System

El LLM no tendrá terminal irrestricto.

Herramientas mínimas previstas:

read_file
list_directory
search_text
write_file
create_file
delete_file
inspect_git_status
inspect_git_diff
run_gradle
provide_context

Podrá existir una herramienta `run_project_command`, siempre controlada por política y limitada a comandos explícitamente permitidos y relacionados con el proyecto.

## 8. Security Boundary

Flujo obligatorio:

LLM
│
│ ToolCall
▼
Tool Executor
│
▼
Security Policy
│
├─ path permitido?
├─ comando permitido?
├─ operación destructiva?
├─ límite alcanzado?
└─ proyecto autorizado?
│
▼
OS / filesystem / process

Invariante:

> El LLM nunca accede directamente al filesystem, Git ni subprocess.

### Aislamiento por proyecto

Cada ejecución recibe un `project_root` autorizado.

Toda ruta debe normalizarse y validarse antes de usarla. Se rechazará cualquier acceso que escape del proyecto, incluyendo traversal, rutas absolutas externas y symlinks que apunten fuera.

Los secretos no deben incorporarse deliberadamente al contexto del modelo.

## 9. Git

Antes de modificar el proyecto, PD Agent inspeccionará al menos:

git status --porcelain
HEAD
branch
diff

Objetivos de Git en v0.1:

- conocer el baseline;
- detectar cambios preexistentes;
- distinguir cambios del agente;
- obtener diffs;
- preservar trazabilidad.

Operaciones destructivas automáticas prohibidas en v0.1:

git reset --hard
git clean
git checkout -- .
git restore .
git stash
force push

PD Agent v0.1 no necesita commits ni push automáticos dentro del loop principal.

Branches, worktrees, snapshots y rollback avanzado quedan para una evolución posterior si demuestran ser necesarios.

## 10. Project Inspector

El inspector será determinista y especializado en detectar la estructura necesaria de un proyecto Fabric existente.

Debe identificar, cuando existan:

project root
Gradle Wrapper
settings.gradle / settings.gradle.kts
build.gradle / build.gradle.kts
gradle.properties
fabric.mod.json
Java/Kotlin source roots
resources
mixin configs
Minecraft version
Fabric Loader
Fabric API
Loom
mappings
Java version/configuration
Git state

No se asumirá una única estructura rígida de proyecto.

## 11. Build subsystem

PD Agent no implementará su propio sistema de build.

Usará el Gradle Wrapper incluido en el proyecto:

./gradlew build

En Windows:

gradlew.bat build

El `BuildRunner` recogerá como mínimo:

command
cwd
start/end
exit_code
stdout
stderr
duration

La autoridad primaria para determinar éxito del proceso será el código de salida, complementado con la comprobación del artefacto esperado.

## 12. Artifact validation

Tras un build exitoso, `ArtifactLocator` localizará el JAR generado.

No bastará con aceptar cualquier `.jar`; deberán excluirse artefactos auxiliares cuando corresponda, por ejemplo:

_-sources.jar
_-dev.jar
\*-javadoc.jar

Resultado conceptual:

ArtifactResult
path
size
timestamp
classification

Para v0.1, validar el JAR significa comprobar que:

- existe;
- es un archivo;
- no está vacío;
- es un ZIP/JAR legible;
- corresponde al build recién realizado.

No significa demostrar que Minecraft pueda cargarlo correctamente.

## 13. Context Manager

La Knowledge Base completa no entra en v0.1.

Se define una abstracción mínima `ContextSource` capaz de aportar contexto desde:

project files
task
build logs
tool results
external technical context

La futura Knowledge Base / Minecraft Brain podrá implementar esa misma frontera sin modificar el Runtime.

No habrá vector DB ni RAG completo en v0.1.

## 14. Estado de ejecución

Cada run mantendrá estado temporal explícito:

RunState
Task
ProjectSnapshot
CurrentPlan
ChangedFiles
ToolHistory
BuildAttempts
Diagnostics
ExternalContext
IterationCount

No habrá memoria a largo plazo, semantic memory, user profiling ni memory graph en v0.1.

## 15. Trazabilidad

Cada ejecución tendrá un `run_id`.

Artefactos mínimos previstos:

run.json
events.jsonl
builds/
final-report.json
final-report.md

Eventos conceptuales:

RUN_STARTED
PROJECT_INSPECTED
MODEL_CALLED
TOOL_REQUESTED
TOOL_EXECUTED
FILE_CHANGED
BUILD_STARTED
BUILD_FAILED
BUILD_SUCCEEDED
ARTIFACT_FOUND
RUN_COMPLETED

No se necesita base de datos para v0.1.

## 16. Límites de ejecución

`ExecutionLimits` pertenecerá al Runtime y contemplará al menos:

max_agent_steps
max_build_attempts
max_tool_calls
command_timeout
max_output_bytes
max_context_bytes

Los valores concretos se fijarán en el RFC y se validarán posteriormente mediante pruebas.

Al superar un límite, el run termina en `LIMIT_REACHED` y genera informe parcial trazable.

## 17. Tecnología base

El runtime de PD Agent se desarrollará en **Python**.

Baseline propuesto para el RFC: **Python 3.13+**.

Motivos principales:

- buena integración con procesos, filesystem y tooling;
- SDKs de LLM maduros;
- desarrollo rápido;
- multiplataforma;
- integración futura sencilla con modelos locales y RAG;
- PD Agent es un orquestador externo, no un mod Minecraft.

## 18. Estructura modular mínima

pd-agent/
├── src/pd_agent/
│ ├── runtime/
│ │ ├── engine
│ │ ├── session
│ │ └── state
│ ├── providers/
│ │ ├── base
│ │ └── openai
│ ├── context/
│ │ └── manager
│ ├── project/
│ │ ├── inspector
│ │ └── fabric
│ ├── tools/
│ │ ├── filesystem
│ │ ├── search
│ │ ├── process
│ │ ├── gradle
│ │ └── git
│ ├── security/
│ │ ├── paths
│ │ └── commands
│ ├── artifacts/
│ │ └── jar
│ ├── reporting/
│ └── cli/
└── tests/

Esta estructura es conceptual para el RFC. El IMP decidirá archivos y orden real de construcción después de la auditoría correspondiente.

## 19. Flujo completo

User
│
│ project + task
▼
CLI
│
▼
RunSession
│
├── Security.initialize(project_root)
├── Git.inspect_baseline()
├── FabricProjectInspector.inspect()
│
▼
ContextManager
│
▼
AgentRuntime
│
│── Provider → plan
│── ToolExecutor → inspect/read/search
│── Provider → edits/tool calls
│── ToolExecutor → apply changes
│
▼
GradleBuildRunner
│
├── SUCCESS ──────────────┐
│ │
└── FAILURE │
│ │
▼ │
AgentRuntime │
│ diagnose │
│ fix │
└── build again │
▼
ArtifactLocator
│
▼
FinalReport

## 20. Decisiones cerradas para llevar al RFC

1. Single-agent en v0.1.
2. Runtime propio pequeño, sin framework multiagente.
3. Python como tecnología del runtime.
4. Core neutral respecto al proveedor de modelos.
5. OpenAI API como primer adaptador funcional.
6. Tool calls controladas; no shell libre para el LLM.
7. Filesystem restringido al proyecto autorizado.
8. Git observacional y no destructivo en v0.1.
9. Gradle Wrapper como autoridad de build.
10. `ContextSource` como frontera para contexto técnico externo.
11. Estado por run, sin memoria avanzada.
12. JSONL + reportes para trazabilidad.
13. Validación del JAR separada del resultado del proceso Gradle.
14. Ninguna ejecución automática de Minecraft en v0.1.

## 21. Fuera de esta arquitectura v0.1

Siguen fuera, conforme al DESIGN:

- creación de proyectos Fabric desde cero;
- ejecución automática de Minecraft;
- Minecraft Test Harness;
- Multi-Agent System;
- `.Fuzzer`;
- Paper / NeoForge / Velocity;
- UI comercial;
- Auto/Hybrid avanzado;
- memoria avanzada;
- Knowledge Base completa;
- benchmarks;
- integración con PD-Ecosystem.

## 22. Siguiente documento

El siguiente paso documental es convertir estas decisiones en:

`docs/rfc/PD_AGENT_V0.1_RFC.md`

El RFC deberá cerrar contratos, interfaces, estados, errores, políticas de seguridad, provider boundary, tool protocol, persistencia de runs, reglas de build/JAR y criterios técnicos verificables.
