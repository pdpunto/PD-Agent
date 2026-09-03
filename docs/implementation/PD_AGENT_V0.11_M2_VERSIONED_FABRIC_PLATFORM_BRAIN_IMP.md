# PD Agent v0.11 - M2 Versioned Fabric Platform and Brain IMP

Status: `IMP - READY FOR PRE-IMPLEMENTATION`

Milestone: `PD Agent v0.11 - M2 Versioned Fabric Platform and Brain`

Baseline: `aa9afaf190ae0d073e620be616f579f8c36f62a4`

## 1. Authorities

- `docs/design/PD_AGENT_V0.11_M2_VERSIONED_FABRIC_PLATFORM_BRAIN_DESIGN.md`
- `docs/rfc/PD_AGENT_V0.11_M2_VERSIONED_FABRIC_PLATFORM_BRAIN_RFC.md`
- `docs/roadmap/PD_AGENT_ROADMAP_TO_ALPHA.md`
- `docs/validation/PD_AGENT_V0.10_M1_CLOSURE.md`

The implementation order is Roadmap -> DESIGN -> RFC -> this IMP -> Lot A
verification -> implementation lots -> M2 validation and closure. This IMP
does not authorize implementation by itself.

## 2. Principles and Preconditions

M2 extends existing authorities and introduces only the minimal platform
profile, support-resolution and project-template boundaries. It does not add
a runtime, Brain, planner, ledger, completion authority or generic registry
framework.

Before every lot:

- confirm the approved commit and branch;
- require a tracked-clean tree;
- preserve the pre-existing untracked `scripts/benchmark/diagnostics/` only;
- inspect the actual target files before editing;
- run the lot's focal tests, `compileall` and `git diff --check`;
- review scope before commit and push.

No API live, Minecraft live, benchmark live or economic-ledger write is part
of this IMP.

## 3. Lot A - Pre-Implementation Platform Verification

Lot A is a non-production gate and must pass before Lot B changes code.

Verify approved concrete pins and evidence for Minecraft 26.2, Minecraft
26.1.2 and the legacy 1.21.11 baseline: Minecraft, Loader, Fabric API, Loom,
Java, mapping family and applicable mappings. Do not declare 26.1.2 or 26.2
`SUPPORTED` merely because they are targets. Confirm the effective legacy pins
as observed in the existing repository and approved evidence.

Audit the exact `FabricInspector` outputs for Minecraft, Loader, Fabric API,
Loom, mappings, Java when available, ambiguity, issues and conflicts. Record
what it cannot observe. Decide whether a minimal Inspector extension is
needed or whether missing fields remain profile requirements.

Verify that nullable `KnowledgeEnvironment` represents modern
`UNOBFUSCATED` profiles without invented Yarn values. Verify compatibility
behavior of `FabricApiKnowledgeSource`, `YarnKnowledgeSource` and existing
frozen packs for modern and legacy environments.

Select the minimal local declarative loading form for profiles and templates,
preferably source-controlled Python declarations or data in existing
namespaces. No network or remote registry is allowed.

Deliverable: `PREIMPLEMENTATION_VERIFICATION_READY` or a fail-closed blocker.
No production profile becomes `SUPPORTED` in Lot A alone.

## 4. Dependency Graph

The default dependency order is:

`A -> B -> C -> D -> E/F -> G -> H -> I -> J`

E and F may proceed independently after D only if their contracts are stable.
No lot may parallelize changes that consume an unresolved profile or contract
schema.

## 5. Lot B - Platform Domain Foundation

### Objective

Implement the immutable, data-only platform domain after Lot A passes.

### New

Likely under `src/pd_agent/fabric/`:

- `FabricPlatformProfile`;
- `FabricPlatformResolution`;
- support and resolution enums;
- minimal evidence metadata;
- canonical identity and invariants;
- `FabricSupportRegistry`.

Exact file placement is confirmed by Lot A; no `v011` package or generic
registry framework is permitted.

### Behavior

