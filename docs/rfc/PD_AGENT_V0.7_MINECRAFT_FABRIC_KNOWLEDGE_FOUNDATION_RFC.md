# PD Agent v0.7 - Minecraft/Fabric Knowledge Foundation RFC

**Estado:** RFC propuesto para aprobacion de Arquitectura
**Milestone:** PD Agent v0.7 - Knowledge Foundation
**Area:** 03 - Knowledge Base / Minecraft Brain
**Design authority:** `docs/design/PD_AGENT_V0.7_MINECRAFT_FABRIC_KNOWLEDGE_FOUNDATION_DESIGN.md`
**Scope:** Minecraft 1.21.11 + Fabric exclusivamente

> Este RFC define contratos, limites y decisiones tecnicas. No autoriza por si
> mismo implementacion, benchmark, API live ni la creacion de un IMP.

## 1. Decision summary

v0.7 convierte el conocimiento versionado de Minecraft/Fabric en una entrada
trazable y reproducible del Brain, sin convertir al provider en conocedor del
ecosistema:

```text
sources -> canonical/versioned knowledge -> compatibility gate
        -> retrieval -> selection -> injection -> AgentRuntime -> ModelProvider
```

El provider recibe contexto preparado. No conoce Yarn, Fabric, Maven, packs,
indices, caches ni adapters. El conocimiento es asesor; build, artifact,
Minecraft y Harness siguen siendo las autoridades funcionales.

Decisiones de este RFC:

- el registro canonico sera estructurado y versionado en un Knowledge Pack;
- el almacenamiento canonico sera filesystem con JSON determinista;
- cualquier indice derivado sera local, reconstruible y no autoritativo;
- se soportaran adapters de mappings/vanilla, Fabric API y conceptos/patrones;
- la compatibilidad sera un hard gate antes de seleccion e inyeccion;
- retrieval, selection e injection seran etapas observables distintas;
- no habra vector DB, cloud KB, crawler general ni Knowledge Graph;
- el primer entorno soportado sera Minecraft 1.21.11 + Fabric.

## 2. Authority and implementation gate

El Design de v0.7 es la autoridad conceptual. Este RFC fija el contrato
tecnico y debe ser leido junto al Design. Un futuro IMP podra fijar lotes y
rutas solo despues de que Arquitectura apruebe este RFC y la auditoria contra
el repo resuelva las discrepancias documentadas en la seccion 18.

La implementacion podra comenzar unicamente despues de:

1. Design y RFC aprobados;
2. auditoria de interfaces, seguridad, fuentes y licencia contra el repo;
3. autorizacion explicita de 01 Arquitectura.

La implementacion no podra declararse validada ni habilitar una candidata
hasta que la matriz offline, persistencia, reproducibilidad, regresiones y
verificacion de las capacidades del SDK/provider tengan resultado PASS, y
exista autorizacion posterior para cualquier live.

## 3. Scope and taxonomy

La taxonomia normativa de v0.7 es exactamente:

| Tipo | Uso |
|---|---|
| `SYMBOL` | clases, metodos, campos, firmas e identificadores |
| `API` | contratos y entry points de APIs |
| `CONCEPT` | significado tecnico y modelo mental |
| `PATTERN` | secuencias o soluciones generales |
| `EXAMPLE` | ejemplo minimo, sin answer key ni solucion oculta |
| `VERSION_CHANGE` | cambio, sustitucion, retirada o deprecacion |
| `CAPABILITY` | capacidad funcional agrupada |
| `DIAGNOSTIC` | conocimiento aplicable a un fallo observable |

`MAPPING`, `BUILD` y `MIGRATION` existentes en el dominio v0.3 son una
discrepancia de nomenclatura documentada, no una ampliacion de scope. Durante
la implementacion deberan mapearse de forma explicita a la taxonomia objetivo
o mantenerse como compatibilidad de lectura sin introducir una novena
categoria normativa.

## 4. Knowledge Pack

Un Knowledge Pack es un snapshot inmutable e identificable de registros
canonicos para un entorno y conjunto de fuentes declarados. Su identidad es
estable y se calcula sobre bytes canonicos, no sobre timestamps ni orden del
filesystem.

### 4.1 Manifest obligatorio

El manifest del pack contiene al menos:

- `pack_id`, `schema_version`, `created_at` y `status`;
- entorno completo y `environment_identity`;
- `source_set` con source id, tipo, revision, licencia y autoridad;
- identidad de cada input, checksum y algoritmo;
- `canonical_records_root` y checksum del conjunto ordenado;
- `derived_indexes` como artefactos no autoritativos;
- politica de licencia, redistribucion y materializacion local;
- herramienta/version de materializacion y encoding;
- lista de exclusiones y resultado de integrity check.

El manifest, los registros y los checksums deben ser serializables sin
secretos. Un pack no se considera usable si falta identidad, checksum,
provenance, licencia o evidencia de integridad.

### 4.2 Canonical versus derived

Los JSON canonicos son la fuente de verdad. Un indice lexical, FTS o cache de
consulta puede borrarse y reconstruirse desde ellos sin cambiar su identidad.
Un indice no puede introducir contenido, corregir una contradiccion ni
convertir texto no autorizado en conocimiento canonico.

El lifecycle es `DRAFT -> VERIFIED -> FROZEN -> SUPERSEDED`. Solo `VERIFIED`
o `FROZEN` puede servir a una ejecucion; `FROZEN` es el estado requerido para
una evaluacion reproducible. No se sobrescribe un pack frozen: una actualizacion
crea otro pack y conserva el anterior.

## 5. Canonical Knowledge Record

Cada record canonico debe contener:

```json
{
  "record_id": "stable-id",
  "schema_version": "v0.7",
  "type": "SYMBOL",
  "title": "short human-readable title",
  "content": {},
  "environment": {},
  "source": {},
  "authority": "AUTHORITATIVE_ARTIFACT",
  "provenance": {},
  "license_policy": {},
  "integrity": {},
  "relations": [],
  "tags": [],
  "status": "VERIFIED"
}
```

Obligatorios: `record_id`, schema, type, content, environment, source,
authority, provenance, license policy, integrity y status. Opcionales:
title, tags, relations, deprecation/change metadata, applicability hints y
diagnostic selectors. `content` es JSON seguro y estructurado; no contiene
objetos Python, codigo ejecutable, credenciales, answer keys ni internals del
Harness.

La identidad canonica se calcula con JSON UTF-8, claves ordenadas, separadores
deterministas y campos de identidad definidos por schema. `retrieved_at` no
forma parte del contenido canonico cuando solo describe una observacion.

## 6. Environment model and compatibility

El entorno debe representar, como minimo:

- Minecraft version;
- Fabric Loader version;
- Fabric API version;
- mappings namespace y version;
- Loom version;
- Java version;
- cualquier profile/namespace adicional necesario para interpretar el record.

La igualdad compara todos los campos declarados relevantes. La compatibilidad
puede ser `COMPATIBLE`, `INCOMPATIBLE` o `UNKNOWN`; la deteccion del proyecto
puede ser `DETECTED`, `UNKNOWN` o `CONFLICT`.

- Exact match permite conocimiento version-sensitive.
- Un campo desconocido no equivale a wildcard.
- Un record incompatible nunca se selecciona ni inyecta.
- `UNKNOWN` falla cerrado para contexto valido; solo puede aparecer en un modo
  diagnostico explicitamente etiquetado y no autoritativo.
- Conflicto entre fuentes del proyecto impide adivinar el entorno.

La comparacion debe ser determinista y conservar evidencia de cada campo y de
la razon del resultado. Cambios de Minecraft, mappings, loader o API requieren
nuevo pack o una relacion `VERSION_CHANGE` aprobada.

## 7. Source adapters

Todos los adapters cumplen una frontera equivalente a:

```text
supports(need) -> bool
compatibility(environment) -> status
materialize/resolve(need, pack_context) -> source result
```

El adapter devuelve items y provenance, pero no decide que llega al modelo ni
llama al provider.

### 7.1 Fuentes v0.7

1. **Vanilla/mappings:** simbolos, firmas y mappings de artefactos autorizados.
2. **Fabric API:** contratos y entry points de la version declarada.
3. **Concept/pattern:** documentacion oficial o material local permitido para
   explicar conceptos y patrones.

Cada categoria puede tener varias fuentes, pero su autoridad, revision,
licencia y compatibilidad se verifican independientemente. No se implementa
un crawler general. La ausencia de una fuente no se rellena con memoria del
modelo ni con una fuente de version desconocida.

### 7.2 Ingest y materializacion

