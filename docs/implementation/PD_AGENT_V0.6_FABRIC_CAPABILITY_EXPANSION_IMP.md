# PD Agent v0.6 - Fabric Capability Expansion - IMP

Status: IMP DRAFT / READY FOR ARCHITECTURE REVIEW
Design: `docs/design/PD_AGENT_V0.6_FABRIC_CAPABILITY_EXPANSION_DESIGN.md`
RFC: `docs/rfc/PD_AGENT_V0.6_FABRIC_CAPABILITY_EXPANSION_RFC.md`
Compatibility: Minecraft/Fabric `1.21.11` only

This document defines how a future implementation may be built. It does not
implement code, authorize implementation, authorize live execution, define a
benchmark matrix, or change the v0.5 freeze.

## 1. Audit baseline

The repository audit was performed against commit
`20646278dfaea5eea0f1bb62b3d1062ddf014db8`.

Relevant existing components:

- `src/pd_agent/minecraft/contracts.py`: current Minecraft specs, legacy
  observations, statuses, launch plans and serializable evidence.
- `src/pd_agent/minecraft/runner.py`: pinned environment validation,
  controlled launch, SecurePathResolver integration and runtime evidence.
- `src/pd_agent/benchmark/functional.py`: post-artifact/runtime validation,
  repairable runtime failures and structured violations.
- `src/pd_agent/benchmark/classifier.py`: benchmark PASS/FAIL/BLOCKED/INVALID
  classification and agent terminal failure semantics.
- `src/pd_agent/validation/prebuild.py`: pre-build contract validation.
- `src/pd_agent/build/runner.py`: bounded Gradle build invocation and logs.
- `src/pd_agent/artifacts/validator.py`: artifact identity and freshness.
- `src/pd_agent/project/inspector.py` and `project/fabric.py`: existing-project
  inspection, module/source/resource roots and pinned Fabric metadata.
- `src/pd_agent/tools/security.py`, `tools/executor.py` and `runtime/engine.py`:
  path boundaries, explicit tools, Action Gate and bounded runtime loop.
- `src/pd_agent/benchmark/collector.py`: run and runtime evidence collection.
- `tests/unit`, `tests/integration` and
  `tests/fixtures/l11_minecraft_harness`: current regression/harness surfaces.

The current Minecraft contracts expose only the v0.5 observations. The plan
below therefore adds new contracts in later lots; it does not claim that they
already exist.

## 2. Frozen architecture

The six observation primitives are fixed:

1. `ITEM_COMPONENT_STATE`
2. `BLOCK_ENTITY_STATE`
3. `INVENTORY_STATE`
4. `TAG_MEMBERSHIP`
5. `RECIPE_MATCH`
6. `LOOT_RESULT`

Commands are actions with typed results and observable side effects. Events
are `real event -> callback -> side effect -> generic observation`. The only
reference event is `ServerWorldEvents.LOAD`. Persistence is a two-phase
orchestration contract, not an observation primitive.

Component values use `Codec.encodeStart(JsonOps.INSTANCE, value)` and
`Codec.parse(JsonOps.INSTANCE, json)`, compared semantically as structured
JSON under evidence profile `DFU_JSON_CODEC_V1`. Codec/DataResult failures
are explicit evidence; reflection is never a fallback.

Persistence uses `PersistenceScenario`, `BEFORE_SAVE`, `AFTER_SAVE` as the
minimum `SAVE_COMPLETED` evidence, controlled shutdown, `WORLD_UNLOAD`, clean
exit, then a new process with `REOPEN_ONLY` and first observation before any
setup or mutation.

## 3. Delivery rules

Each lot is independently auditable and independently committed. The normal
gate is:

`offline tests PASS -> diff review -> commit -> push -> STOP -> architecture
review -> next explicit authorization`

No lot may silently include another lot's contract or consumer. A material
repository change requires a fresh audit before the next lot. Rollback is by
reverting the lot commit, never by rewriting history or mixing diagnostics.

Python owns schemas, orchestration, evidence and classification. The Java
harness owns direct Fabric/Minecraft APIs, controlled actions, observations
and lifecycle callbacks. No general plugin system, event framework, world
manager or task-specific source generator is introduced.

## 4. Batch summary

