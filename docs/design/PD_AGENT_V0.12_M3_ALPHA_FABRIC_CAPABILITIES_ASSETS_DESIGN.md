# PD Agent v0.12 / M3 - Alpha Fabric Capabilities & Assets

Status: `DESIGN - READY FOR RFC`

Milestone: `PD Agent v0.12 / M3 - Alpha Fabric Capabilities & Assets`

Baseline: `5f8aa46022c41482987faff6c9ac60b777a607df`

## 1. Status

This DESIGN defines what M3 must achieve and the product/runtime boundaries that
must remain stable while the Alpha Fabric capability surface grows.

M3 starts with one complete vertical slice, **Vertical A**, and uses it as the
reference pattern for later M3 verticals. It does not define their detailed
technical implementation in advance.

The first complete slice is:

`Block -> associated BlockItem -> minimal assets -> recipe`

The supported platform set for this DESIGN is exactly:

- Fabric 1.21.11;
- Fabric 26.2.

Fabric 26.1.2 remains `TARGET / not certified` and is not an M3 acceptance
platform.

## 2. Context

M2 closed with `PD_AGENT_V0.11_M2_CLOSED_PASS`. The existing Product path is:

`Product request -> CapabilityRegistry/Planner -> FabricTaskContract -> Brain -> existing FabricNormalOrchestrator -> existing AgentRuntime -> Build/Artifact/Runtime -> TaskProgressLedger -> CompletionGate`

M2 established `FabricSupportRegistry` and `FabricPlatformResolution` as the
authority for current Fabric environment support. M3 must consume that authority
rather than reintroduce defaults or capability-specific platform selection.

The accepted reality audits establish that blocks, items, recipes, behaviors
and assets already exist partially, but no Minecraft Alpha capability is yet
complete end to end. Tools, weapons, armor and basic entities do not yet exist
as Alpha capabilities.

The accepted Brain, Build/Debug and Harness boundary audits require M3 to extend
existing components only where Vertical A exposes a concrete gap.

## 3. Problem

M1 proved deterministic capability composition and contract generation. M2
proved version-aware platform and Brain selection. The remaining M3 problem is
to turn those foundations into complete user-facing Fabric capabilities whose
source mutations, resources, build, artifact contents, runtime behavior,
failures, repair and completion are all evidence-backed.

The current partial block/item/recipe/assets support is insufficient because a
capability is not complete merely when source code exists or Gradle builds. M3
needs a reusable definition of capability completeness that reaches
`CompletionGate` with current evidence.

Vertical A is the first place where that definition is made concrete.

## 4. Goals

M3 must:

1. make Vertical A a complete, parameterized, composable Fabric capability;
2. support the same logical Vertical A behavior on Fabric 1.21.11 and 26.2;
3. reuse the M1 capability registry/planner and M2 platform resolution;
4. reuse the existing Brain and extend only its knowledge coverage/composition;
5. allow Java and resource mutations through existing mutation mechanisms;
6. validate required resources before build;
7. build with the existing BuildRunner;
8. prove required resources exist in the produced JAR;
9. prove the block, item and BlockItem association at real Minecraft runtime;
10. preserve source/build/artifact/runtime currentness through failure and repair;
11. leave `TaskProgressLedger` and `CompletionGate` as the only progress and
    completion authorities;
12. establish a pattern that later M3 verticals can reuse without creating
    parallel runtimes, planners, ledgers or validation frameworks.

## 5. Non-goals

M3 does not include:

- a generalized validation architecture;
- a generalized Minecraft Harness;
- arbitrary N runtime validation requirements;
- an arbitrary heterogeneous probe graph;
- generalized RecipeManager introspection;
- generic behavior probes;
- generic entity/worldgen validation;
- client-side rendering correctness;
- generic Java AST validation;
- exhaustive JSON schema infrastructure;
- a generic asset dependency graph;
- universal resource auto-repair;
- universal Fabric version support;
- automatic mod migration;
- Paper, NeoForge or Velocity;
- Multi-Agent execution;
- Alpha release certification.

These remain M4/M5/M6 or post-Alpha work according to the Roadmap.

## 6. Existing Foundations Reused

M3 reuses and does not replace:

