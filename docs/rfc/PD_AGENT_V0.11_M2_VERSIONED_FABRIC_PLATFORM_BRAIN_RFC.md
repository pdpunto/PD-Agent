# PD Agent v0.11 - M2 Versioned Fabric Platform and Brain RFC

Status: `RFC - READY FOR IMP`

Milestone: `PD Agent v0.11 - M2 Versioned Fabric Platform and Brain`

Baseline: `c27ce733d85af998a873f12c95618dfca6d43819`

DESIGN authority: `docs/design/PD_AGENT_V0.11_M2_VERSIONED_FABRIC_PLATFORM_BRAIN_DESIGN.md`

## 1. Architectural Summary

M2 adds one local, declarative support authority between current workspace
inspection and Product preflight:

`FabricInspector -> observed environment -> FabricSupportRegistry ->`
`FabricPlatformResolution -> Product preflight -> M1 planner/contract ->`
`KnowledgeEnvironment/compatible source -> existing runtime`

The registry, profiles and resolution are data-only. They do not execute
commands, own a scheduler, dispatch providers or replace Product, Brain,
build, runtime, evidence or completion authorities.

The existing repository interfaces are sufficient for this design. Current
`KnowledgeEnvironment` fields are nullable, so modern un-obfuscated profiles
can omit non-applicable mappings without inventing Yarn values. Existing
`FabricInspector`, `ProjectInspector`, `FabricBootstrap`, M1 planner and
Product orchestration boundaries are extended rather than replaced.

## 2. Existing Authorities Reused

- `FabricInspector` and `ProjectInspector`: observed workspace facts.
- `PinnedFabricVersions`: legacy/bootstrap compatibility only after M2.
- `FabricBootstrap`: project creation authority.
- `KnowledgeEnvironment`, `KnowledgeEnvironmentResolver`, `KnowledgeService`,
  frozen packs, `FabricApiKnowledgeSource` and `YarnKnowledgeSource`: Brain
  environment, source and compatibility authorities.
- `CapabilityDefinition`, `CapabilityRegistry` and `CapabilityPlanner`: M1
  data-only capability and composition authorities.
- `FabricTaskContract` and `FabricEnvironmentConstraints`: current task
  contract and environment representation.
- `ProductFabricTaskContractResolver`, `FabricProductExecutionRunner`,
  `ExecutionService` and Product application composition: Product boundary.
- `FabricNormalOrchestrator`, `AgentRuntime`, `GradleBuildRunner`,
  `MinecraftTestSpec`, `TaskProgressLedger`, `ArtifactValidator` and
  `CompletionGate`: existing execution and evidence authorities.
- `ProjectRecord` and Product storage: project identity and product metadata.

M2 must not create a second runtime, planner, Brain, ledger, Gate, database or
currentness system.

## 3. Domain Models

The RFC introduces four minimal data-only concepts in existing Fabric/product
namespaces. Exact module ownership is defined in Section 26.

### 3.1 FabricPlatformProfile

An immutable profile declares one concrete PD Agent platform combination and
the evidence supporting its status.

Required fields:

| Field | Type | Rule |
|---|---|---|
| `schema_version` | positive integer | supported profile schema |
| `platform_id` | validated string | stable explicit identity |
| `minecraft_version` | non-empty string | exact version |
| `loader_version` | non-empty string | exact loader version |
| `fabric_api_version` | string or null | null only when not applicable/known by profile |
| `loom_version` | string or null | null only when not applicable/known by profile |
| `java_version` | non-empty string | exact required Java major/version policy |
| `mapping_family` | enum | `UNOBFUSCATED` or `OBFUSCATED_REMAPPED` |
| `mappings_namespace` | string or null | required only when family requires it |
| `mappings_version` | string or null | required only when family requires it |
| `support_status` | enum | `TARGET`, `SUPPORTED` or `RETIRED` |
| `evidence` | immutable tuple | sufficient evidence metadata |

The profile rejects empty identity/version values, invalid family values,
mapping fields inconsistent with the family, duplicate evidence identifiers
and unsupported schema versions. A modern un-obfuscated profile may have null
mappings namespace/version; null does not mean legacy Yarn.

### 3.2 FabricPlatformResolution

Resolution is an immutable result, distinct from profile declaration. It
contains:

- `status`: `SUPPORTED`, `UNSUPPORTED`, `UNKNOWN` or `CONFLICT`;
- the selected profile when status is `SUPPORTED`;
- normalized observed facts;
- stable evidence references;
- structured conflicts or reason codes.

