# PD Agent — Roadmap to Alpha

Status: `IN PROGRESS`

Canonical owner: `00 — Dirección / Master Plan`

Starting baseline: `PD Agent v0.9 — CLOSED / PASS`

Closure commit: `2a5d4c8bb6bf966a939d51db1111d38aa1425751`

This document is the canonical persistent record for the roadmap from v0.9 to the first public Alpha. It is updated only when 00 Dirección closes or explicitly changes a roadmap decision.

## 1. State after v0.9

`PD Agent v0.9 — CLOSED / PASS`

v0.9 proves the functional Web/UI integration over the productive runtime, including Product projects, execution lifecycle, Brain, source mutation, build/debug, Semantic Repair, Minecraft runtime validation for supported contracts, CompletionGate, Delivery/JAR, evidence, persistence, recovery and the functional UI flow.

v0.9 does **not** claim that PD Agent is already a general arbitrary Fabric mod generator.

Accepted post-v0.9 evidence:

- `V0_9_R67_RUBY_TOOLS_CAPABILITY_GAP`
- `PD_AGENT_R68_POST_V0_9_CAPABILITY_INVENTORY_READY`
- `PD_AGENT_R70_MULTI_VERSION_FOUNDATION_PARTIAL`

R67 established that the proposed Ruby Tools task is outside the current productive capability envelope. R68 confirmed that the main generalization boundary is the productive request/capability/contract resolution layer, while much of the underlying runtime infrastructure is already reusable. R70 confirmed that the codebase is already partially version-aware and that multi-version support must extend existing environment/compatibility infrastructure rather than replace it.

## 2. Accepted definition of PD Agent Alpha

Status: `ACCEPTED`

PD Agent Alpha means:

> A user without programming knowledge can enter PD Agent, describe a basic or intermediate Fabric mod, and receive a functional JAR without manually editing code.

Alpha must support:

- creating a new mod from a clean validated template with its own identity;
- importing/modifying a compatible existing Fabric project;
- multiple consecutive tasks on the same project;
- creating a meaningful variety of basic/intermediate Fabric mods;
- combining multiple capabilities in a single request;
- researching, editing, building, testing, diagnosing, repairing, revalidating and delivering autonomously;
- using Brain/Knowledge when needed;
- validating requirements through real evidence rather than model self-assertion;
- delivering the JAR and understandable evidence;
- supporting multiple Fabric/Minecraft versions inside an Alpha support range;
- passing diverse benchmarks without task-specific hardcodes.

Alpha does **not** mean:

> PD Agent can create every Minecraft mod imaginable.

Alpha means:

> PD Agent is genuinely useful for creating a meaningful variety of basic/intermediate Fabric mods without programming.

Ruby Tools should eventually become a normal task inside the Alpha envelope, but it will be only one acceptance case among many.

## 3. Audited post-v0.9 capability state

Status: `AUDITED — R68 + R70`

### Productive infrastructure already present

- Product project creation and continuity over existing workspaces;
- Minecraft Brain retrieval, selection, injection and provenance;
- version-aware `KnowledgeEnvironment` and environment resolution;
- Fabric project/version inspection;
- Brain compatibility/version filtering;
- textual workspace mutation tools;
- Build/Debug pipeline;
- Semantic Repair;
- artifact validation/currentness;
- CompletionGate for supported contracts;
- Delivery/JAR;
- Product/UI execution flow;
- local security controls;
- economic authority;
- persistence/recovery.

### Main audited limitations

1. Productive resolver specialized in the Server Core vertical.
2. No general Fabric capability model.
3. No dynamic planner producing composed requirements.
4. Minecraft validators/probes remain mostly controlled rather than arbitrary/general.
5. Agent mutation tools are text-oriented and lack general binary operations.
6. No productive visual asset generation/transformation/validation pipeline.
7. Productive support currently materializes only the 1.21.11 environment end-to-end.
8. No general workspace/mod bootstrap catalog by supported target version.
9. Brain knowledge does not automatically become an executable contract.
10. Benchmark infrastructure measures capabilities but does not itself make them productive.

R68 confirms R67:

- arbitrary items are not productively exposed;
- swords are not supported productively;
- arbitrary new mod identity generation is not supported;
- binary PNG read/write is not supported;
- deterministic texture recoloring is not supported.

R70 additionally confirms:

- `KnowledgeEnvironment`, `KnowledgeEnvironmentResolver`, `FabricInspector`, Brain compatibility/retrieval/provenance and the Build/Artifact base are reusable;
- Build/Artifact/Storage are largely version-neutral;
- the Harness already transports version context but currently validates only the supported 1.21.11 environment by default;
- no parallel environment/profile architecture should be introduced;
- no existing core version-aware component requires replacement.

The correct interpretation is not that the runtime lacks all reusable primitives. The limiting boundary is predominantly the productive request → planning/capability → requirements/validation path plus the lack of a productive multi-version support matrix.

## 4. Fabric Alpha Capability Catalog

Status: `ACCEPTED`

### MUST — Alpha

#### Project

- Create a new mod from a validated clean template.
- Own name, `mod_id`, package and metadata.
- Import/modify a compatible Fabric project.
- Multiple consecutive tasks on the same mod.

#### Basic content

- Items.
- Blocks.
- Block items.
- Recipes.
- Tags.
- Loot tables / drops.
- Food.
- Basic properties/components.

#### Equipment

- Swords.
- Pickaxes.
- Axes.
- Shovels.
- Hoes.
- Armor.
- Custom materials/tiers.
- Durability, damage, speed and basic configurable properties.

#### Interactions

- Item use/click.
- Block interaction.
- Basic events.
- Effects.
- Simple custom behavior.
- Basic commands.

#### Mobs / entities

- Basic custom entities.
- Basic mobs.
- Health/damage/speed and other basic attributes.
- Drops.
- Spawning.
- Basic AI/behavior, preferably reusing vanilla behavior when appropriate.

#### Basic world generation

- Ores.
- Basic feature generation/configuration.
- Natural spawning/generation where applicable.

#### Composition

Alpha MUST support multi-capability requests.

Canonical conceptual example:

> Create Ruby, its ore and world generation, a sword, pickaxe, armor and all recipes.

The request must become multiple related and independently verifiable requirements.

### SHOULD — Alpha

- Custom status effects.
- Basic enchantments.
- Particles.
- Sounds.
- Simple structures.
- Simple block entities.
- Inventories/containers.
- Basic GUIs/screens.
- Mod configuration.
- Simple persistent data.

These should be included when the architecture makes them reasonably inexpensive, but an isolated SHOULD capability must not indefinitely block Alpha.

### POST-ALPHA

- Complete custom dimensions.
- Complex biomes.
- Advanced world generation.
- Complex networking.
- Complex custom multiplayer protocols.
- Large GUI systems.
- Advanced animations.
- Extremely custom entity AI.
- Deep arbitrary third-party mod integrations.
- Automatic NeoForge/Paper/etc. ports.
- Extremely large mods in a single request.

## 5. Capability design principle

Status: `ACCEPTED`

Do **not** replace the Server Core vertical with a collection of new hardcoded verticals such as:

- `RubyCapability`
- `SwordCapability`
- `ZombieCapability`
- `OreCapability`

Future Fabric capabilities must be:

- `GENERAL`
- `PARAMETERIZED`
- `COMPOSABLE`
- `VALIDATABLE`

Conceptual examples only — these are not final interfaces:

- `ITEM(name, properties...)`
- `TOOL(type=SWORD, material=RUBY, ...)`
- `RECIPE(output=RUBY_SWORD, ingredients=...)`
- `ORE(block=RUBY_ORE, distribution=...)`

The system should transform natural-language intent into related requirements that can be executed and independently verified.

Ruby Tools must become an instance of the system, not special code for Ruby.

Not every imaginable custom behavior should require a predefined capability type. The future architecture must also support custom behavior backed by code + requirements + evidence, otherwise PD Agent would become another closed capability catalog.

## 6. Canonical Roadmap to Alpha checklist

1. [x] Definir qué significa exactamente `PD Agent Alpha`
2. [x] Auditar capacidades reales actuales tras v0.9
3. [x] Definir catálogo mínimo de capacidades Fabric para Alpha
4. [x] Definir estrategia de assets: texturas, modelos, sonidos y generación visual
5. [x] Definir estrategia multi-versión Minecraft/Fabric
6. [x] Definir evolución necesaria del Minecraft Brain
7. [x] Definir evolución de validación, Test Harness y CompletionGate
8. [x] Evaluar dónde Multi-Agent aporta valor real
9. [x] Definir requisitos de seguridad, compatibilidad y rendimiento para Alpha
10. [x] Definir requisitos Product/UI restantes para Alpha
11. [x] Definir benchmarks y Alpha Acceptance Suite
12. [x] Inventariar gaps v0.9 → Alpha
13. [x] Agrupar gaps en milestones mínimos
14. [x] Asignar versiones v0.10 → Alpha
15. [x] Definir dependencias y orden de ejecución
16. [x] Publicar Roadmap to Alpha canónico

