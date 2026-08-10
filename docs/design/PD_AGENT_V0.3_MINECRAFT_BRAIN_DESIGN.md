# PD Agent v0.3 — Minecraft Brain Foundation DESIGN

**Estado:** DESIGN aprobado para v0.3  
**Área:** 03 — Knowledge Base / Minecraft Brain  
**Baseline de inicio:** `a101ddf2eaec1de83d77279aeef9627c8fa86b82`  
**Repositorio:** `pdpunto/PD-Agent`  
**Branch:** `main`

---

## 1. Objetivo

Minecraft Brain será la capa responsable de proporcionar al agente **conocimiento técnico externo, versionado y trazable** para tareas Fabric/Minecraft.

No será:

- memoria;
- otro agente;
- un RAG genérico;
- un sistema de embeddings;
- una base vectorial;
- un crawler general;
- un sistema que decida código por sí mismo.

Su contrato conceptual será:

```text
Environment + KnowledgeNeed
                ↓
         Minecraft Brain
                ↓
KnowledgeItems + Provenance
```

El objetivo de PD Agent v0.3 es demostrar que PD Agent puede:

```text
Tarea Fabric
→ detectar entorno/versiones
→ recuperar conocimiento externo compatible
→ conservar procedencia
→ introducirlo mediante ContextSource
→ usar provider real
→ modificar código
→ compilar
→ generar JAR válido
→ ejecutar Minecraft real
→ observar comportamiento
→ producir PASS/FAIL con evidencia
```

---

## 2. Alcance

El alcance obligatorio de v0.3 es:

- Minecraft `1.21.11`;
- Fabric Loader;
- Fabric Loom cuando corresponda;
- mappings compatibles con el proyecto;
- Fabric API cuando corresponda;
- Java 21;
- integración con el `AgentRuntime` existente;
- reutilización de `ContextSource`;
- ejecución mediante el Minecraft Test Harness existente;
- conocimiento externo con provenance;
- recuperación determinista como primera estrategia;
- cache local;
- comportamiento offline explícito;
- evidencia comparativa Brain OFF vs Brain ON.

---

## 3. Fuera de alcance

No pertenecen a v0.3:

- embeddings;
- vector database;
- Chroma;
- Qdrant;
- FAISS;
- Knowledge Graph;
- crawler general;
- scraping indiscriminado;
- memoria conversacional avanzada;
- aprendizaje automático del Brain;
- generación automática masiva de documentación;
- servicios RAG externos obligatorios;
- Multi-Agent;
- `.Fuzzer`;
- Paper;
- NeoForge;
- Velocity;
- Test Harness client-side;
- GUI/rendering/input humano;
- sistema general de benchmarks;
- Auto/Hybrid;
- UI comercial;
- integración con PD-Ecosystem.

---

## 4. Requisitos funcionales

### RF-01 — Environment detection

Minecraft Brain debe determinar del proyecto objetivo, como mínimo:

- Minecraft;
- Fabric Loader;
- mappings;
- Fabric API cuando exista;
- Loom cuando sea relevante.

El proyecto real debe ser la autoridad primaria para detectar su entorno.

### RF-02 — Version isolation

Conocimiento incompatible con el entorno objetivo no puede introducirse silenciosamente en el contexto.

### RF-03 — Deterministic-first retrieval

La recuperación debe intentar primero resolución exacta y versionada.

La búsqueda semántica queda fuera del MVP.

### RF-04 — KnowledgeItem

Cada fragmento recuperado debe representarse como una unidad identificable de conocimiento.

### RF-05 — Provenance

Cada `KnowledgeItem` debe conservar como mínimo:

- fuente;
- locator/identificador;
- versión o revisión cuando exista;
- timestamp de recuperación;
- checksum cuando esté disponible.

### RF-06 — Source authority

Minecraft Brain debe distinguir niveles de autoridad.

Para hechos exactos como firmas, símbolos o artefactos, deben tener prioridad:

1. artefactos/código correspondiente a la versión;
2. mappings/Javadocs;
3. metadata oficial;
4. documentación oficial;
5. fuentes secundarias;
6. conocimiento propio del LLM.

### RF-07 — Context budget

Minecraft Brain no debe volcar documentación completa al provider.

Debe seleccionar únicamente el conocimiento relevante dentro del presupuesto de contexto.

### RF-08 — ContextSource

