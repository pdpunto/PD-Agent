# PD Agent v0.8 - Autonomous Fabric Agent Foundation IMP

Status: IMP READY FOR APPROVAL
Milestone: PD Agent v0.8 - Autonomous Fabric Agent Foundation
Design authority: `docs/design/PD_AGENT_V0.8_AUTONOMOUS_FABRIC_AGENT_DESIGN.md`
RFC authority: `docs/rfc/PD_AGENT_V0.8_AUTONOMOUS_FABRIC_AGENT_RFC.md`
Baseline for implementation planning:
`6ac12ad2d2ac6f2453ba9676361e8a53705b1e00`

## 1. Purpose and Implementation Rules

This IMP defines HOW TO BUILD the approved Design and RFC. It is a plan only;
it does not implement code, authorize provider use, authorize Minecraft live,
or authorize benchmark execution.

Implementation is incremental over the existing `AgentRuntime`,
`RunController`, `RunState`, `RunStorage`, `ToolExecutor`,
`GradleBuildRunner`, `ArtifactValidator`, Semantic Repair, Minecraft Harness,
and v0.7 Brain. Prefer small models, adapters, and thin orchestration.

The plan must not introduce a second runtime, state machine, DAG, graph
engine, planner service, Brain, Harness, database, or Multi-Agent system.
Each lot ends with focused validation, commit, and push before the next lot
starts. A failed lot stops progression and is not silently bypassed.

## 2. S1 Decision

The RFC decision is `S1_DEFER_AFTER_V0_8`. No safe workflow resume
implementation belongs in this IMP, and E9 is not an implementation gate.
Regression coverage may preserve reasonable future snapshot compatibility, but
there is no resume lifecycle, reconstruction, or mid-execution recovery lot in
v0.8. Any later inclusion requires a new decision in Design/RFC/IMP.

## 3. Dependency Graph and Order

The implementation order is intentionally linear to avoid unstable contracts:

`I0 -> I1 -> I2 -> I3 -> I4 -> I5 -> I6 -> I7 -> I8 -> I9`
`-> I10 -> I11 -> I12 -> I13 -> I14 -> I15 -> I16 -> I17`

I0 is audit-only. I1-I4 establish models and facts. I5-I8 connect build,
Brain, runtime, and repair. I9 provides the completion authority. I10-I13
connect the normal product path, bootstrap, adapter, and observability. I14
proves offline behavior, I15 proves real build/artifact readiness, I16 is the
separately authorized integrated runtime gate, and I17 is final regression.

No lot may change a preceding contract silently. If a contract or architectural
decision must change, stop and return to 00 for Design/RFC correction.

## 4. Lot I0 - Pre-Implementation Audit

**Scope:** documentation and audit evidence only; no production code.

**Audit:** Design, RFC, paths, `RunState`/`RunController`, `RunStorage`,
`AgentRuntime`, `BenchmarkExecutor`, Brain/context, build, artifact validator,
Harness, Semantic Repair, security, reporting, project inspection,
serialization schemas, tests, and commit graph.

**Files/modules:** read-only audit of `src/pd_agent/{core,runtime,reporting,
benchmark,brain,build,artifacts,minecraft,project,tools,validation}` and
relevant tests/docs.

**Tests/gates:** route inventory, schema inventory, import/dependency audit,
security boundary audit, and Design/RFC consistency review.

**Acceptance:** `I0_PASS / I1_READY`; no material contradiction; no scope
expansion; I1 remains separately authorized.

**Rollback:** discard audit output only; never alter historical evidence.

**Commit guidance:** `docs: audit v0.8 implementation boundary` only if an
approved audit record is requested; this IMP does not require that commit.

## 5. Lot I1 - Fabric Task Contract Foundation

**Scope:** general immutable `FabricTaskContract`, requirement and validation
requirement models, knowledge signals, environment constraints, canonical
JSON serialization, schema version, fingerprint, identity and validation.

