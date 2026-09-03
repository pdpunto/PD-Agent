# PD_AGENT_V0.10_M1_RFC

Status: `RFC - READY FOR IMP`

Milestone: `PD Agent v0.10 - M1 General Fabric Task Foundation`

Baseline: `e3c11eca8b5fe388110fb51c2afeaea314a76f1d`

Design authority: `PD_AGENT_V0.10_M1_DESIGN`

## 1. Status

This RFC fixes the technical decisions needed to implement M1. It does not
implement them and does not define M2, M3, M4, M5 or M6 work.

## 2. Authorities

In descending authority:

1. `docs/roadmap/PD_AGENT_ROADMAP_TO_ALPHA.md`;
2. `docs/design/PD_AGENT_V0.10_M1_GENERAL_FABRIC_TASK_FOUNDATION_DESIGN.md`;
3. R91 Pre-Design Reality Audit;
4. R92 Exact Requirements Definition;
5. the current repository and its accepted v0.9 contracts.

The RFC implements the DESIGN conceptually and does not replace existing
runtime, Brain, evidence, Product or completion authorities.

## 3. Architecture Overview

The M1 flow is:

`Product Task/request -> Request Interpreter -> Capability Selection`
` -> Normalized Capability Plan -> Dependency Resolution`
` -> Requirement Expansion -> Validation Expansion -> FabricTaskContract`
` -> existing FabricProductExecutionRunner -> FabricNormalOrchestrator`
` -> existing runtime`

Ownership is intentionally separated:

- Request Interpreter converts user intent into untrusted candidate data.
- Capability Registry owns declarative M1 definitions.
- Planner validates, normalizes, resolves, composes and expands candidates.
- `FabricTaskContract` is the validated execution boundary.
- Existing Product/runtime components execute the contract.
- Existing ledger, evidence and CompletionGate remain authoritative downstream.

The planner never executes tools or provider calls as part of planning.

## 4. Components

### Reuse

Reuse `FabricTaskContract`, `FabricRequirement`,
`FabricValidationRequirement`, `ExecutionPlan`, `ExecutionPlanStep`,
`TaskProgressLedger`, `CompletionGate`, `FabricNormalOrchestrator`,
`AgentRuntime`, `ToolExecutor`, BuildRunner, ArtifactValidator, Minecraft
Harness, Semantic Repair, FabricBrainOrchestrator, KnowledgeEnvironment,
Product Project/Task/Execution/Delivery, RunStorage, ProjectStorage and
SecurePathResolver.

### Extend

Extend the Product request-to-contract boundary, `ExecutionPlan` provenance,
the existing contract generation path and validation support checks.

### New

Add only a declarative Capability Registry, capability instances, a request
interpreter boundary, normalized planning and composition logic, and the
small structured planning result/error boundary required to connect them.

### Retire/transform

The Server Core-specific Product resolver must become a compatibility adapter
or be transformed into a general planner definition. It must not remain a
second permanent resolver architecture.

## 5. Capability Schema

M1 uses two related concepts because they have different lifetimes:

- `CapabilityDefinition`: reusable declarative definition for a capability
  kind, its parameter schema, prerequisites and expansion rules.
- `CapabilityInstance`: one normalized occurrence of a definition in a user
  plan, with concrete parameters and stable identity.

A definition contains conceptually:

- definition/kind ID;
- schema version;
- parameter schema and defaults;
- prerequisite declarations;
- requirement specifications;
- validation specifications;
- mutation expectation specifications when applicable;
- compatibility/support declaration at the limited M1 boundary.

An instance contains:

- definition ID;
- normalized parameters;
- instance ID;
- bound prerequisite references;
- expansion provenance.

Definitions are data and declarative expansion specifications. They are not
Product Tasks, agents, runtime states or arbitrary executable prompt content.

## 6. Capability IDs / Normalization

IDs are generated from canonical data, never from raw LLM text alone.

The canonical identity inputs are:

- a fixed namespace/prefix for the ID kind;
- schema version;
- capability definition ID;
- canonical normalized parameters;
- explicit parent/request scope where required for local uniqueness.

