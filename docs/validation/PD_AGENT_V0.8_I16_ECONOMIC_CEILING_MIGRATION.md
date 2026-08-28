# PD Agent v0.8 - I16 Economic Ceiling Migration

Status: OFFLINE VALIDATED. No provider, Minecraft, benchmark or LIVE execution
was performed for this change.

## Contract

The shared I16 ledger keeps the attempt ceiling at `$0.10` and supports a
configurable global ceiling. New sessions retain the historical default of
`$0.25`. Existing ledgers can be migrated only upward with
`LunaSharedBudgetSession.migrate_global_ceiling(...)`. The operation uses the
existing atomic state store and rejects malformed or non-positive values,
downward migrations, reservations, uncertainty, and any target below
confirmed spend. It preserves all ledger records, counters, dispatch history,
active-attempt state and the attempt ceiling.

## Real Ledger Migration

The authoritative I16 shared state is migrated through the product API:

- Path: `C:\Users\Usuario\AppData\Local\PD-Agent\economic\i16\shared-economic-state.json`
- Before: global ceiling `$0.25`, confirmed `$0.1869635500`, remaining
  `$0.0630364500`, reserved `$0`, uncertain `$0`, active attempt `None`,
  physical `77`, logical `79`.
- After: global ceiling `$0.30`, confirmed `$0.1869635500`, remaining
  `$0.1130364500`, reserved `$0`, uncertain `$0`, active attempt `None`,
  physical `77`, logical `79`.
- Attempt ceiling: unchanged at `$0.10`.

The migration did not rewrite or settle any request record.

## Offline Validation

- Focused economic/I16 tests: PASS.
- The real ledger reopens with `expected_global_ceiling="$0.30"` and remains
  `CLEAR`.
- The real payload preview is performed without a provider request and remains
  under both the attempt and global ceilings.
- Full suite, `compileall`, and `git diff --check` are recorded with
  publication of this document.

This document does not authorize I16 LIVE; separate authorization remains
required.
