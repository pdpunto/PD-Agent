# PD Agent v0.12 / M3 — Alpha Fabric Capabilities & Assets — Implementation Plan

Status: `IMP — READY FOR PRE-IMPLEMENTATION AUDIT`

Milestone: `PD Agent v0.12 / M3 — Alpha Fabric Capabilities & Assets`

Baseline: `b278d893e60710343ca7d7f246d70474e4567d33`

DESIGN: `docs/design/PD_AGENT_V0.12_M3_ALPHA_FABRIC_CAPABILITIES_ASSETS_DESIGN.md`

RFC: `docs/rfc/PD_AGENT_V0.12_M3_ALPHA_FABRIC_CAPABILITIES_ASSETS_RFC.md`

## 1. Status

This IMP defines how M3 is built. It does not authorize implementation by itself.

After this IMP is accepted, the mandatory next action is **Codex LOT 0 — PRE-IMPLEMENTATION AUDIT**. No implementation lot may begin until LOT 0 returns `AUDIT_PASS` against the real repository, DESIGN, RFC and this IMP. Any material discrepancy returns `AUDIT_BLOCKED`; Codex must stop and report to 00 rather than silently redesigning architecture.

The initial executable focus is Vertical A:

`Block -> associated BlockItem -> minimal assets -> recipe`

Required platforms:

- Fabric 1.21.11;
- Fabric 26.2.

## 2. DESIGN / RFC references

Authoritative accepted states:

- `PD_AGENT_V0_12_M3_DESIGN_READY`;
- `PD_AGENT_V0_12_M3_RFC_READY`.

The implementation must preserve:

`Product request -> FabricPlatformResolution -> CapabilityRegistry/Planner -> FabricTaskContract -> Brain -> FabricNormalOrchestrator -> AgentRuntime -> PRE_BUILD -> Build -> Artifact -> Runtime -> TaskProgressLedger -> CompletionGate`

No lot may create a second planner, runtime, build runner, repair engine, ledger, completion authority, Brain path or generic validation/Harness framework.

## 3. Baseline

IMP creation baseline:

`b278d893e60710343ca7d7f246d70474e4567d33`

LOT 0 must require its own starting `HEAD == origin/main` to equal the accepted IMP commit supplied by 00, not this pre-IMP baseline. If main moved unexpectedly after IMP acceptance, LOT 0 must classify whether the movement is authorized and relevant before proceeding.

## 4. Implementation principles

1. Evidence before claims.
2. Small ordered lots with independent tests and commit/push checkpoints.
3. Existing authorities are extended, never duplicated.
4. `FailureFact.requirement_ids` contains only canonical `requirement:*` IDs.
5. Capability/validation/observation identity domains remain separate.
6. Currentness is mandatory after every relevant mutation.
7. `max_needs=8` remains; Brain composition is extended inside the existing deriver.
8. REUSE is the required/sufficient M3 asset strategy; DERIVE is allowed; GENERATE is optional.
9. Vertical A has one runtime validation requirement with exactly the three accepted observations.
10. 26.2 support is bounded to M3, not generalized.
11. Live Minecraft is required only in explicitly authorized live lots.
12. No provider/API live is required for Vertical A acceptance; deterministic/offline productive inputs isolate capability correctness.
13. CompletionGate remains unchanged unless LOT 0 discovers a real contradiction, in which case implementation stops.
14. A lot requiring commit/push is incomplete until tests/gates pass, commit exists, push passes, `HEAD == origin/main`, and tracked tree is clean.
15. Published rollback uses revert, not history rewrite.

## 5. Dependency / order rationale

Direction's proposed LOT 0–12 order is retained.

The dependency chain is intentional:

- capability identities/contracts must exist before Brain, static validation or runtime can correlate evidence;
- Brain signals depend on the composed contract but not on resource validator implementation;
- resource/PRE_BUILD/artifact rules must exist before productive wiring can claim a valid build product;
- build failure normalization/reconciliation must be integrated before the controlled repair lot;
- runtime observation semantics must be stable before adding the 26.2 fixture/runtime implementation;
- 26.2 materialization is separated from productive wiring so platform infrastructure failures cannot be confused with Product orchestration failures;
- offline integration precedes both live platforms;
- each live platform is validated independently;
- failure/repair validation runs only after the success paths are known-good;
- full regression and closure evidence occur last.

No dependency currently requires reordering. LOT 0 may reveal a concrete repository dependency; if it requires architectural or contractual change, return `AUDIT_BLOCKED` rather than silently changing this order.

## 6. LOT 0 — Codex pre-implementation audit

### Objective

Audit DESIGN + RFC + IMP against the real repository and determine whether implementation can start exactly as specified.

### Preconditions

- accepted IMP commit supplied by 00;
- `HEAD == origin/main == accepted IMP baseline`;
- no unauthorized tracked changes.

### Candidate modules / paths

Audit, do not modify, the real locations of at least:

- capability registry/planner/definitions/instances;
- `FabricTaskContract`, `FabricValidationRequirement`;
- `PreCodeKnowledgeNeedDeriver`, `KnowledgeEnvironment`, `FabricBrainOrchestrator`;
- `ToolExecutor`, mutation-target/path confinement;
- `PreBuildWorkspaceValidator` or actual PRE_BUILD owner;
- `BuildRunner`, `BuildFailureNormalizer`, `FabricBuildOrchestrator` if present;
- `FabricNormalOrchestrator`, `AgentRuntime`;
- Semantic Repair and `FailureReconciler`;
- `ArtifactValidator`;
- `runtime_spec_from_requirement`, `ProductiveMinecraftFunctionalValidator`, `FabricRuntimeOrchestrator`;
- `MinecraftTestSpec`, `MinecraftTestRunner`, observation request/result contracts;
- `TaskProgressLedger`, `CompletionGate`;
- 1.21.11 fixtures and all 26.2 support/profile/materialization assumptions;
- tests covering all of the above.

