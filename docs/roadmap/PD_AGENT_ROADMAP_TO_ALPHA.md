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

R67 established that the proposed Ruby Tools task is outside the current productive capability envelope. R68 confirmed that the main generalization boundary is the productive request/capability/contract resolution layer, while much of the underlying runtime infrastructure is already reusable.

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
- supporting multiple Fabric/Minecraft versions inside an Alpha support range still to be defined;
- passing diverse benchmarks without task-specific hardcodes.

Alpha does **not** mean:

> PD Agent can create every Minecraft mod imaginable.

Alpha means:

> PD Agent is genuinely useful for creating a meaningful variety of basic/intermediate Fabric mods without programming.

Ruby Tools should eventually become a normal task inside the Alpha envelope, but it will be only one acceptance case among many.

## 3. Audited post-v0.9 capability state

Status: `AUDITED — R68`

### Productive infrastructure already present

- Product project creation and continuity over existing workspaces;
- Minecraft Brain retrieval, selection, injection and provenance;
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
7. Single-version Fabric/Minecraft support.
8. No general workspace/mod bootstrap from a template.
9. Brain knowledge does not automatically become an executable contract.
10. Benchmark infrastructure measures capabilities but does not itself make them productive.

R68 confirms R67:

- arbitrary items are not productively exposed;
- swords are not supported productively;
- arbitrary new mod identity generation is not supported;
- binary PNG read/write is not supported;
- deterministic texture recoloring is not supported.

The correct interpretation is not that the runtime lacks all reusable primitives. The limiting boundary is predominantly the productive request → planning/capability → requirements/validation path.

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
4. [ ] Definir estrategia de assets: texturas, modelos, sonidos y generación visual
5. [ ] Definir estrategia multi-versión Minecraft/Fabric
6. [ ] Definir evolución necesaria del Minecraft Brain
7. [ ] Definir evolución de validación, Test Harness y CompletionGate
8. [ ] Evaluar dónde Multi-Agent aporta valor real
9. [ ] Definir requisitos de seguridad, compatibilidad y rendimiento para Alpha
10. [ ] Definir requisitos Product/UI restantes para Alpha
11. [ ] Definir benchmarks y Alpha Acceptance Suite
12. [ ] Inventariar gaps v0.9 → Alpha
13. [ ] Agrupar gaps en milestones mínimos
14. [ ] Asignar versiones v0.10 → Alpha
15. [ ] Definir dependencias y orden de ejecución
16. [ ] Publicar Roadmap to Alpha canónico

## 7. Assets strategy

Status: `PENDING / NOT YET DECIDED`

## 8. Multi-version Minecraft/Fabric strategy

Status: `PENDING / NOT YET DECIDED`

## 9. Minecraft Brain evolution

Status: `PENDING / NOT YET DECIDED`

## 10. Validation / Test Harness / CompletionGate evolution

Status: `PENDING / NOT YET DECIDED`

## 11. Multi-Agent decision

Status: `PENDING / NOT YET DECIDED`

## 12. Alpha security / compatibility / performance requirements

Status: `PENDING / NOT YET DECIDED`

## 13. Product/UI requirements remaining for Alpha

Status: `PENDING / NOT YET DECIDED`

## 14. Benchmarks and Alpha Acceptance Suite

Status: `PENDING / NOT YET DECIDED`

## 15. Gap inventory v0.9 → Alpha

Status: `PENDING / NOT YET DECIDED`

## 16. Milestone grouping

Status: `PENDING / NOT YET DECIDED`

## 17. Version assignment v0.10 → Alpha

Status: `PENDING / NOT YET DECIDED`

## 18. Dependency/order plan

Status: `PENDING / NOT YET DECIDED`

## 19. Final roadmap publication

Status: `PENDING / NOT YET DECIDED`