The serialized canonical form uses sorted mapping keys, normalized strings,
stable list ordering where order is semantic, and deterministic numeric/string
representations. A collision-resistant digest is used as the identity suffix.

Capability definition IDs are stable registry IDs. Instance IDs are stable for
the same plan scope, definition and normalized parameters. Requirement and
validation IDs are derived from the instance ID plus stable local output IDs.

Accidental prompt ordering must not change IDs. If two semantically equal
instances normalize to the same identity, they are eligible for
deduplication. Different semantic parameters must not deduplicate.

Allowed parameter values are JSON-compatible bounded values: strings,
booleans, finite numbers, lists and mappings. Keys and identifiers are
normalized and validated. Namespace and name rules are capability-specific
schema constraints, not free shell/path authority.

## 7. Registry

M1 introduces a small immutable-in-use Capability Registry containing
declarative definitions and expansion metadata.

It is distinct from the M2 Version/Support Registry:

- M1 registry answers: what capability kinds exist and how they expand;
- M2 registry answers: which target versions/environments support them and
  which platform resources prove that support.

M1 may expose only a minimal support declaration sufficient to reject a
required unsupported validation. It must not become a version matrix,
bootstrap catalog or populated Alpha capability catalog.

Registry lookup is deterministic. Missing definitions produce
`UNSUPPORTED_CAPABILITY`.

## 8. Request Interpreter

The interpreter boundary accepts a task request plus optional compatible
context and returns candidate capability data and parameter candidates.

Its output is untrusted data until the planner validates it. It may be:

- a deterministic adapter for known request forms;
- a future provider/LLM adapter for broader intent interpretation.

The interpreter cannot create an Execution, invoke tools, select arbitrary
paths, emit a final contract, or claim support. It has no authority over
invariants, prerequisite relationships or validation support.

## 9. Planner

The planner accepts a request/candidate set, registry state, environment
context and planning policy. It returns either a normalized composed plan plus
`FabricTaskContract`, or a structured planning failure.

The deterministic stages are:

1. validate candidate shape;
2. resolve definition IDs;
3. normalize parameters and defaults;
4. instantiate capabilities;
5. expand and validate prerequisites;
6. deduplicate shared instances;
7. detect cycles and incompatible combinations;
8. order instances deterministically;
9. expand requirements;
10. expand validation requirements;
11. verify required validation support;
12. build and validate the existing `FabricTaskContract`;
13. create the execution-facing plan/provenance.

After interpretation, equal inputs and equal registry/environment state must
produce equal normalized plans and contract identities.

## 10. Dependency Resolution

Prerequisites are explicit references to capability definitions or instances,
with parameter bindings only where a definition declares them. Resolution uses
a temporary in-memory directed graph; no persistent generic DAG framework is
introduced.

The resolver rejects missing references, duplicate prerequisite declarations,
invalid bindings, incompatible composition and cycles.

Shared prerequisites are keyed by canonical capability identity and reused
within one normalized plan. They are not copied merely because multiple
capabilities reference them.

## 11. Requirement Generation

Each capability instance expands into zero or more stable requirement outputs.
Each output has a stable local specification, outcome-oriented description and
required/optional policy.

The planner derives a `FabricRequirement` ID from the capability instance ID
and output ID. It aggregates identical requirements only when their canonical
identity and semantics match.

Requirements must not contain arbitrary executable instructions. Mutation
expectations remain declarative and are adapted to the existing contract.

Requirement order follows deterministic capability order and stable local
output order.

## 12. Validation Generation

Validation specifications expand into the existing
`FabricValidationRequirement` with:

- stable validation ID;
- correlated `requirement_ids`;
- normalized validation kind;
- data-only spec;
- required/optional policy;
- capability-origin provenance.

Validation outputs are deduplicated only when their canonical kind, spec and
correlations are identical. Ordering follows the normalized plan.

The planner performs an explicit support check before returning a productive
contract. `Representable` is not automatically `Executable`, and
`Executable` is not automatically `Supported`.

The current runtime first-match limitation for runtime requirements remains an
early M4/M4 concern. M1 can generate N validations but must reject a required
validation that cannot be executed under the current supported boundary.

## 13. Traceability

The canonical chain is:

`capability_instance_id -> requirement_ids`
` -> validation_requirement_ids -> evidence_refs`

