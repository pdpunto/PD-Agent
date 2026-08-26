# PD Agent v0.6 - Fabric Capability Expansion - DESIGN

Status: DESIGN PERSISTED / READY FOR RFC
Milestone: PD Agent v0.6 - Fabric Capability Expansion
Baseline: `a58e973445f59612abdd4c3196c75b45220cd1c3`
Platform: Minecraft/Fabric `1.21.11` only

This document records the scope approved by 04 Architecture. It defines what
v0.6 must be able to demonstrate. It does not define implementation details,
an RFC, an IMP, a new benchmark, or a live validation authorization.

## 1. Purpose

v0.6 expands the Fabric capability foundation from small registry-oriented
features to stateful, event-driven and data-driven server-side behavior in an
existing Fabric project.

The milestone must preserve the evidence-first chain established by v0.5:

`requirement -> context -> inspection -> mutation -> semantic validation ->
build -> artifact -> real Minecraft -> observable state -> PASS/FAIL`

For stateful world behavior, the chain additionally includes:

`save -> clean shutdown -> reopen the same world -> reload -> observation`

## 2. Problem

v0.5 demonstrates an existing-project Fabric development loop with
server-observable content and resource behavior. That scope does not yet
demonstrate durable state, inventory semantics, command side effects, event
effects, or data-driven runtime behavior.

v0.6 addresses those capability gaps without turning the product into a
generic Minecraft automation framework.

## 3. Scope

The v0.6 scope is limited to Minecraft/Fabric `1.21.11` and these four
verticals:

### A. Data Components / Stateful Items

Items whose state is represented by a real component and can be observed after
the relevant mutation.

### B. Block Entities + Persistence + Inventory

Blocks with real block entities and inventory/state behavior. Persistence and
reopen are mandatory for closing this vertical.

### C. Commands + Events

Controlled server or console command execution and a real server-side event
callback with an observable side effect.

### D. Data-driven Content

Tags, recipes and loot tables whose loading and behavior are evaluated through
real Minecraft behavior rather than JSON validity alone.

## 4. Non-goals

The following remain outside v0.6:

- GUI or screens;
- rendering, HUD, keybindings or input;
- client-only events;
- block entity renderers;
- screenshots;
- complex networking;
- entities or mobs;
- world generation;
- multi-version support;
- a large Knowledge Base;
- Multi-Agent orchestration;
- product UI;
- Paper, NeoForge or Velocity;
- a new general GameTest system;
- arbitrary command execution;
- arbitrary user save access;
- project creation from scratch;
- general repair of broken baseline projects.

## 5. Supported Capability Definition

A v0.6 capability is supported only when a reproducible evaluation can show:

1. the user-facing requirement is understood;
2. relevant knowledge or context is identified without replacing inspection;
3. the project is inspected within existing security boundaries;
4. the target is mutated through controlled tools;
5. semantic validation checks the requested behavior;
6. a real build produces a valid artifact;
7. the artifact is loaded by real Minecraft/Fabric;
8. the requested state or side effect is observed;
9. evidence is persisted sufficiently to reproduce the decision; and
10. the result is classified as PASS or FAIL, with infrastructure outcomes
    kept separate.

Build success alone is not capability evidence.

## 6. Expected User/Task Behavior

Tasks describe what the user wants to observe, not the reference source files,
class names or exact implementation sequence. A task may require source,
resource and data changes, but acceptance remains independent of the chosen
implementation.

The target is an existing, valid and compilable Fabric project. Baseline
failure remains a precondition or infrastructure result and is not silently
converted into a v0.6 repair task.

## 7. Vertical A - Data Components / Stateful Items

A supported A task must be able to demonstrate, as applicable:

- a real registered item;
- a real `ItemStack` carrying the component;
- component presence;
- the expected initial value;
- a real mutation of the component value;
- the expected post-mutation value;
- serialization and deserialization when persistence is part of the
  requested behavior; and
- an associated server-side behavior when the requirement includes one.

The vertical does not include UI, tooltips or rendering.

## 8. Vertical B - Block Entities, Persistence and Inventory

A supported B task must be able to demonstrate:

- a real registered block;
- a real block entity type;
- creation or placement in a controlled world;
- a real block entity instance;
- the contractual state of that instance;
- inventory size and slot semantics when inventory is requested;
- a real mutation of state or inventory;
- save behavior;
- clean shutdown; and
- the same persisted state after reopening the same world.

