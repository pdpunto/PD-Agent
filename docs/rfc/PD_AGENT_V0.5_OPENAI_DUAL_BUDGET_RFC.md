# PD Agent v0.5 - OpenAI Dual-Budget RFC Delta

Status: RFC DELTA. This contract is for a future offline-validated official
candidate. No API or live matrix execution is authorized.

## Contract

One candidate execution has a global hard ceiling of `Decimal("1.00")`.
Every scheduled attempt has an independent hard ceiling of
`Decimal("0.10")`.

For every physical request and retry, the guard computes a conservative
reservation and allows the call only if:

```text
attempt_accumulated + reservation <= Decimal("0.10")
global_accumulated + reservation <= Decimal("1.00")
```

The comparisons are inclusive. Any failure blocks before the provider call.
Pricing uses the existing Luna pricing snapshot and accounting rules, with
fail-closed handling for unknown or incoherent usage.

## State Model

Pricing/accounting, execution economic state, active-attempt state and request
reservation/settlement are separate concepts, even if the smallest
implementation stores them in one versioned persistence object.

The persisted economic state contains:

```text
schema_version
execution_id
global_ceiling
global_accumulated
global_reserved
active_attempt_id
attempt_ceiling
attempt_accumulated
attempt_reserved
physical_request_count
provider_retry_count
pricing_snapshot/hash/date
service_tier
ledger_version
reconciliation_state
```

`begin_attempt(attempt_id)` verifies the scheduled identity, resets only
attempt accumulated/reserved cost, and preserves the global values. The same
attempt identity is retained across retries. Replacements receive a new
attempt identity and a fresh attempt budget.

## Request Ledger

The minimum stable request key derives from:

```text
execution_id
scheduled_attempt_id
logical_turn
physical_request_ordinal
```

The ledger must persist `RESERVED` before the provider call and transition it
idempotently to `ACCOUNTED` after validating usage and deriving cost. A request
already accounted must never be settled again.

The runner-owned economic state store is the sole mutable ledger authority.
The scheduler owns attempt identity only, and the provider and aggregator do
not keep independent mutable economic copies. The guard must complete this
synchronous transaction before returning `ALLOW`:

1. identify the request;
2. calculate reservation;
3. check attempt ceiling;
4. check global ceiling;
5. persist `RESERVED`;
6. confirm persistence;
7. return `ALLOW`.

`OpenAIProvider` may call `responses.create` only after `ALLOW`. If the
`RESERVED` write fails, the guard blocks fail-closed and no provider request is
made. Settlement to `ACCOUNTED` is persisted through the same authority.

If execution stops after sending a request but before settlement, the ledger
remains reserved and enters an uncertain fail-closed state. The runner must not
automatically resend that request. Safe reconciliation is allowed only from
existing response identity/evidence. Without that evidence, pause or block;
do not invent a billing or reconciliation endpoint.

## Provider and Retry Rules

The existing `OpenAIProvider` remains the physical request boundary. The
budget guard runs immediately before `responses.create`, including each retry.

Retries:

- use the same scheduled attempt;
- receive separate request-ledger entries;
- consume the same attempt and global ceilings;
- cannot bypass a previous reservation;
- remain fail-closed when usage is missing or incoherent.

## Scheduler and Runner

`BenchmarkScheduler` owns canonical attempts, repetition indexes, replacements
and schedule identity. `BenchmarkExecutionRunner` owns economic lifecycle
integration and persistence. The official runner must not create a parallel
attempt/replacement implementation.

`run_v0_4.py` remains the official methodological entry point and may receive
the reusable guard through a small integration layer. The current
`run_luna_experimental.py` remains a one-attempt experimental smoke launcher.
It must not write official repetition, attempt, replacement or aggregate
evidence.

## Budget Pause Contract

If a reservation exceeds either remaining ceiling before the provider call:

- persist `BenchmarkBatchStatus.BUDGET_PAUSED` with
  `pause_reason=ECONOMIC_BUDGET_BLOCKED`;
- preserve the exact scheduled attempt as pending;
- consume no attempt;
- create no replacement;
- emit no normal `BLOCKED` benchmark run.

`BUDGET_BLOCKED` is not a batch status in this contract. It is only the
economic pause reason/code.

This state is distinct from `RATE_LIMIT_PAUSED`, which retains its current
provider-quota semantics. Normal `BLOCKED` and `INVALID` runs continue to use
existing replacement rules. `COMPLETED + FAIL` remains valid and does not
generate a replacement.

## Manifest and Evidence Contract

The manifest freezes provider/model, service tier, pricing snapshot/hash/date,
accounting mode, both ceilings, retry policy and economic schema version.

Execution state persists global and active-attempt accumulators/reservations,
request ledger, reconciliation state and pause reason. Run evidence persists
unique request settlements, input/cached/uncached/cache-write/output/reasoning/
total tokens, logical turns, physical requests, retries, attempt cost and
global budget metadata.

Raw secrets and encrypted reasoning content are prohibited.

## Economic Schema Compatibility

The official candidate uses a new explicit economic schema version. Resume
must reject an execution when the schema version or any required economic
field is missing, including ceilings, accumulated/reserved values, active
attempt, ledger, pricing snapshot/hash or reconciliation state. There is no
silent migration, zero default, heuristic reconstruction or reuse of an
incompatible historical manifest. Historical evidence remains valid evidence
but is not resumable under this contract unless its economic schema is exactly
compatible.

## Aggregation Contract

Aggregation must use unique request settlements or final unambiguous run costs.
It must never sum repeated `global_accumulated` snapshots from multiple runs or
responses. Report separately:

- cost per physical request;
- cost per scheduled attempt;
- cost per valid run;
- cost per PASS;
- global candidate-execution cost.

## Compatibility and Freeze

This delta does not change F9 Gemini evidence, task prompts, acceptance,
dataset, fixture, runtime limits, Semantic Repair, Fabric behavior or
scheduler identity rules. A future OpenAI candidate needs its own frozen
config/manifest and must pass offline drift checks before any API call.

## Acceptance Boundary

Implementation is not complete until the dual-budget, lifecycle, persistence,
crash-safety, pause, aggregation and redaction tests described by the IMP all
pass offline. This RFC does not authorize live execution.