**Likely modules:** `src/pd_agent/core/contracts.py`, a narrowly scoped new
contract module if required, and exports in `src/pd_agent/core/__init__.py`.

**Tests:** `tests/unit/test_fabric_task_contract.py` (new, exact ownership),
with contract roundtrip, fingerprint, invalid schema, revision,
duplicate requirements, unsafe payload, and legacy isolation cases.

**Acceptance:** stable IDs; deterministic serialization/fingerprint; immutable
run identity; duplicate-ID rejection; contract mismatch is fail-closed; no
orchestration or Brain internals in the contract.

**Dependencies:** I0.

**Rollback:** revert I1 schema/module changes; preserve old RunState readers
and all historical evidence.

**Commit:** `feat: add v0.8 Fabric task contract`.

## 6. Lot I2 - Execution Plan and Task Progress Ledger

**Scope:** ordered lightweight `ExecutionPlan`, `TaskProgressLedger`, pending
derivation, evidence references, `ACTIVE`/`RESOLVED` failure history, and
minimal RunState association. Preserve legacy `current_plan` as a projection.

**Likely modules:** `src/pd_agent/core/state.py`, the I1 contract module, and
new narrowly scoped plan/ledger modules under `src/pd_agent/core/`.

**Tests:** `tests/unit/test_execution_plan_ledger.py` for roundtrip, pending
derivation, failure history, contradictory pending/satisfied prevention,
current_plan compatibility, and legacy RunState reopen.

**Acceptance:** no second state machine; pending is derived from contract and
facts; heavy evidence is referenced through RunStorage; schema version is
explicit and readback is backward-compatible where possible.

**Dependencies:** I1.

**Rollback:** revert ledger projection while retaining legacy RunState and
historical evidence; no destructive migration.

**Commit:** `feat: add v0.8 progress ledger`.

## 7. Lot I3 - Currentness Foundation

**Scope:** deterministic source revision, build attempt binding, artifact
identity/SHA, validation contract fingerprint, runtime attempt identity,
evidence binding, `stale_for_completion`, and invalidation rules.

**Likely modules:** `src/pd_agent/core/state.py`, `src/pd_agent/reporting/store.py`,
`src/pd_agent/artifacts/validator.py`, and a small currentness module if
needed.

**Tests:** `tests/unit/test_currentness.py` for unchanged source, mutation,
build/artifact binding, runtime binding, contract revision invalidation, and
preserved-but-rejected stale evidence.

**Acceptance:** source -> build -> artifact -> validation -> runtime -> evidence
chain is deterministic and persistible; currentness never deletes history.

**Dependencies:** I2.

**Rollback:** disable new currentness evaluation behind the legacy read path;
retain all identifiers and evidence records.

**Commit:** `feat: add v0.8 evidence currentness`.

## 8. Lot I4 - Build Failure Normalization

**Scope:** deterministic `BuildResult` to normalized failure fact/
`ValidationViolation`, minimum RFC taxonomy, bounded requirement correlation,
and stable fingerprint. No LLM parsing and no complete stderr as Brain input.

**Likely modules:** `src/pd_agent/build/runner.py`, `src/pd_agent/validation/`,
and a small `src/pd_agent/build/normalization.py`.

**Tests:** `tests/unit/test_build_failure_normalizer.py` for compilation,
missing symbol, signature/API mismatch, dependency, timeout, environment,
unknown, stable fingerprint, and false requirement mapping.

**Acceptance:** deterministic category and repairability; affected requirement
IDs only when demonstrable; infrastructure/unknown remain fail-closed.

**Dependencies:** I3.

**Rollback:** retain raw BuildResult reporting and disable normalized repair
dispatch; preserve failure history.

**Commit:** `feat: normalize Fabric build failures`.

## 9. Lot I5 - General Build and Artifact Orchestration

**Scope:** extract product build preparation currently too tied to
`BenchmarkExecutor`: prebuild, build, artifact validation, currentness,
failure reconciliation, and stale/current artifact handling. No Minecraft.