### Allowed changes

None. Read-only audit only.

### Prohibited changes

All code/docs/config/fixture modifications; API/provider calls; Minecraft; benchmark; Product Execution; commits/pushes.

### Contracts affected

None; audit only.

### Unit tests

No new tests. Existing test inventory and relevant commands may be identified; non-mutating existing tests may be run only if 00's Codex prompt authorizes them.

### Offline integration

No implementation. Inspect existing integration coverage and fixture contracts.

### Live tests

Forbidden.

### Required audit checks

At minimum verify:

1. HEAD/origin/status/diff;
2. DESIGN/RFC/IMP existence and exact accepted versions;
3. RFC names versus actual paths/classes/functions;
4. schema compatibility of four Vertical A capabilities;
5. hidden Server Core/examplemod coupling;
6. capability schema migration/backward compatibility;
7. exact current `max_needs=8` behavior;
8. duplicate build normalization callers/paths;
9. exact ArtifactValidator extension point;
10. current observation dispatch limitations and whether multi-observation already works;
11. failure-to-requirement correlation behavior;
12. R123 canonical requirement/currentness invariants;
13. Java/toolchain selection path;
14. Loom/Fabric API 26.2 materialization reality;
15. fixture assumptions hardcoded to 1.21.11;
16. existing tests to extend rather than duplicate;
17. compatibility risks for pre-M3 capabilities/contracts;
18. whether any RFC assumption is impossible without changing DESIGN/RFC.

### Acceptance criteria

Return `AUDIT_PASS` only if implementation can proceed without material DESIGN/RFC/IMP correction. Otherwise return `AUDIT_BLOCKED` with exact evidence and minimal correction proposal.

### Evidence

- exact HEAD/origin SHA;
- `git status --short`;
- `git diff --check`;
- path/class/function inventory;
- relevant schema excerpts;
- test inventory;
- 26.2 dependency/fixture findings;
- discrepancy table with PASS/BLOCKED classification.

### Commit/push gate

None. LOT 0 must not commit.

### Rollback/recovery

Not applicable; no writes. If accidental writes occur, stop and report before cleanup.

### STOP blockers

Any material path/schema mismatch, duplicate authority, missing required extension point, incompatible capability migration, unresolved R123 conflict, unavailable 26.2 runtime dependency/toolchain, or RFC assumption requiring redesign.

Result: `AUDIT_PASS` or `AUDIT_BLOCKED` only.

## 7. LOT 1 — Capability / composition / contracts

### Objective

Implement the four parameterized Vertical A capability definitions and deterministic contract expansion while preserving existing planner authority.

### Preconditions

LOT 0 `AUDIT_PASS`; tracked clean; accepted baseline.

### Candidate modules / paths

- existing Fabric capability registry/definition modules;
- existing capability planner/contract expansion modules;
- existing Product-to-capability resolver if required by actual repo;
- corresponding unit tests/fixtures.

Exact paths are confirmed by LOT 0.

### Allowed changes

- add/extend `fabric.block`, `fabric.block_item`, `fabric.block_assets`, `fabric.recipe` definitions;
- add bounded parameters/prerequisites/requirements/validation declarations from RFC;
- add generic parameterized resolver data needed to produce candidates;
- preserve platform identity through existing contract environment/context;
- produce one Vertical A runtime validation requirement containing three observation specs;
- add deterministic traceability tests.

### Prohibited changes

No execution logic, Brain implementation, build runner, Minecraft runner, generic DAG, Server-Core-specific production values, new identity domain, CompletionGate change.

### Contracts affected

`CapabilityDefinition`, `CapabilityInstance`, planner expansion, `FabricTaskContract`, task/validation requirement correlation.

### Unit tests

- deterministic instance identities;
- prerequisite graph and topological order;
- generic namespace/block/item/recipe inputs;
- invalid/missing/wrong prerequisite rejection;
- recipe output correlation;
- asset-to-block/item correlation;
- exactly one runtime validation requirement;
- canonical `requirement:*` vs `validation:*` separation;
- no observation IDs in `FailureFact.requirement_ids`;
- existing capability backward compatibility.

### Offline integration

Plan/expand at least two non-Server-Core Vertical A requests for each supported platform profile without execution.

### Live tests

None.

### Acceptance criteria

Composition is deterministic, generic, platform-context-bound and produces the RFC contract shape with no legacy coupling.

### Evidence

Serialized plan/contract fixtures, identity comparisons, test output, changed-file list.

### Commit/push gate

Required. Suggested commit: `feat: add Vertical A capability contracts`. Push; verify HEAD/origin and tracked clean.

### Rollback/recovery

Revert LOT 1 commit; preserve test/evidence output.

### STOP blockers

Schema migration breaks existing capabilities; planner cannot represent two prerequisites without RFC change; platform context cannot be carried without second authority; identity invariants conflict with existing contracts.

## 8. LOT 2 — Brain knowledge / signals

### Objective

Extend the existing pre-code knowledge derivation/composition for the complete Vertical A need set without exceeding `max_needs=8` or creating a second deriver.

### Preconditions

LOT 1 PASS/committed/pushed.

### Candidate modules / paths

Existing Brain pre-code deriver, knowledge models/service, Fabric Brain orchestration, compatible source/pack tests.

### Allowed changes

