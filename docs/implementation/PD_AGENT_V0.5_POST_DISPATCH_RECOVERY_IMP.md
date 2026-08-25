# PD Agent v0.5 - Post-Dispatch Recovery Implementation Plan

Status: IMPLEMENTATION PLAN. This document authorizes no implementation, API
call, resume, live run, or historical evidence change.

## R0 - Contract and repository audit

Freeze the design, RFC, and recovery schema version. Audit these real owners:

- `src/pd_agent/experimental/luna_budget.py`;
- `src/pd_agent/providers/openai_provider.py`;
- `src/pd_agent/benchmark/runner.py`;
- `src/pd_agent/benchmark/scheduler.py`;
- `src/pd_agent/benchmark/collector.py`;
- `src/pd_agent/benchmark/models.py`.

Confirm the legacy execution remains read-only and excluded from migration.

## R1 - Dispatch identity and write-ahead evidence

Add a versioned `DispatchRecord` with physical identity, reservation identity,
fingerprint, timestamps, dispatch state, and sanitized provider metadata.
Persist `REQUEST_PREPARED`, `RESERVATION_COMMITTED`, and `DISPATCH_STARTED`
before crossing the SDK boundary. Use atomic persistence appropriate to the
existing state store; do not introduce a database.

## R2 - Economic/functional split

Keep Decimal settlement in `LunaBudgetGuard`. Add functional/recovery state
without changing the meanings of `RESERVED`, `ACCOUNTED`, `RELEASED`, or
`UNCERTAIN_CONSUMED`. Preserve separate actual and conservative cost fields.

## R3 - Provider recovery contract

Add provider-neutral `ProviderRecoveryCapabilities` and adapter methods for
capability declaration, response retrieval, and reconciliation only where
officially supported. A missing capability must be a safe negative result, not
an inferred response.

## R4 - OpenAI hardening

Keep `openai 2.53.0` hidden retries disabled (`max_retries=0`). Add only
verified correlation and response/request identity fields. Confirm whether the
exact Responses API supports retrieval for the selected `store` policy before
implementing it. Never treat `X-Client-Request-Id` as idempotency.

## R5 - RecoveryCoordinator

Implement bounded ordering: known response, official retrieval, documented
reconciliation, then one reissue if policy and dual budgets permit. Every
reissue receives a new physical identity and reservation. The original
uncertainty remains immutable.

## R6 - Scheduler and resume integration

Route an uncertain pending operation through the coordinator. Do not increment
attempt/replacement or create a new repetition. Reject legacy uncertainty and
incompatible recovery state explicitly. Preserve exact pending schedule data.

## R7 - Persistence and crash recovery

On startup, reconstruct a potentially dispatched operation from durable
`DISPATCH_STARTED`. Never reissue before ledger and recovery state validation.
Make duplicate resume idempotent and reject state collisions.

## R8 - Accounting and provider regression tests

Cover:

1. validation failure before dispatch releases;
2. proven pre-dispatch failure releases;
3. ambiguous connection failure becomes uncertain;
4. normal response accounts once;
5. known response with unknown billing continues functionally;
6. response ID retrieval passes;
7. retrieval unavailable selects next tier;
8. missing response ID allows policy evaluation only;
9. reissue obtains a new reservation;
10. original reservation is not released on reissue;
11. insufficient budget pauses;
12. pre-dispatch reissue failure releases its new reservation;
13. post-dispatch reissue failure becomes uncertain;
14. recovery limit reaches exhausted;
15. attempt number does not increment;
16. replacement flag does not change;
17. hidden provider retries remain disabled;
18. crash before reservation is safe;
19. crash after reservation before dispatch is safe;
20. crash after dispatch start becomes unknown;
21. durable response identity is recoverable;
22. duplicate resume creates no duplicate recovery;
23. unknown response never creates an invented `AgentResponse`;
24. provider without recovery capabilities pauses safely;
25. `store=false`/retention unavailable degrades safely;
26. later authoritative economic reconciliation accounts once;
27. benchmark reporting exposes recovery state and evidence;
28. scheduler cannot enter a recovery loop.

All tests are offline and use fakes. No test calls OpenAI or Gemini.

## R9 - Functional recovery tests

Exercise valid response continuation, retrieval identity validation, reissue
request construction, response continuation replay, tool context preservation,
and terminal abandonment. Validate that a recovered response is not counted as
an additional inference and that a reissue is visible as a new physical record.

## R10 - Final validation and freeze

Run focused tests, full suite, `compileall`, `git diff --check`, persistence
round trips, redaction scans, crash probes, and scheduler invariants. Verify
that dataset, acceptance, prompts, provider/model, budgets, historical F9,
and diagnostics are unchanged. Create a new freeze only after implementation
validation and separate authorization.

## Real repository mapping and gaps

| Proposed work | Current component | Current status |
|---|---|---|
| dispatch record | `LunaBudgetGuard` ledger | no full dispatch state |
| write-ahead states | `LunaEconomicStateStore` | reservation persistence exists; dispatch phases absent |
| provider identity | `OpenAIProvider` | sanitized IDs only when SDK exposes them |
| recovery coordinator | none | future component |
| economic pause | `BenchmarkExecutionRunner` | implemented fail-closed |
| uncertain resume | runner restore validation | rejected intentionally |
| scheduler identity | `BenchmarkScheduler` | existing attempt/replacement authority |
| evidence | `BenchmarkCollector` | immutable collection exists; recovery records absent |

These are implementation gaps, not changes to the historical execution.

## Readiness gate

`READY_FOR_IMPLEMENTATION_AUDIT` means the documentation is internally
consistent and the real repository owners are identified. It does not mean
that R1-R10 are implemented or that a live run is authorized.