**Likely modules:** `src/pd_agent/build/runner.py`,
`src/pd_agent/artifacts/validator.py`, `src/pd_agent/validation/prebuild.py`,
`src/pd_agent/runtime/engine.py`, and a thin orchestration module.

**Tests:** `tests/unit/test_fabric_build_orchestration.py` for mutation/build,
repair/rebuild, current build, stale artifact, objective failure resolution,
and valid artifact not implying completion.

**Acceptance:** existing runners/validators are reused; relevant mutation
triggers build; stale evidence blocks completion; benchmark internals are not
required by the product path.

**Dependencies:** I4.

**Rollback:** route legacy benchmark preparation through its existing path;
remove only the new orchestration association, never build evidence.

**Commit:** `feat: add general Fabric build orchestration`.

## 10. Lot I6 - Normal-Run Brain Orchestration

**Scope:** generalize pre-code and repair knowledge wiring with existing
`PreCodeKnowledgeNeedDeriver`, `KnowledgeService`, `ContextManager`,
`SemanticRepairKnowledgeNeedDeriver`, and `KnowledgeTrace`.

**Likely modules:** `src/pd_agent/brain/precode.py`,
`src/pd_agent/brain/semantic_repair.py`, `src/pd_agent/context/manager.py`,
`src/pd_agent/context/knowledge.py`, and thin runtime orchestration.

**Tests:** `tests/unit/test_normal_brain_orchestration.py` for pre-code,
before-first-edit, dedup, max 8 pre-code needs, max 4 repair needs/cycle,
normalized build failure trigger, incompatible knowledge, zero-result degraded
mode, and Brain OFF zero knowledge. Fake providers only.

**Acceptance:** provider-visible injection precedes relevant edit; dedup key
includes need/environment/trigger identity; no retrieval each provider turn;
Brain OFF preserves non-Brain behavior.

**Dependencies:** I5.

**Rollback:** disable normal Brain adapter and preserve v0.7 benchmark wiring;
do not create a second Brain.

**Commit:** `feat: generalize normal Fabric Brain orchestration`.

## 11. Lot I7 - General Runtime Validation Orchestration

**Scope:** map contract validation requirements to typed runtime plans,
observation IDs, requirement IDs, runtime facts, artifact/contract/currentness
binding, outside `BenchmarkExecutor`. No live Minecraft.

**Likely modules:** `src/pd_agent/minecraft/contracts.py`,
`src/pd_agent/minecraft/runner.py`, `src/pd_agent/validation/`, and the thin
orchestrator.

**Tests:** `tests/unit/test_fabric_runtime_orchestration.py` for required and
not-required triggers, stale old PASS, requirement/observation mapping,
infrastructure BLOCKED, known repairable failure, unknown crash, and timeout.
Use controlled Harness doubles.

**Acceptance:** typed correlation before launch; Harness supplies facts but
never completion; no runtime launch when contract does not require it.

**Dependencies:** I6 and I3.

**Rollback:** preserve existing benchmark runtime adapter and its evidence;
remove only the general adapter.

**Commit:** `feat: add general Fabric runtime validation`.

## 12. Lot I8 - Runtime Failure Reconciliation and Semantic Repair

**Scope:** connect runtime ACTIVE failure, eligible Semantic Repair/Brain,
mutation, build, artifact, new runtime evidence, and RESOLVED reconciliation.

**Likely modules:** `src/pd_agent/runtime/engine.py`,
`src/pd_agent/brain/semantic_repair.py`, `src/pd_agent/build/`,
`src/pd_agent/artifacts/`, and validation modules.

**Tests:** `tests/unit/test_runtime_failure_reconciliation.py` for same
requirement/current newer PASS, different requirement, stale PASS, history,
no mutation rejection, and no arbitrary logs as Brain authority.

**Acceptance:** old evidence remains; repair requires objective current evidence;
no text-only resolution; bounded repair only.

**Dependencies:** I7, I5, I6.

