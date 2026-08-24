# PD Agent v0.5 - Gemini vs Luna Mini A/B Implementation Plan

Status: DESIGN/RFC follow-up only. Do not implement or run live in this batch.

## Batch 1 - Experimental Launcher

Add a dedicated isolated launcher, preferably under
`scripts/benchmark/`, that accepts the two frozen provider configs, creates a
new execution root, and writes `experimental=true` and `non_official=true`.
It must never call the F9 scheduler or aggregator.

Expected dependencies: `BenchmarkCatalog`, `BenchmarkExecutor`, existing
providers, `BenchmarkGradleEnvironment`, `BenchmarkCollector`,
`BenchmarkClassifier`, artifact validator and Minecraft runner.

## Batch 2 - Config and Frozen Schedule

Represent two cells for `F6-T2@5` with the unchanged task and limits. Persist
the deterministic order `Gemini-0, Luna-0, Luna-1, Gemini-1`, target valid
repetitions `2`, maximum attempts `3`, and a study-specific execution id.
Reject drift before every resume.

## Batch 3 - Provider Dispatch and Budget

Dispatch Gemini and Luna through the existing provider interfaces. Inject
`LunaBudgetGuard` before every physical Luna request, including retries.
Enforce the global experimental OpenAI exposure cap of `$3.00` before starting
the next Luna attempt. Preserve per-run hard budget `$1.00`, corrected
collector accounting, pricing metadata and redaction.

## Batch 4 - Pause, Resume and Evidence

Persist `RATE_LIMIT_PAUSED` with the exact pending attempt and no consumed
attempt/replacement. Resume the same study root only after freeze, commit,
config, schedule and execution identity checks. Persist per-run evidence and a
study aggregate that keeps Gemini cost `NOT_CALCULATED` unless explicitly
priced.

## Batch 5 - Tests and Prelaunch

Required offline tests:

- F9 and historical Luna isolation;
- two provider dispatch and deterministic schedule;
- two valid runs per cell and maximum three attempts;
- functional FAIL validity and replacement rules;
- Gemini rate-limit pause and exact resume;
- Luna per-run budget and global `$3.00` exposure cap;
- retry guard, fail-closed usage and corrected cumulative accounting;
- metrics, secret redaction, config/freeze drift and duplicate-run rejection.

Prelaunch must verify the baseline commit, task/acceptance/fixture, seed,
provider configs, fresh roots, flags, schedule hash, quota pause readiness
limitations and zero API calls during the audit.

## Batch 6 - Authorized Live Study

Only after Batches 1-5 pass and a separate authorization, execute the frozen
four-run target. Stop on the first terminal outcome only for single-run smoke;
for this study continue only according to the persisted schedule and stop
conditions. Do not import the two exploratory Luna runs and do not touch F9.

## Rollback and Boundaries

The implementation is additive and experimental. Roll back only the A/B
launcher, configs, tests and evidence schema changes if validation fails. Do
not alter dataset, acceptance, prompts, official scheduler semantics, F9
evidence or diagnostics.

