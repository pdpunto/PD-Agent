# PD_AGENT_V0.9_IMP

Status: `APPROVED BY 00`

Milestone: `PD Agent v0.9 — Internal Web/UI Integration Preview`

Baseline: `e09246b2790a88381e903ae009a2b3d66d179e04`

Scope: `ALPHA_ALIGNED_FUNCTIONAL_PREVIEW`

## Authorities

1. `docs/product/PD_AGENT_V0.9_PRODUCT_UX_UI_SPEC.md`
2. `docs/design/PD_AGENT_V0.9_DESIGN.md`
3. `docs/rfc/PD_AGENT_V0.9_RFC.md`
4. `V0_9_DESIGN_PERSISTENCE → ACCEPTED`
5. `V0_9_RFC_PERSISTENCE → ACCEPTED`
6. `V0_9_IMP → ACCEPTED`

## Purpose

This implementation plan defines HOW TO BUILD the accepted v0.9 DESIGN + RFC incrementally, with small, testable, reversible implementation lots.

It does not authorize implementation by itself.

Implementation must preserve all accepted Product Spec, DESIGN, RFC and AC-01..AC-25 constraints.

## Canonical implementation sequence

```text
I0  Pre-Implementation Audit
 ↓
I1  Toolchain + Product Contracts
 ↓
I2  ProductCatalog + Project Continuity
 ↓
I3  Runtime Identity Injection
 ↓
I4  ExecutionService + Background Execution
 ↓
I5  Progress + Evidence Projections
 ↓
I6  Delivery + Artifact Security
 ↓
I7  FastAPI Foundation + Local Web Security
 ↓
I8  Product HTTP API
 ↓
I9  React/Vite Frontend Foundation
 ↓
I10 Functional UI + Execution Experience
 ↓
I11 Accessibility + UX Hardening
 ↓
I12 Integrated Productive Runtime Validation
 ↓
I13 Regression + Security + AC Final Gate
```

No lot depends on hidden future work.

No lot may silently redesign accepted architecture.

## Global invariants for every lot

- `RunState = only execution state machine`
- `ExecutionService dispatches; it does not decide lifecycle`
- `UI progress = derived projection`
- `Project != Task != Execution`
- `Project identity != workspace fingerprint`
- `Success requires authoritative CompletionGate satisfaction`
- `Delivery requires successful completion + VALID + current + ownership`
- `RunStorage = runtime/evidence authority`
- `ProductCatalog = product metadata/index authority`
- `Frontend = presentation/client state only`
- `Provider/model/API keys = opaque`
- `No fake progress`
- `No fake intervention`
- `No fake cancellation`

## Global implementation control

For every implementation lot after I0:

```text
implementation
→ focal tests
→ applicable regression
→ git diff --check
→ commit
→ push
→ verify HEAD == origin/main
→ ChatGPT/00 review
→ authorize next lot
```

Codex must not receive authorization to implement I1-I13 together.

If a lot discovers a material DESIGN/RFC/repository contradiction:

```text
STOP affected lot
→ preserve evidence
→ return to 00/01
→ resolve documentation/architecture decision
→ repeat required audit
```

Codex must not silently adapt architecture.

# I0 — Pre-Implementation Audit

## Objective

Audit Product Spec + DESIGN + RFC + IMP against the real repository before any implementation.

## Dependencies

None beyond canonical baseline and approved documents.

## Audit scope

Codex must verify:

- exact canonical baseline;
- `HEAD == origin/main` before audit;
- tracked working-tree state;
- intentionally untracked paths, especially `scripts/benchmark/diagnostics/` if still present;
- module/package paths;
- existing dependency conventions;
- tests and fixtures;
- Windows-specific constraints;
- Python environment/toolchain;
- Node/npm availability and usable versions;
- `RunController`;
- `RunState`;
- `RunStorage`;
- `RunEvent` / `RunEventType`;
- CompletionGate;
- artifact validator/currentness contracts;
- `SecurePathResolver`;
- `ToolExecutor`;
- CLI behavior and integration points;
- real package/build/test conventions;
- conflicts with paths/modules proposed by this IMP.

## Changes permitted

None.

## Changes prohibited

- code changes;
- dependency changes;
- docs changes;
- formatting churn;
- commit/push.

## Required result

`V0_9_PRE_IMPLEMENTATION_AUDIT_PASS`

or:

`V0_9_PRE_IMPLEMENTATION_AUDIT_BLOCKED`

If blocked, STOP before I1.

## Commit boundary

None.

## Rollback

Not applicable; I0 performs no writes.

# I1 — Toolchain + Product Contracts

## Objective

Introduce the minimum reproducible Web/frontend toolchain and product-domain contracts without implementing Web behavior yet.

## Dependency

I0 PASS reviewed by 00.

## Expected modules/files

Subject to I0 reality verification:

```text
pyproject.toml
frontend/package.json
frontend/package-lock.json
frontend/tsconfig*.json
frontend/vite.config.*
src/pd_agent/product/__init__.py
src/pd_agent/product/models.py
tests/product/test_models.py
```

## Dependencies/toolchain

Python runtime dependencies:

- FastAPI;
- Uvicorn.

Frontend runtime dependencies:

- React;
- ReactDOM.

Frontend build/test dependencies:

- TypeScript;
- Vite;
- Vitest;
- React Testing Library.

Targeted Playwright may be introduced here as a test-only dependency or deferred until I11/I12 if I0 shows that to be cleaner for repository/toolchain reproducibility.

## Version strategy

- use explicit compatible version constraints consistent with repo policy;
- commit lockfile for frontend reproducibility;
- document/fix minimum supported Node/npm version in the repository convention chosen after I0;
- avoid floating unbounded major versions;
- do not add unrelated frontend/UI libraries.

## Product contracts

Implement:

### ProjectRecord

- `project_id` UUIDv4;
- `name`;
- `workspace_ref`;
- `created_at`;
- `updated_at`;
- task references.

### TaskRecord

- `task_id` UUIDv4;
- `project_id`;
- `request`;
- `created_at`;
- execution references.

### ExecutionRecord

- `execution_id` UUIDv4;
- `task_id`;
- `run_id`;
- `created_at`;
- optional terminal metadata.

### DeliveryRecord

- `delivery_id` UUIDv4;
- `project_id`;
- `task_id`;
- `execution_id`;
- `artifact_sha256`;
- trusted server-side `artifact_ref`;
- `created_at`.

## Contracts affected

Product metadata only.

`RunState` is not embedded into product models.

## Changes permitted

- dependency declarations;
- frontend bootstrap metadata/config;
- product model module;
- model unit tests.

## Changes prohibited

- ProductCatalog persistence;
- runtime identity injection;
- Web endpoints;
- provider/model/API-key UI/config;
- DB;
- lifecycle changes.

## Tests

- UUID creation/validation;
- serialization boundaries;
- timestamps;
- invalid relationship/reference values;
- immutable/consistent identity semantics where applicable;
- frontend dependency install/build bootstrap.

## Acceptance gate

- focal Python tests PASS;
- frontend dependency install reproducible;
- minimal Vite/test bootstrap succeeds;
- existing applicable regression remains PASS.

## Recommended commit

`feat: add v0.9 product contracts and web toolchain`

## Rollback

Dedicated commit can be reverted without touching v0.8 runtime behavior.

# I2 — ProductCatalog + Project Continuity

## Objective

Implement durable product metadata/index persistence and Project continuity.

## Dependency

I1 accepted.

## Expected modules/files

```text
src/pd_agent/product/catalog.py
src/pd_agent/product/projects.py
tests/product/test_catalog.py
tests/product/test_projects.py
```

plus only minimal related fixtures/helpers justified by repository conventions.

## ProductCatalog schema

Version 1 concept:

```text
schema_version: 1
projects: {}
tasks: {}
executions: {}
deliveries: {}
```

## Persistence requirements

- file-backed versioned JSON;
- separate from RunStorage;
- metadata/index references only;
- no duplication of heavy runtime evidence/JARs;
- missing catalog bootstraps valid empty schema;
- malformed JSON fails closed;
- unsupported newer version fails closed;
- no destructive migration;
- no database.

## Atomic write strategy

```text
serialize
→ sibling temp file
→ flush
→ replace atomically with os.replace()
```

Use repository/platform-appropriate fsync behavior only if I0 confirms it is required and practical; do not invent additional persistence infrastructure.

## Locking

Process-local `threading.RLock` around catalog mutations.

No distributed/cross-process locking infrastructure.

## Project continuity

Implement:

- create/import/register Project;
- canonical workspace registration;
- stable Project identity;
- reopen Project;
- create Task under existing Project;
- store Execution refs;
- read minimum history;
- represent missing/moved/unavailable workspace truthfully.

## Workspace rules

- explicit user registration only;
- canonicalize existing path;
- validate directory/workspace;
- Project identity remains distinct from workspace fingerprint;
- later operations resolve through registered Project/workspace reference;
- no arbitrary filesystem browsing API.

## Adversarial tests

- corrupt JSON;
- unknown future schema;
- interrupted/failed write behavior;
- invalid ownership/reference;
- nonexistent/moved workspace;
- canonicalization/path escape;
- symlink/junction/reparse behavior when applicable on Windows;
- unrelated filesystem path injection.

## Acceptance gate

- catalog roundtrip PASS;
- bootstrap PASS;
- corruption/version fail-closed PASS;
- Project reopen/continuity PASS;
- same Project can create subsequent Task;
- no arbitrary filesystem authority introduced.

## Recommended commit

