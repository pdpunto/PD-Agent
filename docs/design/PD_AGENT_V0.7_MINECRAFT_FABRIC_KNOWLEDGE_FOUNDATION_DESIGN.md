# PD Agent v0.7 — Minecraft/Fabric Knowledge Foundation DESIGN

## 1. Status

**Status:** DESIGN COMPLETE — ready for RFC review  
**Milestone:** PD Agent v0.7 — Minecraft Brain / Knowledge Foundation  
**Baseline audited:** `054a27d305e7bd398fb7d2ee555ff0f6111bc1ad`  
**Target:** Minecraft `1.21.11` + Fabric only

This document defines **WHAT** v0.7 must achieve. It intentionally does not define parser classes, storage schemas, concrete index technology, or implementation sequencing.

## 2. Context

PD Agent v0.6 is CLOSED / PASS and already supports modification, build/debug, Semantic Repair, artifact validation, Minecraft execution, Test Harness validation, persistence/reopen, and the Fabric capabilities used as the initial knowledge scope.

The existing Brain from v0.3 is a valid architectural base. At the audited baseline it already models versioned `KnowledgeEnvironment`, `KnowledgeNeed`, knowledge/provenance/authority, compatibility and retrieval outcomes, cache, deterministic retrieval, selection/context integration and trace concepts. Its production retrieval orchestrator is currently single-source and the concrete knowledge is principally Yarn Tiny v2 symbol/mapping knowledge.

v0.7 evolves that base; it does not replace it without evidence.

## 3. Problem Statement

PD Agent can act on Fabric projects, but it cannot yet treat external, version-specific Minecraft/Fabric knowledge as a broad source of truth. For APIs, patterns, version changes and diagnostics it can still depend excessively on model knowledge or on compiler/runtime feedback after an error occurs.

v0.7 must make external knowledge a first-class, versioned, traceable and reproducible input to reasoning and repair, while preventing incompatible or unsafe knowledge from reaching the model as valid context.

## 4. Goals

v0.7 SHALL:

1. provide a reproducible Knowledge Pack for Minecraft 1.21.11 + Fabric;
2. support multiple categories of authoritative/official knowledge source;
3. represent enough knowledge for the v0.6 Fabric capability surface;
4. isolate knowledge by explicit environment compatibility;
5. retrieve deterministically/structurally before falling back to lexical/text retrieval;
6. provide relevant knowledge before the first edit when the task exposes known Fabric needs;
7. provide applicable knowledge to Semantic Repair after build/runtime/validation failures;
8. distinguish retrieved, selected, injected, referenced and evidenced knowledge;
9. preserve Brain OFF as a real control with no external knowledge injection;
10. remain model-agnostic;
11. make canonical knowledge reproducible independently of rebuildable indexes;
12. leave a clean evolutionary path to future Minecraft/Fabric versions without implementing multi-version support now.

## 5. Non-Goals

v0.7 does NOT include:

- rendering;
- GUI/screens;
- complex networking;
- entities;
- worldgen;
- Paper, NeoForge or Velocity;
- complete multi-version support;
- embeddings or vector DB;
- Knowledge Graph;
- PostgreSQL or Elasticsearch;
- Internet-wide crawling;
- cloud KB service;
- Multi-Agent;
- UI;
- Model Router;
- texture/asset generation;
- statistical provider benchmarking.

## 6. User / Product Value

For v0.7, “PD Agent knows Fabric 1.21.11” means that for the supported capability scope it can obtain relevant external knowledge whose source and compatible environment are known, deliver only compatible selected knowledge to the model, and preserve enough evidence to reproduce what was available to the run.

It does **not** mean that every Minecraft/Fabric API is ingested, that the Brain replaces build/runtime validation, or that retrieved knowledge proves causal use by the model.

The value is reduced dependence on latent model memory, earlier correct implementation choices, more informed repairs, and reproducible technical evidence.

## 7. Current Brain Baseline

The audited baseline already provides reusable concepts for:

- `KnowledgeEnvironment`;
- `KnowledgeNeed` / `KnowledgeType`;
- knowledge items and provenance;
- source authority;
- compatibility states;
- deterministic retrieval outcomes;
- file cache;
- `MinecraftBrain`;
- selection/context integration;
- knowledge tracing.

`KnowledgeEnvironment` already contains Minecraft, Loader, Loom, mappings namespace/version, Fabric API and Java fields. Provenance already has source identity/kind/locator, version/revision, retrieval time, checksum and license/policy fields.

The current `MinecraftBrain` production orchestrator accepts one `KnowledgeSource`, performs compatibility checking, cache lookup and deterministic deduplication. This single-source boundary is a current limitation to evolve in v0.7, not a reason to discard the existing contracts.

## 8. Target Knowledge Foundation

