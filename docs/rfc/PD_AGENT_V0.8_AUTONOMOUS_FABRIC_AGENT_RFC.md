# PD Agent v0.8 - Autonomous Fabric Agent Foundation RFC

Status: RFC APPROVED
Design authority: `docs/design/PD_AGENT_V0.8_AUTONOMOUS_FABRIC_AGENT_DESIGN.md`
Design status: DESIGN ACCEPTED
Milestone: PD Agent v0.8 - Autonomous Fabric Agent Foundation

## 1. Purpose and Boundary

This RFC defines HOW the v0.8 design operates. It is an incremental technical
architecture over the v0.7 capabilities and existing runtime. It does not
authorize implementation, live provider calls, Minecraft execution, or a
benchmark.

The authoritative flow is:

`NaturalRequirement -> TaskContractBuilder/analysis -> FabricTaskContract`
`-> ExecutionPlan -> TaskProgressLedger -> normal Fabric orchestration`
`-> existing AgentRuntime -> CompletionGate -> deliverable/evidence`.

`AgentRuntime`, `RunController`, `RunState`, `RunStorage`, `ToolExecutor`,
`GradleBuildRunner`, `ArtifactValidator`, Semantic Repair, Minecraft Test
Harness, `KnowledgeService`, and the v0.7 Brain remain the foundation. The new
architecture is a thin layer of models, adapters, and orchestration.

## 2. Architectural Invariants

- `RunState` remains the only operational state machine.
- There is no second runtime, DAG, graph engine, planner service, Brain,
  Harness, or database.
- Completion is determined by objective evidence and `CompletionGate`, never by
  an LLM or reporting alone.
- Knowledge is non-executable context and remains subject to v0.7 integrity,
  compatibility, security, and no-leakage gates.
- Failure history is durable and is never deleted when repaired.
- Evidence used for completion must be current for the source and contract.
- Benchmark-specific data enters product orchestration through an adapter.

## 3. Component Ownership

### 3.1 TaskContractBuilder

Accepts a natural requirement and project analysis, validates the result, and
produces an immutable `FabricTaskContract`. It may consume an approved source
adapter, but it does not let model-generated implementation details become
authority.

### 3.2 FabricTaskContract

Owns the stable WHAT: identity, requirements, capabilities, completion rules,
validation obligations, knowledge signals, derivable mutation expectations,
and environment constraints.

### 3.3 ExecutionPlan

Owns a small ordered sequence of coarse intent. It is guidance for orchestration
and may be revised when facts change. It cannot mark a requirement satisfied or
complete a run.

### 3.4 TaskProgressLedger

Owns requirement-related facts: satisfied and pending requirements, failure
history, evidence references, validation results, currentness, and optional
knowledge correlation. It is persisted with or referenced by `RunState` and
does not duplicate heavy evidence.

### 3.5 Normal Fabric Orchestrator

Owns the product flow between contract, plan, ledger, Brain, editing, build,
repair, artifact validation, runtime validation, and CompletionGate. It
coordinates existing components; it does not replace `AgentRuntime` or make
the operational state transitions that belong to `RunController`/`RunState`.

### 3.6 CompletionGate

Owns the deterministic final decision from contract, ledger, RunState, and
current evidence. It is stateless and does not mutate the lifecycle.

### 3.7 Existing Components

`AgentRuntime` executes provider/tool turns, `RunController` and `RunState`
own operational lifecycle, `RunStorage` persists evidence, build and artifact
components produce objective build facts, Brain supplies knowledge context,
and the Harness supplies runtime observations. None of these components may
unilaterally declare completion.

## 4. FabricTaskContract

### 4.1 Shape

The contract contains:

- `task_id`;
- `revision` and canonical `fingerprint`;
- `goal`;
- `requirements[]`;
- `required_capabilities[]`;
- `completion_criteria[]`;
- `validation_requirements[]`;
- `knowledge_signals[]`;
- `mutation_expectations[]` when derivable;
- `environment_constraints`.

Each requirement contains at least `requirement_id`, `description`, and
`required`. IDs are stable within the contract revision. A requirement may
reference validation obligations, but it cannot contain an untrusted solution
or executable instruction.

### 4.2 Identity, Schema, and Revision

Serialization uses canonical JSON-safe data with deterministic field ordering,
normalization, and an explicit schema version. The fingerprint is computed
from canonical contract content, excluding transport metadata such as
timestamps. The identity is `(task_id, revision, fingerprint)`.

