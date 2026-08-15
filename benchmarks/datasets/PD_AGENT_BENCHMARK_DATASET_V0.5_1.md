# PD Agent v0.5 Dataset Freeze

Frozen dataset: `PD_AGENT_BENCHMARK_DATASET_V0.5_1` / `0.5.1`

Project base:

- `benchmarks/projects/v0_5_fabric_base`
- upstream: `FabricMC/fabric-example-mod`
- pinned revision: `8b74965019e71006f0e540b2c570f46fb84d20cb`
- tree hash: `11e7af2c112dd4f7bad08aadd7b4739b44d30a1c35e110b515b50d5b7f89fd54`

Version line:

- Minecraft: `1.21.11`
- Fabric Loader: `0.19.3`
- Fabric Loom: `1.13.3`
- Yarn: `1.21.11+build.6`
- Java: `21`
- Gradle Wrapper: `8.14.3`

## Tasks

| Task | Difficulty | Prompt family | Observation | knowledge_need |
| --- | --- | --- | --- | --- |
| `F6-T1` | Low | Single-file item registry | `REGISTRY_ENTRY_PRESENT` on `item` `examplemod:signal_charm` | `LOW` |
| `F6-T2` | Medium | Multi-file block + resource | `REGISTRY_ENTRY_PRESENT` on `block` `examplemod:marble_lantern` | `LOW` |
| `F6-T3` | Highest | Representative server-side utility | `REGISTRY_ENTRY_PRESENT` on `block` `examplemod:server_core` | `MATERIAL` |

## Anti-bias review

### F6-T1

- Natural user-facing request: add one small item.
- No solution-revealing helper names in the prompt.
- Acceptance checks behavior, not source text.
- One valid implementation path is not forced.

### F6-T2

- Natural user-facing request: add a block, its item, and the usual resource wiring.
- Multi-file work is required by the feature itself, not by an artificial benchmark trick.
- Acceptance remains independent of implementation structure.

### F6-T3

- Natural user-facing request: add a small server-side utility feature.
- Intended to be the most representative task in the freeze.
- Still bounded to the pinned base project and a deterministic runtime observation.

## Dataset rule

- Tasks are selected before any live run.
- All tasks share the pinned project base.
- No task is removed because one implementation is hard.
- No solution helper is exposed in the frozen dataset.
