# PD Agent v0.5 F9 Official Matrix Freeze

Status: FROZEN FOR LAUNCH
Date: 2026-08-22

## Scope

This document freezes the F9 official matrix configuration offline. It does
not execute the provider, AgentRuntime, Gradle, Minecraft, or the matrix.

## Dataset

- Dataset: `PD_AGENT_BENCHMARK_DATASET_V0.5_5`
- Version: `0.5.5`
- Tasks: `F6-T1@5`, `F6-T2@5`, `F6-T3@5`
- Fixture: `projects/v0_5_fabric_base`
- Identity algorithm: `sha256-tree-v2`
- Fixture identity: `3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396`

## Configuration

- Config file: `benchmarks/configs/f9-official-gemini-3.5-flash-lite-brain-on.json`
- Config id: `f9-official-gemini-3.5-flash-lite-brain-on`
- Provider: `gemini`
- Model: `gemini-3.5-flash-lite`
- Brain: `ON ONLY`
- `model_config`: `{}`
- `provider_config`: `provider_retry_limit=2`, `timeout_seconds=60`
- `knowledge_config`: `offline=false`
- `target_repetition_count`: `3`

Config hash, calculated with `BenchmarkConfig.config_hash()`, is:

`04f9f8936619c32c5fafe01748a8ab98174d47700102d796eea199d5f64486eb`

## Matrix

- Cells: `3`
- Valid repetitions per cell: `3`
- Target valid runs: `9`
- Maximum attempts per cell: `5`
- Maximum physical attempts: `15`
- Scheduling seed: `0`
- Brain OFF: not included
- Overall composite score: not used

`COMPLETED + PASS` and `COMPLETED + FAIL` are valid runs. `BLOCKED` and
`INVALID` are not valid runs and may receive replacements until the cell
reaches five attempts.

## F9 Criterion

The comparison is `COMPLETE` only when all three cells contain three valid
runs. F9 is PASS only when every task has at least two functional PASS runs
out of three. A complete matrix below that threshold is F9 FAIL. An
`INCOMPLETE` matrix is never PASS.

PASS runs must also demonstrate real provider execution, relevant mutation,
successful build, valid artifact, Minecraft runtime where required, observed
requested behavior, reproducible evidence, fixture/preservation/security
integrity, and no task-specific runtime hardcodes.

## Limits And Pacing

- `max_agent_steps`: `25`
- `max_tool_calls`: `50`
- `max_build_attempts`: `5`
- `max_context_bytes`: `2000000`
- `max_tool_output_bytes`: `1000000`
- `process_timeout_seconds`: `600`
- `provider_retry_limit`: `2`
- Provider timeout: `60`
- Pacing `min_interval_seconds`: `4.5`
- Logical session cap: `400`

The nominal envelope is `9 * 25 = 225` logical requests. The maximum
attempt envelope is `15 * 25 = 375`, below the logical session cap. F8 is
only a usage reference: 14 logical requests, 61,775 total tokens, 4 builds,
and 123.461135 seconds. No monetary pricing is frozen because no pricing
snapshot exists.

## Stop Conditions

Pause and preserve schedule/evidence on fixture mismatch, dataset/config or
commit drift, systemic evidence inconsistency, security regression,
harness/build infrastructure regression, provider authentication or quota
failure, `BUDGET_PAUSED`, session-cap exhaustion, or any blocker that makes
the matrix methodologically invalid. Do not change dataset, config,
provider, model, or acceptance to rescue results.

## Preflight Contract

The following must pass before launch:

- dataset loads with exactly the three frozen tasks;
- fixture algorithm and identity match this document;
- configuration loads and its hash is stable;
- provider/model and Brain mode match;
- scheduler creates nine initial target-repetition slots and three cells;
- five maximum attempts per cell are enforced;
- limits, pacing, seed, and logical cap match;
- no secrets are present;
- zero API requests are made.
