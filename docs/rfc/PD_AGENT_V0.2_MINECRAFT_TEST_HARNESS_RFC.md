# PD Agent v0.2 — Minecraft Test Harness Foundation — RFC

Status: ACCEPTED
Area: 06 — Minecraft Test Harness
Depends on: PD Agent v0.2 DESIGN
Baseline: fff2d7cb06bb28dfdcec4803dad2d8e0c95ef596

## 1. Decision

v0.2 will validate the final remapped Fabric JAR using a real dedicated Fabric server launched through a Loom production-like server run path.

The runtime contains:

- target JAR;
- test harness Fabric mod;
- only the runtime dependencies required by the harness/target.

The harness executes inside Minecraft and produces structured evidence.

The Python-side `MinecraftTestRunner` orchestrates and validates the complete protocol.

## 2. Core flow

`ArtifactValidator PASS`
→ build `MinecraftTestSpec`
→ SHA-256 target JAR
→ prepare isolated run
→ launch dedicated Fabric production-like server
→ Fabric Loader starts
→ harness starts
→ verify target mod
→ verify runtime artifact identity
→ detect server ready
→ run functional test
→ inspect Minecraft state
→ write atomic harness result
→ request clean shutdown
→ process exits
→ runner correlates all evidence
→ classify result

## 3. MinecraftTestSpec

Minimum conceptual fields:

- `target_jar`
- `target_mod_id`
- `minecraft_version`
- `loader_version`
- `test_id`
- `timeout_seconds`

Initial supported environment:

- dedicated server only;
- Minecraft 1.21.11;
- Java 21;
- Fabric mod JAR;
- one target JAR per execution.

No generic testing DSL is introduced in v0.2.

## 4. MinecraftTestRunner responsibilities

The runner must:

1. Verify prerequisites.
2. Verify the target path.
3. Require prior artifact validation.
4. Calculate SHA-256 and size.
5. Create isolated runtime/evidence directories.
6. Configure the fixed production-like server launch.
7. Supply read-only test metadata.
8. Launch the process.
9. Capture stdout/stderr.
10. Enforce startup/test/shutdown limits.
11. Detect abnormal termination.
12. Read the harness result.
13. Validate the result schema.
14. Correlate the result with external process evidence.
15. Preserve latest.log and crash reports when available.
16. Produce `MinecraftTestResult`.
17. Clean up runtime resources according to policy.

## 5. Target artifact identity

Before launch:

`expected_sha256 = SHA256(target_jar)`

Inside Fabric:

- locate `target_mod_id` using Fabric Loader public APIs;
- obtain the loaded `ModContainer`;
- inspect its origin;
- require an acceptable path-based origin for the v0.2 target case;
- identify the runtime target JAR;
- calculate/compare its SHA-256 with `expected_sha256`.

Acceptance requires:

`runtime_target_sha256 == expected_sha256`

If the runtime origin cannot be verified sufficiently:

`INFRA_ERROR`

The harness must not silently downgrade this requirement to a log check.

## 6. Runtime lifecycle

Internal conceptual states:

- `PREPARING`
- `LAUNCHING`
- `FABRIC_LOADED`
- `TARGET_VERIFIED`
- `SERVER_READY`
- `TEST_RUNNING`
- `TEST_PASSED`
- `TEST_FAILED`
- `SHUTTING_DOWN`
- `COMPLETED`

These states do not require a new global enum if existing PD Agent state types should not be extended. Codex must audit the existing state model first.

`SERVER_READY` must be produced from a real server lifecycle signal inside the harness, not merely from process existence.

## 7. Harness configuration

No network IPC is introduced.

The runner may pass fixed read-only metadata through JVM/system properties or another equally narrow launch-time mechanism proven compatible during implementation.

Conceptual values:

- target mod ID;
- expected SHA-256;
- test ID;
- result-file path.

No arbitrary commands are accepted.

## 8. Harness result protocol

The harness writes one machine-readable result file atomically.

Conceptual schema:

```json
{
  "schema_version": 1,
  "test_id": "runtime_block_test",
  "target_mod_id": "pdagentl11",
  "target_loaded": true,
  "target_sha256_match": true,
  "server_started": true,
  "functional_test": "PASS",
  "shutdown_requested": true
}
```

The exact implementation schema must be versioned.

The runner does not trust this file alone.

It must correlate it with:

- expected target metadata;
- process status;
- timeout state;
- external SHA-256;
- runtime logs;
- crash reports.

## 9. Functional test contract

The v0.2 fixture must perform one deterministic server-side behavior that changes real Minecraft state.

Required pattern:

`known state`
→ `target operation`
→ `observable Minecraft state change`
→ `harness assertion`

A block-state operation is the preferred minimal case unless Codex finds a concrete compatibility reason to use another equally strong server-side state transition.

Pure Java return-value tests do not satisfy final acceptance.

## 10. GameTest

GameTest is not the sole production acceptance mechanism.

It may be used for:

- unit/integration-style in-game tests during build;
- harness regression tests;
- fixture behavior tests.

But the strong final acceptance remains:

`final target JAR + production-like dedicated server + runtime harness`

This avoids confusing development source-set validation with verification of the final distributed artifact.

## 11. Process execution

The runner must use a controlled process launch.

Required captured fields:

- command identity or normalized launch description;
- cwd/runDir;
- start timestamp;
- end timestamp;
- duration;
- exit code;
- timeout flag;
- stdout;
- stderr.

