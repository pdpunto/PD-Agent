# PD Agent v0.5.5 Dataset Freeze Validation

Status: PASS
Date: 2026-08-16

## Repository

- Repository: `PD-Agent`
- Branch: `main`
- Baseline commit: `289524cb05abebf2009b93b572e70cf4601babb3`
- HEAD / origin at audit start: `289524cb05abebf2009b93b572e70cf4601babb3`
- Working tree: tracked clean before this change
- Preexisting untracked diagnostics: `scripts/benchmark/diagnostics/`

## Audit Scope

Audited against:

- `docs/design/PD_AGENT_V0.5_FABRIC_CAPABILITY_DESIGN.md`
- `docs/rfc/PD_AGENT_V0.5_FABRIC_CAPABILITY_RFC.md`
- `docs/implementation/PD_AGENT_V0.5_FABRIC_CAPABILITY_IMP.md`
- `docs/validation/PD_AGENT_V0.5_FUNCTIONAL_EVALUATION.md`
- `benchmarks/projects/v0_5_fabric_base/**`
- `benchmarks/tasks/F6-T1-v5.json`
- `benchmarks/tasks/F6-T2-v5.json`
- `benchmarks/tasks/F6-T3-v5.json`
- `benchmarks/datasets/PD_AGENT_BENCHMARK_DATASET_V0.5_5.json`
- `benchmarks/datasets/PD_AGENT_BENCHMARK_DATASET_V0.5_5.md`
- `benchmarks/datasets/PD_AGENT_BENCHMARK_DATASET_V0.5_1.json`
- `benchmarks/datasets/PD_AGENT_BENCHMARK_DATASET_V0.5_1.md`
- `src/pd_agent/benchmark/catalog.py`
- `src/pd_agent/benchmark/models.py`
- `src/pd_agent/benchmark/runner.py`
- `src/pd_agent/benchmark/scheduler.py`
- `tests/unit/test_benchmark_dataset_v0_5.py`

## Frozen Dataset

- Dataset id: `PD_AGENT_BENCHMARK_DATASET_V0.5_5`
- Dataset version: `0.5.5`
- Task count: `3`
- Task ids: `F6-T1`, `F6-T2`, `F6-T3`
- Project base ref: `projects/v0_5_fabric_base`
- Project base tree hash: `43fa87dbff8a1602d61755cba17fedcae155b08f2763cf7b197d3e56596c43e3`

## Revision History

- `0.5.1` was created and frozen first.
- Review 04 detected hidden acceptance requirements in T1/T2 and a semantic mismatch in T3.
- `0.5.1` remains in the repository as historical evidence only.
- `0.5.2` corrected the naming fairness and initial acceptance shape.
- `0.5.5` supersedes `0.5.4` for official approval and live validation after
  the F1 dependency restoration and F6 rebase.

## Design Fit

The frozen dataset matches the v0.5 design intent:

- existing Fabric project;
- deterministic pinned project base;
- no creation-from-scratch;
- three representative feature-development tasks;
- natural user-facing prompts with explicit product-facing names;
- acceptance independent from implementation details;
- runtime observability kept through the existing harness contract;
- preservation invariants expressed as structured metadata.

## Knowledge Need Review

- `F6-T1`: `LOW`
- `F6-T2`: `LOW`
- `F6-T3`: `MATERIAL`

Reasoning:

- T1 is a small single-file feature and mostly needs local Fabric item-registration knowledge.
- T2 adds resource wiring, but still stays on conventional Fabric block/item patterns.
- T3 is the most representative task and benefits materially from external Yarn/Fabric knowledge without exposing a reference solution.

## Anti-Bias Review

Confirmed for all three tasks:

- the prompt states the desired content request, not the implementation;
- no helper name, class name, or API sequence is required by the prompt;
- no benchmark-specific trick is exposed;
- alternative correct implementations remain possible;
- the tasks are plausible user requests outside the benchmark.

## Preservation Enforcement Matrix

| Invariant | Status | Evidence path |
| --- | --- | --- |
| `mod_id` | PARTIALLY_ENFORCED | Project inspector + artifact validator + Minecraft target validation |
| `entrypoints` | PARTIALLY_ENFORCED | Project inspector + target JAR manifest checks |
| `preserve_unrelated_sources` | DOCUMENTARY_ONLY | Source-change evidence and benchmark notes |
| `resource_contract` | ENFORCED | Resource-file assertions plus paired block/item registry observations |

