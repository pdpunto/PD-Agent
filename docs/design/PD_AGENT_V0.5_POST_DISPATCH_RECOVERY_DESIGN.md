# PD Agent v0.5 - Post-Dispatch Recovery Design

Status: DESIGN DELTA. This document defines a future provider-neutral recovery
capability. It authorizes no production code, API call, resume, or rewrite of
historical evidence.

## 1. Scope

The official OpenAI candidate
`84df7f4b-c82d-4f95-b951-d5eafab79530` is historical evidence. Its first
physical request ended with an ambiguous `APIConnectionError`; the economic
reservation was correctly preserved as `UNCERTAIN_CONSUMED`.

The design separates two facts that are currently coupled:

- economic recovery: preserve exposure and prevent double accounting;
- functional recovery: obtain a valid provider response or abandon safely.

The design does not claim exactly-once provider inference. OpenAI provider
idempotency, response retention, lookup, and billing reconciliation must be
verified before any implementation uses them.

## 2. Goals

- Preserve the original physical dispatch identity and conservative exposure.
- Recover an already available response without creating a new inference.
- Permit at most one bounded recovery reissue when policy and budget allow it.
- Keep scheduled attempt, repetition, and replacement identity unchanged.
- Never invent an `AgentResponse`.
- Persist enough redacted evidence for later review.
- Fail closed on crash, malformed state, missing capability, or ambiguity.

## 3. Mandatory invariants

1. `UNCERTAIN_CONSUMED` never becomes available automatically.
2. A new physical request never reuses another request's reservation.
3. Every physical dispatch has its own identity and accounting record.
4. A timeout or connection error after dispatch does not prove non-delivery.
5. `X-Client-Request-Id` is correlation only, never an idempotency key without
   an explicit provider guarantee.
6. Billable hidden SDK retries remain disabled.
7. Retrieval of an existing response is not a new inference.
8. A reissue is a new physical request with a new reservation.
9. Recovery does not silently increment attempt or create a replacement.
10. Recovery limits are explicit and finite.
11. Crash recovery is conservative and fail closed.
12. Legacy executions do not gain retroactive recovery behavior.

## 4. Conceptual state dimensions

No mega-enum is introduced. Four dimensions are kept separate:

### DispatchState

`PREPARED`, `DISPATCH_STARTED`, `NOT_DISPATCHED`, `DISPATCHED`,
`REMOTE_OUTCOME_UNKNOWN`, `RESPONSE_OBSERVED`.

### EconomicState

The existing settlement states remain authoritative:
`RESERVED`, `ACCOUNTED`, `RELEASED`, `UNCERTAIN_CONSUMED`.

### FunctionalState

`WAITING`, `RESPONSE_AVAILABLE`, `RESPONSE_RECOVERABLE`, `RESPONSE_MISSING`,
`RECOVERED`, `ABANDONED`.

### RecoveryState

`NONE`, `RECONCILIATION_PENDING`, `RECONCILING`, `REISSUE_ELIGIBLE`,
`REISSUE_RESERVED`, `REISSUE_IN_FLIGHT`, `RECOVERED`, `EXHAUSTED`,
`MANUAL_REVIEW`.

## 5. Recovery flow

```text
POST-DISPATCH UNCERTAINTY
        |
        v
PRESERVE UNCERTAIN_CONSUMED
        |
        v
RECOVERABLE RESPONSE HANDLE?
   | yes                 | no
   v                     v
RETRIEVE              RECONCILE
   |                     |
   +------ success ------+
             |
             v
          CONTINUE
             |
             v
   BOUNDED REISSUE ELIGIBLE?
       | yes          | no
       v              v
  NEW DISPATCH     ABANDON/PAUSE
```

Recovery must pass through a `RecoveryCoordinator`. The scheduler cannot
silently resend a pending item while a remote outcome is unknown.

## 6. Dispatch identity

Each physical operation should record, when available:

- logical attempt identity;
- physical request identity;
- recovery generation and `recovery_of`;
- provider and model;
- request fingerprint;
- client correlation ID;
- reservation identity and amount;
- provider request and response IDs;
- dispatch and completion timestamps;
- dispatch, economic, functional, and recovery states.

Client correlation and provider idempotency remain distinct concepts.

## 7. Provider-neutral recovery capabilities

The design introduces a capability contract, not provider assumptions:

- `client_correlation`;
- `response_id_capture`;
- `response_retention`;
- `response_retrieval`;
- `lookup_by_client_request_id`;
- `idempotent_create`;
- `hidden_retry_control`.

Capabilities must be declared by the adapter and tested. An unavailable
capability selects the next safe recovery tier; it never authorizes guessing.

## 8. Economic contract

The current Decimal ceilings remain unchanged: global `1.00`, attempt `0.10`.

- Pre-dispatch proof: `RESERVED -> RELEASED`.
- Known usage: `RESERVED -> ACCOUNTED`.
- Ambiguous post-dispatch outcome: `RESERVED -> UNCERTAIN_CONSUMED`.
- Unknown actual billing remains null/unknown.
- Conservative consumption remains equal to the original reservation.
- A recovery reissue receives a new reservation and identity.

The worst case, original request billed plus recovery request billed, must be
represented before reissue is allowed.

## 9. Functional contract

Recovery levels are ordered:

1. use an already known valid `AgentResponse`;
2. retrieve by an officially supported provider response handle;
3. use provider-specific reconciliation only when documented;
4. issue one bounded new request with a new reservation.

If no level succeeds, the logical attempt is abandoned or paused. No response
object is synthesized.

## 10. Attempt and scheduler semantics

Recovery is inside the same logical scheduled attempt:

```text
attempt=1, replacement=false, recovery_generation=0
physical_request=1
physical_request=2, recovery_of=physical_request_1,
recovery_generation=1
```

The scheduler records no replacement for recovery. Normal replacement logic
only applies after the ordinary benchmark classification contract allows it.

## 11. Crash and resume semantics

Write-ahead states must distinguish:

`REQUEST_PREPARED -> RESERVATION_COMMITTED -> DISPATCH_STARTED`.

If the process stops after `DISPATCH_STARTED` without a durable conclusion,
startup must reconstruct:

`REMOTE_OUTCOME_UNKNOWN + UNCERTAIN_CONSUMED + RECOVERY_REQUIRED`.

Resume routes through `RecoveryCoordinator`; it never immediately repeats the
pending request. Existing executions without the new recovery schema are
legacy and remain subject to their original semantics.

## 12. Non-goals

- no billing endpoint invention;
- no promise of external exactly-once billing;
- no retroactive repair of the historical execution;
- no dataset, prompt, acceptance, provider, model, or scheduler redesign;
- no message broker, database, model router, or distributed transaction layer.

## 13. Acceptance boundary

The design is ready for implementation audit only when the RFC and IMP are
consistent with the real provider boundary, persistence model, scheduler, and
resume contract. Implementation requires a separate authorization.