**Rollback:** stop runtime repair dispatch and leave recorded failures ACTIVE;
never erase evidence.

**Commit:** `feat: reconcile Fabric runtime failures`.

## 13. Lot I9 - CompletionGate

**Scope:** stateless CompletionGate over contract, ledger, RunState and current
evidence; remove the conceptual `REPORTING -> COMPLETED` shortcut only for the
new normal path while preserving legacy callers during migration.

**Likely modules:** `src/pd_agent/runtime/controller.py`,
`src/pd_agent/runtime/engine.py`, `src/pd_agent/core/state.py`, and a small
`src/pd_agent/validation/completion.py`.

**Tests:** `tests/unit/test_completion_gate.py` for complete requirements,
pending, ACTIVE failure, stale build/artifact/runtime, missing required runtime,
valid JAR alone, optional requirements, and LLM/reporting unable to force
completion.

**Acceptance:** all required current evidence, criteria, and validators pass;
no ACTIVE blocker; output includes pending IDs, failures, missing/stale
validation, refs, and next disposition.

**Dependencies:** I2-I8.

**Rollback:** retain legacy completion for non-migrated callers and disable the
normal gate entry point; preserve gate evidence.

**Commit:** `feat: add Fabric completion gate`.

## 14. Lot I10 - Normal Fabric Orchestrator

**Scope:** general entry point from `NaturalRequirement` through builder,
contract, plan, ledger, Brain, existing AgentRuntime, build/validation/repair,
and CompletionGate. No BenchmarkTask required.

**Likely modules:** new thin `src/pd_agent/fabric/` orchestration package only
if existing ownership audit requires it, plus `src/pd_agent/runtime/` and
`src/pd_agent/core/` integration. Avoid broad AgentRuntime ownership.

**Tests:** `tests/unit/test_normal_fabric_orchestrator.py` with fake
provider/tools for existing mod, build repair, incomplete requirement, and no
benchmark imports in product path.

**Acceptance:** one product flow owns coordination while existing components
retain their responsibilities; CompletionGate controls completion.

**Dependencies:** I9, I1-I8.

**Rollback:** route callers to the prior entry point; do not remove legacy
RunController behavior.

**Commit:** `feat: add normal Fabric orchestration`.

## 15. Lot I11 - Pinned Fabric Bootstrap

**Scope:** authorized empty workspace to canonical ProjectInspector-compatible
Fabric project with deterministic manifest/fingerprint and safe inputs.

**Likely modules:** `src/pd_agent/bootstrap.py`,
`src/pd_agent/project/fabric.py`, `src/pd_agent/project/inspector.py`,
`src/pd_agent/project/models.py`, and `src/pd_agent/tools/security.py`.

**Tests:** `tests/unit/test_fabric_bootstrap.py` for clean bootstrap,
deterministic identity, invalid mod ID, traversal, non-empty collision, exact
versions, and inspector PASS.

**Acceptance:** Minecraft `1.21.11`, Loader `0.19.3`, Fabric API
`0.141.6+1.21.11`, Yarn `1.21.11+build.6`, Java 21; wrapper and seed handling
are reproducible, confined, and fail closed on collision.

**Dependencies:** I10 and I5.

**Rollback:** remove bootstrap invocation while preserving existing project
workspaces; never overwrite a non-empty workspace.

**Commit:** `feat: add pinned Fabric project bootstrap`.

## 16. Lot I12 - Benchmark Adapter

**Scope:** `BenchmarkTask -> BenchmarkFabricTaskAdapter -> FabricTaskContract
-> normal orchestration`; migrate only product responsibilities.

**Likely modules:** `src/pd_agent/benchmark/models.py`,
`src/pd_agent/benchmark/acceptance.py`, a new adapter module under
`src/pd_agent/benchmark/`, and normal orchestration imports.

**Tests:** `tests/unit/test_benchmark_fabric_adapter.py` for task adaptation,
acceptance, mutation expectations, environment mapping, preserved benchmark
behavior, and no benchmark imports in product modules.

