# PD Agent v0.7 - Minecraft/Fabric Knowledge Foundation IMP

**Estado:** IMP propuesto para auditoria Codex  
**Milestone:** PD Agent v0.7 - Knowledge Foundation  
**Design:** `docs/design/PD_AGENT_V0.7_MINECRAFT_FABRIC_KNOWLEDGE_FOUNDATION_DESIGN.md`  
**RFC:** `docs/rfc/PD_AGENT_V0.7_MINECRAFT_FABRIC_KNOWLEDGE_FOUNDATION_RFC.md`  
**Scope:** Minecraft 1.21.11 + Fabric exclusivamente

> Este documento define como construir la arquitectura aprobada. No implementa
> codigo, no autoriza API/Minecraft/benchmark live y no inicia v0.8.

## 1. Entry gate

La implementacion solo puede comenzar despues de:

1. DESIGN aceptado;
2. RFC aprobado;
3. auditoria Codex del IMP contra el HEAD real;
4. autorizacion explicita de 01 Arquitectura.

En el momento de esta redaccion:

- `HEAD` y `origin/main` son `ebc860fa4efde88ab183d1e615fafbdcc66e48cb`;
- tracked tree limpio;
- `scripts/benchmark/diagnostics/` es el unico untracked permitido;
- no se modifica codigo ni evidencia historica.

Si el HEAD, el Design, el RFC, una ruta o una interfaz difieren de lo
esperado, el lote no se ejecuta. Se reporta la evidencia, se propone un delta
documental y se vuelve a 00; no se adivina ni se implementa una alternativa.

## 2. Real repository map

El baseline auditado contiene estos puntos de integracion reales:

| Area | Baseline reutilizable |
|---|---|
| Brain | `src/pd_agent/brain/models.py`, `retrieval.py`, `resolver.py`, `yarn.py` |
| Context | `src/pd_agent/context/knowledge.py`, `manager.py`, `sources.py`, `models.py` |
| Runtime | `src/pd_agent/runtime/engine.py`, `controller.py`, `src/pd_agent/bootstrap.py` |
| Reporting | `src/pd_agent/reporting/events.py`, `store.py`, `report.py`, `redaction.py` |
| Tools/security | `src/pd_agent/tools/security.py`, `executor.py`, `context.py` |
| Benchmark | `src/pd_agent/benchmark/executor.py`, `collector.py`, `models.py` |
| Tests | `tests/unit/test_l1_brain_environment.py`, `test_l2_brain_retrieval.py`, `test_l3_context_integration.py`, `test_l2_reporting.py` |

No se asume que los nombres de clases nuevas existan. Las rutas nuevas deben
ser confirmadas por la auditoria de cada lote antes de editar.

## 3. Dependency graph

```text
I0 -> I1 -> I2 -> I3 -> I4
                       |-> I5 -> I6 -> I7
                       |-> I8 -> I9 -> I10 -> I11 -> I12 -> I13
                       |-> I14 -> I15 -> I16 -> I17
I3 + I4 + I9 + I13 -> I14
I5 + I6 + I7 + I9 -> I10
I10 + I11 + I12 + I13 + I14 + I15 + I16 -> I17
```

La flecha representa un gate PASS ya committeado y publicado. Ningun lote
depende de uno posterior. I0 no introduce comportamiento; I17 no puede
convertirse en una nueva capability.

## 4. Common contract for every lot

Cada lote debe entregar objetivo, dependencias, archivos probables, contratos,
no-scope, implementacion, tests unitarios, tests offline de integracion,
acceptance/evidence, rollback y commit gate. Ademas:

- no se stagea `scripts/benchmark/diagnostics/`;
- no se incluyen secretos, JARs Minecraft ni source decompilado;
- los tests provider-free son obligatorios salvo el gate runtime expresamente
  indicado;
- antes de editar se repite `git status`, se confirma el HEAD y se inspeccionan
  rutas/interfaces;
- despues de tests PASS se ejecuta `git diff --check`, se revisa staging y se
  hace un commit pequeno y push antes del siguiente lote.

