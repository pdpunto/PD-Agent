# PD Agent v0.4 Benchmark Dataset

Frozen datasets for v0.4 live comparisons.

- Candidate freeze: `PD_AGENT_BENCHMARK_DATASET_V0.4_1` / `0.4.1`
- Hardened freeze: `PD_AGENT_BENCHMARK_DATASET_V0.4_2` / `0.4.2`
- Source of truth knowledge source: `net.fabricmc:yarn:1.21.11+build.6:v2`

Baseline fixture source:

- `tests/fixtures/l11_fabric_fixture`

Harness source:

- `tests/fixtures/l11_minecraft_harness`

Frozen tasks:

- `B001` - registry lookup
- `B002` - version-sensitive API helper
- `B003` - multi-symbol runtime check

The `benchmarks/` tree is intentionally data-only. No live benchmark run is part of this lot.
