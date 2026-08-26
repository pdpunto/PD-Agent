# PD Agent v0.6 - Fabric Capability Expansion - RFC

Status: RFC DRAFT PERSISTED / READY FOR ARCHITECTURE REVIEW
Milestone: PD Agent v0.6 - Fabric Capability Expansion
Design authority: `docs/design/PD_AGENT_V0.6_FABRIC_CAPABILITY_EXPANSION_DESIGN.md`
Compatibility: Minecraft/Fabric `1.21.11` only

This RFC defines the technical contract for a future v0.6 implementation. It
does not implement the contracts, add an IMP, authorize a benchmark, or claim
that any v0.6 vertical is currently supported.

## 1. Decision and boundaries

The approved capability expansion is server-side and limited to four
verticals:

1. Data Components / Stateful Items.
2. Block Entities, Persistence/Reopen and Inventory.
3. Commands and server-side Events.
4. Tags, Recipes and Loot Tables.

GUI, rendering, client-only behavior, complex networking, entities, worldgen,
multi-version support, arbitrary command execution, arbitrary user saves,
general GameTest infrastructure, Multi-Agent orchestration, product UI and
non-Fabric platforms remain out of scope.

The existing-project precondition is retained. A task describes a behavioral
requirement and acceptance, not a reference implementation, class name or
source-file recipe.

## 2. Existing contract audit

The current repository provides the following compatible foundations:

- `pd_agent.minecraft.contracts` contains serializable Minecraft test specs,
  statuses, launch plans, process evidence, runtime evidence and results.
- `MinecraftObservationType` currently exposes legacy block-state and registry
  observations. The new primitives below are RFC contracts, not existing
  runtime support.
- `MinecraftTestRunner` validates the pinned environment, confines target and
  dependency paths, launches through the controlled Gradle/runtime boundary,
  and persists process/runtime evidence.
- `ProjectInspector` discovers Fabric modules, source/resource roots, build
  files, manifests, wrappers and pinned versions.
- `PreBuildWorkspaceValidator` produces `ValidationResult` and structured
  `ValidationViolation` values for pre-build requirements.
- `ArtifactValidator` validates build success, jar identity, metadata and
  freshness, including stale and ambiguous outcomes.
- `BenchmarkFunctionalValidator` separates post-artifact/runtime validation
  from infrastructure blocking and can mark repairable runtime failures.
- `BenchmarkClassifier` already separates `PASS`, agent `FAIL`, provider or
  infrastructure `BLOCKED`, and evidence `INVALID` at benchmark level.
- Secure path resolution, explicit mutation tools, Action Gate, bounded
  execution, budgets, provider neutrality, Semantic Repair and Post-Dispatch
  Recovery remain mandatory boundaries.

The RFC therefore adds no incompatible meaning to current statuses. Future
implementation must extend these contracts rather than bypass them.

## 3. Common observation envelope

### 3.1 ObservationRequest

Every supported primitive uses a provider-neutral, JSON-serializable envelope:

```json
{
  "id": "obs-001",
  "type": "ITEM_COMPONENT_STATE",
  "selector": {"kind": "controlled_item_stack", "id": "target"},
  "parameters": {"component_id": "example:charge"},
  "expectation": {"present": true, "value": 3}
}
```

Required fields are `id`, `type`, `selector`, `parameters` and `expectation`.
The id is unique within a phase and execution. Type is one of the closed
primitives in this RFC. Selectors and parameters are validated against that
primitive; they are not arbitrary paths, reflection expressions or code.

### 3.2 ObservationResult

```json
{
  "id": "obs-001",
  "type": "ITEM_COMPONENT_STATE",
  "status": "PASS",
  "expected": {"present": true, "value": 3},
  "actual": {"present": true, "value": 3},
  "error": null,
  "evidence_refs": ["runtime/phase-1/observations/obs-001.json"]
}
```