- add the eight RFC Vertical A semantic domains/signals;
- deterministic composition mode inside existing `PreCodeKnowledgeNeedDeriver`;
- at most one primary need per bounded domain;
- exact `KnowledgeEnvironment` propagation;
- compatible hints/provenance and cross-version guards;
- knowledge fixtures/tests needed for 1.21.11 and 26.2.

### Prohibited changes

No second deriver, no max_needs increase beyond 8, no execution authority, no guessed cross-version compatibility, no Yarn for 26.2.

### Contracts affected

`KnowledgeNeed`, `KnowledgeEnvironment`, pre-code derivation, Brain retrieval/selection/injection traces.

### Unit tests

- all Vertical A domains represented within 8 needs;
- stable priority/dedup;
- version-sensitive needs;
- exact environment identity;
- 1.21.11 remapped/Yarn compatibility;
- 26.2 unobfuscated/no-Yarn compatibility;
- wrong-version rejection;
- recipe/assets not starved by earlier signals.

### Offline integration

Contract -> Brain preparation -> selected/injected compatible knowledge for both platform environments using deterministic sources.

### Live tests

None.

### Acceptance criteria

Complete bounded Vertical A knowledge coverage exists on both environments with no leakage and no second Brain path.

### Evidence

Derived needs, environment/provenance traces, test outputs.

### Commit/push gate

Required. Suggested commit: `feat: extend Brain for Vertical A`. Push; HEAD/origin/tracked-clean gate.

### Rollback/recovery

Revert LOT 2 commit only.

### STOP blockers

Eight needs cannot cover RFC domains without semantic loss; 26.2 compatible knowledge source cannot be represented; existing Brain compatibility semantics contradict RFC.

## 9. LOT 3 — Resources / PRE_BUILD / artifact validation

### Objective

Implement bounded `vertical_a_resources_v1` static validation and extend existing ArtifactValidator to prove required JAR entries.

### Preconditions

LOT 2 PASS.

### Candidate modules / paths

Actual PRE_BUILD owner/validator, resource validation helpers, `ArtifactValidator`, contract validation adapters, tests/fixtures.

### Allowed changes

- bounded path/JSON/profile checks from RFC;
- REUSE required path/reference support; DERIVE if already supportable;
- optional GENERATE only if existing approved mechanism already exists; otherwise leave unsupported/blocking;
- normalized/confined `required_entries` extension in existing ArtifactValidator;
- requirement-correlated violations using canonical task IDs;
- stale/current artifact checks through existing identity path.

### Prohibited changes

No generic JSON schema engine, generic asset graph, Java AST validator, rendering claims, universal resource repair, arbitrary archive path access.

### Contracts affected

PRE_BUILD validation specs/results, ArtifactValidator packaging contract, artifact evidence/currentness.

### Unit tests

- required paths present/missing;
- traversal/absolute/symlink rejection;
- JSON object parsing;
- bounded blockstate/model/item-model/recipe shapes;
- namespace/path/reference coherence;
- REUSE without physical texture;
- optional owned texture semantics;
- duplicate normalized path rejection;
- required JAR entry present/missing;
- stale/ambiguous artifact behavior unchanged;
- canonical requirement correlation.

### Offline integration

Build-free workspace fixture validation plus synthetic/current JAR fixture containing Vertical A resources.

### Live tests

None.

### Acceptance criteria

PRE_BUILD fails fast on missing/malformed Vertical A resources; ArtifactValidator proves current required entries without becoming a second artifact authority.

### Evidence

ValidationResult samples, artifact metadata/evidence refs, test outputs.

### Commit/push gate

Required. Suggested commit: `feat: validate Vertical A resources and artifacts`.

### Rollback/recovery

Revert LOT 3 commit.

### STOP blockers

Artifact extension requires replacing authority; path confinement cannot be preserved; platform-specific resource layout cannot be resolved from current profile/contract.

## 10. LOT 4 — Productive build normalization / reconciliation

### Objective

Connect existing BuildFailureNormalizer exactly once in productive build failure handling and prove strict later reconciliation.

### Preconditions

LOT 3 PASS.

### Candidate modules / paths

`AgentRuntime`, existing build orchestration, BuildFailureNormalizer, Semantic Repair, FailureReconciler, ledger/currentness tests. Exact integration point comes from LOT 0.

### Allowed changes

- single normalization call per failed build attempt;
- persist structured normalized evidence;
- create/update ACTIVE FailureFact with canonical BUILD-correlated task IDs;
- reuse Semantic Repair;
- add/extend strict build reconciliation after later current PASS;
- preserve unrelated active failures.

### Prohibited changes

No second BuildRunner, normalizer, repair engine, state machine or automatic resolution on mutation.

### Contracts affected

Build failure evidence, FailureFact lifecycle, source/build currentness, repair/reconciliation.

### Unit tests

- one normalization per failed attempt;
- category/classification/evidence refs;
- only `requirement:*` correlation;
- repair mutation leaves failure ACTIVE;
- new source revision invalidates stale PASS;
- later matching current build PASS resolves matching failure;
- unrelated ACTIVE failure remains ACTIVE;
- repeated ineffective failure behavior remains compatible.

### Offline integration

Controlled failing Gradle fixture where available, or deterministic build-result orchestration test without provider/Minecraft.

### Live tests

No Minecraft.

### Acceptance criteria

Productive build failure enters existing structured repair path once and cannot be falsely resolved.

### Evidence

Build attempt IDs, normalized failure payload/fingerprint, ledger before/after, test output.

### Commit/push gate

Required. Suggested commit: `fix: integrate productive build failure normalization`.

### Rollback/recovery

Revert LOT 4 commit; retain failure evidence.

### STOP blockers

