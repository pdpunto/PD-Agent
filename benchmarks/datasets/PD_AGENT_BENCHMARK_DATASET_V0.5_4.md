# PD Agent v0.5.4 Dataset Freeze

Frozen dataset: `PD_AGENT_BENCHMARK_DATASET_V0.5_4` / `0.5.4`

This revision supersedes the earlier `0.5.3` dataset for official use after
the T3 recipe-path correction. The `0.5.1`, `0.5.2`, and `0.5.3` files remain
in the repository as historical evidence of earlier freeze attempts, but they
are not the official live-validation target.

## Frozen base

- Project base: `benchmarks/projects/v0_5_fabric_base`
- Base identity: `11e7af2c112dd4f7bad08aadd7b4739b44d30a1c35e110b515b50d5b7f89fd54`
- Mod id: `examplemod`
- Main entrypoint: `com.example.examplemod.ExampleMod`
- Client entrypoint: `com.example.examplemod.client.ExampleModClient`

## Tasks

| Task | Difficulty | User-facing request | Observable gate | Knowledge level |
| --- | --- | --- | --- | --- |
| `F6-T1` | Low | Add a decorative item called Signal Charm | `REGISTRY_ENTRY_PRESENT` on `item` `examplemod:signal_charm` | `LOW` |
| `F6-T2` | Medium | Add a decorative block called Marble Lantern | `REGISTRY_ENTRY_PRESENT` on `block` `examplemod:marble_lantern` plus `REGISTRY_ENTRY_PRESENT` on `item` `examplemod:marble_lantern` and lang-resource assertions | `LOW` |
| `F6-T3` | Highest | Add a craftable utility block called Server Core | `REGISTRY_ENTRY_PRESENT` on `block` `examplemod:server_core` plus `REGISTRY_ENTRY_PRESENT` on `item` `examplemod:server_core` and lang/recipe assertions | `MATERIAL` |

## Anti-bias review

### F6-T1

- The prompt names the desired item explicitly.
- The acceptance checks only the observable registry result.
- No implementation class, method, or API sequence is exposed.
- Multiple internal solutions remain possible.
- The request is plausible outside the benchmark.

### F6-T2

- The prompt names the desired block explicitly.
- The acceptance checks the block registry result, the item registry counterpart, and the required resource wiring.
- The prompt does not name Java classes or registry helper calls.
- Multiple internal solutions remain possible.
- The request is plausible outside the benchmark.

### F6-T3

- The prompt names the utility block explicitly.
- The acceptance checks the block registry result, the item registry counterpart, and the associated resource wiring.
- The prompt does not claim to observe a hidden runtime utility behavior.
- Multiple internal solutions remain possible.
- The request is plausible outside the benchmark.

## Knowledge hints review

The hints in the task specs are semantic retrieval cues, not solution code.

- They avoid explicit class names and call sequences.
- They point Brain retrieval toward broad Fabric knowledge.
- They do not encode a full reference implementation.

## Preservation / observability notes

- `mod_id` and entrypoint preservation are checked through the existing artifact and project-inspection path.
- `preserve_unrelated_sources` is documented and enforced only by the existing source-change evidence model.
- `resource_contract` is enforced through resource-file evidence plus the paired block/item registry observations declared by the task acceptance.
- The harness observes registry presence plus resource-file evidence; it does not expose a separate generic server-side-behavior oracle for F6.

## Validation status

- Compile: PASS
- Focused acceptance/dataset/executor tests: PASS
- Full suite: PASS
- F6 candidate: ready for official approval review
