# PD Agent v0.11 M2 Platform Evidence

## Baseline

- Baseline: `8ca84cdf58a81956e1d6a3cb2a1c8ae053c04375`
- R116 scope: Lot I only
- External provider/API requests: 0
- Minecraft launches: 0
- Benchmark runs: 0
- Product executions: 0

## Evidence Gate

`FabricPlatformProfile.evidence_gate_passes` requires the following required
evidence kinds for `SUPPORTED`:

- `PROFILE_DEFINITION`
- `INSPECTION_RESOLUTION`
- `CONTRACT_WIRING`
- `BRAIN_COMPATIBILITY`
- `OFFLINE_BUILD`

The model also defines `BOOTSTRAP` and `IMPORT`; these are reported below when
there is concrete evidence for them. No evidence kind was weakened or bypassed.

## Platform Matrix

| Platform | Profile | Inspection | Contract | Brain | Bootstrap | Import | Offline build | Final status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fabric 1.21.11 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SUPPORTED |
| Fabric 26.1.2 | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | TARGET / not supported |
| Fabric 26.2 | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE | TARGET / not supported |

The legacy profile is the only source-controlled `SUPPORTED` profile. Its
offline build evidence is now revalidated. Modern platforms were not promoted.

## Legacy 1.21.11

Profile pins are declarative in
`src/pd_agent/fabric/data/platform_profiles.json`:

- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Fabric API: `0.141.6+1.21.11`
- Loom: `1.13.3`
- Java: `21`
- Mappings: Yarn `1.21.11+build.6`
- Mapping family: `OBFUSCATED_REMAPPED`
- Mapping namespace: `yarn`
- Support status: `SUPPORTED`

Offline evidence already present in the repository:

- profile loading and exact adapter tests in `tests/unit/test_fabric_platform_support.py`;
- bootstrap and profile/template pairing in `tests/unit/test_r113_bootstrap_templates.py`;
- Product inspection, resolution and exact contract environment in
  `tests/unit/test_productive_contract_preflight.py`;
- imported workspace inspection without bootstrap provenance in
  `tests/unit/test_r115_imported_project_currentness.py`;
- Brain environment adaptation in `tests/unit/test_fabric_platform_support.py`
  and `tests/unit/test_r115_imported_project_currentness.py`.

The real build command attempted for this gate was:

```text
gradlew.bat --offline --no-daemon --console=plain compileJava
```

It used Java 21 and fresh temporary roots:

- workspace: `C:\dev\pruebas\pd-agent-r116-legacy-build-02f315e9e73e4d898511ef8d160070b1`
- `GRADLE_USER_HOME`: `C:\dev\pruebas\pd-agent-r116-gradle-home-43593299c8334e0da567cf76f3de411d`

The first isolated attempt used a Gradle home without the wrapper distribution
and was not accepted as evidence. R117 recovered the existing local
distribution from `%USERPROFILE%\\.gradle\\wrapper\\dists` and the persistent
v0.8 seed, then ran the same build from a fresh temporary Gradle home. Result:
`BUILD SUCCESSFUL`, exit code `0`, using Gradle `8.14.3` and Java `21.0.11`.

Artifact evidence:

- JAR: `C:\\dev\\pruebas\\pd-agent-r116-legacy-build-02f315e9e73e4d898511ef8d160070b1\\build\\libs\\examplemod.jar`
- SHA-256: `2262C6B7747EE8C7CBDC58B92AEA697F4C2C8D1E70AF60E8A86366BA45209E26`
- `OFFLINE_BUILD=PASS`

## Modern Pins

The approved pre-implementation audit records that exact local pins for
Minecraft, Loader, Fabric API, Loom and the required modern environment were
not verified. The local cache/repository audit found no approved exact pin set
for either `26.1.2` or `26.2`.

Consequently:

- no modern profile was created or promoted;
- no Yarn or mappings value was invented;
- `UNOBFUSCATED` remains the intended modern family only where a future
  evidence-backed profile is defined;
- no modern Brain compatibility claim was made;
- no modern bootstrap or build claim was made;
- Product must continue to fail closed for modern target-shaped environments.

Existing tests demonstrate the declarative modern rendering shape without
claiming support in `tests/unit/test_r113_bootstrap_templates.py` and the
target/unsupported resolution behavior in
`tests/unit/test_fabric_platform_support.py`.

## Product Fail-Closed

Current Product preflight resolves the current inspection through
`FabricSupportRegistry` and accepts only `SUPPORTED`. `TARGET`, `RETIRED`,
unsupported, unknown and conflicting observations do not produce an executable
profile. R114/R115 tests demonstrate that failed currentness occurs before
`ExecutionRecord` persistence and worker dispatch.

Import origin and bootstrap provenance are not support authorities. The
workspace is inspected again for every Product preflight.

## Brain and Wrong-Pack Boundary

