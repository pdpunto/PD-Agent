# PD_AGENT_V0.10_M1_IMP

Status: `IMP - READY FOR PRE-IMPLEMENTATION AUDIT`

Milestone: `PD Agent v0.10 - M1 General Fabric Task Foundation`

Baseline: `9945bd642bdbdc37efc05aec92a4f3a60a7e69e4`

Authorities:

- `docs/roadmap/PD_AGENT_ROADMAP_TO_ALPHA.md`
- `docs/design/PD_AGENT_V0.10_M1_GENERAL_FABRIC_TASK_FOUNDATION_DESIGN.md`
- `docs/rfc/PD_AGENT_V0.10_M1_GENERAL_FABRIC_TASK_FOUNDATION_RFC.md`

## 1. Status

This IMP translates the M1 DESIGN and RFC into small, reversible
implementation lots. It does not authorize implementation. R96 must audit
this plan against the real repository before any code change.

## 2. Authorities

The canonical order is Roadmap -> DESIGN -> RFC -> this IMP -> R96 audit ->
implementation -> validation -> closure. Existing v0.9 runtime, Product,
Brain, ledger, evidence, Harness, security and CompletionGate authorities are
preserved.

## 3. Baseline

Required baseline before each lot:

`9945bd642bdbdc37efc05aec92a4f3a60a7e69e4`

Tracked working tree must be clean, with only the pre-existing untracked
`scripts/benchmark/diagnostics/` allowed. No API, Minecraft, benchmark live,
Product Execution or ledger writes are part of this IMP.

## 4. Implementation Principles

- Reuse existing authorities before adding anything.
- Keep capability data declarative and parameterized.
- Keep planning deterministic after interpretation.
- Keep one composed request as one Product Task/Execution.
- Keep `FabricTaskContract` as the execution boundary.
- Reject invalid or unsupported plans before runtime.
- Preserve v0.9 serialization and lifecycle behavior.
- Make every lot independently reviewable and reversible.
- Do not introduce M2/M3/M4/M5/M6 scope to make M1 appear complete.

## 5. Repo Reality / Target Files

Audited existing boundaries:

- `src/pd_agent/core/contracts.py`: Fabric contract, requirements,
  validations, mutation expectations and environment constraints.
- `src/pd_agent/core/progress.py`: `ExecutionPlan`, `ExecutionPlanStep` and
  `TaskProgressLedger`.
- `src/pd_agent/product/fabric.py`: Product resolver and runner; current
  Server Core specialization.
- `src/pd_agent/product/execution.py`: Product `ExecutionService.start`.
- `src/pd_agent/product/application.py`: Product composition root.
- `src/pd_agent/fabric/orchestration.py`: existing Fabric orchestration.
- `src/pd_agent/runtime/engine.py`: provider/tool/build/validation/repair loop.
- `src/pd_agent/validation/completion.py`: sole completion authority.
- `src/pd_agent/validation/runtime.py`: known first-runtime-requirement gap,
  explicitly deferred to early M4/M4.
- `src/pd_agent/brain/`: existing retrieval, context and repair boundaries.
- `src/pd_agent/project/`, `src/pd_agent/reporting/`: inspection and storage.
- `src/pd_agent/tools/`: filesystem and security policy.
- `src/pd_agent/benchmark/`: reusable contract/fixture/test infrastructure,
  not a second Product planner.

Candidate new modules require confirmation by R96 before implementation:

- `src/pd_agent/fabric/capabilities.py`: declarative definitions/instances;
- `src/pd_agent/fabric/planning.py`: normalization, dependencies and plan;
- `tests/unit/test_fabric_capabilities.py`;
- `tests/unit/test_fabric_planning.py`.

These are target proposals, not files created by this IMP.

## 6. Dependency Order

Recommended sequence:

`A Core model -> B Registry/IDs -> C Dependencies/composition`
` -> D Requirement/validation expansion -> E Plan provenance/persistence`
` -> F Product interpreter/resolver migration -> G representative integration`
` -> H regression/security/closure`.

A and B are tightly coupled but independently reviewable. C must follow the
identity rules from B. D needs the normalized order from C. E must stabilize
before F persists or exposes planner metadata. G depends on F. H depends on
all previous lots.

## 7. Lot Overview

