# PD Agent v0.11 / M2 Closure

## Milestone

**Versioned Fabric Platform & Brain**. This document closes M2 on the final
baseline `bc0eb623375aef98daa425451dc157e5a229debe`.

## Scope and Authorities

The closure is audited against the approved DESIGN, RFC, IMP,
pre-implementation audit, platform evidence, source-controlled platform
registry, implementation, and tests. M2 establishes version-aware Fabric
inspection, support resolution, product preflight, bootstrap/template
selection, imported-project currentness, Brain compatibility, and offline
evidence boundaries. It does not add a second runtime architecture.

## Architecture

The final composition is:

`Workspace -> FabricInspector -> observed Fabric environment -> FabricSupportRegistry -> FabricPlatformResolution -> Product preflight -> existing CapabilityRegistry/Planner -> FabricTaskContract -> Brain/KnowledgeEnvironment -> existing FabricNormalOrchestrator -> existing AgentRuntime -> Build/Artifact/Runtime -> TaskProgressLedger -> CompletionGate`

M2 reuses the M1 capability/planner, Brain, KnowledgeEnvironment, build,
runtime, evidence, ledger, and CompletionGate authorities. No second
AgentRuntime, Product runner, planner, registry, Brain service, knowledge
model, CompletionGate, ledger, persistent execution DAG, parallel bootstrap
system, or parallel version resolver was introduced.

## R1-R20 Audit

| Requirement | Result | Evidence |
|---|---|---|
| R1 local declarative FabricSupportRegistry | PASS | `src/pd_agent/fabric/registry.py`, `platform_profiles.json` |
| R2 complete FabricPlatformProfile | PASS | `src/pd_agent/fabric/platform.py` |
| R3 UNOBFUSCATED / OBFUSCATED_REMAPPED | PASS | platform registry and platform model |
| R4 SUPPORTED/UNSUPPORTED/UNKNOWN/CONFLICT | PASS | registry resolution tests |
| R5 Inspector observes; Registry decides | PASS | Inspector, registry, and resolution tests |
| R6 no fallback defaults | PASS | missing/conflicting observation tests |
| R7 product preflight before ExecutionRecord/provider | PASS | `test_r114_product_platform_preflight.py` |
| R8 existing M1 CapabilityRegistry/Planner reused | PASS | productive composition tests |
| R9 contract from current platform resolution | PASS | product preflight and contract tests |
| R10 KnowledgeEnvironment reused | PASS | Brain platform integration tests |
| R11 compatible Brain source/pack and recheck | PASS | R112/R120 evidence and tests |
| R12 version-aware bootstrap/template | PASS | R113 bootstrap/template tests |
| R13 new-project bootstrap and reinspection | PASS | bootstrap and currentness evidence |
| R14 imported project without manifest | PASS | R115 imported-project tests |
| R15 historical provenance is not support authority | PASS | imported/currentness and registry boundaries |
| R16 one version-agnostic BuildRunner | PASS | existing BuildRunner composition and R119/R120 evidence |
| R17 generalized Harness | DEFERRED_AS_DESIGNED | DESIGN/RFC explicitly retain the Harness boundary |
| R18 multi-platform offline evidence as applicable | PASS | R117-R120 evidence |
| R19 wrong/unsupported platform or knowledge fails closed | PASS | product preflight, Brain, currentness, and negative tests |
| R20 SUPPORTED requires PD Agent evidence including offline build | PASS | registry evidence gate and platform profiles |

R17 is the only explicit boundary/deferment: M2 does not generalize the
Minecraft Harness or claim arbitrary validation coverage.

## Supported Platform Matrix

The authority for current status is
`src/pd_agent/fabric/data/platform_profiles.json`.

| Platform | Status | Loader | Fabric API | Loom | Java | Mapping |
|---|---|---|---|---|---|---|
| Fabric 1.21.11 | SUPPORTED | 0.19.3 | 0.141.6+1.21.11 | 1.13.3 | 21 | OBFUSCATED_REMAPPED / yarn 1.21.11+build.6 |
| Fabric 26.2 | SUPPORTED | 0.19.3 | 0.158.0+26.2 | 1.17-SNAPSHOT | 25 | UNOBFUSCATED / no mappings |
| Fabric 26.1.2 | TARGET / not supported | n/a | n/a | n/a | n/a | no profile |

The 26.2 promotion is supported by R119 and R120, including inspection,
contract wiring, Brain compatibility, and offline-build evidence. The earlier
R119 target wording is historical pre-promotion evidence; R120 is the final
certification. No 26.1.2 support claim is made.

## Evidence Matrix

Each supported profile has the required `PROFILE_DEFINITION`,
`INSPECTION_RESOLUTION`, `CONTRACT_WIRING`, `BRAIN_COMPATIBILITY`, and
`OFFLINE_BUILD` evidence in the source-controlled registry.

