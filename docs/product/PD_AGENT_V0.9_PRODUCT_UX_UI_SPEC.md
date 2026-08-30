# PD_AGENT_V0.9_PRODUCT_UX_UI_SPEC

Status: `APPROVED BY 00`

Milestone: `PD Agent v0.9 - Internal Web/UI Integration Preview`

Baseline: `PD Agent v0.8 - CLOSED / PASS`

UI scope: `ALPHA_ALIGNED_FUNCTIONAL_PREVIEW`

## 1. Scope v0.9

v0.9 is an internal functional Web/UI preview over the real v0.8 runtime.
It exposes the approved Alpha structure with the minimum functional UX and a
simplified visual representation.

## 2. TARGET ALPHA UI

The target is the complete Alpha UI. v0.9 previews its structure, hierarchy,
navigation and functional states without claiming final visual completion.

## 3. Classification Matrix

Backend-ready capabilities are exposed through safe adapters. Missing runtime
capabilities are explicit v0.9 work. UI-only details remain presentation work;
final polish is Alpha-deferred.

## 4. User Model

The primary user submits a natural-language request for a persistent project.
Provider, model, API keys, tokens and internal evidence are not normal user
concepts.

## 5. Information Architecture

The information architecture is organized around Projects, executions/tasks,
current status, repair state, success/failure, artifact delivery and Details.

## 6. Navigation

The preview preserves the Alpha navigation hierarchy, including Home,
Projects, Project details, Execution details, Settings and contextual return
paths.

## 7. Complete v0.9 User Flows

The functional flow is: receive request, associate project, start real runtime,
show real milestones, expose repair or failure honestly, validate success and
make the valid artifact locatable or downloadable.

## 8. Home Specification

Home presents the product identity, project entry point, natural-language task
entry and recent relevant work without fabricated progress or capabilities.

## 9. Execution Specification

Execution presents a comprehensible task lifecycle backed by real RunState and
events. Technical logs are available through Details, not used as the primary
UX.

## 10. Repair Specification

Repair is shown only when a real repairable failure, Semantic Repair cycle or
runtime reconciliation exists in evidence. The UI must distinguish normal
execution, repair, blocked and terminal failure.

## 11. Intervention Specification

The structure reserves an intervention state for cases where runtime requires
human input. v0.9 must not claim this capability unless the backend provides a
safe pause, response and continuation lifecycle.

## 12. Success / JAR Specification

Success is shown only after authoritative validation and CompletionGate
evidence. The resulting current valid JAR is locatable or downloadable through
an approved safe delivery path.

## 13. Failure Specification

Terminal failures are presented in human terms with a useful reason and next
disposition. Raw tracebacks and provider internals are not the primary UX.

## 14. Details / Evidence Specification

Details exposes real task, project, state, changes, build, repair, runtime,
observations, artifact, identifiers, hashes and evidence references. It never
exposes chain-of-thought or secrets.

## 15. Projects / Tasks Specification

PROJECT is a persistent mod/workspace context. TASK is a concrete request on
that project. The UI must not conflate project identity with one execution or
one task.

## 16. History / Deliveries Subset

The preview shows the minimum useful history: prior tasks, final states,
dates, artifacts and relevant evidence. It does not promise a complete product
history index until that persistence exists.

## 17. Settings Subset

Settings contains only real user-relevant configuration. Operational limits,
provider credentials and internal paths remain hidden or administrative.

## 18. Managed AI Boundary

The product boundary is user -> PD Agent -> result. Provider and model choice
are implementation/configuration concerns, not the primary Managed UX.

## 19. Credits Boundary

v0.9 does not implement credits, prices, checkout, billing or fictitious
usage claims.

## 20. Component Inventory

The component inventory includes application shell, navigation, project list,
task composer, execution view, milestone/status view, repair/failure view,
success/artifact view, Details, history and Settings.

## 21. Component States

Components must represent loading, ready, running, investigating, editing,
building, testing, verifying, repairing, blocked, failed and succeeded only
when supported by real runtime data.