The result contains `id`, `type`, `status`, `expected`, `actual`, `error` and
`evidence_refs`. Status is a closed result of the primitive, not a benchmark
outcome. It must distinguish matched, mismatched, unavailable and malformed
observations. A malformed selector, unsupported profile or contradictory
evidence is not silently converted to a functional failure.

There is intentionally no universal comparison DSL. Each primitive defines a
small closed expectation schema. This keeps requests serializable,
provider-neutral, task-neutral, evidence-friendly and usable by Semantic
Repair without exposing a reference implementation.

## 4. Observation primitive set

The initial frozen set is:

- `ITEM_COMPONENT_STATE`
- `BLOCK_ENTITY_STATE`
- `INVENTORY_STATE`
- `TAG_MEMBERSHIP`
- `RECIPE_MATCH`
- `LOOT_RESULT`

`COMMAND_EXECUTION` is not an observation primitive. A command is an action;
its result and observable side effect are evaluated through these primitives.
Events likewise use an action/callback/effect chain and do not introduce an
`EVENT_FIRED` primitive.

## 5. Vertical A - Data Components / Stateful Items

The request selects a controlled ItemStack source: a harness-created stack,
an inventory slot, or a block-entity slot. It cannot select arbitrary memory,
reflection, UI state or client state.

The parameters identify the component id and the operation being observed.
The expectation can require presence, absence, initial value and post-mutation
value. Values must use the component's canonical, JSON-safe representation,
with an explicit codec identity/version where the component has structured
state. The harness obtains the value through the real component API, encodes
it through the component's approved serialization codec, and records the
canonical serialized value plus a type-safe summary. Java object identity and
reflection output are never evidence.

An A acceptance contract must identify:

1. the real registered item;
2. the controlled stack source;
3. the component id and codec representation;
4. the initial expected state;
5. the controlled mutation;
6. the post-mutation expected state; and
7. serialization/deserialization when persistence is requested.

## 6. Vertical B - Block Entities and Inventory

### 6.1 Block entity state

`BLOCK_ENTITY_STATE` selects a controlled world, dimension and block position.
It observes existence, registered type, related block state and only
contractual fields exposed by the harness. The Java side uses direct public or
approved Fabric/Minecraft APIs. Java reflection, arbitrary NBT scraping and
client-only state are prohibited.

The general exposure mechanism is a typed harness adapter registered for the
controlled observation profile. The adapter returns a serializable state
record and evidence reference; it does not expose arbitrary objects.

### 6.2 Inventory state

`INVENTORY_STATE` observes a declared inventory contract: presence, size and
selected slots. A slot record contains item id, count and approved component
values. The request must list the slots or a closed slot profile; there is no
universal world snapshot. Before/action/after observations are separate
records linked by the action and phase ids.

### 6.3 B acceptance

A B task must demonstrate a real block and block entity, controlled placement
or creation, contractual state, requested inventory semantics, mutation,
save, clean shutdown, restart of the same world and persisted observation.
Persistence/Reopen is mandatory for closing B.

## 7. Persistence/Reopen protocol

Persistence is orchestration, not a new observation primitive.

### 7.1 PersistenceScenario

The canonical scenario record contains:

- `scenario_id`;
- authorized `world_root` identity and execution root relationship;
- task/test identity and target artifact SHA;
- phase (`PHASE_1` or `PHASE_2`);
- phase-local process identity;
- pre-save observations and expected persisted state;
- save request and save-completion evidence;
- shutdown initiated, world-unload and process-exit evidence;
- reopen observations and evidence references; and
- relationship/lineage metadata connecting both phases.

The world root is generated under the authorized execution root and is never
an arbitrary user save.

### 7.2 Phase 1

Phase 1 is:

`launch -> create/load controlled world -> setup -> mutation -> pre-save
observation -> save request -> save completion -> clean shutdown -> process
exit`

