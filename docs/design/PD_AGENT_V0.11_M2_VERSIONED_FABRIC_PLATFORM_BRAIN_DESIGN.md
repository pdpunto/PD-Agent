# PD Agent v0.11 - M2 Versioned Fabric Platform and Brain

Status: `DESIGN - READY FOR RFC`

Milestone: `PD Agent v0.11 - M2 Versioned Fabric Platform and Brain`

## 1. Background and Baseline

M1 is closed with `PD_AGENT_V0.10_M1_CLOSED_PASS` at
`eb4d6e65b09e8716c3fb3103985ba2a81b794322`. The accepted M1 foundation
provides a general capability registry/planner, Fabric contract expansion and
the existing Product/runtime/evidence path.

The current repository already contains Fabric inspection, Brain environment
and retrieval abstractions, frozen knowledge packs, bootstrap, build,
artifact, runtime and completion authorities. The missing product authority is
the answer to: "Which concrete Fabric platform does PD Agent support, and
under which profile?"

This DESIGN addresses roadmap gaps `GAP-VERSION-001`, `GAP-BRAIN-001` and
`GAP-PROJECT-001`. It does not claim that any of those gaps is closed.

## 2. Problem and Product Outcome

Current workspace facts, historical defaults and Brain compatibility are
related but are not the same authority. M2 establishes one declarative support
boundary that resolves the current workspace to a known Fabric platform
profile, or fails closed when support cannot be established.

The product outcome is a version-aware path:

`workspace inspection -> support resolution -> current Fabric contract ->`
`compatible Brain environment/pack -> existing Product runtime`

Only a resolved `SUPPORTED` platform may continue to Product execution.

## 3. Scope

M2 covers:

- a single `FabricSupportRegistry` authority;
- declarative platform profiles and resolution outcomes;
- the `UNOBFUSCATED` and `OBFUSCATED_REMAPPED` platform families;
- version-aware Product preflight and Brain environment selection;
- platform/template-aware project bootstrap;
- imported-project support resolution without bootstrap metadata;
- current workspace truth and historical provenance separation;
- offline evidence for two distinct platforms and the legacy baseline.

M2 reuses M1 capabilities and the existing runtime rather than expanding the
capability catalog.

## 4. Platform Targets

The target families are:

| Target | Role | Mapping family |
|---|---|---|
| Minecraft 26.2 | Primary target | `UNOBFUSCATED` |
| Minecraft 26.1 family, initially 26.1.2 | Secondary target | `UNOBFUSCATED` |
| Minecraft 1.21.11 | Legacy baseline | `OBFUSCATED_REMAPPED` |

These are target profiles, not automatic support claims. A target is
`SUPPORTED` only after PD Agent has sufficient implementation and validation
evidence. Official existence of a Minecraft/Fabric release is not enough.

M2 must not assume that modern and legacy platforms share mappings, build
semantics or version adapters.

## 5. Core Concepts

### FabricPlatformProfile

A declarative support profile identifies a concrete platform and its evidence.
It includes, at minimum:

- stable platform identity and schema version;
- Minecraft, Loader, Fabric API and Loom versions;
- Java version;
- mappings mode;
- mappings namespace and version where applicable;
- support status;
- provenance and validation evidence.

### FabricPlatformResolution

Resolution is the typed result of comparing current workspace facts with the
registry. Its minimum outcomes are `SUPPORTED`, `UNSUPPORTED`, `UNKNOWN` and
`CONFLICT`. A resolution contains enough profile/evidence context for the
next Product and Brain boundaries without becoming an execution object.

### FabricProjectTemplate

A template is the minimal declarative input needed for deterministic project
creation together with a selected platform. It is not a general project
generator, package manager or executable command store.

## 6. Authority Boundaries

The authorities remain separate:

- `FabricInspector` and `ProjectInspector` report what exists in the current
  workspace.
- `FabricSupportRegistry` reports what PD Agent supports.
- `KnowledgeEnvironment` describes the environment for which Brain knowledge
  is valid.