Contracts are immutable after run start. A revision creates a new contract
identity; it does not silently mutate historical evidence. On reopen/resume,
the persisted identity must match the supplied contract and project binding.
Mismatch is a fail-closed incompatibility requiring a new controlled run or
explicit migration policy; it is not repaired by the provider.

### 4.3 Validation

The schema rejects missing required fields, duplicate requirement IDs,
malformed validation references, unknown unsafe control payloads, and values
outside the JSON-safe contract domain. It does not embed private Brain types.

## 5. ValidationRequirement and Evidence Correlation

A `ValidationRequirement` expresses an obligation with an ID, linked
`requirement_id[]`, kind, required/optional status, and a typed validation
specification. Supported kinds include build, artifact, Minecraft/runtime
observation or action, and non-runtime requirement checks.

The deterministic correlation chain is:

`requirement_id -> validation_requirement_id -> validation_spec`
`-> observation/action or validator result -> evidence reference`.

The adapter maps build obligations to existing build/artifact validators and
runtime obligations to `MinecraftTestSpec`, `MinecraftTestRunner`,
`ObservationRequest/Result`, and `ValidationResult/Violation`. Free-form LLM
text cannot satisfy a validation requirement. Evidence must identify the
contract revision and source/artifact identity it validates.

## 6. ExecutionPlan

The plan is an ordered list of coarse steps, each with stable step identity,
intent, relevant requirement IDs, and disposition. It may be revised after
discovery or failure, with revisions persisted as evidence. It is not a DAG,
scheduler, or completion authority.

The legacy `current_plan` field is a compatibility projection of the current
ordered plan, not a second source of truth. New orchestration writes the
structured plan and may render `current_plan` for existing callers. On
readback, the structured plan is authoritative when present; legacy text is
preserved for compatibility and cannot override the structured plan.

## 7. TaskProgressLedger

The ledger stores lightweight durable facts:

- contract and requirement identity references;
- `satisfied_requirement_ids`;
- derived pending requirement IDs;
- evidence references by requirement;
- build, artifact, runtime, and validation facts;
- source, build, artifact, validation, and runtime currentness IDs;
- active/resolved failure facts;
- optional knowledge trace correlation;
- next safe disposition.

Heavy logs, provider payloads, artifacts, and event streams remain in
`RunStorage` and are referenced by stable evidence IDs. The ledger is
serialized inside or alongside the existing `RunState` schema, with explicit
schema versioning and backward-compatible read behavior where possible. No
new database is introduced.

Pending requirements are derived from the contract and objective evidence;
they are not authoritative merely because a provider lists them.

## 8. Failure Fact and Normalization

The common failure fact reuses the semantics of `ValidationViolation`,
`ValidationResult`, and `BuildResult`. A build is normalized as:

`BuildResult -> deterministic BuildFailureNormalizer -> failure fact`.

The fact contains, when demonstrable:

- stable `code` and `category`;
- repairability/classification;
- affected requirement IDs;
- symbol, location, and capability hints;
- evidence references;
- a deterministic fingerprint;
- source and build revision identifiers.

It does not pass complete stderr to Brain as an unstructured authority. The
minimum categories are compilation error, missing symbol, signature/API
mismatch, dependency error, timeout, environment/infrastructure failure, and
unknown failure.

Runtime keeps `PASS`, `REPAIRABLE_FAIL`, `BLOCKED`, and `INVALID`. Invalid
contract, contamination, contradictory evidence, and identity mismatch remain
fail-closed. Provider failures, limits, infrastructure failures, and runtime
dependency failures remain `BLOCKED` according to existing policy. A known
repairable target failure may enter Semantic Repair; not every failure does.

## 9. Failure Lifecycle and Reconciliation

Failures are append-only facts with at least `ACTIVE` and `RESOLVED`. A
failure may become `RESOLVED` only after later objective evidence validates the
same related obligation against current source and validation identities.

For build failure F1 on build B1, source mutation followed by current build B2
PASS can resolve F1 when the affected obligation is demonstrated. For runtime
failure F2 on artifact A1, repair must produce a new source revision, build B2,
artifact A2, and the same required validation PASS before F2 resolves.

Repair never resolves by provider declaration or by matching text alone.
`SUPERSEDED` is not required by this RFC; if later needed, it must retain the
original fact and its reason.

