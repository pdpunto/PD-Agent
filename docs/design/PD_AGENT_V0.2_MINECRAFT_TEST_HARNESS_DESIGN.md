# PD Agent v0.2 — Minecraft Test Harness Foundation — DESIGN

Status: ACCEPTED
Area: 06 — Minecraft Test Harness
Baseline: fff2d7cb06bb28dfdcec4803dad2d8e0c95ef596
Repository: pdpunto/PD-Agent
Branch: main

## 1. Purpose

PD Agent v0.2 closes the main evidence gap left by v0.1/v0.1.1.

Current proven path:

`source → build → valid Fabric JAR`

Target proven path for v0.2:

`source → build → valid Fabric JAR → real Minecraft/Fabric runtime → target mod loaded → controlled functional test → runtime evidence → PASS/FAIL`

The goal is not merely to prove that a Minecraft process started.

v0.2 must support the claim:

> This JAR was loaded by a real Minecraft/Fabric instance and a controlled functional test produced the expected result.

## 2. Scope

v0.2 is Fabric-first and server-first.

Initial acceptance target:

- Minecraft Java Edition 1.21.11
- Yarn 1.21.11+build.6
- Fabric Loader 0.19.3
- Fabric Loom 1.13.3
- Java 21
- existing `l11_fabric_fixture`
- dedicated Fabric server
- final remapped target JAR
- automated, non-interactive execution

## 3. In scope

v0.2 shall provide:

- isolated Minecraft runtime execution;
- loading of the exact final Fabric JAR;
- target mod identity verification;
- target JAR origin/hash verification when technically available;
- reliable server startup detection;
- one deterministic functional server-side test;
- runtime crash detection;
- timeout handling;
- clean shutdown;
- machine-readable PASS/FAIL evidence;
- persistent logs and reproducible run metadata;
- regression compatibility with v0.1/v0.1.1.

## 4. Out of scope

v0.2 does not attempt to validate:

- rendering;
- GUI;
- mouse/keyboard input;
- client-only mods;
- multiplayer with a real client;
- packet-level client/server behavior;
- screenshots;
- FPS/performance;
- compatibility with arbitrary third-party mods;
- multiple Minecraft versions;
- persistent survival worlds;
- generic remote control;
- RCON;
- HTTP/socket IPC;
- RAG;
- multi-agent orchestration;
- `.Fuzzer`;
- PD-Ecosystem integration.

## 5. Architectural direction

The minimal recommended architecture is:

`ArtifactValidator`
→ `MinecraftTestRunner`
→ Fabric dedicated production-like server
→ target JAR + test harness mod
→ target verification
→ functional runtime test
→ structured evidence
→ clean shutdown
→ result classification

The Minecraft runtime shall be server-side for v0.2 because this avoids GUI/GPU requirements and is more deterministic and CI-compatible.

## 6. Main components

### 6.1 MinecraftTestRunner

PD Agent-side orchestration component.

Responsibilities:

- validate test specification;
- compute target JAR SHA-256;
- create isolated run directory;
- prepare runtime launch;
- enforce timeout;
- capture stdout/stderr;
- collect Minecraft logs/crash reports;
- consume harness result;
- classify final result;
- persist evidence;
- clean up.

It must not contain Minecraft gameplay logic.

### 6.2 Test Harness Fabric Mod

Testing-only Fabric mod.

Responsibilities:

- execute inside the real Fabric server;
- confirm that the target mod is loaded;
- confirm the expected target origin/JAR when possible;
- detect server readiness using server lifecycle APIs;
- trigger a deterministic functional test;
- inspect real Minecraft state;
- write a structured result;
- request clean server shutdown.

It is never part of the user-delivered target JAR.

### 6.3 Acceptance Fixture

The existing `tests/fixtures/l11_fabric_fixture` remains the primary v0.2 acceptance fixture.

It shall be evolved minimally to expose one real server-side Minecraft behavior that can be observed deterministically.

The acceptance must not be satisfied by a pure Java assertion such as checking a returned string.

## 7. Functional acceptance model

The initial functional test shall follow this pattern:

`known Minecraft state A`
→ target mod operation
→ `real Minecraft state B`
→ harness assertion

A suitable minimal example is a target operation that modifies a controlled block position in a loaded server world, followed by the harness verifying the expected block state.

