# PD Agent v0.1 — Implementation Plan (IMP)

**Estado:** Listo para auditoría previa de Codex  
**Versión:** 1.0  
**Fecha:** 2026-08-08  
**Depende de:**  
- `docs/design/PD_AGENT_V0.1_DESIGN.md`
- `docs/architecture/PD_AGENT_V0.1_ARCHITECTURE.md`
- `docs/rfc/PD_AGENT_V0.1_RFC.md`

## 1. Propósito

Este IMP define cómo construir PD Agent v0.1 por lotes verificables.

No modifica el DESIGN ni el RFC. Si la auditoría del repositorio demuestra una incompatibilidad real, se detiene la parte afectada, se documenta la discrepancia y se corrigen los documentos antes de implementar.

Entrada objetivo:

`Proyecto Fabric existente + tarea`

Resultado PASS:

`BUILD SUCCESSFUL + JAR Fabric válido + informe trazable`

Minecraft runtime validation permanece fuera de v0.1.

---

## 2. Reglas de implementación

1. Implementación incremental; ningún lote depende de funcionalidad futura no necesaria.
2. Core provider-neutral; tipos de OpenAI no atraviesan el adapter.
3. Ningún shell libre.
4. Filesystem confinado a `project_root`.
5. Gradle Wrapper es la única autoridad de build.
6. Git es observacional/no destructivo.
7. Cada lote incluye tests antes de considerarse terminado.
8. Cada hito importante termina en commit + push.
9. No se avanza sobre tests rotos atribuibles al lote.
10. No se rediseña DESIGN/RFC silenciosamente durante implementación.
11. Mantener Windows y POSIX donde aplique.
12. No añadir RAG, DB, multiagente, Minecraft runtime, UI ni abstracciones especulativas.

---

## 3. Auditoría obligatoria antes de implementar

Codex debe inspeccionar el repositorio real y contrastarlo con DESIGN + ARCHITECTURE + RFC + IMP.

Debe verificar:

- estado Git, branch, remote y working tree;
- estructura real del repositorio;
- existencia de `pyproject.toml` u otro packaging;
- versión de Python disponible/objetivo;
- dependencias ya existentes;
- convenciones de código/tests;
- CI existente;
- rutas documentales;
- conflictos de nombres/módulos;
- si ya existe código reutilizable;
- compatibilidad real con Python 3.13+;
- disponibilidad/elección del SDK OpenAI;
- estrategia real de CLI;
- cualquier discrepancia entre documentos y repo.

### Salida de auditoría

Informe obligatorio:

```text
AUDIT RESULT
- repo state
- existing structure
- reusable code
- discrepancies
- risks
- proposed document corrections, if any
- GO / NO-GO for implementation
```

**No implementar todavía durante esta auditoría.**

Si existen discrepancias arquitectónicas, volver a ChatGPT antes del Lote 0.

---

## 4. Estructura objetivo

Sujeta a ajustes menores tras auditoría:

```text
src/pd_agent/
├── runtime/
├── providers/
├── context/
├── project/
├── tools/
├── security/
├── artifacts/
├── reporting/
├── config/
└── cli/

tests/
├── unit/
├── integration/
└── fixtures/
```

Los nombres concretos de archivos/clases pueden adaptarse a convenciones reales del repo sin cambiar boundaries del RFC.

---

# 5. Lotes de implementación

## Lote 0 — Foundation del proyecto

### Objetivo

Dejar un paquete Python instalable, testeable y ejecutable, sin lógica de agente todavía.

### Implementar

- packaging/configuración Python;
- estructura `src/pd_agent`;
- estructura de tests;
- configuración de test runner;
- logging base;
- configuración tipada mínima;
- entrypoint CLI mínimo;
- `.gitignore` apropiado;
- README técnico mínimo si falta;
- CI básica solo si el repo ya usa CI o resulta trivial y coherente con la auditoría.

### Tests

- import del paquete;
- carga de configuración;
- CLI `--help`;
- ejecución de suite vacía/base.

### Aceptación

```text
package installs/imports
tests PASS
CLI starts
no product logic yet
```

### Commit

`chore: bootstrap pd-agent runtime`

### Rollback

Revertir el commit completo. No hay migraciones ni estado persistente.

---

## Lote 1 — Core contracts + Run State

### Objetivo

Crear los contratos internos independientes de providers y herramientas concretas.

### Implementar

