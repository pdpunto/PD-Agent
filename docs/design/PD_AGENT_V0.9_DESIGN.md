# PD_AGENT_V0.9_DESIGN

Status: `APPROVED BY 00`

Milestone: `PD Agent v0.9 — Internal Web/UI Integration Preview`

Baseline: `986ea0078c6c4a7fd3b054c19c93ccba7b9854be`

Scope: `ALPHA_ALIGNED_FUNCTIONAL_PREVIEW`

## Authorities

1. `docs/product/PD_AGENT_V0.9_PRODUCT_UX_UI_SPEC.md`
2. `V0_9_PRE_DESIGN_AUDIT_READY → ACCEPTED`
3. `V0_9_TECHNICAL_SCOPE_BOUNDARY_READY → ACCEPTED`
4. `PD_AGENT_V0.9_DESIGN → ACCEPTED` by 00 Dirección

## 1. Purpose

v0.9 converts PD Agent into a functional Web preview over the real productive runtime while preserving the conceptual structure approved for Alpha. It is not a mockup, a fake runtime, a replacement runtime, or the finished Alpha UI.

## 2. Product Outcome

The user can open PD Agent, create or reopen a Project, submit a natural-language Task, start a real Execution, immediately recover UI control, observe evidence-backed progress, navigate elsewhere and return, observe real repair or failure, receive authoritative success, download or locate the valid current JAR, inspect evidence, and start another Task on the same Project.

## 3. User Model

The primary user works with persistent Minecraft mod Projects through natural-language requests. Projects, Tasks, Executions, results and JAR deliveries are normal user concepts. Providers, models, API keys, token mechanics, internal paths and private reasoning are not normal user concepts.

Normal product boundary: `User → PD Agent → validated result`.

## 4. Scope

v0.9 includes:

- local Web application access;
- functional Home, Projects, Project, Execution, Details and Settings structure;
- natural-language Task creation;
- real non-blocking productive execution;
- evidence-backed progress projection;
- real repair, success and failure presentation;
- persistent Project identity and continuity;
- minimum Task/Execution history;
- safe artifact/JAR delivery;
- human and technical evidence views;
- local Web security baseline;
- responsive functional layouts;
- accessibility baseline;
- Alpha-compatible product semantics and navigation.

## 5. Explicit Non-Goals

v0.9 does not include:

- final Alpha art or polish;
- fake runtime or simulated progress;
- general cancellation;
- general workflow resume;
- real human-intervention lifecycle;
- distributed workers or job platform;
- cloud persistence;
- SaaS accounts/authentication;
- collaboration;
- billing or credits;
- commercial Managed backend infrastructure;
- provider/model selection UX;
- complete Settings product;
- project branching or version manager;
- advanced delivery/release management;
- final mobile product;
- Multi-Agent;
- Paper, NeoForge or Velocity support.

## 6. System Boundary

Conceptually:

`Browser → Local Web/Application Boundary → Thin Product Services → productive PD Agent runtime → RunState / RunEvent / RunStorage → projections / evidence / delivery`

The Web layer exposes and coordinates the existing product runtime. It does not reimplement AgentRuntime, FabricNormalOrchestrator, Brain, Build & Debug, Semantic Repair, Minecraft validation, CompletionGate, ToolExecutor or SecurePathResolver.

Invariant: `RunState = only execution state machine`.

Execution handles, Web state and progress projections must not become competing lifecycle authorities.

## 7. User-Visible Conceptual Model

`PROJECT` = persistent mod/workspace product context.

`TASK` = one concrete human request on a Project.

`EXECUTION` = one productive attempt to perform a Task.

`DELIVERY` = validated artifact produced by a successful Execution.

These concepts must remain understandable without exposing runtime implementation details.

## 8. Project / Task / Execution / Delivery Semantics

### Project

A Project has stable product identity, a human-recognizable name, an authorized workspace relationship, creation/update metadata, Tasks and Deliveries. Its identity survives valid workspace mutations.

Invariant: `Project identity != workspace fingerprint`.

### Task

A Task is a concrete natural-language request belonging to one Project. A later request on the same mod is another Task, not automatically another Project.

### Execution

An Execution is a concrete productive attempt for a Task. It has stable identity and maps unambiguously to its Task, Project and underlying productive run.

### Delivery

A Delivery references a validated artifact associated with the correct successful Execution. It does not redefine artifact validity or currentness.

Relationship: `Project → Tasks → Executions → Deliveries`.

## 9. Primary User Flows

### Existing Project

`Projects → Project → New Task → natural request → start → Execution → result`.

