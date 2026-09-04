# PD Agent v0.12 / M3 - Alpha Fabric Capabilities & Assets RFC

Status: `RFC - VERTICAL B DELTA READY FOR IMP`

Milestone: `PD Agent v0.12 / M3 - Alpha Fabric Capabilities & Assets`

Baseline: `f98bdb2c881d29d9200c59f10bbb5b1072e9deff`

DESIGN: `docs/design/PD_AGENT_V0.12_M3_ALPHA_FABRIC_CAPABILITIES_ASSETS_DESIGN.md`

## 1. Status

This RFC specifies how the accepted M3 DESIGN is implemented without changing the established Product/runtime architecture.

Vertical A is the first complete capability slice:

`Block -> associated BlockItem -> minimal assets -> recipe`

Required platforms:

- Fabric 1.21.11;
- Fabric 26.2.

The RFC is intentionally bounded. It defines enough concrete contracts for an executable IMP and repo audit, while leaving generalized validation, generalized Harness behavior and later vertical details to M4 or later M3 deltas.

## 2. DESIGN Reference

The accepted DESIGN verdict is `PD_AGENT_V0_12_M3_DESIGN_READY`.

The RFC preserves these DESIGN authorities:

- M2 `FabricPlatformResolution` owns current supported environment;
- existing `CapabilityRegistry` and `CapabilityPlanner` own deterministic composition;
- `FabricTaskContract` owns task requirements and validation declarations;
- Brain owns knowledge/context only;
- existing `FabricNormalOrchestrator` and `AgentRuntime` own execution flow;
- existing BuildRunner owns Gradle execution;
- existing `ArtifactValidator` owns artifact validity;
- existing runtime/Harness boundary owns Minecraft observations;
- existing `TaskProgressLedger` owns requirement/failure progress;
- existing `CompletionGate` owns completion.

No second authority is introduced.

## 3. Architecture Baseline

The implementation path remains:

`Product request -> FabricPlatformResolution -> CapabilityRegistry/Planner -> FabricTaskContract -> Brain -> FabricNormalOrchestrator -> AgentRuntime -> PRE_BUILD -> Build -> Artifact -> Runtime -> TaskProgressLedger -> CompletionGate`

M3 adds bounded data/contracts and integrations inside this flow only.

The current planner already derives task requirement IDs and validation IDs deterministically from capability instance identity. Runtime R123 normalization already converges runtime correlation back to canonical task requirement IDs. The RFC standardizes this rule for every new Vertical A observation and failure.

## 4. Terminology

### Capability definition ID

Stable registry key such as `fabric.block`.

### Capability instance ID

Existing deterministic SHA-256 `CapabilityInstance.identity` derived from definition ID, schema version, parameters and prerequisite refs.

### Task requirement ID

Canonical completion/failure domain:

`requirement:<derive_capability_output_id(instance, local_requirement_key)>`

Only this domain is legal in `TaskProgressLedger` requirement sets and `FailureFact.requirement_ids`.

### Validation requirement ID

Validation declaration identity:

`validation:<derive_capability_output_id(instance, local_validation_key)>`

It identifies a validation, but it is not a task requirement ID.

### Observation ID

Stable local ID inside one runtime validation spec. It identifies one observation result only. It must not be copied into `FailureFact.requirement_ids`.

### Platform identity

The current M2 `FabricPlatformProfile.platform_id` / platform identity resolved from current workspace facts. It is contract/environment context, not an independent capability execution authority.

### Minimal assets

The bounded Vertical A resource set required for structural packaging and load:

- blockstate;
- block model;
- item model;
- language entry when requested;
- texture reference and, only when chosen, owned physical texture;
- recipe is a separate data resource capability.

## 5. Component Map

| Concern | Existing owner | M3 change |
|---|---|---|
| platform support | `FabricSupportRegistry` / `FabricPlatformResolution` | reuse |
| capability declarations | `fabric.registry` | extend definitions only |
| composition | `CapabilityPlanner` | reuse |
| contract expansion | `fabric.planning` | bounded schema support only |
| Brain need derivation | `PreCodeKnowledgeNeedDeriver` / `FabricBrainOrchestrator` | extend signals/composition |
| mutation | `ToolExecutor` + mutation targets | reuse |
| PRE_BUILD | existing pre-build validator path | extend bounded Vertical A checks |
| build | existing BuildRunner | reuse |
| build failure normalization | `BuildFailureNormalizer` | connect once in productive path |
| repair | existing Semantic Repair / `FailureReconciler` | reuse + build reconciliation call |
| artifact | `ArtifactValidator` | extend required-entry checking |
| runtime | `ProductiveMinecraftFunctionalValidator` + Minecraft contracts/runner | extend bounded observations |
| ledger | `TaskProgressLedger` | reuse |
| completion | `CompletionGate` | reuse unchanged |

## 6. Vertical A Capability Schema

Vertical A uses four explicit capability definitions. Assets are represented as one bounded explicit capability, not a generic asset graph.

### 6.1 `fabric.block`

Canonical parameters:

- `namespace: string identifier`;
- `block_id: string identifier`;
- `display_name: string`, optional;
- `runtime_spec: object`, derived/assembled by resolver/planner integration, not user-authored raw execution data.

Requirements:

- local key `source`;
- local key `block-registration`.

Validations:

- BUILD correlated to `source`;
- RUNTIME participation correlated to `block-registration` through the shared Vertical A runtime validation requirement.

### 6.2 `fabric.block_item`

Canonical parameters:

- `block_instance_id: capability instance identity`;
- `namespace: string identifier`;
- `item_id: string identifier`;
- optional `display_name`.

Prerequisite:

- referenced `fabric.block` instance through `block_instance_id`.

Requirements:

- `item-source`;
- `block-item-association`.

The item identifier may equal the block identifier, but equality is not required and never proves association.

### 6.3 `fabric.block_assets`

This is the M3 bounded asset capability.

Canonical parameters:

- `block_instance_id`;
- `block_item_instance_id`;
- `namespace`;
- `block_id`;
- `item_id`;
- optional `display_name`;
- `texture_strategy: REUSE | DERIVE | GENERATE`;
- `texture_reference: string`, required for REUSE/DERIVE output;
- `texture_path: string`, optional and only legal when a physical owned texture is required;
- `resource_paths: object` containing the exact expected bounded paths.

Prerequisites:

- referenced `fabric.block`;
- referenced `fabric.block_item`.

Requirements:

- `blockstate`;
- `block-model`;
- `item-model`;
- optional `lang` when display name is part of the request;
- `texture-reference`;
- optional `texture-file` only when strategy requires an owned physical texture.

Validation declarations:

- one bounded artifact validation spec correlated to all required asset requirement IDs.

### 6.4 `fabric.recipe`

Canonical parameters:

- `output_instance_id`: BlockItem capability instance identity;
- `namespace`;
- `recipe_id`;
- `recipe_type`: M3 supported recipe form identifier;
- `ingredients`: bounded ordered JSON-safe list;
- `result_item_id`;
- `result_count`, positive integer;
- `resource_path`.