- `RunState`;
- estados y transiciones;
- `ExecutionLimits`;
- errores normalizados;
- contratos:
  - `ModelProvider`;
  - `AgentRequest`;
  - `AgentResponse`;
  - `ToolCall`;
  - `ToolResult`;
  - `Tool`;
  - `ContextSource`;
  - `BuildResult`;
  - `ArtifactResult`;
- generación de `run_id`;
- validaciones básicas de estado.

### Tests

- estados terminales;
- transiciones válidas/inválidas;
- contadores/límites;
- serialización de tipos que deban persistirse;
- provider fake compatible con el contrato;
- tool fake compatible con el contrato.

### Aceptación

El core puede modelar un run sin importar OpenAI, Fabric, Git ni Gradle.

### Commit

`feat: add core runtime contracts and run state`

### Rollback

Revertir el lote sin afectar foundation.

---

## Lote 2 — Reporting y trazabilidad

### Objetivo

Garantizar evidencia desde el inicio antes de añadir efectos reales.

### Implementar

- directorio por `run_id`;
- `run.json`;
- `events.jsonl`;
- event writer;
- almacenamiento de outputs grandes por referencia;
- redacción básica de secretos configurados;
- `FinalReport` JSON + Markdown;
- eventos base de lifecycle.

### Tests

- JSONL válido append-only;
- orden básico de eventos;
- persistencia/relectura;
- secreto no aparece en eventos/reportes;
- outputs grandes se referencian correctamente;
- informe parcial para terminación no exitosa.

### Aceptación

Un run sintético deja una traza reconstruible sin DB.

### Commit

`feat: add run event log and reporting`

### Rollback

Revertir lote; los artefactos de prueba pueden eliminarse.

---

## Lote 3 — Security boundary + filesystem tools

### Objetivo

Crear el boundary de seguridad antes de permitir modificaciones reales.

### Implementar

- normalización/canonicalización de paths;
- confinamiento a `project_root`;
- protección frente a `..`;
- protección frente a symlink/junction escape cuando aplique;
- rutas protegidas (`.git`, root, wrapper según operación destructiva);
- `ToolExecutor`;
- schema/input validation;
- herramientas:
  - `list_directory`;
  - `read_file`;
  - `search_text`;
  - `write_file`;
  - `create_file`;
  - `delete_file`;
- límites de tamaño/output;
- eventos `TOOL_*` y `FILE_CHANGED`.

### Tests

Casos obligatorios:

- lectura válida dentro del root;
- escritura válida;
- creación;
- búsqueda;
- borrado permitido;
- `../` rechazado;
- absolute path externo rechazado;
- symlink escape rechazado;
- `.git` protegido;
- borrado de root rechazado;
- input inválido rechazado;
- output truncado de forma explícita.

### Aceptación

No existe camino conocido desde las tools para leer/modificar fuera del root autorizado.

### Commit

`feat: add secure filesystem tool execution`

### Rollback

Revertir lote. Ninguna herramienta de proceso existe todavía.

---

## Lote 4 — Git observacional + Project Inspector Fabric

### Objetivo

Obtener un snapshot determinista del proyecto antes de pedir razonamiento al modelo.

### Implementar

### Git

Solo lectura:

- detectar repositorio;
- HEAD/branch cuando existan;
- `git status --porcelain`;
- `git diff`;
- `git diff --cached`;
- baseline del working tree.

No implementar comandos Git mutables.

### Project Inspector

Detectar:

- Gradle Wrapper;
- `settings.gradle[.kts]`;
- `build.gradle[.kts]`;
- `gradle.properties`;
- `fabric.mod.json`;
- source/resource roots;
- mixin configs referenciadas;
- mod id/version/environment/entrypoints/dependencies;
- versiones Minecraft/Loader/Fabric API/Loom/mappings cuando sean extraíbles estáticamente;
- estructura multimódulo observable;
- subproyecto objetivo cuando pueda determinarse sin ambigüedad.

### Fixtures

Crear proyectos Fabric mínimos sintéticos para tests. No depender de Internet.

### Tests

- proyecto Fabric simple;
- Kotlin DSL;
- proyecto sin Git;
- working tree sucio;
- metadata Fabric válida;
- metadata inválida;
- Wrapper ausente → diagnóstico de incompatibilidad;
- multimódulo resoluble;
- multimódulo ambiguo → `BLOCKED`/resultado equivalente;
- parser no ejecuta Gradle ni código del proyecto.

### Aceptación

