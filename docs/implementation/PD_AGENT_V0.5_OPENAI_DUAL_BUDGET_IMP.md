# PD Agent v0.5 - OpenAI Dual-Budget Implementation Delta

Status: IMPLEMENTATION PLAN. Do not implement or execute live in this batch.

## Implementation Principles

Extend the existing Luna pricing/accounting guard and official benchmark
runner lifecycle. Do not create a second benchmark scheduler, do not reuse F9
evidence, and do not turn `run_luna_experimental.py` into an official runner.

The implementation must preserve the existing pricing rules for uncached
input, cached input, cache-write, output, reasoning, long-context, service
tier, retries and fail-closed usage validation.

## Lot 1 - Economic State and Ledger

### Scope

Add a serializable economic state and request ledger to the reusable Luna
budget component. Support both `Decimal("1.00")` global and
`Decimal("0.10")` attempt ceilings.

### Expected modules

- `src/pd_agent/experimental/luna_budget.py`, extended or split only if the
  existing public API requires it.
- `tests/unit/test_luna_budget.py`.

### Acceptance

- Both ceilings allow an equality boundary.
- Either ceiling blocks a fractional excess before the provider call.
- Decimal arithmetic remains exact.
- Reservations and settlements are represented independently.
- Request ledger states include `RESERVED`, `ACCOUNTED` and uncertain
  fail-closed handling.

### Boundary and rollback

Commit the state/ledger model and unit tests separately. Roll back only the new
economic component if its tests fail; do not touch scheduler or F9 evidence.

## Lot 2 - Persistence and Resume

### Scope

Persist economic state alongside the candidate manifest and execution state.
Reconstruct global budget, active attempt, attempt budget and ledger on resume.

### Expected modules

- `src/pd_agent/benchmark/models.py`.
- `src/pd_agent/benchmark/runner.py`.
- manifest/state serialization tests.

### Acceptance

- Global cost persists across attempts and repetitions.
- A new attempt resets only attempt cost.
- A replacement receives a fresh attempt budget.
- Resume preserves global cost and active attempt cost.
- No settlement is duplicated after resume.
- An uncertain post-request state is not automatically resent.
- Official resume rejects missing or incompatible economic schema fields; it
  does not migrate them or treat them as zero.

### Boundary and rollback

Commit schema and resume behavior together. Require a new explicit economic
schema version and reject old or incomplete manifests with an explicit resume
compatibility error. Never migrate silently, interpret missing fields as zero,
or reconstruct economic state heuristically.

## Lot 3 - Official Runner Lifecycle and Budget Pause

### Scope

Integrate `begin_attempt`, request reservation, settlement and attempt closing
into `BenchmarkExecutionRunner` while preserving `BenchmarkScheduler` as the
attempt/replacement authority.

### Expected modules

- `src/pd_agent/benchmark/runner.py`.
- `src/pd_agent/benchmark/scheduler.py` only if a narrow lifecycle hook is
  proven necessary.
- runner and scheduler regression tests.

### Acceptance

- Every physical request and retry is checked against both budgets.
- Preventive budget block persists
  `BenchmarkBatchStatus.BUDGET_PAUSED` with
  `pause_reason=ECONOMIC_BUDGET_BLOCKED` and preserves the exact pending
  scheduled attempt.
- Budget block consumes no attempt and creates no replacement.
- Budget block creates no normal `BenchmarkRun`.
- Normal `BLOCKED`/`INVALID` replacement behavior remains unchanged.
- `COMPLETED + FAIL` remains valid without replacement.
- `RATE_LIMIT_PAUSED` semantics do not regress.

### Boundary and rollback

Commit lifecycle and pause semantics as one boundary. Roll back the wiring
without reverting the validated scheduler contracts if offline regression
fails.

## Lot 4 - OpenAI Provider Integration

### Scope

Pass the shared guard into the official OpenAI provider path and ensure the
guard executes immediately before every `responses.create`, including retry
requests.