Prerequisite:

- referenced `fabric.block_item`.

Requirements:

- `recipe-resource`.

Validation declarations:

- bounded PRE_BUILD recipe assertions;
- artifact required entry;
- successful Minecraft resource/datapack load is covered by the shared runtime requirement, without RecipeManager introspection.

### 6.5 Platform identity placement

`platform_id` is canonical Vertical A context but is not copied into each capability parameter set. It comes from current `FabricPlatformResolution` and enters `FabricContractContext` / `FabricEnvironmentConstraints.extra` as immutable run input.

This avoids turning capability data into a second support authority while still binding the generated contract to the resolved platform environment.

## 7. Composition / Dependency Model

The candidate set is:

`fabric.block`

`fabric.block_item -> fabric.block`

`fabric.block_assets -> fabric.block + fabric.block_item`

`fabric.recipe -> fabric.block_item`

The existing planner resolves prerequisite edges and topological order. No persistent DAG is stored.

The resolver that maps Product request to candidates must be generic over namespace/IDs/display/recipe/texture strategy. Historical `server_core` values are permitted only as test fixtures.

Composition fails before execution when:

- a referenced capability instance is absent;
- a prerequisite points to the wrong definition;
- namespace/identifier values are invalid;
- recipe output does not match the intended BlockItem;
- asset references point to another logical block/item;
- platform resolution is not `SUPPORTED`.

## 8. Identity Model

The RFC fixes five non-overlapping domains:

1. capability definition IDs: `fabric.*` strings;
2. capability instance IDs: existing deterministic SHA-256 identity;
3. task requirement IDs: `requirement:<sha256>`;
4. validation requirement IDs: `validation:<sha256>`;
5. observation IDs: bounded strings local to runtime spec.

Rules:

- `FailureFact.requirement_ids` contains task requirement IDs only;
- runtime identities contain task requirement IDs before ledger reconciliation;
- `ValidationViolation.requirement` may identify the validation requirement that raised the violation, but adapters must map resulting failure correlation to canonical task requirement IDs;
- observation result IDs never become requirement IDs;
- requirement IDs are generated only through contract expansion, never handwritten downstream;
- the same instance/local key produces the same requirement ID deterministically;
- changing semantic capability parameters creates a new instance identity and therefore new requirement IDs.

This prevents recurrence of the R123 domain mismatch.

## 9. Requirement Expansion

Contract expansion follows:

`CapabilityInstance -> local requirements -> canonical task requirement IDs -> validation declarations -> FabricTaskContract`.

Vertical A produces at minimum these logical obligations:

- block source/registration;
- BlockItem source/association;
- minimal asset resources;
- recipe resource;
- build success/currentness;
- artifact packaging/currentness;
- shared runtime validation.

PRE_BUILD expectations are carried in validation specs/data consumed before build. BUILD remains a normal build validation. ARTIFACT carries `required_entries`. RUNTIME is one required runtime validation containing three observations.

The RFC does not create multiple runtime validation requirements for Vertical A.

## 10. Brain Integration

Brain receives the exact `KnowledgeEnvironment` converted from current M2 platform resolution.

Vertical A pre-code knowledge domains are:

- `block_registration`;
- `block_item`;
- `blockstate_asset`;
- `block_model_asset`;
- `item_model_asset`;
- `texture_reference`;
- `recipe_resource`;
- `vertical_a_composition`.

Each domain must produce version-sensitive `KnowledgeNeed` data with the exact environment.

The resolver/contract supplies capability signals that are semantic and generic, not fixture names.

Brain remains advisory. Missing knowledge does not authorize guessed compatibility.

## 11. `max_needs` Resolution

The existing deriver has a hard maximum of 8 and currently expands each detected capability into several need kinds, which can starve later recipe/resource signals.

M3 does not add a second deriver. Instead it extends the existing `PreCodeKnowledgeNeedDeriver` with a deterministic Vertical A composition mode:

- the maximum remains 8;
- when the contract exposes the Vertical A composed capability set, the deriver emits at most one bounded primary need per required knowledge domain above;
- each need may carry hints for API/PATTERN/CAPABILITY retrieval rather than triplicating every capability into three separate needs;
- stable priority order is: composition, block, BlockItem, blockstate/model assets, item model/texture, recipe, platform-specific API semantics;
- deduplication remains by type/query/environment;
- no later domain may be silently omitted solely because an earlier capability generated redundant API/PATTERN/CAPABILITY triplets.

This is an extension of the existing deriver, not a new Brain path.

## 12. Cross-Version Knowledge Protection

Protection is layered:

1. Product preflight requires M2 `SUPPORTED` resolution;
2. contract environment is built from that current resolution;
3. every Vertical A `KnowledgeNeed.version_sensitive = True`;
4. `KnowledgeService` rejects incompatible sources;
5. frozen packs/sources re-check environment compatibility;
6. cache identity remains environment-sensitive;
7. 26.2 must not request Yarn/remapped knowledge;
8. 1.21.11 must preserve its Yarn/remapped mapping namespace/version.

Wrong environment is fail-closed as `VERSION_MISMATCH` / `NO_COMPATIBLE_KNOWLEDGE` according to existing Brain semantics.

## 13. Mutation / Resource Contract

All mutations use existing `ToolExecutor` and mutation-target confinement.

The contract exposes bounded expected mutation targets for:

- relevant Java source files;
- `src/main/resources/assets/<namespace>/blockstates/<block_id>.json`;
- `src/main/resources/assets/<namespace>/models/block/<block_id>.json`;
- platform-appropriate item model resource path declared by the capability profile/spec;
- optional lang resource;
- optional owned texture path;
- `src/main/resources/data/<namespace>/recipe/<recipe_id>.json` or the exact platform-valid path resolved by the platform-aware contract.

Mutation target values must be relative, normalized and confined. No absolute path, `..`, symlink escape or command data is legal.

The LLM/provider may choose code/resource contents from compatible knowledge, but it cannot expand allowed filesystem scope beyond declared mutation targets.

## 14. Asset Strategy

Vertical A supports three bounded strategies.

### REUSE

Use an existing valid Minecraft/mod texture reference. No new physical PNG is required. PRE_BUILD validates the reference shape/path convention only; server runtime does not prove rendering.

### DERIVE

Derive a deterministic reference/model relation from existing project resources. It may create/update JSON model resources but does not require a new image generator.

### GENERATE

Use only when the task explicitly requires a new owned texture and the existing mutation/tool path can provide the physical resource. M3 does not build a universal asset generation framework. If no approved generation mechanism exists, the task is blocked rather than fabricating a placeholder claim.

For M3 acceptance, REUSE is mandatory and sufficient for a complete Vertical A slice. DERIVE is allowed when deterministic from existing resources. GENERATE is optional and not required to close Vertical A.

Owner split:

- Planner/capability data chooses the declared strategy based on resolved task inputs;
- Brain provides compatible resource semantics;
- existing mutation tools create/update files;
- PRE_BUILD validates bounded static shape/reference/path;
- ArtifactValidator proves required JAR entries;
- server Harness proves successful load only, never visual correctness.

## 15. PRE_BUILD Contract

Vertical A adds a bounded validation spec, conceptually:

```json
{
  "profile": "vertical_a_resources_v1",
  "required_paths": ["..."],
  "json_documents": [
    {"path": "...", "kind": "blockstate"},
    {"path": "...", "kind": "block_model"},
    {"path": "...", "kind": "item_model"},
    {"path": "...", "kind": "recipe"}
  ],
  "namespace": "modid",
  "block_id": "block_name",
  "item_id": "item_name",
  "recipe_id": "recipe_name",
  "texture_strategy": "REUSE",
  "texture_reference": "minecraft:block/stone"
}
```

Checks are closed and profile-specific:

- all required paths exist and are regular confined files;
- no duplicate normalized path;
- each declared JSON file parses to an object;
- blockstate contains a bounded variant/multipart declaration referencing the expected block model domain;
- block model contains a non-empty parent and/or textures object as required by the chosen bounded form;
- item model contains the platform-valid bounded model reference form selected for the resolved platform;
- optional lang file parses as an object and contains the expected translation key when display name is required;
- recipe contains the expected recipe type, bounded ingredients, expected result item and positive result count;
- namespace/path IDs agree with the contract;
- owned physical texture is required only when strategy requires it.

PRE_BUILD produces `ValidationResult` with `PRE_BUILD` stage using existing validation semantics.

Violations use canonical task requirement correlation supplied by the validation declaration. PRE_BUILD does not invent new requirement IDs.

## 16. Build Integration

`GradleBuildRunner` remains unchanged as execution authority.

The productive integration point is immediately after each completed `BuildResult` is recorded by `AgentRuntime` and before repair classification proceeds.

Flow:

`BuildResult PASS -> normal current build identity path`

`BuildResult FAIL -> exactly one BuildFailureNormalizer.normalize(...) -> structured failure handling`

The normalizer receives:

- current source revision;
- current build attempt identity/reference;
- persisted build stdout/stderr evidence refs;
- canonical task requirement IDs correlated to BUILD for the contract;
- timeout fact from the build path.

No second caller may normalize the same build attempt into another active build FailureFact.

## 17. Build Failure Normalization

Existing `BuildFailureNormalizer` remains the only normalizer.

Its categories/codes are reused:

- `BUILD_MISSING_SYMBOL`;
- `BUILD_SIGNATURE_OR_API_MISMATCH` / `BUILD_API_MISMATCH`;
- `BUILD_COMPILATION_ERROR`;
- `BUILD_DEPENDENCY_FAILURE`;
- `BUILD_TIMEOUT`;
- `BUILD_ENVIRONMENT_FAILURE`;
- `BUILD_UNKNOWN_FAILURE`.

Repairable compile/symbol/API failures enter Semantic Repair. Dependency, timeout, environment and unknown blocked categories do not trigger speculative code repair.

The normalized build failure is persisted as bounded evidence and converted once to the existing `ValidationViolation` / `FailureFact` representation.

## 18. Semantic Repair Integration

Repair flow remains the existing one:

`structured current failure -> compatible repair KnowledgeNeed -> Semantic Repair -> mutation -> new source revision -> revalidation`.

For build failures:

- repair Brain environment is exactly current platform environment;
- source/API hints from `NormalizedBuildFailure` may seed repair knowledge;
- repair cannot mark the failure resolved by mutation alone;
- PRE_BUILD reruns after repair mutation where resource/source expectations may have changed;
- then build reruns;
- later artifact/runtime checks rerun if build succeeds.

Ineffective repair remains governed by existing stall/repeated-failure semantics.

## 19. Build Reconciliation

A build FailureFact is resolved only when all are true:

- it is currently ACTIVE;
- the later build is PASS;
- the PASS belongs to a newer/current source revision after the repair;
- it belongs to the same task contract identity;
- the canonical task requirement IDs match the failed build requirement domain;
- current build evidence refs are persisted.

The existing `FailureReconciler` should own this reconciliation, extended with a build-specific method only if no equivalent strict method already exists.

Unrelated failures remain ACTIVE. A successful build does not resolve runtime, artifact, PRE_BUILD or unrelated build failures with non-matching requirement IDs/fingerprint lineage.

## 20. Artifact Contract

`ArtifactValidator.validate(...)` remains the only artifact selection/classification authority.

M3 extends the existing validator input with optional bounded required-entry expectations derived from the current artifact validation requirement, conceptually:

```json
{
  "required_entries": [
    "assets/<ns>/blockstates/<block>.json",
    "assets/<ns>/models/block/<block>.json",
    "assets/<ns>/models/item/<item>.json",
    "data/<ns>/recipe/<recipe>.json"
  ]
}
```

Optional lang/owned texture entries are included when required by the capability.

Rules:

- normalize every entry to forward-slash relative JAR path;
- reject absolute paths, drive prefixes, empty segments and `..`;
- deduplicate after normalization; duplicates with identical normalized value collapse deterministically;
- conflicting declarations for the same logical requirement are invalid contract/spec input;
- read ZIP central-directory entry names once per selected candidate;
- missing required entry changes artifact validation to non-VALID, using an explicit issue/code such as `ARTIFACT_REQUIRED_ENTRY_MISSING`;
- unsafe required entry spec is BLOCKED/INVALID before trusting artifact contents;
- evidence records selected artifact, required entries, present/missing entries and checked count;
- current artifact identity remains tied to producing build/source/contract.

Artifact validation does not parse the resource semantics again; PRE_BUILD owns static resource semantics.

## 21. Runtime Requirement Contract

Vertical A uses one required runtime validation requirement with one spec:

```json
{
  "profile": "vertical_a_runtime_v1",
  "target_mod_id": "<namespace>",
  "platform_id": "<resolved platform id>",
  "observations": [
    {
      "observation_id": "block-registry",
      "observation_type": "REGISTRY_ENTRY_PRESENT",
      "profile": "registry",
      "selector": {"kind": "registry", "registry_kind": "block", "identifier": "<ns>:<block>"},
      "expected": {"present": true},
      "requirement_ids": ["<canonical block registration requirement id>"]
    },
    {
      "observation_id": "item-registry",
      "observation_type": "REGISTRY_ENTRY_PRESENT",
      "profile": "registry",
      "selector": {"kind": "registry", "registry_kind": "item", "identifier": "<ns>:<item>"},
      "expected": {"present": true},
      "requirement_ids": ["<canonical item source requirement id>"]
    },
    {
      "observation_id": "block-item-association",
      "observation_type": "BLOCK_ITEM_ASSOCIATION",
      "profile": "block_item_association",
      "selector": {"kind": "block_item_association", "item_id": "<ns>:<item>", "block_id": "<ns>:<block>"},
      "expected": {"associated": true},
      "requirement_ids": ["<canonical block-item-association requirement id>"]
    }
  ]
}
```