Resolution never changes a profile and never creates execution state.

### 3.3 FabricProjectTemplate

The minimal immutable template contains:

- `template_id`;
- `schema_version`;
- `template_revision`;
- supported `platform_id` values or an explicit platform-family constraint;
- optional local `seed_identity` for deterministic materialization;
- provenance/evidence.

It contains no commands, processes, provider settings, runtime state,
credentials or filesystem authority.

### 3.4 Evidence Metadata

Profile evidence is declarative metadata, not a ledger or certification
service. Each item identifies an evidence kind, immutable revision/reference,
and whether it is required for the profile status. Evidence kinds cover profile
definition, inspection/resolution, contract wiring, Brain compatibility,
bootstrap/import and offline build where Product support is claimed.

## 4. Platform Identity

`platform_id` is a validated, explicit, stable identifier for one PD Agent
support combination, for example a namespaced identifier for a concrete
Minecraft/loader/API/Loom/Java/mapping profile. It is not derived from a path,
machine, project, run, timestamp, provider or secret.

The profile's canonical identity payload contains the schema version and all
semantic platform/version/mapping fields, plus the declared support-profile
revision. The identity is either the validated explicit registry key or the
deterministic digest of that canonical payload; it must never include paths or
runtime timestamps. Registry construction rejects a key whose canonical
payload does not agree with its declared identity.

Profile identity is not project identity and is not execution identity.

## 5. Support Status and Resolution Status

`support_status` belongs to a profile:

- `TARGET`: planned/declared target with insufficient Product support evidence;
- `SUPPORTED`: evidence-backed and eligible for Product execution;
- `RETIRED`: historically known but not executable.

`FabricPlatformResolution.status` belongs to one current workspace decision:

- `SUPPORTED`: exactly one eligible `SUPPORTED` profile matches all required
  observed facts and evidence gates;
- `UNSUPPORTED`: the workspace is sufficiently identified, but no executable
  supported profile matches;
- `UNKNOWN`: required facts are missing or insufficient to decide;
- `CONFLICT`: authoritative observations or eligible profiles contradict each
  other and no single truth can be selected.

Defaults may fill no missing field for purposes of changing `UNKNOWN` into
`SUPPORTED`.

## 6. FabricSupportRegistry

`FabricSupportRegistry` is a local immutable collection of profiles. Its
ownership is the Fabric domain, with construction from source-controlled
declarative profile data. It has no database, network loader, scheduler,
provider configuration, executable path, process or command field.

The concrete RFC interface is conceptually:

- `get(platform_id) -> FabricPlatformProfile`;
- `list_profiles() -> tuple[FabricPlatformProfile, ...]`;
- `resolve(observed_environment) -> FabricPlatformResolution`.

Construction validates every profile, rejects duplicate `platform_id` values,
rejects invalid profile evidence and freezes profiles in deterministic
platform-id order. Invalid registry data is a configuration failure; it must
not be silently omitted or downgraded.

The registry is not a generic registry framework and is not an execution
authority.

## 7. Evidence and Support Gate

An entry in the registry is not automatically Product-supported. A profile may
be `TARGET` while its definition is visible, but only `SUPPORTED` can resolve
to an executable result.

The minimum evidence gate for `SUPPORTED` requires stable, source-controlled
or persisted references for:

1. profile definition and exact pins;
2. current inspection/resolution;
3. Fabric contract environment wiring;
4. compatible Brain environment/source or frozen-pack behavior;
5. bootstrap or imported-project behavior where claimed;
6. offline build when Product support is declared.

The gate checks presence, identity/revision and required kind, not a new
certification database. Evidence is versioned declarative metadata and test
references. A missing, stale or contradictory item leaves the profile
non-supported.

## 8. Resolution Algorithm

Input is the normalized current observation from `FabricInspector` and its
existing detection signals. The registry does not reparse build files.

Resolution proceeds deterministically:

1. Normalize observed values without supplying legacy defaults.
2. Detect contradictory values in one authority or across authoritative
   inspection signals.
3. If required facts are missing, return `UNKNOWN` unless contradiction was
   already established.
4. Determine mapping family from explicit compatible observation/profile data;
   never infer modern support from a legacy mappings default.
5. Match exact concrete profile fields. Required fields must equal; optional
   fields match when observed and must not contradict when present.
6. Filter profiles to `support_status=SUPPORTED` and passing the evidence gate.
7. If more than one equally eligible profile remains, return `CONFLICT`.
8. If no eligible profile remains but the environment is identified, return
   `UNSUPPORTED`.