El conocimiento recuperado debe llegar al `AgentRuntime` mediante la abstracción existente `ContextSource`, salvo evidencia real obtenida durante la auditoría de que resulta insuficiente.

### RF-09 — Retrieval trace

Cada ejecución debe poder demostrar:

- qué conocimiento fue solicitado;
- qué resultados fueron recuperados;
- de qué fuentes;
- qué resultados llegaron al contexto.

### RF-10 — Cache

Debe existir capacidad de reutilizar localmente conocimiento previamente recuperado.

### RF-11 — Offline behavior

Si una consulta necesaria no puede resolverse sin red y no existe cache compatible, Minecraft Brain debe producir un miss explícito.

Nunca debe etiquetar como conocimiento recuperado algo recordado únicamente por el modelo.

### RF-12 — Knowledge updates

Actualizar conocimiento, metadata o cache no debe requerir publicar una nueva versión del core de PD Agent.

### RF-13 — Fabric 1.21.11

v0.3 debe funcionar obligatoriamente contra el entorno ya validado de Minecraft `1.21.11`.

### RF-14 — Acceptance task

Debe existir una tarea Fabric donde el conocimiento externo versionado sea materialmente relevante para producir la solución.

### RF-15 — End-to-end validation

La validación debe cubrir:

```text
retrieval
→ provenance
→ ContextSource
→ provider real
→ edit
→ build
→ JAR
→ Minecraft Test Harness
→ comportamiento observable
```

### RF-16 — Comparative evidence

Debe ejecutarse una comparación controlada:

```text
Brain OFF
vs
Brain ON
```

No se exige artificialmente que Brain OFF falle.

La condición Brain ON sí debe demostrar uso real de conocimiento externo trazable.

---

## 5. Requisitos no funcionales

- **RNF-01:** sin vector DB en v0.3.
- **RNF-02:** sin embeddings.
- **RNF-03:** sin crawler general.
- **RNF-04:** sin servicio RAG externo obligatorio.
- **RNF-05:** conocimiento reproducible cuando la fuente lo permita.
- **RNF-06:** cache invalidable y versionada.
- **RNF-07:** provenance legible por máquina.
- **RNF-08:** cada fuente debe tener política/licencia identificable.
- **RNF-09:** fallo cerrado ante incompatibilidad de versión.
- **RNF-10:** arquitectura ampliable posteriormente con búsqueda textual y semántica.

---

## 6. Tipos de conocimiento

Minecraft Brain debe poder trabajar conceptualmente con siete clases de conocimiento:

| Clase | Ejemplos | Resolución preferida |
|---|---|---|
| Entorno | Minecraft, Loader, Loom, Java, Fabric API | proyecto + metadata |
| Símbolos | clases, métodos, campos, packages | mappings/Javadocs |
| Fabric API | events, callbacks, networking | API source/Javadocs |
| Minecraft internals | clases vanilla, firmas, registries | mappings + sources preparados por tooling |
| Build/tooling | Gradle, Loom, dependencies | proyecto + Loom docs |
| Conceptual | registro de items, eventos, conceptos Fabric | Fabric Docs |
| Migración | APIs eliminadas/cambiadas | versiones + source/docs/diffs |

No todo conocimiento debe almacenarse en una única base.

---

## 7. Principio 1 — El proyecto es la autoridad del entorno

Antes de recuperar conocimiento:

```text
Fabric Project
      ↓
Environment Resolver
      ↓
KnowledgeEnvironment
```

Ejemplo conceptual:

```text
minecraft      = 1.21.11
loader         = 0.19.3
mappings       = yarn:1.21.11+build.X
fabric_api     = X
loom           = X
java           = 21
```

Las versiones no deben inferirse del prompt cuando puedan obtenerse del proyecto real.

---

## 8. Principio 2 — KnowledgeNeed

Minecraft Brain no debe recibir peticiones ilimitadas como:

> Dame toda la documentación sobre ticks.

Debe recibir necesidades pequeñas y explícitas.

Modelo conceptual:

```text
KnowledgeNeed
 type
 query
 environment
```

Tipos iniciales conceptuales:

```text
SYMBOL
API
MAPPING
BUILD
CONCEPT
MIGRATION
```

La representación definitiva se fijará en el RFC.

---

## 9. Principio 3 — KnowledgeItem

Cada resultado debe ser autocontenido:

```text
KnowledgeItem
 ├─ content
 ├─ environment
 ├─ authority
 └─ provenance
```

El provider no necesita conocer los detalles internos de recuperación.