The contract expander binds canonical task requirement IDs into observation metadata/spec after those IDs are known. It never inserts validation IDs as failure requirement IDs.

## 22. Observation Contracts

### `REGISTRY_ENTRY_PRESENT`

Reuse existing observation type/profile twice:

- `registry_kind=block`, identifier = Block ID;
- `registry_kind=item`, identifier = Item ID.

PASS means the requested registry contains the exact identifier at runtime.

FAIL evidence records requested kind/identifier and observed absence.

### Observation result requirements

Every observation result carries:

- observation ID;
- observation type;
- PASS/FAIL/BLOCKED/INVALID;
- expected;
- bounded actual;
- evidence refs.

Observation results do not own task completion.

## 23. `BLOCK_ITEM_ASSOCIATION`

Add one new `MinecraftObservationType.BLOCK_ITEM_ASSOCIATION` and one closed profile.

Selector:

```json
{
  "kind": "block_item_association",
  "item_id": "namespace:item",
  "block_id": "namespace:block"
}
```

Expected:

```json
{"associated": true}
```

Runtime semantics:

1. resolve `item_id` from Item registry;
2. fail if missing;
3. verify runtime item object is a Fabric/vanilla `BlockItem` instance;
4. obtain its associated Block through the real runtime API/object relation;
5. resolve/compare that Block's registry identity with `block_id`;
6. PASS only when association identity equals expected Block identity.

It is explicitly invalid to infer PASS from matching string names or from independent presence of item and block.

Bounded actual data:

```json
{
  "item_present": true,
  "is_block_item": true,
  "actual_block_id": "namespace:block",
  "associated": true
}
```

Failure variants:

- item absent;
- item is not a BlockItem;
- associated Block absent/unidentifiable;
- associated Block ID differs.

All produce persisted observation evidence.

## 24. Multi-Observation Execution

M3 extends the existing runtime plan/runner only enough to execute the closed `vertical_a_runtime_v1` observation list.

Rules:

- accepted observation types for this profile are exactly two `REGISTRY_ENTRY_PRESENT` forms plus `BLOCK_ITEM_ASSOCIATION`;
- IDs must be unique;
- order is deterministic: block registry, item registry, association;
- all run in the same Minecraft launch when the Harness can evaluate them after server-ready/mod-load boundary;
- startup/load failure blocks all observations with shared process evidence;
- runner persists each observation result independently;
- overall runtime PASS requires all required observations PASS and successful process/resource load;
- M3 does not expose arbitrary observation graph dependencies or arbitrary heterogeneous probe registration.

The existing legacy scalar observation fields remain backward compatible and continue to map to the first observation where required by old paths.

## 25. Runtime Failure Correlation

For the shared Vertical A runtime requirement:

1. collect observation results whose status is not PASS;
2. for each failed observation, read its bound canonical task requirement IDs;
3. validate every ID exists in `runtime_validation_requirement.requirement_ids` and begins in the canonical task requirement domain produced by the contract;
4. compute ordered union preserving contract requirement order;
5. create/update runtime FailureFact with exactly that union;
6. do not include IDs for PASS observations;
7. do not include validation IDs or observation IDs.

Startup/infrastructure failure that prevents observation execution correlates to the runtime requirement's full task requirement set only when no finer observation result exists, because all required runtime claims remain unproven.

## 26. Runtime Reconciliation / Currentness

R123 semantics are preserved.

A later runtime PASS may resolve a prior runtime failure only when:

- failure is ACTIVE;
- artifact identity matches current artifact;
- validation revision matches current runtime validation revision;
- contract identity/current source lineage is current;
- requirement IDs match the canonical task requirement domain for the resolved failed observations;
- evidence refs are current;
- the specific previously failed observations now PASS.

If only one observation is repaired, only failures correlated to that observation's requirement IDs are eligible for resolution. Unrelated failures remain ACTIVE.

Any source mutation invalidating current artifact/runtime forces rebuild/artifact/runtime refresh through existing currentness rules.

## 27. Harness 1.21.11

Reuse the existing Harness/runner architecture and legacy fixture semantics.

Required profile values remain:

- Minecraft `1.21.11`;
- Loader `0.19.3`;
- Fabric API `0.141.6+1.21.11`;
- Loom `1.13.3`;
- Java `21`;
- mapping family `OBFUSCATED_REMAPPED`;
- namespace `yarn`;
- mappings `1.21.11+build.6`.

M3 changes only:

- Harness support for `BLOCK_ITEM_ASSOCIATION`;
- closed Vertical A multi-observation execution;
- any minimal fixture code needed to report the new observation.

No legacy version defaults may leak into the 26.2 path.

## 28. Harness 26.2

26.2 gets one concrete M3 runtime profile, not a universal profile framework.

Canonical values come from M2 `fabric-minecraft-26.2`:

- Minecraft `26.2`;
- Loader `0.19.3`;
- Fabric API `0.158.0+26.2`;
- Loom `1.17-SNAPSHOT` or the exact materialized compatible build pinned by the M2-supported profile/evidence;
- Java `25`;
- mapping family `UNOBFUSCATED`;
- no Yarn namespace/version.

Implementation shape:

- preserve `MinecraftTestRunner` and `MinecraftTestSpec` as the runner/spec boundary;
- select one of exactly two known M3 Harness runtime roots/configurations by resolved `platform_id`;
- 26.2 fixture/config uses Java 25 and unobfuscated source/build semantics;
- dependency materialization uses current project runtime dependencies and Fabric API 26.2, not legacy hardcodes;
- target JAR and runtime mod JAR confinement/current SHA checks remain unchanged;
- reuse server-ready/process/evidence/result handling;
- provide the same closed registry and BlockItem-association observation implementation for 26.2 APIs;
- reject Yarn configuration for 26.2;
- reject platform/profile mismatch before launch.

The selection can be a bounded `if platform_id in {legacy, modern}`/mapping at the composition boundary. It must not become a generic plug-in Harness profile registry in M3.

## 29. Ledger / Evidence Contract

`TaskProgressLedger` remains unchanged in authority.

For Vertical A it must receive:

- satisfied canonical requirement IDs only from authoritative validation/mutation evidence;
- PRE_BUILD evidence refs per correlated resource requirement;
- build evidence refs for current BUILD requirements;
- artifact evidence refs for current artifact requirements;
- runtime observation evidence refs for block/item/association requirements;
- active/resolved FailureFacts using canonical task requirement IDs;
- Brain knowledge correlation remains advisory evidence and does not satisfy completion by itself.

Evidence refs are persisted relative/safe references according to existing storage contracts.

## 30. CompletionGate Integration

`CompletionGate` is not modified.

Vertical A reaches COMPLETE only when existing gate rules observe:

- current source revision;
- current successful build;
- current VALID artifact;
- all required PRE_BUILD/BUILD/ARTIFACT/RUNTIME validations current and PASS;
- all required task requirements satisfied with evidence;
- zero blocking ACTIVE failures;
- no stale or invalid blocking validation refs.

Brain retrieval, mutation occurrence or build PASS alone is insufficient.

## 31. Error Model

| Error | Owner/result | Evidence | Repairability |
|---|---|---|---|
| unsupported platform | Product/M2 preflight `BLOCKED` | platform resolution | terminal until project/platform changes |
| unresolved/conflicting platform | Product/M2 preflight `BLOCKED` | resolution diagnostics | terminal until facts change |
| wrong Brain environment | Brain `VERSION_MISMATCH`/no compatible knowledge | source/pack compatibility | blocking for version-sensitive required knowledge |
| missing Block knowledge | Brain degraded/blocked per need policy | retrieval attempts | retry/source fix, not guessed |
| missing BlockItem knowledge | Brain degraded/blocked | retrieval attempts | retry/source fix |
| missing asset knowledge | Brain degraded/blocked | retrieval attempts | retry/source fix |
| missing recipe knowledge | Brain degraded/blocked | retrieval attempts | retry/source fix |
| invalid composition | Planner failure | planning result | terminal input/spec correction |
| invalid identifier | Planner/model failure | normalized parameters | terminal input correction |
| duplicate resource declaration | PRE_BUILD/spec invalid | normalized path set | repairable if mutation/spec data is agent-controlled |
| missing resource | PRE_BUILD `REPAIRABLE_FAIL` | missing path | repairable |
| malformed JSON | PRE_BUILD `REPAIRABLE_FAIL` | path + parse diagnostic | repairable |
| invalid recipe | PRE_BUILD `REPAIRABLE_FAIL` | bounded assertion diagnostic | repairable |
| compile failure | Build normalizer | build logs + normalized fact | repairable for compile/symbol/API categories |
| missing symbol/API mismatch | Build normalizer | symbol/signature hints + logs | repairable |
| dependency/timeout/environment build failure | Build normalizer `BLOCKED` | build evidence | operational, not semantic code repair |
| artifact required entry missing | Artifact validation non-VALID | missing entry list | repairable through resource/build mutation path |
| unsafe artifact entry spec | artifact contract `BLOCKED` | invalid spec | terminal until contract corrected |
| Minecraft startup failure | runtime `BLOCKED/FAIL/CRASH` | process/log/crash evidence | semantic or infrastructure classification determines next action |
| block registry failure | runtime FAIL | observation evidence | repairable |
| item registry failure | runtime FAIL | observation evidence | repairable |
| BlockItem association failure | runtime FAIL | association actual | repairable |
| stale source/build/artifact/runtime | currentness/gate blocks | identity mismatch | requires rebuild/revalidation |
| repair ineffective | existing repair stall semantics | repeated fingerprint/evidence | blocking after configured threshold |
| unrelated ACTIVE failure | ledger/gate | failure evidence | remains active; never auto-resolved |

## 32. Security / Path Constraints

- all resource/mutation paths are project-relative and normalized;
- JAR required entries are archive-relative forward-slash paths;
- reject absolute paths, Windows drives, `..`, empty/root entries and symlink escape;
- no capability parameter may contain shell/exec/script authority;
- `ToolExecutor` remains the only mutation execution boundary;
- Brain content never widens allowed paths;
- Harness target/runtime JARs remain confined to authorized roots and verified identities;
- observations return bounded JSON-safe actual data;
- no secrets, provider credentials or machine-private paths enter capability/observation evidence.

## 33. Determinism / Idempotency

Determinism rules:

- candidate normalization and capability instance identities are stable;
- prerequisite ordering remains planner deterministic topological order;
- requirement/validation IDs derive from instance/local keys only;
- resource path derivation from namespace/IDs is deterministic;
- required JAR entry list sorts/deduplicates canonically;
- observation order is fixed;
- failure requirement union preserves contract order;
- repeated PRE_BUILD/artifact/runtime validation over unchanged current input yields equivalent semantic result;
- repair mutation is not itself considered success;
- rerunning the same valid resource write should be idempotent where existing tools support replace/update semantics.

## 34. Vertical B-F Reuse

Vertical A establishes reusable contracts, not complete implementations:

- B Standalone Items/Recipes reuses capability identity, recipe, resource, PRE_BUILD, artifact and runtime-correlation patterns;
- C Tools/Weapons/Armor reuses item/resource/build/artifact/currentness and will need a delta DESIGN/RFC for gameplay-specific semantics/probes;
- D Basic mobs/entities reuses composition/identity/Brain/currentness but requires a later delta for entity runtime validation;
- E Basic behaviors reuses failure/repair/currentness but requires behavior-specific validation design;
- F Assets reuses `fabric.block_assets` principles and may later generalize them only through an approved delta.

No B-F detailed implementation is authorized by this RFC.

## 35. M4 Boundary

Explicitly deferred:

- arbitrary N runtime requirements;
- generalized validation graph;
- arbitrary heterogeneous probes;
- generalized RecipeManager introspection;
- generalized behavior/entity probes;
- generalized asset dependency graph;
- client rendering validation;
- Java AST framework;
- exhaustive JSON schema framework;
- universal resource auto-repair;
- universal Harness profile framework;
- full version-by-capability certification.

M3 may expose narrow data extension points, but may not implement these systems early.

## 36. Migration / Backward Compatibility

Existing M1 capability definitions remain valid unless explicitly superseded through registry schema-compatible extension.

Migration rules:

- existing `fabric.block`, `fabric.block_item`, `fabric.recipe` IDs remain stable;
- parameter additions required for M3 should be optional/defaulted only when legacy behavior can remain semantically valid; otherwise Product Vertical A resolver must emit the new required values while old tests continue using old definitions until deliberately migrated;
- new `fabric.block_assets` is additive;
- legacy scalar Minecraft observation fields remain accepted;
- existing 1.21.11 Harness use outside Vertical A remains unchanged;
- existing Product project records and M2 platform profiles require no schema migration;
- CompletionGate/ledger schemas are unchanged.

If repo audit shows an existing field cannot be extended without breaking persisted contract decoding, IMP must include an explicit schema-version migration lot rather than silent reinterpretation.

## 37. Testing Strategy

No live execution is required for RFC creation. Implementation acceptance later requires layered evidence.

### Unit

- capability parameter validation;
- explicit asset capability prerequisites;
- deterministic IDs;
- requirement/validation/observation domain separation;
- Vertical A need derivation capped at 8 with recipe/assets retained;
- cross-version source rejection;
- PRE_BUILD valid/missing/malformed/unsafe cases;
- artifact required-entry normalization/missing/unsafe cases;
- BuildFailureNormalizer exactly-once integration helpers;
- build reconciliation strictness;
- BLOCK_ITEM_ASSOCIATION result parsing/correlation;
- runtime failed-observation union algorithm.