### Expected modules

- `scripts/benchmark/run_v0_4.py`.
- `src/pd_agent/providers/openai_provider.py` only for a proven seam or
  request-identity propagation.
- provider and runner tests.

### Acceptance

- Provider and model are frozen and validated before launch.
- No physical request occurs before a successful dual reservation.
- `RESERVED` is synchronously persisted by the runner-owned economic state
  store before the guard returns `ALLOW`.
- A failed `RESERVED` persistence blocks fail-closed without a provider call.
- Retries use the same attempt identity and separate ledger entries.
- Missing usage remains fail-closed.
- No secret or raw encrypted reasoning is persisted.

### Boundary and rollback

Commit provider wiring separately from the experimental smoke launcher. The
experimental runner must remain isolated and non-official.

## Lot 5 - Economic Evidence and Aggregation

### Scope

Persist unique request settlements and expose per-request, per-attempt,
per-valid-run, per-PASS and execution-global cost metrics.

### Expected modules

- `src/pd_agent/benchmark/collector.py`.
- `src/pd_agent/benchmark/aggregator.py`.
- evidence and redaction tests.

### Acceptance

- Aggregation does not sum repeated accumulated snapshots.
- Cost totals reconcile with unique ledger settlements.
- Token categories include cached, uncached, cache-write, output and
  reasoning without double-counting reasoning.
- Pricing snapshot/hash and budget metadata are traceable.

### Boundary and rollback

Commit evidence schema and aggregation together. If accounting reconciliation
fails, retain the ledger and block official launch rather than emitting a
partial economic aggregate.

## Lot 6 - Offline Regression and Prelaunch

### Scope

Run the complete offline validation after Lots 1-5 and prepare, but do not
execute, the future candidate.

### Acceptance

- Focused dual-budget tests pass.
- Full suite passes.
- `compileall` passes.
- `git diff --check` passes.
- Freeze, config, manifest, state, evidence and redaction checks pass.
- API calls remain zero.
- Fresh LaunchRoot and ExecutionRoot are verified without launching.

### Boundary and rollback

Do not create or resume a live execution in this lot. If any check fails, stop
at prelaunch and preserve all evidence for diagnosis.

## Required Test Contract

The implementation must cover:

1. Both budgets allow.
2. Attempt blocks while global allows.
3. Global blocks while attempt allows.
4. Both block.
5. Exact equality allows.
6. Smallest over-limit fraction blocks.
7. Retry checks both ceilings.
8. New attempt resets only attempt state.
9. Replacement resets only attempt state.
10. Global persists across attempts and repetitions.
11. Resume preserves global state.
12. Resume preserves active attempt state.
13. Reservation is persisted before provider call.
14. Settlement is idempotent.
15. No double accounting after resume.
16. Crash after request and before settlement is fail-closed.
17. Uncertain request is not automatically resent.
18. Unknown usage blocks safely.
19. Pricing reservation is conservative.
20. Reasoning tokens are not charged twice.
21. Cached input and cache-write are correct.
22. Long-context pricing is correct.
23. Decimal exactness holds.
24. Manifest freezes economic settings.
25. Execution state reconstructs economic state.
26. Missing economic schema fields reject resume explicitly.
27. Evidence contains unique settlements and no secrets.
28. Budget pause uses exactly `BUDGET_PAUSED` and consumes no attempt.
29. Budget pause creates no replacement or normal `BenchmarkRun`.
30. Normal `BLOCKED`/`INVALID` replacement semantics remain.
31. `COMPLETED + FAIL` remains valid without replacement.
32. `RATE_LIMIT_PAUSED` remains exact and resumable.

## Prelaunch Gate

The official candidate remains blocked until all six lots required for the
candidate are validated offline and a separate authorization is provided.
This document authorizes no OpenAI API call, Gemini API call, smoke, F9
resume, commit of implementation code or change to dataset/acceptance.
