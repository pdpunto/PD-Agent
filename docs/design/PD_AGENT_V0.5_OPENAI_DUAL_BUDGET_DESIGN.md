# PD Agent v0.5 - OpenAI Dual-Budget Design Delta

Status: DESIGN DELTA. No implementation or live execution is authorized by this document.

## Model-Turn Output Limit

The official OpenAI v0.5 candidate freezes `model_config.max_output_tokens` at
`16384`. This value is a configurable, provider-neutral model-turn setting,
not an OpenAI-specific core field and not an `ExecutionLimits` field.

The limit is supported by the observed PD Agent telemetry: 1,492 turns with
usage had p99 output of 594 tokens, a global maximum of 5,699, a maximum PASS
turn of 1,759 and a maximum Luna turn of 612. No legitimate turn reached 8K
or showed output truncation. The value is an initial evidence-based policy,
not a universal claim about future tasks.

For OpenAI Responses API, `max_output_tokens` covers the relevant output
budget including reasoning tokens. It must therefore leave enough room for
`reasoning=medium` while remaining compatible with the dual-budget guard.
The guard remains fail-closed when input plus the requested output reserve
does not fit either economic ceiling.

Changing this value requires a new configuration identity, semantic hash and
freeze; it must not mutate an existing execution or historical evidence.

## Purpose

Define the smallest architecture that allows a future official OpenAI v0.5
candidate to use both a candidate-execution ceiling of `$1.00` and an
independent per-attempt ceiling of `$0.10`, without changing the F9 dataset,
acceptance, prompts, runtime contracts, or scheduler methodology.

This delta extends the existing Luna pricing and accounting work. It does not
turn `run_luna_experimental.py` into an official scheduler and it does not
introduce billing, model routing, or provider tuning.

## Economic Contract

The ceilings are exact `Decimal` values:

- Global candidate-execution ceiling: `Decimal("1.00")`.
- Per-scheduled-attempt ceiling: `Decimal("0.10")`.

Before every physical provider request, including a retry, the request may be
allowed only when both conditions hold:

```text
attempt_accumulated + reservation <= attempt_ceiling
global_accumulated + reservation <= global_ceiling
```

Equality is allowed. Any excess blocks before the provider call. Both checks
are preventive, fail-closed, and use `Decimal` arithmetic.

The global budget belongs to one candidate execution and never resets within
that execution. The attempt budget belongs to one `BenchmarkScheduledAttempt`
and resets only when a new attempt begins. A replacement is a new economic
attempt. A new repetition's first attempt also starts at zero for the attempt
budget.

Retries remain inside the same scheduled attempt and are checked against both
ceilings. Existing pricing rules remain authoritative for uncached input,
cached input, cache-write, output, reasoning, long-context, service tier and
unknown usage handling.

## Ownership and Lifecycle

`BenchmarkScheduler` remains the authority for task/config cells, repetitions,
attempt numbering, replacements and canonical schedule identity.

`BenchmarkExecutionRunner` owns the integration boundary for economic state:

1. Load or create execution economic state.
2. Call `begin_attempt(scheduled_attempt_id)` before executing an attempt.
3. Keep the attempt identity unchanged across provider retries.
4. Settle each physical response through the shared pricing/accounting guard.
5. Close the attempt and persist its final economic summary.
6. Preserve global state when moving to a repetition or replacement.

The sole mutable authority is the runner-owned economic state store. The
scheduler owns attempt lifecycle and identity but no mutable economic ledger.
The guard calculates pricing and reservations through that authority; the
provider and aggregator do not maintain independent mutable ledger copies.

The guard and its state must not depend on `run_luna_experimental.py`. The
experimental runner may reuse the component, but remains isolated and
non-official. `run_v0_4.py` remains the methodological entry point for a
future official matrix.

## Persistence and Resume

Economic state is part of the candidate execution record and must be persisted
before and after every billable transition. At minimum it contains:

- schema/version;
- `execution_id`;
- global ceiling, accumulated cost and reserved cost;
- active scheduled attempt identity;
- attempt ceiling, accumulated cost and reserved cost;
- physical request and retry counters;
- pricing snapshot, hash, date and service tier;
- request-ledger version and reconciliation state;
- budget pause/block reason.

