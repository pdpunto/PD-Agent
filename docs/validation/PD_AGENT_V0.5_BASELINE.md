# PD Agent v0.5 Baseline Validation

Status: PASS
Date: 2026-08-14

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Baseline commit: `d2b3d05c270aa6dc33c8872c156fc7fab8446e80`
- HEAD: `d2b3d05c270aa6dc33c8872c156fc7fab8446e80`
- origin/main: `d2b3d05c270aa6dc33c8872c156fc7fab8446e80`

## Working Tree

- Tracked tree: clean
- Preexisting untracked diagnostics: `scripts/benchmark/diagnostics/`

## Milestone Predecessor

- PD Agent v0.4: implemented, live validated, and PASS
- v0.4 validation reference: `docs/validation/PD_AGENT_V0.4_VALIDATION.md`

## Frozen Versions

- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Fabric Loom: `1.13.3`
- Yarn: `1.21.11+build.6`
- Java: `21`
- Gradle Wrapper: `8.14.3` on the validated benchmark/harness line

## Gradle Seed Contract

The official Gradle seed for v0.5 must be a coherent portable snapshot of the
dependency cache material actually required by the pinned project base.

In practice that means:

- capture the portable `caches/modules-2` inventory as a unit after the host
  resolves the pinned dependency graph;
- preserve portable metadata files such as
  `module-metadata.bin`, `module-artifact.bin`, `module-artifacts.bin`,
  `resource-at-url.bin`, POMs and JARs;
- exclude nonportable cache-state files such as `*.lock`, `*.lck`,
  `gc.properties`, and other transient bookkeeping files already classified
  as nonportable;
- materialize a fresh per-run `GRADLE_USER_HOME` from that canonical seed;
- keep offline resolution reproducible without depending on the host temp
  path used during bootstrap.

## Capabilities Verified as Inherited

- ProjectInspector READY path
- Gradle Wrapper authority
- Benchmark foundation operational
- Action Transition present
- FILE_EXISTS recovery present
- retained inspection evidence present
- mutation-target policy present
- Brain OFF/ON wiring correct
- reproducible Gradle environment available
- Minecraft Harness current contract still operative

## Commands Executed

### Offline validation

- `python -m compileall src scripts tests`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q tests\\unit\\test_l7_context_system.py tests\\unit\\test_l9_runtime.py tests\\unit\\test_benchmark_executor.py tests\\unit\\test_minecraft_batch_a.py tests\\unit\\test_minecraft_batch_b.py tests\\unit\\test_minecraft_batch_c.py tests\\unit\\test_validation_runner.py`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q`

## Results

### Compile

- PASS

### Focused tests

- PASS
- Result: `129 passed`

### Full suite

- PASS
- Result: `425 passed, 2 skipped`

## Risks / Limitations

- `scripts/benchmark/diagnostics/` remains as an untracked preexisting diagnostics directory and is intentionally ignored.
- This freeze does not introduce F1 project-base material yet.
- No API, no live benchmark, and no new product capability were executed for F0.

## Acceptance Criteria for F0

- v0.4 remains green
- baseline is reproducible
- inherited capabilities are intact
- frozen version line is documented
- no architecture change was introduced

## Final Verdict

F0 accepted and frozen as the technical baseline for PD Agent v0.5.