### Persistence/Reopen Contract

Persistence/Reopen is mandatory for v0.6 closure of this vertical. It is a
multi-phase orchestration requirement, not a new observation type.

Phase 1:

`Minecraft -> create/mutate state -> save -> clean shutdown`

Phase 2:

`same world root -> restart -> reload -> observe -> expected persisted state`

The requirement concerns one controlled world root and one durable state
transition. It does not create a general world or save manager.

## 9. Vertical C - Commands and Events

### Commands

A supported command task must demonstrate, when applicable:

- command registration;
- controlled server or console execution;
- basic contractual arguments;
- success and failure behavior; and
- a real observable side effect.

### Events

The design does not promise support for every event. A supported event task
must identify:

`real event -> real callback -> real side effect -> observable state`

An existing listener in source without a triggered effect is not sufficient.

## 10. Vertical D - Data-driven Content

### Tags

The evaluation must demonstrate real loading, positive membership and negative
membership where the task requires both.

### Recipes

The evaluation must demonstrate a loaded resource, real matching or
resolution, the expected inputs and the expected output.

### Loot Tables

The evaluation must demonstrate a real loot table, a controlled context, an
explicit seed when relevant, real generation and the contractual result.

Valid JSON alone is never sufficient evidence for D.

## 11. Cross-cutting Functional Requirements

Every v0.6 candidate capability must preserve:

- existing-project preconditions;
- server-side, real-runtime observability;
- provider-neutral acceptance;
- semantic validation distinct from build validation;
- artifact identity and freshness evidence;
- meaningful negative evidence;
- no task-specific runtime hardcodes;
- bounded execution and recovery behavior; and
- reproducible PASS/FAIL classification.

The milestone must cover representative tasks rather than rely on one manual
demonstration.

## 12. Evidence Requirements

Evidence must identify, when relevant:

- requirement and acceptance contract;
- project and fixture identity;
- pinned Minecraft/Fabric environment;
- inspected sources and relevant context;
- mutations and mutation targets;
- semantic validation results;
- build attempts and feedback;
- artifact identity and validation;
- world root identity for Persistence/Reopen;
- phase 1 and phase 2 runtime evidence;
- command/event side effects;
- data-driven loading and behavior;
- Brain provenance when used;
- provider/model metadata without secrets;
- limits and recovery state; and
- final outcome and termination reason.

Evidence must distinguish functional FAIL, provider or harness BLOCKED, and
methodologically INVALID results.

## 13. Persistence Requirements

Persistence/Reopen must be auditable as one controlled multi-phase scenario.
The evidence must make it possible to relate phase 1 and phase 2 to the same
world root, task, fixture, artifact and target capability without granting
access to arbitrary user saves.

The design requires durable proof of the state before shutdown, the clean
shutdown boundary, the restart boundary, the reload observation and the final
state comparison. The exact schema and orchestration contract remain for the
RFC.

## 14. Safety

v0.6 preserves the v0.5 boundaries:

- `SecurePathResolver`;
- `ToolExecutor`;
- workspace confinement;
- explicit mutation tools;
- Gradle Wrapper authority;
- no free shell;
- execution limits and budgets;
- Action Gate;
- Post-Dispatch Recovery;
- secret redaction; and
- provider neutrality.

World roots must be explicitly authorized by the controlled execution. The
agent must not access arbitrary user saves. Commands accept only contractual,
controlled inputs and cannot become an arbitrary command bridge.

## 15. Compatibility

The target compatibility line is Minecraft/Fabric `1.21.11`, consistent with
the v0.5 harness and frozen project base. The current pinned environment is
Minecraft `1.21.11`, Yarn `1.21.11+build.6`, Fabric Loader `0.19.3`, Fabric
Loom `1.13.3`, Java `21`, with the existing Fabric API dependency.

No multi-version compatibility is claimed. Any later version expansion needs
separate design and evidence.

## 16. Minecraft Brain Dependencies

v0.6 reuses the current Brain. Each vertical may identify a concrete,
version-sensitive knowledge need, but Brain remains contextual support rather
than a substitute for factual project inspection or a memory of the
workspace.

The milestone does not build a large Knowledge Base. Broad knowledge gaps are
recorded for a later, separately authorized milestone.

