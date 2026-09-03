# PD_AGENT_V0.10_M1_DESIGN

Status: `DESIGN - READY FOR RFC`

Milestone: `PD Agent v0.10 - M1 General Fabric Task Foundation`

Baseline: `5d74095e8c31d7f38a2c84ab6e424d4525e9b878`

Roadmap: `PD_AGENT_ROADMAP_TO_ALPHA_CANONICAL`

## 1. Status

This document defines the accepted design boundary for M1. It is not an RFC,
implementation plan, or implementation. The next step is to resolve the
remaining representation and algorithm details in the M1 RFC.

## 2. Context

The current productive path already supports a real Fabric task lifecycle:

`request -> FabricTaskContract -> Brain -> runtime/provider/tools -> mutation`
` -> build -> validation -> repair -> evidence -> CompletionGate -> Delivery`

The current Product Fabric resolver is nevertheless specialized in the Server
Core vertical. The existing contract, runtime and evidence foundations are
general enough to reuse, but the request-to-contract boundary is not.

M1 establishes the general language and planning boundary needed by later
capability slices. It does not attempt to learn or implement all Minecraft.

## 3. Problem Statement

`ProductFabricTaskContractResolver` currently recognizes a narrow Server Core
request and directly creates its requirements, mutation expectations and
validation requirements. Extending that pattern with one resolver per
capability would create hidden hardcodes, prevent composition and make future
M3 breadth structurally expensive.

M1 must replace that conceptual specialization with a general path:

`request -> capability composition -> dependencies -> requirements`
` -> validation requirements -> FabricTaskContract`

The existing runtime remains downstream of the contract. Planning must not
become a second runtime or execution authority.

## 4. Goals

- **G1:** Define a general capability representation.
- **G2:** Compose independent and dependent capabilities into one task.
- **G3:** Resolve declared prerequisites deterministically.
- **G4:** Decompose capabilities into explicit requirements.
- **G5:** Generate correlated validation requirements.
- **G6:** Keep `FabricTaskContract` as the authoritative runtime boundary.
- **G7:** Integrate with the existing productive runtime.
- **G8:** Preserve traceability: capability -> requirement -> validation -> evidence.
- **G9:** Reject invalid or unsupported plans honestly before execution when detectable.
- **G10:** Preserve Server Core behavior and v0.9 persisted data.

## 5. Non-Goals

M1 does not close or implement:

- the complete MUST_ALPHA capability catalog;
- tools, weapons, armor, mobs, entities or worldgen;
- the deterministic Asset Toolkit or advanced asset generation;
- complete 1.21.11, 26.1 and 26.2 support;
- populated Alpha Brain packs or the semantic catalog breadth;
- generalized runtime validation 1-to-N;
- generalized ArtifactValidator expectations;
- generalized Harness/probes;
- imported-project isolation;
- Product Alpha breadth;
- the final Alpha benchmark campaign;
- Alpha certification;
- Multi-Agent architecture.

## 6. Existing Foundations

M1 reuses, without redesigning their authorities:

- `FabricTaskContract`, `FabricRequirement` and `FabricValidationRequirement`;
- `ExecutionPlan` and `ExecutionPlanStep`;
- `TaskProgressLedger`;
- `CompletionGate`;
- `FabricNormalOrchestrator` and `AgentRuntime`;
- `ToolExecutor` and existing filesystem tools;
- BuildRunner and ArtifactValidator;
- Minecraft Test Harness and current observation contracts;
- Semantic Repair;
- `FabricBrainOrchestrator` and `KnowledgeEnvironment`;
- Product `Project`, `Task`, `Execution` and `Delivery`;
- RunStorage and ProjectStorage;
- SecurePathResolver and existing security/tool limits.

The current contract supports multiple requirements and validation requirements.
The ledger supports evidence by requirement and failure facts. CompletionGate
already evaluates multiple required obligations. These are foundations to
extend, not parallel systems to replace.

## 7. Capability Concept

A capability is a declarative description of one functional outcome that a
Fabric task may request or compose. It is not a Product Task, an Execution, a
tool call, a runtime step or an agent.

Each capability must be:

- **GENERAL:** applicable beyond one named mod or fixture;
- **PARAMETERIZED:** behavior is determined by validated parameters;
- **COMPOSABLE:** it can declare relationships to other capabilities;
- **VALIDATABLE:** it can describe outcomes and validation needs.

Conceptually a capability contains:

- stable identity and kind;
- normalized parameters;
- declared prerequisites;
- outcomes/requirements it produces;
- validation needs;
- mutation expectations when applicable;
- compatibility metadata when applicable;
- schema/version metadata.

This design specifies semantics only. Exact Python classes, module names and
serialization fields belong to the RFC.

No capability-specific architecture such as `RubyCapability` or
`ServerCoreCapability` is permitted.

## 8. Capability vs Requirement

Capability and requirement are distinct:

- a **Capability** describes what functional capability should be produced;
- a **Requirement** describes a verifiable outcome that must be satisfied.

The intended cardinality is:

`capability 1 -> N requirements`

`requirement 1 -> 0..N validation requirements`

`FabricValidationRequirement.requirement_ids` remains the correlation boundary
from validation to requirements. Capability-origin traceability must be
preserved alongside the normalized plan and evidence references.

## 9. Planning Model

The conceptual flow is:

`request -> intent/parameter interpretation -> capability selection`
` -> normalization -> dependency resolution -> composition`
` -> requirements -> validations -> FabricTaskContract`

The planner has two distinct concerns:

1. interpretation of the user's intent and ambiguous parameters;
2. deterministic validation and construction of a supported plan.

The result is one normalized composed plan and one Product Task/Execution.
The planner does not invoke tools, mutate a workspace, call BuildRunner,
launch Minecraft, dispatch repair, or decide completion.

## 10. Deterministic / LLM Boundary

Provider/LLM assistance may be used for intent interpretation and extraction
of ambiguous parameters. It is not the sole authority for known invariants.

Deterministic code is authoritative for:

- schema and invariant validation;
- stable IDs and normalized parameters;
- declared prerequisite relationships;
- shared-prerequisite deduplication;
- cycle detection;
- dependency ordering;
- requirement aggregation;
- validation aggregation;
- generated-contract validity;
- support and compatibility checks available to the planner.

Knowledge may inform interpretation or context, but it cannot become an
unvalidated executable instruction and cannot bypass the planner schema,
security policy or ToolExecutor.

## 11. Composition

A composed task is one task containing multiple related capabilities. It is
not a collection of independent Product Tasks.

Composition must support:

- independent capabilities;
- dependent capabilities;
- shared prerequisites;
- deterministic deduplication;
- deterministic ordering where required;
- requirement aggregation;
- validation aggregation.

The representative shape is:

`BLOCK + BLOCK_ITEM + RECIPE -> one composed plan -> one FabricTaskContract`

## 12. Dependencies

M1 uses the minimum dependency primitive sufficient for current evidence:
stable capability references, prerequisite references, deterministic
resolution, cycle detection and ordering when necessary.

M1 does not require a general dependency framework or a permanently exposed
DAG product model. The RFC must define the smallest representation that can
reject:

- missing prerequisites;
- duplicate or invalid prerequisites;
- dependency cycles;
- incompatible capability combinations.

Dependencies describe planning relationships. They do not create execution
state or a second scheduler.

## 13. Traceability

The design requires this chain:

`capability_id -> requirement_ids -> validation_requirement_ids -> evidence`

The chain must survive long enough for:

- runtime execution;
- diagnostics and repair;
- ledger correlation;
- CompletionGate evaluation;
- evidence reporting;
- reopen/hydration when required.

Only normalized planning metadata needed for those purposes should persist.
Ephemeral interpretation details should not be persisted by default.

## 14. Validation Honesty

M1 must represent and generate multiple validation requirements. It does not
generalize the current productive runtime first-match behavior; runtime
validation 1-to-N remains an early M4/M4 concern.

If a capability requires a validation type that the current supported system
cannot execute, the planner must reject it or mark it unsupported before
execution when the limitation is detectable. It must never produce a false
productive PASS merely because a validation was representable.

