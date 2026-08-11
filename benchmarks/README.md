# PD Agent v0.4 Benchmark Dataset

Frozen dataset for v0.4 live comparisons.

- Dataset: `PD_AGENT_BENCHMARK_DATASET_V0.4_1`
- Dataset version: `0.4.1`
- Source of truth knowledge source: `net.fabricmc:yarn:1.21.11+build.6:v2`

Baseline fixture source:

- `tests/fixtures/l11_fabric_fixture`

Harness source:

- `tests/fixtures/l11_minecraft_harness`

Frozen tasks:

- `B001` - registry lookup
- `B002` - version-sensitive API change
- `B003` - multi-symbol version-sensitive change

The `benchmarks/` tree is intentionally data-only. No live benchmark run is part of this lot.
