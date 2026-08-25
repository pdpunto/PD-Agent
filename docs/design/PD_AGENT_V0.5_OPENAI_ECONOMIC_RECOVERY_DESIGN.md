# PD Agent v0.5 - OpenAI Economic Recovery Design

Status: DESIGN DELTA. This document defines a future implementation; it does
not authorize API calls, resume, or changes to historical evidence.

## Problem

Execution `420d24f1-67ac-43b360-5bd2782e360a` reserved
`Decimal("0.0223195500")`, performed one physical OpenAI request, and then
lost billable-usage observability. The execution correctly paused fail-closed,
but its evidence cannot distinguish a missing provider usage payload from an
SDK, transport, or response-validation failure.

The current `LunaBudgetGuard.on_failure_without_usage()` path records
`UNKNOWN_BILLABLE_USAGE` and replaces the original provider exception. The
recovery delta must preserve uncertainty without treating it as zero cost.

## Goals and invariants

- Keep `actual_billed_cost` separate from
  `conservative_budget_consumed`.
- Prevent every uncertain reservation from becoming available again.
- Keep the global ceiling at `Decimal("1.00")` and the attempt ceiling at
  `Decimal("0.10")`.
- Protect every physical request and retry with both ceilings.
- Preserve scheduler identity, pending items, repetitions, attempts, and
  replacement semantics.
- Make the original sanitized provider/SDK failure auditable.
- Keep the economic ledger provider-neutral; provider details remain in the
  adapter evidence.
- Reject unsafe resume rather than silently repeating a possibly billable
  request.

## Economic states

Each reservation has exactly one terminal settlement state:

- `RESERVED`: persisted before `ALLOW`; no provider call is permitted before
  this state is durable.
- `ACCOUNTED`: valid usage was received and the contractual cost was derived.
- `RELEASED`: explicit evidence proves the request was never dispatched and
  therefore could not be billable.
- `UNCERTAIN_CONSUMED`: dispatch occurred or may have occurred, but actual
  usage/cost cannot be liquidated. This state is terminal for the reservation.

`UNCERTAIN_CONSUMED` stores `actual_billed_cost=UNKNOWN` and retains the
reservation as conservative consumption. It must never be released, reused,
or settled twice.

## Cost semantics

For enforcement:

```text
consumed = accounted_cost + uncertain_conservative_cost + active_reservations
```

All monetary values use `Decimal`. For the 420d incident:

```text
actual_billed_cost = UNKNOWN
conservative_budget_consumed = Decimal("0.0223195500")
```

This does not claim that OpenAI billed exactly that amount. It only prevents
the execution from spending that budget twice.

## Request and retry behavior

The guard persists `RESERVED` before `OpenAIProvider.responses.create()`.
Only an explicit pre-dispatch proof may transition to `RELEASED` and permit a
normal retry. A generic SDK exception, timeout, connection ambiguity,
response-validation error after dispatch, or missing usage is not such proof;
it transitions to `UNCERTAIN_CONSUMED` and stops retries for that operation.

Retries retain the same scheduled attempt but have their own physical request
ordinal and reservation identity. No retry is created after an uncertain
dispatch.

## Scheduler and attempt semantics

`BenchmarkScheduler` remains the authority for canonical scheduled-attempt
identity, repetition numbering, attempt numbering, and replacements.
`BenchmarkExecutionRunner` remains the owner of economic state integration.

An economic pause leaves the scheduled item pending and creates no
replacement. This means the scheduler attempt is not recorded as a completed
benchmark attempt, while the economic reservation is nevertheless consumed
by `UNCERTAIN_CONSUMED`. These are deliberately different facts. The pending
item cannot be executed again in the same execution unless a future,
explicitly specified reconciliation contract proves that the original
request was never dispatched.

`UNCERTAIN_CONSUMED` is not a valid run, functional FAIL, or INVALID result.
It is an economic/provider-observability block and pauses the candidate.

## Resume

Resume must validate execution identity, commit, dataset/config/fixture,
scheduler state, schema version, and the economic ledger. A ledger containing
`UNCERTAIN_CONSUMED` without authoritative reconciliation must be rejected.
It must not resend the pending request, reset either budget, release the
reservation, consume a replacement, or import another execution's evidence.

Execution 420d remains terminal historical evidence and is never retroactively
repaired or made resumable by this delta.

## Observability contract

Every physical request record must include, when available:

- internal `physical_request_id` and `reservation_id`;
- execution, run, scheduled-attempt, logical-turn, and ordinal identity;
- provider, model, service tier, and pre/post timestamps;
- dispatch state and failure phase;
- provider request/response IDs and response/HTTP status;
- sanitized exception type and original failure summary;
- usage presence and validation result;
- settlement state;
- reserved amount, `actual_billed_cost`, and
  `conservative_budget_consumed`.

No API key, Authorization header, credential, raw encrypted reasoning, or
unredacted sensitive header may be persisted.

## Acceptance boundary

The delta is accepted only when offline tests prove the state machine,
accounting, retry, scheduler, resume, evidence, and redaction contracts. It
does not change dataset, prompts, acceptance, fixtures, F9 evidence, runtime
limits, or provider/model selection.

## Non-goals

- No billing API or invented provider reconciliation endpoint.
- No retroactive repair of 420d.
- No cross-execution run mixing.
- No change to F9 Gemini methodology.
- No Model Router, tuning, or product behavior change.