The existing benchmark pipeline is sufficient for the frozen dataset, but it does not expose a generic semantic diff oracle for arbitrary preservation rules.

## Reference Satisfiability Review

The tasks are satisfiable on the pinned project base:

- the base project is valid and has stable identity;
- each prompt names a concrete content addition that can be expressed with standard Fabric patterns;
- the acceptance contract observes registry presence and resource wiring, which the harness can already evaluate;
- no new harness capability is required for F6.

No provider API or live benchmark run was needed for this review.

## Validation Performed

- `python -m compileall src scripts tests`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q tests\\unit\\test_benchmark_acceptance.py tests\\unit\\test_benchmark_dataset_v0_5.py tests\\unit\\test_benchmark_executor.py tests\\unit\\test_v0_5_acceptance_contract.py`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q`

## Results

- Compile: PASS
- Focused acceptance/dataset/executor tests: PASS
- Full suite: PASS

## Risks / Limitations

- The dataset is intentionally limited to three tasks.
- The frozen acceptance layer still relies on the existing harness contract and benchmark evaluator.
- `scripts/benchmark/diagnostics/` remains preexisting and untracked.
- The harness can observe registry presence and resource evidence, not a generic runtime semantics oracle for arbitrary server-side behavior.

## Final Verdict

F6 dataset freeze complete and compatible with the existing benchmark infrastructure.

## Post-freeze Reference Satisfiability Validation

The v0.5.4 reference validation was completed against the frozen target
contract without changing the dataset tasks. F6-T2 used the positive Marble
Lantern artifact with SHA
`5bc5005f390e80173bfd54f659b49af7656b345161690dc35a4ee0e558b8a843`.

Positive reference evidence:

- build: PASS;
- artifact classification: VALID;
- block `REGISTRY_ENTRY_PRESENT` for `examplemod:marble_lantern`: PASS;
- item `REGISTRY_ENTRY_PRESENT` for `examplemod:marble_lantern`: PASS;
- resource acceptance: PASS;
- global acceptance: PASS.

Negative language evidence kept block and item behavior valid but changed the
required language resource. Resource acceptance and global acceptance then
failed as designed, confirming that the resource checker is meaningful.

F6-T1 runtime regression also passed with the current runtime dependency
contract. The Signal Charm item was observed with Fabric API resolved by the
general resolver and loaded by Fabric Loader.

F4 is implemented and live validated. F6 reference satisfiability is now
validated for T1, T2, and T3. F6 is **PASS** and closed; F7 remains the next
phase and is not started by this validation.

### F6-T3 HOST Reference Evidence

The corrected temporary T3 reference was validated from a normal Windows host
without modifying the canonical project, dataset, Harness, or product code.

- reference source tree hash:
  `4d33618c7cf0122f3ee178c11a807816d4442c7d62012f5170328c1d11b53b98`;
- Gradle seed identity: `3f45504a92b4c3ca6a0aff10933f8f193104b5fec08fbdfab50a285900f0e665`;
- Gradle seed components: `11742`;
- build: PASS;
- artifact classification: VALID;
- artifact SHA-256:
  `8be9d6453b00deaa0d76e031fdb7278f111734b85dd34871fd099d76104becc2`;
- runtime dependency: `net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11`;
- runtime dependency SHA-256:
  `bdff7fd7e220085cfad2ff9b1f40dde6534ae0b96cf378f97a374bc54cb9ed0f`;
- dependency provenance: `build.gradle.kts:17:modImplementation`;
- block observation `REGISTRY_ENTRY_PRESENT` for
  `examplemod:server_core`: PASS;
- item observation `REGISTRY_ENTRY_PRESENT` for
  `examplemod:server_core`: PASS;
- both observations reported `target_loaded=true`,
  `target_origin_resolved=true`, `target_sha_match=true`,
  `server_started=true`, `shutdown_requested=true`, and
  `process_timed_out=false`;
- Fabric API loaded: true; `IllegalAccessError`: false for both observations;
- required resource acceptance: PASS with no violations;
- global acceptance: PASS.

Evidence roots:

- host execution:
  `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f6-t3-host-20260821-193201-256-669`;
- block observation:
  `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-f6-t3-ab-20260821-193318-707-947`;
- item observation:
  `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-f6-t3-ab-20260821-193441-432-139`.

F6 final status: `F6-T1 PASS`, `F6-T2 PASS`, `F6-T3 PASS`,
`V0_5_F6_REFERENCE_SATISFIABILITY_PASS`.