The plan carries capability and dependency provenance. Requirements and
validations carry their existing stable IDs and correlations. The ledger
continues to own evidence association; M1 does not create another evidence
store.

Traceability is available to runtime diagnostics, repair, CompletionGate,
reports and reopen/hydration when the normalized plan is persisted.

## 14. FabricTaskContract Integration

M1 does not introduce a breaking change to `FabricTaskContract`.

The generated contract continues to contain the existing requirements,
validation requirements, capabilities, criteria, knowledge signals, mutation
expectations and environment constraints. Existing v0.9 `to_dict/from_dict`
records remain readable.

Capability-origin provenance is carried by the normalized execution plan and
by stable requirement/validation correlations. If future evidence proves that
contract metadata itself is necessary, it must be optional, versioned and
backward-compatible; this RFC does not require a second contract type.

## 15. ExecutionPlan

`ExecutionPlan` requires a minimal backward-compatible extension for planning
provenance and dependency context. It remains lightweight intent guidance and
never becomes a completion authority or task contract.

The extension may carry normalized capability instance IDs, dependency edges,
capability-to-requirement mappings, validation mappings and a plan fingerprint.
It must be optional when reading v0.9 plans and must not carry executable
commands, provider secrets or mutable runtime state.

Existing step status semantics remain unchanged. The planner's plan is created
before runtime and is persisted through the existing RunState/RunStorage path
where that path already persists execution plans.

## 16. Server Core Migration

The final flow is:

`Server Core request -> same interpreter/planner/registry boundary`
` -> FabricTaskContract -> existing runtime`

During implementation, a narrowly scoped adapter may translate the historical
Server Core request into candidate capabilities. It may not directly own a
second contract-generation lifecycle. Its removal condition is that the
general planner accepts the historical Server Core request and its regression
tests pass through the same path.

## 17. Product Integration

The Product model remains:

`Project -> Task -> Execution -> Delivery`

`ProductFabricTaskContractResolver` is extended or transformed to delegate to
the planner. `FabricProductExecutionRunner` keeps its existing contract and
run identity checks. `ExecutionService` remains the execution lifecycle owner.

Planning should complete its validation before a Product Execution is created
when the Product boundary permits preflight. Invalid or unsupported plans
must return a safe structured failure and must not start the runtime. Existing
v0.9 callers and persisted records remain compatible.

No Web UI redesign, new primary screen or second Product execution model is
introduced.

## 18. Error Model

Expected planning failures use a small machine-readable result boundary with:

- code;
- user-safe message;
- bounded diagnostic detail;
- capability/requirement references when safe;
- persistence/evidence policy where applicable.

Required codes:

- `INVALID_PARAMETERS`;
- `UNSUPPORTED_CAPABILITY`;
- `UNRESOLVED_PREREQUISITE`;
- `INVALID_PREREQUISITE`;
- `DEPENDENCY_CYCLE`;
- `INCOMPATIBLE_CAPABILITIES`;
- `UNSUPPORTED_VALIDATION`;
- `INVALID_GENERATED_CONTRACT`.

Expected user/planning errors are result values at the Product boundary;
internal programming invariant violations may remain exceptions. No raw
provider traceback, secret or arbitrary prompt content is exposed as a user
message.

## 19. Persistence

Persist only normalized planning data needed for reproducibility,
traceability, diagnostics, evidence or reopen:

- plan schema/version;
- normalized capability instance IDs and parameters;
- dependency references/order;
- requirement and validation mappings;
- plan fingerprint.

Do not persist ephemeral interpretation alternatives, hidden provider state or
runtime state in the plan. v0.9 records without planning metadata remain
readable through optional defaults. Product identity fields do not change.

## 20. Fingerprint / Currentness

The generated `FabricTaskContract` fingerprint remains the authoritative
contract identity for requirement and validation semantics. A semantic change
to normalized capabilities, parameters, requirements or validations therefore
produces a different contract identity and cannot silently reuse evidence from
the old plan.

The plan fingerprint is additional provenance, not a replacement for contract
identity. Existing currentness and reconciliation rules remain authoritative;
M1 does not redesign them.

## 21. Security