| Batch | Objective | Dependency | Complexity |
| --- | --- | --- | --- |
| I0 | Contract/repo freeze and fixture audit | none | SMALL |
| I1 | Common observation envelope and evidence base | I0 | MEDIUM |
| I2 | Data Components / Stateful Items | I1 | MEDIUM |
| I3 | Block Entity and Inventory adapters | I1 | MEDIUM |
| I4 | Tags | I1 | SMALL |
| I5 | Representative crafting recipe | I1 | MEDIUM |
| I6 | Minimal deterministic loot profile | I1 | MEDIUM |
| I7 | Typed command action/result | I1 | SMALL/MEDIUM |
| I8 | LOAD event callback/effect | I1, I7 action/effect evidence | SMALL |
| I9 | PersistenceScenario foundation | I1, I3 | LARGE |
| I10 | Persistence/Reopen lifecycle and repair | I9, I3, I11 contracts | LARGE |
| I11 | Cross-vertical functional validation/Semantic Repair | I2-I8, I9 schemas | MEDIUM/LARGE |
| I12 | Offline regression and readiness audit | I2-I11 | LARGE |

The order keeps persistence separate from the primitive implementation lots.
I11 defines the consumer behavior after primitive result shapes are stable;
I10 may integrate its persistence violation only after I11's validation
contract is available. This avoids a circular implementation dependency.

## 5. I0 - Contract and repository freeze

### Objective and scope

Record the exact RFC/Design baseline, current fixture identity, Fabric
versions, Java version, existing harness layout and allowed execution roots.
Confirm the current v0.5 suite is the regression baseline.

### Predicted files and contracts

Documentation, inspection snapshots and tests only. No product or Java harness
behavior is changed in I0.

### Tests and evidence

Structural contract checks, existing-project inspection checks, fixture and
version assertions, and a diff review. Evidence records the baseline commit,
dataset/config freeze and untouched diagnostics.

### Acceptance, commit and rollback

Acceptance is a reproducible freeze record with no scope drift. Recommended
commit: `docs: freeze v0.6 implementation baseline`. Rollback is reverting
that documentation commit. STOP if baseline, fixture or pinned versions are
ambiguous.

## 6. I1 - Observation envelope and evidence base

### Objective

Add provider-neutral serializable request/result envelopes and extend existing
Minecraft evidence linkage without breaking v0.5 `MinecraftTestSpec` or its
legacy observations.

### Predicted surfaces

- `src/pd_agent/minecraft/contracts.py` and its exports.
- `src/pd_agent/minecraft/runner.py` only for passing validated envelopes.
- `src/pd_agent/benchmark/collector.py` for references and phase ids.
- focused unit tests and harness fixture support.

### Contract

`ObservationRequest` contains id, closed type, selector, parameters and
expectation. `ObservationResult` contains id, type, status, expected, actual,
error and evidence references. Each primitive validates its own closed
selector/expectation schema. No universal comparison DSL is added.

### Tests and evidence

Round-trip serialization, unknown primitive rejection, malformed selector,
provider-neutral JSON, evidence reference linkage and v0.5 compatibility.
Evidence must show that large logs are referenced once rather than duplicated.

### Acceptance and stop

All six names are closed and serializable; `COMMAND_EXECUTION` and
`EVENT_FIRED` are rejected as observation types. Recommended commit:
`feat: add v0.6 observation evidence contracts`. STOP on any legacy schema
break, arbitrary selector escape or incompatible evidence mutation.

## 7. I2 - Data Components / Stateful Items

### Objective

Implement `ITEM_COMPONENT_STATE` for controlled ItemStacks and codec-based
semantic state.

### Python side

Validate the closed request, component id, source kind, expected structured
JSON and before/after relation. Persist codec profile, component id and
DataResult errors as evidence. Do not add reflection, UI or client logic.

### Java harness side

Use the real ItemStack/component API and a harness-created controlled stack.
Expose component presence/value through the approved Codec path. A reusable
profile may also select a declared inventory or block-entity slot, but may
not traverse arbitrary objects.

### Tests

Unit: presence, absence, correct/wrong value, malformed selector, codec error,
semantic JSON comparison and round-trip. Integration/harness: mutation and
before/after observation. Negative tests verify no UI/client dependency,
reflection fallback or text-JSON comparison.