### Integration offline

For both 1.21.11 and 26.2:

`platform resolution -> candidates -> plan -> FabricTaskContract -> exact KnowledgeEnvironment -> PRE_BUILD fixture -> build fixture/evidence -> artifact required entries`.

Negative cases include wrong platform/Brain, malformed resources, stale artifact/currentness and unrelated failure isolation.

### Runtime/live later in M3

For each supported platform:

- real Minecraft startup;
- target mod load;
- block registry PASS;
- item registry PASS;
- BlockItem association PASS;
- recipe/resource load without startup/datapack error;
- current artifact/runtime identities;
- negative association failure and successful repair/revalidation path as required by IMP.

26.2 runtime evidence is mandatory before Vertical A is M3-complete.

## 38. Risks

1. Existing capability schemas may require careful additive migration instead of in-place required-field changes.
2. Item model/resource conventions may differ materially between 1.21.11 and 26.2; the platform-aware PRE_BUILD profile must encode only verified bounded differences.
3. Harness 26.2 may reveal Loom/Fabric launch differences not visible in M2 offline build evidence.
4. Build failure normalization can duplicate FailureFacts if integrated at more than one layer; ownership is fixed to one AgentRuntime post-BuildResult point.
5. Runtime observation correlation can regress R123 if validation IDs leak into ledger requirement IDs.
6. REUSE texture strategy avoids a new image-generation framework but cannot prove visual correctness; this is intentional M3 scope.
7. Required JAR-entry checks can accidentally inspect wrong paths if Gradle resource relocation differs; implementation tests must use actual produced JAR layout.
8. Resource repair may become tempting to generalize; M3 must keep repairs provider/tool-driven under existing mutation contracts.

## 39. Open Questions

No architectural blocker remains before IMP.

The following are implementation-resolution questions for Codex audit/IMP lots, not open architecture decisions:

- exact existing PRE_BUILD class/function best suited for the `vertical_a_resources_v1` profile;
- exact existing `FailureReconciler` extension point for strict build reconciliation;
- exact 26.2 Harness fixture directory/layout that minimizes duplication;
- verified 26.2 item-model resource shape/path required by the actual pinned platform;
- whether ArtifactValidator accepts validation spec directly or through a thin adapter in AgentRuntime/orchestration.

If repo audit proves any of these require a new authority rather than an extension, implementation must stop and return to 01/00 for RFC correction.

## 40. RFC Acceptance Criteria

The RFC is accepted when all are true:

1. Vertical A uses the existing capability registry/planner and four explicit capability definitions including bounded `fabric.block_assets`.
2. No Server Core/mod-specific identity is embedded in capability semantics.
3. Platform identity comes only from current M2 resolution.
4. Capability, task requirement, validation and observation ID domains are explicit and non-overlapping.
5. `FailureFact.requirement_ids` contains canonical task requirement IDs only.
6. Requirement expansion to PRE_BUILD/BUILD/ARTIFACT/RUNTIME is deterministic.
7. Brain has a concrete eight-need-bounded Vertical A derivation without recipe/assets starvation.
8. Brain compatibility remains exact-environment and fail-closed across 1.21.11/26.2.
9. Mutations remain confined to existing ToolExecutor/mutation-target authority.
10. Minimal assets use bounded REUSE/DERIVE/GENERATE semantics; REUSE is sufficient for M3 acceptance.
11. PRE_BUILD has a closed Vertical A resource schema rather than a generic graph/schema framework.
12. Existing BuildRunner remains the only build runner.
13. Existing BuildFailureNormalizer is integrated exactly once after failed productive BuildResult.
14. Existing Semantic Repair owns repair and cannot resolve failure by mutation alone.
15. Build PASS reconciles only matching current build failures and leaves unrelated failures ACTIVE.
16. Existing ArtifactValidator remains authority and checks normalized required JAR entries.
17. Vertical A has exactly one runtime validation requirement with the three required observations.
18. `REGISTRY_ENTRY_PRESENT` is reused for block/item.
19. `BLOCK_ITEM_ASSOCIATION` proves real runtime BlockItem-to-Block identity.
20. Failed-observation correlation uses only failed observations' canonical task requirement IDs.
21. R123 artifact/revision/requirement/evidence currentness rules remain intact.
22. 1.21.11 preserves Java 21/Yarn/remapped runtime profile.
23. 26.2 uses Java 25/unobfuscated/no-Yarn bounded Harness support.
24. No universal Harness profile framework is created.
25. TaskProgressLedger and CompletionGate schemas/authority remain unchanged.
26. Error ownership/repairability is explicit.
27. Paths/JAR entries/observations are bounded and safe.
28. Deterministic identities/order/deduplication are specified.
29. Vertical B-F reuse is defined without prematurely specifying their implementation.
30. M4 boundary is explicit.
31. No important architecture decision remains for IMP other than repo-specific extension placement confirmed by pre-implementation audit.

Final RFC state when these criteria are accepted:

`PD_AGENT_V0_12_M3_RFC_READY`

## 41. Vertical B RFC Delta - Standalone Items and Recipes

This section is the approved technical delta for the Vertical B DESIGN. It
extends the existing M3 boundaries without introducing a second planner,
runtime, validator, Brain or persistence authority.

### 41.1 Capability-instance reference model

The authoritative identity of a capability instance remains the existing
`CapabilityInstance.identity`: the SHA-256 of its definition ID, schema
version, normalized parameters and prerequisite instance references. It is the
only identity used for dependency edges, requirement derivation and persisted
traceability. `display_name` is presentation data and is never identity.

There are two representations with a strict phase boundary.

**Declaration reference (pre-resolution).** Product requests and candidates use
a task-local bounded declaration key, for example `item_a`, `item_b` or
`recipe_r`. Its minimum logical shape is:

```json
{"kind":"DECLARATION","key":"item_a","capability_id":"fabric.item","role":"ingredient","count":1}
```

The key is unique within the task declaration set, is not a display name, is
not an input-list index and is not an instance identity. It is safe bounded
data and may be serialized through existing candidate/plan boundaries. A
declaration reference can therefore express Item A, Item B, Recipe output B
and Recipe ingredient A before any hash exists.

**Resolved capability-instance reference (post-resolution).** Only the Planner
may replace a declaration reference after creating normalized instances. Its
minimum shape is:

```json
{"kind":"CAPABILITY_INSTANCE","capability_id":"fabric.item","instance_id":"<authoritative-instance-sha>","role":"ingredient","count":1}
```

Vanilla references use the separate resolved shape
`{"kind":"VANILLA_REGISTRY","registry":"item","identifier":"minecraft:iron_ingot","count":1}`.
The canonical serialized forms use normalized JSON, sorted mapping keys and
stable list order. No display-name-derived identity, absolute path,
executable value or arbitrary provider data is legal.