Raw arbitrary commands supplied by the LLM are forbidden.

## 12. Startup detection

A Minecraft process existing is not enough.

Startup evidence requires:

- Fabric Loader active;
- harness active;
- target verified;
- server lifecycle reached ready state.

If the process exits before this:

- classify `CRASH` when Minecraft/runtime failed abnormally;
- classify `INFRA_ERROR` when launch/configuration infrastructure prevented a meaningful runtime attempt.

## 13. Shutdown

Normal path:

functional test completes
→ result persisted
→ harness requests server stop
→ Minecraft performs clean shutdown
→ process exits
→ runner verifies successful termination

Forced termination path:

timeout
→ graceful terminate attempt
→ bounded grace period
→ hard kill if necessary

Any forced termination prevents `PASS`.

## 14. Public result classification

### PASS

Requires every contractual condition:

- validated artifact;
- correct target identity;
- target loaded;
- server ready;
- functional assertion passed;
- valid harness result;
- no crash;
- clean shutdown;
- acceptable process exit;
- evidence persisted.

### FAIL

The runtime/protocol was healthy but the functional assertion failed.

### CRASH

Minecraft/Fabric terminated abnormally before successful protocol completion.

### TIMEOUT

The configured execution deadline was exceeded.

### INFRA_ERROR

Examples:

- unsupported Java;
- launch preparation failure;
- invalid harness result;
- unresolvable target origin;
- missing dependency;
- Gradle/Loom execution infrastructure failure.

## 15. Evidence layout

Conceptual layout:

```text
evidence/minecraft/<run_id>/
├── spec.json
├── target.json
├── harness-result.json
├── result.json
├── stdout.log
├── stderr.log
├── latest.log
└── crash-reports/
```

`target.json` must include at least:

- target path;
- mod ID;
- file size;
- SHA-256;
- Minecraft version;
- Loader version;
- Java version.

`result.json` is the canonical PD Agent-consumable runtime result.

## 16. Isolation

Each execution gets:

- unique run ID;
- fresh run directory;
- fresh world/runtime state;
- fresh configuration;
- fresh evidence files.

Safe dependency caches may be reused.

Previous world state must never be able to produce a false PASS.

## 17. Security

The test runner is not a generic shell.

The launch mechanism, Gradle task, supported flags and output locations are controlled by PD Agent code.

Existing `SecurePathResolver` and `ToolExecutor` security constraints must be preserved; any extension must be explicit and narrowly scoped.

The target JAR must pass existing artifact validation before runtime testing.

## 18. Integration boundary

Do not turn `GradleBuildRunner` into a Minecraft runtime runner.

Preferred conceptual pipeline:

`GradleBuildRunner`
→ `ArtifactValidator`
→ `MinecraftTestRunner`

Existing `RunState`, `RunStorage`, reporting and process helpers should be reused only where their real contracts fit.

Codex must audit them before implementation.

## 19. Failure precedence

When multiple signals exist, final classification must avoid false PASS.

Minimum precedence principle:

- timeout overrides incomplete success evidence;
- crash overrides incomplete functional evidence;
- invalid/missing protocol evidence prevents PASS;
- target identity mismatch prevents PASS;
- failed functional assertion is FAIL only when infrastructure and runtime were otherwise healthy.

Detailed precedence belongs in implementation logic/tests.

## 20. Compatibility

Initial compatibility contract:

- Java 21;
- Minecraft 1.21.11;
- Fabric Loader 0.19.3;
- Loom 1.13.3;
- Windows local validation required because that is the current project environment;
- design must remain compatible with future CI/headless Linux without introducing client GUI requirements.

## 21. EULA/distribution

PD Agent must not redistribute Mojang/Minecraft server binaries.

Runtime artifacts shall be resolved through supported Minecraft/Fabric/Loom tooling.

No Minecraft binary is committed to the repository.

## 22. Acceptance invariants

v0.2 must never mark PASS based only on:

- process startup;
- a line in latest.log;
- exit code 0;
- mod ID presence without target artifact identity;
- pure Java method behavior;
- development classes instead of the final JAR;
- stale world state;
- manually observed behavior.

## 23. Final acceptance evidence chain

The final acceptance must establish:

`target.jar SHA X`
→ Fabric Loader loaded target mod ID
→ runtime target origin resolves to SHA X
→ Minecraft server reached ready state
→ target functionality changed real Minecraft state
→ harness observed expected state
→ result persisted
→ server shut down cleanly
→ runner classified PASS

## 24. Implementation constraint

No implementation begins until:

1. IMP is written.
2. Codex audits DESIGN + RFC + IMP against the real repository.
3. Any discovered incompatibility is reflected back into the documents before implementation.

## 25. References

Primary technical references:

- Fabric automatic testing / GameTest documentation
- Fabric Loom production run task documentation
- Fabric Loader API documentation
- Minecraft EULA

Repository baseline evidence:

- `tests/fixtures/l11_fabric_fixture/gradle.properties`
- `tests/fixtures/l11_fabric_fixture/build.gradle.kts`
- `tests/fixtures/l11_fabric_fixture/src/main/resources/fabric.mod.json`
- `tests/fixtures/l11_fabric_fixture/src/main/java/dev/pdpunto/l11/ExampleMod.java`
- `scripts/validation/validate_v0_1.py`