Se rechaza o marca como no usable cualquier input con checksum incorrecto,
schema invalido, licencia desconocida, revision mutable no fijada, entorno
incompleto, duplicado contradictorio no resuelto o contenido no JSON seguro.
Un fallo parcial no publica un pack como completo. El resultado conserva
`source_error`, `unsupported`, `invalid_provenance` o `integrity_failure` con
evidencia suficiente para reproducirlo.

## 8. Storage and rebuild

La decision inicial es filesystem estructurado: manifest del pack y records
JSON canonicos en rutas derivadas de pack/record. Es portable, auditable y no
requiere un servicio. Se permite un indice local SQLite FTS o equivalente como
artefacto derivado si mejora retrieval lexical; no es obligatorio para
consultas exactas ni puede ser la fuente autoritativa.

No se permite vector database, almacenamiento cloud, servicio distribuido ni
Knowledge Graph en v0.7. El rebuild verifica primero el manifest y los
checksums, elimina/recrea solo derivados y produce el mismo indice para los
mismos bytes y herramienta.

## 9. Retrieval

`KnowledgeNeed` es una consulta pequena y especifica con id, tipo, query,
entorno y hints limitados. No contiene documentacion completa ni instrucciones
operativas.

El orden obligatorio es:

1. exacto por record id/simbolo/clave;
2. estructurado por tipo, relaciones, tags y entorno;
3. lexical acotado por texto normalizado.

Semantic/vector retrieval queda fuera. El ranking considera compatibilidad
primero, autoridad, version/especificidad, exactitud, relevancia y record id
como desempate determinista. Hay limites de resultados, bytes y tiempo.

El compatibility gate se ejecuta antes de que un item sea elegible. Se
conservan misses, source failures, incompatibilidades, cache hit/miss,
checksum, revision y query identity. `NO_COMPATIBLE_KNOWLEDGE` no es igual a
`SOURCE_ERROR` ni a `UNSUPPORTED_NEED`.

Contradicciones materiales no se fusionan silenciosamente. Una fuente
autoritaria compatible puede ganar solo cuando las reglas de version y
autoridad lo justifican; de otro modo el need queda degradado o bloqueado y
no se inyecta como verdad.

## 10. Selection

Retrieved no significa selected. El selector:

- deduplica por identidad/contenido/version;
- rechaza incompatibles y provenance invalida;
- aplica autoridad y relevancia deterministas;
- aplica presupuesto de items y bytes;
- registra cada rechazo y el motivo;
- produce `SelectedKnowledge` con ids y trazabilidad.

Ningun ranking puede elevar conocimiento incompatible. Seleccion vacia es un
resultado explicito y permite continuar sin Brain cuando el flujo seguro lo
permita.

## 11. Injection

Selected no significa injected. El `ContextSource` convierte solo seleccion
valida en contexto etiquetado, limitado y ordenado. Cada item inyectado lleva
record id, need id, entorno, autoridad, source, revision, checksum y etapa.

La inyeccion debe respetar el presupuesto global de contexto y la prioridad de
las fuentes del runtime. Si falla serializacion, licencia, limite o integridad,
el item no se inyecta y queda una razon observable. El provider solo ve el
contexto preparado; nunca los objetos internos de Knowledge Foundation.

## 12. Pre-code knowledge

Antes de la primera mutacion, el flujo puede derivar needs a partir de la task,
fixture y entorno resuelto:

```text
task -> bounded needs -> compatible retrieval -> selection -> injection
     -> provider -> first edit
```

El derivador produce un numero pequeno y justificable de needs, no recupera
todo el pack. Cada need debe tener razon y phase `PRE_CODE`. Si no hay
conocimiento, el agente puede continuar por tools/build/runtime cuando sea
seguro; no se bloquea una task ordinaria por un miss advisory.

## 13. Semantic Repair integration

Semantic Repair conserva sus contratos actuales y puede solicitar knowledge
despues de evidencia de build, artifact, runtime o validation:

```text
failure evidence -> need -> compatibility gate -> selection -> injection
                  -> repair turn -> authoritative validation
```

Debe soportar al menos necesidades `API`, `SYMBOL`, `VERSION_CHANGE`,
`DIAGNOSTIC`, `PATTERN` y `CAPABILITY` cuando la evidencia las justifique.
El feedback incluye expected/actual, phase, violation code y evidence refs,
pero no answer keys ni internals del Harness. Knowledge no reemplaza la
evidencia determinista ni convierte una reparacion en PASS sin build/runtime
valido.