**Acceptance:** benchmark retains fixtures, repetitions, statistics, economics,
and reporting; normal product owns contract, Brain, build, validation, runtime,
progress, and completion.

**Dependencies:** I10, I11.

**Rollback:** retain the current BenchmarkExecutor path and remove adapter
selection; do not rewrite benchmark evidence.

**Commit:** `feat: adapt benchmark tasks to Fabric contracts`.

## 17. Lot I13 - Observability and Reporting

**Scope:** durable events and reporting for contract, plan, requirement
reconciliation, failure lifecycle, stale evidence, CompletionGate, and
bootstrap, reusing existing stores and KnowledgeTrace.

**Likely modules:** `src/pd_agent/reporting/events.py`,
`src/pd_agent/reporting/store.py`, `src/pd_agent/reporting/report.py`, and
normal orchestration event emission.

**Tests:** `tests/unit/test_v08_observability.py` for roundtrip, evidence refs,
no hidden reasoning, gate-reflective report, and historical/legacy readback.

**Acceptance:** events include contract created, plan created/revised,
requirement reconciled, failure ACTIVE/RESOLVED, stale evidence, gate
evaluated, and bootstrap; no trace database.

**Dependencies:** I2, I3, I9-I12.

**Rollback:** disable new event emission while preserving existing reports,
events, and evidence.

**Commit:** `feat: add v0.8 orchestration evidence`.

## 18. Lot I14 - Offline Integrated Acceptance

**Scope:** adversarial fake-provider/controlled validation for E1-E8. E9 is
explicitly not required because `S1_DEFER_AFTER_V0_8`.

**Likely modules:** no new production module unless a proven integration gap;
tests under `tests/integration/` and `tests/unit/`.

**Tests/gates:** existing mod, build repair, runtime repair, multi-capability,
from-scratch, failure honesty, Brain normal run, and benchmark adapter.
Adversarial cases cover stale evidence, wrong correlation, corrupt contract,
fingerprint mismatch, Brain OFF, infrastructure failure, repeated failure,
early completion, benchmark leakage, bootstrap collision, and security.

**Acceptance:** E1-E8 PASS with no live provider; no E9 gate.

**Dependencies:** I13.

**Rollback:** remove only new integration fixtures/harness doubles; preserve
production and historical evidence.

**Commit:** `test: validate v0.8 offline acceptance`.

## 19. Lot I15 - Real Build and Artifact Readiness

**Scope:** real pinned bootstrap, approved Gradle seed/materialization,
`compileJava`, JAR build, ArtifactValidator, and currentness chain without
provider API or live Minecraft.

**Likely modules:** existing `src/pd_agent/build/runner.py`,
`src/pd_agent/artifacts/validator.py`, `src/pd_agent/bootstrap.py`, and
validation tests/scripts already used by the repository.

**Acceptance:** reproducible offline build and valid current artifact; no
external dependency hidden by a copied seed; historical evidence untouched.

**Dependencies:** I11-I14.

**Rollback:** retain validated seed and prior build path; no source/evidence
rewrite.

**Commit:** `test: validate v0.8 build readiness`.

## 20. Lot I16 - Integrated Minecraft Acceptance

**Scope:** authorized live evidence for E1, E3, E5, E6, and E7 where required;
provider use only if separately authorized by 00.

**Preconditions:** I0-I15 PASS, fresh isolated LaunchRoot/ExecutionRoot,
frozen task/config/fixture, credential redaction, budget approval, and a
written authorization naming provider/model/task and ceiling.

**Acceptance:** Brain ON provider-visible injection before relevant edit,
mutation, build, valid current artifact, required Minecraft validation,
failure repair where applicable, current evidence, and CompletionGate PASS.
Any Brain OFF comparison must use the same task/provider/model/tools/
environment/acceptance and inject zero external Brain knowledge.