### New Project

`Home/Projects → create or register Project → authorized workspace → initial Task → Execution`.

### Running Execution

`start → regain UI control → observe → navigate elsewhere → return → recover current real state → terminal result`.

Navigating away does not cancel the Execution.

### Previous Work

`Project → Task history → Execution → result → Details / Delivery when available`.

## 10. Home Behavior

Home presents PD Agent identity, Project entry points, natural-language work entry where context is sufficient, and recent relevant work. It must not fabricate progress, credits, provider state, unsupported capabilities or fake activity.

Its composition and hierarchy remain aligned with the approved Visual Handoff and Product Spec.

## 11. Project Behavior

Project view exposes Project identity, safe workspace relationship, New Task, recent Tasks, execution outcomes and latest valid Delivery when available. Reopening a Project restores product continuity without redefining it from a mutable workspace fingerprint.

## 12. Execution Behavior

Starting a Task must not block the UI until runtime completion. The user receives a stable Execution representation and can observe it, navigate away, return, and obtain current state and final result.

The execution-facing Web/application wrapper is not a second state machine. RunState remains lifecycle authority.

## 13. Progress Behavior

Target human states, only when supported by real evidence:

- Entendiendo;
- Investigando;
- Editando;
- Compilando;
- Probando;
- Verificando;
- Reparando;
- Entregando.

Invariant: `UI progress = derived read-only projection`.

`runtime facts/events/evidence → UX projection`.

No time-based fake progress, invented percentages, fictional stages or independent persisted progress authority are permitted.

## 14. Repair Behavior

Repair is presented only when contractual evidence demonstrates a real diagnosis/correction/retry/revalidation path. The primary UX may describe this as `Corrigiendo un problema…`. Details may expose safe structured facts such as `failure → correction → rebuild/retry → validation`.

Private reasoning is never exposed.

## 15. Success Behavior

Success is authoritative, not cosmetic.

Invariant: `Success requires authoritative CompletionGate satisfaction`.

Required validation must also be satisfied. When a deliverable artifact is required, it must be VALID and current. Build success alone is insufficient. Artifact VALID alone is insufficient. The UI may assert only evidence-backed verification claims.

## 16. Failure Behavior

The UI distinguishes meaningful blocked, validation-failed and terminal-failure outcomes supported by runtime evidence. Failure presentation provides a human-understandable reason and safe next disposition where known. Raw traceback, terminal output and provider internals are not the primary failure UX.

## 17. Details / Evidence Behavior

### Layer 2 — Human Evidence

May present understandable facts about:

- requested change;
- changes made;
- build;
- repair;
- Minecraft validation;
- artifact;
- completion.

### Layer 3 — Technical Evidence

May safely expose:

- Project/Task/Execution/run identifiers;
- timestamps;
- changed files;
- validation summaries;
- observations;
- artifact hashes;
- evidence references;
- failure classification.

Never expose chain-of-thought, hidden reasoning, secrets, unrestricted provider payloads or unrestricted filesystem access.

## 18. History / Delivery Behavior

Minimum recoverable Project history includes previous Tasks, dates, Execution references, final states/results and Delivery references when present. Product history references authoritative runtime evidence rather than duplicating heavy logs/evidence.

`latest delivery` means latest authoritative valid Delivery, not merely the newest JAR found on disk.

## 19. Artifact / JAR Behavior

Primary delivery action: `SAFE WEB DOWNLOAD`.

Secondary internal-preview action: `LOCAL LOCATION / REVEAL`.

Invariant: `Artifact delivery requires VALID + current + correct ownership`.

Delivery additionally requires authoritative successful completion. Project/Task/Execution ownership must match. Browser-provided arbitrary filesystem paths are prohibited. A stale or invalid artifact must never be silently delivered as current.

## 20. Long-Run Execution Requirements

v0.9 requires:

- stable Execution identity;
- non-blocking start;
- observable current state;
- navigation-independent execution lifecycle;
- ability to return to a running Execution;
- structured final result/error;
- truthful degraded state when authoritative state cannot be obtained.

The exact background execution mechanism is reserved for RFC.

## 21. Persistence Requirements

Two authorities are preserved.

### Product metadata

Persists the minimum index/metadata needed for Projects, Tasks, Execution references, Deliveries, timestamps and product-facing final state.

### Runtime evidence

Invariant: `RunStorage remains runtime/evidence authority`.

Invariant: `Product persistence references runtime evidence; it does not duplicate it`.