The Product resolver creates declaration keys. The Planner creates
`CapabilityInstance` values, verifies declaration-key uniqueness, resolves
each key to exactly one compatible instance or vanilla entry, and emits only
resolved references before contract expansion/provider/mutation. After this
phase, the contract and persisted plan use `instance_id`; declaration keys may
remain only as non-authoritative provenance/debug metadata.

Reference failures are deterministic planning failures:

- `UNRESOLVED_CAPABILITY_REFERENCE`: target does not exist;
- `AMBIGUOUS_CAPABILITY_REFERENCE`: more than one target matches;
- `INCOMPATIBLE_CAPABILITY_REFERENCE`: target exists but has the wrong
  capability kind or role;
- `INVALID_REFERENCE`: malformed or unsafe reference data.

These failures occur before Brain/provider execution and before mutation.
Neither Brain nor the provider may resolve or repair an ambiguous reference by
guessing.

Declaration/reference-specific failures are:

- `DUPLICATE_DECLARATION_KEY`: two declarations use one task-local key;
- `MISSING_DECLARATION_KEY`: a reference has no valid key or target
  declaration;
- `AMBIGUOUS_CAPABILITY_REFERENCE`: a key maps to more than one instance;
- `INCOMPATIBLE_CAPABILITY_REFERENCE`: the target exists but has the wrong
  capability or role.

The Planner owns these failures and they are never converted into provider
repair requests. Resolved references are the persistence/contract boundary;
declaration keys are not authoritative after resolution.

### 41.2 Multi-instance planning

The current planner already permits distinct instances of the same definition
because `CapabilityInstance.identity` includes normalized parameters, and it
deduplicates only identical identities. Vertical B preserves that behavior and
adds explicit reference binding where the current prerequisite declaration is
insufficient.

The bounded planning phases are:

1. validate and normalize all candidates and their task-local declaration keys;
2. reject duplicate/missing declaration keys;
3. create one instance identity per distinct semantic declaration;
4. resolve each declaration reference to exactly one instance or vanilla entry;
5. replace declaration references with resolved references;
6. add dependent-to-prerequisite edges to the existing `PlanningResult`;
7. reject duplicates/conflicts/cycles;
8. emit the existing deterministic topological order and contract traces.

Canonical ordering is independent of input order: normalized capability data,
definition ID and authoritative instance ID determine stable ordering, while
dependency edges are sorted canonically. Declaration-local reference keys are
lookup aids only and never replace instance identity.

This supports one Item, N Items, Item plus recipe, N recipes and cross-item
recipes without a persistent DAG or generic graph framework.

### 41.3 Duplicate and conflict semantics

The Planner/PRE_BUILD boundary rejects, fail-closed:

- distinct declarations claiming the same `namespace:item_id` registry
  identity;
- distinct declarations claiming the same Java source identity;
- distinct declarations claiming the same normalized resource path;
- distinct recipes claiming the same namespace/recipe ID or resource path;
- conflicting output declarations for one recipe;
- duplicate capability identities when their declarations are not semantically
  idempotent;
- ambiguous or incompatible references.

Equivalent duplicate candidates may collapse only when canonical semantic
identity and all owned outputs are identical. There is no last-write-wins
behavior. Planner owns capability/reference conflicts; PRE_BUILD owns concrete
path/resource conflicts; existing ledger/runtime authorities own later
evidence conflicts.

### 41.4 `fabric.item`

`fabric.item` is a standalone capability and has no Block or BlockItem
prerequisite.

Logical parameters:

- project `namespace`;
- independent `item_id`;
- optional `display_name`;
- bounded basic Item settings/properties only;
- optional source path declaration;
- no prerequisite on `fabric.item_assets`.

Its requirements are registration source, registry identity and required
asset/resource obligations. Its validation requirements cover PRE_BUILD,
artifact required entries and one runtime registry observation per Item.
Mutation expectations cover only the declared confined Java source and
resource paths. Platform/API details come from the resolved M2 profile and
compatible Brain context; tools, weapons, armor, advanced food and complex
components are invalid Vertical B semantics.

### 41.5 `fabric.item_assets`

`fabric.item_assets` depends on one specific `fabric.item` instance and owns
the Item's minimum resource set:

- language entry, when requested;
- item model;
- `REUSE`, `DERIVE` or optional `GENERATE` texture/reference strategy;
- exact project-relative resource paths;
- artifact required entries for those resources.

The Item capability owns registration/source identity. The asset capability
owns resource mutation and resource validation, preventing duplicated
ownership. `REUSE` is sufficient for the bounded M3 acceptance; no image
pipeline or client rendering proof is introduced.

### 41.6 Generalized `fabric.recipe`

The internal recipe model has one recipe identity composed from namespace,
recipe ID and normalized recipe declaration. It contains:

- explicit output capability-instance reference;
- ordered bounded ingredient references;
- positive bounded result count and ingredient quantities;
- recipe type and resource path;
- recipe-resource requirement;
- PRE_BUILD and artifact validations;
- Brain needs for recipe/data semantics;
- platform context from `FabricPlatformResolution`.

Each ingredient is one of:

```json
{"kind":"VANILLA_REGISTRY","registry":"item","identifier":"minecraft:iron_ingot","count":1}
```

or:

```json
{"kind":"CAPABILITY_INSTANCE","capability_id":"fabric.item","instance_id":"<item-instance-id>","role":"ingredient","count":1}
```

The recipe output is likewise a typed `CAPABILITY_INSTANCE` reference. A
recipe no longer requires `fabric.block_item`; Vertical A compatibility is
handled at the boundary below.

### 41.7 Vertical A recipe compatibility

Strategy B is selected: accept the existing Vertical A input shape only at the
Product resolver boundary and normalize it immediately to the single internal
typed-reference model. A legacy Vertical A output reference to a BlockItem
becomes a typed capability-instance output reference. Existing capability IDs,
persisted contracts and old observation fields remain decodable; no second
recipe engine is introduced.

The compatibility boundary must preserve existing Vertical A fingerprints and
tests where the semantic declaration is unchanged. Any unavoidable persisted
schema change requires an explicit schema-version migration in IMP; silent
reinterpretation is prohibited.

### 41.8 Planner and productive resolver ownership

`CapabilityRegistry` owns definitions only. `CapabilityCandidate` carries
bounded untrusted declaration data. `CapabilityInstance` owns normalized
semantic identity. `CapabilityPlanner` owns validation, instance creation,
reference resolution, dependency edges, duplicate/conflict rejection, cycle
detection and deterministic ordering. `PlanningResult` carries the immutable
plan/failure only.

The productive path is:

`Product request -> candidate derivation -> instance creation -> reference resolution -> planning -> FabricTaskContract -> Brain/context -> ToolExecutor mutation -> PRE_BUILD -> BuildRunner -> ArtifactValidator -> Minecraft -> TaskProgressLedger -> CompletionGate`

Only the productive resolver may map user intent to candidates. It must derive
namespace from the inspected project metadata, preserve all required Item and
recipe parameters through contract expansion and reject unsupported or
ambiguous tasks before provider invocation.

