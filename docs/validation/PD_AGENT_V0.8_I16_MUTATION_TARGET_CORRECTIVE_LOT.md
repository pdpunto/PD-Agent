# PD Agent v0.8 - I16 Mutation Target Corrective Lot

## Scope

This corrective lot addresses the I16 LIVE budget stop from execution
`5f981eb6-3229-436c-a7a8-2c7da90855de`. The historical execution remains
unchanged and no second LIVE run is part of this lot.

## Root Cause

The I16 driver passed `required_resources[].path` values in their logical
artifact namespace (`assets/...` and `data/...`) while the runtime progress
ledger records workspace-relative physical paths under the inspected resource
root (`src/main/resources/...`). The recorder compares exact paths. Therefore
the Java source target could complete, but the language and recipe targets
remained pending even after the corresponding files were edited.

The live language file also lacked the required
`item.examplemod.server_core` assertion. File existence alone is not semantic
completion. The budget guard correctly stopped the bounded run before another
provider request; this lot does not reinterpret that economic stop.

## Fix

`run_i16.py` now uses the same neutral
`resolve_logical_resource_path(ProjectSnapshot, logical_path)` contract used by
the benchmark adapter, after inspecting the fixture/project resource roots.
The I16 runtime also wires `PreBuildWorkspaceValidator` with those inspected
roots and validates the task's resource assertions, including both language
keys and the recipe assertions. No dependency from product code to
`BenchmarkExecutor` was introduced.

## Offline Evidence

The regression matrix demonstrates:

- source edits reconcile `role:source`;
- logical language and recipe paths resolve to their physical workspace paths;
- an incomplete language file remains `REPAIRABLE_FAIL`;
- adding `item.examplemod.server_core` produces `PASS` and permits PRE_BUILD;
- unsafe, external and ambiguous resource roots remain fail-closed through the
  existing path helper tests.

This preserves the historical state: with the incomplete language file,
`pending_mutation_targets` contains the unresolved language target and PRE_BUILD
is not permitted. With all targets and semantic assertions satisfied, pending
targets are empty and PRE_BUILD is allowed.

## Validation Boundary

This lot is offline only. API calls, provider calls, Minecraft runs and live
benchmarks are `0`. No dataset, acceptance, prompt, model, fixture, scheduler
or historical evidence was changed. The fix is expected to reduce redundant
turns by exposing the correct physical targets and enabling the semantic gate
to make an objective transition, but no live cost claim is made here.