The target is a **Versioned Multi-Source Knowledge Foundation** between external/local knowledge sources and runtime context:

`Sources → canonical/versioned knowledge → compatibility gate → retrieval → selection → injection → Agent Runtime → ModelProvider`

The ModelProvider SHALL NOT know about Yarn, Maven, Fabric Docs, source adapters, indexes, caches or Knowledge Packs.

The Knowledge Foundation is advisory knowledge, not a replacement for compiler, artifact validator, Minecraft runtime or Test Harness authority.

## 9. Knowledge Environment

A v0.7 knowledge environment SHALL be able to identify at minimum:

- Minecraft version;
- Fabric Loader version;
- Fabric API version;
- mappings scheme/namespace;
- mappings version.

Tooling metadata such as Loom and Java MAY participate when compatibility or reproducibility requires it.

The design SHALL NOT assume Yarn is the permanent mapping scheme.

The first supported environment is the frozen Minecraft 1.21.11 Fabric environment used by v0.7. Unknown or conflicting environment identity SHALL NOT be silently treated as compatible.

## 10. Knowledge Packs

A **Knowledge Pack** is an immutable, identifiable materialized snapshot of canonical knowledge for a declared environment and source set.

A valid pack SHALL:

- declare its environment identity;
- declare included source identities and revisions/versions;
- preserve provenance and authority for its records;
- preserve integrity identity/checksums sufficient for reproducibility;
- declare applicable license/policy treatment;
- be independently identifiable from mutable “latest” upstream state;
- permit derived indexes to be rebuilt without changing canonical knowledge;
- remain reproducible after a future pack for another Minecraft version is created.

A pack is invalid for injection if its required identity/integrity/compatibility guarantees cannot be established.

v0.7 creates only the Minecraft 1.21.11 + Fabric pack.

## 11. Knowledge Taxonomy

The exact v0.7 taxonomy is:

- **SYMBOL** — class/method/field/signature/mapping knowledge;
- **API** — public API contracts relevant to supported work;
- **CONCEPT** — technical concepts needed to reason correctly;
- **PATTERN** — version-compatible ways of combining APIs/concepts;
- **EXAMPLE** — selective authoritative/official usage examples;
- **VERSION_CHANGE** — explicit changed/removed/deprecated/replaced knowledge between environments;
- **CAPABILITY** — knowledge grouped by supported functional capability;
- **DIAGNOSTIC** — knowledge applicable to observable build/runtime/validation failures.

These eight categories are sufficient for v0.7. Existing v0.3 types such as `MAPPING`, `BUILD` and `MIGRATION` are implementation-compatibility concerns for the RFC; the DESIGN does not require adding further product taxonomy categories.

## 12. Knowledge Record Requirements

A canonical knowledge record SHALL have enough information to establish:

- stable identity;
- knowledge kind;
- compatible environment or compatibility constraint;
- relevant capability when applicable;
- relevant symbols when applicable;
- human/model-consumable knowledge payload or description;
- relations to other records when materially useful;
- source identity and provenance;
- authority;
- source version/revision;
- integrity/checksum identity where applicable;
- license/policy treatment.

The RFC SHALL define the concrete schema. The DESIGN does not require every optional semantic relation to be populated and does not require a graph database.

## 13. Source Requirements / Authority

v0.7 requires source categories sufficient to demonstrate:

1. vanilla/mapping knowledge;
2. Fabric API knowledge;
3. concept/pattern knowledge.

Candidate source families are:

- Yarn mappings/Javadocs;
- Fabric API source/Javadocs;
- relevant Fabric Loader API/source/Javadocs;
- Fabric Docs/reference 1.21.11 subject to license/policy;
- Fabric Meta;
- Maven metadata/artifacts;
- selective official examples;
- locally derived vanilla knowledge where legal and technically appropriate.

**Source authority** means the confidence class attached to the origin of a fact, not a claim that every statement from that source is universally correct. Direct versioned artifacts/source are preferred for exact symbols/contracts; official documentation/examples are preferred for intended usage/concepts. Secondary sources are not required for v0.7.

Every injected record SHALL retain source attribution/provenance internally.

## 14. Version Compatibility / Isolation

Compatibility is a **hard gate**.

Knowledge known to be incompatible with the active environment SHALL NOT be selected or injected as valid context regardless of textual relevance or ranking score.

Unknown compatibility SHALL fail closed for valid-context injection unless the RFC defines a separately labelled non-authoritative diagnostic mode that cannot be mistaken for compatible knowledge.

`VERSION_CHANGE` exists to represent explicit differences; it does not authorize leaking the incompatible side as current API guidance.

A deliberate adversarial incompatible record SHALL be part of v0.7 validation.

## 15. Retrieval Behaviour

The required priority is:

`exact/deterministic > structured > lexical/text > semantic future`

