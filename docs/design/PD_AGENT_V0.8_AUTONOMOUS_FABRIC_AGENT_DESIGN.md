# PD Agent v0.8 - Autonomous Fabric Agent Foundation

Status: DESIGN ACCEPTED
Milestone: PD Agent v0.8 - Autonomous Fabric Agent Foundation
Depends on: PD Agent v0.7 - Minecraft/Fabric Knowledge Foundation (`CLOSED / PASS`)

## 1. Context

PD Agent v0.7 provides the contracts, knowledge foundation, controlled tools,
build and artifact validation, Semantic Repair, and Minecraft evidence needed
for a safe Fabric workflow. v0.8 defines how those capabilities become a
general autonomous Fabric flow rather than a workflow whose preparation is
owned by benchmark-specific concepts.

The existing `AgentRuntime` and `RunState` remain the operational foundation.
The benchmark remains a client and compatibility adapter, not the owner of the
general task lifecycle.

## 2. Problem

The normal product flow must be able to determine what a Fabric project must
achieve, what remains pending, what knowledge is relevant, when validation is
required, and whether current evidence supports completion. These decisions
must not depend on `BenchmarkTask`, `BenchmarkConfig`, private benchmark
acceptance fields, or model declarations of completion.

## 3. Goals

- Represent a general, immutable and persistible Fabric task contract.
- Guide execution with a lightweight plan and durable requirement progress.
- Normalize build and runtime failures into deterministic evidence.
- Reuse the v0.7 Brain for normal pre-code and bounded repair flows.
- Support a pinned, reproducible Fabric 1.21.11 bootstrap.
- Run Minecraft only when the task contract requires it.
- Accept completion only from current objective evidence.
- Preserve safe boundaries for future incremental resume.
- Keep the benchmark as an adapter over the normal orchestration.

## 4. Non-Goals

v0.8 does not add Multi-Agent, specialist agents, UI, Alpha product UI,
Paper, NeoForge, Velocity, `.Fuzzer`, SaaS, payments, a new Knowledge Base,
a new Brain, a new Harness, embeddings, vector storage, long-term memory,
sophisticated planning, a DAG, a graph engine, model routing, multi-version
bootstrap or Minecraft support, client validation, generic dependency repair,
or self-generated benchmarks.

It must not introduce a second runtime, state machine, planner service,
repair engine, Brain, Harness, or trace database without evidence and a
separate architectural decision.

## 5. Scope Requirements

### M1 - General Fabric Task Contract

The product must have a general `FabricTaskContract` representing the stable
WHAT of a task. It contains task identity and revision, goal, requirements,
required capabilities, completion criteria, validation requirements, knowledge
signals, derivable mutation expectations, and applicable environment
constraints.

Every requirement has a stable ID. The contract is immutable/persistible and
must not treat LLM-generated technical solutions as authority. A benchmark
task is adapted as:

`BenchmarkTask -> adapter -> FabricTaskContract`

### M2 - Lightweight Plan and Progress Ledger

An `ExecutionPlan` provides a coarse sequence of intent. It guides work but
does not decide completion, implement a DAG, or create another state machine.

A `TaskProgressLedger` records satisfied requirements, derived pending
requirements, unresolved and resolved failures, evidence by requirement,
current build/artifact/runtime state, validation evidence, and useful
knowledge correlation. It is associated with `RunState`, which remains the
only operational state machine. No new database is introduced by this design.

### M3 - General Validation and Build/Repair Orchestration

Productive preparation and validation must be usable outside
`BenchmarkExecutor`. Build results are normalized deterministically into a
validation violation or failure fact before Semantic Repair or Brain is
considered. The LLM does not choose failure taxonomy.

Failure history is append-only. A failure may transition from `ACTIVE` to
`RESOLVED` only when later objective, current evidence demonstrates that its
related obligation passes. A current successful build may resolve a relevant
build failure. A valid artifact is evidence, but is not by itself task
completion.