`feat: add v0.9 product catalog and project continuity`

## Rollback

- schema remains `v1`;
- no destructive migration;
- revert code without deleting catalog/evidence automatically;
- preserve problematic data for diagnosis.

# I3 — Runtime Identity Injection

## Objective

Implement the minimum runtime extension required for preallocated `execution_id == run_id` while preserving current behavior.

## Dependency

I2 accepted.

## Expected changes

Exact files determined by I0, centered on existing `RunController` / `RunState` construction and their tests.

Conceptual contract:

```text
RunController.run(..., run_id: UUID | None = None)
```

or an equivalent repository-native mechanism preserving the same semantics.

## Required behavior

When no ID is supplied:

```text
current historical behavior
→ RunState generates/uses normal run identity
```

When supplied:

```text
preallocated execution_id
→ RunController accepts predefined run_id
→ RunState uses same identity
→ RunStorage persists under same identity
```

v0.9 invariant:

`execution_id == run_id`

## Changes permitted

Only minimal identity-injection wiring and its tests.

## Changes prohibited

- lifecycle redesign;
- new state machine;
- ExecutionService implementation;
- Web/API work;
- scheduler/queue;
- cancellation/resume semantics.

## Collision/reuse

If the preallocated identity already conflicts with an existing productive/persisted run identity, fail closed using the narrowest repository-consistent behavior.

Do not silently overwrite existing run storage.

## Regression requirements

Preserve:

- CLI behavior;
- existing callers;
- existing v0.8 lifecycle;
- RunState transitions;
- RunStorage semantics.

## Tests

- autogenerated historical ID;
- injected ID;
- exact persisted identity;
- duplicate/collision/reuse;
- RunStorage association;
- existing RunController tests/regression.

## Acceptance gate

All identity-specific tests and applicable v0.8 runtime regression PASS.

## Recommended commit

`feat: support preallocated run identity`

## Rollback

Dedicated isolated commit can restore historical ID generation without reverting ProductCatalog work.

I3 must not be merged into I4.

# I4 — ExecutionService + Background Execution

## Objective

Connect product Task/Execution metadata to the existing synchronous productive runtime without blocking future HTTP request handling.

## Dependency

I3 accepted.

## Expected modules/files

```text
src/pd_agent/product/execution.py
tests/product/test_execution.py
```

plus narrow helpers required by repository reality.

## Execution mechanism

`concurrent.futures.ThreadPoolExecutor(max_workers=1)`

Capacity policy:

`ONE PRODUCTIVE EXECUTION GLOBALLY`

## Dispatch flow

```text
Task
→ allocate execution_id
→ persist ExecutionRecord
→ submit productive RunController with run_id=execution_id
→ return execution identity immediately
```

## Required behavior

- nonblocking dispatch from application/Web caller;
- stable execution mapping;
- browser/navigation independence;
- one active productive execution globally;
- second concurrent start rejected;
- worker exception safely captured/projected;
- terminal state can be reconciled from runtime authority;
- graceful service shutdown behavior;
- restart reconstruction based on persisted facts.

## Capacity error

Second productive start while one is active:

`EXECUTION_CAPACITY_REACHED`

No fake queue.

No scheduler.

## Interrupted/Unknown behavior

A persisted execution found nonterminal after server/process restart may be projected at product level as:

`INTERRUPTED / UNKNOWN`

This is not:

- a new RunState;
- a runtime transition;
- runtime resume;
- a second state machine.

Do not rewrite/falsify persisted RunState to manufacture the product projection.

## Changes prohibited

- cancellation;
- resume;
- intervention lifecycle;
- multi-worker scheduling;
- distributed queue.

## Tests

- immediate dispatch return;
- one-worker capacity;
- second-start rejection;
- execution/run mapping;
- worker exception;
- terminal reconciliation;
- shutdown behavior;
- reconstruction of persisted nonterminal run to product-level interrupted/unknown projection.

Deterministic fake/stub runtime boundary is permitted for this unit/integration lot; it does not satisfy final I12 validation.

## Acceptance gate

Concurrency/capacity/restart/exception tests PASS and existing runtime lifecycle remains unchanged.

## Recommended commit

`feat: add v0.9 execution service`

## Rollback

ExecutionService can be reverted independently without changing RunState lifecycle semantics.

# I5 — Progress + Evidence Projections

## Objective

Implement truthful read-only product projections from RunState/RunEvent/evidence.

## Dependency

I4 accepted.

## Expected modules/files

```text
src/pd_agent/product/evidence.py
tests/product/test_progress_projection.py
tests/product/test_evidence.py
```

## Progress states

Implement deterministic mapping for:

- Entendiendo;
- Investigando;
- Editando;
- Compilando;
- Probando;
- Verificando;
- Reparando;
- Entregando.

## Authority

Only:

- `RunState`;
- `RunEvent` / event sequence;
- real persisted/current evidence.

No elapsed-time inference.

No percentage.

No frontend lifecycle authority.

No new execution state machine.

## Mapping priority

Preserve RFC order:

1. terminal RunState;
2. active repair;
3. runtime validation;
4. artifact/completion verification;
5. build;
6. edit/mutation;
7. knowledge activity;
8. inspect/plan.

## Evidence DTOs

Implement explicit allowlist-based:

`HumanEvidenceDTO`

and:

`TechnicalEvidenceDTO`

Human evidence may contain safe summaries of:

- request/changes;
- build;
- repair;
- runtime validation;
- completion;
- artifact.

Technical evidence may contain allowlisted:

- IDs;
- timestamps;
- run status;
- changed files;
- build attempts;
- validation summaries;
- runtime observations;
- failure classification;
- artifact SHA256;
- safe evidence references.

## Forbidden exposure

Tests must prove no exposure of:

- credentials;
- API keys;
- provider raw payloads;
- hidden reasoning/chain-of-thought;
- unrestricted arbitrary filesystem contents/paths.

## Product terminal/failure projections

Support truthful derived categories:

- RUNNING;
- SUCCEEDED;
- FAILED;
- BLOCKED;
- LIMIT_REACHED;
- INTERRUPTED;
- relevant degraded/infrastructure conditions.

These are product projections only.

## Acceptance gate

All progress states are reproducible from deterministic real-shaped RunState/event/evidence fixtures and leakage tests PASS.

## Recommended commit

`feat: add v0.9 execution and evidence projections`

## Rollback

Projection layer is independently revertible; runtime authority remains untouched.

# I6 — Delivery + Artifact Security

## Objective

Implement trusted Delivery records and fail-closed artifact delivery.

## Dependency

I5 accepted.

## Expected modules/files

```text
src/pd_agent/product/delivery.py
tests/product/test_delivery.py
```

## Delivery validation chain

```text
Delivery ownership
→ authoritative successful execution
→ CompletionGate PASS
→ required validation satisfied
→ artifact identity matches
→ artifact VALID
→ artifact current
→ file exists
→ artifact hash/currentness verified
→ delivery allowed
```

## Primary action

Safe Web JAR download through trusted Delivery ID.

Browser does not provide artifact path.

## Secondary action

Trusted server-side local location/reveal action.

Browser supplies only Delivery identity, never arbitrary reveal path.

## Required adversarial tests

- stale artifact;
- missing artifact;
- corrupt/hash mismatch;
- wrong Project ownership;
- wrong Task ownership;
- wrong Execution ownership;
- forged/nonexistent Delivery;
- traversal attempt;
- manipulated artifact reference;
- stale currentness identity.

## Acceptance gate

No stale, missing, invalid, corrupt, foreign-owned or path-manipulated artifact can be delivered/revealed.

## Recommended commit

`feat: add validated v0.9 artifact delivery`

## Rollback

Delivery layer fails closed and can be reverted without deleting underlying RunStorage/evidence/artifacts.

# I7 — FastAPI Foundation + Local Web Security

## Objective

Introduce the local HTTP boundary with security controls present from its first mutating surface.

## Dependency

I6 accepted.

## Expected modules/files

```text
src/pd_agent/web/__init__.py
src/pd_agent/web/app.py
src/pd_agent/web/dto.py
src/pd_agent/web/security.py
tests/web/
```

## Foundation

Implement:

- FastAPI application composition;
- Uvicorn server configuration integration;
- `/api/v1` prefix foundation;
- canonical safe error envelope;
- request/error IDs if implemented by accepted RFC contract;
- backend static-serving hook prepared for later frontend build.

## Network boundary

Default bind:

`127.0.0.1`

Never default to `0.0.0.0`.

## Security controls

Implement and test:

- Host allowlist;
- same-origin/accepted Origin validation for mutations;
- server-generated CSRF token + custom request header for mutations;
- bounded request/body sizes;
- safe error redaction;
- safe filenames where relevant;
- preservation of SecurePathResolver/ToolExecutor boundaries;
- no generic filesystem exposure.

## Required adversarial tests

- foreign Host;
- foreign Origin;
- absent CSRF;
- incorrect CSRF;
- oversized mutation;
- malformed input;
- traceback/internal detail suppression.

## Changes prohibited

- SaaS auth/accounts;
- provider selection API;
- arbitrary filesystem API;
- cancel/resume/intervention APIs.

## Acceptance gate

Local Web boundary demonstrably fails closed under required adversarial tests.

## Recommended commit

`feat: add secure v0.9 local web foundation`

## Rollback

Web foundation commit is independently revertible; product/runtime layers remain intact.

# I8 — Product HTTP API

## Objective

Expose the canonical Product/RFC application contract over `/api/v1`.

## Dependency

I7 accepted.