Persistence must be versioned and recoverable, and relationships must fail safely when referenced data is missing or stale. A database is not required in v0.9. Exact schema and recovery/write mechanics are reserved for RFC.

## 22. Security Requirements

v0.9 requires:

- local-only exposure by default;
- no accidental LAN exposure;
- registered/authorized Project workspaces;
- no arbitrary browser filesystem paths;
- traversal rejection;
- preservation of SecurePathResolver;
- preservation of ToolExecutor;
- artifact download through trusted identities/references;
- secret redaction;
- safe evidence exposure;
- safe filename handling;
- bounded request/upload payloads;
- Host/Origin protection;
- CSRF protection when applicable.

localhost alone is not treated as a sufficient security boundary. SaaS/multi-user security is outside v0.9.

## 23. Provider Opacity

Invariant: `Provider/model/API key remain opaque to normal UX`.

Normal UX is `User → PD Agent → result`. Provider provisioning, model choice, credentials, operational limits and token mechanics remain administrative/internal configuration. v0.9 does not introduce billing, credits, provider selector, model selector or product API-key manager.

## 24. Settings Boundary

No mandatory USER_SETTING has been demonstrated for v0.9. The approved Settings location may remain in the Alpha-aligned structure, but functionality must not be invented merely to populate it. Provider/model/API credentials, runtime paths and operational limits remain administrative or hidden internal configuration.

## 25. Accessibility Requirements

Accessibility is functional scope, not final polish. v0.9 requires keyboard-operable navigation/actions, visible focus, semantic controls and labels, coherent modal focus, Escape/close behavior, usable scrolling, readable contrast, state not communicated only by color, and reduced-motion consideration when motion is present.

## 26. Alpha Alignment / Evolution Requirements

v0.9 is an accumulative functional skeleton for Alpha, not a temporary information architecture.

The following product contracts must survive conceptually into Alpha:

- Project;
- Task;
- Execution;
- Delivery;
- Execution identity;
- progress semantics;
- success/failure semantics;
- human vs technical evidence;
- Project history;
- artifact delivery;
- provider opacity;
- navigation hierarchy.

Technical implementation underneath may evolve without requiring fundamental redesign of these product concepts.

## 27. Failure / Degraded Behavior

If product metadata cannot be safely read, PD Agent must not invent Projects/history.

If execution evidence is unavailable or incomplete, the UI must not claim unsupported progress or success.

If an artifact is missing, invalid or stale, delivery is unavailable while historical execution facts remain truthful.

If runtime state becomes unavailable after dispatch, the UI represents the real known failure/unknown condition rather than fabricating success.

`REAL HUMAN INTERVENTION = DEFERRED`.

v0.9 does not implement `pause → human response → safe resume`. No accepted v0.9 Task may depend on human intervention during execution. AC-09 remains conditional on a future safe backend capability. The UI must not simulate `Necesito tu ayuda`.

`GENERAL CANCELLATION = DEFERRED`.

No fake Cancel action is permitted. Navigating away from Execution does not cancel it.

## 28. Data / Currentness Requirements

Every user-facing fact must have an identifiable authority. Examples:

- execution state → RunState / RunEvents;
- progress → derived projection from runtime facts/evidence;
- repair → repair evidence;
- success → CompletionGate and required validation;
- artifact availability → validated current artifact reference;
- history and Project identity → product catalog metadata.

Derived views may be cached, but stale cached state must not override authoritative state.

## 29. Testing / Validation Expectations

Later RFC/IMP must make it possible to prove:

- real Web/API → productive runtime integration;
- non-blocking execution start;
- stable Execution identity;
- progress backed by real RunState/events/evidence;
- Project continuity/reopen;
- another Task on an existing Project;
- minimum history recovery;
- real repair projection;
- truthful terminal failure;
- CompletionGate-backed success;
- valid/current JAR download and local location;
- stale/invalid artifact rejection;
- human and technical evidence projections;
- no secret or chain-of-thought leakage;
- traversal rejection;
- unauthorized workspace rejection;
- local Web security boundary;
- keyboard/focus/accessibility baseline;
- v0.8 regression preservation.

Fake-backend-only tests cannot establish final v0.9 PASS.

## 30. Acceptance Criteria Mapping

The Product/UX/UI Spec AC-01..AC-25 remain unchanged.