The minimum conceptual build taxonomy includes compilation error, missing
symbol, signature/API mismatch, dependency error, timeout,
environment/infrastructure failure, and unknown failure. Existing runtime
semantics remain `PASS`, `REPAIRABLE_FAIL`, `BLOCKED`, and `INVALID`.
Infrastructure, identity, timeout, and unknown crashes retain fail-closed
handling and are not sent to repair indiscriminately.

### M4 - Normal-Run Brain Orchestration

Normal execution reuses the v0.7 Brain:

`FabricTaskContract + ProjectSnapshot + KnowledgeEnvironment`
`-> PreCodeKnowledgeNeedDeriver -> KnowledgeService`
`-> selection/injection -> provider`

When applicable, provider-visible knowledge is injected before the first edit.
Semantic Repair knowledge is reused for normalized build and runtime failures.
Bounded triggers are pre-code, newly material material discovery, normalized
build failure, normalized runtime failure, and a pending requirement without an
equivalent query when Brain can help. Retrieval is not performed for every
provider turn. Preferred bounds are eight pre-code needs and four repair needs
per cycle.

Brain never decides requirement satisfaction.

Brain OFF performs zero Brain need derivation, retrieval, selection, and
injection while preserving project/run/external context, tools, build/debug,
validation, and legacy Semantic Repair without knowledge.

### M5 - Pinned Fabric 1.21.11 Bootstrap

For an authorized empty workspace, v0.8 supports a canonical reproducible
bootstrap with:

- Minecraft `1.21.11`;
- Fabric Loader `0.19.3`;
- Fabric API `0.141.6+1.21.11`;
- Yarn `1.21.11+build.6`;
- Java `21`.

This is a pinned v0.8 environment, not a universal generator or a multi-version
bootstrap. It must remain compatible with the current Gradle and Minecraft
validation pipeline.

## 6. Conceptual Lifecycle

The intended product flow is:

`natural Fabric requirement`
`-> project analysis`
`-> FabricTaskContract`
`-> lightweight plan`
`-> knowledge needs and injection`
`-> edit`
`-> build`
`-> diagnose/repair`
`-> current artifact validation`
`-> required Minecraft validation`
`-> requirement/evidence correlation`
`-> CompletionGate`
`-> current valid JAR and evidence`.

The flow may return to edit, build, or validation when objective evidence
shows an unresolved requirement or failure.

## 7. Ownership Boundaries

- `FabricTaskContract` owns the WHAT and completion/validation requirements.
- `ExecutionPlan` owns coarse intent guidance only.
- `TaskProgressLedger` owns requirement-related facts and evidence references.
- `RunState` owns operational lifecycle state.
- Brain owns knowledge need derivation, retrieval, selection, and injection.
- Build and validators own objective build/artifact facts.
- Minecraft Harness owns observations and actions, never completion.
- `CompletionGate` owns the final evidence-based completion decision.
- Benchmark owns adaptation and benchmark reporting, not normal orchestration.

## 8. Validation and Runtime

Minecraft runs only when required by `validation_requirements` or `completion`
criteria. Evidence correlates explicitly:

`requirement_id -> validation requirement -> observation/action spec`
`-> observation result -> validation evidence`.

Correlation is not based on free-form LLM text. The Harness supplies facts and
evidence; it does not decide completion.

## 9. Currentness and Reconciliation

The durable evidence chain is:

`source revision -> build attempt -> artifact identity/SHA`
`-> runtime attempt -> observation evidence`.

When source changes, prior build, artifact, and runtime evidence become stale
for completion. A runtime PASS on an old artifact cannot validate new source.
Repair does not erase prior failure history. For example, a runtime failure on
artifact A is resolved only after source repair, build B, artifact B, and the
same required validation pass objectively.

## 10. CompletionGate

`CompletionGate` is general and stateless. Its conceptual input is the task
contract, progress ledger, and current evidence/RunState. It verifies required
requirements, completion criteria, current mandatory validation, absence of
active blocking failures, and current build, artifact, and runtime evidence
when required.