## 6. Minecraft Brain evolution

Status: `ACCEPTED`

R71 verdict:

`PD_AGENT_R71_ALPHA_BRAIN_FOUNDATION_PARTIAL`

The existing Minecraft Brain is a valid Alpha foundation and must be evolved
through reuse and extension, not replaced by a second Brain or parallel
environment model.

### Reuse-first decision

Preserve and reuse:

- `KnowledgeEnvironment` and `KnowledgeEnvironmentResolver`;
- canonical Knowledge records and frozen Knowledge Packs;
- provenance, integrity and version-sensitive compatibility gates;
- SQLite/index, retrieval, selection and `ContextSource`/provider boundary;
- `KnowledgeTrace` and Semantic Repair foundation.

No central Brain component has evidence requiring replacement.

### Knowledge strategy

Alpha knowledge SHALL use:

`STRUCTURED / VERSIONED SOURCES + SMALL HIGH-VALUE CURATED KNOWLEDGE`

Structured/versioned sources should provide symbols/API, Vanilla registries
and data, materials, recipes, entities, worldgen, assets and relationships,
compatibility, mappings and version changes. Curated knowledge should remain
focused on patterns, workflows, high-value conceptual relationships and
failure/diagnostic knowledge that structured sources do not express well.

PD Agent must not grow a manually maintained dictionary of all Minecraft
content.

### Vanilla and Fabric coverage

The Brain evolution must extend knowledge coverage for the Alpha MUST
capabilities: items, blocks, recipes, tags/loot, food/components, tools and
materials, armor, interactions/events, effects, commands, entities/mobs,
attributes, spawning, Vanilla behavior reuse, worldgen, resources, models,
blockstates and version-sensitive Fabric knowledge.

Alpha also requires a versioned Vanilla semantic catalog/index covering
registries, content relationships, materials, behaviors, worldgen and asset
metadata. Yarn/mappings alone do not provide that semantic layer.

### Multi-version knowledge

Use the existing `KnowledgeEnvironment`, compatibility filtering,
version-sensitive records, frozen packs and provenance. Alpha targets are
Minecraft `1.21.11`, `26.1` and `26.2`; legacy and modern mappings require
different compatible sources/adapters, not duplicated Brain runtimes.

A version is not supported merely because it can be represented or detected.
It requires populated compatible knowledge and later end-to-end validation.
Cross-version leakage must remain fail-closed.

### Ownership boundaries

- Brain: facts, knowledge, compatibility, provenance, retrieval and injection.
- Capability Planner: intent to capabilities, requirements and expectations.
- Fabric Agent Runtime: code/resource mutations.
- Asset Pipeline: asset reuse, derivation, generation and transformation.
- Build/Debug: build evidence and repair.
- Test Harness: Minecraft runtime evidence.
- CompletionGate: requirement satisfaction and completion.

No Asset Agent is created by this decision.

### Implementation timing

No independent Brain DESIGN/RFC/IMP is created yet. Roadmap completion must
first establish the grouping and dependencies between Brain evolution,
Capability Planner, Multi-Version, Asset Pipeline and Validation/Harness.

## 7. Validation, Test Harness and CompletionGate evolution

Status: `ACCEPTED`

R73 evidence:

- `PD_AGENT_R73_ALPHA_VALIDATION_FOUNDATION_PARTIAL`
- `PD_AGENT_R73_V_EVIDENCE_CONFIRMED_WITH_CORRECTIONS`

Offline validation evidence at baseline `1cc9d4add3644072820945b9b110639886d9b536`:

`295 passed, 1 warning, 0 failed`

No central validation component should be replaced. Alpha must reuse and
extend `FabricTaskContract`, `TaskProgressLedger`, validation results and
violations, evidence/currentness identities, failure facts, Semantic Repair,
ArtifactValidator, the Minecraft Test Harness and `CompletionGate`.

`CompletionGate` remains the single global completion authority. It must stay
data-driven, requirement-aware, failure-aware, currentness-aware,
artifact-aware and runtime-aware. No parallel completion authority is added.

### Composed validation

The contract and gate already support multiple requirements. The confirmed
productive gap is `PRODUCTIVE_RUNTIME_SINGLE_VALIDATION_SELECTION`: the
current Minecraft runtime selects only the first compatible runtime validation
requirement. Alpha must extend this to N independently executed, evidenced and
reconciled validation requirements.

The canonical validation shape is:

`Capability -> Requirement -> ValidationExpectation(s) -> parameterized validator/probe -> normalized Evidence -> Ledger -> CompletionGate`

Validators and probes must remain parameterized and data-driven rather than
being created for individual mods. The Capability Planner owns what must be
demonstrated; validators and the Harness produce the evidence.

### Artifact and Harness evolution

`ArtifactValidator` keeps its current JAR, ZIP, manifest, metadata, identity,
version, candidate and stale/currentness responsibilities and must gain
structural expectations for required entries, resources, classes, assets,
recipes, tags, loot, models, blockstates and references without hardcoding
specific mod content.

The existing Harness is extended rather than duplicated. Its observation
foundation is:

- `LEGACY_BLOCK_STATE`;
- `REGISTRY_ENTRY_PRESENT`;
- `ITEM_COMPONENT_STATE`;
- `BLOCK_ENTITY_STATE`;
- `INVENTORY_STATE`;
- `TAG_MEMBERSHIP`;
- `RECIPE_MATCH`;
- `LOOT_RESULT`.

`REGISTRY_ENTRY_PRESENT` demonstrates the parameterized pattern; several other
observations remain fixture-specific and must become productive only as Alpha
capabilities require them. New coverage includes equipment, entities,
interactions, effects, commands, drops, spawning and deterministic worldgen.

### Multi-version, assets and repair

Requirements and normalized observations are shared across Alpha targets
`1.21.11`, `26.1` and `26.2`, while implementations and probes may vary by
environment. A representable version is not supported until its compatible
knowledge, bootstrap, Harness and probes are validated end-to-end.

Asset Pipeline owns creation and transformation. Structural artifact
validation owns format, dimensions, alpha, paths, references and packaging.
Screenshot/render validation is not a general Alpha blocking gate.

New probes must emit the existing normalized validation evidence so they can
reuse Semantic Repair, rebuild, revalidation and reconciliation. No parallel
evidence system is introduced.

### Ownership and blockers

- Capability Planner: capabilities, requirements and expectations.
- ArtifactValidator: structural artifact evidence.
- Build/Debug: build evidence and build repair.
- Test Harness: Minecraft runtime evidence.
- Asset Pipeline: asset operations and asset validation.
- Brain: knowledge and diagnosis/repair.
- Runtime/Ledger: execution and evidence reconciliation.
- CompletionGate: final completion decision.

Current Alpha blockers are general expectation generation, single runtime
validation selection, fixture-specific probes, entity/spawn/attribute/
interaction/worldgen coverage, real `26.1`/`26.2` Harness support and broader
asset structural expectations. Visual screenshots are not an Alpha blocker.

## 7. Assets strategy

Status: `ACCEPTED`

### Core principle — Vanilla-First Asset Strategy

PD Agent must not default to generating a new visual asset whenever the user requests new content. It must first determine whether Minecraft already contains a semantically and visually similar asset that can be reused or adapted.

Canonical decision order:

`REUSE → DERIVE → GENERATE`

1. `REUSE`: use an appropriate existing vanilla asset/reference when no meaningful visual transformation is required.
2. `DERIVE`: start from the closest appropriate vanilla asset or coherent vanilla asset family and apply deterministic transformations.
3. `GENERATE`: invoke visual generation only when reuse/derivation is insufficient for the requested concept.

Examples:

- tin/metal content may derive from an appropriate vanilla metal family;
- ruby/gem content may derive from an appropriate vanilla gemstone such as emerald;
- strawberry cake may derive from vanilla cake;
- ruby equipment may derive from the corresponding vanilla equipment silhouettes and be transformed consistently;
- a new ore may derive from an appropriate vanilla ore texture/pattern;
- a new wood family should prefer transforming a coherent vanilla wood family instead of independently inventing every related asset;
- a mob variant may reuse a compatible vanilla model/behavior and derive its texture when that satisfies the request.