---

## 10. Principio 4 — Provenance inseparable

No debe existir conocimiento externo utilizado por Minecraft Brain sin procedencia.

No es válido producir simplemente:

```text
"ServerTickEvents funciona así"
```

Debe ser posible recorrer:

```text
KnowledgeItem
     ↓
Provenance
     ↓
source / version / locator / hash / retrieval metadata
```

Provenance forma parte del dato de conocimiento, no de un log opcional posterior.

---

## 11. Principio 5 — Recuperación determinista primero

Pipeline inicial:

```text
KnowledgeNeed
      ↓
exact/version resolution
      ↓
local cache
      ↓
authoritative external source
      ↓
textual lookup if required
      ↓
MISS
```

No se diseñará inicialmente alrededor de:

```text
vector search
→ documentos parecidos
→ LLM decide
```

La búsqueda semántica sólo deberá añadirse en versiones posteriores si existe evidencia de necesidad.

---

## 12. Principio 6 — Source adapters

Minecraft Brain no debe acoplarse directamente a una única fuente.

Arquitectura conceptual:

```text
MinecraftBrain
      │
      ├── Source A
      ├── Source B
      ├── Source C
      └── Cache
```

Cada source deberá declarar qué tipos de conocimiento puede resolver.

Esto permitirá actualizar fuentes sin modificar `AgentRuntime`.

---

## 13. Principio 7 — Source policy

Las fuentes no son equivalentes.

Minecraft Brain deberá distinguir, como mínimo:

```text
AUTHORITATIVE_ARTIFACT
AUTHORITATIVE_SOURCE
OFFICIAL_DOCUMENTATION
SECONDARY
```

v0.3 debe trabajar principalmente con las tres primeras.

Una fuente secundaria nunca debe sobrescribir silenciosamente una fuente autoritativa compatible.

---

## 14. Principio 8 — ContextSource como frontera

No debe introducirse un camino especial:

```text
Brain → Provider
```

Se reutilizará:

```text
Brain
 ↓
Knowledge ContextSource
 ↓
existing context system
 ↓
AgentRuntime
 ↓
Provider
```

Esto preserva las fronteras arquitectónicas existentes.

---

## 15. Principio 9 — Contexto limitado

Minecraft Brain puede recuperar más información de la que recibe finalmente el modelo.

Pipeline:

```text
retrieved KnowledgeItems
          ↓
version filter
          ↓
authority/ranking
          ↓
deduplication
          ↓
context budget
          ↓
ContextSource
```

El contexto debe contener la evidencia mínima suficiente para resolver la tarea.

---

## 16. Principio 10 — Cache no es la fuente de verdad

La cache es:

- optimización;
- capacidad offline;
- mecanismo de reproducibilidad.

No debe convertirse en autoridad conceptual independiente.

```text
Authoritative Source
        ↓
KnowledgeItem
        ↓
Cache
```

Debe poder eliminarse y reconstruirse.

---

## 17. Principio 11 — Offline explícito

Comportamiento esperado:

```text
Need
 ↓
compatible cache?
 ├─ yes → result
 └─ no  → MISS
```

Nunca:

```text
no internet
→ usar conocimiento recordado por el provider
→ etiquetarlo como Minecraft Brain
```

El provider puede seguir razonando según políticas futuras, pero ese razonamiento debe quedar separado de retrieved knowledge.

---

## 18. Principio 12 — Frontera legal

Minecraft Brain debe distinguir:

- uso local;
- cache local;
- redistribución dentro de PD Agent.

PD Agent no debe empaquetar ni redistribuir como parte del Brain:

- Minecraft JAR;
- código Mojang decompilado;
- artefactos cuya licencia no permita redistribución.

Las políticas de source/cache/distribution deberán quedar separadas.

---

## 19. Fuentes y autoridad

Jerarquía inicial:

| Tipo de conocimiento | Autoridad preferida |
|---|---|
| Versiones Fabric | Fabric Meta |
| Artefactos/versiones | Fabric Maven |
| Fabric Loader | repositorio/código oficial |
| Fabric API | repositorio/código + artefactos oficiales |
| Fabric Loom | documentación + repositorio oficial |
| Yarn mappings | Yarn + artefactos Tiny |
| Uso conceptual Fabric | Fabric Docs |
| Cambios entre versiones | docs/porting + repos/tags/diffs |
| Símbolos Minecraft 1.21.11 | mappings + Javadocs/sources disponibles legalmente |
| Dependencias reales | archivos de build del proyecto |
| Comportamiento final | build + Minecraft Test Harness |