### Fabric 1.21.11

R117/R118 and the previously validated v0.7/v0.8 evidence cover the legacy
profile, its pinned environment, contract wiring, Brain compatibility, and
offline build/artifact path.

### Fabric 26.2

R119/R120 cover the modern profile, real inspection and bootstrap material,
contract wiring, compatible modern Brain sources, and offline build evidence.
The profile uses `UNOBFUSCATED` mappings and therefore has no Yarn namespace or
mappings version.

## Project, Bootstrap, Import, and Currentness

New Fabric projects select a versioned template, bootstrap deterministically,
and are reinspected against the resulting profile. Imported projects are
resolved from their current observable metadata; missing or ambiguous
manifests do not inherit historical support. Manual changes invalidate
currentness and require fresh inspection/preflight.

## Brain Compatibility

Brain source and pack selection is platform-aware and rechecked against the
resolved environment. Wrong-version sources, packs, Yarn, Fabric API, or
stale material fail closed. The 26.2 path uses compatible modern Fabric API
and concept material; legacy 1.21.11 knowledge is not silently reused as 26.2
support.

## Product Fail-Closed Behavior

The product blocks `UNSUPPORTED`, `UNKNOWN`, `CONFLICT`, `TARGET`, stale or
ambiguous imported projects, wrong Brain source, wrong Yarn, wrong Fabric API,
and wrong frozen pack. Where applicable, these checks occur before provider,
worker, and `ExecutionRecord` dispatch. Historical provenance remains
diagnostic evidence, never a support authority.

## R123 Runtime Reconciliation Closure Defect

R123 corrected a real closure defect: runtime observation requirements used
`validation:*` identifiers while the task ledger and CompletionGate used
`requirement:*` identifiers. A runtime failure therefore remained active after
the later authoritative PASS, and CompletionGate correctly returned
`completion_not_authoritative`.

The adapter in `src/pd_agent/validation/runtime.py` now normalizes the runtime
identity to the canonical task requirement domain before reconciling through
the existing strict `FailureReconciler`. The reconciler still requires ACTIVE,
PASS, current artifact, current validation revision, exact requirement IDs,
and matching evidence. Unrelated active failures remain active.

This is a closure defect repair, not a new M2 capability:

- repair commit: `dc46ebe0a55aad0b6ab3b80993986a7cfdccb990`;
- isolation regression: `bc0eb623375aef98daa425451dc157e5a229debe`.

## Regression Results

Evidence on the final R123 implementation baseline:

- Python: `1414 passed, 4 skipped, 0 failed`;
- Playwright general: `10 passed`;
- dedicated R15 Playwright: `1 passed`;
- Vitest: `70 passed`;
- TypeScript: PASS;
- Vite build: PASS;
- compileall: PASS;
- `git diff --check`: PASS.

The dedicated R15 deterministic browser scenario exercised runtime failure,
repair, rebuild, authoritative runtime PASS, and terminal success. The
runtime reconciliation focal suite passed, including wrong artifact,
wrong requirement, wrong revision, non-PASS, non-ACTIVE, and unrelated-failure
isolation cases.

## Static and Repository Validation

Final implementation baseline: `bc0eb623375aef98daa425451dc157e5a229debe`.
The closure document itself is the only intended tracked change in the
closure commit. The pre-existing untracked
`scripts/benchmark/diagnostics/` directory is preserved and is not part of
the product or closure.

## Live-Call Counts

For the closure and R123 validation:

- external provider/API requests: `0`;
- Minecraft live launches: `0`;
- benchmark live runs: `0`;
- new productive executions: `0`.

## Nonclaims

M2 does not certify Fabric 26.1.2, arbitrary Fabric versions, automatic mod
migration, a generalized Harness, generalized M4 validation, broad M3 Alpha
capabilities, other loaders, Paper, NeoForge, Velocity, Multi-Agent,
universal Brain coverage, full version-by-capability certification, or an
Alpha release.

26.2 support means that the PD Agent platform/profile/bootstrap/inspection/
contract/Brain/preflight/build support evidence required by M2 is certified.
It does not certify every future M3 capability on 26.2.

## Deferments

- v0.12 / M3: Alpha Fabric Capabilities & Assets;
- v0.13 / M4: Generalized Validation, Repair & Runtime;
- v0.14 / M5: Secure Product Alpha;
- Alpha / M6: Acceptance & Release Candidate.

Fabric 26.1.2 remains eligible for a future certification and does not block
M2 because two platforms are supported: 1.21.11 and 26.2.

## Final Verdict

`PD_AGENT_V0.11_M2_CLOSED_PASS`