The LLM must not be the sole source of truth for asset similarity. The future Brain/asset layer should expose a version-aware vanilla asset catalog/index with enough semantic metadata to select suitable source assets and families reproducibly.

### Deterministic Asset Toolkit — MUST Alpha

The productive runtime must gain safe workspace-contained binary/asset operations sufficient to:

- read/write/copy PNG assets;
- move/rename supported assets where needed;
- preserve and validate alpha/transparency;
- validate image format and dimensions;
- recolor and palette-map textures;
- perform simple deterministic pixel-art transformations;
- crop/compose/mask where required by supported Alpha tasks;
- preserve nearest-neighbor/pixel-art characteristics where resizing or transformation requires it;
- produce assets at the correct namespace/path;
- verify that required assets are packaged in the delivered JAR.

Deterministic operations should be preferred when they can satisfy the user's intent because they are cheaper, faster, more reproducible and more likely to remain visually coherent with Minecraft.

### Visual generation — MUST capability, fallback path

Alpha must have a model-agnostic visual-generation boundary for basic genuinely novel assets when deterministic derivation is insufficient. The final interface name is deferred, but conceptually it may resemble an `AssetGenerationProvider`.

The product must not depend on one image model/provider. Managed routing can choose the concrete provider later.

Visual generation is a fallback, not the default path. Generated output must still pass the same Minecraft-aware processing and validation pipeline before it can become part of a completed task.

### Minecraft-aware asset planning

Asset work must be planned according to its Minecraft role, rather than treating every asset as a generic image. The pipeline must understand at least the supported Alpha categories required by the capability catalog, including item, block, equipment and basic entity textures, and their related models/blockstates/resource references.

The planner should also reason about coherent asset families so a multi-part request produces visually consistent related assets.

### Models and blockstates

MUST Alpha:

- item models required by supported Alpha content;
- block models required by supported Alpha content;
- blockstates required by supported Alpha content;
- simple/basic entity model reuse or adaptation sufficient for the accepted basic mob/entity scope;
- correct linkage between models, textures, namespaces and generated resources.

Complex custom 3D modelling and advanced animations are POST-ALPHA.

### Sounds

For Alpha:

- referencing/reusing appropriate vanilla sounds is MUST where supported content requires sound behavior;
- safely incorporating a user-provided compatible sound is SHOULD;
- arbitrary AI-generated original audio is POST-ALPHA and must not block Alpha.

### Validation and evidence

An asset is not complete merely because a file exists.

For supported Alpha assets, validation must be able to prove as applicable:

- file exists and is a valid supported format;
- expected dimensions/alpha constraints are satisfied;
- path and namespace are correct;
- model/blockstate/resource references resolve correctly;
- the asset is packaged into the current delivered JAR;
- Minecraft/build/runtime does not reject the resulting resource set.

PD Agent must not claim that an asset "looks correct" solely from structural validation. Genuine visual correctness requires separate visual evidence such as a render/screenshot plus appropriate analysis when that capability exists.

### Provenance and safety

Asset operations must preserve provenance sufficient to distinguish reused, deterministically derived, generated and user-provided assets. The implementation must not assume that arbitrary external assets can legally or safely be downloaded/repackaged. Exact licensing/distribution policy is a later implementation requirement and must be researched before enabling external asset acquisition.

### Multi-Agent boundary

No dedicated Image/Asset Agent is approved by this decision.

Alpha first defines the capability/tool/provider boundary:

`Fabric planning/runtime → Asset Pipeline → deterministic tools and/or visual-generation provider`

Whether this responsibility should later become a specialized agent remains explicitly deferred to roadmap Point 8. The asset architecture must not prevent that future separation.

## 8. Multi-version Minecraft/Fabric strategy

Status: `ACCEPTED`

R70 verdict:

`PD_AGENT_R70_MULTI_VERSION_FOUNDATION_PARTIAL`

### Reuse-first architecture decision

PD Agent must **reuse** the existing version-aware foundation:

- `KnowledgeEnvironment`;
- `KnowledgeEnvironmentResolver`;
- `FabricInspector`;
- Brain compatibility/version filtering;
- provenance/retrieval/cache infrastructure;
- version context already transported by the Minecraft Harness;
- version-neutral Build/Artifact/Storage components.

Do **not** introduce a parallel `FabricEnvironmentProfile` or second environment model unless a future audited requirement proves that the existing environment abstraction cannot be extended safely.

### Alpha supported targets

Alpha MUST support the following Fabric/Minecraft targets end-to-end:

- Minecraft `1.21.11` — legacy/obfuscated baseline already used by the current productive stack;
- Minecraft `26.1` — first modern deobfuscated-generation target and an important architectural boundary;
- Minecraft `26.2` — primary modern/recommended Alpha target.

This is an explicit support matrix, not a promise to support every historical Minecraft version.

### Two technical environment families

The implementation must account for the ecosystem boundary between:

- `LEGACY_OBFUSCATED`: Minecraft `<= 1.21.11`;
- `MODERN_UNOBFUSCATED`: Minecraft `>= 26.1`.

These are compatibility/environment families, not separate agents or separate PD Agent runtimes.

The same product/runtime architecture remains authoritative. Version-specific differences belong in version-aware data, adapters, templates, knowledge and Harness/probe compatibility where necessary.

### Productive version selection

Canonical flow:

`request/project → detect/resolve version → KnowledgeEnvironment → support matrix → compatible knowledge/template/capabilities → build → compatible Harness → CompletionGate → Delivery`

Rules:

- If the user explicitly requests a supported target version, PD Agent uses that target.
- If the user does not specify a version for a newly created mod, PD Agent uses the current recommended Alpha target, initially `26.2`.
- For an imported project, PD Agent detects the existing environment and preserves it when supported.
- Unsupported imported/project versions must fail clearly as `UNSUPPORTED_VERSION` or equivalent; PD Agent must not silently migrate or change the target version.
- Explicit migration between supported versions may be added later, but it is not required to silently occur during normal task execution.

### Version-aware support registry

PD Agent needs a small canonical support registry/matrix that complements — not replaces — `KnowledgeEnvironment`.

Conceptually it maps a supported target/environment to the resources required to prove support, including as applicable:

- validated bootstrap/template materialization;
- Brain knowledge sources/packs;
- mapping/deobfuscation mode;
- compatible Loader/Fabric API/Loom/Java/Gradle constraints;
- capability compatibility;
- Harness/probe compatibility;
- Alpha acceptance evidence.

The registry must not become a monolithic duplicate of the existing environment/knowledge system.

### Brain isolation across versions

Version-sensitive knowledge must not leak across incompatible environments.

Especially:

- legacy Yarn/Intermediary-oriented knowledge must not be injected into modern deobfuscated targets unless explicitly compatible;
- source packs, mappings, examples and compatibility claims must be selected against the resolved `KnowledgeEnvironment`;
- provenance must preserve the exact source/version used.

### Templates and capabilities

Supported versions must use validated version-aware bootstrap/template materialization rather than ad-hoc copies.

Capability contracts should remain version-neutral where possible. Version-specific implementation details belong behind compatibility/adaptation boundaries rather than multiplying capability types by Minecraft version.

Example principle:

`TOOL(type=SWORD, material=RUBY, ...)`

should remain one conceptual capability even if the generated implementation differs between `1.21.11` and `26.2`.

### Validation rule for advertised support

PD Agent may advertise a Minecraft/Fabric target as Alpha-supported only when the relevant end-to-end chain is validated for that target:

`template/bootstrap → Brain/context → capability planning → mutation → build → artifact → Minecraft Harness/probes → CompletionGate → Delivery`

A version being detectable or buildable is not enough to claim product support.

### Scope control

Alpha intentionally supports a small explicit set of targets rather than attempting every Fabric-compatible Minecraft release.

New versions should be added by extending the support registry/data/adapters and passing the same validation/acceptance gates, not by forking the runtime.

## Point 8. Multi-Agent decision

Status: `ACCEPTED`

R75 audit verdict:

`PD_AGENT_R75_ALPHA_SPECIALIZED_TOOLS_ROUTING_RECOMMENDED`

The audit was performed against baseline
`8aaf3d5a7f256f7913db4b6249a20b08de0aaf66` with no repository, provider,
Minecraft, benchmark, Product Execution or ledger side effects.

### Canonical Alpha decision

`ALPHA_SINGLE_AGENT_WITH_SPECIALIZED_TOOLS_AND_MODEL_ROUTING`