Para hechos exactos, el artefacto correspondiente a la versión debe prevalecer sobre documentación narrativa.

---

## 20. Version awareness

Minecraft version por sí sola no identifica completamente el conocimiento.

Conceptualmente:

```text
KnowledgeEnvironment
  minecraft
  loader
  loom
  mappings_namespace
  mappings_version
  fabric_api
  java
```

Los resultados deben estar ligados a un `KnowledgeEnvironment` compatible.

Una incompatibilidad de versión debe excluir el resultado, no simplemente reducir su ranking.

---

## 21. Offline y cache

Modelo conceptual inicial:

```text
brain-cache/
 ├── metadata/
 ├── mappings/
 ├── indexes/
 ├── documents/
 └── provenance/
```

La estructura física definitiva se decidirá en RFC.

Online:

```text
resolver
→ fetch
→ validate
→ use
→ cache
```

Offline:

```text
resolver
→ compatible cache
→ use
```

Si falta conocimiento necesario:

```text
OFFLINE_MISS
```

---

## 22. Actualización independiente

El Brain debe separar:

```text
Brain Engine
```

de:

```text
Knowledge / Metadata / Cache
```

Así, una actualización de mappings, metadata o documentación no obliga a actualizar el ejecutable/core de PD Agent.

---

## 23. Trazabilidad

La evidencia mínima de uso debe permitir reconstruir:

```text
KnowledgeNeed
→ resolver elegido
→ source consultada
→ KnowledgeItem IDs
→ provenance
→ elementos seleccionados
→ ContextSource
→ provider request
→ modificación resultante
→ build
→ Minecraft Test Harness
```

No basta con guardar el prompt final.

---

## 24. Arquitectura lógica

```text
                  Fabric Project
                        │
                        ▼
              Environment Resolver
                        │
                        ▼
              KnowledgeEnvironment
                        │
Task ──► KnowledgeNeed │
              │         │
              └────┬────┘
                   ▼
             Minecraft Brain
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
        Cache   Sources   Policies
                   │
                   ▼
             KnowledgeItems
                   │
             + Provenance
                   │
                   ▼
          Knowledge ContextSource
                   │
                   ▼
              AgentRuntime
                   │
                   ▼
                Provider
                   │
                   ▼
                 Tools
                   │
                   ▼
             Fabric Project
                   │
                   ▼
             Gradle / JAR
                   │
                   ▼
          Minecraft Test Harness
```

---

## 25. Acceptance Design

v0.3 debe incluir una fixture/tarea donde una API, símbolo o firma específica de Minecraft/Fabric `1.21.11` sea materialmente relevante.

La condición Brain ON deberá demostrar:

```text
Target Environment
        ↓
KnowledgeNeed
        ↓
Authoritative Source
        ↓
KnowledgeItem
        ↓
Provenance
        ↓
ContextSource
        ↓
Provider real
        ↓
Code change
        ↓
BUILD SUCCESSFUL
        ↓
valid Fabric JAR
        ↓
Minecraft real
        ↓
expected behavior
        ↓
PASS
```

Además deberá ejecutarse:

```text
Brain OFF
vs
Brain ON
```

No se exige que Brain OFF falle.

Se exige que Brain ON demuestre conocimiento externo real, compatible y trazable.

---

## 26. Criterio rector de cierre

PD Agent v0.3 sólo puede considerarse cerrado cuando exista evidencia suficiente para afirmar:

> **PD Agent recuperó conocimiento externo correspondiente al entorno Fabric/Minecraft objetivo, conservó su procedencia, lo incorporó al contexto del agente y lo utilizó para producir una solución que fue validada mediante build y Minecraft real.**

---

## 27. Siguiente documento

Después de este DESIGN debe redactarse:

**RFC — PD Agent v0.3 Minecraft Brain Foundation**

El RFC definirá:

- componentes concretos;
- interfaces;
- modelos de datos;
- contratos;
- errores;
- selección/ranking;
- source adapters;
- cache;
- traces;
- integración exacta con `ContextSource`;
- mecanismos de version resolution;
- políticas de provenance;
- flujo offline;
- fixture de aceptación;
- estrategia de validación.

No debe comenzar implementación antes de:

```text
DESIGN
→ RFC
→ IMP
→ auditoría Codex contra repo real
```
