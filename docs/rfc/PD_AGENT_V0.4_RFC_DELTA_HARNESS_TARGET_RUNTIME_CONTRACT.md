# PD Agent v0.4 RFC Delta: Harness Target Runtime Contract

## Status

Proposed.

## Baseline

- `HEAD == origin/main == ae489b25d728bf68c7aac5d60a347b3a68b44b9e`
- `scripts/benchmark/diagnostics/` may exist locally and is out of scope.

## Problem

The current Minecraft harness still has a compile-time dependency on the target fixture:

- `tests/fixtures/l11_minecraft_harness/build.gradle.kts` uses `compileOnly(files("../l11_fabric_fixture/build/classes/java/main"))`
- `HarnessRunner.java` imports `dev.pdpunto.l11.ExampleMod`
- `HarnessRuntimeOptions.java` imports `dev.pdpunto.l11.ExampleMod`

That contract only works when the sibling fixture has precompiled classes on disk. The live benchmark does not provide that sibling class directory. It provides a validated target JAR inside the benchmark workspace and injects that JAR at runtime.

Result: the harness compile step fails before Minecraft starts, even though the benchmark-produced target artifact is valid.

## Real repo facts

### Target fixture manifest

The validated target JAR is the Fabric mod with:

- `schemaVersion = 1`
- `id = "pdagentl11"`
- `version = "1.0.0"`
- `environment = "*"`
- `entrypoints.main = ["dev.pdpunto.l11.ExampleMod"]`
- `depends.fabricloader = ">=0.19.3"`
- `depends.minecraft = "~1.21.11"`

### Target runtime helper

The target class currently exposes:

```java
public static boolean applyProbeState(ServerWorld world, BlockPos pos)
```

and that method calls:

```java
world.setBlockState(pos, PROBE_STATE, Block.NOTIFY_ALL)
```

It also exposes:

```java
public static BlockState expectedProbeState()
```

which resolves to `Blocks.DIAMOND_BLOCK.getDefaultState()`.

### Current harness runtime properties

`MinecraftTestRunner` already passes target identity and runtime control through system properties, including:

- `pd.agent.targetJar`
- `pd.agent.targetModId`
- `pd.agent.targetSha256`
- `pd.agent.testId`
- `pd.agent.resultPath`
- `pd.agent.runDir`
- `pd.agent.resultMode`
- `pd.agent.expectedBlockStateId`
- `pd.agent.expectNeighborUpdate`
- `pd.agent.hangMillis`

The harness Gradle task consumes `pd.agent.targetJar` and `pd.agent.runDir`, and the Minecraft runtime receives the validated target JAR and harness JAR through `mods.from(files(targetJar, harnessJar))`.

## Contract problem to solve

The harness must be able to validate dynamically produced benchmark artifacts without compiling against the target fixture's sibling classes.

The target JAR is runtime input, not compile-time source dependency.

## New contract

### Ownership

- `BenchmarkExecutor` remains responsible for producing the benchmark artifact and for deciding whether Minecraft validation should run.
- `MinecraftTestRunner` remains responsible for validating the target JAR containment, mod id, SHA, and runtime launch plan.
- The harness remains responsible for runtime validation of the loaded target JAR.
- A new harness-local `TargetBridge` becomes responsible for invoking the target contract at runtime.

### Entry point discovery

`MinecraftTestRunner` must inspect the validated target JAR's `fabric.mod.json` and derive the Fabric entrypoint class from the artifact itself.

For v0.4, the contract is:

- use the validated JAR's `entrypoints.main`
- take the first entrypoint class as the runtime target class
- pass that derived class to the harness as runtime configuration

No untrusted class name may be accepted from an arbitrary path or from user input.

### Runtime bridge

The harness must resolve the target class in runtime only and invoke the exact contract required by these fixtures:

- `applyProbeState(ServerWorld, BlockPos)`

The harness must fail explicitly if:

- the class does not exist
- the method does not exist
- the signature does not match
- the invocation throws

There is no fallback to `l11_fabric_fixture` classes.

### Expected state

`HarnessRuntimeOptions` must not depend on `ExampleMod.expectedProbeState()` at compile time.

For v0.4, the expected block state for `diamond_block` remains the same, but it is resolved inside harness code using Minecraft APIs and harness configuration, not through the target class import.

### Security

The following must remain enforced:

- target containment inside `project_root`
- `SecurePathResolver`
- SHA validation
- mod id validation
- runtime-only loading of the target JAR

The following remain forbidden:

- arbitrary classpath injection
- arbitrary class names from unsafe input
- filesystem escape
- fallback to static sibling fixture classes
- false PASS from accidental fixture reuse

Reflection must stay scoped to the explicit harness contract only.

## Compatibility

### B001

Compatible.

- runtime bridge invokes `applyProbeState`
- expected state stays `diamond_block`
- neighbor update logic remains unchanged

### B002

Compatible.

- B002 primary controls do not depend on the Minecraft harness contract
- no functional change to benchmark semantics

### B003

Compatible.

- same runtime bridge
- same `test_id`
- `expect_neighbor_update` remains the independent authority for signal validation
- the neighbor signal mixin and harness listener remain intact

## Error taxonomy

The runtime bridge must surface failures as explicit harness/runtime failures, not silent PASSes.

Recommended classification:

- missing entrypoint class -> `INFRA_ERROR`
- missing method or signature mismatch -> `INFRA_ERROR`
- invocation failure -> `INFRA_ERROR`
- containment / SHA / mod id failures -> existing `INFRA_ERROR` preflight path

The benchmark classifier should continue to map these as Minecraft harness / infrastructure failures.

## Non-goals

- Do not change B001/B002/B003 semantics.
- Do not change dataset freeze controls.
- Do not change acceptance.
- Do not relax `SecurePathResolver`.
- Do not copy classes into the sibling fixture.
- Do not introduce a broad reflection framework.
- Do not add a new top-level design layer.

## Evidence requirements

The implementation must preserve evidence for:

- target JAR path
- target SHA
- derived entrypoint class
- runtime harness result
- containment and launch plan
- environment overrides

## Conclusion

The repo supports a runtime-only target contract. The current compile-time harness dependency is the mismatch. The fix is to move the target interaction to runtime and remove compile-time coupling to `ExampleMod` and the sibling compiled classes directory.