9. Otherwise return `SUPPORTED` with the one selected profile and evidence.

No fuzzy version matching, nearest-version selection or arbitrary `26.1.x`
folding is permitted. Each concrete supported profile is registered
individually; a future 26.1 family can contain multiple concrete profiles.

## 9. Conflict Precedence

`CONFLICT` takes precedence over `UNKNOWN` and `UNSUPPORTED` whenever two
authoritative observations disagree, including Minecraft versions, loader/API
compatibility, Loom, Java policy or mapping family/namespace. It also applies
when multiple profiles remain equally eligible for the same concrete facts.

If a value is simply absent and no contradictory value exists, the result is
`UNKNOWN`. If all required facts identify a combination that has no
evidence-backed supported profile, the result is `UNSUPPORTED`.

Existing `FabricInspector` ambiguity/issues signals are reused. The support
resolver consumes those signals rather than duplicating the project parser.

## 10. Mapping Families

Modern 26.1+ profiles use `UNOBFUSCATED`. Mappings namespace/version are null
when not applicable and are never filled with invented Yarn/intermediary
values.

Legacy 1.21.11 uses `OBFUSCATED_REMAPPED`; mappings namespace/version are
required when the legacy profile depends on them. Business behavior branches
on the profile family, not on scattered Minecraft-version conditionals.

The initial concrete targets are 26.2, 26.1.2 and 1.21.11. Loader, Fabric
API, Loom, Java and mapping pins for 26.1/26.2 remain implementation
verification inputs until confirmed by repository/approved evidence. The RFC
does not invent those values.

## 11. Product Preflight Integration

The existing `ExecutionService`/Product runner boundary is extended so the
order is:

`inspect -> resolve platform -> require SUPPORTED -> resolve capabilities ->`
`plan -> expand contract -> create/use prepared contract -> existing execution`

The support check occurs before provider dispatch and before `ExecutionRecord`
persistence, preserving the M1 invalid-preflight invariant. Unsupported,
unknown, conflicting or invalid support data has zero dispatch.

The resolver is invoked again for every execution. Historical Product or
bootstrap metadata cannot skip inspection.

## 12. FabricTaskContract Integration

The generated contract receives the current profile environment through the
existing `FabricEnvironmentConstraints` fields:

- Minecraft;
- Loader;
- Fabric API;
- Loom in existing extra metadata;
- Java;
- mappings namespace/version where applicable;
- mapping family and current `platform_id` as typed/validated extra metadata
  if the existing contract schema cannot yet add dedicated fields.

The contract fingerprint remains authoritative. Profile identity influences it
only through current environment data; it is not a competing identity.
Existing v0.9/M1 contract readers remain compatible. Any schema extension is
additive and must preserve old reads.

## 13. KnowledgeEnvironment Adapter

M2 defines a pure adapter from `FabricPlatformProfile` to the existing
`KnowledgeEnvironment`. It copies applicable version fields and leaves
non-applicable modern mappings as null.

For `UNOBFUSCATED`, no Yarn/intermediary value is invented. For
`OBFUSCATED_REMAPPED`, the legacy mappings namespace/version are copied when
required. The adapter does not select sources, execute Brain work or mutate
profiles.

The current nullable `KnowledgeEnvironment` can represent both families; no
parallel Brain environment is needed. If future evidence shows a required
field cannot be represented, implementation must first propose the smallest
backward-compatible extension rather than apply a legacy default.

## 14. Brain Source and Pack Selection

Composition obtains one existing `KnowledgeService` configured with sources
compatible with the resolved environment. Selection is:

`SUPPORTED profile -> KnowledgeEnvironment -> compatible source/pack selection`

`FrozenKnowledgePackSource`, `FabricApiKnowledgeSource`, `YarnKnowledgeSource`
and other sources retain their own compatibility and identity validation. A
wrong or incompatible pack returns a structured version/compatibility failure;
Support Registry success cannot override it.

No Brain is created per version and no KnowledgeService is duplicated. The
environment and source checks jointly prevent cross-version leakage.

## 15. Project Template and Bootstrap

`FabricProjectTemplate` is declarative source-controlled data. Bootstrap
accepts a selected platform profile and compatible template, validates their
relationship, and uses the existing `FabricBootstrap` to produce a
deterministic workspace.

`PinnedFabricVersions` remains a legacy compatibility adapter for existing
fixtures/tests. It is not consulted as the Product support authority.

Bootstrap manifests may record platform/template provenance and seed identity,
but they contain no executable commands or provider configuration.

## 16. Reinspection and Project Identity

