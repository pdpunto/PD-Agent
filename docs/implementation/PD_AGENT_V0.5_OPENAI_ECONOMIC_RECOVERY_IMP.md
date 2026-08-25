# PD Agent v0.5 - OpenAI Economic Recovery Implementation Plan

Status: IMPLEMENTATION PLAN. No production code, tests, API, resume, or live
execution is authorized by this document.

## Lot 0 - Contract and compatibility audit

Record the current owners and preserve the scheduler boundary:

- `src/pd_agent/experimental/luna_budget.py` for reservation/settlement;
- `src/pd_agent/providers/openai_provider.py` for the physical request seam;
- `src/pd_agent/benchmark/runner.py` for pause/resume integration;
- `src/pd_agent/benchmark/collector.py` for immutable evidence;
- `src/pd_agent/benchmark/scheduler.py` for attempt identity/replacements;
- `src/pd_agent/benchmark/models.py` for serialized execution records.

Confirm that 420d remains terminal and is not migrated or edited.

## Lot 1 - Economic schema and state model

Add explicit schema version `2` and fields for:

- `actual_billed_cost` (`Decimal` or `UNKNOWN`);
- `conservative_budget_consumed` (`Decimal`);
- `accounted`, `uncertain`, and active reserved totals;
- dispatch and reconciliation state;
- request/reservation identity and ordinal;
- provider-safe metadata references.

Implement `RESERVED`, `ACCOUNTED`, `RELEASED`, and terminal
`UNCERTAIN_CONSUMED` transitions with idempotence and Decimal arithmetic.
Reject schema `1` or incomplete state on resume; do not silently migrate.

Likely files: `luna_budget.py`, `models.py`, and their unit tests.

## Lot 2 - Provider failure evidence

Update `OpenAIProvider.execute()` so the adapter records a sanitized
pre/post-dispatch outcome without exposing secrets. Preserve the original
exception type, safe message, request ID, response ID, status and HTTP status
when available. Do not classify a generic SDK exception as pre-dispatch.

The guard must receive enough dispatch information to choose `RELEASED` only
when no provider request could have been sent. Otherwise it must choose
`UNCERTAIN_CONSUMED` and stop the operation without an automatic retry.

Likely files: `openai_provider.py`, `luna_budget.py`, provider tests, and
redaction tests.

## Lot 3 - Runner pause and resume safety

Keep the current scheduler attempt pending on economic pause, but make the
economic reservation terminal and non-reusable. Add resume validation for:

- active uncertain settlements;
- request identity collisions;
- inconsistent physical/retry counters;
- missing schema fields;
- commit/config/dataset/fixture drift.

Resume must either use authoritative reconciliation evidence or reject the
execution. It must never resend the uncertain physical request. Do not add a
replacement for an economic pause.

Likely files: `runner.py`, `scheduler.py` only for a narrow validation hook,
and runner/resume tests.

## Lot 4 - Collector and aggregation evidence

Persist one immutable physical-request evidence record per ordinal. Expose:

- logical and physical request counts;
- retries;
- input, cached, uncached, cache-write, output, reasoning and total tokens;
- actual billed cost;
- conservative consumed amount;
- attempt and global budget values.

Do not sum repeated cumulative snapshots. Keep uncertain records visible as
blocked economic evidence and exclude them from valid/PASS/FAIL/INVALID
functional aggregates.

Likely files: `collector.py`, aggregator models, evidence tests.

## Lot 5 - Offline regression suite

Add tests for:

1. valid usage to `ACCOUNTED`;
2. missing usage to `UNCERTAIN_CONSUMED`;
3. explicit pre-dispatch failure to `RELEASED`;
4. post-dispatch exception to `UNCERTAIN_CONSUMED`;
5. HTTP error with request ID;
6. SDK exception with uncertain dispatch;
7. response validation error after dispatch;
8. durable reservation before `ALLOW`;
9. exactly-once `ACCOUNTED`, `RELEASED`, and `UNCERTAIN_CONSUMED` settlement;
10. no release or reuse of uncertain budget;
11. separate unknown actual cost and conservative consumption;
12. global and attempt ceiling accounting;
13. equality and over-boundary enforcement;
14. pre-dispatch retry and no post-dispatch uncertain retry;
15. no duplicate physical request or double accounting;
16. new attempt/replacement global-budget preservation;
17. clean resume and rejection of uncertain resume;
18. historical execution immutability;
19. budget pause and pending preservation;
20. attempt/replacement scheduler identity;
21. provider IDs and sanitized exception persistence;
22. API key, Authorization and encrypted-reasoning redaction;
23. pricing, `max_output_tokens=16384`, and dual-budget regressions.

All tests are offline. No test may call OpenAI or Gemini.

## Lot 6 - Validation and freeze

Run focused tests, complete suite, `compileall`, `git diff --check`, and
schema/evidence redaction checks. Verify that F9 historical evidence and
`scripts/benchmark/diagnostics/` are untouched. Create a new freeze only after
all checks pass; do not reuse 420d.

## Acceptance

The implementation is accepted only when:

- the original failure cause remains observable even when usage is absent;
- uncertain consumption cannot be reused or double-counted;
- pre-dispatch release is proven, not inferred;
- post-dispatch uncertainty pauses safely;
- resume rejects unreconciled uncertainty;
- scheduler identity and replacement semantics remain unchanged;
- no secrets or raw encrypted reasoning are persisted;
- all offline tests and validation checks pass.

## Commit and rollback strategy

Commit schema/state, provider evidence, runner/resume, and aggregation in
separately reviewable commits or one coordinated change only after all tests
pass. Do not amend historical commits. Roll back only the recovery delta if
validation fails; never rewrite 420d or F9 evidence.

## Risks and non-goals

The provider may expose insufficient evidence to determine whether a failed
request was billed. The correct result is a terminal uncertain reservation,
not a guessed cost or an automatic retry. No billing endpoint, provider
tuning, scheduler redesign, dataset change, prompt change, or historical
repair is included.