- `FabricSupportRegistry`;
- `FabricPlatformResolution`;
- `FabricTaskContract`;
- `CapabilityDefinition` and `CapabilityInstance`;
- `CapabilityRegistry`;
- `CapabilityPlanner`;
- `ToolExecutor` and existing mutation-target controls;
- Brain `KnowledgeEnvironment`, `KnowledgeNeed`, `KnowledgeService` and
  `FabricBrainOrchestrator`;
- existing selector/context injection pipeline;
- existing Semantic Repair;
- `BuildRunner` / `GradleBuildRunner`;
- existing build/artifact/source currentness identities;
- `ArtifactValidator` as the artifact-validation authority;
- existing runtime observation contracts;
- current Minecraft Harness boundary;
- `TaskProgressLedger`;
- `CompletionGate`.

M3 may extend these boundaries where this DESIGN explicitly requires more
coverage, but may not create competing authorities.

## 7. M3 Capability Definition

An M3 capability is **complete** only when all of the following are true for a
supported platform:

- its capability inputs are parameterized rather than tied to a historical mod;
- its dependencies can be composed deterministically by the existing planner;
- the resulting `FabricTaskContract` carries the required PRE_BUILD, BUILD,
  ARTIFACT and RUNTIME obligations;
- Brain can supply compatible, provenance-backed knowledge for the capability
  without cross-version leakage;
- required source/resource mutations can be performed through existing safe
  mutation mechanisms;
- PRE_BUILD proves the minimum static workspace expectations;
- the existing build path succeeds or produces structured repairable evidence;
- the current artifact is valid and contains its required entries;
- required runtime observations pass against the current artifact;
- failures are correctly correlated, repaired and reconciled when repair is
  possible;
- `CompletionGate` returns authoritative completion with no blocking active
  failures.

A build-only or source-only implementation is therefore not an M3-complete
capability.

## 8. Vertical A Scope

Vertical A consists of one logical composed feature:

1. one Fabric Block;
2. one associated BlockItem that represents that Block;
3. the minimum resource/assets needed for that feature to be structurally
   complete;
4. one recipe producing the item/block representation.

The slice is parameterized by capability data such as namespace, identifiers,
display/resource naming and recipe inputs. `server_core`, `examplemod` or any
other historical fixture may be used only as test data, never as the capability
model.

Vertical A must work on both supported M2 profiles:

- `fabric-minecraft-1.21.11`;
- `fabric-minecraft-26.2`.

## 9. Vertical A Behavior

Given a supported Fabric project and a request that resolves to Vertical A, PD
Agent must be able to produce a current project state in which:

- the requested Block is registered under the requested namespace/identifier;
- an Item registry entry exists for its associated BlockItem;
- the Item is actually a BlockItem associated with the expected Block;
- the minimum required blockstate/model/item-model resources exist and parse;
- resource references are coherent enough for build, packaging and Minecraft
  resource loading;
- a valid recipe resource exists for the requested output;
- Gradle builds successfully;
- the resulting JAR is valid/current and contains all required capability
  resources;
- Minecraft starts successfully with the current artifact;
- block registry, item registry and BlockItem association observations pass;
- required resource/datapack loading does not prevent successful runtime load;
- no blocking active failure remains;
- `CompletionGate` returns complete.

The observable claim is functional/runtime capability completion, not visual
render correctness.

## 10. Composition Model

Vertical A is conceptually a composition of dependency-linked capability
instances, not a hardcoded resolver branch:

`Block`
`  -> associated BlockItem`
`  -> minimal asset/resource obligations`
`  -> recipe producing the associated item`
`  -> validation expectations`

The existing planner remains responsible for deterministic dependency
resolution. The composition may be represented through existing capability
definitions plus the minimum additional M3 definitions/declarations required by
the RFC, but it must not introduce a second planner or persistent DAG.

The composition must preserve stable references between instances so that:

- BlockItem refers to the intended Block;
- assets refer to the intended block/item identifiers;
- the recipe refers to the intended output;
- validation requirements can be traced to the capability instances that
  require them.

The exact serialized field shapes are RFC work.

## 11. Planner Responsibilities

The Planner owns deterministic composition only. It must:

- resolve the Block capability;
- resolve the BlockItem dependency on that Block;
- include the minimal assets/resource obligations;
- include the recipe obligation;
- preserve parameterized namespace/IDs;
- emit deterministic requirements and validation expectations;
- produce PRE_BUILD, BUILD, ARTIFACT and RUNTIME obligations in the resulting
  `FabricTaskContract`;
- preserve capability/requirement traceability.

For M3, one runtime validation requirement may contain the required multiple
observations. This intentionally avoids opening the generalized 1-to-N runtime
validation architecture reserved for M4.

The Planner must not:

- execute mutations;
- query Minecraft directly;
- own repair;
- own Brain retrieval;
- infer platform support independently from M2 resolution;
- decide completion.

## 12. Brain Responsibilities

Brain supplies knowledge/context only.

For Vertical A, Brain must provide compatible knowledge for:

- Block registration and relevant platform APIs;
- BlockItem creation/association;
- blockstate resources;
- block model resources;
- item model resources;
- texture/resource references and conventional paths;
- recipe schema/resource semantics;
- composition relationships between those concerns;
- failure repair when a current structured failure requires compatible
  knowledge.

Brain must use the exact `KnowledgeEnvironment` derived from the current M2
platform resolution. Knowledge provenance must remain compatible with that
environment. Legacy 1.21.11 knowledge must not leak into 26.2, and 26.2
knowledge must not be treated as compatible with the remapped legacy profile
without evidence.

The pre-code composition must not silently drop recipe/resource knowledge due
to a need-count limit. M3 therefore requires enough bounded composition
coverage to represent the complete Vertical A need set.

Brain does not produce mutation plans and does not gain execution authority.

## 13. Fabric Mutation Responsibilities

Fabric mutation remains inside the existing safe mutation/tool boundary.
Vertical A must allow the agent to create or update, as needed:

- Java registration of the Block;
- Java registration of the associated BlockItem;
- blockstate JSON;
- block model JSON;
- item model JSON;
- language resource when the capability requires a user-facing name;
- required texture asset or valid texture/reference declaration;
- recipe JSON.

Mutation targets must remain confined and attributable to the current
capability/task. M3 does not introduce a capability-specific filesystem or
parallel mutation engine.

Version-specific Java/API syntax is knowledge/platform-sensitive behavior, not
a new mutation authority.

## 14. Asset Responsibilities

M3 defines a **minimal asset contract**, not a generic asset graph.

For Vertical A, the asset responsibility is satisfied when the capability has
the minimum resource set needed to package and load coherently:

- blockstate definition;
- block model definition;
- item model definition;
- texture resource or explicit valid texture reference as required by that
  model;
- language entry when applicable;
- correct namespace/path relationships.

Asset handling must preserve references between the Block, BlockItem and their
resource identifiers. It must also make required JAR entries explicit so the
artifact boundary can prove packaging.

M3 does not claim that the model renders correctly in a client, that every
possible asset relation is resolved, or that a generic dependency graph exists.

## 15. PRE_BUILD Requirements

PRE_BUILD is the minimum fail-fast static boundary before Gradle.

For Vertical A it must prove, at minimum:

- all contract-required resource paths exist;
- required JSON resources parse;
- the minimum expected object/field shape exists for blockstate, block model,
  item model and recipe;
- namespace/identifier/path expectations are internally coherent at the
  bounded Vertical A level;
- required recipe output/input declaration is structurally present;
- required asset/resource files expected in the final JAR are known;
- obviously missing required Vertical A resources block the build path.

PRE_BUILD is not a generic JSON schema framework, asset graph validator or Java
AST validator.

PRE_BUILD must execute again after a repair mutation that could affect its
expectations. A stale PRE_BUILD PASS cannot authorize later completion.

## 16. Build/Debug Requirements

The existing BuildRunner remains the only build runner.

M3 requires productive build failures to enter the existing structured
Build/Debug and Semantic Repair path. In particular:

- build failures must be normalized into structured evidence;
- normalized build failures must be correlated to the relevant current
  failure/requirements;
- Semantic Repair may use exact-platform Brain knowledge;
- repair mutation must be followed by PRE_BUILD as applicable;
- then rebuild;
- then artifact/runtime revalidation as required;
- authoritative later PASS evidence must reconcile the prior failure through
  the existing strict failure/currentness model.

M3 does not create a second repair engine or state machine.

## 17. Artifact Requirements