## 5. Lotes

### I0 - Baseline and migration audit

- **Objetivo:** congelar baseline, auditar Design/RFC/IMP y elaborar mapa de
  migracion sin cambiar codigo.
- **Dependencias:** Design y RFC aprobados.
- **Archivos probables:** solo documentos de evidencia; no se autoriza editar
  `src/`.
- **Contratos:** preserva exports, Brain OFF, ToolExecutor, reporting y cache
  historica.
- **No tocar:** codigo, packs, evidence, diagnostics, providers y Minecraft.
- **Trabajo:** comparar interfaces reales, taxonomia historica, licencias,
  dependencias y riesgos; resolver discrepancias documentales antes de I1.
- **Tests:** inventario de comandos y tests existentes; ninguna API.
- **Acceptance/evidence:** audit report con rutas, HEAD, riesgos y decision
  go/no-go.
- **Rollback:** revertir solo el documento de auditoria.
- **Commit gate:** auditoria PASS, `git diff --check`, commit/push documental.

### I1 - Taxonomy and environment compatibility foundation

- **Objetivo:** introducir compatibilidad v0.7 sin romper lectura de modelos
  v0.3 ni inventar valores para entornos desconocidos.
- **Dependencias:** I0.
- **Archivos probables:** `brain/models.py`, `brain/resolver.py`, exports y
  tests `test_l1_brain_environment.py`; confirmar rutas antes de editar.
- **Contratos:** `KnowledgeEnvironment`, detection status, compatibility,
  serializacion y `KnowledgeNeed`.
- **No tocar:** adapters, provider, tools, runtime behavior y acceptance.
- **Trabajo:** representar los ocho tipos normativos; mapping de lectura para
  `MAPPING`, `BUILD`, `MIGRATION`; hard gate para version-sensitive `UNKNOWN`.
- **Tests:** igualdad/compatibilidad, conflict/unknown, taxonomy, round-trip y
  historical cache/trace read.
- **Acceptance/evidence:** environment identity reproducible y migration map.
- **Rollback:** revertir el commit I1; conservar cache historica intacta.
- **Commit gate:** unit PASS, full Brain regression PASS, diff-check, commit/push.

### I2 - Canonical KnowledgeRecord and Pack manifest

- **Objetivo:** modelar record canonico, pack manifest, schema, identity y
  provenance sin materializar fuentes aun.
- **Dependencias:** I1.
- **Archivos probables:** nuevos modulo(s) bajo `src/pd_agent/brain/` o
  `src/pd_agent/knowledge/` solo tras auditoria; exports y tests nuevos.
- **Contratos:** `record_id`, type, content JSON-safe, environment, source,
  authority, provenance, license, integrity y status.
- **No tocar:** provider, prompts, Minecraft JARs, caches historicas ni
  `KnowledgeItem` sin compatibilidad explicita.
- **Trabajo:** JSON canonico UTF-8 determinista, checksum y schema versionado;
  separar canonical de derived.
- **Tests:** schema cerrado, JSON-safe, identidad estable, missing fields,
  checksum, redaction y licencia.
- **Acceptance/evidence:** manifest reproducible de fixture sintetica.
- **Rollback:** eliminar solo nuevos modelos/fixtures y dejar v0.3 igual.
- **Commit gate:** unit/integration offline PASS, commit/push.

### I3 - Pack lifecycle, integrity and freeze

- **Objetivo:** implementar/verificar `DRAFT -> VERIFIED -> FROZEN ->
  SUPERSEDED` y checksums de pack.
- **Dependencias:** I2.
- **Archivos probables:** modulo de pack, storage canonico y tests; no fijar
  ruta definitiva sin auditoria I3.
- **Contratos:** solo VERIFIED/FROZEN sirven conocimiento; FROZEN es requisito
  de reproducibilidad.
- **No tocar:** source adapters, provider, runtime y packs historicos.
- **Trabajo:** validacion de manifest, atomicidad de snapshot, stale detection,
  immutable identity y rebuild metadata.