### Acceptance and evidence

Real item, component, mutation and post-mutation state are observed. Evidence
contains controlled source, component id, profile, expected/actual JSON,
codec error if present, artifact and process references. Recommended commit:
`feat: validate Fabric item component state`. STOP if the component cannot be
observed through a real approved codec.

## 8. I3 - Block Entity and Inventory

### Objective

Add the smallest typed block-entity adapter and selected inventory contract.

### Adapter contract

The first adapter exposes only:

- `block_entity_type`;
- related block id/state;
- a small named state map fixed by the acceptance profile; and
- inventory presence/size/selected slots when requested.

The adapter is registered and selected by a closed profile id and validated
against the task contract. It is not a reflection/property language.

### Python and Java split

Python validates `BLOCK_ENTITY_STATE` and `INVENTORY_STATE` envelopes and
evidence. Java calls direct Fabric/Minecraft APIs and emits typed records.
Selected slots contain item id, count and approved component values. No
universal snapshot or arbitrary NBT map is permitted.

### Tests and acceptance

Unit: presence, missing entity, wrong type/state, size mismatch, slot mismatch,
unsupported profile and malformed selector. Harness integration: controlled
placement/creation, real state and inventory before/action/after. Acceptance
requires real block entity and requested inventory behavior. Recommended
commit: `feat: add typed Fabric block entity observations`. STOP if adapter
selection becomes task-specific code or reflection.

## 9. I4 - Tags

### Objective and contract

Implement `TAG_MEMBERSHIP` for a resolved registry kind, tag id and member id,
with expected positive or negative membership.

### Tests and evidence

Real runtime tests cover tag resolved, member resolved, positive membership,
negative membership, mismatch, missing tag/member, malformed selector and
unsupported registry kind. Evidence records actual membership and resolution,
not just JSON file presence.

Recommended commit: `feat: validate Fabric tag membership`. STOP on a test
that passes from resource parsing without runtime resolution.

## 10. I5 - Representative crafting recipe

### Objective and profile

Use one deterministic crafting profile through the real RecipeManager. Inputs
are controlled ItemStacks; the request declares recipe id/type, inputs,
expected output item/count/components and matching operation.

### Tests and evidence

Matching recipe, no match, wrong output, missing recipe and relevant component
mismatch. Evidence includes recipe resolution, controlled inputs and actual
output. No universal recipe abstraction is added.

Recommended commit: `feat: validate Fabric crafting recipes`. STOP if JSON
validity is used as functional proof or if arbitrary recipe engine behavior is
introduced.

## 11. I6 - Minimal deterministic loot profile

### Objective and profile

Select the simplest closed loot context compatible with 1.21.11, using an
explicit seed where applicable. The profile has typed fields and no arbitrary
`LootContext` map.

### Tests and evidence

Table resolved, deterministic generated result, mismatch, missing table and
unsupported context profile. Evidence records table id, profile, seed when
applicable, generated stacks and expected/actual result.

Recommended commit: `feat: validate deterministic Fabric loot`. STOP if
non-deterministic context or arbitrary map input is required.

## 12. I7 - Typed command action/result

### Objective and contract

Implement `CommandInvocation` and `CommandResult` for one closed command
argument profile. Fields cover invocation id, contract, typed args,
source/context, permission, registered, parsed, executed, return code,
success, output summary and error.

### Safety and tests

Use only controlled server/console APIs and typed arguments. Tests cover
registered, parsed, executed, success/failure, invalid typed args and the
required observable side effect. Security tests reject shell injection,
arbitrary command text, `/op`, `/stop` and unrestricted proxy behavior.

Recommended commit: `feat: add typed Fabric command actions`. STOP if command
execution can reach a shell or arbitrary server command.

## 13. I8 - LOAD event callback/effect

### Objective and fixture

Use only `ServerWorldEvents.LOAD` in a controlled fixture. The callback must
produce a deterministic server-side side effect observed by a generic
primitive. No tick event, `EVENT_FIRED` primitive or event framework.

### Tests and evidence

Verify real registration, callback execution in a controlled load, effect
observation, missing effect and duplicate/incorrect effect. Evidence links
event registration, lifecycle/process identity, side effect and generic
observation; it does not claim an event merely because source contains a
listener.

