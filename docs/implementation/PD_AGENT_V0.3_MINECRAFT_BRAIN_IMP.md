# PD Agent v0.3 — Minecraft Brain Foundation IMP

**Estado:** Plan de implementación previo a auditoría Codex  
**Área:** 03 — Knowledge Base / Minecraft Brain  
**Baseline de inicio:** `a101ddf2eaec1de83d77279aeef9627c8fa86b82`  
**Repositorio:** `pdpunto/PD-Agent`  
**Branch:** `main`

Documentos normativos:

- `PD_AGENT_V0.3_MINECRAFT_BRAIN_DESIGN.md`
- `PD_AGENT_V0.3_MINECRAFT_BRAIN_RFC.md`

> Este IMP define orden, lotes, criterios y evidencia. Las rutas/clases concretas deben validarse contra el repositorio real antes de implementar.

---

## 1. Objetivo de implementación

Construir la mínima capacidad necesaria para demostrar:

```text
Fabric task
→ environment detection
→ version-aware external retrieval
→ provenance
→ selection
→ ContextSource
→ provider real
→ code modification
→ build
→ valid JAR
→ Minecraft Test Harness
→ observed behavior
→ PASS
```

Sin embeddings, vector DB, crawler general ni arquitectura RAG distribuida.

---

## 2. Regla de entrada

No comenzar implementación hasta completar:

```text
DESIGN
→ RFC
→ IMP
→ auditoría Codex contra repo real
→ resolución de discrepancias
```

La auditoría puede obligar a ajustar este IMP antes del primer cambio de código.

---

## 3. Estrategia de lotes

Se proponen seis lotes:

```text
L0 Audit
L1 Domain + Environment
L2 Retrieval + Provenance + Cache
L3 Context Integration + Trace
L4 Acceptance Fixture + End-to-End
L5 Comparison + Regression + Closure
```

Cada lote debe ser pequeño, verificable y dejar el repositorio en estado coherente.

---

# L0 — Auditoría contra repositorio real

## Objetivo

Comprobar DESIGN + RFC + IMP contra el estado real del repo antes de implementar.

## Codex debe inspeccionar

### Git

- branch;
- `HEAD`;
- `origin/main`;
- working tree;
- baseline esperado.

### Arquitectura existente

- módulos/paquetes;
- `AgentRuntime`;
- `ContextSource`;
- context assembly;
- context budgeting/priorities;
- provider continuation;
- tool execution;
- security policy;
- evidence/run artifacts;
- configuration;
- HTTP/network helpers;
- serialization;
- cache/temp directories;
- exception/error conventions.

### Fabric

- fixtures existentes;
- Gradle conventions;
- Minecraft `1.21.11`;
- Loader;
- mappings;
- Fabric API;
- Loom;
- Java 21.

### Validation

- v0.1 validation;
- v0.1.1 validation;
- v0.2 validation;
- Minecraft Test Harness;
- unit/integration/e2e tests;
- current regression command.

## Salida requerida

Informe con:

1. baseline real;
2. mapa de integración;
3. coincidencias con DESIGN/RFC/IMP;
4. discrepancias;
5. riesgos;
6. propuesta de rutas/clases reales;
7. fixture candidata;
8. comandos de test;
9. cambios documentales necesarios antes de implementar.

## Gate

No pasar a L1 si existe una discrepancia arquitectónica sin resolver.

---

# L1 — Domain + Environment

## Objetivo

Introducir el dominio mínimo de Minecraft Brain y detectar el entorno objetivo desde el proyecto.

## Componentes conceptuales

- `KnowledgeEnvironment`;
- `KnowledgeNeed`;
- `KnowledgeType`;
- `SourceAuthority`;
- compatibility model;
- `KnowledgeEnvironmentResolver`.

Los nombres exactos se adaptarán al repo.

## Implementación mínima

### A. KnowledgeEnvironment

Representar:

- Minecraft;
- Loader;
- Loom;
- mappings namespace/version;
- Fabric API;
- Java cuando sea útil.

### B. KnowledgeNeed

Representar:

- ID;
- type;
- query;
- environment;
- hints mínimos si son necesarios.

### C. Environment Resolver

Detectar versiones desde configuración real del fixture/proyecto.

Debe soportar el formato realmente usado en el repo, no todos los formatos Gradle existentes.

### D. Conflictos

Distinguir:

```text
DETECTED
UNKNOWN
CONFLICT
```

## Tests

Unit tests mínimos:

- detecta Minecraft 1.21.11;
- detecta Loader;
- detecta mappings;
- detecta Fabric API cuando exista;
- no inventa campo ausente;
- conflicto produce estado/error explícito;
- serialización/equality si el repo la necesita.

## Aceptación L1

Una fixture existente puede producir un `KnowledgeEnvironment` correcto y verificable.

## Commit sugerido

```text
feat(brain): add version-aware knowledge environment
```

Commit + push obligatorio antes de L2.

---

# L2 — Retrieval + Provenance + Cache

## Objetivo

Recuperar al menos un tipo de conocimiento externo autoritativo y versionado con provenance.

## Componentes conceptuales

- `KnowledgeSource`;
- `KnowledgeItem`;
- `KnowledgeProvenance`;
- `KnowledgeRetrievalResult`;
- `MinecraftBrain`;
- cache mínima;
- source adapter mínimo.

## Source mínima

Elegir durante auditoría la fuente más simple que satisfaga la acceptance fixture.

Preferencia:

```text
deterministic local/versioned artifact
>
deterministic official remote metadata/artifact
>
official textual documentation
```

No implementar múltiples adapters sólo por completitud.

## Provenance

Registrar como mínimo:

- source ID/kind;
- locator;
- version/revision cuando exista;
- retrieval timestamp;
- checksum cuando sea accesible;
- política/licencia si aplica.

## Compatibility

Implementar filtro:

```text
COMPATIBLE
INCOMPATIBLE
UNKNOWN
```

`INCOMPATIBLE` nunca puede llegar a selección.

Para acceptance, `UNKNOWN` tampoco debe tratarse como válido.

## Cache

Implementar sólo lo necesario:

- exact/version-aware;
- local;
- reconstruible;
- provenance preservado.

No DB.

Preferir formato simple consistente con el repo.

## Offline

Testear:

```text
cache hit → success
cache miss → OFFLINE_MISS
```

## Tests

- source soporta/rechaza KnowledgeNeed correctamente;
- resultado contiene provenance;
- versión correcta aceptada;
- versión incorrecta excluida;
- cache no mezcla versiones;
- cache conserva provenance;
- offline hit;
- offline miss;
- source failure explícito;
- deduplicación básica si se implementa en este lote.

## Aceptación L2

Dado un `KnowledgeNeed` para el entorno de acceptance:

```text
MinecraftBrain.retrieve()
```

devuelve conocimiento externo compatible, versionado y trazable.

## Commit sugerido

```text
feat(brain): add deterministic retrieval and provenance
```

Commit + push obligatorio antes de L3.

---

# L3 — Context Integration + Trace

## Objetivo

Introducir conocimiento recuperado realmente en el contexto existente sin crear un camino paralelo al provider.

## Componentes conceptuales

- `KnowledgeSelector`;
- `KnowledgeContextSource`;
- `KnowledgeTrace`;
- integración con context budgeting existente.

## Selection

Pipeline:

```text
retrieved
→ compatibility
→ authority
→ relevance
→ dedup
→ budget
→ selected
```

No ML ranking.

## ContextSource

Crear/adaptar una implementación que use el contrato existente.

No modificar la abstracción base salvo evidencia documentada.

## Context payload

Debe permitir distinguir:

- target environment;
- retrieved technical knowledge;
- provenance/identidad suficiente.

Debe ser compacto.