Trust boundaries are:

`request/interpreter output = untrusted data`

`normalized planner output = validated plan`

`FabricTaskContract = validated execution contract`

All plans must pass schema, support, dependency and security validation before
runtime. SecurePathResolver, workspace boundaries, protected paths,
ToolExecutor policy, step/tool limits, no free shell and no implicit root
expansion remain mandatory. Brain output cannot become executable authority.

Imported-project technical isolation remains M5. M1 must not weaken it or
claim to solve it.

## 22. Validation Support Boundary

M1 uses a minimal support declaration associated with a capability/validation
definition to answer whether a required validation is supported by the current
productive boundary.

This is not the M2 Support Registry and does not claim multi-version support.
The check must be conservative: absent or unknown support is unsupported for a
required validation. A representable `REGISTRY_ENTRY_PRESENT` or other kind
cannot produce a productive execution unless the relevant executor/probe is
available and compatible.

General runtime 1-to-N execution and generalized probes remain early M4/M4.

## 23. Brain Interaction

The interpreter may receive compatible context from the existing Brain pipeline
when interpretation needs it. The deterministic planner does not use
retrieval to decide declared schema invariants or dependency relationships.

No retrieval pipeline, pack/index, KnowledgeEnvironment or Brain orchestration
is duplicated. Compatibility filtering and provenance remain Brain authority.

## 24. Concurrency / Determinism

The planner is pure/stateless for the same normalized input, registry state and
environment/support context. It owns no scheduler, cache, worker, ledger or
execution lock.

Repeated planning must produce the same IDs, order, requirements, validations,
contract fingerprint and plan fingerprint. Any future cache is an optimization
only and cannot replace validation.

## 25. Representative Vertical

M1 defines three general capability definitions:

- `BLOCK`: parameters identify a block and its functional outcome; produces a
  block requirement and its applicable validation needs.
- `BLOCK_ITEM`: parameters identify the block it represents; prerequisite is a
  compatible `BLOCK` instance; produces the item outcome and validation needs.
- `RECIPE`: parameters identify output and ingredients; prerequisite/output
  references bind it to the composed block/item result; produces the recipe
  outcome and validation needs.

The future test uses names and parameters different from historical Server
Core and proves one request, three instances, shared/dependent prerequisites,
multiple requirements, multiple validations, one contract, existing runtime,
evidence and CompletionGate. It does not add tools, armor, entities, worldgen
or advanced assets.

## 26. Test Architecture

The future implementation must include offline tests for:

1. schema validity and bounded parameters;
2. normalization and defaults;
3. stable IDs and order independence;
4. prerequisite expansion and missing references;
5. shared-prerequisite deduplication;
6. cycle rejection;
7. deterministic ordering;
8. unsupported capability;
9. unsupported validation;
10. requirement generation and capability provenance;
11. validation correlation;
12. contract roundtrip and v0.9 compatibility;
13. Server Core regression through the common path;
14. BLOCK + BLOCK_ITEM + RECIPE integration;
15. Ledger and CompletionGate evidence correlation;
16. security rejection paths;
17. invalid plans rejected before runtime/Product Execution.

No live provider, Minecraft, benchmark or Product Execution is required to
implement these tests.

## 27. Implementation Boundaries

### REUSE

Existing contract, plan, ledger, runtime, Brain, build, artifact, Harness,
repair, Product and security authorities.

### EXTEND

Product resolver boundary, `ExecutionPlan` optional provenance, support check
and existing contract generation integration.

### NEW

Declarative capability definitions/instances, small M1 registry, interpreter
boundary, normalized planner, dependency resolution and structured planning
result/error boundary.

### REMOVE/RETIRE

Retire the permanent Server Core-only contract-generation path after the
general planner handles the historical request and its regression evidence
passes. Do not remove the compatibility behavior before that condition.

No new runtime, scheduler, mutation engine, ledger, evidence system, Brain,
Harness, Product model or Multi-Agent framework is permitted.

## 28. RFC Decisions D1-D22

- **D1 - Definition vs Instance:** both are required; definition is reusable
  registry data, instance is normalized plan occurrence.