Its output includes `complete`, pending requirements, unresolved failures,
missing or stale validation, and evidence references. Reporting cannot imply
`COMPLETED`, and an LLM cannot declare completion unilaterally.

## 11. Brain and Security Invariants

The v0.7 compatibility hard gate, frozen pack, version isolation, controlled
tools, filesystem confinement, security policy, and no-leakage guarantees are
preserved. Knowledge is context, never executable instruction. Unknown
version-sensitive knowledge fails closed. Brain OFF remains a real mode, not a
different task or acceptance contract.

## 12. Resume Boundary (SHOULD)

Incremental resume is a viable design direction, not an automatic requirement.
If implemented, it may resume only from durable safe boundaries: after source
mutation, completed build, artifact validation, runtime failure, repair pending,
or runtime pass.

Resume reloads the contract, verifies contract/project identity, reloads
progress and evidence, recomputes pending requirements and currentness, and
re-enters a planning/correction/validation boundary. It must not resume
mid-provider, mid-tool, mid-build, mid-Minecraft, or mid-dispatch. Post-Dispatch
Recovery remains authoritative for its own domain.

If implementing this SHOULD requires large runtime changes, it may be deferred
without blocking the v0.8 core.

## 13. Benchmark Boundary

The benchmark remains supported through:

`BenchmarkTask -> adapter -> FabricTaskContract -> normal orchestration`.

General product code must not depend on benchmark task/config/acceptance
internals to prepare contracts, Brain, builds, validation, runtime
dependencies, mutations, progress, or completion.

## 14. Design Acceptance

Future implementation and validation must provide evidence for the following:

- **E1 Existing Mod:** natural requirement through general contract, Brain,
  edit, build, required validation, CompletionGate PASS, JAR and evidence.
- **E2 Build Repair:** normalized build failure, bounded repair, mutation,
  rebuild PASS, and old failure RESOLVED.
- **E3 Runtime Repair:** artifact-valid Minecraft failure, normalized ACTIVE
  failure, bounded Brain/Semantic Repair, source change, stale old evidence,
  new artifact, Minecraft PASS, failure RESOLVED, and CompletionGate PASS.
- **E4 Multi-Capability:** all requirements complete without private benchmark
  acceptance or mutation metadata.
- **E5 From Scratch:** authorized empty workspace through pinned bootstrap,
  implementation, build, required validation, CompletionGate and JAR.
- **E6 Failure Honesty:** valid JAR, stale evidence, or blocking unresolved
  failure never produces `COMPLETED` when requirements are not satisfied.
- **E7 Brain Normal Run:** provider-visible pre-code knowledge before a
  relevant edit, knowledge-assisted normalized repair, and Brain OFF with zero
  Brain knowledge.
- **E8 Benchmark Adapter:** benchmark adaptation uses the same normal
  orchestration without product dependence on benchmark internals.
- **E9 Resume:** only if S1 enters implementation scope, controlled
  interruption resumes at a safe boundary without duplicate work/evidence and
  reaches the correct completion decision.

## 15. Risks and Open Questions for RFC

The RFC must define the exact persistence shape, ownership boundaries,
transition rules, currentness identifiers, bootstrap input contract, and
provider/tool integration without weakening the boundaries in this DESIGN.
It must also resolve how requirement evidence is correlated across repeated
repair cycles and how safe resume identity is verified.

No RFC or implementation detail is frozen by this document. These questions
are intentionally deferred to the next approved documents.

## 16. Deferred Direction

`ALPHA_SCOPE = FABRIC ONLY` remains preserved. v0.9 may later address internal
Web/UI and product integration, followed by separate Alpha hardening/readiness
work, but neither v0.9 nor Alpha is started or declared here. Additional
versions and platforms require a new Direction decision.

## 17. Status

This document defines WHAT for v0.8 and is ready for approval. It does not
authorize RFC, IMP, implementation, live provider use, Minecraft execution,
benchmark execution, or v0.8 closure.