After bootstrap, an unchanged workspace must reinspect and resolve to the same
profile. A changed workspace must be evaluated from current facts.

`ProjectRecord.project_id` remains independent of `platform_id`. M2 does not
add platform identity to the project identity or require a Product storage
schema change. If provenance is needed for display/audit, optional
`created_from_platform_id` and `created_from_template_id` metadata may be
added backward-compatibly, but it cannot authorize execution.

## 17. Imported Projects

Imported projects follow:

`workspace -> FabricInspector/ProjectInspector -> support resolution ->`
`Product preflight`

They do not require a bootstrap manifest, PD Agent seed identity or historical
platform metadata to resolve a supported platform. M5 still owns trust,
isolation and resource controls for imported workspaces.

## 18. Currentness and Provenance

Historical platform provenance is explanatory only:

`historical platform provenance != current platform truth`

Every Product execution reinspects and resolves the workspace. The current
resolution supplies the contract environment and therefore participates in
the existing contract fingerprint. No `PlatformCurrentnessLedger`, version
state machine or competing fingerprint is introduced.

## 19. Structured Errors

The Fabric boundary exposes Product-safe structured errors, while retaining
internal causes for diagnostics. Minimum codes are:

- `INVALID_PLATFORM_PROFILE`;
- `UNSUPPORTED_PLATFORM`;
- `UNKNOWN_PLATFORM`;
- `PLATFORM_CONFLICT`;
- `INSUFFICIENT_PLATFORM_EVIDENCE`;
- `INCOMPATIBLE_KNOWLEDGE_ENVIRONMENT`;
- `UNKNOWN_PROJECT_TEMPLATE`;
- `TEMPLATE_PLATFORM_MISMATCH`;
- `INVALID_PLATFORM_CONTRACT`.

Internal parser/exception details are not exposed directly to Product/UI.
Failures are terminal for preflight, safe to persist only through existing
error/evidence authorities, and never trigger provider or runtime dispatch.

## 20. Persistence

The registry and profiles are source-controlled declarative data. No database,
remote registry or second ledger is introduced.

Resolution is ephemeral preflight data by default. Current profile identity and
environment may be represented in the existing contract/evidence references
when needed for traceability. Project and RunState persistence is unchanged
unless implementation proves a backward-compatible provenance field necessary.

No destructive migration is allowed. Existing v0.9 Product records, M1
contracts and fixtures must remain readable.

## 21. Security

- profiles, templates and registry are data-only;
- no secrets, commands, processes or executable paths are stored there;
- no dynamic code loading or remote registry is permitted;
- planner remains data-only;
- Brain has no execution authority;
- Product preflight remains fail-closed;
- `ToolExecutor` and `SecurePathResolver` remain filesystem authorities;
- imported-project trust/isolation remains M5;
- `GAP-SEC-001` remains open for M5.

## 22. Build Boundary

`GradleBuildRunner` remains the single shared build boundary. There is no
modern/legacy runner fork. Platform differences are represented through
profile, workspace, bootstrap and configuration inputs.

Offline build evidence is required before a profile can be declared Product
`SUPPORTED` when Product build support is part of that profile's claim.

## 23. Harness Boundary

M2 does not generalize the Minecraft Harness, probes or runtime validation.
When an existing runtime validation applies, the current platform environment
and versions are adapted into `MinecraftTestSpec`. The first-compatible
runtime requirement limitation and generalized 1-to-N validation remain M4.

## 24. Backward Compatibility

M2 preserves v0.9 persistence/hydration, M1 planner/contracts, existing
fixtures, legacy 1.21.11 tests, Brain tests and bootstrap tests. Additive
schema changes require a schema version and backward-compatible reads. No
destructive migration or silent reinterpretation of legacy records is allowed.

## 25. Test Strategy

### Unit

- profile type, family and identity invariants;
- registry duplicate rejection, freeze and deterministic ordering;
- supported, unsupported, unknown and conflict resolution;
- modern/legacy mapping family behavior;
- profile-to-`KnowledgeEnvironment` adaptation;
- evidence sufficiency and template/profile compatibility;
- structured Product-safe errors.

### Integration

- unsupported/unknown/conflicting preflight blocks before execution record and
  provider;
- supported workspace produces a current contract;
- wrong Brain pack/source is rejected;
- imported workspace resolves without bootstrap metadata;
- bootstrap followed by reinspection resolves to the same profile;
- manual version modification triggers fresh resolution;
- the same M1 planner/capabilities work across profiles.

### Representative offline vertical

