# PD Agent v0.5 - Gemini vs Luna Mini A/B RFC

Status: RFC for an isolated experimental implementation. No live execution.

## Contract

The implementation creates exactly two cells for `F6-T2@5`, targets two valid
runs per cell, and permits at most three attempts per cell. A functional FAIL
is valid and does not create a replacement. Only real `INVALID` or `BLOCKED`
runs can create a replacement while the cell is below its target.

The schedule is persisted before launch with a deterministic seed and the
frozen order `Gemini-0, Luna-0, Luna-1, Gemini-1`. Resume must consume the
exact pending schedule item and must reject dataset, config, fixture, commit,
limit, schedule or execution identity drift.

## Experimental Runner

Use a small A/B launcher with an experimental manifest rather than the
official F9 runner. It should reuse:

- `BenchmarkCatalog` and the versioned task/config models;
- `BenchmarkExecutor`, `BenchmarkCollector`, `BenchmarkClassifier` and
  existing artifact/Minecraft/harness implementations;
- `BenchmarkGradleEnvironment` and the pinned seed validation;
- `GeminiProvider`, `OpenAIProvider`, the existing tool/security contracts;
- `LunaBudgetGuard` for Luna requests only.

The current `run_luna_experimental.py` is intentionally hard-coded to one
OpenAI Luna run and cannot be generalized by changing a flag. The current
`run_v0_4.py` can dispatch official provider runs, but its manifest and
scheduler are official-oriented. Neither is sufficient as the A/B launcher
without an explicit experimental isolation layer.

## State Machine

`RUNNING` transitions to `COMPLETED`, `FAILED`, `BLOCKED`, `INVALID`, or
`INCOMPLETE`. A provider quota event transitions to `RATE_LIMIT_PAUSED` while
preserving the same pending attempt, without consuming an attempt, replacement
or valid-run slot. Resume returns to `RUNNING` only after offline identity and
freeze checks pass. Luna budget exhaustion is recorded as `BUDGET_PAUSED` or
`BUDGET_BLOCKED` according to the existing contracts and is never a Gemini
functional result.

## Provider and Budget Rules

Gemini has no comparable pricing snapshot in this experiment; its cost is
`NOT_CALCULATED`. Luna uses the existing `$1.00` per-run
`LunaBudgetGuard`, including pre-request reservation, retry protection,
fail-closed usage validation and corrected cumulative accounting. The runner
must enforce a simple operational OpenAI exposure cap of `$3.00` for the three
possible Luna attempts. This is an experiment cap, not a general billing
subsystem.

## Evidence

Every run records provider/model, validity, outcome, logical turns, physical
requests, retries, token breakdown, duration, PRE_BUILD, Semantic Repair and
repair turns, builds, artifact, Minecraft, terminal reason, provider errors,
rate-limit state and experimental/non-official flags. Secrets and raw
encrypted reasoning are never persisted.

## Resume and Quota Fairness

Quota pauses are provider-neutral scheduler states. They must not be converted
to FAIL and must not be replaced by another provider run. The predeclared
balanced order prevents changing provider order after observing results. If
Gemini cannot recover quota, the study remains `INCOMPLETE` rather than
claiming a provider comparison.