Existing path already normalizes and a second call would duplicate facts; reconciliation API cannot preserve currentness/unrelated failures without RFC correction.

## 11. LOT 5 — Runtime observations Vertical A

### Objective

Implement bounded multi-observation runtime support for Vertical A, including `BLOCK_ITEM_ASSOCIATION`, while preserving one runtime validation requirement and R123 invariants.

### Preconditions

LOT 4 PASS.

### Candidate modules / paths

Minecraft observation contracts, runtime spec adapter, Harness runner/dispatch, ProductiveMinecraftFunctionalValidator, FabricRuntimeOrchestrator, FailureReconciler, tests.

### Allowed changes

- add `BLOCK_ITEM_ASSOCIATION` observation type/params/result;
- support exactly the RFC Vertical A observation profile/order;
- dispatch three observations under one validation requirement;
- map failed observations to canonical task requirement IDs;
- preserve current artifact/source/validation revision correlation;
- reconcile only current passing represented requirements.

### Prohibited changes

No arbitrary probe graph, generic RecipeManager introspection, generalized N-validation architecture, visual rendering check, observation IDs as task requirement IDs.

### Contracts affected

Observation request/result, runtime spec, runtime identity, validation result, failure correlation/reconciliation.

### Unit tests

- block registry PASS/FAIL;
- item registry PASS/FAIL;
- BlockItem association PASS;
- item missing/not BlockItem/wrong block failures;
- deterministic observation order;
- selective failure correlation;
- R123 canonicalization;
- stale artifact/runtime evidence rejected;
- unrelated failures preserved.

### Offline integration

Synthetic Harness-result parsing/aggregation for all combinations needed to prove correlation/currentness without Minecraft.

### Live tests

None in this lot.

### Acceptance criteria

Runtime contracts can represent all three Vertical A observations and produce correct canonical/current evidence without generalized Harness architecture.

### Evidence

Observation payloads, runtime identity/revision, failure correlation snapshots, tests.

### Commit/push gate

Required. Suggested commit: `feat: add Vertical A runtime observations`.

### Rollback/recovery

Revert LOT 5 commit.

### STOP blockers

Current runner cannot support bounded multi-observation without architectural redesign; R123 invariants conflict; BlockItem association cannot be observed in supported server runtime boundary.

## 12. LOT 6 — Harness 26.2 bounded support

### Objective

Materialize the minimum 26.2 Harness/runtime path needed by Vertical A, separately validating infrastructure before full capability execution.

### Preconditions

LOT 5 PASS; LOT 0 confirmed exact 26.2 assumptions.

### Candidate modules / paths

Existing Minecraft Harness fixtures/build files/runner platform selection, support profiles, runtime dependency resolution, test harness mod sources.

### Allowed changes

Only concrete 26.2 M3 support by resolved `platform_id`: Java 25/toolchain, Minecraft 26.2, Loader 0.19.3, Fabric API 0.158.0+26.2, compatible/materialized Loom 1.17-SNAPSHOT path, UNOBFUSCATED/no-Yarn assumptions as verified by LOT 0, and the bounded observation code needed by LOT 5.

### Prohibited changes

No universal Harness framework, arbitrary version registry inside Harness, Yarn/remapped 26.2 path, provider/API/Product Execution.

### Contracts affected

Harness fixture/runtime materialization and platform-specific launch inputs only; logical observation/result contracts stay those of LOT 5.

### Unit tests

- platform selection;
- Java/toolchain values;
- no Yarn for 26.2;
- dependency/version materialization configuration;
- 1.21.11 fixture remains unchanged/compatible.

### Offline integration

Separate gates:

A. materialize/configure 26.2 fixture/runtime;
B. compile/package Harness fixture if possible offline from materialized dependencies;
C. verify observation command/config generation for registry checks;
D. verify BlockItem association command/config generation;
E. prepare full Vertical A spec without launching Minecraft.

### Live tests

None during implementation lot unless 00 explicitly authorizes a bounded infrastructure smoke; normal plan defers live to LOT 10.

### Acceptance criteria

26.2 Harness is concretely materializable and can accept the Vertical A observation profile without introducing M4 architecture.

### Evidence

Resolved versions/toolchain, materialization/build logs, fixture hashes, generated launch/spec data.

### Commit/push gate

Required. Suggested commit: `feat: add bounded Fabric 26.2 harness support`.

### Rollback/recovery

Revert LOT 6 commit; preserve downloaded/materialized evidence references where safe; return to LOT 5 checkpoint.

### STOP blockers

Required Loom/Fabric API/toolchain cannot be reproducibly materialized; current fixture assumes 1.21.11 in a way requiring generalized redesign; 26.2 APIs invalidate RFC observation assumptions.

## 13. LOT 7 — Vertical A productive wiring

### Objective

Connect the completed Vertical A contracts through the existing productive orchestration path without provider dependency.

### Preconditions

LOTS 1–6 PASS and pushed.

### Candidate modules / paths

Product Fabric task resolver, FabricNormalOrchestrator composition, Brain preparation integration, PRE_BUILD/build/artifact/runtime adapters, ProductiveMinecraftFunctionalValidator.

### Allowed changes

- parameterized Product/task input -> platform resolution -> four capability candidates -> contract;
- exact Brain environment/signals;
- existing mutation-target exposure for Java/resources;
- existing PRE_BUILD/build/artifact/runtime invocation;
- current evidence/ledger/gate propagation;
- deterministic/offline execution seam already supported by repo for later validation.

### Prohibited changes

No Server Core branch, provider-specific logic, second orchestration path, fake success, bypass of platform resolution/Brain/currentness/CompletionGate.