| Lot | Boundary | Primary result |
|---|---|---|
| A | Core capability model | Definitions, instances and candidate data |
| B | Registry, normalization and IDs | Deterministic registry and identities |
| C | Dependencies and composition | Validated ordered composed plan |
| D | Requirement/validation expansion | Existing Fabric contract generation |
| E | ExecutionPlan provenance | Traceability and v0.9 persistence compatibility |
| F | Product migration | Common planner path and Server Core compatibility |
| G | Representative vertical | BLOCK + BLOCK_ITEM + RECIPE evidence |
| H | Regression/security/closure | Full M1 evidence and closure readiness |

## 8. Lot A - Core Capability Model

### Objective

Introduce the smallest declarative model for capability definitions, instances,
normalized candidate data and planning failures.

### Prerequisites

R96 PASS; current contract/progress tests understood; no unresolved
DESIGN/RFC discrepancy.

### Files

- NEW candidate: `src/pd_agent/fabric/capabilities.py`.
- EXTEND only if required: `src/pd_agent/fabric/__init__.py`.
- NEW tests: `tests/unit/test_fabric_capabilities.py`.
- REMOVE/RETIRE: none in this lot.

### Symbols

`CapabilityDefinition`, `CapabilityInstance`, normalized candidate value and
the small planning failure/result boundary.

### Behavior

- bounded JSON-compatible parameters;
- schema/version validation;
- stable definition and instance identity inputs;
- declarative prerequisites, outcomes, validations and mutation expectations;
- no executable commands or runtime state.

### Invariants

No capability-specific class hierarchy; no provider/tool execution; no second
contract, runtime or Product task model.

### Tests and gate

Run new schema/parameter tests plus `tests/unit/test_fabric_task_contract.py`.
Acceptance gate: valid generic definitions and instances are accepted;
malformed data is rejected deterministically; existing tests pass.

### Side effects

Only source/test files in the lot. No filesystem, provider, Minecraft,
benchmark or ledger side effects.

### Commit and rollback

Commit: `feat: add M1 capability model`.

Rollback: revert the single lot commit; no persisted data exists yet.

### Later dependencies

B consumes the model; all other lots depend on its identity and validation
semantics.

## 9. Lot B - Registry, Normalization and Stable IDs

### Objective

Provide the minimal declarative registry for `BLOCK`, `BLOCK_ITEM` and
`RECIPE`, plus canonical normalization and stable IDs.

### Prerequisites

Lot A PASS.

### Files

- EXTEND candidate: `src/pd_agent/fabric/capabilities.py`.
- NEW candidate: `src/pd_agent/fabric/registry.py` only if separation is
  justified by R96.
- EXTEND candidate: `src/pd_agent/fabric/__init__.py`.
- NEW/extend tests in `tests/unit/test_fabric_capabilities.py` and
  `tests/unit/test_fabric_planning.py`.
- REMOVE/RETIRE: no permanent Server Core resolver removal yet.

### Symbols

Capability registry, canonical parameter normalizer, definition ID,
instance ID, requirement ID and validation ID derivation.

### Behavior

- registry lookup is deterministic;
- only the three representative capability definitions and strict
  Server-Core compatibility data are included;
- mapping keys, identifiers, strings, defaults and semantic list ordering are
  normalized;
- IDs use schema/version/kind/canonical parameters and collision-resistant
  canonical data;
- prompt ordering does not affect identity.

### Invariants

No M2 Support Registry, version matrix, Alpha catalog or raw LLM identity.
Equivalent semantics may deduplicate; semantic changes must not.

### Tests and gate

Test same semantics, reordered candidates, changed parameters, default values,
invalid identifiers and shared-prerequisite identity. Run existing contract
roundtrip tests. Gate: deterministic identities and registry lookup pass.

### Side effects

Source/test changes only; no registry persistence or external access.

### Commit and rollback

Commit: `feat: add M1 capability registry`.

Rollback: revert Lot B, preserving Lot A if desired; no runtime behavior is
changed before Lot F.

### Later dependencies

C uses IDs for graph keys and deduplication. D uses IDs for output mapping.

## 10. Lot C - Dependency and Composition Planner

### Objective

Resolve a candidate set into one validated, normalized and deterministically
ordered composed plan.

### Prerequisites

Lots A and B PASS.

### Files

- NEW candidate: `src/pd_agent/fabric/planning.py`.
- EXTEND candidate: `src/pd_agent/fabric/__init__.py`.
- NEW tests: `tests/unit/test_fabric_planning.py`.
- REMOVE/RETIRE: none.

### Symbols