**No automatic live action:** this IMP does not authorize I16. On mismatch,
uncertain consumption, security blocker, or transport uncertainty, stop.

**Rollback:** never rewrite live evidence; abandon only the isolated execution
according to its evidence policy.

**Commit:** `test: validate v0.8 integrated acceptance` only after authorized
validation and review.

## 21. Lot I17 - Full Regression and Technical Closure

**Scope:** final suite, `compileall`, approved offline compileJava, security,
and v0.5/v0.6/v0.7 compatibility; E1-E8 and I16 evidence review. No v0.9.

**Tests/gates:** full repository suite, compileall, `git diff --check`,
security checks, currentness/evidence review, and final A-J style report for
v0.8. I16 live evidence is reused only when identity and currentness remain
valid.

**Acceptance:** no demonstrated product defect or capability gap within scope;
all required evidence current; technical closure returned to 00. Formal
closure is not declared by the IMP.

**Dependencies:** I0-I16.

**Rollback:** no code rollback from a documentation decision; isolate any
failed evidence and return a blocker report.

**Commit:** `test: validate v0.8 technical closure` only when authorized.

## 22. Acceptance Mapping

| Acceptance | Primary lots | Required gate |
| --- | --- | --- |
| E1 Existing Mod | I10, I14, I15, I16 | current JAR, required validation, CompletionGate |
| E2 Build Repair | I4-I5, I8, I14 | normalized failure, repair, rebuild, RESOLVED |
| E3 Runtime Repair | I7-I8, I14, I16 | stale old evidence, new artifact/runtime PASS |
| E4 Multi-Capability | I1-I3, I9-I10, I14 | every required ID satisfied |
| E5 From Scratch | I11, I14-I16 | pinned bootstrap through current JAR |
| E6 Failure Honesty | I3-I4, I7-I9, I14, I16 | no completion with missing/stale/blocking facts |
| E7 Brain Normal Run | I6, I10, I14, I16 | pre-edit injection, repair knowledge, Brain OFF |
| E8 Benchmark Adapter | I12-I14 | adapter uses normal orchestration |
| E9 Resume | deferred | not required; S1 deferred |

## 23. Security and Migration Gates

Every lot must preserve `SecurePathResolver`, `ToolExecutor`, controlled tools,
filesystem confinement, knowledge integrity/version gates, secret redaction,
Post-Dispatch Recovery, economic guards, historical RunState/readback, and
benchmark compatibility. Contract, validation, and bootstrap inputs cannot
grant shell, arbitrary paths, reflection, or executable knowledge content.

Schema changes must be versioned and backward-readable where reasonable.
Historical executions/evidence are immutable. Benchmark compatibility remains
through the adapter, not product imports of benchmark internals. A lot that
breaks these guarantees fails its acceptance even if its new feature works.

## 24. Commit and Rollback Strategy

Each material lot follows:

`focused tests/checks -> review -> git diff --check -> commit -> push`

The suggested commit messages above are guidance, not permission to commit.
No squash is required. Diagnostics remain outside staging. Rollback means
reverting the lot's code/schema association without deleting evidence or
rewriting historical snapshots. Any migration that cannot be safely reverted
must stop for architectural review.

## 25. Live Authorization Boundaries

I0-I15 are provider-free/API-free wherever possible; fake providers and
controlled Harness doubles are preferred. I16 is the only planned live gate
and requires explicit later authorization. Provider/model, task, acceptance,
fixture, limits, credentials, budget, and Brain mode must be frozen before a
live run. No live run may be used to silently tune the implementation or
change the benchmark contract.

## 26. Closure Criteria

The IMP is complete when I0-I17 are implemented and validated according to
their gates, the final regression is PASS, current evidence supports all
required acceptance, and 00 receives the technical report. This document does
not declare v0.8 closed, Alpha, v0.9, or any later milestone.

## 27. Status

`V0_8_AUTONOMOUS_FABRIC_AGENT_IMP_READY_FOR_APPROVAL`

No implementation is authorized by this document alone.
