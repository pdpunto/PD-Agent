# PD Agent v0.3 — Minecraft Brain Foundation RFC

**Estado:** RFC técnico previo a auditoría Codex  
**Área:** 03 — Knowledge Base / Minecraft Brain  
**Baseline de inicio:** `a101ddf2eaec1de83d77279aeef9627c8fa86b82`  
**Repositorio:** `pdpunto/PD-Agent`  
**Branch:** `main`  
**Design:** `PD_AGENT_V0.3_MINECRAFT_BRAIN_DESIGN.md`

> Este RFC define contratos y arquitectura lógica. Los nombres/rutas concretos deberán validarse contra el repositorio real durante la auditoría Codex antes de implementar.

---

## 1. Objetivo

Implementar la mínima infraestructura que permita:

```text
Fabric Project
→ detectar KnowledgeEnvironment
→ expresar KnowledgeNeed
→ recuperar KnowledgeItems compatibles
→ conservar Provenance
→ seleccionar contexto limitado
→ exponerlo mediante ContextSource
→ AgentRuntime/provider real
→ herramientas
→ build
→ JAR
→ Minecraft Test Harness
→ evidencia
```

La estrategia de v0.3 es **deterministic-first**. No incluye embeddings ni vector database.

---

## 2. Componentes lógicos

```text
KnowledgeEnvironmentResolver
KnowledgeNeed
MinecraftBrain
KnowledgeSource
KnowledgeCache
KnowledgePolicy
KnowledgeSelector
KnowledgeItem
KnowledgeProvenance
KnowledgeTrace
KnowledgeContextSource
```

Las clases, módulos y nombres definitivos se adaptarán a las convenciones existentes del repositorio.

---

## 3. KnowledgeEnvironment

Representa el entorno técnico contra el que debe ser válido el conocimiento.

Campos conceptuales mínimos:

```text
minecraft_version
java_version?
loader_version?
loom_version?
mappings_namespace?
mappings_version?
fabric_api_version?
```

### Reglas

1. `minecraft_version` es obligatorio para consultas version-sensitive.
2. Los demás campos pueden ser desconocidos cuando no apliquen.
3. `unknown` no significa compatible con cualquier versión.
4. El entorno se obtiene prioritariamente del proyecto real.
5. El prompt del usuario no debe sobrescribir silenciosamente datos verificables del proyecto.
6. Debe poder serializarse en traces/evidencia.

---

## 4. Environment Resolver

### Entrada

```text
project/workspace
```

### Salida

```text
KnowledgeEnvironment
+ detection evidence
```

### Fuentes iniciales a inspeccionar

Según la estructura real del proyecto:

- `gradle.properties`;
- `build.gradle`;
- `build.gradle.kts`;
- `settings.gradle`;
- `settings.gradle.kts`;
- version catalogs;
- plugin/dependency declarations;
- metadata Fabric relevante.

### Comportamiento

Debe diferenciar:

```text
DETECTED
UNKNOWN
CONFLICT
```

Un conflicto entre fuentes del propio proyecto no se resuelve adivinando.

---

## 5. KnowledgeNeed

Describe una necesidad concreta de conocimiento.

Modelo conceptual:

```text
KnowledgeNeed {
    id
    type
    query
    environment
    optional hints
}
```

Tipos iniciales:

```text
SYMBOL
API
MAPPING
BUILD
CONCEPT
MIGRATION
```

### Reglas

- Debe ser pequeña y específica.
- Debe incluir `KnowledgeEnvironment`.
- No debe contener documentación completa.
- Debe poder registrarse en `KnowledgeTrace`.

---

## 6. KnowledgeSource

Contrato conceptual:

```text
supports(need) -> bool
resolve(need) -> KnowledgeSourceResult
```

Una source:

- declara qué necesidades soporta;
- respeta versiones;
- devuelve resultados con provenance;
- no decide qué entra finalmente al contexto;
- no llama directamente al provider.

### Sources v0.3

El conjunto mínimo exacto se fijará tras auditoría, pero se priorizan adapters para fuentes deterministas ya disponibles en el entorno/proyecto.

Candidatos:

1. metadata/versiones Fabric;
2. artefactos/mappings versionados;
3. Javadocs/source metadata compatibles;
4. documentación oficial seleccionada cuando una consulta conceptual lo requiera.

No es requisito implementar todos los candidatos si la fixture de aceptación puede cubrirse correctamente con un subconjunto mínimo.

---

## 7. Source Authority

Enum/concepto mínimo:

```text
AUTHORITATIVE_ARTIFACT
AUTHORITATIVE_SOURCE
OFFICIAL_DOCUMENTATION
SECONDARY
```