- **Tests:** transitions, tampered record, checksum mismatch, stale pack,
  repeatable rebuild y crash/partial materialization.
- **Acceptance/evidence:** manifest, tree checksum y lifecycle trace.
- **Rollback:** eliminar pack de test y revertir lifecycle, sin borrar packs
  frozen existentes.
- **Commit gate:** offline PASS, diff-check, commit/push.

### I4 - Ordered multi-source KnowledgeService

- **Objetivo:** implementar el contrato ya decidido para collection,
  supports, compatibility, aggregation y partial failures.
- **Dependencias:** I2, I3.
- **Archivos probables:** evolucion de `brain/retrieval.py` o modulo de service;
  adaptar `KnowledgeSource`, `KnowledgeSourceResult` y tests L2.
- **Contratos:** sources ordenadas por `source_id`; consultar solo elegibles;
  conservar todos los attempts; devolver estados sin ocultar fallos.
- **No tocar:** provider/model context, scheduler, benchmark aggregates.
- **Trabajo:** dedupe cross-source, provenance groups, conflict input y
  provider-agnostic result.
- **Tests:** supports false, incompatible hard gate, source error/unavailable,
  partial success, unsupported need, deterministic ordering y duplicate.
- **Acceptance/evidence:** source-attempt trace y aggregate fixture.
- **Rollback:** volver al adapter single-source mediante commit revertible.
- **Commit gate:** tests retrieval/context existentes y nuevos PASS; commit/push.

### I5 - Yarn mappings source migration

- **Objetivo:** convertir Yarn Tiny v2 exacto de Minecraft 1.21.11 en records
  canonicos `SYMBOL`/`VERSION_CHANGE`.
- **Dependencias:** I3, I4.
- **Archivos probables:** evolucion de `brain/yarn.py`, adapter/marshaller y
  fixtures de mappings; confirmar API Tiny v2 real.
- **Contratos:** version, namespace, revision, SHA-256, license policy y
  environment compatibility.
- **No tocar:** distribuir Minecraft JAR/source decompilado, provider o
  mappings de otra version.
- **Trabajo:** ingest acotado, materializacion legal, ids estables y source
  authority `AUTHORITATIVE_ARTIFACT`.
- **Tests:** symbol exact lookup, namespace/version mismatch, checksum,
  malformed input, license metadata y deterministic output.
- **Acceptance/evidence:** record symbol reproducible y provenance completa.
- **Rollback:** retirar solo adapter/fixture de Yarn v0.7.
- **Commit gate:** offline source tests PASS; commit/push.

### I6 - Fabric API source/materialization

- **Objetivo:** materializar records `API`, `SYMBOL`, `CAPABILITY` desde el
  artifact Fabric API exacto y compatible.
- **Dependencias:** I3, I4, I5.
- **Archivos probables:** adapter Fabric API nuevo bajo la ruta auditada y
  tests de source/pack.
- **Contratos:** dependency lock, artifact revision, SHA-256, license policy.
- **No tocar:** dependencias del producto, otras versiones, live provider.
- **Trabajo:** extractor estructurado limitado al API declarado, sin empaquetar
  JAR no redistribuible; cache reference-only donde corresponda.
- **Tests:** exact version, compatible/incompatible environment, provenance,
  malformed artifact y no leakage.
- **Acceptance/evidence:** API record recuperable desde pack frozen.
- **Rollback:** revertir adapter y materialization, sin tocar build del proyecto.
- **Commit gate:** source/pack offline PASS; commit/push.

### I7 - Concept/pattern source/materialization

- **Objetivo:** records curados `CONCEPT`, `PATTERN`, `EXAMPLE`, `DIAGNOSTIC`
  desde fuente oficial versionada para 1.21.11.
- **Dependencias:** I3, I4.
- **Archivos probables:** adapter curado, policy metadata y fixtures; confirmar
  la fuente y licencia exactas antes de editar.
- **Contratos:** commit/tag inmutable, locator, checksum de extracto y
  `OFFICIAL_DOCUMENTATION`.