The current Fabric contract is adapted to `KnowledgeEnvironment` before Brain
preparation and repair wiring. A fixed legacy knowledge pack does not promote a
modern platform: modern platforms have no supported profile and no compatible
modern knowledge evidence. No modern pack was fabricated for this gate.

## Tests and Validation

Focal/regression command:

```text
\.venv-l0fix\Scripts\python.exe -m pytest -q tests/unit/test_fabric_platform_support.py tests/unit/test_fabric_bootstrap.py tests/unit/test_fabric_task_contract.py tests/unit/test_r112_brain_platform_selection.py tests/unit/test_r113_bootstrap_templates.py tests/unit/test_r114_product_platform_preflight.py tests/unit/test_r115_imported_project_currentness.py tests/unit/test_productive_contract_preflight.py tests/unit/test_product_fabric_execution.py tests/unit/test_product_application.py tests/unit/test_product_execution.py tests/unit/test_brain_orchestration.py tests/unit/test_l1_brain_environment.py tests/unit/test_productive_runtime_wiring.py --basetemp=C:\dev\pruebas\pd-agent-r116-focal-20260903 -p no:cacheprovider
```

Result: `170 passed` on the R109-R116 focal/regression command.

Static validation:

- `python -m compileall src tests`: PASS
- `git diff --check`: PASS

## Non-Claims and Next Gate

This document does not claim multi-platform support certification. The current
classification is:

`MULTI_PLATFORM_SUPPORT_NOT_YET_CERTIFIED`

The exact next step is to provide an approved, locally materialized Gradle
distribution and rerun the legacy strict offline build, then separately obtain
approved exact pins and complete evidence for modern profiles. No Lot J work is
started by this evidence gate.

## R118 - Fabric 26.2 Materialization Audit

The official Fabric example-mod `26.2` branch was audited on 2026-09-03. The
following upstream files are the provenance for the modern reference pins:

- `gradle.properties`: Minecraft `26.2`, Loader `0.19.3`, Loom `1.17-SNAPSHOT`,
  Fabric API `0.158.0+26.2`.
- `build.gradle`: `net.fabricmc.fabric-loom`, Java release/toolchain `25`.
- `gradle/wrapper/gradle-wrapper.properties`: Gradle `9.5.1` binary wrapper.
- `src/main/resources/fabric.mod.json`: Minecraft `~26.2`, Loader `>=0.19.3`,
  Java `>=25`, and Fabric API dependency.

Official references:

- https://github.com/FabricMC/fabric-example-mod/tree/26.2
- https://raw.githubusercontent.com/FabricMC/fabric-example-mod/26.2/gradle.properties
- https://raw.githubusercontent.com/FabricMC/fabric-example-mod/26.2/build.gradle
- https://raw.githubusercontent.com/FabricMC/fabric-example-mod/26.2/gradle/wrapper/gradle-wrapper.properties
- https://raw.githubusercontent.com/FabricMC/fabric-example-mod/26.2/src/main/resources/fabric.mod.json
- https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/0.158.0%2B26.2/

The modern mapping semantics are `UNOBFUSCATED` with no Yarn dependency and no
mapping namespace/version. The repository model already supports that shape,
but there is no source-controlled 26.2 profile or template and no evidence was
created to promote it.

Local materialization audit:

- The host has only `C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot`;
  no JDK 25 installation is available.
- Local Gradle wrapper distributions include `8.14.3`, `8.9` and `9.2.0`, but
  not the official `9.5.1` distribution required by the 26.2 reference.
- No approved local 26.2 Minecraft, Loader, Fabric API or Loom material was
  found in the inspected Gradle caches or PD-Agent materialization roots.
- Consequently no 26.2 bootstrap, online build, strict offline rebuild, JAR,
  Inspector match, Brain compatibility proof, wrong-pack rejection, or
  post-promotion Product proof is claimed.

R118 decision:

- Initial 26.2 profile: not added; the platform remains `TARGET` implicitly
  unsupported by the source-controlled registry.
- Template compatibility: declarative modern rendering is covered by the
  existing target-only bootstrap test; no production template change was made.
- Registry/Product: existing fail-closed TARGET behavior remains unchanged.
- Brain: no 26.2 knowledge source or frozen pack was fabricated.
- Required evidence: `PROFILE_DEFINITION`, `INSPECTION_RESOLUTION`,
  `CONTRACT_WIRING`, `BRAIN_COMPATIBILITY` and `OFFLINE_BUILD` are not a
  complete real 26.2 evidence set; promotion is forbidden.
- 26.1.2: no new evidence was established.

Classification: `FABRIC_26_2_SUPPORT_NOT_CERTIFIED`.

Overall classification: `MULTI_PLATFORM_SUPPORT_NOT_YET_CERTIFIED`.

The exact blocker is missing locally materialized Java 25 and the complete
official 26.2 toolchain/cache set needed for a real online build followed by a
strict offline rebuild. No product defect was demonstrated, no production code
was changed, and Lot J was not started.

## R119 - 26.2 Toolchain and Build Gate