Recommended commit: `feat: validate Fabric world load effects`. STOP if the
fixture needs client behavior or a general event bus.

## 14. I9 - PersistenceScenario foundation

### Objective

Add the serializable scenario/phase/evidence relation before lifecycle
execution. This lot must remain schema-first.

### Contract and predicted surfaces

Extend `src/pd_agent/minecraft/contracts.py` and evidence storage with
scenario id, phase, authorized world root identity, artifact SHA, task/test
identity, process identity, phase relation and bounded same-world fingerprint
metadata. Extend runner plan inputs only to validate authorized roots; do not
launch a second process in I9.

### Tests and acceptance

Serialization round-trip, phase relation, artifact identity, missing metadata,
world-root escape, symlink/junction escape, arbitrary save path and fingerprint
scope tests. Acceptance is a complete immutable schema that cannot represent
an unbounded user save or a phase-2 mutation-before-observation.

Recommended commit: `feat: add persistence scenario contracts`. STOP if the
schema starts implementing world lifecycle or cleanup.

## 15. I10 - Persistence/Reopen integration

### Phase 1 implementation

Extend the Java harness lifecycle adapter and Python runner to record setup,
mutation, pre-save observation, save request, `BEFORE_SAVE`, `AFTER_SAVE`/
`SAVE_COMPLETED`, controlled shutdown, `SERVER_STOPPING` when applicable,
`WORLD_UNLOAD` and clean process exit. These are distinct evidence facts;
`AFTER_SAVE` is the minimum save completion criterion.

### Phase 2 implementation

Start a new Minecraft process with the same authorized world root and artifact
identity in `REOPEN_ONLY`. Load the existing world, perform the first
persisted observation before any setup/mutation, compare it, then shut down.

### Tests and recovery

Correct persistence, wrong persisted state, missing save completion, phase-2
infra failure, world identity mismatch, recreated-world rejection,
contamination, crash/timeout and cleanup confinement. If state is wrong, emit
`REPAIRABLE_FAIL`; after repair require a new artifact, new scenario and
Phase 1 from zero. Never reuse a contaminated world.

Recommended commit: `feat: integrate Fabric persistence reopen validation`.
Rollback is the full I10 commit only; no evidence mutation or historical
execution rewrite. STOP on uncertain save completion, world substitution or
cleanup escape.

## 16. I11 - Functional validation and Semantic Repair

### Objective

Map primitive/runtime results to the existing validation and classifier
contracts after I2-I10 have stable result shapes.

### Violation mapping

Implement the closed codes:

`ITEM_COMPONENT_VALUE_MISMATCH`, `BLOCK_ENTITY_MISSING`,
`BLOCK_ENTITY_STATE_MISMATCH`, `INVENTORY_SIZE_MISMATCH`,
`INVENTORY_SLOT_MISMATCH`, `COMMAND_EXECUTION_FAILED`,
`COMMAND_SIDE_EFFECT_MISMATCH`, `EVENT_SIDE_EFFECT_MISSING`,
`TAG_MEMBERSHIP_MISMATCH`, `RECIPE_MATCH_MISMATCH`, `LOOT_RESULT_MISMATCH`,
`PERSISTED_STATE_MISMATCH`.

Each feedback record contains requirement, expected, actual, phase when
applicable and evidence references. It contains no reference implementation,
secret, arbitrary class/API leakage or hidden solution.

### Tests and acceptance

Positive validation, each mismatch, missing/unsupported profile, malformed or
contradictory evidence, infrastructure blocking, target crash repairability,
repair -> rebuild -> runtime revalidation, no-op repair guard and existing
agent terminal failure regressions. Infrastructure remains `BLOCKED`, semantic
behavior remains `FAIL`/`REPAIRABLE_FAIL`, and invalid evidence remains
`INVALID`.

Recommended commit: `feat: extend v0.6 semantic validation repair`. STOP if
the classifier needs to reinterpret v0.5 statuses or if feedback leaks a
reference implementation.

## 17. I12 - Final offline validation

### Scope

Run the existing v0.5 suite, new unit tests, deterministic harness tests,
integration tests, persistence multi-process tests, negative evidence tests,
security regressions and Semantic Repair regressions. Also run `compileall`
and `git diff --check`.