## 10. Currentness Model

Currentness is represented by durable identities:

1. `source_revision`: hash of the authorized relevant source tree and contract
   binding, excluding transient build directories and evidence output;
2. `build_attempt_id`: unique attempt linked to source revision and toolchain;
3. `artifact_identity`: artifact SHA and producing build attempt;
4. `validation_contract_revision`: fingerprint of the validation obligation;
5. `runtime_attempt_id`: attempt linked to artifact and validation revision;
6. `evidence_id`: durable evidence record linked to all applicable identities.

Source revision changes when authorized source content relevant to the project
changes. A new contract revision also invalidates evidence whose obligation
definition no longer matches. A build is current only when its source,
toolchain/environment identity, and contract binding match. An artifact is
current only when it was produced by a current successful build. Runtime PASS
is current only when it validates the current artifact and validation contract.

When an identity changes, old evidence remains in history but is marked
`stale_for_completion` with the superseding identity and reason. CompletionGate
must reject stale evidence. This prevents an old runtime PASS from validating
new source.

## 11. General Build and Validation Orchestration

The normal orchestrator coordinates existing components rather than duplicating
them. Its responsibilities are:

- pre-build validation;
- build execution through `GradleBuildRunner`;
- `ArtifactValidator` evaluation;
- runtime dependency preparation;
- typed functional/runtime validation configuration;
- normalized repair feedback;
- bounded repair/rebuild sequencing.

The triggers are deterministic:

- relevant mutation -> pre-build/build;
- repair mutation -> rebuild;
- completion candidate with no current build -> build;
- current artifact and required runtime obligation -> runtime validation;
- no current PASS for the same artifact/contract -> launch when required.

No second Gradle runner or validator is introduced. Runtime dependencies are
resolved through reusable product components, not only through
`BenchmarkExecutor`.

## 12. Normal-Run Brain Orchestration

The normal path supplies:

`FabricTaskContract + ProjectSnapshot + KnowledgeEnvironment`
`+ TaskProgressLedger/pending requirements`

to the existing `PreCodeKnowledgeNeedDeriver`, `KnowledgeService`, selector,
context builder, `SemanticRepairKnowledgeNeedDeriver`, and `KnowledgeTrace`.

Pre-code derivation is bounded to at most eight needs. Repair derivation is
bounded to at most four needs per cycle. A deduplication key includes need
identity, environment identity, and trigger/failure identity. Triggers are
pre-code, material discovery, normalized build failure, normalized runtime
failure, and a useful pending requirement without an equivalent query.

Selected knowledge is injected into provider-visible context before the first
relevant edit. Retrieval is not repeated for every provider turn. Brain OFF
performs zero Brain derivation/retrieval/selection/injection while retaining
all non-Brain context, tools, build/debug, validation, and legacy Semantic
Repair behavior.

KnowledgeTrace may correlate requirement ID with trigger, failure, and repair
cycle identity. It never stores hidden reasoning as a substitute for evidence.

## 13. Minecraft Runtime Orchestration

The runtime adapter translates contract validation requirements into typed
Minecraft validation plans. It reuses `MinecraftTestSpec`,
`MinecraftTestRunner`, `ObservationRequest/Result`, and
`ValidationResult/Violation`. Before launch, every observation/action has an
`observation_id` linked to one or more requirement IDs.

Launch requires current build PASS, current valid artifact, a required runtime
obligation, and no current PASS for the same artifact and contract. The Harness
reports observations and actions; it does not decide global completion.

## 14. CompletionGate Algorithm

`CompletionGate` receives the immutable contract, ledger, RunState, and current
evidence. It evaluates in order:

1. contract identity and schema are valid;
2. every required requirement has acceptable current evidence;
3. completion criteria are satisfied;
4. no blocking failure is `ACTIVE`;
5. required build evidence is current and PASS;
6. required artifact evidence is current and VALID;
7. required runtime evidence is current and PASS;
8. no required evidence is missing or stale.

Its result contains `complete`, pending requirement IDs, active failures,
missing validation, stale evidence, evidence references, and a next
disposition/reason. Satisfying a requirement requires the validation or
objective evidence specified by the contract. LLM output and reporting cannot
set `complete` or transition RunState to `COMPLETED` without the gate result.

## 15. RunState and RunController Integration

