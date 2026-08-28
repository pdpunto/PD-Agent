# PD Agent v0.8 - I15 Build and Artifact Readiness

## Status

`I15_HOST_FINAL_PASS`

I15, Real Build and Artifact Readiness, is closed as `PASS` on technical
baseline `fcad625f5549b8f5d85fe70e62bb2dbdacf68159`.

This record documents implementation and build-readiness evidence only. It
does not start or authorize I16.

## Defects and Fixes

### Canonical Seed Identity

The original portable identity implementation and the bootstrap path used
different semantics. The product-neutral `portable_seed_identity` helper now
centralizes the canonical file inventory and identity calculation. It keeps
the declared nonportable entries excluded, rejects symlinks, and does not
relax filtering for ordinary Gradle cache mutations.

### Generated Kotlin DSL

Generated `build.gradle.kts` contained invalid escaped property interpolation.
The generator now emits valid Kotlin DSL property expressions while retaining
the pinned versions and the existing bootstrap contract.

### Environment Blocker

Codex sandbox execution encountered `RmStartSession` / `AccessDenied` while
the host control validated the same offline build. This was classified as an
environmental blocker, not a product defect.

### Post-Gradle Restore

The host driver attempted to call `restore()` after Gradle had legitimately
mutated the Gradle home. The final driver no longer performs that call. A
fresh Gradle home is used for each validation run instead of weakening seed
identity filters.

### Physical Seed Recovery

The former seed path was missing 203 entries and therefore did not match its
stored manifest. An exact canonical copy was recovered and materialized under
a new controlled temporary snapshot with identity
`eb211b00633cbbc909d2494c777c1070ad0db668aa0e64896e9691d2f3bfba83` and
`10453` components. The expected `minecraft-server.jar` SHA-256 is
`F83B8E093865806F931C7E34AAE41B177D4C076335263DD124C75D6D65DD1726`.
No filter relaxation was introduced.

## Final Host Validation

The final host validation used two new independent host-owned LaunchRoots and
did not reuse the historical Run 1 as a passing requirement.

Both runs demonstrated:

- canonical seed identity and `10453` components;
- pinned Minecraft `1.21.11`, Loader `0.19.3`, Fabric API `0.141.6+1.21.11`,
  Yarn `1.21.11+build.6`, Loom `1.13.3`, Java `21`;
- `ProjectInspector READY`;
- real wrapper execution with `--offline --no-daemon build`;
- build exit code `0`;
- `ArtifactValidator VALID`;
- artifact size `1469` bytes;
- artifact SHA-256
  `EDAF5A9939ABA19FC5587010D491EF9555FCDF2E955845A3F39A156413368B6A`;
- source A artifact current and source B artifact stale;
- independent Gradle homes and byte-identical artifacts.

The persisted host summary is temporary validation evidence, not a product
artifact. It is not required for normal product operation.

## Validation

- focused I15 tests: `72 passed, 1 skipped`;
- full suite: `1077 passed, 3 skipped`;
- `compileall src tests`: `PASS`;
- `git diff --check`: `PASS`.

The first focused invocation was blocked before test execution by a Windows
permission error while pytest inspected its default temporary directory. The
same tests passed using an isolated temporary basetemp; no test was excluded.

## Boundaries and Compatibility

- network fallback: `0`;
- provider/API: `0`;
- Minecraft runtime: `0`;
- benchmark live: `0`;
- global Gradle: `0`;
- real wrapper: used;
- v0.5/v0.6/v0.7 contracts: unchanged;
- historical executions and evidence: unchanged;
- product capability scope: not expanded.

## Final Verdict

`V0_8_I15_PASS`

I16 remains pending separate authorization. No v0.9 scope is defined here.