`ProjectInspector.inspect()` produce `ProjectSnapshot` útil sin LLM y sin ejecutar código arbitrario.

### Commit

`feat: inspect fabric projects and git baseline`

### Rollback

Revertir lote; no existen cambios en proyectos externos durante tests salvo fixtures temporales.

---

## Lote 5 — Gradle Build Runner

### Objetivo

Ejecutar builds reales exclusivamente mediante el Wrapper.

### Implementar

- detección Windows/POSIX;
- construcción interna del comando;
- `cwd` validado;
- timeout;
- captura stdout/stderr;
- límite de output;
- persistencia completa de logs;
- exit code;
- duración;
- contador de build attempts;
- terminación controlada del proceso/hijos al timeout;
- eventos `BUILD_STARTED` / `BUILD_FINISHED`.

El modelo no proporciona executable ni flags arbitrarios.

### Tests

- wrapper fixture/fake exitoso;
- wrapper fixture/fake fallido;
- timeout;
- stdout/stderr;
- exit code;
- wrapper ausente;
- command injection imposible desde argumentos públicos;
- incremento correcto de attempts.

### Aceptación

`success` depende del exit code y los logs quedan trazados.

### Commit

`feat: add controlled gradle wrapper builds`

### Rollback

Revertir lote. No modifica configuración Gradle del proyecto.

---

## Lote 6 — Artifact Validator

### Objetivo

Separar estrictamente build success de PASS.

### Implementar

- localizar JAR candidato del subproyecto relevante;
- excluir `sources`, `javadoc`, `dev` y auxiliares evidentes;
- existencia;
- tamaño > 0;
- ZIP/JAR legible;
- `fabric.mod.json` en raíz;
- correlación de metadata cuando sea posible;
- timestamp/path/size/metadata;
- fallo explícito si build 0 pero JAR inválido/ausente.

### Tests

- JAR Fabric válido;
- JAR vacío;
- ZIP corrupto;
- sources-only;
- JAR sin `fabric.mod.json`;
- varios candidatos;
- metadata incompatible;
- build exitoso sin artefacto.

### Aceptación

Ningún `BuildResult.success == true` implica automáticamente PASS.

### Commit

`feat: validate fabric build artifacts`

### Rollback

Revertir lote; funcionalidad aislada.

---

## Lote 7 — Context system

### Objetivo

Proporcionar contexto suficiente al agente sin implementar Minecraft Brain/RAG.

### Implementar

- `ContextManager`;
- `ProjectContextSource`;
- `RunContextSource`;
- `ExternalContextSource`;
- selección y límites;
- truncado explícito;
- prioridad mínima de contexto;
- representación apta para `AgentRequest`.

### Tests

- combinación de fuentes;
- límites de contexto;
- external context;
- build logs acotados;
- archivos grandes;
- no inclusión accidental de secretos configurados.

### Aceptación

El Runtime puede obtener contexto técnico externo mediante el contrato sin conocer RAG/vector DB.

### Commit

`feat: add bounded run context system`

### Rollback

Revertir lote sin afectar inspector/tools.

---

## Lote 8 — OpenAI Provider Adapter

### Objetivo

Añadir el primer provider funcional sin contaminar el core.

### Implementar

- `OpenAIProvider`;
- traducción `AgentRequest ↔ API`;
- tool definitions;
- tool calls;
- usage/metadata cuando estén disponibles;
- configuración de modelo;
- API key desde entorno/configuración segura;
- errores normalizados:
  - authentication;
  - rate limit;
  - timeout;
  - protocol;
  - unavailable;
- retries de provider limitados y separados de build attempts.

### Tests

Preferir mocks/fakes de frontera para suite normal.

Validar:

- request mapping;
- response mapping;
- tool call mapping;
- errores normalizados;
- API key no se serializa/loguea;
- ningún tipo OpenAI sale del módulo provider.

Test real contra API: separado/opt-in, no requisito de la suite offline.

### Aceptación

Cambiar `OpenAIProvider` por un fake no exige cambios en Runtime.

### Commit

`feat: add openai model provider adapter`

### Rollback

Revertir adapter; core permanece funcional con fake provider.

---

## Lote 9 — Agent Runtime + execution loop

### Objetivo

Integrar razonamiento, tools y estados sin todavía declarar el MVP final.

### Implementar