Planner, normalized capability plan, prerequisite resolver and deterministic
ordering result.

### Behavior

- validate candidates and support declarations;
- expand prerequisites;
- bind only declared parameters;
- deduplicate shared instances;
- reject missing/duplicate/invalid prerequisites;
- reject incompatible compositions;
- detect cycles;
- stable topological ordering with stable capability ID tie-break;
- produce one composed plan.

### Invariants

Temporary in-memory graph only; no persistent DAG framework, scheduler,
runtime state, tools or provider calls.

### Tests and gate

Test independent and dependent capabilities, shared prerequisites, missing
references, duplicate references, cycles, incompatible inputs, prompt-order
independence and stable ordering. Gate: `BLOCK + BLOCK_ITEM + RECIPE` produces
one ordered plan and invalid plans stop before runtime.

### Side effects

Pure in-memory planning and deterministic test artifacts only.

### Commit and rollback

Commit: `feat: add M1 composition planner`.

Rollback: revert Lot C; no Product/runtime migration has occurred.

### Later dependencies

D expands the ordered plan. F consumes the planner boundary.

## 11. Lot D - Requirement and Validation Expansion

### Objective

Expand each normalized capability instance into existing
`FabricRequirement` and `FabricValidationRequirement` values with complete
correlation and conservative support checks.

### Prerequisites

Lot C PASS; existing contract and CompletionGate behavior verified.

### Files

- EXTEND candidate: `src/pd_agent/fabric/planning.py` or the confirmed
  contract adapter location.
- EXTEND only when necessary: `src/pd_agent/core/contracts.py`.
- NEW/extend tests: `tests/unit/test_fabric_planning.py`,
  `tests/unit/test_fabric_task_contract.py` and
  `tests/unit/test_completion_gate.py`.
- REMOVE/RETIRE: none.

### Symbols

Requirement expansion, validation expansion, support declaration and contract
adapter.

### Behavior

- stable outcome-oriented requirement IDs;
- required/optional propagation;
- capability provenance;
- stable validation IDs and `requirement_ids` correlation;
- validation kind/spec normalization;
- deduplication and ordering;
- reject required unsupported validation;
- construct and validate the existing `FabricTaskContract`.

### Invariants

Representable is not executable or supported. No runtime first-match fix is
implemented; runtime validation 1-to-N remains early M4/M4.

### Tests and gate

Test multiple requirements, multiple validations, correlation, deduplication,
unsupported validation and contract roundtrip. Gate: a composed plan yields a
valid existing contract or an honest structured failure.

### Side effects

Source/test changes only; no Product Execution, provider, Minecraft or ledger.

### Commit and rollback

Commit: `feat: expand M1 task requirements`.

Rollback: revert Lot D and keep the planner contract-only. No persisted
runtime evidence may be invalidated.

### Later dependencies

E stores provenance; F uses the generated contract.

## 12. Lot E - ExecutionPlan Provenance and Persistence Compatibility

### Objective

Add the minimum optional plan provenance required for traceability,
reproducibility, evidence, diagnostics and reopen while preserving v0.9 data.

### Prerequisites

Lot D PASS; audit `ExecutionPlan`, `RunState`, RunStorage and hydration paths.

### Files

- EXTEND: `src/pd_agent/core/progress.py` (`ExecutionPlan` and roundtrip).
- Inspect/extend only if required: `src/pd_agent/core/state.py` and
  `src/pd_agent/reporting/` storage serializers.
- NEW/extend tests: `tests/unit/test_execution_plan_ledger.py`,
  `tests/unit/test_runtime_identity_injection.py` only if relevant, and a
  focused persistence roundtrip test.
- REMOVE/RETIRE: none.

### Symbols

Optional plan provenance, dependency context, capability/requirement mapping,
validation mapping and plan fingerprint.

### Behavior

Persist only normalized metadata. `from_dict` must default missing metadata
for v0.9 records. Do not persist executable commands, secrets, interpreter
alternatives or runtime state.

### Invariants

`ExecutionPlan` remains lightweight guidance, not a contract, ledger or
completion authority. Project/Task/Execution/Delivery identities remain
unchanged.

### Tests and gate

Test v0.9 plan roundtrip, new metadata roundtrip, omitted metadata, reopen,
unknown-field tolerance where current conventions allow it, and contract
identity preservation. Gate: old records hydrate unchanged and traceability is
available to evidence.

### Side effects

Only versioned serialization and tests. No migration or destructive rewrite.