- **No tocar:** crawler general, corpus bruto Fabric Docs, answer keys o
  internals Harness.
- **Trabajo:** materializar solo records estructurados permitidos; texto bruto
  queda local/cache-only cuando la licencia lo exige.
- **Tests:** license modes, source pin, schema, no raw corpus, concept lookup y
  diagnostic applicability.
- **Acceptance/evidence:** provenance y policy de distribucion auditables.
- **Rollback:** retirar solo source/fixtures conceptuales.
- **Commit gate:** licensing/offline tests PASS; commit/push.

### I8 - Derived structured index and SQLite FTS5

- **Objetivo:** crear indices exactos/estructurados y SQLite FTS5 derivado,
  reconstruible desde canonical JSON.
- **Dependencias:** I3, I5, I6, I7.
- **Archivos probables:** index service y tests; cache local solo bajo ruta
  confirmada por auditoria.
- **Contratos:** indice no autoritativo, deterministic tokenizer/schema/order,
  pack checksum binding.
- **No tocar:** Knowledge Pack canonical, cloud/vector DB, provider.
- **Trabajo:** exact/structured paths primero; FTS5 solo para lexical; rebuild
  elimina derivados y no altera canonical identity.
- **Tests:** rebuild equivalence, missing/corrupt index, stale pack, Windows
  temp DB, exact/structured/lexical behavior y limits.
- **Acceptance/evidence:** hashes/logical snapshot del indice y rebuild log.
- **Rollback:** borrar/recrear derivado; canonical pack permanece.
- **Commit gate:** index offline PASS; commit/push.

### I9 - Retrieval hard gate, ranking and conflicts

- **Objetivo:** conectar aggregate + pack + index con exact -> structured ->
  lexical, hard compatibility gate y policy de contradicciones.
- **Dependencias:** I1, I4, I5, I6, I7, I8.
- **Archivos probables:** `brain/retrieval.py`, selector bridge y tests L2.
- **Contratos:** incompatible/unknown no llega a selection valida; authority,
  specificity, relevance y id como orden determinista.
- **No tocar:** injection/provider, task prompts, benchmark scoring.
- **Trabajo:** no-result/source-error/unsupported/conflict distintos; conservar
  all provenance y no fusionar verdad contradictoria.
- **Tests:** version isolation, conflicts, dedupe, ranking, missing knowledge,
  limits, cache and deterministic query hash.
- **Acceptance/evidence:** retrieval result y rejection/conflict evidence.
- **Rollback:** desactivar v0.7 service y mantener retrieval v0.3.
- **Commit gate:** Brain L1-L2 and integration offline PASS; commit/push.

### I10 - Selection/context/injection integration

- **Objetivo:** mantener separadas las etapas retrieved, selected e injected y
  conectar el resultado al ContextManager existente.
- **Dependencias:** I9, I8.
- **Archivos probables:** `context/knowledge.py`, `manager.py`, `sources.py`,
  `context/models.py`, `benchmark/executor.py` solo tras auditoria.
- **Contratos:** budgets, ordering, authority, rejection reasons, prepared
  context y provider-agnostic boundary.
- **No tocar:** provider internals, tool permissions, Brain OFF behavior.
- **Trabajo:** ContextItem metadata con pack/record/need/phase; inyeccion solo
  tras hard gate; redaction through existing reporting.
- **Tests:** selected != injected, budget, no compatible item, metadata,
  provider-visible context isolation and regression L3/L7.
- **Acceptance/evidence:** selected/injected ids and context snapshot.
- **Rollback:** feature gate off retorna ContextManager baseline.
- **Commit gate:** context/runtime offline tests PASS; commit/push.

### I11 - PreCodeKnowledgeNeedDeriver

- **Objetivo:** derivar needs bounded antes de la primera edicion desde task,
  fixture, environment y capability signals.
- **Dependencias:** I10.
- **Archivos probables:** `benchmark/executor.py`/`runtime/engine.py` o modulo
  separado confirmado por auditoria; tests nuevos.
