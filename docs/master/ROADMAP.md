# PD Agent - Roadmap

Status: Updated after v0.5 final closure.

## Confirmed Milestones

1. `v0.1` - Fabric Coding Loop - completed
2. `v0.1.1` - Real Provider Validation - completed
3. `v0.2` - Minecraft Test Harness Foundation - completed
4. `v0.3` - Minecraft Brain Foundation - completed
5. `v0.4` - Benchmark Foundation - completed
6. `v0.5` - Fabric Agent Capability Foundation - closed / pass
7. `v0.6` - Fabric Capability Expansion - closed / pass

## v0.6 Closure

`v0.6` is formally closed as:

- `CLOSED / PASS`;
- technical closure baseline: `1d9d3e86b315ee023e41ea2c548f2399680bdc4d`;
- implementation status: `IMPLEMENTED + RUNTIME VALIDATED`;
- representative runtime gates: PASS;
- multi-process Persistence/Reopen: PASS.

The delivered capability scope includes Data Components, Block Entities,
Inventory, Persistence/Reopen, typed server Commands, ServerWorldEvents LOAD,
Tags, Recipes and deterministic Loot. The complete validation record is
`docs/validation/PD_AGENT_V0.6_FINAL_CLOSURE.md`.

The v0.6 closure records implementation and capability completeness only. It
does not require an official benchmark matrix and does not make model/provider
performance claims. v0.7+ capabilities remain deferred and are not started.

Alpha is not declared reached.

## v0.5 Closure

`v0.5` is formally closed as:

- `CLOSED / PASS`;
- technical closure baseline: `f2524a15b58c82e6ad4ad417c25895b686ecafde`;
- implementation completeness: `IMPLEMENTED + OFFLINE VALIDATED`;
- Post-Dispatch Recovery: `DETERMINISTIC FAULT-INJECTION VALIDATED`;
- final focused recovery validation: `212 passed`;
- final full suite: `741 passed, 1 skipped`.

Implementation completeness is separate from model/provider performance. The
official Gemini F9 evidence remains `TERMINAL / INCOMPLETE / NON-PASS` with
T1 `1/3 PASS`, T2 `2/3 PASS` and T3 `1/2 PASS`. The isolated Luna F6-T2@5
result remains experimental evidence only, with observed cost `$0.0155072`.

The detailed closure record is
`docs/validation/PD_AGENT_V0.5_FINAL_CLOSURE.md`.

Alpha is not declared reached, and this roadmap does not define v0.6 scope.

## v0.2 Closure

`v0.2` stays closed as:

- `IMPLEMENTADO + VALIDADO + PASS`
- baseline closure: `3a58ad0212413f4b15b44666fb22a34507b856ae`
- final suite: `190 passed, 1 skipped`
- regression v0.1: `PASS`
- v0.1.1 historical live validation: `PASS`
- v0.1.1 current re-run: `BLOCKED BY CREDENTIALS`

This is strategic closure point for Minecraft Test Harness Foundation.

## v0.3 Closure

`v0.3` stays closed as:

- `IMPLEMENTADO + LIVE VALIDATED + PASS`
- baseline closure: `9d86344c445df3ad98b1674fdf6922e812637b13`
- final suite: `238 passed, 1 skipped`
- regression v0.1: `PASS`
- regression v0.1.1: `PASS`
- regression v0.2: `PASS`

The project now has a validated Minecraft Brain Foundation with versioned external knowledge and provenance.

## v0.4 Closure

`v0.4` is now closed as:

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

Brain OFF and Brain ON were validated with the same dataset, provider, model, fairness constraints and run budget. The official matrix showed no provider errors, no 429s and no benchmark-level blockers.

## v0.2 Strategic Goal

Close the gap:

`valid JAR` -> `Minecraft real` -> `mod loaded` -> `behavior observed` -> `PASS/FAIL`

The purpose was to improve evidence quality inside Minecraft before expanding the system with heavier intelligence layers such as Knowledge Base / RAG.

## v0.2 Scope, at a high level

- controlled Minecraft environment;
- startup;
- startup detection;
- mod load confirmation;
- controlled test execution;
- observed result;
- stop Minecraft cleanly;
- PASS/FAIL plus evidence.

## Decisions intentionally deferred

Do not decide yet:

- client vs server;
- GameTest;
- worlds;
- commands;
- IPC;
- screenshots;
- instrumentation;
- auxiliary mod;
- headless process;
- concrete architecture.

Those decisions belong to the later Minecraft Test Harness work after investigation and Design.

## Principles Still Valid

- model-agnostic;
- Python;
- small owned runtime;
- provider-neutral core;
- Local + API/BYOK support;
- Subscription only as a category when a supported integration exists;
- controlled tools;
- no free shell;
- filesystem confined;
- Gradle Wrapper authority;
- real evidence before model claims;
- incremental development;
- do not overbuild;
- PD Agent stays independent from PD-Ecosystem.

## Later Sequence

Later milestones are directional only and may be re-prioritized after each milestone:

- Build & Debug advanced
- Fabric Agent complete
- Multi-Agent
- Product UI
- `.Fuzzer`