Orden por defecto:

```text
AUTHORITATIVE_ARTIFACT
>
AUTHORITATIVE_SOURCE
>
OFFICIAL_DOCUMENTATION
>
SECONDARY
```

Este orden puede complementarse con especificidad/version compatibility.

Una source secundaria incompatible nunca puede vencer a una fuente autoritativa compatible.

---

## 8. KnowledgeProvenance

Cada resultado externo debe incluir provenance.

Campos conceptuales:

```text
source_id
source_kind
locator
artifact_or_document_version?
revision?
retrieved_at
checksum_algorithm?
checksum?
license_id_or_policy?
```

### Reglas

- `source_id`, `source_kind`, `locator` y `retrieved_at` son mínimos.
- Si existe una versión/revisión verificable debe conservarse.
- Si existe checksum razonablemente accesible debe conservarse.
- Provenance debe ser serializable.
- Un resultado sin provenance válido no puede etiquetarse como `retrieved knowledge`.

---

## 9. KnowledgeItem

Modelo conceptual:

```text
KnowledgeItem {
    id
    content
    environment
    authority
    provenance
    relevance metadata
}
```

### Identidad

El ID debe ser estable dentro de una ejecución y suficientemente determinista para poder relacionar:

```text
retrieval
→ selection
→ context
→ evidence
```

No se exige todavía un ID global permanente.

---

## 10. Compatibility

Antes de seleccionar un resultado debe comprobarse compatibilidad con `KnowledgeEnvironment`.

Resultado conceptual:

```text
COMPATIBLE
INCOMPATIBLE
UNKNOWN
```

### Política v0.3

- `INCOMPATIBLE` → excluir.
- `COMPATIBLE` → elegible.
- `UNKNOWN` → no tratar como compatible automáticamente.

Para la fixture de aceptación se exigirán resultados cuya compatibilidad pueda demostrarse.

---

## 11. MinecraftBrain

Orquestador de recuperación.

Contrato conceptual:

```text
retrieve(KnowledgeNeed) -> KnowledgeRetrievalResult
```

Flujo:

```text
KnowledgeNeed
      ↓
validate environment
      ↓
eligible sources
      ↓
compatible cache lookup
      ↓
source resolution if needed
      ↓
normalize KnowledgeItems
      ↓
compatibility filter
      ↓
authority/relevance ordering
      ↓
deduplication
      ↓
KnowledgeRetrievalResult
```

MinecraftBrain no:

- modifica código;
- ejecuta herramientas;
- invoca Minecraft;
- llama directamente al LLM.

---

## 12. Deterministic-first strategy

Prioridad:

```text
exact identifiers / project versions
→ cache exact match
→ authoritative versioned source
→ exact/textual lookup in selected official material
→ MISS
```

Búsqueda semántica:

```text
OUT OF SCOPE v0.3
```

La interfaz no debe impedir añadirla posteriormente.

---

## 13. KnowledgeCache

La cache no es fuente independiente de verdad.

Contrato conceptual:

```text
get(need/environment/source identity) -> cached items
put(items)
invalidate(...)
```

### Requisitos

- version-aware;
- reconstruible;
- eliminable;
- provenance preservado;
- no mezclar entornos;
- permitir ejecución offline cuando exista material compatible.

### Cache key

Debe incorporar suficiente identidad para impedir colisiones entre versiones.

Conceptualmente:

```text
source
+ knowledge type/query identity
+ minecraft
+ mappings
+ fabric api
+ relevant artifact version
```

La clave física se decidirá tras auditoría.

---

## 14. Offline mode

Flujo:

```text
KnowledgeNeed
      ↓
compatible cache
   ┌──┴──┐
  HIT   MISS
   │      │
result  OFFLINE_MISS
```

No se consulta red.

No se convierte conocimiento interno del provider en retrieved knowledge.

Errores/misses deben ser observables en trace.

---

## 15. KnowledgeSelector

Responsable de decidir qué resultados llegan al contexto.

Entrada:

```text
KnowledgeRetrievalResult
+ context budget
```

Proceso:

```text
compatibility
→ authority
→ relevance
→ deduplication
→ budget
```

Salida:

```text
SelectedKnowledge
```

### Reglas

- nunca incluir `INCOMPATIBLE`;
- priorizar evidencia exacta sobre explicación general;
- evitar duplicados;
- no incluir documentos completos si un fragmento basta;
- mantener IDs/provenance de cada fragmento seleccionado.

No se requiere ranking ML.

---

## 16. Context budget

Debe existir un límite explícito.

El mecanismo exacto debe reutilizar las capacidades existentes del sistema de contexto si ya existen.

