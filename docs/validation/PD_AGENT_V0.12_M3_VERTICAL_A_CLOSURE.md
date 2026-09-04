# PD Agent v0.12 / M3 - Vertical A Closure

Status: `CLOSED / PASS`

Baseline: `f2a1246ba8f5b3ed986f0edaaeca7b5e22ea7ebf`

## Scope

This closure covers only Vertical A: one Fabric Block, its associated
BlockItem, minimal assets and a recipe. Vertical B, generalized capability
graphs, client rendering and new Minecraft capabilities are out of scope.

The mandatory platforms are Fabric 1.21.11 and Fabric 26.2.

## Capability Acceptance

| Criterion | Implementation/evidence | Result |
| --- | --- | --- |
| Parameterized composition | `CapabilityRegistry`, `CapabilityPlanner`, Vertical A definitions | PASS |
| `fabric.block` | Capability contracts and Vertical A planning tests | PASS |
| `fabric.block_item` | Explicit dependency on the block | PASS |
| `fabric.block_assets` | Blockstate, block model, item model and language resources | PASS |
| `fabric.recipe` | Recipe output references the associated BlockItem | PASS |
| Dependency order | Planner dependency/order assertions | PASS |
| PRE_BUILD resources | Vertical A resource validation and R5 evidence | PASS |
| Artifact entries/currentness | ArtifactValidator and R5 artifact evidence | PASS |
| Block registry | Runtime observation | PASS |
| Item registry | Runtime observation | PASS |
| BlockItem association | Runtime observation proves item type and block identity | PASS |
| Controlled repair | R5 initial failure, actionable feedback, repair and revalidation | PASS |
| Failure reconciliation | R5 requirement reconciliation and zero active failures | PASS |
| RuntimeIdentity/currentness | R5 current artifact and runtime evidence | PASS |
| CompletionGate | R5 `COMPLETE` | PASS |

## LOT Summary

| Lots | Scope | Result |
| --- | --- | --- |
| LOT1-LOT2 | Capabilities, composition, contracts and Brain/version awareness | PASS |
| LOT3-LOT4 | PRE_BUILD/resources, artifact and build failure normalization | PASS |
| LOT5-LOT6 | Runtime observations and bounded Fabric 26.2 harness | PASS |
| LOT7-LOT8 | Productive wiring and offline/integration validation | PASS |
| LOT9 | Fabric 1.21.11 Vertical A live validation | PASS, accepted historical evidence |
| LOT10 | Fabric 26.2 environment and Vertical A live validation | PASS |
| LOT11 | Controlled failure -> repair -> revalidation | PASS |
| LOT12 | Regression and closure evidence | PASS |

## Fabric 1.21.11 Evidence

LOT9/R1 evidence was accepted before this closure and is reused rather than
rerun. It covers Vertical A on Fabric 1.21.11 with block registry, item
registry and BlockItem association PASS, current artifact evidence and no
unresolved runtime failure.

The historical evidence is not recreated or rewritten by this document.

## Fabric 26.2 Evidence

The authoritative R5 run was:

- Project: `e692a0c7-19ba-4995-b2ff-33510650085b`
- Task: `5706bb5a-4652-4a32-a99e-3448aac9e7d4`
- Execution/Run: `adc217a2-d0c9-4a7f-acd1-842878453de8`
- Environment: Minecraft `26.2`, Java `25`, Loader `0.19.3`, Fabric API
  `0.158.0+26.2`, Loom `1.17.20`, `UNOBFUSCATED`, Yarn `NONE`
- Artifact SHA-256:
  `97c8570851e3fe09247b8ad0d5f9d70ec71ae830af2f7b0cb6f11a7a3797df54`
- ArtifactValidator: `VALID`
- CompletionGate: `COMPLETE`
- Execution state: `COMPLETED`

The three runtime observations all passed against that artifact SHA:

1. `REGISTRY_ENTRY_PRESENT` for the block: PASS.
2. `REGISTRY_ENTRY_PRESENT` for the item: PASS.
3. `BLOCK_ITEM_ASSOCIATION`: PASS, item is a BlockItem associated with the
   expected block.

R4 independently reproduced the same three harness launches across three
sequences, 9/9 PASS, with exit code 0, no residual server process and no
residual `26.2-server.jar.tmp`. The historical R3 lock is therefore
non-blocking and not reproducible under the controlled R4 protocol.

## Controlled Repair Evidence

The R5 evidence chain is persisted under:

`C:\dev\pruebas\pd-agent-lot11-r3-vertical-a\runs\adc217a2-d0c9-4a7f-acd1-842878453de8`

The sequence was:

`initial mutation -> PRE_BUILD REPAIRABLE_FAIL -> FailureFact/feedback -> CORRECTING request -> one recipe repair -> PRE_BUILD PASS -> reconciliation -> build PASS -> artifact VALID -> runtime 3/3 PASS -> CompletionGate COMPLETE -> COMPLETED`

Failure code: `VERTICAL_A_RECIPE_INGREDIENT_MISMATCH`

- Expected: `minecraft:iron_ingot`
- Actual: `minecraft:copper_ingot`
- Repair: exactly one relevant mutation, copper ingredient to iron ingredient
- Provider calls: 2, both local deterministic; external API calls: 0
- Build attempts: 1, successful
- Active failures after reconciliation: 0

## Regression Evidence

Focal command, using an external pytest base directory:

`python -m pytest -q --basetemp C:\dev\pruebas\pd-agent-lot11-r5-pytest-focal tests/unit/test_prebuild_semantic_repair.py tests/unit/test_functional_validation_repair.py tests/unit/test_runtime_failure_reconciliation.py tests/unit/test_i12_r35_repair_reconciliation.py tests/unit/test_currentness.py tests/unit/test_completion_gate.py tests/unit/test_m3_vertical_a_brain.py tests/unit/test_m3_vertical_a_resources.py tests/unit/test_product_fabric_execution.py tests/unit/test_minecraft_observation_contracts.py`

Result: `147 passed, 1 skipped`.

Full regression command:

`python -m pytest -q --basetemp C:\dev\pruebas\pd-agent-lot11-r5-pytest-full`

Result: `1458 passed, 4 skipped, 0 failed`.

Additional checks:

- `python -m compileall src tests`: PASS.
- `git diff --check`: PASS.
- Frontend/Vitest/TypeScript/Vite/Playwright: not required for this backend,
  Fabric capability closure; no live frontend validation was performed.

## Final Acceptance

Vertical A is implemented and validated on both mandatory platforms. The
required source, resource, artifact, runtime, repair, reconciliation,
currentness and completion evidence is present. No unresolved Vertical A
blocker remains.

Out of scope: Vertical B, LOT12 new capabilities, client visual rendering,
external API execution, benchmark execution and any new architecture.

Final verdict: `V0_12_M3_VERTICAL_A_CLOSED_PASS`
