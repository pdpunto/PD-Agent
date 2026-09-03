# PD Agent v0.10 - M1 Closure

Status: `PD_AGENT_V0.10_M1_CLOSED_PASS`

Milestone: `PD Agent v0.10 - M1 General Fabric Task Foundation`

## 1. Baselines and Scope

The v0.10 M1 DESIGN baseline is `5d74095e8c31d7f38a2c84ab6e424d4525e9b878`.
The RFC baseline is `e3c11eca8b5fe388110fb51c2afeaea314a76f1d` and the IMP
baseline is `9945bd642bdbdc37efc05aec92a4f3a60a7e69e4`.
The final implementation baseline before closure is
`c175b14439d798747e5121c12e27850177718558`.

M1 delivers a small general Fabric capability foundation. It does not claim
the complete Alpha capability catalog or generalized Minecraft validation.

## 2. Delivered Architecture

The final productive composition is:

`Product request -> CapabilityCandidate -> CapabilityRegistry ->`
`CapabilityPlanner -> deterministic dependency resolution -> requirement and`
`validation expansion -> FabricTaskContract -> FabricProductExecutionRunner`
`-> FabricNormalOrchestrator -> AgentRuntime -> build/artifact/evidence ->`
`TaskProgressLedger -> CompletionGate`.

The foundation capabilities are:

- `fabric.block`
- `fabric.block_item`
- `fabric.recipe`

They are declarative, parameterized, composable, deterministic and
validatable. The planner is data-only and has no execution authority. The
existing Product runtime, RunStorage, TaskProgressLedger and CompletionGate
remain the authorities for their respective responsibilities.

No second runtime, Brain, CompletionGate, ledger, persistent DAG framework,
M2 Support Registry, M3 parallel capability framework or benchmark-owned
Product planner was introduced.

## 3. Lots R91-R103

R91 established the pre-design reality audit. R92 defined the exact M1
requirements. R93 persisted DESIGN, R94 persisted RFC, and R95 persisted IMP.
R96 accepted the pre-implementation audit. R97 delivered the capability model,
R98 the registry, R99 deterministic planning, R100 requirement expansion, R101
validation expansion and R102 Product integration. R103 added the
representative BLOCK + BLOCK_ITEM + RECIPE Product flow evidence.

## 4. AC1-AC17 Closure Matrix

| Criterion | Implementation evidence | Test evidence | Result |
|---|---|---|---|
| AC1 composed plan | `CapabilityPlanner` and contract expansion | planner and R103 integration | PASS |
| AC2 at least three capabilities | foundation registry | R103 asserts three instances | PASS |
| AC3 deterministic dependencies | stable prerequisite resolution/order | planner regression and R103 | PASS |
| AC4 shared prerequisite deduplication | planner identity map | planning regression | PASS |
| AC5 multiple requirements | `expand_plan_to_contract` | contract and R103 assertions | PASS |
| AC6 correlated validations and traceability | requirement/validation binding | contract, trace and R103 tests | PASS |
| AC7 contract authority | Product runner consumes generated contract | Product boundary tests | PASS |
| AC8 existing runtime | existing orchestrator and AgentRuntime | R103 offline Product flow | PASS |
| AC9 ledger evidence correlation | `TaskProgressLedger` reconciliation | progress and Product tests | PASS |
| AC10 CompletionGate | existing read-only gate | completion and R103 tests | PASS |
| AC11 Server Core compatibility | temporary request adapter delegates to common planner | productive contract regression | PASS |
| AC12 honest unsupported behavior | fail-closed planner/preflight errors | `test_product_preflight_rejects_before_execution_persistence` | PASS |
| AC13 invalid plans before runtime | planner cycle/invalid checks | adversarial planning/preflight tests | PASS |
| AC14 v0.9 persistence/hydration | existing serialization authorities retained | persistence and Product regressions | PASS |
| AC15 security boundaries | SecurePathResolver and ToolExecutor retained | security regression suite | PASS |
| AC16 deterministic foundation | schemas, identities and stable ordering | capability/planner/contract suites | PASS |
| AC17 complete regression | final closure regression | `1353 passed, 4 skipped, 0 failed` | PASS |

## 5. Server Core Migration

`ProductFabricTaskContractResolver` still recognizes the historical Server Core
request as a temporary compatibility adapter. It derives the project namespace
from Fabric metadata and delegates capability composition, planning and
contract expansion to the general M1 path. It does not define a second
contract lifecycle, capability architecture, requirement-ID architecture,
validation branch or CompletionGate branch.

This is documented as `SERVER_CORE_REQUEST_ADAPTER_TEMPORARY`. It is retained
for compatibility because the common planner path is now authoritative and
the regression remains passing. M1 does not claim to retire every historical
request adapter beyond this compatibility boundary.