### Commit and rollback

Commit: `feat: persist M1 plan provenance`.

Rollback: revert E; v0.9 records remain readable because metadata is optional.

### Later dependencies

F must use this persistence boundary; H verifies full compatibility.

## 13. Lot F - Product Interpreter and Server Core Migration

### Objective

Connect Product requests to the common interpreter/planner/contract path and
retire the permanent Server Core-only resolver architecture.

### Prerequisites

Lots A-E PASS; Product boundary audit; security review; Server Core regression
fixture available.

### Files

- EXTEND: `src/pd_agent/product/fabric.py`.
- Inspect/extend: `src/pd_agent/product/execution.py` and
  `src/pd_agent/product/application.py` only where the boundary requires it.
- EXTEND tests: `tests/unit/test_product_fabric_execution.py` and
  `tests/unit/test_product_execution.py`.
- NEW interpreter/planner Product-boundary tests only if no existing file fits.
- REMOVE/RETIRE: direct permanent Server Core contract generation after the
  common path passes; do not delete compatibility behavior prematurely.

### Symbols

Product request interpreter adapter, planner integration,
`ProductFabricTaskContractResolver`, `FabricProductExecutionRunner` and
`ExecutionService.start` boundary.

### Behavior

- invalid/unsupported planning returns safe structured failure;
- invalid plans do not start runtime or create a misleading supported execution
  when preflight can reject them;
- valid plans produce the existing contract and use existing runner;
- one Product Task/Execution remains the unit of a composed request;
- Server Core is translated through the common path.

### Invariants

No UI redesign, second resolver lifecycle, second runtime or Product model.
Existing execution/run identity and persistence behavior remain compatible.

### Tests and gate

Test unsupported requests, invalid plans, Product ownership, Server Core common
path, existing callers and execution creation boundary. Gate: historical
Server Core remains PASS and no invalid plan reaches `FabricNormalOrchestrator`.

### Side effects

Offline Product/unit tests only. No real execution or external calls.

### Commit and rollback

Commit: `feat: connect Product to M1 planner`.

Rollback: temporarily route Server Core through the compatibility adapter while
diagnosing, then complete retirement before M1 closure. The adapter is not an
accepted final architecture.

### Later dependencies

G exercises the common Product boundary; H verifies no hidden hardcode remains.

## 14. Lot G - Representative BLOCK + BLOCK_ITEM + RECIPE Integration

### Objective

Demonstrate M1 foundation with one request, at least three capabilities,
dependencies, multiple requirements/validations, existing runtime boundary,
evidence and CompletionGate, using parameters different from Server Core.

### Prerequisites

Lots A-F PASS; clean deterministic fixture; existing offline test harness and
fake provider/tool boundaries.

### Files

- Extend only confirmed planner/Product test modules.
- NEW candidate integration test: `tests/integration/test_m1_composed_fabric.py`.
- No production file unless a missing integration seam is demonstrated.
- REMOVE/RETIRE: no fixture source deletion.

### Symbols

Representative capability definitions, composed plan, generated contract,
existing FabricProductExecutionRunner and CompletionGate.

### Behavior

The offline scenario uses a distinct block/item/recipe parameter set and
demonstrates normalized ordering, dependency deduplication, generated
requirements, generated validations, evidence association and completion
evaluation. Provider and runtime boundaries use fakes where required.

### Invariants

One Product Task/Execution; no M3 tools, armor, entities, worldgen or advanced
assets; no false support claim for unavailable runtime validations.

### Tests and gate

Run the integration test, focused contract/ledger/Gate tests,
`tests/unit/test_product_fabric_execution.py` and
`tests/unit/test_productive_validation_pipeline.py`. Gate: AC1-AC10 and AC13
are evidenced offline, with deferred M4 limitations explicit.

### Side effects

Temporary test directories only, cleaned by test fixtures; no external
provider, Minecraft, Product Execution or ledger writes.

### Commit and rollback

Commit: `test: prove M1 composed Fabric vertical`.

Rollback: revert the integration test and any test-only fixture additions.

### Later dependencies

H maps the scenario to full closure evidence and regression.

## 15. Lot H - Regression, Security and Closure Preparation

### Objective

Close remaining M1 evidence without silently expanding to later milestones.

### Prerequisites

Lots A-G PASS and no open implementation discrepancy.

### Files

- Extend only files proven necessary by failing focused tests.
- Tests: existing contract, Product, planning, ledger, security, persistence,
  runtime boundary and completion suites.