`ArtifactValidator` remains the artifact authority and must be extended only as
needed to prove the Vertical A packaging contract.

A Vertical A artifact PASS requires:

- a valid artifact produced from the current successful build;
- artifact identity bound to the current source/build/contract;
- all contract-required Vertical A JAR entries present;
- required blockstate/model/item-model/lang/recipe/owned texture entries
  present when applicable;
- no use of a stale artifact produced before the latest relevant mutation.

Artifact validation proves packaging/currentness. It does not prove client
rendering or runtime semantic behavior.

## 18. Runtime Validation Requirements

Vertical A runtime validation must use real Minecraft and current artifact
identity.

The minimum runtime observations are:

1. `REGISTRY_ENTRY_PRESENT` for the Block identifier;
2. `REGISTRY_ENTRY_PRESENT` for the Item identifier;
3. `BLOCK_ITEM_ASSOCIATION` for `item_id -> block_id`.

`BLOCK_ITEM_ASSOCIATION` must prove that the item exists, is a BlockItem and is
associated with the expected Block identity. Merely observing two independent
registry entries is insufficient.

The Vertical A runtime contract also requires successful Minecraft startup and
successful resource/datapack loading sufficient to load the mod and its recipe
resources. M3 does not require generic RecipeManager introspection.

For M3 these observations may be grouped under one runtime validation
requirement. A failed observation produces failure correlation only for the
requirements represented by that failed observation; unrelated requirements
must not be marked failed.

## 19. Fabric 1.21.11 Behavior

Fabric 1.21.11 is an existing supported M2 platform and has an existing runtime
Harness path that M3 reuses.

Vertical A on 1.21.11 must:

- resolve through the M2 `SUPPORTED` profile;
- use the exact remapped/Yarn-compatible `KnowledgeEnvironment`;
- use existing 1.21.11 build/runtime infrastructure;
- apply the same logical Vertical A capability/requirement model;
- perform the three required runtime observations;
- preserve currentness and completion semantics identical to other supported
  platforms.

Platform-specific Java/API/resource details may differ, but the product claim
and evidence obligations do not.

## 20. Fabric 26.2 Behavior

Fabric 26.2 is an M2 `SUPPORTED` platform but does not currently have the
required live Harness runtime path for Vertical A.

M3 must therefore add a concrete 26.2 Harness extension sufficient to execute
Vertical A runtime validation. The extension is intentionally bounded to the
M3 observations and startup/resource-load needs; it must not generalize the
Harness architecture.

Vertical A on 26.2 must:

- resolve through the M2 `SUPPORTED` 26.2 profile;
- use the exact unobfuscated 26.2 `KnowledgeEnvironment`;
- avoid Yarn/remapped legacy assumptions;
- build using the existing version-agnostic BuildRunner;
- run the current 26.2 artifact under the bounded M3 Harness extension;
- perform Block registry, Item registry and BlockItem association observations;
- preserve the same currentness/failure/completion semantics as 1.21.11.

26.2 support from M2 does not itself certify Vertical A. M3 must produce its
own capability evidence on 26.2.

## 21. Evidence and Currentness Model

M3 reuses the existing source/build/artifact/runtime currentness model.

Evidence used for Vertical A completion must be tied to:

- the current task contract identity;
- the current source revision;
- the current successful build identity;
- the current artifact identity/SHA;
- the current validation revision;
- stable requirement IDs for the current contract;
- persisted evidence references.

A later mutation invalidates earlier build/artifact/runtime evidence when the
existing currentness rules say it is stale. M3 may not bypass this by retaining
historical PASS results.

Requirement IDs must remain stable for the life of the current contract and
must be correlated consistently between validation observations, failure facts,
ledger entries and completion evaluation. The exact generation algorithm is
RFC scope.

## 22. Failure, Repair and Revalidation Behavior

A Vertical A failure/blocker includes, as applicable:

- unsupported/unknown/conflicting platform resolution;
- missing or incompatible Brain knowledge when the contract cannot safely
  proceed without it;
- missing/invalid required resources at PRE_BUILD;
- build failure;
- invalid or incomplete artifact packaging;
- Minecraft startup/resource-load failure;
- missing Block registry entry;
- missing Item registry entry;
- wrong or missing BlockItem association;
- stale evidence;
- unresolved current active failure.