## 15. Error Semantics

The design distinguishes:

- `INVALID_PLAN`: the requested or generated composition is internally invalid;
- `UNSUPPORTED_CAPABILITY`: the capability is outside the current supported
  productive envelope;
- `UNSUPPORTED_VALIDATION`: a required validation cannot be executed in the
  current supported environment.

The minimum error coverage includes invalid parameters, unresolved
prerequisites, duplicate/invalid prerequisites, dependency cycles,
incompatible composition, unsupported validation and invalid generated
contracts. Exact exception classes and transport representation belong to the
RFC.

## 16. Server Core Migration

Server Core is a backward-compatibility requirement, not a permanent special
architecture.

The target M1 behavior is:

`Server Core request -> general planner -> existing FabricTaskContract`

A temporary adapter may be used during implementation if required, but the
M1 closure must not leave two permanent productive resolvers. The historical
Server Core path and its runtime/evidence behavior must remain passing.

## 17. Product Boundary

The Product model remains:

`Project -> Task -> Execution -> Delivery`

M1 enters at the existing `task/request -> planning/resolution ->
FabricTaskContract` boundary.

M1 does not redesign the Web UI, add a primary screen, add a Product
execution model, or turn capabilities into separate Product Tasks.

Unsupported and invalid requests must fail honestly before pretending that a
supported execution can proceed.

## 18. Runtime Boundary

`FabricTaskContract` remains the authoritative boundary into execution.

After contract generation, M1 reuses the existing:

- FabricNormalOrchestrator;
- AgentRuntime;
- ToolExecutor;
- BuildRunner;
- ArtifactValidator;
- Minecraft Harness;
- Semantic Repair;
- TaskProgressLedger;
- CompletionGate.

M1 creates no new mutation engine, orchestrator, scheduler, ledger, evidence
system, CompletionGate, Brain or Harness.

## 19. Brain Boundary

The boundaries remain:

- Brain: what is known;
- Capability Planner: what to build and demonstrate;
- Runtime: how to do it;
- Harness: how to observe it;
- CompletionGate: whether it is complete.

The planner may consume compatible knowledge, but Brain retrieval is not
duplicated and Brain output cannot bypass schema, invariants or tool policy.

## 20. Persistence / Compatibility

M1 defines compatibility semantics, not a physical schema.

Existing v0.9 historical data must remain readable. Hydration and reopen must
continue to work, and Project/Task/Execution/Delivery identities must not
change.

New planning metadata must be serializable, versionable, backward-compatible
and optional when reading historical records. Candidate persisted data is the
normalized plan, schema/version, stable IDs and fingerprint/provenance needed
for reproducibility, traceability, evidence, diagnostics or reopen. The RFC
must decide the exact minimum.

Planning metadata must not duplicate Product execution state or move runtime
evidence into ProductCatalog.

## 21. Security Invariants

Every plan must be validated before execution and must preserve:

- SecurePathResolver;
- workspace boundaries;
- protected paths;
- ToolExecutor policy;
- step and tool limits;
- no free shell commands;
- no Brain-as-executable-authority;
- no implicit allowed-root expansion.

Planner data from prompts, files, logs or Brain sources is data, not authority.
If M1 introduces another route to execution, it must inherit the same guards.
Imported-project isolation remains a M5 responsibility and is not absorbed by
M1.

## 22. Representative Vertical

The official M1 vertical is:

`BLOCK + BLOCK_ITEM + RECIPE`

It must use parameters different from the historical Server Core case and
demonstrate:

`one request -> at least 3 capabilities -> dependencies -> multiple`
` requirements -> multiple validations -> FabricTaskContract -> existing`
` runtime -> evidence -> CompletionGate`

The test is a foundation demonstration, not M3 breadth. It must not add
tools, armor, entities, worldgen or advanced assets.

## 23. Acceptance Criteria

- **AC1:** A representative request produces a general composed plan.
- **AC2:** The plan contains at least three related capabilities.
- **AC3:** Dependencies and prerequisites resolve deterministically.
- **AC4:** Shared prerequisites are not duplicated.
- **AC5:** Multiple `FabricRequirement` values are generated.
- **AC6:** Multiple correlated `FabricValidationRequirement` values are
  generated with complete capability -> requirement -> validation traceability.