- **Contratos:** fase PRE_CODE, maximo 8, tipos permitidos, dedupe y reason.
- **No tocar:** crear otro agente, modificar task/prompt/acceptance o usar
  indiscriminate retrieval.
- **Trabajo:** reutilizar AgentRuntime; cero signals -> cero needs y continuar.
- **Tests:** signals por capability, max limit, dedupe, unknown environment,
  Brain OFF and no pre-edit mutation.
- **Acceptance/evidence:** trace reason and first-edit ordering.
- **Rollback:** feature flag disables derivation without affecting normal flow.
- **Commit gate:** offline runtime/context regression PASS; commit/push.

### I12 - SemanticRepairKnowledgeNeedDeriver

- **Objetivo:** convertir violation/build/runtime evidence en needs bounded para
  el repair existente.
- **Dependencias:** I9, I10, I11.
- **Archivos probables:** `benchmark/functional.py`, `runtime/engine.py`,
  semantic validation modules y tests de repair.
- **Contratos:** maximo 4 por turn; mapping de symbol/signature/Fabric/mapping/
  changed API/runtime/persistence; no answer keys.
- **No tocar:** segundo repair engine, acceptance semantics o Harness internals.
- **Trabajo:** conservar expected/actual, phase, code y evidence refs; retrieval
  compatible -> context -> repair turn -> authoritative validation.
- **Tests:** cada mapping, no-knowledge continuation, source failure, Brain OFF,
  feedback redaction and bounded repeated turns.
- **Acceptance/evidence:** need-to-repair trace correlated with violation.
- **Rollback:** desactivar knowledge-assisted repair, retaining existing repair.
- **Commit gate:** semantic repair offline PASS; commit/push.

### I13 - KnowledgeTrace v0.7 evidence semantics

- **Objetivo:** completar trace `RETRIEVED`, `SELECTED`, `INJECTED`,
  `REFERENCED`, `EVIDENCED` usando reporting existente.
- **Dependencias:** I10, I11, I12.
- **Archivos probables:** `reporting/events.py`, `store.py`, `collector.py`,
  `context/knowledge.py` y tests reporting/collector.
- **Contratos:** RunStorage, `events.jsonl`, evidence payload refs, redaction,
  run/turn/phase/need/record identity.
- **No tocar:** crear trace DB, alterar historical evidence o inferir causalidad
  interna del modelo.
- **Trabajo:** append-only events, correlation with build/artifact/runtime/
  validation, statuses and source attempts.
- **Tests:** event ordering, large payload, restart/read, redaction, each status,
  missing refs and collector round-trip.
- **Acceptance/evidence:** machine-readable trace end-to-end offline.
- **Rollback:** omit new event interpretation; preserve old event schema.
- **Commit gate:** reporting/collector regression PASS; commit/push.

### I14 - Brain OFF, degraded modes and security boundary

- **Objetivo:** cerrar OFF/no injection, degraded outcomes y enforcement de la
  barrera real `SecurePathResolver` + `ToolExecutor`.
- **Dependencias:** I9, I10, I13.
- **Archivos probables:** `context/manager.py`, `tools/security.py`,
  `tools/executor.py`, runtime wiring y security tests.
- **Contratos:** OFF no retrieval/injection; missing knowledge no bloquea si es
  seguro; incompatible/provenance invalid fail closed.
- **No tocar:** inventar `SecurityPolicy`, ampliar path/command/NBT/reflection,
  provider security contracts.
- **Trabajo:** comprobar que knowledge no bypassa path resolver, tool schema,
  protected paths ni redaction; clasificar missing/source failure/degraded.
- **Tests:** OFF/ON, incompatible item, unknown compatibility, corrupt pack,
  tool traversal/protected paths, leakage and partial source failure.
- **Acceptance/evidence:** security and degraded-mode matrix.
- **Rollback:** feature gate OFF; revertir solo wiring v0.7.
- **Commit gate:** security/context/runtime offline PASS; commit/push.

### I15 - Acceptance fixtures and adversarial isolation

- **Objetivo:** construir fixtures offline para A-H y una fixture deliberada
  incompatible; preparar I/I runtime sin live aun.