No provider/API, live benchmark or Minecraft live launch is required for this
documentation-defined gate; any local runtime evidence must be explicitly
authorized and isolated.

### Readiness evidence

Before Benchmarks, preserve the implementation commit lineage, fixture/config
identity, test results, harness/runtime evidence, artifact SHA/freshness,
PersistenceScenario phase linkage, security checks and final classification.
Only then may Architecture review whether the implementation is
`IMPLEMENTED + OFFLINE/RUNTIME VALIDATED`. This IMP does not grant that
status.

Recommended commit: `test: validate v0.6 Fabric capability expansion`.
STOP on any regression, unbounded security path, stale artifact, missing
negative evidence or incomplete persistence proof.

## 18. Security matrix

Every relevant lot must retain or add tests for:

- world-root escape;
- symlink/junction escape;
- arbitrary save path;
- command injection and arbitrary command proxy;
- unsupported action;
- invalid selectors;
- cleanup escape;
- phase-2 world substitution;
- phase-2 setup/mutation before first observation;
- reflection/arbitrary NBT attempts where an equivalent input exists.

Do not alter the general security policy unless a demonstrated blocker is
audited and separately approved.

## 19. Compatibility freeze

All lots target exactly:

- Minecraft `1.21.11`;
- Fabric Loader `0.19.3`;
- Fabric Loom `1.13.3`;
- Yarn `1.21.11+build.6`;
- Java `21`;
- current pinned Fabric API fixture.

No compatibility matrix or multi-version abstraction is part of this IMP.

## 20. Critical path and dependencies

`I0 -> I1 -> {I2, I3, I4, I5, I6, I7} -> I8 -> I9 -> I10 -> I11 -> I12`

I2-I7 may be developed as separate reviewed lots after I1. I8 depends on
generic effect evidence and the typed action boundary. I9 depends on I1 and
I3 schemas but does not depend on the completed behavior of every vertical.
I10 depends on I9 and the validator contract from I11; I11 can define
validation mappings before I10 lifecycle integration is complete, but must
not consume unstable persistence result shapes. I12 is last.

No lot may be implemented automatically after another lot is pushed.

## 21. Scope creep and stop conditions

Architecture review is required for a new observation primitive, universal
comparison DSL, arbitrary command/world access, client behavior, reflection,
arbitrary NBT, general event framework, world manager, multi-version support,
large Knowledge Base, Multi-Agent behavior, material harness redesign or
benchmark matrix design.

Stop immediately for a baseline project failure, ambiguous target module,
missing pinned dependency, unsupported Fabric API signal, evidence identity
drift, stale/ambiguous artifact, unbounded path, unrecoverable world identity,
or a need to alter v0.5 semantics.

## 22. Design/RFC compatibility audit

The plan preserves the closed DESIGN/RFC decisions:

- six observation primitives and no command/event observation primitive;
- Codec/DFU JSON representation and round-trip;
- `ServerWorldEvents.LOAD` only;
- `PersistenceScenario` and two-phase reopen proof;
- semantic repair and failure separation;
- current ownership, security and compatibility boundaries.

The plan does not define benchmark repetitions, thresholds, provider choices,
dataset changes or live authorization. No circular dependency requires a
later lot before its contract can be reviewed; I10/I11 are explicitly split
so persistence schemas and validator mappings stabilize before integration.

Design/RFC compatibility: PASS
Design delta: NO
Scope expansion: NO

## 23. Remaining non-blocking questions

These are implementation-planning decisions, not architecture reopeners:

1. Concrete typed fields for the first block-entity adapter.
2. First closed command argument profiles.
3. Representative crafting fixture/profile.
4. Minimal loot context profile.
5. Exact harness file/module placement after the first implementation audit.
6. Benchmark matrix, repetitions and thresholds in the later Benchmarks area.

## 24. Implementation gate

This IMP is not authorization. Each lot requires explicit Architecture
approval, fresh repository audit when material changes occur, focused tests,
diff review, commit/push and STOP. No implementation or live candidate may
begin merely because this document is persisted.

Implementation readiness: `IMP_READY_FOR_ARCHITECTURE_REVIEW`

## 25. IMP Verdict

`V0_6_IMP_PERSISTED_READY_FOR_ARCHITECTURE_REVIEW`