R119 materialized the official toolchain in isolated roots. Temurin JDK 25 was
downloaded from the Adoptium API as a portable ZIP and extracted without
changing global `JAVA_HOME` or `PATH`:

- Vendor/version: Eclipse Temurin `25.0.4.1+1`, Windows x64.
- JDK root: `C:\dev\pruebas\pd-agent-r119-toolchain-ece20dc41dd2468fb29fcccdbf3377b1\jdk-25.0.4.1+1`.
- `java -version`: `25.0.4.1`.
- `javac -version`: `25.0.4.1`.
- Archive SHA-256: `00C847D804F4A78E9F04F2683FAF14FED898535B177B7FC704486CB0284E9283`.
- Official source: https://api.adoptium.net/v3/binary/latest/25/ga/windows/x64/jdk/hotspot/normal/eclipse

The official Fabric example-mod branch `26.2` was checked out at commit
`34080f0b6644dd726519d578f339f8e4e50ad331`. Its wrapper materialized Gradle
`9.5.1`. The generated TARGET profile uses the exact R118 pins and the
official wrapper files.

The first generated Kotlin DSL build exposed two real bootstrap defects:

1. Modern dependencies must use `implementation`, not legacy
   `modImplementation`.
2. Modern Loom uses plugin id `net.fabricmc.fabric-loom`, not the legacy
   `fabric-loom` alias.

The minimal conditional fix is in `src/pd_agent/bootstrap.py`; Legacy keeps its
existing configuration. Regression assertions were added to
`tests/unit/test_r113_bootstrap_templates.py`. The declarative 26.2 TARGET
profile and template are in `src/pd_agent/fabric/data/platform_profiles.json`
and `src/pd_agent/fabric/data/project_templates.json`.

Bootstrap result: `PASS`, `READY`, with Minecraft `26.2`, Loader `0.19.3`,
Fabric API `0.158.0+26.2`, Loom `1.17-SNAPSHOT`, Java `25`,
`UNOBFUSCATED`, no Yarn and no `mappings_version`.

Online build:

```text
gradlew.bat --no-daemon --console=plain build
```

Result: `BUILD SUCCESSFUL`, exit code `0`, workspace
`C:\dev\pruebas\pd-agent-r119-26.2-online-final-6b8cf46a54064eceb68f3575d68f3b70`,
isolated Gradle home
`C:\dev\pruebas\pd-agent-r119-gradle-home-final-335e8c91702b485c9138f0645f3d5845`.

Strict offline rebuild:

```text
gradlew.bat --offline --no-daemon --console=plain build
```

Result: `BUILD SUCCESSFUL`, exit code `0`, clean workspace
`C:\dev\pruebas\pd-agent-r119-26.2-offline-c6c4b072e33a43628495790e622100c7`.

Both artifacts are `modid-1.0.0.jar`, 1406 bytes, and have identical SHA-256:
`40CC8F8210912B5E83A5E497235C912D6FB0F78573D169CCA1D2D0DD0317F5E3`.
`OFFLINE_BUILD=PASS` is therefore established for the generated TARGET
workspace.

Inspector and resolution:

- `FabricInspector`: `READY`; Minecraft, Loader, Fabric API and Loom observed.
- Java and mapping family are not observed by the current Inspector; modern
  mapping facts remain null/missing rather than receiving defaults.
- Exact adapter: `FabricEnvironmentConstraints` and `KnowledgeEnvironment`
  contain Java `25`, `UNOBFUSCATED`, and null mappings.
- Registry result remains `UNSUPPORTED / NO_SUPPORTED_PROFILE` because the
  profile is TARGET and the Inspector lacks all matching facts. Product
  preflight therefore fails closed with zero record/worker/provider activity.

Brain compatibility is not available for 26.2. Existing Yarn
`1.21.11+build.6`, Fabric API `0.141.6+1.21.11`, and curated concept sources
all return `INCOMPATIBLE`; no modern source or frozen pack was fabricated.
Legacy knowledge is consequently rejected for the 26.2 environment.

Evidence gate:

| Evidence kind | 26.2 result |
| --- | --- |
| PROFILE_DEFINITION | PASS, TARGET declaration |
| BOOTSTRAP | PASS |
| INSPECTION_RESOLUTION | FAIL / incomplete modern facts |
| CONTRACT_WIRING | PASS, exact adapter and null mappings |
| BRAIN_COMPATIBILITY | FAIL, no compatible 26.2 source |
| OFFLINE_BUILD | PASS |
| IMPORT | NOT RUN, promotion prerequisite absent |

Promotion: `NO`. 26.2 remains `TARGET`; no after-promotion Product,
import-origin, currentness or Minecraft validation is claimed. Legacy remains
SUPPORTED and its R117 offline evidence is unchanged.

R119 tests: `40 passed` for the platform/bootstrap focal tests; prior
R109-R116 regression evidence remains `170 passed`. `compileall`: PASS.
`git diff --check`: PASS. API/provider, Minecraft and benchmark activity: `0`.