v0.7 SHALL support the first three levels where required by its acceptance scenarios. Semantic retrieval is deferred.

Retrieval SHALL be constrained by the active environment before knowledge becomes eligible for selection. It SHALL preserve source/result evidence and distinguish “no result” from source failure, incompatibility and unsupported need.

If two sources conflict, the system SHALL NOT silently merge the contradiction into a single asserted truth. Exact versioned artifacts/source outrank interpretive documentation for exact API/symbol facts. Unresolved material contradictions SHALL be surfaced as degraded/blocked knowledge for that need rather than injected as unqualified truth.

## 16. Selection / Injection Behaviour

Selection SHALL choose only relevant, compatible records within a bounded context budget. Authority, exactness, capability relevance and need relevance SHALL be available selection signals.

**SELECTED is not INJECTED.**

A record becomes INJECTED only when its content is actually delivered in model context for the relevant provider turn. Truncation, budget rejection, Brain OFF or later context assembly changes must not be reported as injection.

The provider receives prepared knowledge context, not Knowledge Foundation internals.

## 17. Pre-Code Knowledge Behaviour

For supported Fabric tasks, PD Agent SHALL be able to derive knowledge needs before the first mutation/edit when the task clearly implicates known capabilities.

Expected flow:

`task → identify applicable knowledge needs → retrieve compatible records → select → inject → provider → first edit`

Pre-code retrieval is advisory and bounded. Missing knowledge SHALL NOT automatically prevent work when the task can safely continue using normal tools/build/runtime evidence.

The v0.7 capability scope is:

- registries;
- items;
- blocks;
- Data Components;
- Block Entities;
- inventories;
- persistence;
- commands;
- events;
- tags;
- recipes;
- loot.

The pack need only contain the minimum knowledge required to make these supported areas materially useful in v0.7 acceptance scenarios; it is not a complete Fabric corpus.

## 18. Semantic Repair Behaviour

Semantic Repair SHALL be able to request/receive compatible knowledge derived from failures including:

- cannot-find-symbol;
- incorrect method/signature;
- incorrect Fabric API usage;
- mapping mismatch;
- changed/removed API;
- build diagnostics;
- runtime failures;
- applicable persistence/runtime validation failures.

Expected flow:

`failure evidence → knowledge need → retrieval/version gate → selection/injection → repair turn → build/runtime validation`

Knowledge supplements the existing deterministic failure evidence. It SHALL NOT include benchmark answer keys, hidden reference solutions or Harness internals.

A knowledge-assisted repair is not PASS until the existing authoritative validation path reaches the required successful result.

## 19. Trace / Evidence Semantics

v0.7 SHALL persist/reconstruct five distinct states:

- **RETRIEVED:** a compatible candidate was returned by Knowledge Foundation retrieval;
- **SELECTED:** the selector chose the record for a specific context opportunity;
- **INJECTED:** the record was actually included in provider-visible context for a specific turn;
- **REFERENCED:** a later agent action/output can be associated with the record by explicit traceable reference or deterministic linkage defined by RFC; this is not proof of causality;
- **EVIDENCED:** subsequent authoritative evidence (for example build/runtime/Test Harness) validates an outcome materially associated with the knowledge-assisted action.

The trace SHALL retain environment, record identity, source/provenance, stage/turn association and enough deterministic identity to reproduce the knowledge path.

No state SHALL imply absolute causal proof that the LLM “used” knowledge internally.

## 20. Update / Reproducibility Requirements

Canonical knowledge SHALL be separable from derived indexes. Derived indexes SHALL be rebuildable from canonical records.

A future upstream change SHALL NOT mutate the identity/content of an already frozen valid pack. A new source revision or Minecraft/Fabric environment produces a new pack/revision according to RFC rules.

**Stale knowledge** is knowledge whose declared source/environment/revision no longer satisfies the active pack/environment policy, or whose upstream mutability cannot be reconciled with the frozen identity expected by the pack. Stale knowledge SHALL NOT silently replace frozen canonical knowledge.

Updating the KB SHALL preserve previous reproducible packs and allow explicit `VERSION_CHANGE` knowledge when differences are known.

## 21. Security / Licensing Requirements

v0.7 SHALL be conservative by design:

- do not distribute Minecraft JARs or decompiled Minecraft source as Knowledge Pack payloads;
- distinguish redistributable knowledge from locally materialized knowledge and reference/fetch/cache-only knowledge;
- preserve source license/policy metadata;
- prevent a source ingestion path from silently changing distribution rights;
- treat Fabric Docs content conservatively because the prior audit identified CC BY-NC-SA 4.0 implications;
- avoid mass copying documentation where metadata/reference or selective permitted material is sufficient;
- do not expose hidden benchmark/reference-solution knowledge through the Brain;
- do not treat model-generated statements as authoritative canonical source records merely because a model produced them.

