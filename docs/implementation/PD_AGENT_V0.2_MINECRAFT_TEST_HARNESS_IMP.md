# PD Agent v0.2 — Minecraft Test Harness Foundation — IMP

Status: READY FOR CODEX AUDIT
Area: 06 — Minecraft Test Harness
Depends on:
- PD_AGENT_V0.2_MINECRAFT_TEST_HARNESS_DESIGN.md
- PD_AGENT_V0.2_MINECRAFT_TEST_HARNESS_RFC.md

Expected baseline before audit:
- repository: pdpunto/PD-Agent
- branch: main
- baseline: fff2d7cb06bb28dfdcec4803dad2d8e0c95ef596
- working tree: clean

IMPORTANT:
This document is an implementation plan, not authorization to implement.
Codex must audit DESIGN + RFC + IMP against the real repository before any implementation.

## 1. Implementation objective

Build the minimum runtime test path that can prove:

`validated final Fabric JAR`
→ `real dedicated Minecraft/Fabric runtime`
→ `exact target artifact loaded`
→ `server ready`
→ `controlled functional behavior`
→ `real Minecraft state verified`
→ `clean shutdown`
→ `structured PASS/FAIL evidence`

Initial supported target:

- Minecraft 1.21.11
- Java 21
- Fabric Loader 0.19.3
- Loom 1.13.3
- existing `l11_fabric_fixture`
- dedicated server only

## 2. Mandatory pre-implementation audit

Codex must first inspect the repository and report:

1. HEAD and origin/main.
2. Working tree status.
3. Existing package/module layout.
4. Exact contracts of:
   - `ArtifactValidator`;
   - `GradleBuildRunner`;
   - `RunState`;
   - `RunStorage` / reporting;
   - `SecurePathResolver` and `ToolExecutor` security boundary;
   - existing subprocess/process helpers;
   - configuration/execution limits.
5. Existing validation scripts and fixture conventions.
6. Current Gradle wrapper/fixture behavior.
7. Whether Loom 1.13.3 exposes the production server task/API exactly as assumed by the RFC.
8. Exact Fabric Loader 0.19.3 APIs needed for mod origin verification.
9. Exact Minecraft/Fabric APIs for:
   - dedicated server lifecycle readiness;
   - accessing a server world;
   - deterministic block-state mutation/inspection;
   - clean server shutdown.
10. Whether Fabric API is required by the harness and/or target fixture.
11. How EULA acceptance is handled for the automated dedicated test environment.
12. Whether the proposed system-property/result-file mechanism is compatible with the real launch path.
13. Any conflict between DESIGN/RFC/IMP and repository reality.

If any material mismatch exists:
- STOP implementation;
- report evidence;
- propose the smallest correction;
- update DESIGN/RFC/IMP first;
- only then implement.

## 3. Planned implementation batches

Implementation is split into four batches.

No batch should silently expand scope.

### Batch A — Core runtime contracts and runner skeleton

Goal:
Introduce PD Agent-side Minecraft test contracts without launching Minecraft yet.

Expected work:

- add `MinecraftTestSpec`;
- add public result status model:
  - PASS
  - FAIL
  - CRASH
  - TIMEOUT
  - INFRA_ERROR
- add `MinecraftTestResult`;
- add target metadata/hash calculation;
- add evidence path/layout support;
- add `MinecraftTestRunner` skeleton;
- validate supported environment;
- reject unsupported/malformed specifications;
- establish controlled launch abstraction;
- unit-test classification and evidence contracts.

Rules:

- do not modify `GradleBuildRunner` into a runtime runner;
- reuse existing process/reporting helpers only if repository audit proves they fit;
- no Minecraft launch in this batch;
- no generic shell execution API;
- no IPC/RCON/network service.

Acceptance:

- unit tests PASS;
- existing suite remains PASS;
- result/status contracts serialized deterministically;
- SHA-256 metadata test PASS;
- invalid/unsupported spec tests PASS;
- no v0.1/v0.1.1 regression.

Commit after Batch A.

Suggested commit:
`feat(test-harness): add minecraft runtime test contracts`

### Batch B — Fabric test harness + functional fixture

Goal:
Create the minimum code that can run inside Minecraft and prove target identity plus a real state transition.

Expected work:

- create a testing-only Fabric harness source/module/fixture location consistent with repo conventions;
- read fixed launch metadata;
- locate target mod using Fabric Loader;
- inspect target `ModContainer` origin;
- resolve the loaded target JAR for the supported plain-JAR case;
- calculate runtime target SHA-256;
- compare against expected SHA-256;
- detect dedicated server ready state;
- execute one deterministic functional target behavior;
- inspect resulting real Minecraft state;
- atomically write versioned harness result;
- request clean shutdown;
- evolve `l11_fabric_fixture` minimally to expose the tested server-side behavior;
- add GameTest only where useful for fast harness/fixture regression.

Preferred functional acceptance:
a controlled block position begins in a known state, target functionality changes it, and harness verifies the expected block state.

If exact Minecraft APIs make this unnecessarily invasive, Codex may propose an equally strong deterministic server-world state transition, but must not replace it with a pure Java assertion.

Acceptance:

- harness compiles;
- target fixture compiles;
- tests for result protocol PASS;
- any GameTest regression introduced PASS;
- target JAR remains a normal Fabric JAR;
- harness is not packaged into target JAR;
- existing suite remains PASS.

Commit after Batch B.

Suggested commit:
`feat(test-harness): add fabric runtime harness fixture`

### Batch C — Real production-like Minecraft execution

Goal:
Connect `MinecraftTestRunner` to the real dedicated Fabric server and final target JAR.

Expected work:

- prepare unique isolated run directory;
- configure production-like Loom dedicated server execution;
- load the final remapped target JAR;
- load harness JAR and required runtime dependencies;
- pass fixed test metadata;
- capture stdout/stderr;
- enforce execution timeout;
- collect `latest.log`;
- collect crash reports if generated;
- read and validate harness result;
- correlate:
  - external target SHA;
  - runtime target SHA;
  - mod ID;
  - server readiness;
  - functional result;
  - process exit;
  - shutdown behavior;
- classify final result;
- persist canonical `result.json`.

Required negative scenarios:

1. wrong/nonexistent target mod ID → no PASS;
2. target hash mismatch → no PASS;
3. functional assertion failure → FAIL;
4. runtime crash → CRASH;
5. timeout/hang → TIMEOUT;
6. malformed/missing harness result → INFRA_ERROR or appropriate non-PASS classification.

Acceptance:

- real Minecraft 1.21.11 dedicated server starts automatically;
- exact final JAR is verified inside runtime;
- functional test passes against real Minecraft state;
- server shuts down without manual action;
- canonical evidence exists;
- repeated clean run passes;
- negative cases cannot produce false PASS.

Commit after Batch C.

Suggested commit:
`feat(test-harness): run validated jars in real fabric server`

### Batch D — PD Agent integration and final validation

Goal:
Integrate the runtime test as the post-artifact-validation evidence layer without breaking existing behavior.

Expected work:

- connect runtime test result to existing reporting/state architecture at the narrowest correct boundary;
- preserve provider-neutral core;
- preserve existing v0.1/v0.1.1 acceptance behavior where runtime testing is not requested;
- add v0.2 external validation scenario/script following existing validation conventions;
- ensure evidence is stored under the existing reporting philosophy;
- document invocation and supported scope;
- run complete regression suite;
- run final real Minecraft acceptance from a clean validation workspace.

Final acceptance run must record at least:

- repository commit;
- target JAR path;
- target mod ID;
- target SHA-256;
- Minecraft version;
- Loader version;
- Java version;
- server-ready evidence;
- runtime target hash match;
- functional test PASS;
- clean shutdown;
- process exit;
- evidence paths;
- total duration.

Acceptance:

- all automated tests PASS;
- existing v0.1/v0.1.1 validation remains PASS;
- v0.2 real Minecraft acceptance PASS;
- no manual interaction required;
- no unsupported architecture added;
- documentation matches implementation.

Commit after Batch D.

Suggested commit:
`feat(test-harness): integrate minecraft runtime acceptance`

## 4. Expected file areas

Exact paths must be decided from repository audit.

Likely areas, subject to audit:

- `src/pd_agent/` for runner/contracts;
- `tests/unit/` for Python contracts/classification;
- `tests/integration/` if existing conventions support it;
- `tests/fixtures/l11_fabric_fixture/` for target behavior;
- a dedicated testing-only Fabric harness fixture/module under `tests/fixtures/` or another existing test-support location;
- `scripts/validation/` for v0.2 external validation;
- `docs/` for usage/status updates.

