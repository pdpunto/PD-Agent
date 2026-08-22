# PD Agent v0.5 Offline Validation

Status: PASS  
Milestone: Fabric Agent Capability Foundation  
Validation baseline: `1f404c54d33fc4e4db6dd18d54ceb7570ee0e6d4`  
Branch: `main`

## Scope

This document records the completed F7 offline validation. It does not start
or approve F8, and it does not replace the historical F0-F6 validation
documents.

No provider API, Gemini/OpenAI request, live benchmark matrix, or F8 smoke was
executed for this validation.

## Dataset and Project

- dataset: `PD_AGENT_BENCHMARK_DATASET_V0.5_5`;
- dataset version: `0.5.5`;
- task count: `3`;
- project base identity:
  `3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396`;
- project inspector: `READY`.

## Gradle Environment

- seed identity:
  `3f45504a92b4c3ca6a0aff10933f8f193104b5fec08fbdfab50a285900f0e665`;
- seed component count: `11742`;
- `GRADLE_USER_HOME`: fresh and isolated for every build;
- fallback to `~/.gradle`: not used;
- project base: canonical `benchmarks/projects/v0_5_fabric_base`;
- dependency graph includes Fabric API `0.141.6+1.21.11`;
- two independent HOST builds: PASS;
- ArtifactValidator: VALID;
- AccessDenied on `minecraft-server.jar`: not reproduced on HOST; the earlier
  occurrence was a Codex/sandbox limitation and requires no product workaround.

The canonical validation command is:

```text
gradlew.bat build --offline --no-daemon --stacktrace --info --console=plain
```

Each build uses a new workspace and a new materialized
`GRADLE_USER_HOME` from the validated seed. The earlier probe that invoked
only `gradlew.bat build` is not considered F7 gate evidence.

## Capability Coverage

- dataset/catalog loading and schema validation: PASS;
- acceptance resources and required Minecraft observation contracts: PASS;
- runtime dependency resolution, provenance, SHA and confinement: PASS;
- Minecraft contracts, target identity and result classification: PASS;
- AgentRuntime regressions, including multi-file and Action Transition: PASS;
- BenchmarkExecutor integration: PASS;
- project base inspection and artifact validation: PASS.

## Validation Commands

- `python -m compileall src scripts tests`: PASS;
- focused F7 suite: `145 passed`;
- full suite: `480 passed, 2 skipped`;
- `git diff --check`: PASS.

## Limitations and Next Phase

- `scripts/benchmark/diagnostics/` remains preexisting and untracked; it is
  not part of the product or this commit;
- no provider behavior or live benchmark result is inferred from F7;
- F8, Live Smoke / Readiness, is the next phase and remains pending;
- F8 is not started, passed, or authorized by this document.

## Final Verdict

`V0_5_F7_OFFLINE_VALIDATION_PASS`