At run start, the controller persists contract identity, plan, ledger schema,
and project/source binding. Editing records source mutation and invalidates
dependent evidence. Build failure records a normalized ACTIVE fact; build PASS
records current build evidence. Artifact validation marks the produced
artifact valid or invalid. Runtime failure records an ACTIVE fact and may
trigger bounded repair. Repair records a new source revision and stale prior
evidence. Runtime PASS records current evidence. Reporting summarizes facts;
CompletionGate decides whether completion is allowed.

Existing `RunStatus` values are reused. A new operational state is not needed
by this RFC. All transitions and evidence are persisted through existing
RunController/RunStorage mechanisms.

## 16. Pinned Project Bootstrap

For an authorized empty workspace, bootstrap materializes a canonical project
compatible with `ProjectInspector` and the normal orchestration using:

- Minecraft `1.21.11`;
- Fabric Loader `0.19.3`;
- Fabric API `0.141.6+1.21.11`;
- Yarn `1.21.11+build.6`;
- Java `21`.

The source/template authority is a versioned, reviewed project template or
equivalent canonical materialization manifest. The manifest has deterministic
identity over pinned inputs and namespace/mod-id parameters. Safe creation is
confined to the authorized workspace, rejects traversal/symlink escapes, and
does not execute Knowledge Pack content.

An existing non-empty project is not silently overwritten. Namespace/mod-id
collisions fail closed unless an explicit compatible project mode is selected.
Wrapper and Gradle handling follows the existing authoritative wrapper and
isolated environment rules. Offline reproducibility is required where the
approved seed and caches make it possible; missing dependencies are reported,
not silently substituted.

## 17. Benchmark Adapter

The benchmark path becomes:

`BenchmarkTask -> BenchmarkFabricTaskAdapter -> FabricTaskContract`
`-> normal Fabric orchestration`.

The adapter maps task identity, requirements, acceptance obligations, mutation
expectations, and environment constraints into the general contract. Benchmark
continues to own fixtures, repetitions, statistics, economic contracts, and
benchmark reporting. Product orchestration owns contract processing, Brain,
build, validation, runtime dependencies, mutation/progress, and completion.

This is an inversion of dependency, not a benchmark rewrite. Private
`BenchmarkTask`, `BenchmarkConfig`, and acceptance internals must not be
required by normal product callers.

## 18. Safe Workflow Resume Decision

The safe workflow resume capability is classified:

`S1_DEFER_AFTER_V0_8`

The v0.8 core does not require resume because implementing durable
reconstruction across the existing runtime would expand the critical path.
The acceptable future boundary is nevertheless fixed: after persisted source
mutation, completed build, artifact validation, runtime FAIL, repair pending,
or runtime PASS.

If later included, reconstruction must reload and verify contract identity,
project/source identity, ledger, evidence, currentness, active failures, and
next safe disposition. It must not resume mid-provider, mid-tool, mid-build,
mid-Minecraft, or mid-dispatch. Post-Dispatch Recovery remains authoritative
for dispatch uncertainty. Any future inclusion requires an IMP decision and
regressions for no duplicated work/evidence.

## 19. Error and Blocked Policy

- Invalid contract: fail closed as invalid input; no provider turn.
- Unsupported project: blocked with inspector evidence.
- Bootstrap collision: blocked without overwrite.
- Build environment failure: blocked; preserve evidence and do not fabricate a
  repairable compiler fact.
- Compiler repairable failure: normalized failure, then bounded repair if
  eligible.
- Invalid or stale artifact: no runtime completion; rebuild or report pending.
- Runtime dependency failure: blocked with dependency evidence.
- Runtime timeout: blocked under existing timeout policy.
- Known target crash: normalized runtime failure; repair only when contract
  and validators classify it as repairable.
- Unknown crash: blocked/fail-closed according to existing runtime policy.
- Corrupt Knowledge Pack or incompatible knowledge: blocked/fail-closed.
- No knowledge results: continue without invented knowledge or report pending
  when the contract requires it.
- Provider failure: blocked under provider policy; do not misclassify as a
  functional failure.
- Execution limit: blocked/incomplete according to existing lifecycle.
- CompletionGate incomplete: remain non-complete with pending evidence.

These outcomes reuse existing lifecycle and reporting semantics and do not add
new terminal states.

## 20. Security, Compatibility, and Migration