Do not create a new top-level architecture solely for v0.2 unless repository conventions require it.

## 5. Evidence contract

Target conceptual layout:

`evidence/minecraft/<run_id>/`

Required artifacts:

- `spec.json`
- `target.json`
- `harness-result.json`
- `result.json`
- `stdout.log`
- `stderr.log`
- `latest.log` when produced
- `crash-reports/` when produced

`result.json` is canonical.

Evidence writes that represent completion should be atomic where practical.

## 6. Classification tests

At minimum test these decision paths:

- all evidence valid → PASS;
- functional assertion false with healthy runtime → FAIL;
- process abnormal termination before completion → CRASH;
- execution deadline exceeded → TIMEOUT;
- invalid result schema → INFRA_ERROR;
- target mod absent → non-PASS;
- runtime target SHA mismatch → non-PASS;
- clean functional result but forced shutdown → non-PASS;
- exit code 0 but missing functional evidence → non-PASS;
- log claims success but protocol evidence missing → non-PASS.

False PASS prevention has priority over fine-grained error labeling.

## 7. Security requirements

Implementation must:

- avoid model-provided arbitrary commands;
- constrain runtime paths;
- preserve existing `SecurePathResolver` / `ToolExecutor` security boundary;
- not weaken `SecurePathResolver` write/path restrictions globally;
- never commit Minecraft binaries;
- never package Mojang artifacts;
- not expose a generic process runner as an LLM tool;
- not add RCON/network listeners;
- treat target execution as potentially failing/untrusted within the limits of the current local execution model.

If stronger sandboxing is required for arbitrary third-party mods, document it as future work rather than overbuilding v0.2.

## 8. Reproducibility requirements

Each real test must:

- start from a fresh run directory;
- avoid previous world state;
- record versions;
- record target hash;
- use bounded timeouts;
- preserve enough logs to diagnose failure;
- be repeatable from documented commands.

Safe Gradle/Minecraft dependency caches may be reused.

## 9. Regression requirements

Before final acceptance:

- run full Python test suite;
- run existing Fabric fixture build validation;
- run v0.1/v0.1.1 validation relevant to regression;
- run v0.2 positive real-Minecraft acceptance;
- run selected negative runtime cases;
- verify git working tree contains only intended changes before commit.

No checklist item requiring validation is complete from implementation alone.

## 10. Rollback strategy

Each batch has its own commit.

If a batch fails:

- revert only that batch commit where possible;
- do not rewrite validated earlier batches unnecessarily;
- preserve evidence/logs from the failure for diagnosis.

If the production-run mechanism proves incompatible with the documented assumptions:
- stop;
- do not substitute `runServer` development classes silently;
- return to RFC/IMP correction.

## 11. Commit/push policy

After each accepted batch:

1. tests/build required for that batch PASS;
2. review diff;
3. commit with scoped message;
4. push to `origin/main` only if that matches the repository's established workflow and Codex audit confirms direct-main work remains intended;
5. report commit SHA and push result.

Final v0.2 is not complete until final commit and push are confirmed.

## 12. Final Definition of Done

v0.2 is done only when all are true:

- DESIGN implemented without unresolved deviations;
- RFC contracts satisfied;
- IMP batches completed;
- exact final target JAR loaded by real Fabric server;
- runtime target artifact identity verified;
- real server reached ready state;
- deterministic Minecraft-state behavior PASS;
- no crash;
- clean automated shutdown;
- evidence persisted;
- negative scenarios prevent false PASS;
- complete regression PASS;
- final commit pushed;
- repository clean;
- final evidence reviewed by ChatGPT;
- project returned to 00 Dirección for master-plan closure/update.

## 13. Codex audit output required before implementation

Codex must return:

1. baseline verification;
2. files/modules inspected;
3. reusable existing components and exact contracts;
4. DESIGN findings;
5. RFC findings;
6. IMP findings;
7. Fabric/Loom/Minecraft API verification;
8. discrepancies/risks;
9. exact proposed file plan;
10. test plan;
11. whether documentation requires correction;
12. explicit verdict:
   - `AUDIT PASS — READY TO IMPLEMENT`
   - or `AUDIT BLOCKED — DOC CHANGES REQUIRED`

Codex must not implement in the same step as this audit.
