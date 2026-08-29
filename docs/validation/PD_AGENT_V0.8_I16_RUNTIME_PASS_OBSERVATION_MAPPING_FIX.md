# PD Agent v0.8 - I16 Runtime Observation Mapping Fix

## Historical finding

Execution `21d95008-58e2-46b5-9239-95ae14939ed2`, run
`abe36ac0-91b4-4e48-b06d-eea8c2993c9e`, reached a valid final artifact and a
Minecraft process/harness `PASS`. The productive runtime nevertheless
recorded zero observations and classified the result as
`RUNTIME_OBSERVATION_MAPPING_INVALID`.

The harness result contained a `REGISTRY_ENTRY_PRESENT` result for the block,
but the Python runner had no registry-result conversion branch. In addition,
the productive `MinecraftTestSpec` discarded the observation request list, so
the item observation could not be executed. This was an implementation gap,
not a task or specification gap.

## Contract and ownership

Runtime observations remain required evidence. A process or harness `PASS`
without all required structured observations is not a functional `PASS`.
The product-owned path is:

`ObservationRequest -> MinecraftTestSpec -> MinecraftTestRunner -> ObservationResult -> FabricRuntimeOrchestrator -> CompletionGate`

The runner now preserves explicit observation requests, maps registry harness
results into provider-neutral `ObservationResult` values, and executes one
controlled harness invocation per registry request when a spec contains more
than one request. The orchestrator consumes the structured results and keeps
the existing stale-evidence and failure-reconciliation guards.

## Validation

- The historical runtime #3 raw result had `target_loaded=true`,
  `target_sha_match=true`, `server_started=true`, and
  `functional_test_result=PASS`, but no structured observation records.
- The required IDs were `F6-T3:primary` and `F6-T3:item`.
- Focused runtime, runner, contract, and reconciliation tests pass.
- Negative mappings, stale evidence, target startup failures, generic crashes,
  timeouts, and infrastructure errors retain their existing guarded behavior.
- No live provider, Minecraft, or benchmark execution is part of this fix.
