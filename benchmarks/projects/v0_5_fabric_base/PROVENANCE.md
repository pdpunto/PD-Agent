# Provenance

## Source

- Upstream template: `FabricMC/fabric-example-mod`
- Pinned revision: `8b74965019e71006f0e540b2c570f46fb84d20cb`
- Branch reference: `refs/heads/1.21.11`

## Version Line

- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Fabric API: `0.141.6+1.21.11`
- Fabric Loom: `1.13.3`
- Yarn: `1.21.11+build.6`
- Java: `21`
- Gradle Wrapper: `8.14.3`

## Local Adaptation

- Retained a small conventional Fabric mod layout.
- Pinned the repository to the frozen v0.5 line.
- Replaced benchmark-specific names and helper paths with a generic example mod layout.
- Kept the project independent from benchmark tasks, harness helpers, and solution hints.

## Identity

- Tree hash algorithm: `sha256-tree-v1`
- Tree hash: `0b663a8712b72f194aa6d09b4608e57a102a8089559067fcf3a579dd0ba21706`

## Rebase Note

- F1 was reopened after F6 runtime evidence showed the project base needed the Fabric API runtime dependency restored for the reference implementation to start cleanly in Minecraft.
- The project base now pins the Fabric API dependency in `build.gradle.kts` and `gradle.properties`.

## Notes

- The project is intended as a representative baseline project, not a benchmark fixture.
- Generated build outputs are intentionally excluded from the canonical tree.