Platform A and Platform B each traverse resolution, M1 BLOCK + BLOCK_ITEM +
RECIPE planning, contract generation and compatible Brain selection. The
1.21.11 legacy baseline remains separately representable. No live provider,
Minecraft or benchmark run is required for the M2 implementation tests.

## 26. Module Ownership

The preferred ownership is:

- `pd_agent.fabric`: profile, registry, resolution and template data models;
- existing project inspection namespace: observation adaptation only;
- `pd_agent.knowledge`/existing Brain namespace: profile-to-environment
  adapter and source selection integration;
- `pd_agent.product`: preflight integration and Product-safe errors;
- existing `pd_agent.bootstrap`: platform/template bootstrap extension.

No `v011` package and no parallel namespace is introduced.

## 27. Acceptance Traceability AC1-AC18

| DESIGN AC | RFC mechanism | Future evidence |
|---|---|---|
| AC1 single authority | immutable `FabricSupportRegistry` | registry construction/ownership tests |
| AC2 deterministic supported resolution | exact matching and evidence gate | supported resolution test |
| AC3 fail-closed preflight | resolution status required before Product persistence/dispatch | Product preflight integration |
| AC4 distinct mapping models | profile family plus nullable modern mappings | modern/legacy profile tests |
| AC5 M1 reuse | same registry/planner/capabilities for every profile | cross-profile planner test |
| AC6 current contract environment | profile adapter to `FabricEnvironmentConstraints` | contract environment assertion |
| AC7 compatible Brain | pure profile-to-`KnowledgeEnvironment` adapter | compatible environment test |
| AC8 wrong pack rejection | source/pack compatibility remains independent | frozen/source mismatch test |
| AC9 platform/template bootstrap | template compatibility validated by existing bootstrap | bootstrap integration test |
| AC10 bootstrap reinspection | current inspection must return selected profile | round-trip inspection test |
| AC11 imported resolution | no manifest prerequisite | imported project test |
| AC12 currentness | every execution reinspects | version mutation regression |
| AC13 shared Gradle | one `GradleBuildRunner` boundary | composition identity test |
| AC14 no duplicate authorities | ownership and dependency review | architecture regression |
| AC15 two-platform offline path | representative A/B vertical | offline integration evidence |
| AC16 legacy representation | concrete 1.21.11 legacy profile model | legacy resolution test |
| AC17 required fail-closed cases | status/error table and integration cases | unsupported/unknown/conflict/pack tests |
| AC18 regression | existing suite remains green | full regression report |

## 28. Risks and Mitigations

- Defaults may accidentally authorize support: support checks must use registry
  status and evidence only.
- Modern and legacy mappings may be conflated: family invariants reject
  incompatible fields and no legacy defaults fill modern nulls.
- Historical metadata may mask edits: execution always reinspects.
- Brain success may be mistaken for platform support: both gates are required.
- M1 may fork by version: planner and capability identity remain shared.
- Imported projects may bypass trust: M5 boundary remains explicit.
- Registry breadth may become M3 catalog scope: M2 profiles cover support, not
  general capabilities.

## 29. Non-Goals

M2 does not implement a new runtime, AgentRuntime, planner, Brain, DAG,
database, distributed registry, cloud version service, package manager,
automatic network resolver, Alpha capability catalog, general asset toolkit,
generalized Harness/probes, generalized runtime validation 1-to-N, exhaustive
version-by-capability certification, automatic mod migration, Paper, NeoForge,
Velocity, Multi-Agent support, full M5 import trust/isolation or M6 held-out
certification.

## 30. Pre-Implementation Verification Requirements

Before implementation, verify without invention:

1. concrete 26.1.2 and 26.2 pins from approved repository/evidence;
2. how current Inspector signals expose conflicts and absent fields;
3. exact compatibility behavior for modern KnowledgeEnvironment values;
4. source-controlled profile/evidence loading location;
5. additive contract metadata/read compatibility;
6. bootstrap manifest compatibility and existing fixture callers;
7. Product error translation and zero-dispatch ordering;
8. offline build evidence for each profile claimed `SUPPORTED`;
9. no profile contains executable paths, commands or secrets;
10. existing full regression remains green after each implementation lot.

If any verification invalidates the model, implementation stops and returns to
Direction rather than silently changing the DESIGN.

## 31. Explicit Deferments

M3 owns broad capability/catalog and asset breadth. Early M4/M4 owns
generalized probes, Harness and runtime validation. M5 owns imported-project
trust/isolation and broader Product security/recovery. M6/Alpha owns held-out
acceptance and exhaustive version-by-capability certification.