- `KnowledgeEnvironmentResolver` and `KnowledgeService` select and validate
  compatible knowledge.
- `FabricTaskContract` remains the authoritative task contract.
- M1 `CapabilityRegistry` and `CapabilityPlanner` remain data-only planning
  authorities.
- `FabricNormalOrchestrator`, `AgentRuntime`, `TaskProgressLedger`,
  `ArtifactValidator`, `MinecraftTestSpec` and `CompletionGate` retain their
  existing authorities.

No authority may infer support merely from a default or from another
authority's historical record.

## 7. Support Resolution

Resolution compares the current inspected platform facts against registered
profiles and their evidence. A unique compatible profile yields `SUPPORTED`.
Missing or insufficient facts yield `UNKNOWN`; a known but unsupported
combination yields `UNSUPPORTED`; contradictory detected facts or profiles
yield `CONFLICT`.

Only `SUPPORTED` is executable. The other outcomes produce a structured,
human-readable failure before provider use, `ExecutionRecord` creation or
dispatch.

`PinnedFabricVersions`, `YarnKnowledgeSource` defaults,
`FabricApiKnowledgeSource` defaults and similar constants may remain as
compatibility adapters. They are not productive support authorities.

## 8. Product Preflight and Contracts

Every Product execution reinspects the workspace and resolves the current
platform before provider dispatch. The generated `FabricTaskContract` receives
the resolved current environment and its contract fingerprint remains the
authoritative identity.

Unsupported, unknown or conflicting resolution is fail-closed before provider
use and before Product execution persistence. Existing M1 capabilities and
planner are reused unchanged across platform profiles; M2 does not create a
versioned capability registry or a planner fork.

## 9. Brain and Knowledge Compatibility

The resolved platform is converted cleanly into the existing
`KnowledgeEnvironment`. Brain selection may use version-aware retrieval,
cache and frozen pack/source selection, but every selected source remains
responsible for its own compatibility checks.

The Support Registry does not replace pack identity, source compatibility or
knowledge leakage protections. An incompatible or wrong-version pack/source
must be rejected, not silently downgraded or treated as current.

Legacy 1.21.11 knowledge must not leak into 26.1 or 26.2, and modern knowledge
must not be used for the legacy mapping family without compatible evidence.

## 10. Bootstrap and Templates

`FabricBootstrap` is reused and extended at its existing boundary. New project
creation is conceptually based on:

`platform + template`

The selected template and platform determine deterministic project metadata;
they do not become a second runtime or an executable command registry.
`PinnedFabricVersions` is demoted from primary authority. Bootstrap manifests
are useful provenance, but current execution truth is always re-inspected.

## 11. New and Imported Projects

A newly bootstrapped project should reinspect to the selected profile when it
has not been modified. Its project identity is independent of platform
identity.

An imported project does not require a bootstrap manifest. It follows:

`workspace -> inspection -> support resolution`

If the project is later edited or its versions change, historical platform
data remains provenance only and cannot authorize the next execution.

## 12. Currentness and Provenance

The governing rule is:

`historical platform provenance != current platform truth`

Current platform truth is derived from current workspace inspection plus
current support resolution. Platform provenance may explain how a project was
created or previously validated, but it cannot override current facts.

Existing contract, source, artifact and evidence currentness authorities are
reused. M2 does not create a second currentness system.

## 13. Build, Runtime and Harness Boundaries

`GradleBuildRunner` remains shared and essentially version-agnostic. M2 does
not create a runner per version.

`MinecraftTestSpec` and the current Harness boundary are reused. M2 ensures
that a supported platform's correct versions and mapping family reach those
boundaries when applicable; it does not generalize Harness/probes or runtime
validation 1-to-N.

M2 closure must demonstrate offline:

`Platform A -> resolution -> M1 capabilities -> contract A -> compatible Brain A`

and the same path for Platform B, while preserving a correctly representable
1.21.11 legacy baseline.

