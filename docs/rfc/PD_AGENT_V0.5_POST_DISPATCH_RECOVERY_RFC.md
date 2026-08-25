# PD Agent v0.5 - Post-Dispatch Recovery RFC

Status: RFC DELTA. This RFC describes a future implementation contract. It
authorizes no API calls, resume, production code, or historical mutation.

## 1. Current repository boundary

The repository currently has these owners:

- `LunaBudgetGuard`: Decimal reservation and settlement;
- `LunaEconomicStateStore`: durable economic state;
- `OpenAIProvider`: Responses request boundary and sanitized provider errors;
- `BenchmarkExecutionRunner`: economic pause and resume validation;
- `BenchmarkScheduler`: scheduled attempt, repetition, and replacement identity;
- `BenchmarkCollector`: immutable run evidence and usage aggregation.

The installed SDK is `openai 2.53.0`. The real adapter constructs the client
with `max_retries=0` and also requests `max_retries=0` through `with_options`.
The adapter currently does not provide a durable client correlation ID,
response retrieval operation, or provider-side reconciliation operation.
Those capabilities are therefore unverified and unavailable by default.

## 2. Proposed ownership

Add a `RecoveryCoordinator` above the provider boundary. It consumes a
provider-neutral `ProviderRecoveryCapabilities` declaration and coordinates:

```text
OpenAIProvider -> DispatchRecord -> LunaBudgetGuard/ledger
                         |
                         v
                 RecoveryCoordinator
                         |
                         v
                 Runner/resume/scheduler
```

The coordinator owns functional recovery decisions. The guard remains the
owner of economic accounting. The scheduler remains the owner of scheduled
identity. No second mutable ledger is introduced.

## 3. Records and schema

### DispatchRecord

Required conceptual fields:

```text
physical_request_id
logical_attempt_id
recovery_generation
recovery_of
provider
model
request_fingerprint
client_correlation_id
reservation_id
reserved_cost
actual_billed_cost
dispatch_state
economic_state
functional_state
provider_request_id?
provider_response_id?
response_status?
http_status?
sanitized_error?
prepared_at
reservation_committed_at
dispatch_started_at
completed_at?
```

### RecoveryRecord

```text
recovery_id
source_physical_request_id
strategy
started_at
completed_at?
result
new_physical_request_id?
evidence_refs
```

The new fields require an explicit recovery schema version. Missing or
incompatible fields reject resume; there is no heuristic migration.

## 4. Physical request protocol

1. Build a request fingerprint and physical identity.
2. Persist `REQUEST_PREPARED`.
3. Calculate and persist a Decimal reservation.
4. Persist `RESERVATION_COMMITTED`.
5. Persist `DISPATCH_STARTED` immediately before the SDK call.
6. Disable hidden billable retries.
7. Persist provider response/error identity at the adapter boundary.
8. Settle exactly once as `ACCOUNTED`, `RELEASED`, or
   `UNCERTAIN_CONSUMED`.

The existing adapter already guards `responses.create()` before dispatch and
has hidden retries disabled. It does not yet persist steps 1, 2, 5, or the
full provider correlation record.

## 5. Recovery decision algorithm

```text
if AgentResponse already exists:
    continue without inference
elif response retrieval is declared and handle is present:
    retrieve and validate identity/context
elif provider reconciliation is declared and supported:
    reconcile through adapter
elif policy allows reissue and worst-case budget fits:
    reserve new physical operation and dispatch once
else:
    pause as RECOVERY_EXHAUSTED or MANUAL_REVIEW
```

The original uncertain reservation is never released or reused. A reissue is
not a scheduler attempt, replacement, or new repetition.

## 6. OpenAI adapter contract

The adapter must verify against the exact SDK/API version before implementation:

- `max_retries=0` is mandatory and is already present in HEAD;
- a client correlation header may be sent only as correlation;
- provider request/response IDs are captured when exposed;
- retrieval is used only through an officially supported operation;
- `store=false` means retrieval may be unavailable;
- no lookup by client correlation is assumed;
- raw Authorization, API key, sensitive headers, and encrypted reasoning are
  redacted.

No OpenAI API call is part of this RFC validation.

## 7. Economic and functional separation

Economic settlement and functional outcome are independent:

| Condition | Economic state | Functional state |
|---|---|---|
| pre-dispatch proof | RELEASED | ABANDONED or retryable |
| valid response and usage | ACCOUNTED | RESPONSE_AVAILABLE |
| ambiguous post-dispatch error | UNCERTAIN_CONSUMED | RESPONSE_MISSING |
| recovered response | unchanged original settlement | RECOVERED |
| successful reissue | new reservation settlement | RESPONSE_AVAILABLE |
| exhausted recovery | original uncertainty retained | ABANDONED |

`UNCERTAIN_CONSUMED` is not PASS, FAIL, or INVALID. It maps to economic
pause/incomplete evidence.

## 8. Resume and scheduler

Resume must validate execution identity, commit, dataset, config, fixture,
schedule, schema, ledger counters, and pending item. A pending item with an
unknown remote outcome is not permission to resend.

While recovery is pending, the scheduler must not create another attempt or
replacement. The coordinator returns one of `RECOVERED`, `ABANDONED`,
`BUDGET_PAUSED`, `RECOVERY_EXHAUSTED`, or `MANUAL_REVIEW`.

Baseline policy: one recovery reissue per logical attempt. A second ambiguous
outcome is exhausted and remains paused/incomplete.

## 9. Legacy execution

The historical execution
`84df7f4b-c82d-4f95-b951-d5eafab79530` remains unchanged and is not eligible
for retroactive recovery. Its persisted state is `BUDGET_PAUSED` with
`UNCERTAIN_CONSUMED`; it has no recovery schema or durable dispatch record.

## 10. Compatibility and security

Old evidence remains readable without inventing absent fields. Legacy records
may be marked `legacy_execution=true` and `recovery_contract_version=null` in
future readers, but no new recovery behavior is granted retroactively.

Evidence must exclude API keys, Authorization, credentials, raw encrypted
reasoning, and unredacted sensitive headers.

## 11. RFC acceptance

Implementation R1-R10 may begin only after the DESIGN, RFC, and IMP are
approved, the contract has been audited against the real repository, and
ChatGPT/01 Architecture has granted explicit implementation authorization.
The offline IMP matrix is an implementation validation gate, not a prerequisite
for starting R1-R7; its R8/R9 tests depend on those components existing.

Implementation cannot be declared complete or used to enable a new candidate
until all of the following are true:

- the offline IMP matrix is PASS;
- relevant SDK/provider behavior is verified without assuming undeclared
  capabilities;
- persistence and recovery schema behavior is validated;
- the full regression suite and recovery regressions are PASS; and
- a separate authorization exists for any live run or candidate.

The historical execution
`84df7f4b-c82d-4f95-b951-d5eafab79530` remains non-recoverable retroactively
and must not be modified.