## 6. Representative Offline Product E2E

Test: `tests/integration/test_m1_representative_product_e2e.py`.

The test uses the real Product application composition, Product preflight,
Fabric resolver, capability planner, contract expansion, Product runner,
FabricNormalOrchestrator, AgentRuntime, filesystem ToolExecutor,
`GradleBuildRunner`, `ArtifactValidator`, RunStorage, progress reconciliation
and CompletionGate.

Observed evidence:

- planner instances: `fabric.block`, `fabric.block_item`, `fabric.recipe`;
- dependency edges: `2`;
- generated contract: `6` requirements and build/artifact/minecraft validations;
- real filesystem mutations: Java source, `en_us.json` and recipe;
- offline Gradle build: `BUILD SUCCESSFUL`;
- ArtifactValidator classification: `VALID`;
- progress ledger: no pending requirements;
- CompletionGate: `COMPLETE`;
- Product result: `SUCCEEDED`;
- execution/run identity: `execution_id == run_id`;
- ProjectInspector final status: `READY`.

The provider is a deterministic fake and the Minecraft functional-validation
boundary is controlled offline. No external provider request or Minecraft
launch was performed. This is `REPRESENTATIVE OFFLINE PRODUCT E2E`, not full
live E2E or Minecraft-live certification.

The negative unsupported/preflight path remains covered by the existing
Product tests and rejects before runtime execution persistence.

## 7. Security, Currentness and Completion Invariants

- Planner and capability data have no execution authority.
- Product preflight occurs before an `ExecutionRecord` is created.
- Planning failures produce zero dispatch.
- ToolExecutor and SecurePathResolver remain the filesystem authorities.
- Provider/model values remain opaque and no secrets enter planner provenance.
- Generated fixture `bin/` output remains excluded from Fabric inspection as
  intended.
- `FabricTaskContract.fingerprint` remains authoritative.
- Plan fingerprint is provenance only.
- `TaskProgressLedger` remains the only requirement-progress ledger.
- Build and artifact identities remain correlated to contract and source
  revisions.
- CompletionGate remains the only completion authority.

## 8. Deferred Scope

The following are intentionally deferred and are not M1 blockers:

- M2/v0.11: version/support registry, multi-version platform, version-aware
  Brain/bootstrap and new project identity/template foundation.
- M3/v0.12: broad Fabric capability catalog, deterministic asset toolkit and
  general assets.
- M4/v0.13: generalized 1-to-N runtime validation, generalized Harness/probes,
  generalized repair/currentness validation and the runtime first-match
  limitation.
- M5/v0.14: secure import isolation, full Product trust/version/capability UX,
  broader cancellation, recovery and concurrency closure.
- Alpha/M6: held-out acceptance, version-by-capability certification and the
  frozen RC campaign.

## 9. Explicit Non-Claims

M1 does not claim all Alpha capabilities, multi-version support, generalized
runtime validation, generalized probes, Minecraft-live certification,
provider-live certification, benchmark certification, imported-project trust
closure or M5 security closure. In particular, `GAP-SEC-001` remains a later
M5 concern.

R103 exercised the Minecraft validation port through a controlled offline
functional validator boundary. It did not launch Minecraft and must not be
reported as Minecraft-live evidence.

## 10. Final Regression and Git State

Final full regression command:

`..venv-l0fix\\Scripts\\python.exe -m pytest -q --basetemp C:\\dev\\pruebas\\pd-agent-r104-full-basetemp`

Result: `1353 passed, 4 skipped, 0 failed`.

Final focal command covered:

- `tests/unit/test_fabric_capabilities.py`;
- `tests/unit/test_fabric_planning.py`;
- `tests/unit/test_fabric_task_contract.py`;
- `tests/unit/test_product_execution.py`;
- `tests/unit/test_productive_contract_preflight.py`;
- `tests/integration/test_m1_representative_product_e2e.py`.

Result: `72 passed, 1 warning`.

`python -m compileall src tests`: PASS.

`git diff --check`: PASS.

The warning is an environmental `.pytest_cache` permission warning and does
not affect test results. No API/provider-live request, Minecraft live launch,
benchmark run or economic-ledger write was performed for R104.

Before the closure commit, the final implementation HEAD was
`c175b14439d798747e5121c12e27850177718558`. The closure commit is the only
tracked change introduced by R104. The pre-existing untracked
`scripts/benchmark/diagnostics/` directory is preserved and excluded.

## 11. Verdict

`PD_AGENT_V0.10_M1_CLOSED_PASS`

Formal closure is limited to v0.10/M1. No v0.11/M2 work is started by this
document.