## 14. Trace and evidence

La traza por need/run conserva pack id, environment identity, query hash,
source attempts, record ids, authority, revision, checksum, decision y fase.
Estados obligatorios:

- `RETRIEVED`: el adapter devolvio un candidato compatible;
- `SELECTED`: el selector lo eligio;
- `INJECTED`: el ContextSource lo puso a disposicion del provider;
- `REFERENCED`: una salida/feedback cita el record o need;
- `EVIDENCED`: una validacion autoritativa observa un resultado asociado.

Los estados no prueban causalidad interna del LLM. `REFERENCED` no implica que
el modelo uso realmente el conocimiento, y `EVIDENCED` no elimina la necesidad
de la ruta normal de validacion.

## 15. Brain OFF and ON

Con Brain OFF:

- no se derivan ni recuperan fuentes externas;
- no se lee/inserta un Knowledge Pack en contexto;
- no se escribe traza de conocimiento como si hubiera retrieval;
- AgentRuntime, tools, build, runtime y acceptance conservan su conducta
  normal.

Con Brain ON, solo se permite el flujo bounded de este RFC. Cambiar el flag no
puede cambiar task, prompt, acceptance, provider, seguridad ni answer keys.

## 16. Failure and degraded modes

| Condicion | Resultado |
|---|---|
| need no soportado | `UNSUPPORTED_NEED`, flujo normal si es seguro |
| fuente no disponible | `SOURCE_UNAVAILABLE`, usar pack frozen compatible si existe |
| error de fuente | `SOURCE_ERROR`, no fabricar conocimiento |
| version incompatible | `VERSION_MISMATCH`, no seleccionar/injectar |
| compatibilidad desconocida | `NO_COMPATIBLE_KNOWLEDGE` en modo valido |
| provenance/checksum invalido | `PROVENANCE_INVALID`, excluir record |
| cache/indice corrupto | `CACHE_ERROR`, rebuild derivado o miss |
| contradiccion no resoluble | degraded/blocked, no verdad no cualificada |
| pack integro inexistente | blocked para ese need, no answer del modelo como fuente |

Estos estados son del Knowledge Foundation. No deben reinterpretarse como
`FAIL` funcional, `BLOCKED` de infraestructura o `INVALID` metodologico del
benchmark sin pasar por sus contratos propios.

## 17. Security and licensing

No se distribuyen Minecraft JARs, source decompilado, credenciales, dumps,
answer keys, soluciones ocultas ni internals del Harness como knowledge.
Cada fuente declara si es redistributable, local-only, reference-only o
fetch/cache-only. Las restricciones de licencia se aplican en ingest, pack,
cache, trace e injection, no solo al final.

El output del LLM nunca es autoridad canonica. Knowledge no otorga path
capability, command capability, reflection, arbitrary NBT access ni bypass de
SecurityPolicy/ToolExecutor. Los textos se tratan como datos y se mantienen
separados de instrucciones operativas.

## 18. Audited repository baseline and discrepancies

La auditoria de este RFC inspecciono `brain/models.py`, `brain/retrieval.py`,
`brain/resolver.py`, `context/knowledge.py`, `benchmark/executor.py`, exports,
tests L1-L3, AgentRuntime, Semantic Repair, SecurityPolicy, ToolExecutor y
evidencia/Harness existente.

Coincidencias confirmadas:

- existen `KnowledgeEnvironment`, `KnowledgeNeed`, `KnowledgeItem` y
  `KnowledgeProvenance` serializables;
- existen `SourceAuthority`, compatibility y estados de retrieval;
- `FileKnowledgeCache` ya es local y JSON;
- `MinecraftBrain` ya comprueba compatibilidad, cachea, deduplica y devuelve
  resultados deterministas;
- `KnowledgeSelector` separa retrieval de selection y aplica presupuesto;
- `KnowledgeContextSource` separa selection de injection y conserva trace;
- AgentRuntime/benchmark ya pueden funcionar con resultado sin knowledge.

Discrepancias e impacto:

1. El enum v0.3 no coincide exactamente con la taxonomia v0.7 y contiene
   `MAPPING`, `BUILD`, `MIGRATION`. Impacto: posible incompatibilidad de schema
   y queries. Decision: mapping/version de schema explicito antes de publicar
   packs v0.7; no cambiarlo en esta RFC.
