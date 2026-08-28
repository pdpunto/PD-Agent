# PD Agent v0.8 - I16 Thin Validation Driver

## Boundary

`scripts/validation/run_i16.py` is an isolated integrated-run driver. It does
not own benchmark task scheduling, repetitions, replacements, or aggregation.
It composes the normal Fabric orchestrator and persists a redacted manifest.

## Gates

`PRECHECK` and `DRY-RUN` validate the frozen task, config, fixture, Gradle
seed, frozen Knowledge Pack, repository baseline, credential presence, and
shared economic ledger without creating an `ExecutionRoot` or contacting a
provider. `LIVE` requires both `--live` and `--authorize-i16` and repeats all
prechecks before creating a fresh root.

The live path is fail-closed for baseline, fixture, seed, pack, budget,
credential, and fresh-root mismatches. Secrets are used only to configure the
provider redactor and are never written to the manifest.

## Frozen I16 Contract

The driver is pinned to `F6-T3@5`, OpenAI `gpt-5.6-luna`, Brain ON, reasoning
`medium`, `service_tier=default`, `store=false`, `max_output_tokens=16384`,
25 agent steps, 50 tools, 5 builds, and provider retry limit 2. The shared
economic ceiling is `$0.25`; uncertain or paused ledgers block LIVE.

## Live Authorization

No live execution is authorized by this document. Direction must provide an
explicit authorization outside the driver before a live invocation.
