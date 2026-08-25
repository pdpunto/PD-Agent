# PD Agent v0.5 - OpenAI Economic Recovery RFC

Status: RFC DELTA. Implementation and live execution require a later,
separate authorization.

## Ownership

- `LunaBudgetGuard` owns reservation math and settlement transitions.
- `LunaEconomicStateStore` owns durable economic state.
- `OpenAIProvider` owns provider request/response metadata and sanitized
  failure capture.
- `BenchmarkExecutionRunner` owns pause propagation and resume validation.
- `BenchmarkScheduler` owns canonical attempt/repetition/replacement
  identity.
- Collector/aggregator consume immutable evidence and never maintain a second
  mutable ledger.

## State machine

```text
                 response + valid usage
RESERVED --------------------------------> ACCOUNTED
   |                                           |
   | explicit pre-dispatch proof              | idempotent replay
   v                                           v
RELEASED                                    ACCOUNTED
   |
   | dispatch or dispatch uncertainty,
   | missing/invalid usage, post-dispatch error
   v
UNCERTAIN_CONSUMED (terminal)
```

`actual_billed_cost` is a Decimal when known and `UNKNOWN` otherwise.
`conservative_budget_consumed` is always a Decimal for
`ACCOUNTED` and `UNCERTAIN_CONSUMED`; it is zero for `RELEASED`.

## Physical request lifecycle

1. Construct the stable request identity from execution, scheduled attempt,
   logical turn, and physical ordinal.
2. Calculate the worst-case reservation using the frozen pricing snapshot and
   configured `max_output_tokens=16384`.
3. Validate global and attempt ceilings with Decimal arithmetic.
4. Persist `RESERVED` synchronously.
5. Mark dispatch state `READY_TO_DISPATCH`, then call the provider.
6. Persist provider metadata and sanitized failure/response metadata as soon
   as the adapter boundary returns or raises.
7. For valid usage, settle once as `ACCOUNTED`.
8. For proven pre-dispatch failure, settle once as `RELEASED`.
9. Otherwise settle once as `UNCERTAIN_CONSUMED` and pause.

The provider adapter must not discard the original exception when invoking the
fail-closed guard. If the SDK exposes no response identity, that fact is
persisted explicitly; it is not converted into a successful or zero-cost
response.

## Proposed schema version

The recovery schema is version `2`; schema `1` is not migrated heuristically.
Each ledger entry adds:

```text
physical_request_id
reservation_id
dispatch_state
failure_phase
provider_request_id
provider_response_id
response_status
http_status
sanitized_exception_type
sanitized_original_failure
usage_presence
usage_validation
settlement_state
reserved_amount
actual_billed_cost
conservative_budget_consumed
pre_dispatch_at
post_dispatch_at
```

The execution state records schema version, execution identity, both ceilings,
accounted cost, uncertain conservative cost, active reservations, active
attempt, physical/retry counters, pricing snapshot/hash, and reconciliation
state. Missing required fields reject resume.

## Budget formulas

```text
reservation = worst_case(input_estimate, max_output_tokens, pricing)
global_consumed = global_accounted + global_uncertain + global_reserved
attempt_consumed = attempt_accounted + attempt_uncertain + attempt_reserved
allow iff global_consumed + reservation <= global_ceiling
       and attempt_consumed + reservation <= attempt_ceiling
```

Equality is allowed. An uncertain amount remains in the corresponding
consumed total until authoritative reconciliation, which is outside this
delta.

## Retry and pause protocol

Only an explicitly proven pre-dispatch failure can release a reservation and
enter the ordinary retry path. All other failures are terminal for that
physical operation. The runner maps `UNKNOWN_BILLABLE_USAGE` and
`UNCERTAIN_CONSUMED` to `BUDGET_PAUSED` with
`pause_reason=ECONOMIC_BUDGET_BLOCKED`, preserves the exact pending scheduled
item, consumes no scheduler attempt, and creates no replacement.

The pending scheduler item must not be treated as permission to resend the
uncertain request. The current execution is paused until reconciliation or is
rejected for resume.

## Resume validation

Resume must reject:

- schema mismatch or missing economic fields;
- execution/config/dataset/fixture/commit drift;
- active `UNCERTAIN_CONSUMED` without reconciliation evidence;
- physical counter/ledger inconsistency;
- missing pending item for a non-complete pause;
- a pending item whose request identity collides with a prior physical record.

The 420d execution fails this contract by design and remains terminal.

## Provider-neutral and provider-specific evidence

Core fields and settlement states are provider-neutral. OpenAI adapter fields
may include Responses status, request/response IDs, usage details,
`cached_tokens`, `cache_write_tokens`, `reasoning_tokens`, and SDK exception
type. They remain redacted and are not used to create a second scheduler.

## Aggregation and classification

`UNCERTAIN_CONSUMED` is excluded from valid, PASS, functional FAIL, and
INVALID counts. It is reported as an economic/provider-observability block.
Aggregators use unique settlement records and never sum repeated cumulative
budget snapshots.

## Compatibility

No historical execution is rewritten. F9 Gemini, dataset, acceptance,
fixture, prompts, limits, scheduler seed, and model configuration remain
unchanged. A future candidate needs a new freeze after implementation and
offline validation.
