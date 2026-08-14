# PD Agent v0.5 Minecraft Harness Capability Validation

Status: PASS
Date: 2026-08-14

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Baseline commit audited: `10e295dd1a86415a4ae875b4cbafe5819d099b23`
- HEAD / origin at audit start: `10e295dd1a86415a4ae875b4cbafe5819d099b23`
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

### B. Required Minimal Extension

- The harness `test_id` contract must remain generic and not be locked to the two v0.4 probe labels.
- v0.5 acceptance can carry an observation label as metadata without forcing the harness to know the task catalog.

### C. Would Require Redesign

- A new generic harness architecture.
- Hardcoded task-specific runtime logic in the runner core.
- A solution-revealing helper path in the target fixture.

No item in the audited v0.5 requirement set required category C.

## Gap Identified

The only contract gap found was the v0.4-era whitelist in `HarnessConfig.java`:

- `block_state_probe`
- `block_state_probe_with_signal`

That whitelist was acceptable for v0.4 but too narrow for v0.5, where the harness should accept a generic observation label carried by the benchmark/acceptance layer.

## Extension Applied

The harness contract was minimally generalized:

- `test_id` remains required and non-empty.
- The closed whitelist was removed.
- Existing v0.4 probe labels remain valid because they are ordinary non-empty strings.
- No task-specific hardcode was added to the runner core.

## Security Preserved

- `SecurePathResolver` unchanged.
- Absolute/external target paths still rejected.
- Target mod id validation unchanged.
- Target hash validation unchanged.
- JAR validity checks unchanged.
- Timeout / crash / missing-result semantics unchanged.
- Evidence layout unchanged.

## Compatibility with Previous Probes

- `block_state_probe` still works.
- `block_state_probe_with_signal` still works.
- Neighbor-update observation remains intact.
- The harness still records structured runtime evidence.

## v0.5 Observation Contracts

The v0.5 acceptance layer can now describe observations such as:

- registry presence
- source + resource coupling
- server-side multi-file behavior

without requiring a dedicated task whitelist in the harness runner.

## Tests

Executed for this change:

- `python -m compileall src scripts tests`
- `.\.venv-l0fix\Scripts\python.exe -m pytest -q tests\unit\test_minecraft_batch_b.py tests\unit\test_minecraft_batch_c.py tests\unit\test_v0_5_acceptance_contract.py tests\unit\test_v0_5_project_base.py`
- `.\.venv-l0fix\Scripts\python.exe -m pytest -q`

## Results

- Compile: PASS
- Focused tests: PASS
- Full suite: PASS
- Live Minecraft/provider API: not required for this harness-contract change

## Limitations

- No live Minecraft provider run was needed for this harness-contract extension.
- The harness still uses the existing public bridge contract and does not invent a new generic runner architecture.
- Future F5 acceptance logic may still need separate benchmark-layer adapters, but not a Harness redesign.

## Relation to F5 / F6

- F4 closes the observation-transport gap needed for v0.5 to reuse the current harness.
- F5 can build task-specific acceptance adapters on top of this harness contract.
- F6 can freeze the official v0.5 tasks without requiring a new Harness architecture.

## Final Verdict

The Minecraft harness is minimally extended and valid for v0.5 observation labels without a redesign.