The bridge stores the scenario, canonical world-root identity, artifact SHA,
phase-1 observations, save evidence, shutdown evidence, process identity,
world metadata and a deterministic world fingerprint. A save request is not
treated as completed until the current supported lifecycle API provides the
completion boundary. Shutdown initiated, world unloaded and process exited
are separate evidence facts.

### 7.3 Phase 2

Phase 2 starts a new Minecraft process with `REOPEN_ONLY`:

`new process -> load existing world -> locate target -> first persisted
observation -> compare -> clean shutdown`

No setup or mutation is permitted before the first persisted observation. The
same world root, scenario identity, artifact identity and phase relationship
must be proven. A new process identity is required.

### 7.4 Anti-recreation and recovery

Phase 2 is invalid if the world root is absent/recreated, metadata is missing,
scenario identity changes, the artifact identity differs without an
authorized lineage, or setup occurs before the first observation.

If Phase 2 runs but the persisted state is wrong, the result is
`REPAIRABLE_FAIL` and Semantic Repair may issue structured feedback. Repair
requires a new artifact and a NEW persistence scenario whose Phase 1 starts
from zero. A contaminated world is never reused as a clean baseline.

Cleanup is limited to the authorized execution/scenario root and occurs only
through the existing secure path boundary.

## 8. Vertical C - Commands and Events

### 8.1 Command action contract

`CommandInvocation` contains invocation id, a closed command contract, typed
arguments, source/context and permission. `CommandResult` contains registered,
parsed, executed, return code, success, output summary and error. Arguments
are validated against the task contract. There is no shell bridge, arbitrary
command string proxy or unrestricted server console.

Acceptance requires a real observable side effect when the command is meant
to change state; a successful return code alone is insufficient.

### 8.2 Event contract

Events are evaluated as:

`real event -> real callback -> real side effect -> observable state`

The first reference event is `ServerWorldEvents.LOAD`. A tick callback such as
`ServerTickEvents.END_SERVER_TICK` is considered only when needed by a closed
task and after architecture review. No general event framework and no
`EVENT_FIRED` primitive are introduced.

## 9. Vertical D - Data-driven content

### 9.1 Tags

The request identifies registry kind, tag id and member id, plus expected
positive or negative membership. The result records tag resolution, actual
membership and the real runtime evidence. JSON presence alone is insufficient.

### 9.2 Recipes

The initial profile is representative crafting through the real RecipeManager.
The contract declares recipe id/type, controlled input stacks, matching
operation, expected output item/count/components and relevant evidence. It
does not expose a universal recipe engine or accept JSON validity as proof.

### 9.3 Loot tables

The request identifies a loot table and a closed context profile. The profile
may include controlled source, tool/conditions and an explicit seed when
applicable. The result records generated stacks and expected outcome. Only a
small deterministic set of profiles is supported; arbitrary maps and
statistical distribution tests are out of scope.

## 10. Actions and mutation boundaries

The harness exposes only closed actions required by the task: controlled item
mutation, block placement/state mutation, inventory mutation, command
invocation, event-triggering lifecycle operation, recipe resolution and loot
generation. Actions produce action evidence and are followed by observations.

Action Gate remains authoritative. A provider or Brain must not directly
choose unrestricted Java calls, filesystem paths, commands or world roots.
Mutation targets remain explicit and are validated against workspace and task
contracts. The RFC does not add arbitrary tool capabilities.

## 11. Semantic validation and repair

The future functional validator maps primitive results into the existing
`ValidationResult`/`ValidationViolation` model. The following closed violation
codes are reserved for v0.6:

- `ITEM_COMPONENT_VALUE_MISMATCH`
- `BLOCK_ENTITY_MISSING`
- `BLOCK_ENTITY_STATE_MISMATCH`
- `INVENTORY_SIZE_MISMATCH`
- `INVENTORY_SLOT_MISMATCH`
- `COMMAND_EXECUTION_FAILED`
- `COMMAND_SIDE_EFFECT_MISMATCH`
- `EVENT_SIDE_EFFECT_MISSING`
- `TAG_MEMBERSHIP_MISMATCH`
- `RECIPE_MATCH_MISMATCH`
- `LOOT_RESULT_MISMATCH`
- `PERSISTED_STATE_MISMATCH`