Alpha continues with one productive agent/runtime. Specialization comes from
deterministic components, specialized tools, scoped context, Minecraft Brain,
Capability Planner, Asset Pipeline, validators, Test Harness, Semantic Repair,
version-specific adapters and provider/model routing where useful.

Model routing does not require multiple models in every run. Multi-model,
parallel execution and specialized components are not Multi-Agent.

Multi-Agent is `NOT_REQUIRED_FOR_ALPHA`. No Manager, Architect, Planner,
Developer, Repair, Brain/Research, Asset, QA or version-specialist agents,
consensus/voting, or agent orchestration framework is approved for Alpha.
A reviewer agent remains a post-Alpha experiment only if future evidence
justifies it.

### Alpha boundaries

- Capability Planner remains deterministic/code-first, with LLM assistance for
  intent interpretation only when needed; it is not a separate agent.
- Asset Pipeline keeps `REUSE -> DERIVE -> GENERATE`, using deterministic
  tools, same-agent reasoning and an optional specialized generation provider.
- Correctness remains authoritative through `ArtifactValidator`, Test Harness,
  normalized evidence, `TaskProgressLedger` and `CompletionGate`.
- Semantic Repair remains a phase of the same runtime; Brain remains the
  knowledge boundary; version differences remain data, adapters and probes.
- Future deterministic workers may provide parallelism without introducing
  Multi-Agent infrastructure.

Context specialization must be attempted with scoped context, selectors,
contracts, structured evidence, summaries, budgeting and retained repair
evidence before creating separate agents. Provider/model specialization may
be added where useful, but provider specialization is not agent specialization.

Historical step exhaustion, ineffective repair, Harness failures, Brain gaps
and planning gaps do not demonstrate that another agent would have fixed their
root causes. Multi-Agent must not be added without evidence of a repeated
problem, insufficiency of the single-agent/tool architecture, a clear
non-overlapping boundary, structured input/output, ownership and recovery,
and no parallel authority to `CompletionGate`.

### Post-Alpha reopening rule

Multi-Agent may be reconsidered only after comparative evidence demonstrates
material benefit in quality/success, cost, latency, recovery and complexity.
The evidence must include a favorable benchmark against the single-agent
architecture and show acceptable reliability, security and ownership costs.

This decision does not start Point 9 or v0.10 work.

## Point 9. Alpha security, compatibility and performance requirements

Status: `ACCEPTED`

R77 audit verdict:

`PD_AGENT_R77_ALPHA_SCP_FOUNDATION_PARTIAL`

R77-V verdict:

`PD_AGENT_R77_V_SCP_EVIDENCE_CONFIRMED_WITH_CORRECTIONS`

R77-V validation recorded `208 passed, 0 failed, 0 errors`. The earlier
pytest errors were environmental permission failures in the default temp
directory and were not product failures.

The existing Security, Compatibility and Performance foundation is reusable
but requires the extensions below. Alpha must not create a parallel runtime
architecture.

### Security

Validated PD Agent templates may be treated as trusted bootstrap material
within normal runtime limits. Content added later is not trusted automatically.

Imported projects are `UNTRUSTED` until inspection, compatibility/trust
classification and an effective execution boundary have been applied.

An imported Gradle build can execute its wrapper, build files, settings and
plugins with the child process authority inherited from PD Agent. `shell=False`
prevents shell injection but does not constrain Gradle authority. Timeout
limits duration, not filesystem, network, process or secret authority.

For Alpha, imported build/runtime execution requires technical isolation. User
confirmation may make the risk explicit, but it is not a substitute for
isolation. If effective isolation is unavailable, the runtime must block before
build or Minecraft execution while still permitting safe inspection.

README files, source comments, Gradle/configuration, JSON/resources, logs,
Minecraft output, imported project content and external/Brain sources are
untrusted data. Embedded text grants no authority. System/runtime policy,
structured contracts, tool schemas and deterministic security policies remain
authoritative.

Provider/API secrets must not be inherited unnecessarily by Gradle, Minecraft,
Harness or other untrusted child processes. Child environments contain only
task-required values.

Alpha resource safety must bound workspace and disk growth, asset input/output,
image dimensions and pixel counts, logs/evidence, child-process lifetime and
cleanup, and concurrent Product executions. Exact numeric limits remain an
implementation decision and must not be invented here.

Asset processing must validate type, format, dimensions, size, malformed data,
paths/namespaces, archive/JAR paths, bounded decompression and provenance.

### Compatibility

Alpha MUST support these targets end-to-end before Alpha is declared:

- Minecraft/Fabric `1.21.11`;
- Minecraft/Fabric `26.1`;
- Minecraft/Fabric `26.2`.

`SUPPORTED_VERSION` requires the complete chain:

`Support Registry/environment -> compatible template/import classification -> compatible Brain knowledge -> capability implementation -> build -> required Artifact/Runtime validation -> CompletionGate -> Delivery`

`VERSION_SUPPORTED` does not imply `CAPABILITY_SUPPORTED`. A `(version,
capability)` pair is supported only when its implementation path, required
validators/probes and acceptance evidence exist. Otherwise it must fail fast as
`NOT_SUPPORTED`; silent best-effort execution is forbidden.

Imported projects must be classified as `SUPPORTED`,
`SUPPORTED_WITH_LIMITATIONS`, `UNSUPPORTED` or `UNKNOWN/REVIEW_REQUIRED`.
Unknown versions, loaders, mappings and build systems must not be silently
modified or upgraded. Forge, NeoForge, Paper, Velocity, Kotlin, multi-module
projects and custom mappings/plugins/build systems are not promised without
explicit later validation.

Knowledge compatibility is a hard gate. Version-sensitive records, packs,
mappings and examples must match the active `KnowledgeEnvironment` or carry
explicit compatible status, with provenance preserved. In particular,
1.21.11 Yarn/Intermediary knowledge must not leak into `26.1` or `26.2`.

### Performance

Alpha does not define an artificial task-duration SLA. Acceptable performance
means bounded, observable execution without infinite loops, pathological
redundant work or unpredictable recovery.

Provider requests, tokens/context, tool calls, retries, builds and processes
must have explicit configurable limits. Current baseline values are recorded,
not permanent Alpha values:

- `max_agent_steps = 40`;
- `max_tool_calls = 120`;
- `max_build_attempts = 5`;
- `provider_retry_limit = 2`;
- `process_timeout_seconds = 600`;
- `max_tool_output_bytes = 1000000`;
- `max_context_bytes = 2000000`.

Reuse build, artifact and runtime evidence only when it is both `CURRENT` and
contract-compatible. Caching must never replace required validation.

Composed tasks should plan coherent mutation batches, run static/pre-build
validation, build once when safe, validate the artifact and execute only the
required current runtime validations. Brain must retain bounded retrieval,
bounded context, deduplication where applicable and version filtering before
injection.

The existing non-blocking Product execution handle and RunState/RunEvent
projection remain the foundation. Build, Minecraft, provider and repair work
must not block the UI; cancellation and presentation details remain deferred
to Point 10.

### Alpha blockers

Current Alpha blockers are:

- imported Gradle execution without effective technical isolation;
- unnecessary secret/environment inheritance to untrusted child processes;
- no complete untrusted-data boundary for project/source content;
- incomplete resource and asset safety limits;
- no end-to-end validation chain for `26.1` and `26.2`;
- no productive Support Registry/capability matrix;
- missing implementation and validation evidence for capabilities advertised on
  each target;
- incomplete bounds for disk, assets, logs, process lifetime and concurrency.

Imperfect caching alone is not an Alpha blocker.

### Architecture disposition

Reuse `SecurePathResolver`, `ToolExecutor`, AgentRuntime limits,
`GradleBuildRunner` process mechanics, ArtifactValidator/currentness,
TaskProgressLedger, RunStorage/recovery, Minecraft Test Harness,
KnowledgeEnvironment, CompletionGate, provider/economic telemetry and
non-blocking Product execution.

Extend project inspection/classification, child-process environment policy,
resource limits, Harness multi-version support, ArtifactValidator, knowledge
compatibility gates, Capability Planner, Support Registry, capability/version
validation, Brain budgeting and asset validation.

Create only the missing imported-project trust boundary, asset safety pipeline
and version-by-capability support representation. Defer Multi-Agent, a second
completion authority, distributed orchestration, commercial SLA and cloud
hardening.

## Point 10. Product/UI requirements remaining for Alpha

Status: `ACCEPTED`

R79 audit verdict:

`PD_AGENT_ALPHA_PRODUCT_UI_REQUIREMENTS_READY`

The v0.9 product direction is extended into Alpha. It is not replaced by a
new visual direction or a new Product/UI architecture.

### Reuse-first product foundation