## Expected modules/files

Subject to I0/repository conventions:

```text
src/pd_agent/web/api/projects.py
src/pd_agent/web/api/executions.py
src/pd_agent/web/api/deliveries.py
```

plus minimal router registration/tests.

## Required endpoints

```text
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{project_id}

POST   /api/v1/projects/{project_id}/tasks
POST   /api/v1/tasks/{task_id}/executions

GET    /api/v1/executions/{execution_id}
GET    /api/v1/executions/{execution_id}/evidence/human
GET    /api/v1/executions/{execution_id}/evidence/technical

GET    /api/v1/projects/{project_id}/history

GET    /api/v1/deliveries/{delivery_id}
GET    /api/v1/deliveries/{delivery_id}/artifact
POST   /api/v1/deliveries/{delivery_id}/reveal
```

## Explicitly prohibited endpoints/capabilities

- DELETE;
- Cancel;
- pause;
- human response;
- resume;
- arbitrary filesystem read/write/download;
- provider/model/API-key configuration.

## Error model

Preserve canonical safe envelope and RFC codes, including where applicable:

- `PROJECT_NOT_FOUND`;
- `WORKSPACE_INVALID`;
- `WORKSPACE_UNAVAILABLE`;
- `TASK_NOT_FOUND`;
- `EXECUTION_NOT_FOUND`;
- `EXECUTION_CAPACITY_REACHED`;
- `EXECUTION_INTERRUPTED`;
- `DELIVERY_NOT_FOUND`;
- `ARTIFACT_NOT_CURRENT`;
- `ARTIFACT_UNAVAILABLE`;
- `CATALOG_CORRUPT`;
- `CATALOG_VERSION_UNSUPPORTED`;
- `SECURITY_REJECTED`.

## Tests

- status codes;
- DTO schemas;
- Project/Task/Execution ownership;
- capacity rejection;
- CSRF/Origin/Host behavior;
- stale/missing delivery;
- error envelope;
- evidence allowlists;
- safe artifact download/reveal entrypoints.

## Acceptance gate

Complete canonical API usable without frontend and all security/contract tests PASS.

## Recommended commit

`feat: expose v0.9 product api`

## Rollback

API routers can be reverted while retaining product/application implementation.

# I9 — React/Vite Frontend Foundation

## Objective

Build the Alpha-compatible functional shell over the real API.

## Dependency

I8 accepted.

## Expected modules/files

Repository layout subject to I0 but conceptually:

```text
frontend/src/
  app/
  api/
  components/
  pages/
```

## Required foundation

- React + TypeScript + Vite app;
- routing;
- API client;
- shell/navigation;
- Home route;
- Projects route;
- Project route;
- Execution route;
- Settings route;
- modal/layer foundation;
- execution polling client;
- frontend error/loading/degraded presentation state;
- production Vite build served by FastAPI.

## Frontend authority boundary

Frontend owns presentation/client state only.

Frontend does not decide:

- execution lifecycle;
- completion;
- artifact validity/currentness;
- repair truth;
- persistence authority;
- provider configuration.

## Visual implementation boundary

From this lot the UI must already be recognizably PD Agent and aligned with approved target direction:

- moderate dark treatment;
- violet identity;
- approved hierarchy/navigation;
- Minecraft-linked treatment;
- correct layout structure.

Do not build a disposable generic UI that would require structural redesign for Alpha.

Deferred final polish includes:

- cinematic/final assets;
- complete agent poses;
- final animation system;
- proprietary final iconography;
- final mobile polish.

## Tests

- Vitest;
- React Testing Library;
- routing/navigation;
- API client behavior;
- polling lifecycle basics;
- error/degraded rendering;
- production Vite build.

## Acceptance gate

Navigation/client foundation works against backend API contracts and production frontend build is served successfully.

## Recommended commit

`feat: add v0.9 frontend foundation`

## Rollback

Frontend foundation is separable from product/backend runtime layers.

# I10 — Functional UI + Execution Experience

## Objective

Complete the functional Alpha-aligned v0.9 user experience using real API DTOs.

## Dependency

I9 accepted.

## Functional surfaces

Implement:

- Home;
- Projects;
- Project detail;
- Project create/import/register;
- Task composer;
- Execution view;
- real progress states;
- Repair presentation;
- Success;
- Failure;
- Details;
- Human Evidence;
- Technical Evidence;
- minimum Project history;
- artifact download;
- local reveal/location action;
- truthful Settings structure/placeholder;
- refresh/reconnect restoration.

## Functional rules

- Project is not Task;
- Task is not Execution;
- every visual execution state originates from backend DTO truth;
- repair appears only with repair evidence;
- success appears only after authoritative completion criteria;
- artifact actions appear only when Delivery is valid/current/owned;
- no provider/model/API-key normal UX.

## Explicitly prohibited