## Trace

Registrar:

- environment;
- needs;
- source attempts;
- retrieved IDs;
- rejected IDs + reason;
- selected IDs;
- IDs incluidos en contexto;
- misses/errors.

## Provider proof

Debe existir una prueba que demuestre que el contenido de Brain llega al request/context que consume el provider, sin depender únicamente de logs informales.

## Tests

- incompatibles no llegan a contexto;
- autoridad ordenada;
- dedup;
- budget respetado;
- ContextSource produce contenido esperado;
- trace relaciona retrieved → selected → context;
- provider integration recibe contenido;
- Brain disabled conserva flujo previo.

## Aceptación L3

Cadena demostrada:

```text
KnowledgeNeed
→ KnowledgeItem
→ selection
→ ContextSource
→ AgentRuntime/provider context
```

## Commit sugerido

```text
feat(brain): integrate retrieved knowledge with agent context
```

Commit + push obligatorio antes de L4.

---

# L4 — Acceptance Fixture + End-to-End

## Objetivo

Demostrar utilidad real sobre una tarea Fabric server-side compatible con el Test Harness de v0.2.

## Selección de fixture

La auditoría debe elegir la tarea mínima.

Requisitos:

- Minecraft 1.21.11;
- server-side;
- Fabric;
- API/símbolo version-sensitive;
- comportamiento observable;
- build rápido/reproducible;
- no GUI;
- no input humano;
- no networking complejo;
- no nueva infraestructura innecesaria.

## Ejecución Brain ON

Debe registrar:

1. environment;
2. KnowledgeNeed;
3. source;
4. provenance;
5. KnowledgeItem IDs;
6. selected/context IDs;
7. provider real;
8. modificación;
9. Gradle result;
10. JAR;
11. JAR/hash cuando corresponda;
12. Minecraft startup;
13. target mod load;
14. comportamiento esperado;
15. shutdown;
16. PASS/FAIL.

## Provider

Usar un provider real ya validado y disponible para el entorno de ejecución.

No introducir un provider nuevo.

## Minecraft

Reutilizar Test Harness v0.2.

No extender a client-side.

## Tests

Además de unit/integration:

- validation runner específico v0.3 o extensión coherente del existente;
- failure evidence;
- success evidence;
- deterministic fixture reset/cleanup.

## Aceptación L4

Debe existir un run Brain ON completo:

```text
retrieved knowledge
→ provider
→ code
→ BUILD SUCCESSFUL
→ valid JAR
→ Minecraft real
→ expected server-side behavior
→ PASS
```

## Commit sugerido

```text
test(brain): add minecraft brain acceptance validation
```

Commit + push obligatorio antes de L5.

---

# L5 — Comparison + Regression + Closure

## Objetivo

Cerrar v0.3 con comparación, regresión y evidencia reproducible.

## A. Brain OFF

Ejecutar la misma tarea sin Brain.

Registrar resultado sin manipularlo para provocar fallo.

## B. Brain ON

Ejecutar la misma tarea con Brain.

Debe incluir KnowledgeTrace/provenance.

## C. Comparación

Informe mínimo:

| Aspecto | Brain OFF | Brain ON |
|---|---|---|
| Environment | | |
| Retrieved external knowledge | no | sí |
| Provenance | no Brain provenance | sí |
| Build | | |
| JAR | | |
| Minecraft behavior | | |
| Result | | |

No interpretar una victoria/derrota aislada como benchmark general.

## D. Regression

Ejecutar la suite completa apropiada y las validaciones previas que sigan siendo reproducibles.

Debe comprobarse que v0.3 no rompe:

- v0.1;
- v0.1.1 offline/unit behavior;
- v0.2;
- provider/tool/security/context contracts.

Una live validation que requiera credenciales/billing no disponibles debe marcarse explícitamente como bloqueada, no como fallo funcional ni PASS inventado.

## E. Documentación

Actualizar:

- DESIGN si la auditoría aprobó cambios;
- RFC si cambió arquitectura;
- IMP si cambió plan;
- documento de validación v0.3;
- documentación master/roadmap sólo cuando corresponda al cierre y según Dirección.

## F. Final acceptance

Debe poder afirmarse con evidencia:

> PD Agent recuperó conocimiento externo correspondiente al entorno Fabric/Minecraft objetivo, conservó su procedencia, lo incorporó al contexto del agente y lo utilizó para producir una solución que fue validada mediante build y Minecraft real.

## Commit sugerido

```text
docs(brain): close minecraft brain v0.3 validation
```

Commit + push obligatorio.

---

# 4. Dependencias entre lotes

```text
L0
 ↓
L1
 ↓
L2
 ↓
L3
 ↓
L4
 ↓
L5
```

No paralelizar L2/L3 antes de estabilizar contratos del lote anterior.

---

# 5. Política de cambios

Si durante implementación aparece una discrepancia menor de naming/ruta compatible con DESIGN/RFC:

- adaptar al repo;
- documentar en informe.

Si aparece una discrepancia que cambia:

- comportamiento;
- contrato;
- scope;
- arquitectura;
- aceptación;

detener esa parte y volver a ChatGPT.

No rediseñar silenciosamente.

---

# 6. Política de tests

Cada lote debe añadir tests al mismo tiempo que la implementación.

No acumular tests para el final.

Orden esperado:

```text
unit
→ integration
→ validation
→ Minecraft runtime
→ regression
```

Los tests no deben depender innecesariamente de Internet.

Los tests de adapters remotos deben separar:

- parsing/logic determinista;
- live/network validation cuando sea necesaria.

---

# 7. Política de red

Las pruebas unitarias no deben depender de servicios externos vivos.

Cuando sea necesario validar una source remota:

- usar una prueba específica;
- timeout;
- evidencia;
- cache;
- fallo explícito.

No convertir una caída de red en regresión del core.

---

# 8. Política de credenciales

Minecraft Brain no debe necesitar credenciales para fuentes públicas seleccionadas en v0.3.

El provider real puede requerir su API key según el flujo existente.

Nunca almacenar secrets en:

- fixtures;
- traces;
- evidence;
- cache;
- commits.

---

# 9. Política de rollback

Cada lote debe tener commit independiente.

Rollback:

```text
revert commit del lote
```

No mezclar refactors no relacionados con Minecraft Brain.

Si un cambio en infraestructura compartida es imprescindible, debe ser mínimo y quedar cubierto por regresión.

---

# 10. Evidencia por lote

## L1

```text
environment detection evidence
+ unit tests
```

## L2

```text
retrieval
+ provenance
+ compatibility
+ cache/offline evidence
```

## L3

```text
selection
+ ContextSource
+ trace
+ provider-context proof
```

## L4

```text
provider real
+ diff
+ build
+ JAR
+ Minecraft runtime
+ behavior
```

## L5

```text
OFF vs ON
+ full regression
+ closure evidence
```

---

# 11. Definition of Done

v0.3 no está terminado por:

- compilar;
- recuperar documentación;
- crear KnowledgeItem;
- mostrar provenance;
- pasar unit tests.

Está terminado únicamente cuando se demuestra la cadena completa:

```text
correct target environment
→ compatible external knowledge
→ provenance
→ ContextSource
→ real provider
→ real code change
→ build
→ valid Fabric JAR
→ real Minecraft
→ expected behavior
→ reproducible evidence
→ regression PASS
→ commit + push
```

---

# 12. Primera acción de Codex

La primera acción después de aprobar este IMP es **L0 — auditoría**, no implementación.

Codex debe recibir DESIGN + RFC + IMP, comprobarlos contra el repo real y devolver hallazgos antes de tocar código.

No debe realizar cambios ni commits durante L0 salvo que ChatGPT lo solicite posteriormente para corregir documentación.