## 14. Security Constraints

- Registry and profiles are declarative and have no execution authority.
- Planner data remains data-only.
- Product preflight remains fail-closed.
- `ToolExecutor` and `SecurePathResolver` remain filesystem authorities.
- Brain remains separate from execution authority.
- Profiles, templates and provenance contain no secrets.
- The registry stores no commands, executable processes or executable paths.
- Imported-project trust and full isolation remain M5 scope.
- `GAP-SEC-001` is not closed by M2.

## 15. Failure Behavior

The following must be observable and fail closed before provider/runtime use:

- unsupported platform;
- unknown platform or incomplete detection;
- conflicting detected versions;
- wrong or incompatible Brain pack/source;
- insufficient evidence for a `SUPPORTED` profile.

Failures must preserve safe diagnostics without exposing secrets or inventing
support. No Product success, delivery or completion may be projected from a
non-supported resolution.

## 16. Non-Goals

M2 does not include:

- a new runtime, AgentRuntime, planner, Brain, DAG, database or distributed
  registry;
- a cloud version service, package manager or automatic network resolver;
- the full Alpha capability catalog or general asset toolkit;
- generalized Harness/probes or runtime validation 1-to-N;
- version-by-capability exhaustive certification;
- automatic mod migration between Minecraft versions;
- Paper, NeoForge, Velocity or Multi-Agent support;
- complete M5 import trust/isolation;
- M6 held-out release certification.

## 17. Roadmap Gap Mapping

| Gap | M2 response | M2 closure claim |
|---|---|---|
| `GAP-VERSION-001` | common versioned support authority and resolution | Not closed until evidence passes |
| `GAP-BRAIN-001` | compatible environment and pack/source selection | Not closed until compatibility evidence passes |
| `GAP-PROJECT-001` | platform/template bootstrap and imported resolution | Not closed until project evidence passes |

## 18. Acceptance Criteria

1. Exactly one declarative support authority exists.
2. A supported workspace resolves deterministically to one profile.
3. Unsupported, unknown and conflicting workspaces block before execution and
   provider dispatch.
4. 26.1+ and 1.21.11 represent their distinct mapping/platform models.
5. M1 capabilities use the same planner and registry model without version
   forks.
6. The current resolved platform supplies the contract environment.
7. Brain receives a compatible environment for the current platform.
8. Incompatible frozen packs/sources are rejected.
9. Bootstrap can select a platform and template deterministically.
10. An unchanged bootstrapped project reinspects to the selected profile.
11. An imported project resolves without bootstrap metadata.
12. Manual version changes invalidate historical trust and trigger resolution.
13. `GradleBuildRunner` remains shared.
14. No second runtime, Brain, planner, ledger or CompletionGate exists.
15. Two distinct platforms pass offline through resolution, M1 planning,
    contract generation and compatible Brain selection.
16. The 1.21.11 legacy baseline remains representable.
17. Every required fail-closed case has verifiable behavior.
18. The existing full regression remains passing.

## 19. Risks

- registry entries become implicit defaults instead of evidence-backed support;
- modern and legacy mapping semantics are accidentally conflated;
- historical bootstrap metadata overrides current inspection;
- Brain compatibility is assumed from platform support alone;
- M1 capability logic forks by version;
- imported projects receive weaker safety checks;
- M2 absorbs M3 catalog or M4 runtime scope prematurely.

## 20. Explicit Deferments

M3 owns capability breadth, composition breadth and deterministic assets.
Early M4/M4 owns generalized validation, probes, Harness and runtime
validation. M5 owns imported-project trust/isolation and broader Product
security/recovery. M6/Alpha owns held-out acceptance and exhaustive
version-by-capability certification.

## 21. Open Questions for RFC

The RFC must decide the exact profile schema, registry loading authority,
evidence sufficiency rules, conflict precedence, bootstrap template metadata
and the compatibility boundary between support resolution and knowledge-source
selection. Those are implementation decisions, not additional DESIGN scope.