This is a technical product policy, not definitive legal advice. Ambiguous redistribution rights SHALL fail closed for bundled distribution until separately resolved.

## 22. Failure / Degraded Behaviour

If knowledge is missing, the Brain SHALL return an explicit no-knowledge/unsupported outcome; normal agent/tool/build/runtime workflows may continue when safe.

If a source is temporarily unavailable, a previously frozen and verified compatible pack MAY continue to serve its canonical knowledge. If required knowledge was never materialized and cannot be obtained, the need degrades explicitly rather than fabricating knowledge.

If integrity/provenance is invalid, affected knowledge SHALL NOT be injected as valid knowledge.

If sources materially contradict each other and authority/version rules cannot resolve the conflict, the need SHALL degrade or block knowledge injection for the conflicting fact.

If the active environment is unknown/conflicting, version-sensitive knowledge SHALL fail closed.

With **Brain OFF**:

- no external Brain knowledge is injected;
- no selected record may be reported as injected;
- ordinary project files, compiler output, runtime evidence and user-provided context remain available through their normal non-Brain paths;
- trace SHALL make the absence of Brain injection reproducible.

## 23. Compatibility with v0.1–v0.6

v0.7 SHALL preserve all established authority boundaries and validated capabilities from v0.1–v0.6.

In particular:

- ModelProvider remains model-agnostic;
- compiler/build remains authority for compilation;
- ArtifactValidator remains authority for artifact validity;
- Minecraft/Test Harness remains authority for runtime observations;
- Semantic Repair continues to work when Brain returns no applicable knowledge;
- existing Brain concepts are evolved compatibly where reasonable;
- no v0.7 knowledge path may bypass security/path/tool controls or acceptance leakage boundaries.

Regression validation SHALL cover the existing suite and the v0.6 supported capability surface affected by Brain integration.

## 24. Acceptance Criteria

v0.7 is PASS only when all of the following are demonstrated with reproducible evidence:

### A — Knowledge Pack
A frozen, identifiable Knowledge Pack exists for Minecraft 1.21.11 + Fabric and its canonical source/environment/integrity metadata can be reproduced.

### B — Multi-Source
The Brain retrieves compatible knowledge equivalent to all three classes: vanilla/mapping, Fabric API, and concept/pattern, using more than one source category.

### C — Version Isolation
A deliberately incompatible knowledge record is presented to retrieval and demonstrably does not reach provider-visible context.

### D — Pre-Code Knowledge
At least one supported Fabric task retrieves and injects relevant compatible knowledge before the first mutation/edit.

### E — Semantic Repair
At least one real compile/API/symbol/runtime-applicable failure follows `failure → knowledge retrieval → injected repair context → repair → authoritative build/runtime PASS`.

### F — Trace
Evidence distinguishes RETRIEVED, SELECTED, INJECTED and the later repair/action plus authoritative outcome. REFERENCED/EVIDENCED semantics must not overclaim model causality.

### G — Brain OFF / ON
A comparable control demonstrates Brain ON injection and Brain OFF absence of external Brain injection.

### H — No Leakage
No answer key, hidden reference solution, Harness internals or incompatible knowledge is injected as valid context.

### I — Minecraft Runtime
At least one supported vertical completes `Brain ON → modification/repair → build → artifact → Minecraft → PASS`.

### J — Regression
The established v0.1–v0.6 regression suite/capabilities remain healthy after v0.7 integration.

No statistical claim that Brain ON generally outperforms Brain OFF is required for v0.7 closure.

## 25. Explicit Deferred Work

Deferred to v0.8+ or later evidence-driven work:

- additional Minecraft versions and full multi-version pack lifecycle;
- semantic embeddings/vector retrieval;
- vector databases;
- Knowledge Graph;
- distributed/cloud knowledge service;
- generalized Internet crawling;
- automatic broad migration corpus;
- Paper/NeoForge/Velocity knowledge;
- rendering/GUI/networking/entities/worldgen knowledge;
- model routing or provider-specific Brain behaviour;
- statistical provider/Brain benchmark claims.

SQLite FTS5 or another concrete text-index implementation is an RFC decision, not a DESIGN requirement.

## 26. Open Questions

**No product-level open question blocks RFC.**

The RFC must still choose implementation details including concrete pack/record schemas, source adapters, index technology, conflict-resolution mechanics, trace persistence representation, and the exact bridge from task/failure signals to knowledge needs. Those are HOW decisions and do not alter the DESIGN contract.

## Design Closure

The DESIGN is closed when 00 Dirección accepts the requirements above as the v0.7 product/architecture contract.

Recommended next phase after acceptance:

`DESIGN → RFC`

No RFC, IMP or production implementation is part of this document.