- `RunController`;
- `AgentRuntime`;
- protocolo de steps;
- construcción de `AgentRequest`;
- recepción/validación de tool calls;
- ejecución mediante `ToolExecutor`;
- retorno de `ToolResult`;
- `current_plan` mínimo;
- límites:
  - agent steps;
  - tool calls;
  - provider retries;
  - build attempts;
- transiciones:
  - inspect;
  - plan;
  - edit;
  - build;
  - diagnose;
  - correct;
  - rebuild;
- protección anti-loop simple basada en ausencia de progreso/error repetido;
- terminales `FAILED`, `BLOCKED`, `LIMIT_REACHED`, `ABORTED`.

### Tests

Con fake provider determinista:

1. tarea que modifica archivo y build pasa;
2. build falla → diagnóstico → corrección → build pasa;
3. tool call inválida;
4. security rejection;
5. provider failure;
6. max steps;
7. max tool calls;
8. max builds;
9. error repetido/anti-loop;
10. excepción interna nunca produce PASS.

### Aceptación

El loop completo funciona offline con provider fake y herramientas reales sobre fixtures temporales.

### Commit

`feat: implement single-agent execution loop`

### Rollback

Revertir integración; subsistemas previos permanecen testeables.

---

## Lote 10 — CLI end-to-end + semántica PASS

### Objetivo

Exponer el flujo completo de v0.1.

### Implementar

Contrato:

```text
pd-agent run --project <path> --task <text>
```

Más opciones mínimas de provider/model/config cuando sean necesarias.

La CLI:

- valida inputs;
- carga configuración;
- crea `RunController`;
- muestra estado/resumen útil;
- devuelve exit code coherente;
- nunca contiene lógica de Fabric/Gradle/provider.

### PASS obligatorio

Solo:

```text
final build exit_code == 0
AND artifact validation == valid
AND final report persisted
```

Informe:

`Minecraft runtime validation: NOT PERFORMED (v0.1)`

### Tests

- argumentos inválidos;
- proyecto inexistente;
- proyecto incompatible;
- run exitoso fake;
- run fallido;
- exit codes;
- informe final persistido;
- build 0 + JAR inválido = FAIL.

### Aceptación

Existe una única entrada operativa que ejecuta el contrato completo del RFC.

### Commit

`feat: expose pd-agent v0.1 run command`

### Rollback

Revertir CLI; Runtime permanece usable por tests/API interna.

---

## Lote 11 — Validación real del MVP

### Objetivo

Demostrar v0.1 con evidencia real sobre proyecto(s) Fabric existentes de prueba.

### Preparación

Usar al menos un fixture/proyecto Fabric real controlado y compatible con el entorno.

No usar un proyecto personal con cambios importantes como primera prueba.

### Escenario A — modificación que compila

1. baseline Git;
2. tarea concreta;
3. PD Agent inspecciona;
4. modifica;
5. ejecuta Wrapper;
6. build exit 0;
7. JAR válido;
8. informe persistido.

Esperado: `PASS`.

### Escenario B — reparación

Preparar una tarea/estado donde la primera modificación produzca o encuentre un fallo corregible.

Esperado:

```text
build failure
→ diagnosis
→ correction
→ rebuild
→ build success
→ JAR valid
→ PASS
```

### Escenario C — límite/fallo seguro

Forzar provider fake o proyecto de prueba a no progresar.

Esperado:

`LIMIT_REACHED` o `FAILED`, nunca PASS.

### Evidencia requerida

- comandos ejecutados;
- resultados de tests;
- logs de builds;
- `events.jsonl`;
- `final-report.json`;
- `final-report.md`;
- path y metadata del JAR;
- Git diff final;
- confirmación de que Minecraft no fue ejecutado.

### Aceptación final v0.1

Debe demostrarse:

1. provider desacoplado;
2. OpenAI adapter funcional;
3. inspector Fabric/Gradle/Git;
4. filesystem confinado;
5. modificación real;
6. Wrapper-only build;
7. reparación tras fallo;
8. límites;
9. JAR validation separada;
10. reporting trazable;
11. PASS correcto;
12. cero ejecución Minecraft.

### Commit

`test: validate pd-agent v0.1 end-to-end`

Después:

- ejecutar suite completa;
- confirmar working tree esperado;
- push del commit/hito.

---

# 6. Dependencias entre lotes