Repairable failures follow the existing loop:

`failure -> structured evidence -> compatible Semantic Repair knowledge -> mutation -> PRE_BUILD/rebuild -> artifact revalidation -> runtime revalidation -> failure reconciliation`

A repair mutation alone never proves repair. Reconciliation requires later
current authoritative PASS evidence.

Failure correlation must be narrow. A runtime failure for one observation may
activate only the requirement IDs represented by that observation. Unrelated
requirements stay untouched.

## 23. Completion Semantics

`CompletionGate` remains the only completion authority.

Vertical A can complete only when all required contract obligations are
satisfied and current. At minimum this requires:

- current source revision;
- current successful build;
- current valid artifact;
- required JAR entries present;
- current runtime validation against that artifact;
- Block registry observation PASS;
- Item registry observation PASS;
- BlockItem association PASS;
- required resource/datapack load successful within the runtime attempt;
- all required validations satisfied;
- no blocking `ACTIVE` failure;
- `CompletionGate` returns authoritative complete.

Product success or delivery may only follow that existing completion result.

## 24. Vertical A Acceptance Criteria

Vertical A DESIGN acceptance requires the later RFC/IMP/implementation to prove
all of the following.

### Deterministic/offline acceptance

- a generic parameterized request can compose Block + BlockItem + assets +
  recipe without a Server Core special case;
- dependency ordering and references are deterministic;
- both supported platform profiles generate coherent current
  `FabricTaskContract` environments;
- Brain need derivation retains Block, BlockItem, assets and recipe knowledge;
- wrong-version knowledge is rejected;
- required Vertical A PRE_BUILD expectations are enforced;
- required JAR entries are enforced by artifact validation;
- structured build-failure normalization and reconciliation are covered;
- failure correlation isolates unrelated requirements;
- mutation invalidates stale build/artifact/runtime evidence;
- CompletionGate remains fail-closed when any required evidence is absent or
  stale.

### Runtime acceptance - Fabric 1.21.11

A real Minecraft validation must demonstrate with current evidence:

- target mod loads;
- block `REGISTRY_ENTRY_PRESENT` PASS;
- item `REGISTRY_ENTRY_PRESENT` PASS;
- `BLOCK_ITEM_ASSOCIATION` PASS;
- required resources/recipe do not prevent successful load;
- evidence is bound to the current artifact/validation revision;
- final completion can become authoritative when all other requirements pass.

### Runtime acceptance - Fabric 26.2

The same logical evidence is mandatory on real Minecraft 26.2 through the
bounded M3 Harness extension. An offline build-only 26.2 result is insufficient
for Vertical A closure.

### Repair acceptance

At least one representative repair path must prove:

`failure -> semantic repair -> mutation -> rebuild -> revalidation -> RESOLVED`

without losing source/build/artifact/runtime currentness and without falsely
resolving unrelated failures.

## 25. Reusable Pattern for Vertical B-F

Vertical A establishes this reusable M3 pattern:

`parameterized capability instances`
`-> deterministic dependency composition`
`-> contract requirements/validation expectations`
`-> exact-platform Brain knowledge`
`-> safe Java/resource mutation`
`-> bounded PRE_BUILD checks`
`-> existing build/debug/repair`
`-> required artifact entries`
`-> bounded runtime evidence where needed`
`-> currentness/reconciliation`
`-> existing CompletionGate`

Vertical B-F should reuse that pattern rather than add parallel execution
paths.

Planned M3 order remains:

- Vertical A: Block + BlockItem + assets + recipe;
- Vertical B: standalone Items + Recipes;
- Vertical C: Tools + Weapons + Armor;
- Vertical D: basic mobs/entities;
- Vertical E: basic behaviors;
- Vertical F/transversal: assets contract/capabilities.

This DESIGN intentionally does not define detailed technical schemas or probes
for C/D/E. Each later vertical may require a scoped DESIGN/RFC/IMP delta after a
reality audit demonstrates its concrete gaps.

Vertical F may consolidate reusable asset concepts learned from A-E, but may
not retroactively introduce a generic M4 asset graph into M3.

## 26. Explicit M4 Boundary

M3 stops at capability-specific, bounded validation necessary to prove the
Alpha capability slices selected for M3.