## 22. Modal / Layer Behavior

Modal and layer behavior must preserve back, close, Escape, focus, scroll and
stacking semantics. A modal must not hide a required failure or fabricate an
intervention capability.

## 23. Visual Base Requirements

The visual base must be recognizably PD Agent, preserve the approved
composition and density, and use simplified but intentional visual treatment.

## 24. Responsive Requirements

The preview must preserve hierarchy and usable execution/details flows across
the supported desktop and mobile-sized layouts.

## 25. Accessibility Requirements

Keyboard navigation, focus visibility, semantic labels, readable contrast,
usable scrolling and coherent Escape/close behavior are required.

## 26. Alpha-Deferred Visual Assets / Polish

Final art, cinematic assets, advanced animation, effects and visual polish are
deferred to Alpha. Their absence must not be replaced by fake product
capabilities.

## 27. Explicit Non-Goals

No final Alpha UI, fake runtime, simulated progress, fictitious billing,
provider marketplace, Multi-Agent system, new loader support or architecture
redesign is included in v0.9.

## 28. Open Questions

The later DESIGN must resolve the minimum persistence/index boundary for
Projects and deliveries, the safe UI execution handle, cancellation policy,
intervention lifecycle and artifact delivery mode. These are not silently
assumed to exist.

## 29. Product Acceptance Criteria - v0.9

- **AC-01:** Home structurally aligned with Visual Handoff.
- **AC-02:** Request through natural language.
- **AC-03:** Correct project association when applicable.
- **AC-04:** Action starts the real runtime.
- **AC-05:** Only states/progress backed by real data.
- **AC-06:** No simulated percentages/progress.
- **AC-07:** Execution understandable without logs.
- **AC-08:** Repair shown only when it actually occurs.
- **AC-09:** Intervention may request human input when runtime requires it.
- **AC-10:** Terminal failure does not use traceback/terminal output as primary UX.
- **AC-11:** Success asserts only evidence-backed verifications.
- **AC-12:** Valid JAR is functionally downloadable or locatable.
- **AC-13:** Details exposes real human-relevant evidence.
- **AC-14:** Technical evidence does not expose chain-of-thought.
- **AC-15:** Projects correctly represent persistent project != task.
- **AC-16:** Another request can be started from Project.
- **AC-17:** Minimum history retrieves relevant tasks/results.
- **AC-18:** Settings contains only real configuration.
- **AC-19:** Providers/models/API keys/tokens are not normal Managed UX.
- **AC-20:** No fictitious credits/prices/checkout.
- **AC-21:** Projects/Settings/Details preserve context.
- **AC-22:** Back/close/Escape/focus/scroll/stacking are coherent.
- **AC-23:** Basic keyboard navigation is functional.
- **AC-24:** PD Agent visual identity is recognizable.
- **AC-25:** Structure can evolve toward Alpha without fundamental redesign.

Final gate: this is not the finished Alpha UI, but it is clearly PD Agent,
works for real, and can evolve toward Alpha without fundamental redesign.

## 30. Evolution Path v0.9 -> Alpha

Alpha extends this structure with final visual assets, polish and broader
product maturity. v0.9 must not create a temporary information architecture
that would require replacing the approved Alpha structure.

## 31. Mapping to Approved Visual References

Primary visual reference: `LAMINA 1 de integracion de Fase 8`.

It governs composition, aesthetics, density, Minecraft treatment, distribution,
lighting and overall feel. State-specific UX decisions from Phases 1-7 take
precedence over accidental details of that reference. Images need not be
stored when they are not available as repository assets; assets must not be
invented.

## Final Product Direction

`ALPHA STRUCTURE`

`REAL RUNTIME STATE`

`MINIMUM FUNCTIONAL UX`

`SIMPLIFIED VISUAL REPRESENTATION`

Not included:

`FINAL ART/POLISH`

`FAKE PRODUCT CAPABILITIES`