### Contracts affected

Integration only; no new authority.

### Unit tests

Wiring and fail-closed tests for unsupported platform, missing knowledge, PRE_BUILD failure, build failure, artifact failure, runtime failure and incomplete gate.

### Offline integration

Parameterized Vertical A Product/normal Fabric path with deterministic mutation/execution dependencies, stopping before live Minecraft where necessary.

### Live tests

None.

### Acceptance criteria

One generic Vertical A request reaches every existing authority in correct order and no fixture-specific production coupling exists.

### Evidence

Execution/order traces, contract identity, environment, ledger snapshots, tests.

### Commit/push gate

Required. Suggested commit: `feat: wire Vertical A productive execution`.

### Rollback/recovery

Revert LOT 7 commit; previous subsystem lots remain independently valid.

### STOP blockers

Product resolver requires hardcoded fixture values; productive path bypasses an accepted authority; deterministic seam cannot exercise wiring without provider/API and no existing approved substitute exists.

## 14. LOT 8 — Offline / integration validation

### Objective

Prove the complete Vertical A implementation deterministically without provider/API or live Minecraft before spending live-runtime effort.

### Preconditions

LOT 7 PASS.

### Candidate modules / paths

Tests/fixtures only unless a defect requires a minimal corrective code change within an already-defined contract.

### Allowed changes

Tests/fixtures and contract-conformant bug fixes only. Any architectural discrepancy stops and returns to 00.

### Prohibited changes

No live Minecraft, API/provider, benchmark, generalized framework.

### Test matrix

UNIT: all LOT 1–7 focused suites.

OFFLINE INTEGRATION:
- both platform profiles;
- generic non-Server-Core request;
- deterministic composition/identities;
- Brain environment/no leakage;
- Java/resource mutation expectations;
- PRE_BUILD PASS/FAIL;
- synthetic/current artifact required entries;
- three observation result aggregation;
- canonical failure correlation/currentness;
- CompletionGate deterministic PASS when all authoritative evidence is supplied.

PRODUCTIVE OFFLINE:
- Product/Fabric normal path using deterministic local dependencies, no provider/API and no Minecraft process;
- prove no alternate runtime/build/ledger/gate authority.

### Live tests

None.

### Acceptance criteria

All offline layers PASS on both profiles; no unresolved functional defect before live validation.

### Evidence

Test commands/results, fixture identities/hashes, contract/source/build/artifact/runtime synthetic identities, gate result.

### Commit/push gate

Required only if tests/fixtures or conformant fixes change tracked files. Suggested commit: `test: validate Vertical A offline integration`. If no changes, record no-commit PASS checkpoint and verify HEAD/origin/clean.

### Rollback/recovery

Revert only LOT 8 tracked commit if created.

### STOP blockers

Any defect requiring DESIGN/RFC/IMP change; any profile-specific mismatch hidden by mocks; any evidence currentness/correlation inconsistency.

## 15. LOT 9 — Live Minecraft 1.21.11 validation

### Objective

Prove Vertical A against real Fabric 1.21.11 Minecraft using the current artifact and existing Harness.

### Preconditions

LOT 8 PASS; explicit 00 authorization for Minecraft live; environment/dependencies ready; no API/provider live.

### Candidate modules / paths

Validation scripts/tests/evidence locations only; implementation changes are defect fixes followed by re-running appropriate earlier gates.

### Allowed changes

Evidence-producing test configuration/fixtures and minimal contract-conformant defect fixes.

### Prohibited changes

No provider/API, benchmark, fake observations, acceptance reduction.

### Unit / offline tests

Relevant regressions rerun after any fix.

### Live tests

Real 1.21.11 dedicated server proving:

- supported platform/profile;
- current built artifact loaded;
- Minecraft starts;
- `REGISTRY_ENTRY_PRESENT(block)` PASS;
- `REGISTRY_ENTRY_PRESENT(item)` PASS;
- `BLOCK_ITEM_ASSOCIATION` PASS;
- resource/datapack load sufficient for startup;
- runtime evidence current and requirement-correlated;
- CompletionGate PASS when all Vertical A requirements are satisfied.

### Acceptance criteria

All above PASS with reproducible evidence and exact current identities.

### Evidence

Platform/profile, request/contract identity, source revision, build identity, artifact identity/SHA, validation revision, all observation results, requirement IDs, failure states, CompletionGate result, logs/evidence paths.

### Commit/push gate

If no code/test changes, no commit required; record live evidence checkpoint. Any corrective tracked change requires tests, commit/push, HEAD/origin/clean, then live rerun. Suggested fix commit must describe actual defect.

### Rollback/recovery

Revert corrective commit if it regresses; preserve failed and passing live evidence.

### STOP blockers

Infrastructure failure not attributable to product code; stale artifact; unsupported/mismatched runtime; observation ambiguity; any attempt to substitute mocks.

## 16. LOT 10 — Live Minecraft 26.2 validation

### Objective

Independently prove the same logical Vertical A acceptance on real Fabric 26.2.

### Preconditions

LOT 9 PASS; LOT 6 materialization PASS; explicit 00 authorization; Java 25/runtime dependencies verified.

### Candidate modules / paths

26.2 Harness/runtime validation/evidence only, plus contract-conformant fixes if necessary.

### Allowed changes

Minimal 26.2-specific bounded fixes inside RFC scope, with earlier gates rerun.

### Prohibited changes

No universal Harness, Yarn/remapped assumptions, provider/API, benchmark, lowered observations.

### Live validation sequence