`SecurePathResolver`, `ToolExecutor`, filesystem confinement, controlled tools,
Knowledge integrity/version gates, secret redaction, Post-Dispatch Recovery,
and economic guards remain authoritative. Contracts, validation specs, and
bootstrap cannot grant shell, arbitrary path, reflection, or executable
Knowledge Pack capability.

Migration is incremental. Legacy normal `RunController` callers continue to
work; benchmark behavior is preserved through the adapter; existing RunState
readback remains supported where possible; and historical evidence is never
rewritten. New snapshots use explicit schema versions and preserve legacy
`KnowledgeTrace` semantics. v0.5, v0.6, and v0.7 behavior remains compatible
unless a separately approved contract migration says otherwise.

## 21. Persistence and Observability

Existing `RunStorage`, `run.json`, `events.jsonl`, evidence directories,
validation results, KnowledgeTrace, and reports remain the persistence and
observability surfaces. The minimum new event concepts are:

- contract created;
- plan created or revised;
- requirement evidence reconciled;
- failure ACTIVE or RESOLVED;
- evidence stale;
- CompletionGate evaluated;
- bootstrap completed or blocked.

Events reference contract, source, build, artifact, validation, runtime, and
evidence identities. Heavy payloads remain in their existing stores. No trace
database is introduced.

## 22. Acceptance Mapping

### E1 - Existing Mod

The normal entry point creates a contract, derives/injects Brain knowledge,
edits, builds, validates required runtime behavior, evaluates CompletionGate,
and delivers a current JAR plus evidence. PASS requires all required current
evidence and a true gate result.

### E2 - Build Repair

The build normalizer creates a deterministic failure fact. Eligible repair uses
bounded Semantic Repair/Brain, records mutation, rebuilds, and resolves the
old failure only after current PASS evidence. PASS requires the old fact to be
`RESOLVED`, not deleted.

### E3 - Runtime Repair

After current artifact validation, a runtime failure becomes ACTIVE. Bounded
repair changes source, marks old evidence stale, creates a new build and
artifact, reruns the required validation, resolves the old failure, and passes
CompletionGate. Text-only matching or old-artifact PASS is insufficient.

### E4 - Multi-Capability

The contract carries multiple stable requirements and typed validations. The
ledger correlates each requirement independently and CompletionGate requires
all required obligations without private benchmark metadata.

### E5 - From Scratch

An authorized empty workspace uses pinned bootstrap, then normal inspection,
implementation, build, required validation, CompletionGate, and JAR delivery.
PASS requires deterministic bootstrap identity and confined safe creation.

### E6 - Failure Honesty

Valid JAR without a required satisfied requirement, stale runtime evidence, or
an ACTIVE blocking failure yields non-complete. The gate, not the provider or
reporting, supplies this result.

### E7 - Brain Normal Run

The normal non-benchmark entry point demonstrates provider-visible pre-code
knowledge before relevant edit, bounded knowledge-assisted normalized repair,
and Brain OFF with zero Brain knowledge while preserving the rest of the flow.

### E8 - Benchmark Adapter

The adapter produces the general contract and invokes normal orchestration.
Benchmark-only repetition, statistics, fixtures, and economic reporting stay
outside product ownership.

### E9 - Resume

E9 is conditional because S1 is deferred. If S1 is later included, controlled
interruption must reopen only at a safe boundary, avoid duplicate work/evidence,
recompute currentness and pending requirements, and reach the correct gate
decision.

## 23. Risks and Tradeoffs

The principal risks are contract schema migration, incorrect currentness
identity, accidental duplicate evidence, over-triggered knowledge retrieval,
and benchmark leakage into normal orchestration. The mitigations are immutable
fingerprints, explicit evidence links, append-only history, bounded dedup keys,
typed validation correlation, and the adapter boundary.

The thin orchestration may leave some advanced resume and generic dependency
repair for later work. This is intentional and avoids a second runtime or
planner before evidence justifies it.

## 24. Decisions Deferred to IMP

The IMP must decide implementation sequencing, exact module placement, schema
version migration steps, adapter construction order, test fixtures, fault
injection, and the smallest implementation slices for M1-M5. It must not
silently change the Design, introduce excluded architecture, or include S1
without a new decision. Live provider and Minecraft validation require the
separate authorization specified by the project workflow.

## 25. Status

This RFC is complete at the architecture level and ready for approval. It does
not create implementation files, execute providers, run Minecraft, or define
the implementation plan.