- **Dependencias:** I3, I5, I6, I7, I9, I13, I14.
- **Archivos probables:** fixtures bajo `tests/fixtures` o ruta existente
  confirmada; tests nuevos; no tocar dataset oficial v0.5.
- **Contratos:** pack frozen 1.21.11 + Fabric, source set minimo, no leakage,
  deterministic rebuild y trace.
- **No tocar:** benchmarks oficiales, provider/API, historical executions,
  diagnostics y respuestas de modelo.
- **Trabajo:** fixture minima con records de las tres familias y corruptions
  controladas; mapear A-H evidence.
- **Tests:** complete offline matrix, adversarial version mismatch, license and
  index deletion/rebuild.
- **Acceptance/evidence:** A-H reportable artifacts with checksums.
- **Rollback:** eliminar fixtures nuevas, no borrar dataset oficial.
- **Commit gate:** offline acceptance A-H PASS; commit/push.

### I16 - Brain ON/OFF integrated runtime acceptance

- **Objetivo:** validar al menos una vertical Minecraft real con Brain ON,
  modification/repair, build, artifact, runtime y PASS, y comparar Brain OFF.
- **Dependencias:** I10-I15.
- **Archivos probables:** harness/fixture existente y runtime integration tests;
  confirmar todos los paths antes de ejecución.
- **Contratos:** conocimiento advisory; build/artifact/Minecraft/Harness son
  autoridades; same fixed environment and pack identity.
- **No tocar:** otras versiones, provider tuning, F9 or statistical benchmark.
- **Trabajo:** ejecutar solo con autorización explícita posterior; conservar
  full evidence and no API outside approved protocol.
- **Tests:** offline setup first; runtime gate ON; OFF control; no leakage.
- **Acceptance/evidence:** I gate with artifact SHA, Minecraft/Harness result,
  trace statuses and reproducible environment.
- **Rollback:** borrar solo execution temp; never alter frozen pack or repo
  evidence; disable integration feature.
- **Commit gate:** runtime PASS and review of evidence before commit.

### I17 - Full regression, readiness and closure

- **Objetivo:** validar A-J, regresion v0.1-v0.6 y readiness documental; no
  introducir capability nueva.
- **Dependencias:** I2-I16.
- **Archivos probables:** tests/regression, validation report and closure doc;
  no production code changes expected for this gate.
- **Contratos:** all RFC gates, provider boundary, Brain OFF, security,
  reproducibility and historical compatibility.
- **No tocar:** v0.8, benchmark statistical claims, F9 official, diagnostics.
- **Trabajo:** unit + offline integration + approved runtime regression,
  compileall, full suite, diff-check and evidence audit.
- **Tests:** acceptance A-J; all existing suite; no API unless separately
  authorized by 00 after offline PASS.
- **Acceptance/evidence:** final matrix, pack/index hashes, traces, runtime
  artifact and regression counts.
- **Rollback:** revert last closure-only commit; preserve prior validated lots.
- **Commit gate:** all PASS, review, closure commit/push.

## 6. Acceptance mapping

| Acceptance | Construction gates |
|---|---|
| A Pack | I2, I3, I8, I15 |
| B Multi-source | I4, I5, I6, I7, I15 |
| C Version isolation | I1, I9, I14, I15 |
| D Pre-code | I10, I11, I13, I15 |
| E Semantic Repair | I10, I12, I13, I16 |
| F Trace | I13, I15, I16 |
| G Brain OFF/ON | I10, I14, I16 |
| H No leakage | I3, I7, I10, I14, I15 |
| I Minecraft runtime | I15, I16 |
| J Regression | I0, I14, I17 |

No acceptance is considered PASS from unit evidence alone when its contract
requires an artifact/runtime observation.

## 7. Test strategy

### Unit

Taxonomy, environment, compatibility, JSON/schema, record identity, manifest,
integrity, source adapters, lifecycle, SQLite index, retrieval, ranking,
dedupe/conflicts, selection, injection metadata, need derivation, trace,
redaction and security.