2. `MinecraftBrain` acepta una sola `KnowledgeSource`. Impacto: no cumple aun
   multi-source. Decision: un futuro trabajo de implementacion añadira un
   agregador bounded sin cambiar el contrato del provider.
3. `FileKnowledgeCache` cachea resultados por source/query, pero no existe aun
   manifest de pack ni separacion formal canonical/derived. Impacto:
   reproducibilidad de pack no demostrada. Decision: introducirla solo en la
   implementacion autorizada.
4. El retrieval actual permite continuar con compatibilidad `UNKNOWN` fuera
   de offline. Impacto: el hard gate de este RFC es mas estricto. Decision:
   v0.7 debe etiquetar ese camino y cerrarlo para contexto valido; no asumir
   que la conducta actual ya satisface el RFC.
5. El trace actual modela retrieval/selection/context, pero no demuestra por
   si solo `REFERENCED` y `EVIDENCED` con la semantica completa. Impacto: la
   acceptance de trazabilidad requiere ampliacion verificable.

Estas son decisiones conscientes de frontera, no bugs ocultos ni autorizacion
de implementacion. Si Arquitectura rechaza alguna, el RFC vuelve a revision.

## 19. Update, freeze and reproducibility

La identidad de una ejecucion registra pack id, manifest checksum, schema,
environment identity, source revisions e indice version. Rebuild con los mismos
inputs debe producir los mismos records, ids, orden y resultados de retrieval.
Una fuente actualizada crea nuevo revision/pack; nunca muta silenciosamente
uno frozen. `VERSION_CHANGE` expresa diferencias conocidas entre entornos.

Un pack stale no sustituye el frozen esperado. Un checksum o manifest drift
bloquea uso autoritativo y queda en evidencia. La limpieza de indices derivados
no altera el pack ni su identidad.

## 20. Acceptance and test architecture

La futura implementacion debera demostrar offline, sin provider:

**A - Pack:** manifest, records, checksum, freeze y rebuild reproducible.
**B - Multi-source:** las tres categorias mediante mas de un adapter.
**C - Isolation:** record incompatible no llega a contexto.
**D - Pre-code:** need aplicable recuperado e inyectado antes de la primera mutacion.
**E - Repair:** fallo real -> need -> retrieval -> injection -> repair -> build/runtime PASS.
**F - Trace:** RETRIEVED/SELECTED/INJECTED/REFERENCED/EVIDENCED completos.
**G - Brain OFF/ON:** OFF no inyecta y ON respeta gates.
**H - No leakage:** sin answer keys, Harness internals ni conocimiento incompatible.
**I - Runtime:** knowledge no sustituye Harness ni acceptance.
**J - Regression:** v0.1-v0.6 siguen PASS y no cambia el provider contract.

Los tests deben cubrir miss, source unavailable, unknown/incompatible
environment, checksum/licencia, contradiccion, limites, cache rebuild,
determinismo, redaccion y security. Las capacidades del SDK/provider se
verifican con comportamiento observable y fixtures controladas, nunca por
suposicion de nombres o capabilities.

## 21. Deferred work

Queda fuera de v0.7: embeddings/vector retrieval, Knowledge Graph, cloud o
servicio distribuido, crawler amplio, corpus automatico de migracion,
Paper/NeoForge/Velocity, rendering/GUI/networking/entities/worldgen y nuevas
capabilities no incluidas en el Design. v0.8 no se inicia con este RFC.

## 22. Open implementation questions

Antes del IMP deben cerrarse con evidencia: schema final de manifest/record,
adapter concreto y licencia de cada fuente, agregador multi-source, indice
derivado exacto, resolucion de contradicciones, persistencia de trace y
derivacion de needs task/failure. Resolverlas no puede relajar el hard gate,
seguridad, reproducibilidad ni la separacion provider/knowledge.

## 23. RFC acceptance

Este RFC queda **propuesto**, no CLOSED. La aprobacion debe confirmar que sus
decisiones implementan el Design aceptado, que el grafo de futuras tareas sera
acíclico y que las discrepancias de la seccion 18 tienen plan verificable.
Solo despues puede redactarse un IMP; no se crea automaticamente aqui.

**Resultado esperado tras aprobacion:** `V0_7_KNOWLEDGE_FOUNDATION_RFC_APPROVED`
