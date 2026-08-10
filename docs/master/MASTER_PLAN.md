# PD Agent — Master Plan

Status: Active strategic direction.

PD Agent is a small, provider-neutral Python runtime for safe, evidence-based coding and validation workflows.

## Current State

- `v0.1` is `IMPLEMENTADO + VALIDADO + PASS`.
- `v0.1.1` is `IMPLEMENTADO + LIVE VALIDATED + PASS`.
- `Minecraft runtime` is not validated yet and remains out of scope for v0.1.1.

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
3. `v0.2` - Minecraft Test Harness Foundation - next
4. `Minecraft Brain` / Knowledge Base
5. `Build & Debug` advanced
6. `Fabric Agent` complete
7. Later expansions such as benchmarks, multi-agent, UI and `.Fuzzer` remain dependent on evidence and re-evaluation
