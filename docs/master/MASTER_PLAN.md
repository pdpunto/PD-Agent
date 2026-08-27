# PD Agent - Master Plan

Status: v0.7 closed; later direction remains subject to separate authorization.

PD Agent is a small, provider-neutral Python runtime for safe, evidence-based coding and validation workflows.

## Current State

- `v0.1` is `IMPLEMENTADO + VALIDADO + PASS`.
- `v0.1.1` is `IMPLEMENTADO + LIVE VALIDATED + PASS`.
- `v0.2` is `IMPLEMENTADO + VALIDADO + PASS`.
- `v0.3` is `IMPLEMENTADO + LIVE VALIDATED + PASS`.
- `v0.4` is `IMPLEMENTADO + LIVE VALIDATED + PASS`.

## Strategic Direction

The project remains:

- model-agnostic;
- Python-first;
- provider-neutral at core/runtime;
- controlled-tools only;
- filesystem confined to `project_root`;
- Gradle Wrapper authoritative for Fabric builds;
- evidence-first over model claims;
- incremental and deliberately small;
- independent of PD-Ecosystem product layers.

## Milestone Sequence

1. `v0.1` - Fabric coding/build loop - completed
2. `v0.1.1` - real provider validation - completed
3. `v0.2` - Minecraft Test Harness Foundation - completed
4. `v0.3` - Minecraft Brain Foundation - completed
5. `v0.4` - Benchmark Foundation - completed
6. `v0.5` - Fabric Agent Capability Foundation - closed / pass
7. `v0.6` - Fabric Capability Expansion - closed / pass
8. Later expansions remain subject to separate evidence and authorization.

## v0.7 Closure

`PD Agent v0.7 - Minecraft/Fabric Knowledge Foundation` is closed as:

- `CLOSED / PASS`;
- technical closure baseline: `42db50ca8f788dee4850c1c8e90917e6c3e37dcb`;
- implementation status: `IMPLEMENTED + VALIDATED`;
- final suite: `942 passed, 2 skipped`;
- `compileJava --offline`: PASS;
- `compileall`: PASS;
- `git diff --check`: PASS.

The frozen Knowledge Pack is
`9045db86cf29d54f526a918be95c74cc37db87597bcc443cfbdb6f396ca04ef1`, with
104978 records and a derived SQLite FTS5 index. The complete scope and
acceptance A-J evidence are recorded in
`docs/validation/PD_AGENT_V0.7_FINAL_CLOSURE.md`.

The v0.7 closure concerns technical capability completeness, not model or
provider performance. No official benchmark was required. Alpha is not
declared, v0.8 has not started, and later work remains subject to a separate
Direction decision.

## v0.6 Closure

`PD Agent v0.6 - Fabric Capability Expansion` is closed as:

- `CLOSED / PASS`;
- technical closure baseline: `1d9d3e86b315ee023e41ea2c548f2399680bdc4d`;
- implementation status: `IMPLEMENTED + RUNTIME VALIDATED`;
- representative runtime gates: PASS;
- multi-process Persistence/Reopen: PASS.

The v0.6 scope is documented in
`docs/validation/PD_AGENT_V0.6_FINAL_CLOSURE.md`. This is implementation and
capability completeness, separate from model/provider performance. No
official v0.6 benchmark is required for this closure. Capabilities beyond the
closed scope are deferred to a separately authorized future milestone; v0.7
has not started and Alpha is not declared.

## v0.5 Closure

`PD Agent v0.5 - Fabric Agent Capability Foundation` is closed as:

- `CLOSED / PASS`;
- technical closure baseline: `f2524a15b58c82e6ad4ad417c25895b686ecafde`;
- implementation completeness: `IMPLEMENTED + OFFLINE VALIDATED`;
- Post-Dispatch Recovery: `DETERMINISTIC FAULT-INJECTION VALIDATED`;
- final focused recovery validation: `212 passed`;
- final full suite: `741 passed, 1 skipped`.

The official Gemini F9 result remains terminal, incomplete and non-pass:
T1 `1/3 PASS`, T2 `2/3 PASS`, T3 `1/2 PASS`. This is a model/provider
performance result and is separate from implementation completeness. The
isolated Luna F6-T2@5 result is experimental evidence only, with observed
cost `$0.0155072`.

See `docs/validation/PD_AGENT_V0.5_FINAL_CLOSURE.md` for the complete
closure record. Alpha is not declared reached, and this document does not
define v0.6 scope.

## v0.2 Closure

`PD Agent v0.2 - Minecraft Test Harness Foundation` is now strategically closed as:

- `IMPLEMENTADO + VALIDADO + PASS`
- baseline closure: `3a58ad0212413f4b15b44666fb22a34507b856ae`
- final suite: `190 passed, 1 skipped`
- regression v0.1: `PASS`
- v0.1.1 historical live validation: `PASS`
- v0.1.1 current re-run: `BLOCKED BY CREDENTIALS`

This closes the v0.2 evidence loop without broadening scope beyond dedicated server-side Minecraft validation.

## v0.3 Closure

`PD Agent v0.3 - Minecraft Brain Foundation` is now strategically closed as:

- `IMPLEMENTADO + LIVE VALIDATED + PASS`
- baseline closure: `9d86344c445df3ad98b1674fdf6922e812637b13`
- final suite: `238 passed, 1 skipped`
- regression v0.1: `PASS`
- regression v0.1.1: `PASS`
- regression v0.2: `PASS`

This confirms the project can use versioned, provenance-bearing external knowledge in a real Fabric/Minecraft flow.

## v0.4 Closure

`PD Agent v0.4 - Benchmark Foundation` is now strategically closed as:

- `IMPLEMENTADO + LIVE VALIDATED + PASS`
- baseline closure: `d2966403ded33e9f7100002fddf452718a8bf78a`
- official matrix: `18/18 valid`
- invalid: `0`
- blocked: `0`
- replacements: `0`
- comparison status: `COMPLETE`
- batch status: `COMPLETED`
- final suite: `425 passed, 2 skipped`
- official execution root: `C:\Users\Usuario\AppData\Local\Temp\pd-agent-v0.4-official-launch-20260814-204850-235\execution\e86d7abe-aae4-4f5d-bd37-8b751be6323c`

Brain OFF and Brain ON were both validated with the same dataset, provider, model, fairness constraints and run budget. The official matrix showed no provider errors, no 429s and no benchmark-level blockers.
