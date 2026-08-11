# PD Agent v0.4 Dataset Freeze

Frozen dataset: `PD_AGENT_BENCHMARK_DATASET_V0.4_2` / `0.4.2`

Candidate freeze that preceded this version:

- `PD_AGENT_BENCHMARK_DATASET_V0.4_1` / `0.4.1`
- commit `86f18e830a835daace176af2a8097198519fc106`

Source of truth knowledge source:

- `net.fabricmc:yarn:1.21.11+build.6:v2`

No live benchmark result is recorded here.

## Anti-bias analysis

| Aspect | B001 | B002 | B003 |
| --- | --- | --- | --- |
| Task type | Registry lookup | Version-sensitive API helper | Multi-symbol runtime check |
| Runtime observable | Yes | No | Yes |
| Same starting fixture | Yes | Yes | Yes |
| Same harness family | Yes | No | Yes |
| Expected change size | Small | Small | Small to medium |
| Bias risk | Familiar registry path | Build-only control | More than one symbol plus runtime |
| Why distinct | Baseline v0.3 transfer | Dedicated API helper path | Registry + update flag signal |

## Dataset rule

- Tasks are selected before any live result.
- Fixtures are resettable and versioned.
- No task is removed because a result is unfavorable.
- Semantic changes require a new dataset version.
