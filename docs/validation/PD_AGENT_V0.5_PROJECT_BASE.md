# PD Agent v0.5 Project Base Validation

Status: PASS
Date: 2026-08-16

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Baseline commit: `289524cb05abebf2009b93b572e70cf4601babb3`
- HEAD: `289524cb05abebf2009b93b572e70cf4601babb3`
- origin/main: `289524cb05abebf2009b93b572e70cf4601babb3`

## Working Tree

- Tracked tree: clean before this F1 change
- Preexisting untracked diagnostics: `scripts/benchmark/diagnostics/`

## F1 Decision

- Option chosen: `C`
- Reason: the existing benchmark fixtures and `tests/fixtures/l11_fabric_fixture` are benchmark-adapted and not representative enough for the v0.5 project-base milestone.
- The final project base is a pinned representative Fabric project snapshot tracked in `benchmarks/projects/v0_5_fabric_base/`.
- F1 was reopened after F6 runtime evidence confirmed the project base needed the Fabric API runtime dependency restored.

## Upstream / Provenance

- Upstream template: `FabricMC/fabric-example-mod`
- Pinned revision: `8b74965019e71006f0e540b2c570f46fb84d20cb`
- Branch reference: `refs/heads/1.21.11`

## Version Line

- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Fabric Loom: `1.13.3`
- Yarn: `1.21.11+build.6`
- Java: `21`
- Gradle Wrapper: `8.14.3`

## Project Base

- Path: `benchmarks/projects/v0_5_fabric_base`
- Main files:
  - `build.gradle.kts`
  - `settings.gradle.kts`
  - `gradle.properties`
  - `PROVENANCE.md`
  - `src/main/resources/fabric.mod.json`
  - `src/main/java/com/example/examplemod/ExampleMod.java`
  - `src/main/java/com/example/examplemod/client/ExampleModClient.java`

## Identity

- Tree hash algorithm: `sha256-tree-v1`
- Tree hash: `43fa87dbff8a1602d61755cba17fedcae155b08f2763cf7b197d3e56596c43e3`

## Wrapper

- `gradlew`: present
- `gradlew.bat`: present
- `gradle/wrapper/gradle-wrapper.jar`: present
- `gradle/wrapper/gradle-wrapper.properties`: present

## Inspector

- `ProjectInspector`: `READY`
- `fabric.mod.json` mod id: `examplemod`
- main entrypoint: `com.example.examplemod.ExampleMod`
- client entrypoint: `com.example.examplemod.client.ExampleModClient`

## Baseline Build

- Executed on a fresh temporary copy of `benchmarks/projects/v0_5_fabric_base`
- Command: Gradle wrapper `build`
- Result: `BUILD SUCCESSFUL`

## Rebase Note

- The project base now restores `fabric_api_version=0.141.6+1.21.11` in `gradle.properties`.
- The build file now restores `modImplementation("net.fabricmc.fabric-api:fabric-api:${property("fabric_api_version")}")`.
- F1 remains the same representative base, but the dependency line is now part of the frozen base contract after the F6 runtime evidence.

## Artifact Validation

- Artifact jar: `examplemod.jar`
- Artifact classification: `VALID`
- Artifact mod id: `examplemod`
- Artifact version: `1.0.0`

## Representativeness Review

1. Yes, this is more representative than `tests/fixtures/l11_fabric_fixture`.
2. Yes, it contains normal Fabric source/resources rather than benchmark helpers.
3. Yes, it allows future multi-file changes.
4. Yes, it allows adding classes/resources naturally.
5. Yes, it avoids revealing future benchmark tasks.
6. No, it is not excessively simplified for a base project.
7. No, it is not coupled to the harness.

## Forbidden Helper Audit

- No `B001`, `B002`, `B003`
- No `HarnessRunner`
- No `TargetBridge`
- No `applyProbeState`
- No `expectedProbeState`
- No `probeIdentifier`
- No `Registries.BLOCK`

## Tests Executed

- `python -m compileall src scripts tests`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q tests\\unit\\test_v0_5_project_base.py tests\\unit\\test_l4_project_inspector.py tests\\unit\\test_l5_gradle_build_runner.py`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q`

## Results

- Compile: PASS
- Focused tests: PASS
- Full suite: PASS
- Baseline build/artifact on temp copy: PASS

## Risks / Limitations

- `scripts/benchmark/diagnostics/` remains preexisting and untracked.
- Runtime sanity is not part of F1 yet; that remains for later milestones.
- The project base is pinned and reproducible, but its validation build still depends on the existing Gradle/Minecraft caches available in the validated environment.

## Final Verdict

F1 accepted and frozen as the representative pinned Fabric base project for PD Agent v0.5.