Preserve these v0.9 contracts and product authorities:

- `Project -> Task -> Execution -> Delivery`;
- prompt-centered Home with attachments/assets and a clear CTA;
- execution based on real persisted state;
- navigation independent from execution;
- authoritative Success and `CompletionGate`;
- JAR as the primary Delivery;
- Human Evidence and Technical Evidence;
- persistent Projects and History;
- Details as a secondary layer;
- managed-first provider opacity;
- minimal PD Agent/Minecraft visual identity;
- functional accessibility baseline;
- non-blocking execution handles and RunState/RunEvent projection.

Do not introduce a permanent dashboard, permanent sidebar, IDE, terminal-first
UX or a technical pipeline as the primary experience.

### Canonical Alpha product flow

`HOME -> NEW / IMPORT / CONTINUE -> target + compatibility + capability + trust resolution -> TASK -> EXECUTION -> optional INTERVENTION -> CompletionGate -> SUCCESS / FAILURE -> DELIVERY -> CONTINUE SAME PROJECT / HISTORY / REOPEN`

`Project != Task != Execution` remains an invariant. A successful task may
create the next Task on the same Project without reimport or reupload.

### Home and project entry

Home is extended, not redesigned. Its primary elements remain the prompt,
attachments/assets and CTA, with Import, recent Projects and discreet examples.
New, Import and Continue are Alpha requirements:

- New creates a Project from a compatible template when no Project exists;
- Import inspects the project, detects its environment and classifies
  compatibility and trust;
- Continue opens an existing Project and creates a new Task on it.

No mandatory technical wizard is added. Imported Projects start as
`UNTRUSTED`; inspection may be allowed while build/runtime remain blocked until
the technical trust boundary is satisfied. User confirmation alone must never
be presented as proof that arbitrary project code is safe.

### Version and capability UX

Alpha targets are `1.21.11`, `26.1` and `26.2`. Version resolution is automatic
by default: New without an explicit version uses the recommended target
`26.2`, explicit supported versions are respected, Import detects and
preserves the project target, and Continue keeps the Project target. There is
no silent upgrade and no mandatory technical version selector in Home.

Capabilities expose truthful, human-readable states:

- `SUPPORTED`;
- `SUPPORTED_WITH_LIMITATIONS`;
- `NOT_SUPPORTED`;
- `REVIEW_REQUIRED`.

Material limitations are communicated before promising a result. Unsupported
work must not silently fall back to best effort.

### Execution, intervention and recovery

Execution shows understandable overall state, honest activity, Details and
Intervention when needed, without exposing the complete technical pipeline or
invented percentages. Brain, build, repair and Minecraft remain secondary
unless a human-readable activity adds value.

Safe Cancel is `MUST_ALPHA`: it must stop and reconcile the real Execution,
including provider, build and Minecraft work, with an unequivocal persisted
outcome. The implementation is not designed by this roadmap entry.

Internal recoverable failures use `diagnose -> repair -> retry` without
unnecessary user interruption. User action is required only for irreducible
ambiguity, missing input/assets, trust/security decisions, incompatibility,
provider configuration or recovery conflicts. Terminal failure explains what
did not complete, what remains valid and the next useful action, without a
traceback as the primary UX.

Closing the browser must not cancel automatically. Alpha must reopen active
Executions from persisted authority, represent Interrupted/Unknown honestly,
prevent duplicate/conflicting execution and recover History/Delivery. General
checkpoint/resume remains `POST_ALPHA`; contextual retry is `SHOULD_ALPHA` when
a safe new operation exists.

### Composed tasks and assets

Composed tasks remain one objective and one CompletionGate evaluation, not a
technical checklist. The UI may show an optional expandable summary by area,
but partial results are never Success.

Assets use the mostly automatic `REUSE -> DERIVE -> GENERATE` strategy and may
accept user-provided assets. Activity such as asset creation may be shown;
provenance distinguishes reused, derived, generated and user-provided assets.
Asset previews are `SHOULD_ALPHA`; a graphics editor is `POST_ALPHA`.

### Brain, managed AI and settings

Brain and research remain mostly invisible. Human-readable research activity
may appear, while sources and provenance belong in Details. There is no Alpha
Knowledge Browser/dashboard.

Managed-first remains the normal-user experience. Provider/model selectors,
BYOK, API-key management, routing controls, token controls, billing and admin
UX are `POST_ALPHA`; pricing and billing are not designed here.

Settings stay minimal. A preferred Minecraft version is not an Alpha Settings
requirement; automatic target resolution is the normal behavior. Preferences
are added only when they have demonstrated Product value.

### Success, Delivery, Projects and evidence

Success keeps the JAR prominent and includes Project/mod name, Minecraft
target, verified completion status, JAR, a short summary, Details and
Continue modifying. Tokens, tool calls, Brain records, build counters and
provider internals are not primary UX.

Projects must be findable, openable and continuable. History preserves
`Task -> Execution -> result/evidence -> Delivery`; the existing modal/layer
pattern remains valid while usable and must not become a dashboard by default.

Details exposes activity, result, target, validation, JAR and relevant
intervention. Human Evidence summarizes requirements, changes, build, repairs,
runtime validation, artifact and completion. Technical Evidence carries IDs,
environment, files, attempts, validations, observations, SHA/currentness,
failures/repairs, references and useful Brain provenance.

### Accessibility and required states

Alpha accessibility is desktop-first with reasonable responsiveness,
keyboard operation, visible focus, semantic dialog behavior, Escape and focus
restoration, semantic labels, readable contrast, non-color-only state, basic
screen-reader support and reduced motion for meaningful movement.

The product must represent truthful, actionable states for empty/loading,
reopening, provider unavailable, unsupported version/project, compatibility
limits, import trust, missing workspace, corrupt metadata, interrupted
execution, missing/stale Delivery, unavailable network/API and internal error.

### Alpha disposition

`MUST_ALPHA` includes New/Import/Continue, consecutive tasks, multi-version
automatic resolution, capability support states, import trust UX, asset
strategy, composed tasks, real Intervention, safe Cancel, browser
close/reopen, persistent recovery, conflict protection, History reopen, JAR
Delivery, Human/Technical Evidence, required empty/loading/error states,
accessibility baseline and non-blocking UI.

`SHOULD_ALPHA` includes asset previews, contextual Retry, expandable composed
task summaries, Brain provenance in Details and useful project defaults when
evidence supports them.

`POST_ALPHA` includes general checkpoint/resume, normal-user provider/model
selection, full Local/BYOK UX, billing/credits, collaboration/cloud,
advanced release management, project branches/version management, graphics
editor, dashboard/IDE and final mobile product.

No new primary Product/UI architecture or visual direction is opened by this
decision.

## Point 12. Alpha gap inventory

Status: `ACCEPTED`

R81 audit verdict: `PD_AGENT_R81_ALPHA_GAP_INVENTORY_READY`

The inventory below records the consolidated work required between v0.9 and
Alpha. It is a planning input, not a milestone plan. No evidence justifies
replacing the primary architecture. The strategy is `REUSE + EXTEND + NEW`
where a capability is genuinely absent.

### Foundations to reuse

Preserve and extend, without duplicating:

- `FabricTaskContract`, `TaskProgressLedger`, `CompletionGate` and `RunState`;
- `RunStorage`, evidence/currentness and `Project -> Task -> Execution -> Delivery`;
- `ProjectInspector`, BuildRunner, ArtifactValidator foundation and Minecraft Harness core;
- `KnowledgeEnvironment`, Brain retrieval/selection/injection and provenance;
- benchmark catalog, manifests, hashes, workspace preparation, scheduler,
  executor and collector;
- provider/economic telemetry, `SecurePathResolver`, tool policy and
  non-blocking Product execution.

### Rework and extension

These are extensions or rework, not replacement architecture:

- hardcoded Server Core resolver;
- productive runtime first-match validation selection;
- benchmark classification linkage to the authoritative CompletionGate;
- capability, scenario and version schemas;
- ArtifactValidator expectations and generalized probes;
- multi-version support, Brain packs/catalog and Product Alpha states;
- security and resource boundaries.

### Consolidated gap register

