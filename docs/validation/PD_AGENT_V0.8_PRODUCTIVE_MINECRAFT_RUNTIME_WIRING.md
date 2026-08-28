# PD Agent v0.8 - Productive Minecraft Runtime Wiring

## Finding

The I16 preflight identified that normal Fabric orchestration exposed an
optional functional-validator port but did not provide a product-owned path to
the Minecraft harness. The complete path was therefore available only through
the benchmark executor.

The finding was classified as `IMPLEMENTATION_GAP_ONLY`; the Design, RFC, and
IMP already require runtime validation outside benchmark ownership.

## Corrected flow

`FabricNormalOrchestrator -> ProductiveMinecraftFunctionalValidator`
`-> FabricRuntimeOrchestrator -> MinecraftRunner -> structured evidence`
`-> RunState/TaskProgressLedger -> CompletionGate`

The adapter binds current source, build, artifact, contract, runtime identity,
and failure facts before invoking the runner. Invalid or stale artifacts do not
reach Minecraft. Runtime PASS marks its requirement satisfied with current
evidence; runtime failure remains available for bounded repair and
reconciliation.

`RunState` remains the only state machine and `CompletionGate` remains the sole
completion authority. No product module imports benchmark internals.

## Ownership

Product code owns the generic runtime boundary and can receive any compatible
`MinecraftRunner`. Benchmark remains a consumer/adapter for benchmark task
translation, scheduling, and reporting.

## Offline validation

The new regressions cover normal product-owned validation, invalid artifact
gating, runtime failure facts, and the no-runtime path using controlled doubles.
No provider, API, Minecraft live run, or benchmark live run is used.