Feedback contains requirement, expected, actual, phase when applicable and
evidence references. It must not contain a reference implementation,
secret, arbitrary class name, or hidden solution. The lifecycle remains:

`validation -> REPAIRABLE_FAIL -> structured feedback -> CORRECTING/EDITING ->
build -> artifact validation -> runtime revalidation`

Functional behavior failures remain `FAIL`; provider, harness, world-root,
save or phase-2 infrastructure failures remain `BLOCKED`; malformed,
unsupported, contaminated or contradictory evidence remains `INVALID`.

## 12. Evidence contract

The existing run evidence is extended, not replaced. Each observation and
action has a phase id, expected/actual values, artifact identity, process
identity, result and references. Large logs are stored once and referenced;
they are not duplicated into feedback or aggregate records.

Persistence evidence adds scenario id, phase, phase-1 process/world identity,
pre-save observation, save request/completion, shutdown facts, phase-2 process
identity, same-world proof, first reopened observation and the relationship
between phases. Provider/model metadata may be recorded without credentials.

Every evidence record is immutable after finalization and includes the
execution/run/task identity required by the existing benchmark storage. A
missing record is not inferred as success.

## 13. Failure and outcome semantics

The existing benchmark outcome categories remain authoritative:

- `PASS`: required runtime behavior and evidence match.
- `FAIL`: runtime is available and behavior is wrong, including a repairable
  semantic mismatch after the allowed repair lifecycle.
- `BLOCKED`: provider, process, harness, authorized world-root, save/reopen
  infrastructure, timeout or other environmental boundary prevented valid
  evaluation.
- `INVALID`: malformed request/evidence, prohibited selector, unsupported
  profile, world identity mismatch, contamination or contradictory evidence.

Build success is not PASS. A target crash with a concrete repairable target
reason follows existing Semantic Repair rules; an infrastructure crash is
BLOCKED. The classifier must preserve explicit agent terminal failures and
must not infer INVALID solely from naturally absent downstream evidence.

## 14. Ownership and interfaces

Ownership is deliberately narrow:

- `pd_agent.minecraft.contracts`: request/result/action/persistence schemas
  and serialization.
- `pd_agent.minecraft.runner`: process lifecycle, authorized roots, phase
  control, save/shutdown/reopen and evidence linkage.
- Fabric harness Java: direct Minecraft/Fabric API calls, controlled actions,
  observations and lifecycle hooks.
- `pd_agent.benchmark.functional`: expected/actual comparison,
  `ValidationResult` and repairability.
- Build & Debug: consumes feedback, edits, builds and revalidates.
- ProjectInspector/ArtifactValidator: existing inspection and artifact
  authority.
- Core/runtime/providers/scheduler: no Minecraft-specific policy.

No new provider API, scheduler semantics, general event framework or generic
world manager is implied.

## 15. Brain and provider neutrality

The current Brain may retrieve contextual knowledge for:

- component ids/codecs and ItemStack APIs;
- block entities, serialization and inventory;
- commands and lifecycle APIs; and
- tags, recipes and loot APIs.

Brain retrieval, selection and injection must remain provenance-bearing and
must not replace ProjectInspector, runtime evidence or acceptance. Broad
version-sensitive gaps are deferred to `03 / v0.7` or a separately approved
scope. Provider output cannot alter the closed schemas or security boundaries.

## 16. Security and safety

All paths pass through `SecurePathResolver` and existing workspace confinement.
Only the controlled execution root and an authorized scenario world root may
be accessed. Tool execution remains explicit and bounded. Action Gate blocks
unapproved actions. Budgets, step/tool/build/time limits, provider recovery,
secret redaction and Post-Dispatch Recovery remain active.

