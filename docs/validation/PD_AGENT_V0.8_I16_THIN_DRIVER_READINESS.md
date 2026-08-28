# PD Agent v0.8 - I16 Thin Validation Driver

## Boundary

`scripts/validation/run_i16.py` is an isolated integrated-run driver. It does
not own benchmark task scheduling, repetitions, replacements, or aggregation.
It composes the normal Fabric orchestrator and persists a redacted manifest.

## Gates

`PRECHECK` and `DRY-RUN` validate the explicitly supplied commit against both
local `HEAD` and `origin/main`, then validate the frozen task, config, fixture, Gradle
seed, frozen Knowledge Pack, repository baseline, credential presence, and
shared economic ledger without creating an `ExecutionRoot` or contacting a
provider. `LIVE` requires both `--live` and `--authorize-i16` and repeats all
prechecks before creating a fresh root.

The live path is fail-closed for baseline, fixture, seed, pack, budget,
credential, and fresh-root mismatches. Secrets are used only to configure the
provider redactor and are never written to the manifest.

The commit is intentionally not hardcoded: callers must pass
`--pd-agent-commit <SHA>`, and a mismatch against either side of `main` blocks
the run. This prevents the driver commit itself from making its own default
baseline stale.

## Frozen I16 Contract

The driver is pinned to `F6-T3@5`, OpenAI `gpt-5.6-luna`, Brain ON, reasoning
`medium`, `service_tier=default`, `store=false`, `max_output_tokens=16384`,
25 agent steps, 50 tools, 5 builds, and provider retry limit 2. The shared
economic ceiling is `$0.30`, migrated upward from the historical `$0.25`
ledger through the product API; uncertain or paused ledgers block LIVE. The
per-attempt ceiling remains `$0.10`.

## Live Authorization

No live execution is authorized by this document. Direction must provide an
explicit authorization outside the driver before a live invocation.

## Final Preflight Blocker

The original driver release used the preceding commit as a hardcoded baseline,
which made its own preparation commit fail closed. The driver now requires
`--pd-agent-commit` explicitly and compares it with both local `HEAD` and
`origin/main`.

The recovered Gradle seed is readable and verifies against the frozen identity.
The current v0.8 Knowledge Pack identity is
`9f1ef7ac14fa63b79aa8ef3decd1fce232729b4eefee6f2292382db4f3f4f3a5` with
104978 records. The v0.7 identity `9045db86cf29d54f526a918be95c74cc37db87597bcc443cfbdb6f396ca04ef1`
is retained only as historical evidence and is not the current I16 expectation.
The frozen Knowledge Pack candidates found in the local temporary area exist,
but their roots are ACL-inaccessible from this context. No ACL, source pack,
or historical execution was changed. The required next step is a host-owned
control recovery using `scripts/validation/recover_i16_knowledge_pack.ps1`;
the I16 live gate remains blocked until that copied pack passes the real loader.