A. confirm exact 26.2 platform/profile/materialization;
B. start real Minecraft and prove server/runtime readiness;
C. block registry observation;
D. item registry observation;
E. BlockItem association observation;
F. full Vertical A current-evidence CompletionGate PASS.

Do not collapse these diagnostics: each stage must be distinguishable in evidence so infrastructure and semantic failures can be separated.

### Acceptance criteria

Same logical Vertical A contract as 1.21.11 passes on 26.2 with exact unobfuscated environment and current evidence.

### Evidence

Same identity/log matrix as LOT 9 plus Java/toolchain, Loader/Fabric API/Loom/runtime dependency materialization evidence.

### Commit/push gate

Same rule as LOT 9. Corrective tracked changes require dedicated commit/push and rerun.

### Rollback/recovery

Revert corrective 26.2 commit; retain evidence; return to last PASS checkpoint.

### STOP blockers

Any RFC assumption about 26.2 API/Harness proves false and requires redesign; dependency/toolchain cannot be reproduced; success requires generalized M4 framework.

## 17. LOT 11 — Controlled failure / repair / revalidation

### Objective

Prove one real repairable Vertical A failure traverses the existing failure/repair/currentness lifecycle and that unrelated failures are not accidentally resolved.

### Preconditions

Both live success lots PASS; controlled deterministic fault defined without generic fault framework; explicit authorization for any Minecraft rerun required by the chosen failure.

### Candidate modules / paths

Existing test fixture/mutation input, build normalization, Semantic Repair, FailureReconciler, PRE_BUILD/build/artifact/runtime validation, ledger/gate evidence.

### Allowed changes

A single bounded test fixture/scenario and minimal defect fixes. Fault injection must be explicit test data, not production fault framework.

### Prohibited changes

No new repair engine, state machine, fault framework, manual ledger editing, resolving failure on mutation alone.

### Required sequence

`FAIL -> normalized structured failure -> ACTIVE FailureFact -> repair mutation -> new source revision -> PRE_BUILD -> rebuild -> artifact revalidation -> runtime revalidation when applicable -> RESOLVED -> CompletionGate PASS`

Also seed/retain an unrelated ACTIVE failure and prove it remains ACTIVE until its own authoritative evidence exists. For the final CompletionGate PASS assertion, the unrelated control failure must be removed/resolved only by its legitimate test setup/evidence, never by the repair under test.

### Unit tests

Strict failure identity/currentness/reconciliation and unrelated-failure preservation.

### Offline integration

Controlled repair lifecycle with deterministic build/runtime evidence where possible.

### Live tests

At least one real repairable failure must be demonstrated. Preferred first fault is a real build compilation/API failure because it directly exercises BuildFailureNormalizer; runtime revalidation is then required if the repaired task requires runtime, which Vertical A does. If the repo audit proves a safer existing repair fixture is more representative, Codex may use it only if it still demonstrates the full required sequence.

### Acceptance criteria

Every lifecycle transition is evidence-backed; repair mutation alone leaves failure ACTIVE; later current evidence resolves only the represented failure; gate cannot pass while unrelated ACTIVE failure remains.

### Evidence

Failure fingerprint/category, canonical requirement IDs, source revisions before/after, build attempts, artifact SHA before/after, runtime revision/observations, ledger snapshots, repair trace, CompletionGate before/after.

### Commit/push gate

Required if tracked fixture/tests/fixes are added. Suggested commit: `test: prove Vertical A repair reconciliation`.

### Rollback/recovery

Revert LOT 11 tracked commit; preserve evidence; do not mutate historical ledger evidence manually.

### STOP blockers

Repair path cannot consume normalized failure; mutation falsely resolves failure; unrelated failure is reconciled; currentness cannot be demonstrated; test would require provider/API not separately approved.

## 18. LOT 12 — Full regression / Vertical A closure evidence

### Objective

Run final regressions and assemble authoritative Vertical A closure evidence across both supported platforms.

### Preconditions

LOTS 1–11 PASS; all corrective commits pushed; tracked clean.

### Candidate modules / paths

Tests and evidence/reporting only. No new feature scope.

### Allowed changes

Closure tests/evidence documentation only if explicitly authorized; defect fixes must return to the owning earlier lot and rerun downstream gates.

### Prohibited changes

No new capability scope, B–F implementation, M4 framework, acceptance reduction.

### Tests

- focused unit suites for capability/planner/Brain/resources/build/artifact/runtime/ledger/gate;
- offline integration;
- Productive offline;
- full repository regression suite;
- compile/static checks already canonical to repo;
- `git diff --check`;
- evidence verification for live 1.21.11 and 26.2;
- controlled failure/repair evidence verification.

No new live run is required if LOT 9–11 evidence is current relative to final code. If a later corrective change touches behavior relevant to a live proof, rerun the affected live lot.

### Acceptance criteria

All final Vertical A acceptance rows PASS, full regression PASS, no stale live evidence, no unauthorized tracked files, HEAD/origin aligned.

### Evidence

Final acceptance matrix with exact evidence refs, test logs, live run IDs/paths, artifact SHAs, final commit SHA and clean status.

### Commit/push gate

Any tracked closure change requires dedicated commit/push. Final state must satisfy `HEAD == origin/main` and tracked clean.

### Rollback/recovery

A failing regression returns to the owning lot. Revert only the offending published lot/fix commit; do not rewrite history.

### STOP blockers

Any acceptance row lacks current evidence; full regression fails; live evidence became stale; B–F/M4 work is needed to make A pass.

## 19. Vertical A final acceptance matrix

