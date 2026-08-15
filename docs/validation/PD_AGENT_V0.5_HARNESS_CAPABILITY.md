# PD Agent v0.5 Minecraft Harness Capability Validation

Status: PASS
Date: 2026-08-15

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Baseline commit audited: `561e0127bf39604a20d8250976503bd2de8ebebc`
- HEAD / origin at audit start: `561e0127bf39604a20d8250976503bd2de8ebebc`
- Working tree: tracked clean before this change
- Preexisting untracked diagnostics: `scripts/benchmark/diagnostics/`

## Audit Scope

Audited against:

- `docs/design/PD_AGENT_V0.5_FABRIC_CAPABILITY_DESIGN.md`
- `docs/rfc/PD_AGENT_V0.5_FABRIC_CAPABILITY_RFC.md`
- `docs/implementation/PD_AGENT_V0.5_FABRIC_CAPABILITY_IMP.md`
- `src/pd_agent/minecraft/contracts.py`
- `src/pd_agent/minecraft/runner.py`
- `src/pd_agent/benchmark/executor.py`
- `tests/fixtures/l11_minecraft_harness/**`
- `tests/fixtures/l11_fabric_fixture/**`
- `benchmarks/projects/v0_5_fabric_base/**`
- Minecraft harness unit tests

## Functional Observations Required by v0.5

### A. Already Supported

- Loading a real target JAR from a confined path.
- Verifying target mod id.
- Verifying target artifact hash.
- Resolving the target main entrypoint from `fabric.mod.json`.
- Invoking target runtime behavior through the public `applyProbeState(ServerWorld, BlockPos)` bridge.
- Distinguishing `PASS`, `FAIL`, `CRASH`, `TIMEOUT`, and `INFRA_ERROR`.
- Preserving shutdown control and structured result output.
- Preserving target JAR containment and `SecurePathResolver` boundaries.
- Preserving neighbor-update observation for the current block-state signal path.
- Preserving a second observation path for registry presence checks without using the legacy block-state bridge.

### B. Required Minimal Extension

- The harness `test_id` contract must remain generic and not be locked to the two v0.4 probe labels.
- v0.5 acceptance can carry an observation label as metadata without forcing the harness to know the task catalog.
- The observation contract must distinguish label text from observation semantics.

### C. Would Require Redesign

- A new generic harness architecture.
- Hardcoded task-specific runtime logic in the runner core.
- A solution-revealing helper path in the target fixture.

No item in the audited v0.5 requirement set required category C.

## Gap Identified

The first v0.5 harness gap was the v0.4-era whitelist in `HarnessConfig.java`:

- `block_state_probe`
- `block_state_probe_with_signal`

That whitelist was acceptable for v0.4 but too narrow for v0.5, where the harness should accept a generic observation label carried by the benchmark/acceptance layer.

The second gap was the API mismatch in the registry-presence path:

- `Registries.BLOCK.getOrEmpty(identifier).isPresent()`
- `Registries.ITEM.getOrEmpty(identifier).isPresent()`

That lookup was not supported in this environment for `DefaultedRegistry<Block>` / `DefaultedRegistry<Item>`.

## Extension Applied

The harness contract was minimally generalized:

- `test_id` remains required and non-empty.
- The closed whitelist was removed.
- Existing v0.4 probe labels remain valid because they are ordinary non-empty strings.
- No task-specific hardcode was added to the runner core.
- The registry-presence lookup now uses `containsId(identifier)` for both `block` and `item`.

## Security Preserved

- `SecurePathResolver` unchanged.
- Absolute/external target paths still rejected.
- Target mod id validation unchanged.
- Target hash validation unchanged.
- JAR validity checks unchanged.
- Timeout / crash / missing-result semantics unchanged.
- Evidence layout unchanged.
- `REGISTRY_ENTRY_PRESENT` is still confined to a semantic presence lookup and does not expose a solution-revealing helper path.

## Compatibility with Previous Probes

- `block_state_probe` still works.
- `block_state_probe_with_signal` still works.
- Neighbor-update observation remains intact.
- `REGISTRY_ENTRY_PRESENT` is a separate observation contract and does not dispatch through the legacy block-state bridge.
- The harness still records structured runtime evidence.

## v0.5 Observation Contracts

The v0.5 acceptance layer can now describe observations such as:

- registry presence over `block` / `item`
- source + resource coupling
- server-side multi-file behavior

without requiring a dedicated task whitelist in the harness runner.

## Tests

Executed for this change:

- `python -m compileall src scripts tests`
- `.\.venv-l0fix\Scripts\python.exe -m pytest -q tests\unit\test_minecraft_batch_a.py tests\unit\test_minecraft_batch_b.py tests\unit\test_minecraft_batch_c.py tests\unit\test_benchmark_executor.py`
- `.\.venv-l0fix\Scripts\python.exe -m pytest -q`

## Results

- Compile: PASS
- Focused tests: PASS
- Full suite: 444 passed, 2 skipped
- Live Minecraft/provider API: not required for this harness-contract change

## Minecraft Revalidation

### PASS evidence persisted

- Observation: `REGISTRY_ENTRY_PRESENT`
- `registry_kind=block`
- `identifier=minecraft:stone`
- `MinecraftTestResult = PASS`
- `process_exit_code = 0`
- `process_timed_out = false`
- `server_started = true`
- `target_loaded = true`
- `target_origin_resolved = true`
- `target_sha_match = true`
- `observation_type = REGISTRY_ENTRY_PRESENT`
- `observed_identifier = minecraft:stone`
- `shutdown_requested = true`
- `Target mod = examplemod`
- `Target SHA = 2262c6b7747ee8c7cbdc58b92aea697f4c2c8d1e70af60e8a86366ba45209e26`
- Harness result: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-registry-pass-20260815-032449-278\execution\evidence\minecraft\f4-registry-pass\harness-result.json`
- Latest log: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-registry-pass-20260815-032449-278\execution\evidence\minecraft\f4-registry-pass\latest.log`
- `GRADLE_USER_HOME`: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-registry-pass-20260815-032449-278\execution\environment\gradle-user-home`

### Functional FAIL evidence persisted

- Observation: `REGISTRY_ENTRY_PRESENT`
- `registry_kind=block`
- `identifier=examplemod:definitely_missing_registry_entry`
- `MinecraftTestResult = FAIL`
- `process_exit_code = 0`
- `process_timed_out = false`
- `server_started = true`
- `target_loaded = true`
- `target_origin_resolved = true`
- `target_sha_match = true`
- `observation_type = REGISTRY_ENTRY_PRESENT`
- `observed_identifier = examplemod:definitely_missing_registry_entry`
- `reason = registry entry was not observed: block examplemod:definitely_missing_registry_entry`
- `shutdown_requested = true`
- Harness result: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-registry-fail-20260815-033139-518\execution\evidence\minecraft\f4-registry-fail\harness-result.json`
- Latest log: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-registry-fail-20260815-033139-518\execution\evidence\minecraft\f4-registry-fail\latest.log`
- `GRADLE_USER_HOME`: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-f4-registry-fail-20260815-033139-518\execution\environment\gradle-user-home`

### TargetBridge bypass

`REGISTRY_ENTRY_PRESENT` dispatches through:

- `runRegistryObservation`
- `isRegistryEntryPresent`
- `Registries.BLOCK.containsId(...)` / `Registries.ITEM.containsId(...)`

It does **not** call:

- `TargetBridge.applyProbeState`
- the legacy block-state probe path

`TargetBridge` remains exclusive to `LEGACY_BLOCK_STATE`.

## Limitations

- No live Minecraft provider run was needed for this harness-contract extension.
- The harness still uses the existing public bridge contract for `LEGACY_BLOCK_STATE` and does not invent a new generic runner architecture.
- The earlier `AccessDeniedException` was environmental to the sandbox/temp Gradle home, not a reproducible F4 product bug.
- The canonical project base remained unchanged.
- Future F5 acceptance logic may still need separate benchmark-layer adapters, but not a Harness redesign.

## Relation to F5 / F6

- F4 closes the observation-transport gap needed for v0.5 to reuse the current harness.
- F5 can build task-specific acceptance adapters on top of this harness contract.
- F6 can freeze the official v0.5 tasks without requiring a new Harness architecture.

## Final Verdict

The Minecraft harness is minimally extended and valid for v0.5 observation labels without a redesign.
F4 is implemented and validated with real Minecraft PASS and real Minecraft functional FAIL evidence.
