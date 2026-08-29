# PD Agent v0.8 - I16 Economic Preview Lifecycle Fix

## Finding

The I16 economic preview used the pure `LunaBudgetGuard.preview_budget()`
calculation after a caller had already invoked `begin_attempt()`. The latter is
a durable lifecycle operation, so the preview left an empty active attempt in
the shared ledger even though no request was prepared or dispatched.

The affected state had no reservation, uncertainty, ledger entry, dispatch
record, or counter increment. It was reconciled through the product API with
`LunaBudgetGuard.end_attempt()`, preserving the historical ledger.

## Contract

`LunaSharedBudgetSession.preview_budget()` is the persistence-free affordability
entry point. It creates no attempt, reservation, ledger entry, dispatch record,
or counter increment. It reuses the guard's existing worst-case pricing and
dual-ceiling checks; it does not implement a second budgeting algorithm.

An actual provider attempt must use `begin_attempt()` and the normal durable
dispatch lifecycle. Preview code must not call `begin_attempt()`.

## Validation

- The repaired shared ledger is `CLEAR` with ceiling `$0.56`, confirmed spend
  `$0.4595822000`, remaining `$0.1004178000`, and no active attempt.
- Physical requests, logical turns, retries, ledger entries, and dispatch
  records were unchanged by reconciliation.
- Focused lifecycle tests verify byte-identical persistence and preservation of
  an existing real attempt.