- fake percentages;
- fake progress;
- functional Cancel;
- functional human intervention;
- fake waiting-for-user lifecycle;
- provider selector;
- credits/billing;
- fake Settings controls.

## Tests

Component/integration fixtures for:

- each progress state;
- repair active/resolved;
- success;
- failure;
- blocked/limit/interrupted/degraded states;
- history;
- Details evidence;
- stale/unavailable Delivery;
- refresh/reconnect;
- same Project/new Task.

## Acceptance gate

Every UI state has a corresponding real backend DTO condition; unsupported capabilities are absent, disabled or truthfully described.

## Recommended commit

`feat: complete v0.9 functional execution ui`

## Rollback

Functional UI commit can be reverted without modifying productive runtime/evidence.

# I11 — Accessibility + UX Hardening

## Objective

Perform adversarial accessibility and interaction validation/hardening.

Accessibility must already be incorporated during I9/I10; I11 is not permission to defer all accessibility until the end.

## Dependency

I10 accepted.

## Verify/correct

- keyboard-only operation;
- visible focus;
- semantic controls;
- labels;
- dialog semantics;
- focus trap where applicable;
- focus restore;
- Escape behavior;
- restrained aria-live/status announcements;
- no duplicate polling announcement spam;
- non-color-only states;
- reduced motion;
- contrast;
- scrolling behavior;
- responsive behavior required for v0.9 functional preview.

## Browser validation

Use targeted Playwright for critical user/browser flows.

## Tests/gates

- automated component/interaction tests;
- targeted browser tests;
- explicit manual accessibility/interaction checklist where automation is insufficient.

## Acceptance gate

Critical flows usable by keyboard and required focus/dialog/status semantics validated.

## Recommended commit

Only if corrections are required:

`fix: harden v0.9 accessibility and ux`

Do not create an artificial empty/no-op commit.

## Rollback

Accessibility corrections should remain local to frontend behavior unless a real API accessibility dependency is proven.

# I12 — Integrated Productive Runtime Validation

## Objective

Prove the Web/UI is integrated with productive PD Agent runtime rather than only mocks/fakes.

## Dependency

I11 accepted.

## Required end-to-end flow

```text
Browser
→ FastAPI
→ Project
→ Task
→ ExecutionService
→ real RunController
→ productive PD Agent runtime
→ RunStorage/events
→ real progress/evidence
→ authoritative success/failure
→ CompletionGate
→ Delivery
→ JAR download
```

## Validation levels

### A. Deterministic/offline integration

Cover as much as possible without external API cost:

- Browser/Web/API wiring;
- ProductCatalog;
- worker dispatch;
- RunStorage observation;
- progress/evidence;
- success/failure projection;
- Delivery/security;
- frontend download path.

### B. Productive real runtime validation

Demonstrate at least one real Task through productive PD Agent runtime with authoritative result and real artifact when the Task requires one.

Fake backend/runtime alone does not satisfy this gate.

## Live/cost rule

No external API spending is authorized by this IMP.

When an explicitly authorized productive validation uses the OpenAI runtime,
the composition root must receive its maximum economic budget explicitly and
inject the existing fail-closed `LunaBudgetGuard` before the first physical
request. No I12 ceiling is a global product default; callers without an
economic policy retain the existing behavior.

If productive validation requires paid/external API usage:

```text
STOP
→ return to 00
→ request explicit authorization
```

No benchmark live unless separately authorized.

Minecraft live is required only when the real Task contract/acceptance requires runtime validation.

## Evidence required

Record at minimum:

- Project/Task/execution identity;
- `execution_id` / `run_id` relation;
- terminal runtime result;
- relevant event/evidence references;
- CompletionGate result;
- validation result;
- artifact SHA256;
- downloaded JAR SHA256;
- relevant tests/logs;
- Delivery identity/currentness result.

## Acceptance gate

`V0_9_WEB_RUNTIME_INTEGRATION_PASS`

## Commit boundary

Validation alone does not justify a commit.

If validation exposes defects, corrections require tests and a dedicated reviewed commit/push before repeating validation.

## Rollback

Do not delete RunStorage/evidence after failed integrated validation; preserve evidence for diagnosis.

# I12-A — Productive Fabric Execution Boundary

**Dependency:** I11 accepted.

Implement `ProductFabricTaskContractResolver`, `ProductExecutionRunner`,
`FabricProductExecutionRunner`, and optional preallocated `run_id` support in
`FabricNormalOrchestrator`. Resolve Product Task → valid `FabricTaskContract`,
preserve `task_id`, produce structured validation requirements, keep Minecraft
conditional on those requirements, and reject identity collision/reuse.
Preserve historical behavior without an injected ID and the v0.8 regression.
No Web entrypoint or ProductApplication wiring belongs here.

**Acceptance:** valid contract, preserved identity, no new lifecycle/state
machine, and collision/reuse failure closed.