Commands are typed and closed. No arbitrary shell, arbitrary Java reflection,
arbitrary NBT traversal, arbitrary user save, credential persistence or raw
encrypted reasoning content is permitted.

## 17. Compatibility and dependency freeze

The only supported line is:

- Minecraft `1.21.11`;
- Fabric Loader `0.19.3`;
- Fabric Loom `1.13.3`;
- Yarn `1.21.11+build.6`;
- Java `21`;
- current pinned Fabric API fixture.

No multiversion abstraction is designed. A version change requires a new
design decision and evidence. The current v0.5 harness and fixture remain the
starting point; no dataset, acceptance, prompt, provider or benchmark freeze
is changed by this RFC.

## 18. Complexity and sequencing

Envelope and result: MEDIUM. A: MEDIUM. B state: MEDIUM. Inventory: MEDIUM.
Commands: SMALL/MEDIUM. Events: SMALL. Tags: SMALL. Recipes: MEDIUM. Loot:
MEDIUM. Persistence/Reopen: LARGE.

Conceptual dependency order is contracts and evidence, A/D primitives, B
state/inventory, C actions/effects, then persistence/reopen integration and
cross-vertical validation. This is not an implementation batch plan and does
not authorize work. Persistence is intentionally the largest risk because it
requires lifecycle boundaries and anti-recreation proof.

Scope creep requires a new architecture decision when it introduces a new
primitive, arbitrary command/world access, client behavior, a version line,
general GameTest/world management, broad knowledge infrastructure, or a
material harness redesign.

## 19. Architecture audit and readiness

The RFC was checked against the persisted DESIGN, current Minecraft contracts
and runner, functional validator, classifier, ProjectInspector,
ArtifactValidator, validation package, security/recovery boundaries and
existing evidence model. No material contradiction was found.

The current implementation does not yet provide the v0.6 primitives or
Persistence/Reopen implementation. That is an expected implementation gap,
not a reason to claim support and not a reason to modify code in this RFC
task. The RFC is ready for Architecture review, after which a separately
authorized IMP and implementation may be considered.

Design Delta: NO
Implementation readiness: `RFC_READY_FOR_REVIEW`

## 20. Open questions for Architecture review

1. Confirm the exact canonical component codec envelope for the first A task.
2. Confirm the minimal typed block-entity adapter fields for the first B task.
3. Confirm save-completion and world-unload lifecycle signals available in
   the pinned Fabric runtime.
4. Confirm the first closed command argument profiles.
5. Confirm the reference event task and whether a tick callback is necessary.
6. Confirm representative recipe and loot context profiles.
7. Confirm the future task matrix, repetitions and threshold independently of
   this technical RFC.
8. Decide which harness changes are small extensions and which require a new
   architecture review.

## 21. Implementation gate

Implementation may begin only after DESIGN/RFC approval, repository audit and
explicit authorization from Architecture. Implementation cannot be declared
validated or enable a candidate until the corresponding offline IMP matrix,
SDK/provider capability checks, persistence/recovery schema validation and
regression suite pass, followed by explicit authorization for any live or
candidate execution.

## 22. References

- `docs/design/PD_AGENT_V0.6_FABRIC_CAPABILITY_EXPANSION_DESIGN.md`
- `docs/rfc/PD_AGENT_V0.5_FABRIC_CAPABILITY_RFC.md`
- `docs/rfc/PD_AGENT_V0.5_POST_DISPATCH_RECOVERY_RFC.md`
- `src/pd_agent/minecraft/contracts.py`
- `src/pd_agent/minecraft/runner.py`
- `src/pd_agent/benchmark/functional.py`
- `src/pd_agent/benchmark/classifier.py`
- `src/pd_agent/project/inspector.py`
- `src/pd_agent/artifacts/validator.py`
- `src/pd_agent/validation/prebuild.py`

## 23. RFC Verdict

`V0_6_RFC_ARCHITECTURE_READY`