Si el repo ya posee budgeting/prioridades, Minecraft Brain no debe duplicarlas.

La auditoría Codex debe comprobar este punto antes de fijar implementación.

---

## 17. KnowledgeContextSource

Adaptador entre Brain y el sistema existente.

Conceptualmente:

```text
SelectedKnowledge
        ↓
KnowledgeContextSource
        ↓
existing ContextSource contract
        ↓
AgentRuntime
```

### Contenido expuesto

El contexto debe permitir al provider distinguir:

- conocimiento recuperado;
- entorno objetivo;
- contenido técnico;
- provenance resumido/identificable.

### Restricción

No modificar `ContextSource` salvo evidencia durante auditoría de que el contrato actual no puede expresar esta información.

---

## 18. Provider boundary

El provider recibe contexto preparado por el sistema existente.

No debe:

- consultar Minecraft Brain directamente;
- conocer adapters;
- gestionar cache;
- resolver versiones;
- fabricar provenance.

Esto mantiene PD Agent model-agnostic.

---

## 19. KnowledgeTrace

Trace legible por máquina para demostrar uso.

Modelo conceptual:

```text
KnowledgeTrace {
    run_id
    environment
    needs[]
    source_attempts[]
    retrieved_item_ids[]
    rejected_items[]
    selected_item_ids[]
    context_item_ids[]
    misses[]
    timestamps
}
```

Cuando sea posible, registrar motivos de rechazo:

```text
VERSION_MISMATCH
UNKNOWN_COMPATIBILITY
LOWER_AUTHORITY_DUPLICATE
CONTEXT_BUDGET
SOURCE_ERROR
```

---

## 20. Evidencia de uso

No se afirmará que Brain fue usado sólo porque existió una llamada de retrieval.

Cadena mínima:

```text
KnowledgeNeed
→ KnowledgeItem ID
→ selected
→ ContextSource
→ provider execution
→ resulting task execution
```

Para cierre end-to-end se añade:

```text
→ code diff
→ build
→ JAR
→ Minecraft Test Harness
→ observed expected behavior
```

---

## 21. Error model

Errores conceptuales mínimos:

```text
ENVIRONMENT_UNRESOLVED
ENVIRONMENT_CONFLICT
UNSUPPORTED_NEED
SOURCE_UNAVAILABLE
SOURCE_ERROR
VERSION_MISMATCH
PROVENANCE_INVALID
CACHE_ERROR
OFFLINE_MISS
NO_COMPATIBLE_KNOWLEDGE
CONTEXT_SELECTION_EMPTY
```

### Principio

Errores de Brain deben ser explícitos y diagnosticables.

No deben convertirse silenciosamente en contenido inventado.

---

## 22. Network policy

La recuperación remota debe ser:

- limitada a sources conocidas;
- determinista cuando sea posible;
- timeout-bound;
- auditable;
- cacheable según política;
- independiente del provider LLM.

No se implementará crawling web abierto en v0.3.

---

## 23. Legal/source policy

Cada source debe poder asociarse a una política conceptual:

```text
FETCH_ALLOWED
CACHE_ALLOWED
REDISTRIBUTION_ALLOWED / NOT_ALLOWED / REVIEW_REQUIRED
```

v0.3 no necesita construir un motor jurídico general.

Sí necesita evitar que la implementación asuma:

```text
puedo descargar
== puedo redistribuir
```

No se empaquetarán Minecraft JARs ni código Mojang decompilado dentro de PD Agent.

---

## 24. Actualización

Separación:

```text
Brain engine
≠
cached/versioned knowledge
```

La actualización de metadata/mappings/documentos cacheados no debe exigir modificar el core.

Adapters que requieran cambios de protocolo sí pueden requerir una actualización de PD Agent.

---

## 25. Acceptance fixture

La fixture debe:

1. usar Minecraft `1.21.11`;
2. ser Fabric;
3. ejecutarse en el flujo ya soportado por v0.2;
4. ser server-side;
5. evitar GUI/render/input/networking complejo;
6. requerir conocimiento versionado concreto;
7. permitir comportamiento observable en Minecraft;
8. producir evidencia reproducible.

### Selección definitiva

La tarea exacta **no se congela antes de la auditoría Codex**.

Codex debe inspeccionar:

- fixtures existentes;
- APIs ya usadas;
- Test Harness;
- provider flow;
- ContextSource;
- oportunidades para una tarea pequeña que no esté ya trivialmente resuelta por fixtures existentes.

Después se elegirá la tarea mínima que satisfaga el Design sin introducir scope nuevo.

---

## 26. Brain OFF vs Brain ON

### Brain OFF

Flujo normal sin `KnowledgeContextSource` derivado del Brain.