| # | Requirement | Primary proving lot | Required evidence |
|---|---|---|---|
| 1 | parameterized request, not Server-Core-specific | 1/7/8 | request + plan/contract |
| 2 | deterministic capability composition | 1 | repeated identities/order |
| 3 | exact supported platform resolution | 1/8/9/10 | platform resolution/profile |
| 4 | correct Brain environment | 2/8 | KnowledgeEnvironment + provenance |
| 5 | Java/resources correct | 3/8 | workspace/PRE_BUILD evidence |
| 6 | PRE_BUILD PASS | 3/8/11 | ValidationResult/current source |
| 7 | build PASS | 8/9/10/11 | BuildResult/build identity |
| 8 | artifact current/VALID | 3/9/10/11 | artifact identity/currentness |
| 9 | required JAR entries present | 3/9/10 | required_entries evidence |
| 10 | Minecraft starts | 9/10 | real runtime process evidence |
| 11 | block registry PASS | 9/10 | observation result |
| 12 | item registry PASS | 9/10 | observation result |
| 13 | BlockItem association PASS | 9/10 | observation result |
| 14 | current runtime evidence | 5/9/10/11 | validation revision + artifact identity |
| 15 | canonical requirement correlation | 1/5/8/11 | requirement IDs/ledger |
| 16 | no cross-version knowledge leakage | 2/8 | environment/source compatibility tests |
| 17 | failure→repair→revalidation | 4/11 | full lifecycle evidence |
| 18 | unrelated failures preserved | 4/5/11 | ledger before/after |
| 19 | CompletionGate PASS | 8/9/10/11/12 | gate result with no blockers |
| 20 | equivalent proof on 1.21.11 and 26.2 | 9/10/12 | paired platform evidence |

Vertical A closes only when all 20 rows are PASS with current evidence.

## 20. Transition B — Standalone Items + Recipes

### Reuse from A

Capability identity/composition pattern, canonical requirement domains, Brain bounded composition, resource/PRE_BUILD profile pattern, required_entries artifact checks, build normalization/repair/currentness, registry observation pattern, ledger/gate evidence.

### Required research / DESIGN/RFC delta

Define standalone item semantics, item-specific resource/model requirements and recipe variants not already covered by A. Do not assume BlockItem association.

### M4 dependency

None for bounded standalone item/recipe support if current observation model suffices; generalized recipe introspection remains M4.

No B implementation begins before A closure and accepted delta.

## 21. Transition C — Tools + Weapons + Armor

### Reuse from A

Composition/contracts, Brain version protection, safe mutations/resources, PRE_BUILD/artifact/build/repair/currentness, registry checks.

### Required research / DESIGN/RFC delta

Tool/weapon/armor component APIs for both platforms, equipment attributes/components, model/resources, bounded functional validation semantics.

### M4 dependency

Likely requires new bounded behavior/equipment observations. If validation requires generalized heterogeneous probe architecture, defer that portion to M4 rather than expanding M3 silently.

## 22. Transition D — Basic mobs / entities

### Reuse from A

Platform resolution, capability/planner identities, Brain environment, build/artifact/currentness/failure lifecycle, Harness process/evidence foundations.

### Required research / DESIGN/RFC delta

Entity type registration, attributes, spawning, model/client boundary, minimal server-functional definition, entity observation semantics on both platforms.

### M4 dependency

Generic entity/world observation is explicitly outside current RFC and likely M4-dependent. M3 may only proceed after an accepted bounded delta that does not smuggle in generalized Harness architecture.

## 23. Transition E — Basic behaviors

### Reuse from A

Failure/currentness/repair lifecycle, Brain exact-platform knowledge, runtime evidence and CompletionGate principles.

### Required research / DESIGN/RFC delta

Define each behavior's observable server-side contract, deterministic setup and bounded probe semantics.

### M4 dependency

Generic behavior probes are M4-deferred. E requires a specific accepted delta or waits for M4 infrastructure.

## 24. Transition F — Assets transversal

### Reuse from A

`fabric.block_assets` bounded asset identity, REUSE/DERIVE/GENERATE strategy split, path confinement, PRE_BUILD JSON/reference checks, artifact required_entries.

### Required research / DESIGN/RFC delta

Generalize only the asset cases concretely needed by B–E: item/entity/equipment resource forms and platform differences. Preserve client-rendering non-claim unless separately designed/tested.

### M4 dependency

Generic asset dependency graph and universal asset validation remain M4 or later. F is transversal reuse/extension, not authorization for a generic graph.

## 25. M4 deferments

Remain explicitly out of M3 implementation unless a new accepted DESIGN/RFC changes scope:

- generalized validation architecture;
- generalized/universal Minecraft Harness;
- arbitrary N runtime validation requirements;
- heterogeneous arbitrary probe graph;
- generalized RecipeManager introspection;
- generic behavior/entity/worldgen probes;
- client rendering correctness;
- generic Java AST validation;
- exhaustive JSON schema infrastructure;
- generic asset dependency graph;
- universal resource auto-repair;
- universal Fabric version support/migration;
- Multi-Agent architecture.

If any M3 lot requires one of these to pass, STOP and return to 00.

## 26. Commit strategy

Implementation uses independent published checkpoints:

- LOT 0: no commit;
- LOT 1: capability/contracts commit;
- LOT 2: Brain commit;
- LOT 3: resources/artifact commit;
- LOT 4: build normalization/reconciliation commit;
- LOT 5: runtime observation commit;
- LOT 6: 26.2 Harness commit;
- LOT 7: productive wiring commit;
- LOT 8: test commit only if tracked changes;
- LOT 9/10: evidence-only unless corrective tracked changes;
- LOT 11: controlled repair test/fix commit if tracked changes;
- LOT 12: closure commit only if tracked closure files are authorized.

Every required commit gate:

1. focused tests PASS;
2. required integration gate PASS;
3. `git diff --check` PASS;
4. only intended tracked files changed;
5. commit created with scoped message;
6. push `origin/main` PASS;
7. `HEAD == origin/main`;
8. tracked tree clean.

Do not accumulate multiple implementation lots into one commit. Do not amend/rewrite already published milestone history as normal workflow.

## 27. Rollback strategy

Rollback unit is the last published lot commit or corrective commit.

Default recovery:

1. preserve failure evidence/logs;
2. identify owning lot;
3. if rollback is required, create a normal `git revert <commit>`;
4. run that checkpoint's regression gates;
5. push revert;
6. verify HEAD/origin/clean;
7. resume only after root cause and document compatibility are understood.

`git reset --hard` is not the normal strategy for published history. No force-push for ordinary recovery.

Uncommitted accidental changes discovered during LOT 0 are reported before cleanup; Codex must not destroy user work.

## 28. Evidence requirements

Every implementation lot records:

- starting/final SHA;
- changed files;
- tests/commands and exact results;
- relevant contract/identity data;
- failures/deviations;
- commit/push/clean status.

Vertical A closure evidence additionally requires:

- platform/profile;
- parameterized request identity;
- plan/contract identity;
- exact KnowledgeEnvironment and compatible Brain provenance;
- source revision;
- PRE_BUILD result/evidence;
- build attempt identity/result;
- artifact identity/path/SHA/currentness;
- required JAR entry results;
- validation revision;
- all three observation requests/results;
- canonical task requirement IDs;
- FailureFact states before/after repair where applicable;
- TaskProgressLedger snapshot/evidence refs;
- CompletionGate result;
- Minecraft process/startup/resource-load logs;
- evidence paths sufficient for reproduction.

Evidence must be persisted through existing storage/reporting mechanisms where they already own the data. This IMP does not authorize a new evidence database.

## 29. Risks / blockers

Primary risks:

1. actual repo names/paths differ from RFC terminology;
2. existing capability schemas need migration incompatible with old fixtures/contracts;
3. hidden `server_core`/`examplemod` coupling survives in resolver/tests;
4. `max_needs=8` composition cannot cover A without changing existing semantics;
5. build failure normalization already occurs elsewhere and would duplicate facts;
6. ArtifactValidator extension point differs from assumed contract;
7. runner currently supports only one observation or maps IDs incorrectly;
8. R123 canonical/currentness invariants regress under multi-observation;
9. 26.2 Java/Loom/Fabric API materialization is unavailable or non-reproducible;
10. 1.21.11 fixture assumptions are embedded too deeply for bounded 26.2 support;
11. resource path/schema differences between 1.21.11 and 26.2 exceed current RFC assumptions;
12. live evidence becomes stale after later fixes;
13. unrelated active failures are accidentally reconciled;
14. CompletionGate requires a contract change not anticipated by DESIGN/RFC.

Any architectural risk materializing into a contradiction is a STOP condition, not permission to redesign locally.

## 30. M3 closure path

M3 execution sequence is:

1. 00 accepts this IMP;
2. 00 sends one complete Codex LOT 0 prompt;
3. Codex returns `AUDIT_PASS` or `AUDIT_BLOCKED`;
4. if blocked, 00 routes findings back to the owning DESIGN/RFC/IMP conversation and documents are corrected before implementation;
5. if pass, implement LOTS 1–8 sequentially with checkpoint commits;
6. obtain explicit authorization and execute live LOT 9 on 1.21.11;
7. execute live LOT 10 on 26.2;
8. execute LOT 11 controlled failure/repair;
9. execute LOT 12 full regression and Vertical A closure matrix;
10. only after Vertical A is closed, open bounded research/deltas for B, then C/D/E/F according to dependency and M4 boundaries;
11. each later vertical receives its required DESIGN/RFC delta and executable IMP delta before implementation;
12. M3 milestone closes only when its accepted vertical scope is implemented, validated, regression-clean and evidence-backed on required platforms.

Vertical A is therefore the implementation template, not proof that B–F are already specified.

## 31. IMP acceptance criteria

This IMP is ready for 00 review when all are true:

1. baseline and authoritative DESIGN/RFC are explicit;
2. architecture authority chain is unchanged;
3. LOT 0 is mandatory, read-only and fail-closed;
4. LOTS 1–12 are ordered by real contract dependency;
5. every lot defines objective, preconditions, candidate paths, allowed/prohibited changes, contracts, unit/integration/live tests, acceptance, evidence, commit gate, rollback and STOP blockers;
6. Vertical A capabilities/dependencies match RFC exactly;
7. identity-domain and R123 constraints are preserved;
8. Brain remains one deriver with `max_needs=8` and exact environments;
9. resource/PRE_BUILD/artifact responsibilities remain bounded;
10. build normalization occurs exactly once and repair does not imply resolution;
11. runtime has exactly one Vertical A validation requirement with three observations;
12. 26.2 is a bounded explicit risk/gate, not generalized Harness work;
13. live 1.21.11 and 26.2 proofs are separate and mandatory;
14. controlled failure/repair proves strict current reconciliation and unrelated-failure preservation;
15. final acceptance matrix contains all 20 required Vertical A claims;
16. B–F contain transition strategy only and require their own accepted deltas where needed;
17. M4 deferments are explicit;
18. commits/pushes and rollback are lot-scoped;
19. no provider/API/benchmark/Product Execution is required by this IMP creation;
20. implementation cannot start before Codex LOT 0 `AUDIT_PASS`.

Expected verdict after document persistence and repository verification:

`PD_AGENT_V0_12_M3_IMP_READY`
