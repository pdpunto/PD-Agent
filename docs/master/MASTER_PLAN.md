# PD Agent — Master Plan

Status: Active strategic direction.

PD Agent is a small, provider-neutral Python runtime for safe, evidence-based coding and validation workflows.

## Current State

- `v0.1` is `IMPLEMENTADO + VALIDADO + PASS`.
- `v0.1.1` is `IMPLEMENTADO + LIVE VALIDATED + PASS`.
- `v0.2` is `IMPLEMENTADO + VALIDADO + PASS`.

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
4. `Minecraft Brain` / Knowledge Base - under evaluation
5. `Build & Debug` advanced - future review
6. `Fabric Agent` complete - future review
7. Later expansions such as benchmarks, multi-agent, UI and `.Fuzzer` remain dependent on evidence and re-evaluation

## v0.2 Closure

`PD Agent v0.2 - Minecraft Test Harness Foundation` is now strategically closed as:

- `IMPLEMENTADO + VALIDADO + PASS`
- baseline closure: `3a58ad0212413f4b15b44666fb22a34507b856ae`
- final suite: `190 passed, 1 skipped`
- regression v0.1: `PASS`
- v0.1.1 historical live validation: `PASS`
- v0.1.1 current re-run: `BLOCKED BY CREDENTIALS`

This closes the v0.2 evidence loop without broadening scope beyond dedicated server-side Minecraft validation.