- No new production architecture.
- REMOVE/RETIRE: temporary compatibility adapter if its removal condition is
  satisfied.

### Symbols

M1 acceptance evidence, security rejection paths, regression gate and closure
report.

### Behavior

Verify all M1 acceptance criteria, Server Core compatibility, v0.9 hydration,
security boundaries, unsupported validation honesty and no runtime entry for
invalid plans.

### Invariants

No M2/M3/M4/M5/M6 implementation, no live provider/Minecraft/benchmark,
CompletionGate remains sole authority.

### Tests and gate

Run all focused M1 tests, relevant v0.9 regressions, compileall and the full
Python suite. AC17 requires complete regression PASS. Run `git diff --check`
and verify diagnostics remain untouched.

### Side effects

Tests may use isolated temporary directories only. No live side effects.

### Commit and rollback

Each corrective change gets its own focused commit. Final closure commit is
`test: close M1 foundation validation` only if a legitimate closure artifact is
needed; do not create an empty commit.

Rollback: revert the smallest failing lot, preserve evidence, and do not patch
around a product defect without review.

### Later dependencies

M2, M3 and early M4 may consume the closed M1 contracts; no later work starts
automatically from this lot.

## 16. Error Propagation Plan

Expected planning failures originate in normalization, registry lookup,
dependency resolution, support checks or contract expansion.

Codes:

`INVALID_PARAMETERS`, `UNSUPPORTED_CAPABILITY`,
`UNRESOLVED_PREREQUISITE`, `INVALID_PREREQUISITE`, `DEPENDENCY_CYCLE`,
`INCOMPATIBLE_CAPABILITIES`, `UNSUPPORTED_VALIDATION`,
`INVALID_GENERATED_CONTRACT`.

They propagate as bounded structured planning results through Product. User
messages are safe and concise; diagnostics retain stable IDs and bounded detail.
Unexpected internal invariant failures may remain exceptions. No raw prompt,
provider traceback, secret or executable detail is exposed.

## 17. Persistence Plan

Persist only normalized plan schema/version, capability instance IDs and
parameters, dependency order, requirement/validation mappings and plan
fingerprint when needed for reproducibility, evidence, diagnostics or reopen.

Use existing `ExecutionPlan`/RunState/RunStorage paths. v0.9 plans with no new
metadata remain readable through optional defaults. No destructive migration,
ProductCatalog runtime state or duplicate evidence ledger.

## 18. Security Plan

Before runtime:

- interpreter output is treated as untrusted data;
- parameters and identifiers are schema-validated;
- paths remain relative and workspace-confined;
- SecurePathResolver and protected-path policy remain authoritative;
- ToolExecutor and step/tool limits remain mandatory;
- no free shell or implicit root expansion is introduced;
- Brain data cannot become executable authority;
- invalid/unsupported plans fail before execution.

Imported-project isolation remains M5.

## 19. Test Strategy

### UNIT

Capability schema, bounded parameters, normalization, defaults and stable IDs.

### CONTRACT

Requirement/validation expansion, correlations, contract fingerprint and
`to_dict/from_dict` compatibility.

### INTEGRATION

Dependencies, composition, ordering, deduplication and BLOCK + BLOCK_ITEM +
RECIPE plan generation.

### PRODUCT BOUNDARY

Resolver, Product ownership, invalid-plan preflight, Server Core common path
and one Task/Execution behavior.

### REGRESSION

Existing v0.9 Product, runtime, persistence, ledger, evidence and CompletionGate
tests.

### SECURITY

Malicious/path-like parameters, protected paths, root expansion, unsupported
validation and no-runtime-on-invalid-plan.

### FINAL SUITE

Focused suites, compileall, `git diff --check` and complete Python suite at H
closure. All tests are offline with fakes/mocks where needed. No live provider,
Minecraft, benchmark or Product Execution is used for M1 implementation tests.

## 20. Server Core Migration / Retirement

The migration starts only after the planner and contract expansion are stable.
The historical request may temporarily enter through a compatibility adapter,
but that adapter must delegate to the same general planner and must not own a
second contract-generation lifecycle.

Retirement condition: historical Server Core request passes through the common
interpreter/planner path, produces equivalent required outcomes, and Product
and regression tests pass. At closure, no direct permanent Server Core-only
resolver remains.

## 21. Validation Limitation / M4 Boundary