## 17. Minecraft Test Harness Dependencies

The current server-side harness remains the evidence authority. v0.6 may
require small, generic observation extensions for A, B, C or D. The expected
qualitative harness delta is:

- A: validable with a small harness delta;
- B state/inventory: validable with a small harness delta;
- B Persistence/Reopen: validable with a large harness delta;
- C: validable with a small harness delta;
- D: validable with a small harness delta.

Conceptual observation candidates are:

- `ITEM_COMPONENT_STATE`;
- `BLOCK_ENTITY_STATE`;
- `INVENTORY_STATE`;
- `COMMAND_EXECUTION`;
- `TAG_MEMBERSHIP`;
- `RECIPE_MATCH`; and
- `LOOT_RESULT`.

These names are not frozen by this DESIGN. Persistence/Reopen remains
multi-phase orchestration, not an observation type. Events should prefer
observable side effects through generic primitives rather than event-specific
task hardcodes.

If a vertical requires a material harness redesign, it is a dependency and
decision for the Harness area and RFC, not an implicit v0.6 implementation.

## 18. Build & Debug Dependencies

v0.6 reuses the v0.5 Build & Debug capabilities:

- isolated Gradle environment;
- `ArtifactValidator`;
- build feedback and diagnosis;
- Semantic Repair;
- bounded multi-turn repair; and
- runtime feedback.

v0.6 does not reopen v0.5 infrastructure without a demonstrated blocker.
Baseline project failures, generic Gradle repair and unrelated environment
recovery remain outside this capability expansion.

## 19. Acceptance Criteria

### A

- real item, component and expected state;
- real mutation; and
- post-mutation observation.

### B

- real block entity;
- contractual state and inventory;
- real mutation;
- save and clean shutdown;
- restart of the same world; and
- persisted state observed after reload.

### C

- real command and observable side effect; and
- real server-side event callback with observable side effect.

### D

- tag loaded and membership observed;
- recipe resolved with expected inputs/output; and
- loot table executed with controlled context and expected result.

### Transversal

- real builds;
- valid artifacts;
- real Minecraft runtime;
- reproducible evidence;
- Semantic Repair compatibility;
- meaningful negative evidence; and
- no task-specific hardcodes.

Milestone closure also requires Persistence/Reopen evidence for the B
vertical, offline regression validation and an explicit RFC-defined evaluation
contract. This DESIGN alone does not close v0.6.

## 20. Risks

- stateful behavior may require more harness support than registry checks;
- Persistence/Reopen may expose lifecycle nondeterminism;
- inventory and command semantics may be version-sensitive;
- event side effects may be difficult to observe without solution leakage;
- data-driven behavior may appear valid structurally while failing at runtime;
- Brain may lack a concrete version-sensitive API detail; and
- Build & Debug may be incorrectly blamed for baseline failures.

Mitigation is deterministic, server-side evidence with controlled worlds,
explicit boundaries, and escalation of material harness or contract gaps.

## 21. Deferred Work for the RFC

The following questions are intentionally open:

1. What is the minimum exact set of observation primitives?
2. How are generic component, block-entity and inventory queries represented?
3. What is the technical Phase 1 -> persisted world -> Phase 2 contract?
4. How are commands and loot contexts executed safely and deterministically?
5. Which concrete server-side callbacks are reference event cases?
6. What exact task matrix, repetitions and thresholds are required?
7. Which harness changes are small extensions versus a material redesign?

No answer is frozen here. These items belong to the RFC and later IMP.

## 22. Conceptual Success Criterion

v0.6 succeeds conceptually when PD Agent can implement and validate a
representative stateful, event-driven or data-driven Fabric capability on a
real existing project, including durable state where required, while keeping
the evidence chain reproducible, secure, provider-neutral and independent of
task-specific shortcuts.

## 23. Audit Against v0.5

The repository audit found no material contradiction between this DESIGN and
the v0.5 closure, dataset freeze, current harness contracts, Brain boundary,
Build & Debug boundary or security model.

v0.5 closed the base existing-project capability. v0.6 adds new verticals and
the mandatory Persistence/Reopen requirement; it does not relabel v0.5
registry observations as v0.6 support and does not claim that any v0.6
vertical is implemented.

## 24. DESIGN Verdict

`V0_6_FABRIC_CAPABILITY_DESIGN_PASS`