M4 begins when PD Agent needs generalized validation/repair/runtime
infrastructure such as:

- arbitrary 1-to-N runtime validation requirements;
- arbitrary heterogeneous observation/probe graphs;
- generalized recipe introspection;
- generalized asset-reference graphs;
- generalized behavior/entity/world validation;
- generalized Java semantic/AST validation;
- generalized resource repair;
- capability-independent runtime probe orchestration.

Vertical A must not be used as a reason to implement those abstractions early.

## 27. Risks

### R1 - Capability-specific hardcoding

The largest product risk is recreating the historical Server Core path under a
new name. Mitigation: all Vertical A identifiers/namespaces/relationships are
capability parameters and test fixtures are never support authorities.

### R2 - Cross-version knowledge leakage

M3 adds more version-sensitive resource/API knowledge. Mitigation: exact M2
platform resolution plus existing `KnowledgeEnvironment`/source compatibility
checks remain mandatory.

### R3 - Asset overgeneralization

A generic asset graph would expand scope into M4. Mitigation: validate only the
minimal Vertical A resource contract and required JAR entries.

### R4 - Runtime overgeneralization

Adding multiple observations could accidentally become a general probe graph.
Mitigation: M3 supports only the explicit Block registry, Item registry and
BlockItem association set for this slice.

### R5 - False repair completion

Mutation or rebuild success could be mistaken for repaired behavior. Mitigation:
existing currentness plus authoritative revalidation and failure reconciliation
remain required.

### R6 - 26.2 runtime gap

M2 certified platform/build/Brain support but not the M3 live Harness path.
Mitigation: Vertical A closure explicitly requires the bounded 26.2 runtime
extension and real runtime evidence.

### R7 - Requirement identity mismatch

The M2 R123 defect showed that mismatched validation/task requirement domains
can prevent correct reconciliation. Mitigation: M3 requires one stable
requirement identity domain across observations, failures, ledger and
CompletionGate.

## 28. Open Questions

No open question currently blocks DESIGN acceptance.

RFC must still specify, without changing this DESIGN:

- exact capability declaration shapes for minimal assets and recipe composition;
- exact deterministic requirement/validation ID derivation;
- exact bounded PRE_BUILD minimum field checks;
- exact required JAR-entry representation;
- exact `BLOCK_ITEM_ASSOCIATION` request/result schema;
- exact 26.2 Harness adaptation point;
- exact Brain need-budget/composition adjustment;
- exact productive BuildFailureNormalizer/reconciliation wiring.

If RFC investigation shows that any of those require a generalized M4
architecture rather than a bounded M3 extension, that part must stop and return
to architecture instead of silently expanding scope.

## 29. DESIGN Acceptance Criteria

This DESIGN is acceptable only if it is understood and preserved that:

1. Vertical A is the first complete M3 slice and is generic/parameterized;
2. Fabric 1.21.11 and Fabric 26.2 are both mandatory Vertical A platforms;
3. Fabric 26.1.2 remains outside certified M3 acceptance;
4. M1 CapabilityRegistry/Planner remain the only capability planning path;
5. M2 Platform Resolution remains the environment/support authority;
6. Brain supplies knowledge only and uses exact compatible environment;
7. mutation uses existing safe tool/mutation mechanisms;
8. PRE_BUILD validates only the bounded Vertical A resource contract;
9. the existing BuildRunner remains authoritative;
10. productive build failures become structured repair evidence;
11. ArtifactValidator proves required current JAR entries;
12. runtime proves Block registry, Item registry and BlockItem association;
13. 26.2 receives only the bounded Harness extension needed by M3;
14. recipe/assets require static/artifact evidence plus successful Minecraft
    resource/datapack load, not generalized runtime introspection;
15. failures are correlated only to affected requirements;
16. repair requires rebuild/revalidation/reconciliation;
17. stale evidence cannot satisfy completion;
18. TaskProgressLedger and CompletionGate remain the sole progress/completion
    authorities;
19. Vertical A establishes a reusable pattern for B-F without predesigning
    their detailed implementations;
20. M4 generalized validation/runtime architecture is not pulled into M3.

When these constraints are carried into RFC, the DESIGN state is:

`PD_AGENT_V0_12_M3_DESIGN_READY`