**Validation and rollback:** focused contract/identity/runtime tests plus v0.8
regression. Dedicated commit/push. Revert only the product execution/contract
boundary and FabricNormalOrchestrator identity extension.

## I12-B — Productive Composition Root + Delivery Reconciliation

**Dependency:** I12-A.

Implement `ProductApplication`, `build_product_application(...)`, real
product/runtime wiring, shared economic-budget lifetime, Delivery
reconciliation after authoritative success, and lifecycle/shutdown ownership.

**Acceptance:** full composition constructible, existing Fabric runtime reused,
correct service ownership, one shared guard, fail-closed Delivery, clean
shutdown, no second runtime or state machine.

**Validation and rollback:** composition, ownership, budget, delivery and
shutdown tests. Dedicated commit/push. Revert composition wiring without
deleting ProductCatalog or RunStorage.

## I12-C — Productive Web Entrypoint

**Dependency:** I12-B.

Implement `pd-agent web`, configuration/startup, ProductApplication
construction, FastAPI/Uvicorn startup, loopback binding, frontend/dist serving,
and clean shutdown.

**Acceptance:** server starts with ProductApplication active, frontend/API are
served, local security remains enforced, startup does not execute a Task, and
shutdown is clean.

**Validation and rollback:** server, security, static-serving and lifecycle
tests. Dedicated commit/push. Revert the Web entrypoint independently.

## I12-D — Browser Validation Infrastructure

**Dependency:** I12-C.

Test-only Playwright/browser setup for the real Browser → frontend/dist →
FastAPI → ProductApplication boundary. It must not contain product
architecture, require a paid provider, or require Minecraft live.

**Acceptance:** targeted browser flow and critical accessibility/navigation
coverage. Dedicated commit/push only when repository files change. Remove this
test-only infrastructure independently on rollback.

## I12-E — Integrated Productive Validation

**Dependency:** I12-A through I12-D.

Validate Browser → Web/API → Product → FabricTaskContract →
FabricNormalOrchestrator → provider → mutation → build → Minecraft when
required → CompletionGate → Delivery → browser JAR download → independent
SHA-256 verification. Preserve evidence for identities, budget, milestones,
build, Minecraft, gate, Delivery, download, Details, reconstruction,
continuity, and security.

Before any billable provider execution, stop and request explicit authorization
from 00. The previously authorized `$0.50` does not authorize I12-E after this
architecture correction. No benchmark live is implied.

**Acceptance:** `V0_9_WEB_RUNTIME_INTEGRATION_PASS` with no fake progress,
success, delivery, or intervention.

**Validation and rollback:** validation-only evidence; if defects appear,
preserve evidence and use a dedicated reviewed fix before repeating. Never
delete runtime/evidence automatically.

# I13 — Regression + Security + AC Final Gate

## Objective

Prove v0.9 completeness without regressing v0.8 or violating security/product acceptance.

## Dependency

I12 PASS.

## Independent final gates

1. implementation completeness;
2. integrated functional validation;
3. UX/accessibility validation;
4. v0.8 regression;
5. security;
6. AC traceability;
7. documentation/evidence;
8. final Git state.

## Required checks

Exact commands are finalized by I0/repository reality, but must include applicable equivalents of:

- complete Python suite;
- compileall;
- Fabric/productive runtime tests;
- security regression;
- ProductCatalog/product tests;
- Web/API tests;
- frontend Vitest/RTL suite;
- production frontend build;
- targeted Playwright critical flows;
- integrated Web/runtime validation;
- `git diff --check`;
- working-tree verification;
- `HEAD == origin/main` after final committed changes.

## v0.8 regression

v0.9 cannot close if existing v0.8 productive runtime/security behavior is broken.

## Benchmark/live rule

No benchmark live unless separately authorized/required by 00.

No external API spend unless explicitly authorized.

## Required final gate

`V0_9_FINAL_VALIDATION_PASS`

No v0.9 PASS before all required gates pass with evidence.

## Commit boundary

Only create a final commit if legitimate final corrections/documentation changes remain.

No artificial mega-commit.

# AC-01..AC-25 Traceability