M1 can prove schema, representation, generation, correlation, support honesty,
offline planning and existing supported validation paths. It cannot claim that
the current runtime executes arbitrary N runtime validations because
`src/pd_agent/validation/runtime.py` still selects the first compatible
runtime requirement.

M1 tests must either use validation kinds supported by the existing boundary or
assert explicit `UNSUPPORTED_VALIDATION` before runtime. General 1-to-N runtime
execution, generalized probes and generalized ArtifactValidator remain early
M4/M4 work.

## 22. Commit Strategy

Use one focused commit per lot, in dependency order. Before each commit:

- inspect status and preserve diagnostics;
- run lot tests;
- run `git diff --check`;
- review scope and staged files.

Suggested sequence:

1. `feat: add M1 capability model`
2. `feat: add M1 capability registry`
3. `feat: add M1 composition planner`
4. `feat: expand M1 task requirements`
5. `feat: persist M1 plan provenance`
6. `feat: connect Product to M1 planner`
7. `test: prove M1 composed Fabric vertical`
8. focused regression/closure commits only when required.

Do not create an empty closure commit and do not amend unrelated commits.

## 23. Rollback Strategy

Each lot is independently revertible in reverse order H -> A.

F has the highest risk: retain a temporary compatibility adapter during
diagnosis, but remove it before closure once the common path is proven.

If a product defect appears, freeze evidence and stop rather than weakening a
gate. Persisted v0.9 records must remain readable after any rollback.

## 24. AC1-AC17 Evidence Matrix

| Criterion | Lot | Evidence/test | Expected |
|---|---|---|---|
| AC1 composed plan | C/G | planner + integration test | PASS |
| AC2 >=3 capabilities | G | composed vertical assertions | PASS |
| AC3 deterministic dependencies | B/C/G | normalization/order tests | PASS |
| AC4 shared dedup | B/C/G | shared prerequisite test | PASS |
| AC5 multiple requirements | D/G | contract assertions | PASS |
| AC6 correlated validations/trace | D/E/G | mapping and roundtrip tests | PASS |
| AC7 contract authority | D/F/G | runner boundary test | PASS |
| AC8 existing runtime | F/G | Product/orchestrator fake integration | PASS |
| AC9 ledger evidence correlation | E/G | ledger/Gate tests | PASS |
| AC10 CompletionGate | G/H | completion tests | PASS |
| AC11 Server Core regression | F/H | historical Product test | PASS |
| AC12 honest unsupported | B/D/F/H | error and preflight tests | PASS |
| AC13 invalid/cycle pre-runtime | C/F/H | adversarial planner tests | PASS |
| AC14 persistence/hydration | E/H | v0.9 roundtrip/reopen tests | PASS |
| AC15 security | A/C/F/H | security rejection tests | PASS |
| AC16 deterministic foundation | A/B/C/D | unit/contract suites | PASS |
| AC17 complete regression | H | full Python suite | PASS |

AC17 is a closure requirement, not an assumption made during earlier lots.

## 25. R96 Pre-Implementation Gate

R96 must re-audit:

- every target file and symbol against the repository;
- candidate new modules and package exports;
- Product execution creation/preflight semantics;
- `ExecutionPlan` serialization and RunStorage hydration;
- current Server Core callers and compatibility tests;
- validation support boundary and first-match limitation;
- security inheritance and path handling;
- no accidental M2/M3/M4/M5/M6 scope.

No implementation may start until R96 returns an accepted verdict and any
`PRE_IMPLEMENTATION_DISCREPANCY` is resolved by Direction.

## 26. Risks

- Overly broad schema or registry becomes an M3 catalog.
- Planner silently embeds Server Core hardcodes.
- Capability IDs or ordering become unstable.
- Shared prerequisite deduplication changes semantics.
- `ExecutionPlan` extension breaks v0.9 hydration.
- Product creates an Execution before rejecting an invalid plan.
- Required unsupported validation is falsely treated as supported.
- Temporary adapter survives as a second permanent resolver.
- Test fixture behavior is mistaken for productive generality.
- Early M4 runtime work is absorbed into M1.

Each risk is addressed by focused lots, deterministic tests, explicit gates,
backward-compatible persistence and R96 review.

## 27. IMP Verdict

`PD_AGENT_R95_M1_IMP_READY`

This IMP defines how M1 may be built after R96. It does not authorize code
changes, API calls, Minecraft, live benchmarks, Product Execution or ledger
writes.