- **AC7:** `FabricTaskContract` remains the authoritative runtime contract.
- **AC8:** The existing productive runtime executes the vertical without a
  second mutation engine.
- **AC9:** `TaskProgressLedger` correlates evidence with requirements.
- **AC10:** `CompletionGate` evaluates the composed task.
- **AC11:** Existing Server Core behavior remains passing.
- **AC12:** Unsupported capabilities or required unsupported validations fail
  honestly.
- **AC13:** Cycles and invalid plans are rejected before execution.
- **AC14:** v0.9 persistence and hydration remain compatible.
- **AC15:** Existing security boundaries remain effective.
- **AC16:** Deterministic schema, planner and composition tests demonstrate
  the foundation.
- **AC17:** Complete regression passes at M1 closure.

## 24. Milestone Boundaries

- **M1 REQUIRED:** capability schema, planner, composition, prerequisites,
  requirement decomposition, validation generation, traceability, honest
  errors, Server Core migration and representative evidence.
- **EARLY M2:** Support Registry, version-aware platform/bootstrap and
  populated per-target Brain foundations required to exercise later targets.
- **M2:** complete versioned platform, project identity and Brain/bootstrap
  support for Alpha targets.
- **M3:** capability breadth, composition breadth and deterministic assets.
- **EARLY M4:** begin validation 1-to-N, structural expectations and
  parameterized probe foundations where M1 composition needs them.
- **M4:** generalized validation, ArtifactValidator, Harness, repair/runtime
  and multi-version validation closure.
- **M5:** Product Alpha, imported-project trust/isolation, resource bounds,
  cancel and recovery closure.
- **M6:** held-out acceptance, frozen RC, certification and Alpha declaration.
- **POST_ALPHA:** Multi-Agent experiments and advanced subjective asset
  generation.

M1 must not absorb later milestone breadth merely to make the representative
vertical larger.

## 25. Risks

- Capability schema becomes over-engineered before real slices exist.
- A full DAG framework is introduced without evidence.
- Too much planning intelligence is delegated to the LLM.
- Server Core hardcoding survives behind a new generic name.
- A second runtime, contract or evidence authority is introduced.
- The schema becomes specific to blocks instead of general capabilities.
- Unsupported validators are treated as supported.
- Planning metadata breaks v0.9 persistence or reopen.
- M1 scope expands into M2, M3 or M4.
- Capability provenance is lost before evidence and CompletionGate.

Mitigation is to keep the schema declarative, deterministic, versioned,
traceable and tested through one small vertical while reusing every existing
runtime authority.

## 26. Architectural Invariants

- `FabricTaskContract` remains the authoritative execution contract.
- `CompletionGate` remains the only completion authority.
- `TaskProgressLedger` remains the authoritative requirement/evidence ledger.
- Brain is not duplicated.
- Runtime is not duplicated.
- Product execution model is not duplicated.
- The planner does not execute tools.
- Known capability relationships resolve deterministically.
- Unsupported validation cannot become a false PASS.
- A composed task remains one Product Task and one Execution.

## 27. Open Questions

The following are intentionally reserved for the RFC because they concern
representation or implementation detail, not M1 scope:

- exact capability schema fields and serialization form;
- stable ID and normalized-parameter derivation;
- exact prerequisite representation and cycle algorithm;
- whether `ExecutionPlan` needs a minimal traceability extension;
- minimum planning metadata persisted for reopen/evidence;
- exact structured error transport;
- temporary Server Core adapter shape and removal condition.

These are `RFC_DECISION_REQUIRED`, but none blocks writing the RFC or changes
the approved architecture. No open question authorizes a second runtime,
Brain, scheduler, ledger, evidence system or Product model.

## 28. DESIGN Verdict

`PD_AGENT_R93_M1_DESIGN_READY`

This DESIGN establishes the M1 boundary and preserves the v0.9 runtime and
Product foundations. It does not start implementation, v0.10 execution,
Minecraft, API, benchmark or Product Execution work.