Validate schema, mapping-family fields, stable identity, immutable contents,
duplicate profile rejection, evidence sufficiency and deterministic ordering.
Distinguish profile `TARGET`/`SUPPORTED`/`RETIRED` from resolution
`SUPPORTED`/`UNSUPPORTED`/`UNKNOWN`/`CONFLICT`.

### Tests

Valid/invalid profiles, schema and family invariants, identity stability,
duplicate/freeze/order behavior, evidence gate, exact supported match,
unsupported, unknown, conflict, multiple eligible profiles, modern profiles
without fake Yarn mappings and legacy mappings requirements.

### Commit

`feat: add Fabric platform support registry`

## 6. Lot C - Observation to Support Resolution

### Objective

Connect current Inspector facts to the registry without duplicating parsers:

`current workspace -> normalized observation -> FabricPlatformResolution`

### Modify

Existing project/Fabric inspection and support integration modules only where
Lot A proves necessary. `FabricInspector` remains the observation authority;
the registry remains the support authority.

### Tests

Exact supported observation, missing facts to `UNKNOWN`, contradictory facts
to `CONFLICT`, fully known unsupported combination to `UNSUPPORTED`, preserved
Inspector ambiguity and proof that defaults never turn `UNKNOWN` into
`SUPPORTED`.

### Commit

`feat: resolve current Fabric platform`

## 7. Lot D - Contract and Knowledge Adapter

### Objective

Adapt the current resolved profile to existing contract and Brain models.

### Modify

Existing contract/Product/Brain namespaces only as required. Reuse
`FabricEnvironmentConstraints` and nullable `KnowledgeEnvironment`.

Modern profiles use `UNOBFUSCATED` and do not receive invented mappings.
Legacy profiles use `OBFUSCATED_REMAPPED` and preserve real mapping fields.
Any contract extension is additive, fingerprint-aware and backward-compatible.

### Tests

Modern and legacy contract environments, platform-sensitive fingerprints,
old contract deserialization, both Brain environments and wrong
mapping-family rejection.

### Commit

`feat: adapt Fabric platform to contracts and Brain`

## 8. Lot E - Brain Platform Selection

### Objective

Connect one resolved platform to one existing `KnowledgeService` and
compatible sources/packs.

### Modify

Existing Brain/application composition only. Do not create a Brain or
KnowledgeService per version.

### Tests

Compatible pack acceptance, incompatible pack rejection, legacy/modern
cross-version rejection, leakage prevention and unchanged existing Brain
behavior. No live API is required.

### Commit

`feat: select Brain knowledge by platform`

## 9. Lot F - Project Template and Bootstrap

### Objective

Implement the minimal declarative `FabricProjectTemplate` and adapt the
existing `FabricBootstrap`:

`platform profile + template -> deterministic workspace`

### Modify/New

Existing bootstrap namespace plus the confirmed template module from Lot A.
`PinnedFabricVersions` becomes a compatibility adapter and is retained while
fixtures/tests require it.

Templates contain no commands, processes, provider configuration, runtime
state, filesystem authority or secrets.

### Tests

Template invariants and platform compatibility, mismatch rejection,
deterministic bootstrap, manifest/provenance, bootstrap reinspection to the
same profile, and legacy bootstrap compatibility.

### Commit

`feat: version Fabric bootstrap templates`

## 10. Lot G - Product Version-Aware Preflight

### Objective

Integrate the support authority into Product in this order:

`inspect -> resolve support -> require SUPPORTED -> interpret/plan ->`
`expand contract -> existing Product execution`

### Modify

Existing `pd_agent.product` resolver, Product application composition and
`ExecutionService` preflight boundary only as necessary.

### Invariants

Unsupported, unknown, conflicting or insufficient support fails before
`ExecutionRecord`, provider use or dispatch. Historical metadata and defaults
cannot bypass current resolution. M1 CapabilityRegistry/CapabilityPlanner,
FabricProductExecutionRunner and FabricNormalOrchestrator remain shared.

Product-safe errors include:

- `INVALID_PLATFORM_PROFILE`;
- `UNSUPPORTED_PLATFORM`;
- `UNKNOWN_PLATFORM`;
- `PLATFORM_CONFLICT`;
- `INSUFFICIENT_PLATFORM_EVIDENCE`;
- `INCOMPATIBLE_KNOWLEDGE_ENVIRONMENT`;
- `UNKNOWN_PROJECT_TEMPLATE`;
- `TEMPLATE_PLATFORM_MISMATCH`;
- `INVALID_PLATFORM_CONTRACT`.

### Tests

Unsupported/unknown/conflict before execution, zero provider calls and
dispatch, supported path through the M1 planner, current platform in the
contract and historical metadata unable to authorize stale support.

### Commit

`feat: enforce Product platform preflight`

## 11. Lot H - Imported Projects and Currentness

### Objective

Validate imported projects through:

`workspace -> inspection -> support resolution -> Product preflight`

No bootstrap manifest, seed identity or historical platform metadata is
required for recognition. Do not add Product storage fields unless a proven
backward-compatible provenance need exists.

### Tests

Supported and unsupported imported projects, manual version changes, mandatory
reinspection and stale historical platform rejection.

### Commit

`feat: resolve imported Fabric projects`

## 12. Lot I - Multi-Platform Offline Evidence

### Objective

Exercise the real integration, not isolated model construction, for at least
two distinct platforms:

`Platform A -> support resolution -> M1 BLOCK/BLOCK_ITEM/RECIPE -> contract A`
`-> compatible Brain A`

and the same path for Platform B, using the same M1 registry/planner/contract
machinery. Also represent and resolve the 1.21.11 legacy baseline.

Only profiles with actual approved evidence may transition from `TARGET` to
`SUPPORTED`. If local caches/dependencies prevent an offline build, preserve
`TARGET` and document the missing evidence.

### Tests/Evidence

Integration composition, profile-specific current contracts, compatible Brain
selection and legacy representation. No provider live or Minecraft live.

### Commit

`test: validate M2 multi-platform foundation`

## 13. Lot J - Final Regression and Closure Preparation

Run focal M2, Product, Brain, bootstrap, M1 planner/contract tests, full
Python regression, `compileall` and `git diff --check`. Classify every concrete
profile as `TARGET`, `SUPPORTED` or `RETIRED` from evidence, not intent.

This lot prepares closure but does not close M2 while acceptance evidence or
required profile verification remains pending.

## 14. Module and File Ownership

| Lot | New | Modify | Tests | Docs/evidence |
|---|---|---|---|---|
| A | none | none | audit commands/reports | verification record |
| B | `pd_agent.fabric` platform domain | exports if required | Fabric domain tests | lot evidence |
| C | none unless Inspector extension proven | Fabric/project integration | resolution tests | lot evidence |
| D | adapter in existing namespaces if needed | contracts/Brain integration | environment/compatibility tests | lot evidence |
| E | none | Brain/application composition | source/pack tests | lot evidence |
| F | template model in existing namespace | bootstrap | template/bootstrap tests | manifest evidence |
| G | none | Product preflight/errors | Product boundary tests | Product evidence |
| H | none by default | none by default | imported/currentness tests | provenance evidence |
| I | none | fixtures/test composition only | multi-platform integration | profile evidence |
| J | none | none unless closure documentation | complete regression | closure report |

Exact filenames are confirmed at Lot A; no invented paths should be created
only to satisfy this table.

## 15. Test Policy

Each production lot has focal tests and must run `compileall` and
`git diff --check`. Full regression is required after risky Product/Brain/
bootstrap integrations and before M2 closure. Existing coverage is not
reduced. Live provider, Minecraft and benchmark executions remain prohibited.

## 16. AC1-AC18 Traceability