| AC | Primary implementation lot(s) | Required proof/gate |
| --- | --- | --- |
| AC-01 | I9, I10 | Alpha-aligned Home/navigation frontend tests/browser review |
| AC-02 | I2, I10 | Natural-language Task creation flow |
| AC-03 | I2, I8 | Task correctly bound to Project ownership tests |
| AC-04 | I3, I4, I12 | Web starts real productive runtime execution |
| AC-05 | I5, I10 | UI facts derive from authoritative DTO/evidence |
| AC-06 | I5, I10 | No percentage/time-derived fake progress tests/review |
| AC-07 | I5, I10 | Human execution UX states driven by execution projection |
| AC-08 | I5, I10 | Repair appears only from real repair evidence |
| AC-09 | DEFERRED / CONDITIONAL | Verify no intervention lifecycle/endpoints are implemented |
| AC-10 | I5, I10 | Human terminal failure/blocked/limit presentation |
| AC-11 | I5, I12 | CompletionGate-backed authoritative success |
| AC-12 | I6, I8, I12 | Valid/current owned JAR download/location |
| AC-13 | I5, I10 | Human Evidence Details |
| AC-14 | I5, I7 | CoT/secrets/provider payload leakage rejection |
| AC-15 | I1, I2 | Product contract tests prove Project != Task |
| AC-16 | I2, I10 | New Task on same persistent Project |
| AC-17 | I2, I8, I10 | Minimum Project history |
| AC-18 | I9, I10 | Truthful Settings only |
| AC-19 | I7, I8, I9, I10 | Provider/model/API keys absent from normal UX/API |
| AC-20 | I10, I13 | Verify credits/billing absent |
| AC-21 | I9, I10 | Context-preserving navigation |
| AC-22 | I9, I10, I11 | Modal/back/close/focus/scroll behavior |
| AC-23 | I11 | Keyboard accessibility gate |
| AC-24 | I9, I10 | Recognizable approved PD Agent visual identity |
| AC-25 | I0-I13 architectural/final review | Contracts remain evolvable to Alpha without fundamental redesign |

AC-09 remains conditional/deferred and must not be falsely marked implemented or PASS.

# Commit boundaries

Recommended implementation commits:

- I1 → `feat: add v0.9 product contracts and web toolchain`
- I2 → `feat: add v0.9 product catalog and project continuity`
- I3 → `feat: support preallocated run identity`
- I4 → `feat: add v0.9 execution service`
- I5 → `feat: add v0.9 execution and evidence projections`
- I6 → `feat: add validated v0.9 artifact delivery`
- I7 → `feat: add secure v0.9 local web foundation`
- I8 → `feat: expose v0.9 product api`
- I9 → `feat: add v0.9 frontend foundation`
- I10 → `feat: complete v0.9 functional execution ui`
- I11 → `fix: harden v0.9 accessibility and ux` only if changes are required
- I12 → no commit unless validation produces corrections
- I13 → final commit only for legitimate remaining changes

Each commit is followed by push and verification before next-lot authorization.

No mega-commit at the end.

# Rollback strategy

## I1

Revert dependencies/contracts commit. Productive v0.8 runtime remains unchanged.

## I2

Catalog uses schema v1 with no destructive migration. Revert implementation without automatically deleting persisted catalog data; preserve diagnostic data.

## I3

Dedicated identity-injection commit allows isolated rollback to historical run ID behavior.

## I4

ExecutionService layer can be removed without changing RunState lifecycle authority.

## I5

Projection/evidence product layer can be reverted without rewriting runtime state/evidence.

## I6

Delivery remains fail-closed; revert application delivery layer without deleting artifacts/RunStorage.

## I7/I8

Web/API boundary is separate from productive runtime and can be reverted independently.

## I9-I11

Frontend can be reverted independently of backend/runtime behavior.

## Global rollback rule

Never automatically delete RunStorage/evidence merely because an implementation lot is reverted.

# Final implementation gate

v0.9 cannot be declared PASS until all required gates have evidence:

1. `V0_9_PRE_IMPLEMENTATION_AUDIT_PASS`
2. I1-I11 accepted implementation lots as applicable
3. `V0_9_WEB_RUNTIME_INTEGRATION_PASS`
4. implementation completeness PASS
5. UX/accessibility PASS
6. v0.8 regression PASS
7. security PASS
8. AC-01..AC-25 traceability reviewed, with AC-09 explicitly deferred/conditional
9. docs/evidence complete
10. final repository state clean/expected
11. final required commit(s) pushed with `HEAD == origin/main`
12. `V0_9_FINAL_VALIDATION_PASS`

No benchmark live, external API spend, general cancellation, general resume, human-intervention lifecycle, distributed workers, cloud/SaaS architecture, billing, provider-selection UX, Multi-Agent or loader expansion is authorized by this IMP.

# Deferred capabilities preserved

Outside v0.9:

- general cancellation;
- general resume;
- real human intervention lifecycle;
- distributed workers;
- general job scheduler;
- cloud persistence;
- SaaS accounts/auth;
- collaboration;
- billing/credits;
- commercial Managed backend;
- provider/model selection UX;
- complete Settings;
- Project branches/version manager;
- advanced delivery management;
- final Alpha polish;
- final mobile product;
- Multi-Agent;
- Paper;
- NeoForge;
- Velocity.

# Final verdict

`V0_9_IMP_READY`

This accepted implementation plan is complete enough for Codex to implement later without redesigning the accepted architecture.

Persistence of this document does not authorize I0 or implementation.