| AC | DESIGN requirement |
| --- | --- |
| AC-01 | Home preserves the approved Alpha-aligned structure and Visual Handoff hierarchy. |
| AC-02 | Task creation accepts a natural-language request. |
| AC-03 | Every Task/Execution is associated with the correct Project where applicable. |
| AC-04 | User action starts the real productive runtime. |
| AC-05 | Status/progress is projected only from authoritative runtime facts/evidence. |
| AC-06 | No simulated percentages or fabricated progress. |
| AC-07 | Execution is understandable through human UX without requiring logs. |
| AC-08 | Repair is shown only when real repair evidence exists. |
| AC-09 | Conditional: intervention may be represented only after a future safe pause/response/continuation backend exists; v0.9 does not implement or simulate it. |
| AC-10 | Terminal failure uses human-readable product UX rather than traceback/terminal output as primary presentation. |
| AC-11 | Success assertions are backed by CompletionGate/validation evidence. |
| AC-12 | A valid current JAR is safely downloadable and secondarily locatable when authoritative delivery conditions hold. |
| AC-13 | Details exposes real human-relevant evidence. |
| AC-14 | Technical evidence never exposes chain-of-thought/hidden reasoning. |
| AC-15 | Project is persistent and distinct from Task and Execution. |
| AC-16 | Another Task can be started from an existing Project. |
| AC-17 | Minimum history retrieves relevant previous Tasks/results/Deliveries. |
| AC-18 | Settings exposes only real user configuration; none is invented. |
| AC-19 | Provider/model/API keys/tokens remain outside normal Managed UX. |
| AC-20 | No fictitious credits, prices, checkout or billing. |
| AC-21 | Projects, Settings and Details preserve navigation/context semantics. |
| AC-22 | Back/close/Escape/focus/scroll/stacking behavior is coherent. |
| AC-23 | Basic keyboard navigation and operation are functional. |
| AC-24 | PD Agent visual identity remains recognizable with simplified intentional treatment. |
| AC-25 | Product structure evolves toward Alpha without fundamental redesign. |

No AC is removed or silently reinterpreted. AC-09 retains its explicitly approved conditional status.

## 31. Deferred Capabilities

Explicitly deferred beyond v0.9:

- general cancellation;
- general resume/restart;
- real human-intervention lifecycle;
- distributed workers;
- cloud persistence;
- accounts/auth SaaS;
- collaboration;
- billing;
- credits;
- Managed commercial backend infrastructure;
- provider/model selection UX;
- complete Settings;
- Project branches/version manager;
- advanced delivery management;
- final Alpha art/polish;
- final mobile product;
- Multi-Agent;
- Paper;
- NeoForge;
- Velocity.

## 32. Open Questions Reserved for RFC

The RFC must resolve without changing this DESIGN scope:

- HTTP framework;
- frontend technology;
- application-service interfaces;
- exact background execution mechanism;
- polling vs SSE;
- execution DTOs;
- Product Catalog schema;
- persistence/recovery mechanics;
- workspace registration interface;
- Delivery schema;
- artifact download mechanics;
- local reveal integration;
- exact progress mapping;
- evidence DTO schemas;
- Host/Origin/CSRF mechanism;
- module/package layout;
- test architecture.

These are intentionally unresolved here.

## Final Invariants

- `RunState = only execution state machine`
- `UI progress = derived read-only projection`
- `Project != Task != Execution`
- `Project identity != workspace fingerprint`
- `Success requires authoritative CompletionGate satisfaction`
- `Artifact delivery requires VALID + current + correct ownership`
- `RunStorage remains runtime/evidence authority`
- `Product persistence references runtime evidence; it does not duplicate it`
- `Provider/model/API key remain opaque to normal UX`
- `No fake progress`
- `No fake intervention`
- `No fake cancellation`

## DESIGN Verdict

`V0_9_DESIGN_READY → ACCEPTED BY 00 → PERSISTED`

No RFC decisions are intentionally resolved by this document beyond boundaries already frozen by 00.

## Post-I12 Productive Composition Clarification

The v0.9 product has a **Productive Application Composition Root**. Before
productive Fabric execution, the application resolves a Project, its
TaskRecord, and an authorized and inspected Fabric workspace into a Product
Task contract and then into a `FabricTaskContract`:

`Project + TaskRecord + authorized/inspected Fabric workspace`
`→ Product Task contract resolution → FabricTaskContract → productive Fabric execution`

This composition consumes the existing productive Fabric runtime. It does not
create a parallel runtime, second `RunState`, workflow engine, scheduler, DAG,
or general orchestrator. `RunState` remains the only execution state machine.

This clarification is a post-I12 architecture correction discovered by the
real integration audit. It does not change product scope, UX, acceptance
criteria, or deferred capabilities, and does not claim that this composition
already existed in the original DESIGN baseline.
