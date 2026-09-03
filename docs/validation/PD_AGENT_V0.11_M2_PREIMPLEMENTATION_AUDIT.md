# PD Agent v0.11 - M2 Pre-Implementation Audit

## 1. Baseline

- Repository: `C:\dev\proyectos\PD-Agent`
- Branch: `main`
- HEAD/origin: `4a5a5721dd08a312ba04f4220b409837c23f25c5`
- Tracked tree: clean
- Authorized pre-existing untracked path: `scripts/benchmark/diagnostics/`
- Scope: read-only verification for M2 Lot A; no Lot B implementation.
- External API/provider requests: 0
- Minecraft launches: 0
- Benchmark runs: 0

## 2. Repository Reality Audit

The repository contains the M1 authorities and the relevant existing
boundaries:

| Boundary | Current authority | Result |
|---|---|---|
| Project observation | `pd_agent.project.ProjectInspector` and `FabricInspector` | Present |
| Fabric facts | `FabricInspectionResult.detected_versions`, manifests, roots and issues | Present |
| Bootstrap | `FabricBootstrap`, `PinnedFabricVersions`, `FabricBootstrapResult` | Present; legacy-oriented |
| Brain environment | `KnowledgeEnvironment`, `KnowledgeEnvironmentResolver` | Present; nullable fields |
| Knowledge retrieval | `KnowledgeService`, frozen/source adapters and compatibility checks | Present |
| Capabilities | `CapabilityRegistry`, `CapabilityPlanner`, M1 contract expansion | Present and reusable |
| Product preflight | `ExecutionService.start()` calls product runner `preflight()` before `ExecutionRecord` persistence | Present |
| Runtime/build | `AgentRuntime`, `GradleBuildRunner`, `FabricNormalOrchestrator` | Present |
| Artifact | `ArtifactValidator` | Present; generic JAR expectation gap remains |
| Minecraft | `MinecraftTestSpec` and runner/harness boundary | Present; only legacy support is validated |
| Evidence/completion | `TaskProgressLedger` and `CompletionGate` | Present |

The current implementation has no `FabricPlatformProfile`,
`FabricPlatformResolution`, `FabricSupportRegistry` or `FabricProjectTemplate`.
Those are correctly deferred to Lot B and later lots.

## 3. DESIGN/RFC/IMP Consistency

The three M2 documents agree on the following architecture:

- one local declarative support registry;
- profile resolution from observed workspace facts;
- one product preflight boundary before execution persistence or dispatch;
- reuse of the M1 planner, contract, Brain, build, artifact, runtime and
  CompletionGate authorities;
- separate `UNOBFUSCATED` modern and `OBFUSCATED_REMAPPED` legacy families;
- no second runtime, planner, Brain, currentness authority, database or remote
  registry.

The RFC and IMP already classify concrete modern pins as verification inputs,
not as current support claims. No DESIGN/RFC/IMP edit is required by this
audit.

## 4. Platform Pin Evidence

The official Fabric material reviewed for the platform boundary is:

- [Fabric 26.1 announcement](https://www.fabricmc.net/2026/03/14/261.html)
- [Fabric Loom documentation](https://docs.fabricmc.net/develop/loom/)
- [Fabric mappings migration](https://docs.fabricmc.net/develop/porting/mappings/index)
- [Fabric porting documentation](https://docs.fabricmc.net/develop/porting/index)
- [Fabric 1.21.11 announcement](https://www.fabricmc.net/2025/12/05/12111.html)
- [Fabric documentation home](https://docs.fabricmc.net/)

| Target | Minecraft | Loader | Fabric API | Loom | Java | Mapping family | Status |
|---|---|---|---|---|---|---|---|
| A | 26.2 | exact pin not locally verified | exact pin not locally verified | exact pin not locally verified | exact requirement not locally verified | `UNOBFUSCATED` | TARGET, not supported |
| B | 26.1.2 | exact pin not locally verified | exact pin not locally verified | exact pin not locally verified | exact requirement not locally verified | `UNOBFUSCATED` | TARGET, not supported |
| C | 1.21.11 | `0.19.3` | `0.141.6+1.21.11` | `1.13.3` | `21` | Yarn `1.21.11+build.6`, `OBFUSCATED_REMAPPED` | historical validated baseline |

The official sources establish the modern boundary and the Loom plugin/mapping
model, but they do not provide a complete locally reproducible pin manifest for
26.1.2 and 26.2 in this checkout. Therefore A and B remain `TARGET`; they are
not falsely marked `SUPPORTED`. The legacy pins are evidenced by the existing
bootstrap, fixtures and validation documents.

## 5. Modern/Legacy Boundary

Fabric documentation states that Minecraft 26.1+ is unobfuscated and does not
use the old obfuscation mappings workflow. Modern projects use
`net.fabricmc.fabric-loom`; legacy 1.21.11 uses the remapping plugin/workflow.
The modern family must not receive invented Yarn/Intermediary values. The
legacy family must retain its real mapping namespace and version.

The RFC claim that modern mappings can be null is valid for the nullable Brain
`KnowledgeEnvironment`. The current `FabricEnvironmentConstraints` is nullable
at the Python type level as well, but the current Product resolver still supplies
legacy Yarn and a `PinnedFabricVersions().java` fallback. Lot D must replace
those defaults with profile-derived values and must add/encode mapping family
without changing the meaning of legacy contracts.

## 6. FabricInspector Capability Matrix

Current detection is implemented in `FabricInspector._detect_versions()`:

| Fact | Current sources | Current behavior | M2 requirement |
|---|---|---|---|
| Minecraft | `gradle.properties`, version catalog, build file | detected as `minecraft` | required exact profile field |
| Loader | properties/catalog/build file | detected as `loader` | required exact profile field |
| Fabric API | properties/catalog/build file | detected as `fabric_api` | required exact profile field |
| Loom | properties/catalog/build file | detected as `loom` | required exact profile field |
| Mappings version | properties/catalog/build file | detected as `mappings` | required only for legacy family |
| Mappings namespace/family | not independently observed | resolver currently assumes Yarn | must become explicit/derived from profile evidence |
| Java | no reliable current inspector detection | Product resolver falls back to pinned Java | must be an explicit observation or fail-closed profile fact |
| Manifest/mod identity | `fabric.mod.json` | parsed with ambiguity/issues handling | remains authoritative project identity |

Ambiguous modules and missing wrapper/manifest facts already produce inspector
issues. Lot C must normalize these observations into a single support-resolution
input; a missing required fact must not be silently filled by a legacy default.

## 7. Resolution Feasibility

The proposed flow is implementable:

`FabricInspector -> normalized observation -> FabricSupportRegistry.resolve() ->
FabricPlatformResolution -> Product preflight`

For the current legacy fixture, the observable values are sufficient to match
the existing 1.21.11 profile once the profile registry supplies the known Java,
mapping-family and namespace evidence. For modern targets, Minecraft and the
unobfuscated family are observable/profile facts, while the exact approved
Loader/API/Loom/Java pins and evidence are not yet present locally.

No current workspace can legitimately resolve as modern `SUPPORTED` in Lot A.
This is the intended fail-closed result, not an architecture blocker.

## 8. KnowledgeEnvironment

`KnowledgeEnvironment` is a frozen slots dataclass with nullable fields for
Minecraft, Loader, Loom, mapping namespace/version, Fabric API and Java. Its
serialization and equality are suitable for a profile adapter. The resolver
returns detected/unknown/conflict outcomes, and `KnowledgeService` treats
missing version-sensitive facts as unknown rather than compatible.

`FrozenKnowledgePackSource` compares the complete environment supplied by the
pack manifest. `FabricApiKnowledgeSource` and `YarnKnowledgeSource` still carry
1.21.11 defaults. Those defaults are safe only as legacy compatibility adapters;
Lot E must select sources/packs by resolved profile and reject wrong-family
material. No new pack should be created in Lot A.

## 9. Brain Sources and Packs

Available source/pack implementation is legacy-focused:

- Yarn source: real 1.21.11 Yarn-oriented knowledge;
- Fabric API source: real 1.21.11 API-oriented knowledge;
- Concept/pattern and frozen pack infrastructure: present;
- 26.1.2 pack: not present;
- 26.2 pack: not present.

The selector required by M2 is therefore profile-aware selection, not a new
retrieval system. Legacy knowledge must be rejected for modern profiles unless
explicit compatible evidence exists. The current data is sufficient to design
the selector and fail closed, but not to claim modern Brain support.

## 10. FabricBootstrap

`FabricBootstrap.create()` currently consumes `PinnedFabricVersions`, generates
the legacy Gradle/settings/manifest inputs, copies the wrapper/seed material,
and records workspace fingerprint, seed identity and inspection metadata in
`FabricBootstrapResult`. This is enough for the historical 1.21.11 path.

M2 must turn profile plus template into the bootstrap input while retaining
seed/workspace identity checks. `PinnedFabricVersions` must be demoted to a
legacy compatibility adapter. No modern bootstrap, profile, template or seed
was created during this audit.

## 11. Profile/Template Loading

Recommended form: source-controlled JSON or TOML declarative files loaded by a
small validated data loader. The schema should contain only scalar pins, mapping
family/namespace metadata, evidence references, support status and template
metadata. It must reject duplicate IDs, unknown schema versions, empty pins,
unsafe paths, executable content and secrets. Python declarations are less
reviewable for the growing matrix; no executable profile loading is acceptable.

The existing fixture/data layout may provide test fixtures, but it must not be
treated as a support registry without explicit profile evidence.

## 12. Product Preflight Insertion

The exact existing boundary is `ExecutionService.start()` before construction
and persistence of `ExecutionRecord`: it calls the product runner's
`preflight(project, task)`, and converts a failure into
`ExecutionServiceError` before catalog insertion and worker submission.

Lot G should resolve the current workspace and platform there, fail closed for
unknown/unsupported/conflicting resolution, and pass the resolved profile into
the existing product runner. This preserves the M1 invariant that unsupported
workspaces create no execution and dispatch no provider.

## 13. Contract Compatibility

`FabricTaskContract` already supports multiple `requirements` and
`validation_requirements`, serializes them and fingerprints them. Its
`FabricEnvironmentConstraints` carries version fields, `platform` and validated
`extra`; the current resolver also places Loom and mappings namespace in
`extra`.

Minimal future extension: carry explicit mapping family and profile identity in
the environment adapter or validated extras, and allow modern mapping version
to remain absent without supplying Yarn. Preserve all legacy serialized fields
and fingerprints for existing contracts. No new execution state or contract
authority is needed.

## 14. Build Boundary

There is one `GradleBuildRunner`. It is not version-specific and remains the
build authority. Current offline caches/fixtures and tests provide evidence for
1.21.11 only. No local cache evidence or fixture was found for 26.1.2/26.2.
Lot A therefore verifies feasibility and ownership, while profile-specific
offline build evidence belongs to later lots before `SUPPORTED` status.

## 15. Harness

`MinecraftTestSpec` transports target JAR, target mod ID, Minecraft/Loader,
Java-related launch metadata, runtime dependencies, observations and evidence
paths. The runner validates only the currently supported 1.21.11 environment
and the existing harness fixtures are legacy-only. The harness must not be
generalized in Lot A. Modern harness support is a later evidence-backed lot.

## 16. Support Evidence Gate

The existing `ArtifactValidator` validates build success, candidate JAR
selection, Fabric metadata, identity/version, freshness and ambiguity. It does
not currently accept a general profile-supplied expectation set for arbitrary
JAR entries, resources, classes or assets. This is a real future requirement,
but it is already assigned to the artifact/evidence work after Lot A.

`TaskProgressLedger` stores evidence by requirement and failure facts. Its
failure model supports active/resolved reconciliation and currentness metadata.
`CompletionGate` iterates every required task requirement and every required
validation requirement, checking current evidence, stale evidence and active
failures. It is viable as the sole completion authority and is not structurally
limited to one validation requirement.

Minimum profile support evidence should include exact pins, mapping family,
source/revision identity, loader/API/Loom/Java evidence, deterministic
inspection, offline build evidence where claimed, and runtime/harness evidence
where claimed. The legacy 1.21.11 evidence is the existing baseline; modern
profiles remain TARGET.

## 17. Structured Errors

Existing conventions include inspector issues, `ProductFabricTaskContractError`
with stable codes, `ExecutionServiceError`, compatibility statuses
`COMPATIBLE`/`INCOMPATIBLE`/`UNKNOWN`, and fail-closed Minecraft environment
errors. Lot G should add stable support-resolution codes at the Product boundary
without leaking provider/runtime exceptions or introducing a parallel error
authority.

## 18. Real Test/Module Plan

Relevant existing tests inspected:

- `tests/unit/test_fabric_task_contract.py`
- `tests/unit/test_execution_plan_ledger.py`
- `tests/unit/test_completion_gate.py`
- `tests/unit/test_fabric_bootstrap.py`
- `tests/unit/test_l1_brain_environment.py`
- `tests/unit/test_l2_brain_retrieval.py`
- `tests/unit/test_l6_artifact_validator.py`
- `tests/unit/test_minecraft_observation_contracts.py`
- `tests/unit/test_minecraft_batch_a.py`
- `tests/unit/test_minecraft_batch_b.py`
- `tests/unit/test_minecraft_batch_c.py`
- `tests/unit/test_i16_runtime_mapping.py`
- `tests/unit/test_i12_r26_offline_repairs.py`
- `tests/unit/test_runtime_failure_reconciliation.py`
- `tests/unit/test_productive_contract_preflight.py`
- `tests/unit/test_productive_runtime_wiring.py`
- `tests/unit/test_i12_r35_repair_reconciliation.py`
- `tests/unit/test_currentness.py`

Command attempted:

```text
.venv-l0fix\Scripts\python.exe -m pytest -q [the modules listed above]
```

Result: `131 passed, 2 warnings, 141 errors in 3.80s`. The errors occurred
during pytest `tmp_path` setup because the environment denied scanning
`C:\Users\Usuario\AppData\Local\Temp\pytest-of-Usuario` (`WinError 5`).
The warnings were pytest cache write warnings for the same permission-restricted
environment. This is an environmental validation limitation, not a product
assertion failure. Full pytest is not required for the Lot A audit.

Additional command correction: an initial command referenced the nonexistent
`tests/unit/test_minecraft_runtime.py`; it failed at collection before running
tests and was not treated as product evidence.

Required Lot B tests should add profile schema/family/identity validation,
registry duplicate/conflict behavior and modern/legacy resolution. Lot C/D/E/F/G
should then cover observation mapping, contract adaptation, Brain selection,
bootstrap/template round-trip and preflight-before-persistence respectively.

## 19. Discrepancies and Classification

| Finding | Classification | Action |
|---|---|---|
| No M2 profile/registry/template implementation exists | A - no discrepancy | Expected Lot B scope |
| Modern exact pins and local evidence are absent | B - clarification only | Keep 26.1.2/26.2 as `TARGET`; verify before support claim |
| Product resolver still uses legacy Java/Yarn fallbacks | B - clarification only | Remove/demote in Lots C/D/G; do not certify modern support |
| Current ArtifactValidator lacks arbitrary required-entry expectations | B - clarification only | Assign to later evidence/artifact work |
| Current harness validates legacy only | B - clarification only | Do not claim modern runtime support in M2 Lot A |
| No second runtime/planner/Brain/currentness/DB/registry authority | A - no discrepancy | Preserve invariant |
| Pytest temp-root permission denial | Environmental validation limitation | Do not modify ACL; rerun in a permitted environment |

No DESIGN, RFC or IMP correction is required by the evidence collected here.
No implementation plan change is required. No architecture blocker was found.

## 20. Lot A Verdict

`PREIMPLEMENTATION_VERIFICATION_READY`

Lot A is ready to hand off to implementation. It verifies the architecture,
documents the modern/legacy boundary and prevents false support certification;
it does not certify 26.1.2 or 26.2 as supported.

## 21. Lot B Authorization Recommendation

Authorize Lot B only for the declarative platform domain foundation:

1. implement profile, resolution, registry and template data models;
2. implement strict deterministic schema validation and identity;
3. load only source-controlled declarative data;
4. register the historical 1.21.11 profile with its verified evidence;
5. keep 26.1.2 and 26.2 as `TARGET` until exact pins/evidence are verified;
6. add offline tests for supported, target, unknown, unsupported and conflict;
7. do not modify Product preflight, Brain selection, bootstrap, build or
   Minecraft execution in Lot B;
8. do not create modern packs or claim modern end-to-end support.

The next authorization should explicitly require a clean test environment or
host-side pytest temp root so that the environmental `WinError 5` does not mask
Lot B regression results.