Exact mappings/API calls are implementation details and belong to RFC/IMP plus Codex audit.

## 8. Evidence model

A successful v0.2 run must prove all of the following:

1. ArtifactValidator accepted the target JAR.
2. The exact target JAR was identified before runtime.
3. A real Fabric dedicated server was launched.
4. Fabric Loader reported the target mod as loaded.
5. The runtime origin corresponds to the expected target JAR strongly enough to verify the same artifact.
6. The server reached a ready state.
7. The target behavior changed real Minecraft state.
8. The harness observed the expected result.
9. Minecraft did not crash.
10. The server shut down cleanly.
11. Evidence was persisted.

## 9. Result statuses

Public result statuses:

- `PASS`
- `FAIL`
- `CRASH`
- `TIMEOUT`
- `INFRA_ERROR`

Definitions:

### PASS

All contractual runtime and functional conditions succeeded.

### FAIL

Minecraft and the harness operated correctly, but the functional assertion failed.

### CRASH

Minecraft terminated abnormally before the protocol completed.

### TIMEOUT

The runtime protocol did not complete within the configured limit.

### INFRA_ERROR

The test could not be evaluated reliably because of infrastructure or protocol failure.

## 10. PASS contract

`PASS` requires:

- ArtifactValidator PASS;
- exact target artifact identified;
- production-like Fabric server launch;
- target mod loaded;
- runtime artifact identity verified;
- server ready;
- functional assertion PASS;
- valid harness result;
- no crash;
- controlled clean shutdown;
- successful process termination;
- evidence persisted.

Exit code `0` alone is never sufficient.

Log text alone is never sufficient.

Development classes alone are never sufficient.

## 11. Isolation

Each runtime test uses:

- a new run ID;
- a new run directory;
- fresh test world/runtime state;
- fresh result files;
- fresh logs.

Only safe dependency caches may be reused.

## 12. Security

The model must not be allowed to supply arbitrary Gradle or OS commands for Minecraft testing.

Runtime preparation and launch must be controlled by PD Agent.

The target artifact remains subject to the existing `SecurePathResolver` / `ToolExecutor` security boundary where applicable, plus artifact validation controls before execution.

## 13. GameTest position

Minecraft/Fabric GameTest is useful and remains part of the testing strategy.

It may be used for:

- harness tests;
- fixture regression;
- fast server-side development checks.

However, a development GameTest PASS is not equivalent to the v0.2 production-runtime acceptance PASS.

The final acceptance must exercise the final remapped target JAR in the production-like runtime path.

## 14. Existing capability reuse

v0.2 should reuse or align with existing PD Agent concepts where appropriate:

- ArtifactValidator;
- Gradle Wrapper handling;
- process execution patterns;
- timeout handling;
- RunState;
- RunStorage/reporting;
- evidence directories;
- `SecurePathResolver` + `ToolExecutor` security boundary;
- fixture-copy isolation.

Exact reuse is subject to Codex repository audit.

## 15. Non-goals and anti-overengineering rules

v0.2 must not introduce:

- generic IPC;
- sockets;
- HTTP services;
- RCON;
- a universal Minecraft testing framework;
- client automation;
- persistent infrastructure;
- a new agent;
- a new provider abstraction.

Any such addition requires evidence that the minimal architecture cannot satisfy the acceptance goal.

## 16. Acceptance statement

When v0.2 is complete, PD Agent must be able to produce reproducible evidence supporting:

> This exact Fabric JAR was loaded by a real Minecraft/Fabric dedicated server, its target mod was verified at runtime, a controlled server-side functional behavior modified real Minecraft state as expected, and the server completed the test without crash and shut down cleanly.

## 17. References

Primary technical references used during design:

- Fabric automatic testing / GameTest documentation
- Fabric Loom production run task documentation
- Fabric Loader public API (`FabricLoader`, `ModContainer`, mod origin)
- Minecraft EULA / distribution terms

Repository evidence at baseline:

- `tests/fixtures/l11_fabric_fixture/gradle.properties`
- `tests/fixtures/l11_fabric_fixture/build.gradle.kts`
- `tests/fixtures/l11_fabric_fixture/src/main/resources/fabric.mod.json`
- `tests/fixtures/l11_fabric_fixture/src/main/java/dev/pdpunto/l11/ExampleMod.java`
- `scripts/validation/validate_v0_1.py`
