# PD Agent v0.4 Implementation Delta: Harness Target Runtime Contract

## Status

Proposed.

## Baseline

- `HEAD == origin/main == ae489b25d728bf68c7aac5d60a347b3a68b44b9e`
- Do not touch `scripts/benchmark/diagnostics/`

## Goal

Implement the runtime-only harness target contract without changing dataset, acceptance, B001/B002/B003 semantics, or Minecraft security boundaries.

## Implementation order

### A. Remove compile-time coupling from the harness

Update `tests/fixtures/l11_minecraft_harness/build.gradle.kts`:

- remove `compileOnly(files("../l11_fabric_fixture/build/classes/java/main"))`
- keep the harness as an independent project

Update harness source:

- remove imports of `dev.pdpunto.l11.ExampleMod`
- `HarnessRuntimeOptions` must resolve the expected block state internally
- `HarnessRunner` must not call the target class directly at compile time

### B. Add a runtime target bridge

Add a harness-local bridge, for example:

- `tests/fixtures/l11_minecraft_harness/src/main/java/dev/pdpunto/l11harness/TargetBridge.java`

Responsibilities:

- receive the validated target entrypoint class name at runtime
- load that class with runtime reflection
- locate `applyProbeState(ServerWorld, BlockPos)`
- invoke it and return the boolean result
- fail explicitly on any mismatch

### C. Propagate entrypoint metadata from `MinecraftTestRunner`

Extend `MinecraftTestRunner` runtime plan behavior, not the public benchmark spec, unless a later audit proves a spec field is required.

Preferred behavior:

- inspect the validated target JAR's `fabric.mod.json`
- derive the first class from `entrypoints.main`
- pass the derived class to the harness as a runtime property

Suggested property name:

- `pd.agent.targetEntrypointClass`

The runner must not accept an arbitrary class name from untrusted input.

### D. Keep existing target validation

Do not change:

- containment checks
- SHA validation
- mod id validation
- `SecurePathResolver`
- `MinecraftTestRunner.validate_target()`

The bridge runs only after the target JAR has already passed validation.

### E. Preserve runtime propagation

Keep current runtime property propagation intact:

- `pd.agent.targetJar`
- `pd.agent.targetModId`
- `pd.agent.targetSha256`
- `pd.agent.testId`
- `pd.agent.resultPath`
- `pd.agent.runDir`
- `pd.agent.resultMode`
- `pd.agent.expectedBlockStateId`
- `pd.agent.expectNeighborUpdate`
- `pd.agent.hangMillis`

Add the entrypoint class property only if needed by the harness bridge.

### F. Offline build verification

Verify the harness can build offline without the sibling compiled classes directory.

Required checks:

- harness build does not depend on `../l11_fabric_fixture/build/classes/java/main`
- no compile-time import of `ExampleMod`
- target JAR is still runtime validated
- `GRADLE_USER_HOME` isolation continues to propagate

### G. External smoke only if the sandbox blocks Gradle

If the sandbox cannot complete an offline build because of the existing Loom/lock environment issue, do not change product code to work around the environment.

Use the external owner-validating environment only as a diagnostic step, not as a production workaround.

### H. B001 OFF/ON live smoke after the contract lands

After the docs are implemented, run only the readiness smoke needed to confirm:

- B001 Brain OFF
- B001 Brain ON

Do not jump to the full 18-run benchmark matrix until readiness is confirmed.

## Tests to add

Minimum required regressions:

1. Harness build succeeds without sibling compileOnly classes.
2. Harness sources do not import `ExampleMod`.
3. Target entrypoint is extracted successfully from a valid target JAR.
4. Missing or invalid target entrypoint fails explicitly.
5. Missing target method fails explicitly.
6. Signature mismatch fails explicitly.
7. Invocation failure fails explicitly.
8. Containment is still enforced.
9. SHA validation is still enforced.
10. No fallback to static fixture classes exists.
11. B001 runtime contract still works.
12. B003 neighbor contract still works.
13. `environment_overrides` propagation still works.
14. Harness build remains offline-compatible.

## Suggested test locations

- `tests/unit/test_minecraft_batch_b.py`
- `tests/unit/test_minecraft_batch_c.py`
- `tests/unit/test_benchmark_executor.py`
- `tests/unit/test_benchmark_run_v0_4.py`

## Files likely to change

- `tests/fixtures/l11_minecraft_harness/build.gradle.kts`
- `tests/fixtures/l11_minecraft_harness/src/main/java/dev/pdpunto/l11harness/HarnessRunner.java`
- `tests/fixtures/l11_minecraft_harness/src/main/java/dev/pdpunto/l11harness/HarnessRuntimeOptions.java`
- new harness bridge source file
- possibly `src/pd_agent/minecraft/runner.py` if the entrypoint property is propagated there
- possibly benchmark tests that assert the launch plan properties

## What must not change

- dataset freeze controls
- acceptance
- `max_agent_steps`
- B001/B002/B003 semantics
- `SecurePathResolver`
- runtime security boundary
- Action Transition logic
- provider/model settings

## Documentation commitment

This implementation delta assumes:

- no Design delta
- RFC defines the runtime contract
- IMP defines order, tests, and acceptance

## Final note

The harness should validate a runtime target JAR, not a sibling compiled class directory. That is the contract change to implement.
