# PD Agent v0.5 - OpenAI Dual-Budget Design Delta

Status: DESIGN DELTA. No implementation or live execution is authorized by this document.

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

If the process stops after the provider call but before settlement, the
request remains reserved and is marked uncertain/fail-closed. It must not be
automatically resent. Reconciliation is allowed only when existing provider
response identity is sufficient; no new provider API is invented by this
delta. Otherwise the execution pauses or blocks safely.

## Budget Pause Semantics

A preventive budget denial before a physical request is not a normal
`BenchmarkRun` with status `BLOCKED`:

- the scheduled attempt remains pending;
- no attempt is consumed;
- no replacement is generated;
- the reason is persisted in execution state;
- the candidate execution enters an unambiguous budget-paused/blocked state.

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

## Out of Scope

- Model Router.
- Commercial billing.
- Provider/model tuning.
- Dataset, prompt, acceptance or fixture changes.
- Fabric Agent, Minecraft, runtime or Semantic Repair behavior changes.
- F9 historical execution changes.
- Converting the experimental Luna runner into the official scheduler.