### Offline integration

Multi-source aggregation, pack rebuild, FTS rebuild, hard gate, Brain OFF,
partial failure, corrupt/stale pack, invalid provenance, historical cache
reading, pre-code derivation, Semantic Repair derivation and reporting
round-trip.

### Runtime

Only I16/I17 acceptance gates use Minecraft. They use an isolated fresh
workspace, fixed Minecraft 1.21.11 + Fabric environment, frozen pack identity
and existing Harness. No provider/API or benchmark is implied by this IMP.

## 8. Licensing and policy implementation plan

Every source materialization records one of `REDISTRIBUTABLE`,
`LOCALLY_MATERIALIZABLE` or `FETCH_CACHE_REFERENCE_ONLY` in manifest and
provenance. Controls belong at ingest, pack publication, cache, trace and
injection. Minecraft JARs and decompiled source are never Knowledge Pack
payloads. Fabric Docs use structured/curated records and locator/policy, not
an indiscriminate raw corpus. A licensing uncertainty rejects publication or
keeps the material local; it never silently changes rights.

## 9. Migration strategy

- Preserve v0.3 classes and read paths while adding explicit schema versions.
- Translate `MAPPING` to `SYMBOL` or `VERSION_CHANGE`; `BUILD` to `API`,
  `PATTERN` or `DIAGNOSTIC`; `MIGRATION` to `VERSION_CHANGE`.
- Never rewrite historical IDs/checksums merely to fit v0.7 taxonomy.
- Historical caches/traces are read-compatible or explicitly degraded; they
  are not silently treated as frozen v0.7 packs.
- New packs accept only the eight normative types and require pack identity,
  provenance, license and integrity.

## 10. Commit and rollback strategy

Each significant lot follows:

```text
offline tests -> diff-check -> staged-file audit -> commit -> push
              -> remote verification -> next lot
```

Suggested commit subjects:

1. `feat: add v0.7 knowledge domain compatibility`
2. `feat: add canonical knowledge packs`
3. `feat: add multi-source knowledge retrieval`
4. `feat: materialize Minecraft Fabric knowledge sources`
5. `feat: add deterministic knowledge indexing`
6. `feat: integrate knowledge context and repair`
7. `feat: persist v0.7 knowledge evidence`
8. `feat: validate v0.7 knowledge acceptance`
9. `docs: close PD Agent v0.7`

The exact commit split may combine adjacent lots only if each gate remains
auditable. Rollback is a revert of the last published lot, never reset/rebase
or deletion of historical evidence. Canonical frozen packs and diagnostics
are never included in rollback or staging.

## 11. Codex pre-implementation audit

After approval of this IMP and before each code change, Codex must compare
DESIGN + RFC + IMP + HEAD against the actual repo: routes, exports, APIs,
dependency versions, Windows behavior, tests, licenses, security boundary,
provider boundary, evidence layout and prior lot commits. A material
contradiction is a STOP condition. The required response is:

1. quote the concrete repo evidence;
2. classify it as compatible migration, RFC change required or blocker;
3. propose the minimum Design/RFC/IMP delta;
4. return to 00 for approval;
5. continue only after the corrected documents are published.

Codex must not invent a module path, source revision, parser capability,
provider capability or fixture behavior. Runtime/provider assumptions require
observable offline or explicitly authorized runtime evidence.

## 12. Decisions pending only for IMP execution

No architecture decision remains open in this IMP/RFC pair. The only remaining
execution details are exact module paths after each audit, exact upstream
revision/checksum values in the frozen pack manifest, concrete test command
syntax, fixture filesystem location and batch commit grouping. None may change
the approved architecture or scope. If one of them exposes a material
contradiction, the Codex audit gate above applies.

## 13. Readiness

This IMP is ready for the required Codex pre-implementation audit. It does
not authorize I0 implementation, API calls, Minecraft live, benchmark runs or
v0.8 work.

**Expected status:** `V0_7_KNOWLEDGE_FOUNDATION_IMP_COMPLETE`