- **D2 - Schema:** declarative definition plus normalized instance containing
  kind, parameters, prerequisites, outcomes, validations, mutation
  expectations, compatibility metadata and schema version.
- **D3 - IDs:** canonical namespace/version/data inputs with collision-resistant
  digest; no raw LLM text identity.
- **D4 - Normalization:** bounded JSON values, normalized strings/identifiers,
  sorted mapping keys, semantic list ordering and explicit defaults.
- **D5 - Registry:** small deterministic M1 capability registry; M2 owns the
  version/support registry.
- **D6 - Interpreter:** untrusted candidate data boundary; deterministic or
  provider-backed implementations are permitted, but no execution authority.
- **D7 - Planner:** pure deterministic normalization, dependency resolution,
  composition and contract expansion after interpretation.
- **D8 - Dependencies:** explicit prerequisite references with optional schema-
  declared parameter bindings; temporary graph only.
- **D9 - Algorithm:** cycle detection followed by stable topological ordering;
  stable capability ID is the tie-breaker.
- **D10 - Requirements:** derive stable IDs from instance/output IDs, preserve
  `FabricRequirement`, aggregate only semantically identical outcomes.
- **D11 - Validations:** derive correlated `FabricValidationRequirement` values,
  deduplicate identical specs and reject required unsupported validations.
- **D12 - Traceability:** store mappings in normalized `ExecutionPlan`
  provenance and preserve existing requirement/validation/evidence IDs.
- **D13 - Contract:** no breaking `FabricTaskContract` change; existing fields
  and roundtrip remain authoritative.
- **D14 - ExecutionPlan:** yes, minimal optional provenance/dependency context;
  it remains non-authoritative guidance.
- **D15 - Errors:** structured machine-readable planning result at Product
  boundary; exceptions remain for unexpected internal invariant violations.
- **D16 - Persistence:** persist only normalized plan metadata required for
  reproducibility, traceability, diagnostics, evidence or reopen.
- **D17 - Currentness:** semantic contract changes change contract fingerprint;
  plan fingerprint supplements but does not replace currentness authority.
- **D18 - Server Core:** common planner path is the target; temporary adapter
  is allowed only until common-path regression passes.
- **D19 - Product:** integrate at task/request resolution; preserve Project ->
  Task -> Execution -> Delivery and avoid runtime start for invalid plans.
- **D20 - Security:** validate plan before execution and preserve all existing
  path, workspace, tool and resource guards.
- **D21 - Brain:** optional compatible context for interpretation; no duplicate
  retrieval or Brain authority over deterministic invariants.
- **D22 - Vertical:** general BLOCK + BLOCK_ITEM + RECIPE composition with
  parameters distinct from Server Core and one Product Task/Execution.

## 29. Risks / Failure Modes

- Schema overengineering before real vertical slices.
- Accidental capability-specific hardcoding behind generic names.
- LLM output bypassing deterministic validation.
- Unstable IDs or ordering causing evidence invalidation.
- Incorrect shared-prerequisite deduplication.
- DAG scope expanding beyond M1 needs.
- Contract/plan provenance lost before evidence.
- v0.9 hydration or currentness regressions.
- Unsupported validation incorrectly reported as supported.
- Product execution created before invalid-plan rejection.
- M1 absorbing M2/M3/M4 scope.

The IMP must mitigate these with small declarative boundaries, offline
deterministic tests, common-path Server Core regression and explicit scope
checks.

## 30. RFC Invariants

1. `FabricTaskContract` is authoritative for execution.
2. `TaskProgressLedger` is authoritative for requirement/evidence facts.
3. `CompletionGate` is the sole completion authority.
4. One composed request creates one Product Task/Execution.
5. Planner executes no tools.
6. Known invariants are deterministic after interpretation.
7. No second runtime.
8. No second Brain.
9. No second evidence system.
10. Required unsupported validation cannot become a false PASS.
11. v0.9 backward compatibility is preserved.
12. Existing security guards remain effective.

## 31. RFC Verdict

`PD_AGENT_R94_M1_RFC_READY`

This RFC resolves the required M1 technical decisions without implementing
M1, starting v0.10 execution, writing an IMP, calling APIs, launching
Minecraft, running benchmarks or starting Product Execution.