Registrar:

- provider;
- task;
- environment;
- resultado;
- build;
- runtime si llega a ejecutarse.

### Brain ON

Misma tarea y entorno, añadiendo retrieval trazable.

Registrar:

- todo lo anterior;
- KnowledgeTrace;
- provenance;
- items seleccionados.

### Interpretación

No se exige:

```text
OFF = FAIL
```

Sí se exige:

```text
ON = retrieved external compatible knowledge
   + context integration proven
   + valid solution
   + build PASS
   + Minecraft behavior PASS
```

La comparación no constituye todavía un benchmark framework.

---

## 27. Seguridad

Minecraft Brain debe respetar las políticas existentes de PD Agent.

No obtiene privilegios adicionales para:

- escribir archivos;
- ejecutar comandos;
- modificar repositorios;
- acceder a secrets.

Retrieval y tool execution siguen siendo responsabilidades separadas.

---

## 28. Observabilidad

Los resultados deben permitir diagnosticar:

```text
qué entorno detectó
qué necesitó saber
qué sources intentó
qué recuperó
qué descartó
qué seleccionó
qué llegó al contexto
qué falló
```

Los formatos exactos de evidencia deben alinearse con las convenciones existentes del repo.

---

## 29. Persistencia

v0.3 necesita persistencia sólo para:

- cache;
- traces/evidencia cuando corresponda.

No necesita:

- base de datos;
- memoria del usuario;
- historial semántico;
- perfiles;
- Knowledge Graph.

Preferencia inicial: formatos locales simples y legibles por máquina, si encajan con el repositorio.

---

## 30. Evolución futura

El diseño permite añadir posteriormente:

```text
TextSearchKnowledgeSource
SemanticKnowledgeSource
AdditionalMinecraftVersions
PaperKnowledgeSource
NeoForgeKnowledgeSource
VelocityKnowledgeSource
```

sin cambiar el contrato principal:

```text
KnowledgeNeed
→ MinecraftBrain
→ KnowledgeItems
→ ContextSource
```

Estas extensiones no forman parte de v0.3.

---

## 31. Invariantes

1. No mezclar versiones silenciosamente.
2. No llamar retrieved knowledge al conocimiento interno del LLM.
3. Todo `KnowledgeItem` externo tiene provenance.
4. Todo item que entra al contexto es compatible o explícitamente validado.
5. Cache no altera provenance.
6. Brain no llama directamente al provider.
7. Provider no conoce sources/cache.
8. `ContextSource` sigue siendo la frontera salvo incompatibilidad demostrada.
9. No se necesita búsqueda semántica para cerrar v0.3.
10. El éxito final requiere Minecraft real, no sólo retrieval/build.

---

## 32. Criterios de aceptación del RFC

La implementación derivada deberá demostrar:

### A. Environment

El entorno objetivo se detecta y queda registrado.

### B. Retrieval

Una necesidad concreta recupera conocimiento externo compatible.

### C. Provenance

El resultado identifica su origen y versión/revisión cuando exista.

### D. Isolation

Conocimiento incompatible queda excluido.

### E. Context

Los items seleccionados llegan al provider mediante `ContextSource`.

### F. Trace

Existe relación entre necesidad, item recuperado, item seleccionado y contexto.

### G. Build

La modificación producida compila y genera JAR válido.

### H. Runtime

Minecraft Test Harness observa el comportamiento esperado.

### I. Comparison

Se conserva evidencia Brain OFF vs Brain ON.

### J. Regression

Las capacidades v0.1, v0.1.1 y v0.2 no sufren regresiones atribuibles a v0.3.

---

## 33. Decisiones explícitamente diferidas a auditoría

Antes de implementación, Codex debe verificar contra el repo real:

- ubicación exacta de módulos/paquetes;
- firma actual de `ContextSource`;
- mecanismo actual de context budgeting;
- modelos de evidencia existentes;
- formato/configuración de runs;
- provider continuation flow;
- fixture más adecuada;
- Test Harness hooks reutilizables;
- convenciones de errores;
- serialización;
- HTTP/network utilities existentes;
- cache/config paths existentes;
- tests y naming conventions.

Si el repo contradice este RFC en detalles de integración, no se improvisará implementación.

Se documentará la discrepancia y se actualizarán DESIGN/RFC/IMP cuando corresponda.

---

## 34. Orden obligatorio

```text
DESIGN
→ RFC
→ IMP
→ auditoría Codex contra repo
→ resolver hallazgos
→ implementación incremental
→ tests/build
→ Minecraft Test Harness
→ comparación
→ regresión
→ commit/push
→ cierre
```

No implementar antes de la auditoría.