```text
L0 Foundation
 ↓
L1 Contracts/State
 ↓
L2 Reporting
 ↓
L3 Security + Files
 ↓
L4 Git + Inspector
 ↓
L5 Gradle
 ↓
L6 Artifact
 ↓
L7 Context
 ↓
L8 OpenAI Provider
 ↓
L9 Runtime Loop
 ↓
L10 CLI E2E
 ↓
L11 MVP Validation
```

La secuencia prioriza boundaries deterministas y seguridad antes de conectar el LLM.

L4-L8 tienen partes técnicamente paralelizables, pero v0.1 se implementará secuencialmente para reducir integración simultánea y facilitar revisión/rollback.

---

# 7. Estrategia de tests

## Unit

Cubrir lógica determinista:

- paths/security;
- state machine;
- parsers;
- inspector;
- Git;
- Gradle result parsing/control;
- artifact validation;
- context limits;
- provider mappings;
- reporting.

## Integration

Cubrir fronteras:

- ToolExecutor + filesystem;
- inspector + fixture Fabric;
- Gradle runner + wrapper controlado;
- Runtime + fake provider;
- reporting completo.

## End-to-end

Cubrir el flujo v0.1 sobre proyecto Fabric real/controlado.

La suite normal debe poder ejecutarse sin API key ni Internet. Las pruebas reales del provider serán opt-in.

---

# 8. Defaults iniciales de límites

Los valores finales deben validarse durante Lote 11. Para iniciar implementación se usarán defaults centralizados conservadores:

```text
max_agent_steps = 40
max_tool_calls = 120
max_build_attempts = 5
provider_retry_limit = 2
process_timeout_seconds = 600
max_tool_output_bytes = 1_000_000
max_context_bytes = 2_000_000
```

Estos valores son configuración, no invariantes arquitectónicos.

Durante auditoría/implementación Codex puede aportar evidencia para ajustarlos, pero no dispersarlos por el código.

---

# 9. Política de commits y push

Mínimo un commit por lote completado.

Reglas:

- no mezclar lotes no relacionados;
- mensaje descriptivo;
- tests del lote PASS antes del commit;
- push tras cada hito importante;
- informar hash del commit;
- no reescribir historia remota;
- no usar force push;
- no incluir secretos ni artefactos temporales.

Si el repositorio todavía no tiene Git/GitHub correctamente configurado, la auditoría debe señalarlo. Su preparación será requisito antes de comenzar implementación, conforme al proceso general del proyecto.

---

# 10. Conducta ante discrepancias

Si Codex descubre que una decisión del IMP no encaja con el repo:

1. detener la parte afectada;
2. no improvisar un rediseño arquitectónico;
3. aportar evidencia concreta;
4. clasificar:
   - ajuste menor de implementación;
   - discrepancia de IMP;
   - discrepancia de RFC;
   - discrepancia de DESIGN;
5. volver a ChatGPT;
6. actualizar documento(s);
7. reanudar solo tras resolución.

Los ajustes menores de nombres/rutas que no cambien contratos pueden proponerse en el informe de auditoría.

---

# 11. Criterio para autorizar implementación

La implementación solo puede empezar cuando:

- DESIGN aprobado;
- arquitectura aprobada;
- RFC aprobado;
- IMP aprobado;
- auditoría Codex terminada;
- discrepancias resueltas;
- Git/GitHub operativo;
- ChatGPT marque explícitamente el punto 12 del checklist como completado.

Por tanto, la existencia de este IMP **no autoriza todavía a programar**.

---

# 12. Primer prompt previsto para Codex

El siguiente paso tras aprobar este documento será una **auditoría únicamente**, no implementación.

Objetivo del prompt:

```text
Auditar DESIGN + ARCHITECTURE + RFC + IMP contra el repositorio real.
No modificar código de producto.
No comenzar lotes.
Informar estructura, Git/GitHub, Python/tooling, dependencias,
tests, CI, discrepancias, riesgos y GO/NO-GO.
```

El prompt operativo completo lo proporcionará ChatGPT en el punto 10.

---

# 13. Definition of Done de PD Agent v0.1

v0.1 está terminado solo cuando existe evidencia reproducible de:

```text
existing Fabric project + task
→ inspect
→ plan
→ controlled edits
→ Gradle Wrapper build
→ diagnose/correct/retry when needed
→ successful build
→ valid Fabric JAR
→ traceable final report
```

y además:

- suite PASS;
- límites y seguridad probados;
- Git no fue usado destructivamente;
- Minecraft no fue ejecutado;
- commits/push confirmados;
- documentación refleja el estado real.