| ID | Area | Classification | Alpha blocker | Concrete gap |
|---|---|---|---|---|
| GAP-PLANNER-001 | Planning | FOUNDATIONAL_BLOCKER | YES | General capability planner/resolver, schema, version/capability support and requirement decomposition |
| GAP-COMPOSE-001 | Composition | CAPABILITY_BLOCKER | YES | Multi-capability dependencies, composition and batching |
| GAP-VERSION-001 | Version Matrix | FOUNDATIONAL_BLOCKER | YES | Complete 1.21.11/26.1/26.2 bootstrap-to-Delivery support chain |
| GAP-BRAIN-001 | Brain Knowledge | FOUNDATIONAL_BLOCKER | YES | Populated versioned knowledge, vanilla semantic catalog, capability/assets relations and leakage evidence |
| GAP-PROJECT-001 | New Project | PRODUCT_BLOCKER | YES | Version-aware clean-template bootstrap with own identity |
| GAP-IMPORT-001 | Import/Trust | SECURITY_BLOCKER | YES | Compatibility/trust classification and safe imported execution boundary |
| GAP-CAP-001 | Fabric Capability Catalog | CAPABILITY_BLOCKER | YES | General productive paths beyond Server Core |
| GAP-ASSET-001 | Deterministic Assets | CAPABILITY_BLOCKER | YES | Binary-safe toolkit, semantic lookup and structural/reference/package validation |
| GAP-ASSET-002 | Advanced Asset Generation | NON_BLOCKING_ALPHA | NO | Advanced/generative/subjective visual capability beyond deterministic Alpha requirements |
| GAP-VALID-001 | Runtime Validation | VALIDATION_BLOCKER | YES | Execute all applicable 1-to-N runtime validation requirements |
| GAP-VALID-002 | Artifact Validation | VALIDATION_BLOCKER | YES | General structural expectations for resources, classes, assets and references |
| GAP-HARNESS-001 | Minecraft Harness | VALIDATION_BLOCKER | YES | General parameterized probes and multi-version Harness evidence |
| GAP-REPAIR-001 | Repair | VALIDATION_BLOCKER | YES | Generalized compile/resource/runtime repair evidence across capabilities and versions |
| GAP-SEC-001 | Imported Execution Isolation | SECURITY_BLOCKER | YES | Technical isolation for untrusted imported Gradle/build/runtime execution |
| GAP-SEC-002 | Resources/Processes/Concurrency | SECURITY_BLOCKER | YES | Bounds for workspace, disk, assets, logs, secrets, cleanup and concurrency |
| GAP-PRODUCT-001 | Product Project Flow | PRODUCT_BLOCKER | YES | General New, Import and Continue flows |
| GAP-PRODUCT-002 | Product Capability/Version/Trust UX | PRODUCT_BLOCKER | YES | Truthful support states, trust, composition, assets and intervention |
| GAP-PRODUCT-003 | Product E2E | ACCEPTANCE_BLOCKER | YES | Alpha breadth Product E2E beyond controlled Server Core |
| GAP-BENCH-001 | Alpha Benchmark Campaign | ACCEPTANCE_BLOCKER | YES | Breadth, composition, consecutive, versions, New/Import, assets, repair, negative and held-out campaign |
| GAP-EVIDENCE-001 | Version x Capability Evidence | ACCEPTANCE_BLOCKER | YES | Evidence for every advertised supported `(version, capability)` pair |

Count: **20 consolidated gaps**, including **19 Alpha blockers**. Gaps are
not milestones; Point 13 must group them into the minimum coherent set.

The semantic catalog and metadata needed for `REUSE -> DERIVE` are Alpha
blocking and belong to `GAP-ASSET-001` and/or `GAP-BRAIN-001`. Only advanced,
generative or subjective visual quality remains `GAP-ASSET-002` and
non-blocking.

### Capability state

`EXTEND`: items, blocks, block items, recipes, tags, loot/drops and the
assets/models/lang foundation.

`NEW` general productive path: food/components, tools, weapons, armor,
materials/tiers, durability/damage/speed, interactions, events, effects,
commands, mobs/entities, attributes, spawning, vanilla AI reuse and
ores/worldgen.

Filesystem mutation alone is not Product capability support.

### Version state

- `1.21.11`: validated foundation exists, with limited breadth.
- `26.1`: not Alpha-supported.
- `26.2`: not Alpha-supported.

Configurability or model representation is not support. Support requires:

`bootstrap -> Brain/environment -> capability implementation -> build ->
validation -> CompletionGate -> Delivery -> acceptance evidence`.

### Validation, security, product and acceptance state

Reusable validation foundation includes declarative requirements,
multi-requirement CompletionGate, ledger/currentness, ArtifactValidator base,
registry observation and Semantic Repair. Alpha blockers are N runtime
validation, structural artifact expectations, generalized and multi-version
probes, generalized repair evidence and explicit benchmark-to-CompletionGate
authority.

Reusable security foundation includes path traversal and protected paths,
ancestry/symlink checks, fixture contamination detection,
redaction/evidence and process-timeout mechanics. Alpha blockers are imported
execution isolation, child environment/secrets policy, bounded resources,
asset/archive safety, cleanup/cancellation, concurrency and the complete
untrusted-data authority boundary.

The v0.9 Product architecture is reusable and Server Core Product E2E is
validated. Alpha still requires general New/Import/Continue, version and
capability states, trust, composition, assets, intervention, cancellation,
recovery/reopen, Success/Delivery and broader Product E2E.

Benchmark infrastructure is `REUSE + EXTEND`. Missing campaign evidence covers
capability breadth, composition, consecutive tasks, real multi-version,
held-out, New/Import, assets, repair/adversarial, Product E2E,
version-by-capability, frozen RC, Managed Reference Configuration, hard gates
and explicit CompletionGate authority.

### Direct dependencies

Dependencies are technical only and do not define milestone order:

- Planner -> capability schema and version support data.
- Composition -> planner, dependency representation and N validation.
- New Project -> version registry, templates and identity generation.
- Import -> inspector, compatibility, trust and isolation.
- Brain -> populated versioned sources and semantic catalog.
- Capability support -> planner, implementation tools and validation.
- Multi-version -> bootstrap, Fabric environment, Brain, adapters and Harness.
- Assets -> binary-safe tools, semantic metadata, validation and provenance.
- Product Alpha -> backend capability/version/trust contracts.
- Held-out/release campaign -> implementation readiness, frozen RC, manifests
  and CompletionGate.

### Duplication prohibitions

Do not create a second Brain, CompletionGate, ledger/evidence system,
Minecraft Harness, BuildRunner, Project/Task/Execution/Delivery model,
scheduler, benchmark framework, Multi-Agent framework, non-blocking execution
architecture or tool/security policy.

### Point 13 readiness

The inventory is sufficiently complete to begin Point 13. Point 13 must group
these gaps into the minimum coherent milestone set and must not map one gap to
one milestone automatically. No milestones, versions or ordering are defined
by Point 12.

## Point 13. Alpha milestone grouping

Status: `ACCEPTED`

R83 audit verdict: `PD_AGENT_R83_SIX_MILESTONE_GROUPING_READY_WITH_CORRECTIONS`

The minimum coherent Alpha grouping is six conceptual milestones. They are
not a rigid waterfall, do not assign release versions and do not replace the
v0.9 architecture. `GAPS != MILESTONES`.

### M1 - General Fabric Task Foundation

Primary closure: `GAP-PLANNER-001`, `GAP-COMPOSE-001`.

Foundation for `GAP-CAP-001`. Establish a general, parameterized,
composable, version-aware path:

`request -> capability schema -> planning -> dependency/composition ->
requirements -> validation requirements`.

Reuse `FabricTaskContract`, `TaskProgressLedger`, `CompletionGate` and the
existing runtime/orchestration. No second runtime or orchestrator.

Exit capability: representable Fabric requests become capability and
validation plans without Server Core hardcoding. This does not promise full
capability breadth, three supported versions, Product Alpha or release
readiness.

### M2 - Versioned Fabric Platform and Brain

Primary closure: `GAP-VERSION-001`, `GAP-BRAIN-001`, `GAP-PROJECT-001`.

Foundation for `GAP-CAP-001` and `GAP-ASSET-001`. Establish Support Registry,
version-aware templates/bootstrap, own project identity, mod/package/metadata
handling, populated versioned Brain packs, semantic catalog foundation and
correct Fabric environment adapters for `1.21.11`, `26.1` and `26.2`.

Detection or configurability is not support. Exit capability is a clean
identity-bearing project with the correct platform and knowledge environment
for each Alpha target, not complete capability breadth.

### M3 - Alpha Fabric Capabilities and Assets

Primary closure: `GAP-CAP-001`, `GAP-ASSET-001`.

`GAP-ASSET-002` is explicitly `POST_ALPHA / DEFER`. Implement the MUST_ALPHA
capability breadth with general primitives, composition and the asset boundary
`REUSE -> DERIVE -> GENERATE`.