The shared global ceiling is persisted configuration rather than a fixed
loader constant. New sessions default to the historical `Decimal("0.25")`,
while callers may provide another positive ceiling. Existing ledgers may be
migrated only upward through the product API. Migration is atomic, preserves
spend, reservations, uncertainty, counters, dispatch history and attempt
state, and is rejected while reserved or uncertain money exists. A loader may
require `expected_global_ceiling` to fail closed on configuration drift. The
per-attempt ceiling remains `Decimal("0.10")`.

Resume must reconstruct the same global state and active attempt state. It may
not reset either budget, duplicate a settlement, or resend a request whose
economic result is uncertain.

## Request Crash Safety

Each request receives a stable ledger identity derived from at least:

```text
execution_id + scheduled_attempt_id + logical_turn + physical_request_ordinal
```

The reservation is persisted as `RESERVED` before the provider call. A valid
response is settled idempotently as `ACCOUNTED`, with the reservation released
and both accumulators updated.

The request transaction is strictly ordered:

1. identify the request;
2. calculate the reservation;
3. check attempt and global ceilings;
4. synchronously persist `RESERVED` through the economic state store;
5. confirm persistence;
6. return `ALLOW` from the guard;
7. allow `OpenAIProvider` to call `responses.create`.

If persisting `RESERVED` fails, the guard fails closed and no provider request
is allowed. Settlement to `ACCOUNTED` uses the same state authority.

If the process stops after the provider call but before settlement, the
request remains reserved and is marked uncertain/fail-closed. It must not be
automatically resent. Reconciliation is allowed only when existing provider
response identity is sufficient; no new provider API is invented by this
delta. Otherwise the execution pauses or blocks safely.

## Budget Pause Semantics

A preventive budget denial before a physical request uses exactly
`BenchmarkBatchStatus.BUDGET_PAUSED` with the contractual pause reason
`ECONOMIC_BUDGET_BLOCKED`. It is not a normal `BenchmarkRun` with status
`BLOCKED`:

- the scheduled attempt remains pending;
- no attempt is consumed;
- no replacement is generated;
- the reason is persisted in execution state;
- no new `BUDGET_BLOCKED` batch status is introduced.

This does not alter `RATE_LIMIT_PAUSED`. Real provider, infrastructure,
harness and execution-limit blocks retain the existing `BLOCKED` and
replacement semantics. `INVALID` remains reserved for contamination,
contradictory evidence or real methodological invalidity. `COMPLETED + FAIL`
remains a valid run and does not create a replacement.

## Evidence and Aggregation

Per-attempt evidence must include unique settled request costs, token
breakdowns, reservations, retries, physical requests and final attempt cost.
Execution evidence must include the global accumulated and remaining budget.
Secrets, API keys and raw encrypted reasoning must never be persisted.

Aggregators must not add repeated accumulated snapshots. Cost totals derive
from unique ledger settlements or unambiguous final per-request/per-run costs.
The global total is an execution-level value, not the sum of repeated metadata
snapshots.

`reconciliation_state=CLEAR` means that no reservation or economic uncertainty
is pending. It does not guarantee that another request fits the remaining
global or active-attempt ceiling. Preflight must use the guard's preventive
reservation projection before reporting a dispatch as economically permitted.

## Out of Scope

- Model Router.
- Commercial billing.
- Provider/model tuning.
- Dataset, prompt, acceptance or fixture changes.
- Fabric Agent, Minecraft, runtime or Semantic Repair behavior changes.
- F9 historical execution changes.
- Converting the experimental Luna runner into the official scheduler.

## Economic Schema Compatibility

The official dual-budget candidate requires a new explicit economic schema
version. An execution or resume missing that version, either ceiling,
accumulator, reservation, active attempt, ledger, pricing snapshot/hash or
reconciliation state is rejected as incompatible. Missing economic fields are
never interpreted as zero, migrated heuristically or reconstructed from old
evidence. Historical executions remain valid historical evidence but are not
dual-budget resumable unless they already contain the exact compatible schema.