### 41.9 PRE_BUILD profile

Vertical B uses a separate bounded `vertical_b_resources_v1` profile because
the existing `vertical_a_resources_v1` profile contains block/blockstate
assumptions. Vertical A continues using its existing profile unchanged.

The Vertical B profile validates, before build:

- Java registration expectation and namespace/item identity;
- confined source/resource paths;
- lang object and requested translation key;
- item model structure and texture/reference strategy;
- recipe JSON structure, output reference and ingredient references;
- positive bounded quantities;
- duplicate/conflicting registry/resource/recipe identities.

Representative fail-closed codes are `VERTICAL_B_ITEM_INVALID`,
`VERTICAL_B_RESOURCE_INVALID`, `VERTICAL_B_RECIPE_INVALID`,
`VERTICAL_B_REFERENCE_INVALID` and `VERTICAL_B_IDENTITY_CONFLICT`.
Malformed resource content may enter the existing repair path; unresolved
references and identity conflicts are preflight failures unless the request
itself is changed.

### 41.10 Artifact strategy

The existing `ArtifactValidator` remains the sole validator. Its current
`required_entries` sequence is already cardinality-neutral and supports N
Item models, language/resource entries, optional textures and N recipe JSONs
after capability instances aggregate them deterministically. The capability/
contract layer must produce a canonical sorted list; the validator normalizes
path separators and rejects duplicate/unsafe entries before checking the
current JAR.

Compiled classes and metadata may be included as required entries when the
existing contract exposes them. No second artifact schema or validator is
required; semantic Java/resource validation remains PRE_BUILD responsibility.

### 41.11 Runtime strategy and known gap

Runtime uses the existing `MinecraftTestSpec`, `ObservationRequest`, runner,
Harness and `ProductiveMinecraftFunctionalValidator`. One bounded Vertical B
runtime validation requirement contains N ordered
`REGISTRY_ENTRY_PRESENT(item)` observations, one for each standalone Item.
This is the minimum extension of the existing one-requirement/many-observation
boundary; no arbitrary runtime graph is introduced.

Recipe acceptance remains:

`PRE_BUILD PASS + required JAR entry + successful resource/datapack load`.

The current repository has recipe observation contracts and a `RECIPE_MATCH`
profile, but that profile is not the approved generic Vertical B acceptance,
and current Productive Vertical A evidence does not prove arbitrary recipe
resource loading independently. IMP must therefore identify the exact
existing runner/Harness load evidence or add the smallest bounded load-result
evidence needed. It must not claim RecipeManager matching or invent a generic
probe.

Runtime results remain bound to the current artifact, source revision,
validation revision and canonical task requirement IDs. `CompletionGate` stays
the sole completion authority.

### 41.12 Brain and version strategy

Keep `max_needs = 8`. Extend the existing composition mode rather than adding
a new Brain. Priority must preserve coverage for:

1. standalone Item registration/settings;
2. Item assets/model/lang/texture reference;
3. recipe resource/schema;
4. vanilla ingredient semantics;
5. capability-reference output/ingredients;
6. composition/reference constraints;
7. resolved platform API semantics;
8. repair-specific knowledge when a structured failure exists.

Needs remain `KnowledgeNeed` values with exact `KnowledgeEnvironment`,
`version_sensitive=True`, and compatible source selection. Brain supplies
context only and cannot create references, plans or mutations.

Capability-generic semantics are identity/reference rules, logical contract
shape, validation invariants and artifact/runtime obligations. Platform-specific
semantics are Java/API registration, mappings, resource conventions and
source-selection details for 1.21.11 versus 26.2. The sole platform authorities
remain `FabricSupportRegistry` and `FabricPlatformResolution`; 26.2 must not
receive Yarn/remapped knowledge and 26.1.2 remains excluded.

### 41.13 Failure, repair and security ownership

Preflight unresolved/ambiguous/incompatible references and duplicate productive
identities are non-repairable contract failures and do not invoke the provider.
PRE_BUILD malformed Item/asset/recipe resources may be repairable through the
existing Semantic Repair flow. Build failures use the existing
`BuildFailureNormalizer`; runtime failures use existing `FailureFact`,
`FailureReconciler`, currentness and observation correlation. Mutation never
resolves a failure without later authoritative revalidation.

All namespace, item ID, recipe ID and resource components pass existing bounded
identifier/path validation before path construction. `SecurePathResolver` and
`ToolExecutor` remain the path/mutation authorities. Absolute paths, traversal,
separator injection, symlink escape, shell data and request-controlled
arbitrary filesystem paths fail closed.

### 41.14 Technical acceptance matrix

| Requirement | Test layer | Evidence/pass condition | Failure behavior |
| --- | --- | --- | --- |
| Standalone Item | unit/offline | valid `fabric.item` plan and contract | planner fail-closed |
| Multiple Items | offline integration | N independent identities and entries | conflict blocks |
| Item assets | PRE_BUILD/artifact | lang/model/texture entries current | repairable resource failure |
| Vanilla recipe | offline/build | typed vanilla ingredients and recipe entry | invalid schema blocks |
| Standalone output | offline/PRE_BUILD | output resolves to Item instance | incompatible reference blocks |
| Cross-item A -> B | offline/completion | ingredient A and output B resolve exactly | unresolved/ambiguous blocks |
| Duplicate/conflict | unit/PRE_BUILD | same productive identity rejected | no last-write-wins |
| Current artifact | build/artifact | VALID/current with all entries | stale/missing blocks |
| Item runtime 1.21.11 | Harness | every item registry observation PASS | runtime failure reconciles |
| Item runtime 26.2 | Harness | every item registry observation PASS | profile mismatch blocks |
| Recipe resource load | Harness | successful bounded load evidence | runtime/load failure blocks |
| Brain version awareness | unit/integration | compatible environment and needs | mismatch blocks/degrades safely |
| CompletionGate | integration | COMPLETE only with all current evidence | incomplete remains non-success |
| Vertical A regression | full regression | prior contracts/tests remain PASS | implementation blocked |

### 41.15 No overbuild and IMP checklist

This RFC does not introduce generic AST validation, a generic recipe engine, a
persistent dependency graph, new orchestrator/runtime/validation framework,
new Brain, full asset pipeline, Vertical C semantics or multi-agent execution.

Before implementation, IMP must verify the real repository boundaries for:

- additive `CapabilityInstance`/planner reference support and deterministic
  ordering;
- `FabricTaskContract` compatibility and persisted decoding;
- productive resolver assumptions and metadata-derived namespace;
- separate PRE_BUILD profile composition;
- required-entry aggregation/cardinality and actual JAR layout;
- bounded N-observation runtime behavior;
- concrete recipe/datapack load evidence in the current Harness;
- Item registration APIs on both supported platforms;
- Vertical A recipe regression and legacy normalization;
- `max_needs=8` behavior without starvation.

No architectural decision remains open for IMP. These are repository-specific
extension placement and verification points, not permission to expand scope.