| DESIGN AC | Owner lot | Planned evidence |
|---|---|---|
| AC1 single support authority | B | registry ownership/freeze tests |
| AC2 deterministic supported resolution | B/C | exact-match resolution tests |
| AC3 fail-closed preflight | G | Product preflight with zero dispatch |
| AC4 distinct mapping models | A/B/D | modern/legacy profile and adapter tests |
| AC5 M1 planner reuse | D/I | cross-profile planner integration |
| AC6 current contract environment | D/G | contract environment/fingerprint tests |
| AC7 compatible Brain environment | D/E | adapter and source-selection tests |
| AC8 incompatible pack rejection | E | frozen/source mismatch tests |
| AC9 platform/template bootstrap | F | template/bootstrap tests |
| AC10 bootstrap reinspection | F/H | unchanged workspace round trip |
| AC11 imported resolution | H | imported project integration |
| AC12 currentness after manual change | G/H | reinspection regression |
| AC13 shared Gradle runner | D/I | composition identity/evidence |
| AC14 no duplicate authorities | B-G | architecture/scope review |
| AC15 two-platform offline path | I | Platform A/B integration evidence |
| AC16 legacy representation | A/B/D/I | 1.21.11 resolution evidence |
| AC17 fail-closed cases | B/C/E/G/H | structured negative tests |
| AC18 complete regression | J | full suite report |

No AC is ownerless. A profile remains `TARGET` when its required evidence is
missing.

## 17. Gap Mapping

- `GAP-VERSION-001`: Lots A, B, C, D, G, I.
- `GAP-BRAIN-001`: Lots A, D, E, I.
- `GAP-PROJECT-001`: Lots F, G, H, I.
- `GAP-SEC-001`: remains M5 and is not an M2 deliverable.

These mappings are implementation ownership, not closure claims.

## 18. Commit and Rollback Strategy

Use one focused commit per significant lot and push after validation. Suggested
messages are listed in each lot. Do not accumulate all M2 changes into one
commit. Preserve diagnostics and never stage generated artifacts.

Rollback is lot-local and non-destructive:

- B/C: revert registry/resolution code and tests without touching project data;
- D/E: revert additive adapters/composition while preserving old contract
  readers and Brain sources;
- F: revert template/bootstrap changes while retaining legacy pinned fixture
  compatibility;
- G/H: revert preflight integration without allowing defaults to silently
  authorize unsupported support;
- I/J: remove evidence/tests or closure documentation only.

Any contract schema change must have backward-compatible reads and a defined
non-destructive migration. No manual ledger edits or data deletion is a
rollback strategy.

## 19. Security and Currentness Constraints

Registry, profiles, templates and planner remain data-only. They store no
secrets, commands, processes or executable paths. `ToolExecutor` and
`SecurePathResolver` remain filesystem authorities. Brain cannot execute.
Product preflight fails closed and existing M5 import trust/isolation remains
outside this milestone.

Historical platform provenance is not current truth. Every execution
reinspects and resolves the current workspace. Do not add a
`PlatformCurrentnessLedger`, version state machine or competing fingerprint.

## 20. Compatibility and Migration Rules

Preserve v0.9 Product persistence/hydration, M1 contracts/planner, legacy
fixtures, Brain tests and bootstrap tests. New profile/template/contract data
must be additive and schema-versioned where persisted. No destructive migration
or silent legacy reinterpretation is permitted. `PinnedFabricVersions` remains
available only where compatibility callers need it and cannot authorize M2
support.

## 21. Non-Goals

M2 does not implement a new runtime, AgentRuntime, planner, Brain, DAG,
database, distributed/remote registry, cloud version service, package manager,
automatic network resolver, Alpha capability catalog, general asset toolkit,
generalized Harness/probes, generalized runtime validation 1-to-N,
version-by-capability exhaustive certification, automatic mod migration,
Paper, NeoForge, Velocity, Multi-Agent, complete M5 import trust/isolation or
M6 held-out release certification.

## 22. Closure Requirements

M2 may close only when:

- Lot A verification is accepted;
- all required platform profiles are classified from evidence;
- AC1-AC18 have passing evidence or an explicitly approved non-M2 boundary;
- two distinct platform paths and the 1.21.11 legacy representation pass
  offline as required;
- incompatible and unknown cases fail closed before provider/ExecutionRecord;
- currentness, Brain compatibility, bootstrap/import and security boundaries
  remain intact;
- focal and full regression pass;
- `compileall` and `git diff --check` pass;
- no unapproved production, live or benchmark activity occurred.

No M2 closure or v0.12/M3 work is authorized by this IMP.