Every capability batch must include implementation, required validators or
probes, artifact expectations and tests/evidence. `(version, capability)` is
the real support/evidence unit. Advanced subjective visual generation is not
an Alpha blocker.

Exit capability: MUST_ALPHA breadth is implemented with deterministic asset
operations and corresponding evidence, without fixture-specific hardcoding.

### M4 - Generalized Validation, Repair and Runtime

Primary closure: `GAP-VALID-001`, `GAP-VALID-002`, `GAP-HARNESS-001`,
`GAP-REPAIR-001`.

Extend the existing Harness, ArtifactValidator, Semantic Repair,
ledger/currentness and CompletionGate. Add 1-to-N validation, structural
artifact expectations, parameterized probes, multi-version runtime evidence,
build/resource/runtime repair, rebuild/revalidation and reconciliation.

M3 and M4 are mandatory co-development. M4 is not deferred QA and must not
create a second validation or evidence system.

Exit capability: Alpha capabilities can produce reproducible, version-aware,
repairable evidence through the authoritative CompletionGate.

### M5 - Secure Product Alpha

Primary closure: `GAP-IMPORT-001`, `GAP-SEC-001`, `GAP-SEC-002`,
`GAP-PRODUCT-001`, `GAP-PRODUCT-002`.

Close New, Import, Continue, compatibility/trust/capability states, composed
task and asset UX, Intervention, safe Cancel, reopen/recovery, imported
execution isolation, child environment/secrets policy, resource bounds,
cleanup and concurrency boundaries.

Security is a continuous concern from M1. No M1-M4 execution path may be
introduced without the applicable safety guardrails. Product integration is
also continuous through M1-M4; M5 closes Product Alpha breadth rather than
starting Product work.

Exit capability: a non-programmer can use Alpha capabilities through the real
Product with truthful states and Alpha security guarantees.

### M6 - Alpha Acceptance and Release Candidate

Primary closure: `GAP-PRODUCT-003`, `GAP-BENCH-001`, `GAP-EVIDENCE-001`.

Certify, rather than discover for the first time, capability breadth,
composition, consecutive tasks, New/Import, assets, repair/negative,
security, Product E2E, all three targets, version-by-capability evidence,
held-out acceptance, Managed Reference Configuration, frozen RC, hard gates,
Delivery/JAR and CompletionGate authority.

Acceptance/evidence hooks evolve incrementally: M1 schemas, M2
version/project manifests, M3 capability/composition/assets scenarios, M4
validation/repair/runtime/gate evidence and M5 Product/security E2E hooks.
M6 uses the existing catalog, manifests, hashes, workspaces, scheduler,
executor, collector and telemetry; it does not create a parallel benchmark
framework.

Exit capability: a frozen RC demonstrates the Alpha hard gates over the
immutable held-out set and can be declared PD Agent Alpha.

### Primary gap ownership

Each gap has one primary closure owner:

- `GAP-PLANNER-001` -> M1; `GAP-COMPOSE-001` -> M1.
- `GAP-VERSION-001` -> M2; `GAP-BRAIN-001` -> M2;
  `GAP-PROJECT-001` -> M2.
- `GAP-CAP-001` -> M3; `GAP-ASSET-001` -> M3;
  `GAP-ASSET-002` -> POST_ALPHA.
- `GAP-VALID-001` -> M4; `GAP-VALID-002` -> M4;
  `GAP-HARNESS-001` -> M4; `GAP-REPAIR-001` -> M4.
- `GAP-IMPORT-001` -> M5; `GAP-SEC-001` -> M5;
  `GAP-SEC-002` -> M5; `GAP-PRODUCT-001` -> M5;
  `GAP-PRODUCT-002` -> M5.
- `GAP-PRODUCT-003` -> M6; `GAP-BENCH-001` -> M6;
  `GAP-EVIDENCE-001` -> M6.

There are 20 consolidated gaps, 19 with an Alpha closure milestone, and 19
Alpha blockers. `GAP-ASSET-002` is explicitly deferred to POST_ALPHA.

### Continuous concerns and dependencies

Security, Product integration, acceptance/evidence, telemetry/economics,
currentness and CompletionGate authority remain cross-cutting concerns, not
additional milestones.

Hard conceptual dependencies are:

`M1 -> M3`, `M2 -> M3`, `M2 -> M4`, `M3 + M4 -> Product capability breadth`,
`M4 -> M6`, `M5 -> M6`, and `M1-M5 -> M6`.

Co-development overlaps are `M3 <-> M4`, `M2 <-> M3`, `M4 <-> M5` and
`M5 <-> M6`. These notes justify grouping only; they do not define the
canonical execution order of Point 15.

### Alternatives and disposition

- Four milestones: rejected as too coarse and authority-mixing.
- Six milestones: accepted as the minimum coherent grouping.
- Seven or eight milestones: rejected for fragmenting work that must be
  co-developed.

M3, M5 and M6 are intentionally large but remain coherent. No split or merge
is justified at this stage.

### Duplication prohibitions

Do not create a second Brain, CompletionGate, ledger/evidence system,
Minecraft Harness, BuildRunner, Product execution model, scheduler, benchmark
framework, Alpha Multi-Agent framework or security/tool policy.

This grouping is ready for Point 14. It does not assign `v0.10`, `v0.11` or
any other version, and it does not define Point 15.

## Point 14. Roadmap version assignment

Status: `ACCEPTED`

R85 audit verdict: `PD_AGENT_R85_VERSION_ASSIGNMENT_READY_WITH_CORRECTIONS`

The canonical roadmap closure-gate assignment is:

| Roadmap label | Primary closure milestone |
|---|---|
| `v0.10` | M1 - General Fabric Task Foundation |
| `v0.11` | M2 - Versioned Fabric Platform and Brain |
| `v0.12` | M3 - Alpha Fabric Capabilities and Assets |
| `v0.13` | M4 - Generalized Validation, Repair and Runtime |
| `v0.14` | M5 - Secure Product Alpha |
| `Alpha` | M6 - Alpha Acceptance and Release Candidate |

`v0.10` through `v0.14` identify the **primary closure gate** of each
milestone. They do not define a rigid waterfall and do not mean that all
related work can occur only inside that label. M3 and M4 remain co-development;
security, Product integration, acceptance/evidence, telemetry/economics,
currentness, CompletionGate authority and `(version, capability)` evidence
remain continuous concerns.

### Roadmap labels and package versions

The labels `v0.10` through `v0.14` are roadmap/milestone labels. They do not
replace or automatically change:

- Python package version: `0.1.0`;
- frontend package version: `0.1.0`;
- schema versions;
- benchmark, dataset or task versions;
- Minecraft/Fabric versions.

Package/software version evolution will be decided explicitly when required;
there is no artificial synchronization with roadmap labels.

### Alpha semantics

Alpha is not `v0.15`. No `v0.15` is introduced without a future decision and
real need. `v0.14 CLOSED/PASS` is not Alpha; after M5 closes, M6 must complete
the Alpha certification.

Alpha may be declared only after M6 satisfies its hard gates, including
Product E2E, held-out acceptance, advertised version-by-capability evidence,
three-version support evidence, security/resource gates,
repair/negative/adversarial gates, Managed Reference Configuration, frozen RC,
CompletionGate-authoritative campaign and valid Delivery/JAR.

### Preserved milestone meaning

Point 13 remains unchanged:

- M1: General Fabric Task Foundation;
- M2: Versioned Fabric Platform and Brain;
- M3: Alpha Fabric Capabilities and Assets;
- M4: Generalized Validation, Repair and Runtime;
- M5: Secure Product Alpha;
- M6: Alpha Acceptance and Release Candidate.

No gap is moved, split or fused, and no primary ownership changes.

### Rationale and scope boundary

R85 found no collision with previous PD Agent versions, no conflicting Git
tags, no prior Alpha=v1.0 commitment and no incompatible Alpha definition.
One conceptual milestone per primary closure gate is coherent, and no
evidence requires `v0.15` before Alpha. The labels do not invalidate
co-development or continuous concerns.

Point 14 does not define the technical dependency graph, implementation
batches, internal order, prerequisites, overlap schedule or critical path.
Those decisions belong to Point 15.

## Point 15. Alpha dependency graph and execution order

Status: ACCEPTED

Source audit: R87 - Dependency Graph & Execution Order Audit

Verdict: `PD_AGENT_R87_EXECUTION_ORDER_READY_WITH_CORRECTIONS`

Decision: `POINT_15_ACCEPTED`

This point defines dependency semantics and execution order only. It does not
implement a milestone, create a new milestone, or start Point 16.

### Closure gate order

The canonical closure gates remain:

`v0.10 / M1 CLOSED/PASS` -> `v0.11 / M2 CLOSED/PASS` ->
`v0.12 / M3 CLOSED/PASS` -> `v0.13 / M4 CLOSED/PASS` ->
`v0.14 / M5 CLOSED/PASS` -> `PD Agent Alpha`.

Each gate owns the closure of its primary milestone. This is a closure order,
not a technical waterfall: foundations and continuous concerns belonging to
later milestones may begin earlier when required.

### Hard dependencies

- M1 usable is prerequisite for serious M3 breadth.
- M2 platform support sufficient for a target is prerequisite for claiming
  that target's capability.
- Early M4 validation foundation is prerequisite for serious M3 breadth.
- Real M3 capability slices are necessary to generalize and close M4.
- M3 and M4 contracts and capability evidence are necessary for M5 Product
  breadth closure.
- M4 CLOSED/PASS and M5 CLOSED/PASS are both prerequisites for M6.
- M1-M5 CLOSED/PASS are prerequisites for Alpha certification.

M1 has no hard dependency on M2 CLOSED or M4 CLOSED. M1 may close its
  planner, schema, composition, dependency representation, requirement
  decomposition, and validation-requirement contracts through deterministic
  tests and representative composition on the existing foundation. The
  minimum evidence compatibility observed by R87 must not become a circular
  M1 -> M2/M4 -> M1 closure dependency.

### Early foundations

Before serious M3 breadth, the project must have:

1. M1 usable planner/composition foundations.
2. M2 minimum platform foundations: Support Registry, version-aware
   bootstrap/template, project identity, per-target KnowledgeEnvironment,
   Fabric/Loom/API/mappings adapters, and leakage controls.
3. Early M4 foundations: productive 1-to-N validation, structural artifact
   expectations, parameterized probes, normalized observations, and
   CompletionGate/currentness integration.
4. Security guardrails appropriate to every new execution path.

These foundations must not be deferred until v0.13 or v0.14.

### M3/M4 co-development

The required capability-slice loop is:

`capability slice` -> `artifact expectations` -> `validator/probe` -> `build`
-> `runtime/Harness evidence when applicable` -> `repair/revalidation when
applicable` -> `CompletionGate` -> `next capability slice`.

M3 must close MUST_ALPHA breadth, assets, and capability/version-specific
evidence. M4 must subsequently close generalized, parameterized, reusable,
multi-version N validation/repair/runtime foundations. M3 and M4 therefore do
not mean implementing all capabilities first and validating everything at the
end; v0.12 may close before v0.13 without turning M4 into post-hoc QA.

### Multi-version strategy

1. Use validated 1.21.11 as the initial baseline for common abstractions.
2. Introduce 26.1 early, before substantial M3 breadth, because it is the
   first MODERN_UNOBFUSCATED boundary.
3. Make the first cross-family test a simple, parameterized, composable
   capability through request -> plan -> mutation -> build -> artifact ->
   validation on both 1.21.11 and 26.1.
4. Introduce 26.2 during M2/M3 and before M3 closure.
5. Keep one conceptual capability with version-aware adapters and
   expectations where necessary.
6. Treat `(version, capability)` as the unit of support and evidence.

Do not implement all capabilities in 1.21.11 and port them at the end.

### Continuous concerns and sequencing

Security, Product integration, Acceptance/Evidence, Telemetry/Economics,
Currentness, and CompletionGate authority are transversal concerns, not new
milestones.

Security guardrails must precede relevant execution paths: protected-path and
workspace boundaries, archive validation, imported-Gradle prohibition until
trust/isolation, child-environment policy, provider-secret sanitization,
timeouts, cleanup, resource bounds, duplicate-execution protection, and
cancel/reconciliation foundations before Product exposure. No milestone may
introduce a known-insecure path with a promise to fix it in v0.14.

Product integration is incremental: M1 request/capability status and honest
unsupported rejection; M2 project identity, target version, and compatibility;
M3 composed capabilities, assets, and meaningful support states; M4
validation, repair, currentness, and CompletionGate projection; M5 New/Import/
Continue, trust/isolation, intervention, cancel, recovery, History, Delivery,
JAR, and Product Alpha breadth. M5 does not start Product from zero.

Acceptance/evidence hooks are incremental: M1 schemas/requirement IDs/scenario
metadata; M2 version/project/bootstrap manifests; M3 capability/composition
scenarios, assets, and `(version, capability)` evidence; M4 validation,
repair, runtime, artifact, and CompletionGate evidence; M5 Product E2E and
security/recovery hooks; M6 RC freeze, held-out campaign, Managed Reference
Configuration, and certification. M6 must not discover fundamental M1-M5
failures for the first time.

### Internal technical path

`M1 planner/composition` -> `M2 platform/Brain/bootstrap baseline` +
`early M4 validation foundation` -> `M3 <-> M4 capability/validation slices`
-> `M4 generalized validation/repair/runtime closure` -> `M5 secure Product
closure` -> `M6 frozen RC + held-out certification`.

M1 and M2 may overlap, as may M2 and early M4. M3 and M4 are iterative.
Product, Security, and Acceptance evolve throughout the applicable work.

### Parallelism and anti-patterns

Conceptually parallel work includes M1 <-> M2, M2 <-> early M4, M3 <-> M4,
M3/M4 <-> Product integration, M1-M5 <-> acceptance hooks, and Security
guardrails alongside applicable execution areas. This does not require
multiple agents; Codex may execute sequentially while preserving these
semantics.

Prohibited ordering includes: M1 then all M3 then M4; late porting from
1.21.11; deferring Security or Product until M5; deferring acceptance hooks
until M6; claiming support without `(version, capability)` evidence; declaring
Alpha because v0.14 closed; or creating parallel frameworks for sequencing.

Mitigations are small vertical slices, validator/probe per capability, early
26.1 and pre-closure 26.2, guardrails before new execution paths, incremental
Product projections, incremental evidence scenarios, explicit contracts/
manifests/identities/Gate, and verifiable boundary-sized commits.

### Per-gate conditions

- **v0.10 / M1:** starts from v0.9 contracts/runtime; closes general
  planner/schema/composition/requirements/validation requirements; makes no
  Alpha breadth, full multi-version, or Alpha claim.
- **v0.11 / M2:** may start while M1 progresses; closes versioned Platform,
  Brain, and New Project bootstrap for M2 Alpha targets; makes no full
  MUST_ALPHA breadth claim.
- **v0.12 / M3:** starts with usable M1, sufficient M2 target support, early
  M4 foundation, and security guardrails; closes MUST_ALPHA breadth, assets,
  and required version/capability evidence; does not close generalized
  validation, Product Alpha, or certification.
- **v0.13 / M4:** starts from real capability slices; closes generalized,
  reusable, multi-version N validation, ArtifactValidator, probes, Harness,
  repair/runtime, and CompletionGate authority; does not close Product Alpha
  or certification.
- **v0.14 / M5:** starts from stable backend capability/version contracts;
  closes New/Import/Continue, trust/isolation/resources, Product Alpha
  breadth, and recovery/cancel requirements; does not certify Alpha.
- **Alpha / M6:** starts after M1-M5 CLOSED/PASS and RC freeze; closes held-out
  Product E2E, version-by-capability evidence, security, repair/adversarial
  validation, Managed Reference Configuration, Delivery/JAR, and the final
  CompletionGate-authoritative campaign. It makes no claim outside the
  announced support matrix.

## Publication record

Status: `PD_AGENT_ROADMAP_TO_ALPHA_CANONICAL`

Publication record: R90

Canonical roadmap scope:

`PD Agent v0.9 CLOSED/PASS` -> `v0.10` -> `v0.11` -> `v0.12` -> `v0.13`
-> `v0.14` -> `PD Agent Alpha`.

Milestone closure mapping:

- `v0.10` -> M1 - General Fabric Task Foundation
- `v0.11` -> M2 - Versioned Fabric Platform and Brain
- `v0.12` -> M3 - Alpha Fabric Capabilities and Assets
- `v0.13` -> M4 - Generalized Validation, Repair and Runtime
- `v0.14` -> M5 - Secure Product Alpha
- `Alpha` -> M6 - Alpha Acceptance and Release Candidate

This roadmap is the canonical Direction authority for the path from v0.9 to
PD Agent Alpha. Each milestone must subsequently follow DESIGN -> RFC -> IMP
-> Codex pre-implementation audit -> implementation -> validation -> closure.
The roadmap does not replace milestone-specific DESIGN/RFC/IMP documents.
Future changes require an explicit proposal, justification, evidence and
roadmap/checklist update; no decision may be changed silently.
