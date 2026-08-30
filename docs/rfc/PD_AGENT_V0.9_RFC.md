# PD_AGENT_V0.9_RFC

Status: `APPROVED BY 00`

Milestone: `PD Agent v0.9 — Internal Web/UI Integration Preview`

Baseline: `fc5cc6526dfdb086006a31935ded23f30eb673e3`

Scope: `ALPHA_ALIGNED_FUNCTIONAL_PREVIEW`

## Authorities

1. `docs/product/PD_AGENT_V0.9_PRODUCT_UX_UI_SPEC.md`
2. `docs/design/PD_AGENT_V0.9_DESIGN.md`
3. `V0_9_PRE_DESIGN_AUDIT_READY → ACCEPTED`
4. `V0_9_TECHNICAL_SCOPE_BOUNDARY_READY → ACCEPTED`
5. `V0_9_DESIGN_PERSISTENCE → ACCEPTED`
6. `V0_9_RFC → ACCEPTED`

## 0. Reality Audit

Reality Audit against baseline `fc5cc6526dfdb086006a31935ded23f30eb673e3` found no material repository contradiction with the approved DESIGN.

Repository facts relevant to this RFC:

- Python `>=3.13` with setuptools and pytest.
- Existing productive runtime is synchronous.
- `RunController.run()` creates `RunState` and its `run_id` internally before delegating to `AgentRuntime`.
- `RunState` remains the only execution lifecycle state machine.
- `RunStorage` already persists run state, JSONL events, evidence, builds and final reports.
- Existing `RunEventType` covers build, artifact validation, functional validation, semantic repair, knowledge, failures, runtime validation and CompletionGate evaluation.
- `SecurePathResolver` already enforces project-root confinement and rejects absolute/escaping paths.
- No existing productive Web/API/frontend layer constrains the v0.9 Web architecture.

Reality Audit verdict: `PASS`.

## 1. Web / Application Architecture

Selected architecture:

`Browser → FastAPI/Uvicorn Local Web/API → Thin Application Services → existing productive runtime`

Decisions:

- HTTP framework: `FastAPI`.
- Local server: `Uvicorn`.
- Single local process for v0.9.
- Default bind: `127.0.0.1`.
- Frontend static assets are served by the same local backend in production preview mode.
- API is versioned under `/api/v1`.
- Dependency direction is Web → product/application → existing runtime.
- Existing runtime does not import Web/presentation code.

No microservices, distributed backend, Redis, Celery or job platform.

## 2. Frontend Technology

Selected frontend:

`React + TypeScript + Vite`

No SSR and no Next.js.

Build flow:

`frontend source → Vite build → static assets → FastAPI serves assets`

Frontend owns only:

- routing/navigation state;
- modal/layer presentation state;
- form/input state;
- cached API responses;
- visual rendering.

Frontend does not own:

- execution lifecycle;
- completion authority;
- artifact validity/currentness;
- repair truth;
- Project persistence authority;
- provider/model configuration.

## 3. Application Services

Minimum product/application services:

### ProjectService

Responsible for:

- Project creation/list/open;
- workspace registration;
- Project continuity;
- Task/history access;
- ProductCatalog access.

### ExecutionService

Responsible for:

- Task/Execution creation and linkage;
- background dispatch;
- execution capacity policy;
- execution observation/snapshot composition;
- `execution_id ↔ productive run` mapping.

Invariant: `ExecutionService dispatches; it does not decide lifecycle`.

### EvidenceService

Responsible for:

- progress projection;
- Human Evidence DTO;
- Technical Evidence DTO;
- safe success/failure/repair projections.

### DeliveryService

Responsible for:

- Delivery lookup;
- Project/Task/Execution ownership validation;
- CompletionGate/artifact validation/currentness checks;
- safe JAR download;
- local reveal.

No separate TaskService or ObservationService is required for v0.9.

## 4. Project / Task / Execution / Delivery Contracts

All public product IDs are UUIDv4 strings.

### ProjectRecord

- `project_id`
- `name`
- `workspace_ref`
- `created_at`
- `updated_at`
- `task_ids`

Invariant: `Project identity != workspace fingerprint`.

`workspace_ref` is a server-side authorized reference, not a browser filesystem authority.

### TaskRecord

- `task_id`
- `project_id`
- `request`
- `created_at`
- `execution_ids`

### ExecutionRecord

- `execution_id`
- `task_id`
- `run_id`
- `created_at`
- `terminal_recorded_at` when applicable

v0.9 decision:

`execution_id == run_id`

internally.

The HTTP API treats `execution_id` as opaque, allowing future Alpha internals to decouple execution and run identity without breaking the product contract.

### DeliveryRecord

- `delivery_id`
- `project_id`
- `task_id`
- `execution_id`
- `artifact_sha256`
- `artifact_ref`
- `created_at`

`artifact_ref` remains server-side and is never accepted from the browser as an arbitrary filesystem path.

Invariant: `Project != Task != Execution`.

Relationship:

`Project → Tasks → Executions → Deliveries`.

## 5. Product Catalog / Persistence

v0.9 uses a minimal file-backed ProductCatalog.

Conceptual layout:

```text
<data_root>/
  product/
    catalog-v1.json
  runs/
    <run_id>/...
```

Exact administrative root configuration is implementation detail, but product metadata and runtime evidence remain separate authorities.

Catalog schema:

```text
schema_version: 1
projects: {}
tasks: {}
executions: {}
deliveries: {}
```

The catalog contains metadata/index references only. It does not duplicate heavy logs, runtime evidence or JAR files.

Invariant: `ProductCatalog = product metadata/index authority`.

Invariant: `RunStorage = runtime/evidence authority`.

Invariant: `Product persistence references runtime evidence; it does not duplicate it`.

### Atomic writes

Write strategy:

`serialize → sibling temporary file → flush → os.replace()`

### Locking

Use one process-local `threading.RLock` around catalog mutations.

v0.9 is single-process; no cross-process locking infrastructure is introduced.

### Corruption handling

- Missing catalog: initialize empty valid schema.
- Malformed/corrupt catalog: fail closed.
- Do not silently overwrite corrupt data.
- Return safe product error such as `CATALOG_CORRUPT`.

### Version handling

Unknown newer schema returns `CATALOG_VERSION_UNSUPPORTED`.

No destructive automatic migration.

No database unless future evidence justifies one.

## 6. Workspace Registration

A local path may enter the browser/API only during explicit Project create/import/register flow.

Flow:

`user selects/enters local directory → backend canonicalizes → validates existing directory/workspace → registers authorized workspace_ref → persists Project`

Canonicalization uses `Path.resolve(strict=True)`.

Windows junction/symlink/reparse targets are evaluated through canonical target resolution.

After registration, all runtime/filesystem actions use:

`project_id → ProductCatalog → authorized workspace_ref → existing runtime/SecurePathResolver`

The API never exposes a generic arbitrary filesystem read/write/download endpoint.

Browser-provided paths cannot be used for Delivery or evidence access.

## 7. Background Execution

Selected mechanism:

`concurrent.futures.ThreadPoolExecutor(max_workers=1)`

v0.9 capacity policy:

`one productive Execution globally`

Reasons:

- productive runtime is synchronous;
- minimizes thread-safety risk;
- avoids overlapping workspace/build/Minecraft mutation;
- sufficient for internal preview;
- avoids scheduler/job-platform overengineering.

Start lifecycle:

`POST start → generate execution_id → persist Task/Execution relationship → submit worker → 202 Accepted + execution_id`

### Minimum runtime extension

Current behavior:

`RunController.run() → creates RunState → run_id generated internally`

Required v0.9 behavior:

`ExecutionService generates execution_id → RunController accepts predefined run_id → RunState(run_id=execution_id)`

This is identity injection only. It does not create a second lifecycle or state machine.

### Capacity

If one productive Execution is active, a second start request returns:

`409 EXECUTION_CAPACITY_REACHED`

No fake queue is created.

### Browser disappears

Execution continues independently of browser navigation/connection.

### Graceful server shutdown

- stop accepting new productive Executions;
- allow current worker to finish within shutdown policy where possible;
- do not invent cancellation semantics.

### Unexpected server/process termination

A persisted run left non-terminal is represented after restart using a product-level degraded projection:

`INTERRUPTED / UNKNOWN`

This is explicitly not:

- a new `RunState`;
- a runtime transition;
- resume;
- a second state machine.

The persisted runtime state is not falsified or rewritten merely to produce this projection.

## 8. Execution Observation

Selected mechanism: `polling`.

No SSE or WebSocket for v0.9.

Primary snapshot endpoint:

`GET /api/v1/executions/{execution_id}`

Requirements:

- snapshot can be reconstructed from ProductCatalog + RunStorage/current runtime facts;
- refresh/reconnect does not depend on a permanent connection;
- snapshots include a monotonic last-observed event sequence when available;
- frontend ignores an older snapshot than one already rendered;
- polling stops at terminal state;
- hidden/background tabs may reduce cadence.

Alpha may replace polling with SSE/WebSocket while preserving the snapshot contract.

## 9. Progress Projection

Invariant: `UI progress = derived projection`.

Progress is read-only and derived from `RunState`, `RunEvent` and evidence.

No elapsed-time inference, fake percentage or independent progress state authority.

Mapping:

| UX state | Source authority |
| --- | --- |
| Entendiendo | `INSPECTING`, `PLANNING`, project inspection/plan evidence |
| Investigando | knowledge retrieval/selection/reference events while no later phase is active |
| Editando | `EDITING`, mutation/file-change evidence |
| Compilando | `BUILDING`, `BUILD_STARTED` until matching build completion |
| Probando | `VALIDATING_FUNCTIONAL`, runtime validation evidence |
| Verificando | artifact validation, validation completion, CompletionGate evaluation before terminal success |
| Reparando | `DIAGNOSING`, `CORRECTING`, failure/repair evidence |
| Entregando | `REPORTING` after required validation is satisfied |

Priority when multiple signals exist:

1. terminal `RunState`;
2. active repair;
3. runtime validation;
4. artifact/completion verification;
5. build;
6. edit/mutation;
7. knowledge activity;
8. inspect/plan.

Fallback uses recognized `RunState` mapping only. No invented stage is created.

## 10. Success / Failure / Repair

Product-facing execution status enum:

- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `BLOCKED`
- `LIMIT_REACHED`
- `INTERRUPTED`

These are derived presentation categories, not a new runtime state machine.

### Success

Invariant: `Success requires authoritative CompletionGate satisfaction`.

Success requires:

- productive `RunState` is successful/complete;
- CompletionGate satisfaction;
- required validation satisfied.

A build PASS alone is insufficient.

An artifact VALID alone is insufficient.

### Repair

Repair projection exists only from real diagnosis/correction/retry/revalidation evidence.

Conceptual `RepairSummary`:

- `active`
- `attempt_count`
- `problem_summary`
- `resolution_status`

### Failure

Human UX distinguishes supported cases such as:

- repairable/active repair;
- resolved repair;
- terminal failure;
- blocked;
- limit reached;
- infrastructure failure;
- incomplete/interrupted;
- invalid/stale artifact delivery condition.

Primary UX never exposes traceback/provider internals as the main message.

## 11. Evidence Contract

Evidence API is allowlist-based, not a generic raw-internals API.

### HumanEvidenceDTO

May include:

- requested/changed files summary;
- build summary;
- repair summary;
- runtime/Minecraft validation summary;
- completion summary;
- artifact summary.

### TechnicalEvidenceDTO

May include:

- Project/Task/Execution/run IDs;
- timestamps;
- run status;
- changed files;
- build attempts;
- validation summaries;
- runtime observations;
- failure classification;
- artifact SHA256;
- safe evidence references.

Forbidden:

- chain-of-thought;
- hidden reasoning;
- credentials;
- secrets;
- unrestricted provider payloads;
- unrestricted filesystem exposure;
- generic raw event/evidence dump endpoints.

Heavy evidence is referenced rather than duplicated.

Existing RunStorage redaction remains the first persistence defense; EvidenceService applies a second product/API allowlist.

## 12. JAR Delivery

Primary action:

`SAFE WEB DOWNLOAD`

Endpoint:

`GET /api/v1/deliveries/{delivery_id}/artifact`

Validation chain:

`Delivery exists → Project/Task/Execution ownership valid → authoritative successful completion → CompletionGate PASS → artifact identity matches → artifact VALID → artifact current → file exists → hash/currentness verified → response`

Invariant:

`Delivery requires successful completion + VALID + current + ownership`.

Response uses safe `Content-Disposition: attachment` filename generated server-side.

Browser never supplies the artifact filesystem path.

### Local location / reveal

Secondary action:

`POST /api/v1/deliveries/{delivery_id}/reveal`

Backend resolves trusted server-side artifact reference.

On Windows, local reveal may select/open containing folder using the resolved trusted path.

Browser never supplies reveal path.

## 13. HTTP / API Contract

Prefix: `/api/v1`.

Minimum operations:

```text
GET    /projects
POST   /projects
GET    /projects/{project_id}

POST   /projects/{project_id}/tasks
POST   /tasks/{task_id}/executions

GET    /executions/{execution_id}
GET    /executions/{execution_id}/evidence/human
GET    /executions/{execution_id}/evidence/technical

GET    /projects/{project_id}/history

GET    /deliveries/{delivery_id}
GET    /deliveries/{delivery_id}/artifact
POST   /deliveries/{delivery_id}/reveal
```

No DELETE API is required in v0.9.

No Cancel, pause, human-response or resume endpoint.

### Error model

Canonical safe envelope:

```text
error:
  code
  message
  request_id?
```

Important codes include:

- `PROJECT_NOT_FOUND`
- `WORKSPACE_INVALID`
- `WORKSPACE_UNAVAILABLE`
- `TASK_NOT_FOUND`
- `EXECUTION_NOT_FOUND`
- `EXECUTION_CAPACITY_REACHED`
- `EXECUTION_INTERRUPTED`
- `DELIVERY_NOT_FOUND`
- `ARTIFACT_NOT_CURRENT`
- `ARTIFACT_UNAVAILABLE`
- `CATALOG_CORRUPT`
- `CATALOG_VERSION_UNSUPPORTED`
- `SECURITY_REJECTED`

No internal traceback is returned as normal product UX.

## 14. Local Web Security

Localhost alone is not sufficient authorization.

### Network boundary

- Uvicorn binds to `127.0.0.1` by default.
- No wildcard `0.0.0.0` default.

### Host validation

Allow only expected local hosts such as:

- `localhost`
- `127.0.0.1`
- explicitly configured exact local host when administratively enabled.

### Origin validation

Mutating requests require an accepted same-origin `Origin`.

Foreign origins are rejected.

### CSRF

Use same-origin architecture plus server-generated CSRF token for mutating requests.

Frontend sends token in a custom header; backend validates it.

This does not imply SaaS authentication/account semantics.

### Additional requirements

- bounded JSON/request payload sizes;
- safe filenames;
- authorized workspace resolution only through Project records;
- path traversal rejection;
- existing `SecurePathResolver` preserved;
- existing `ToolExecutor` security preserved;
- Delivery ownership validation;
- evidence allowlists;
- secret redaction;
- safe error redaction.

No SaaS/multi-user security architecture is introduced in v0.9.

## 15. Provider Boundary

Invariant: `Provider/model/API keys = opaque`.

Provider/model/credentials remain server-side administrative/startup configuration.

Flow:

`administrative config/env → backend composition root → existing provider → RunController`

Normal frontend/API does not receive, store or modify:

- provider identity;
- model selector;
- API key;
- token mechanics;
- billing/credits.

No new provider abstraction is introduced without demonstrated need.

## 16. Settings Boundary

No mandatory USER_SETTING has been demonstrated for v0.9.

The Settings route/location may remain for Alpha-compatible navigation, but it must be truthful.

Valid v0.9 state may simply communicate:

`No user-configurable settings are available in this preview.`

No fake controls and no dev/admin provider/runtime configuration exposed as product settings.

## 17. Intervention

`REAL HUMAN INTERVENTION = DEFERRED`.

No:

- pause endpoint;
- human-response endpoint;
- resume endpoint;
- fake waiting-for-human backend state.

No accepted v0.9 Task may require intervention during execution.

AC-09 remains conditional on a future safe pause/response/continuation backend.

## 18. Cancellation / Resume

`GENERAL CANCELLATION = DEFERRED`.

`GENERAL RESUME = DEFERRED`.

No fake Cancel action or endpoint.

Browser refresh/reconnect is UI reconstruction, not runtime resume.

Server restart may reconstruct product metadata and persisted runtime evidence but does not resume an interrupted productive runtime.

## 19. Frontend UX Contract

Conceptual routes:

```text
/
/projects
/projects/:projectId
/executions/:executionId
/settings
```

Frontend responsibilities cover:

- Home;
- Projects layer;
- Project detail;
- Execution;
- Repair;
- Success;
- Failure;
- Details;
- artifact action;
- navigation/context restoration.

Execution UI consumes only HTTP DTOs.

Frontend never accesses directly:

- Python `RunState` objects;
- filesystem paths as authority;
- provider internals;
- RunStorage filesystem layout.

## 20. Accessibility Architecture

Use semantic HTML before ARIA.

Requirements:

- buttons are real buttons;
- links are real links;
- forms/inputs are labelled;
- keyboard navigation works;
- focus is visible;
- dialogs use correct semantics;
- modal focus trap and restoration;
- Escape closes dismissible layers;
- execution status updates use restrained accessible announcement mechanisms such as `aria-live`;
- polling must not cause repeated duplicate announcements when semantic state did not change;
- reduced-motion support when motion is present;
- state is never conveyed by color alone.

## 21. Failure / Recovery

Required product behavior:

| Condition | Behavior |
| --- | --- |
| malformed catalog | Product layer degraded/fail closed |
| missing Project workspace | Project remains visible; new Execution disabled |
| missing Execution | safe 404/product error |
| stale RunStorage reference | degraded historical/Execution representation |
| browser refresh | reconstruct from API |
| browser reconnect | polling reconstructs snapshot |
| server restart + terminal run | reconstruct normally |
| server restart + non-terminal run | `INTERRUPTED / UNKNOWN` product projection; no resume |
| runtime exception | safe infrastructure/terminal projection |
| artifact missing | Delivery unavailable |
| artifact stale | reject delivery |
| artifact corrupt | reject delivery |
| evidence missing | mark evidence unavailable; never invent facts |
| frontend build unavailable | backend health may remain but UI is unavailable |

Critical distinction:

`UI/metadata recovery != runtime resume`.

`INTERRUPTED / UNKNOWN` is only a derived product projection. It is not a `RunState`, runtime transition, resume state or second state machine.

## 22. Concurrency

v0.9 policy:

`ONE PRODUCTIVE EXECUTION GLOBALLY`.

Reads and downloads may execute concurrently.

Catalog writes use the single in-process `RLock`.

Two simultaneous productive start requests:

- first accepted;
- second returns `409 EXECUTION_CAPACITY_REACHED`.

No scheduler, job queue or distributed concurrency system is built in v0.9.

## 23. Module / Package Boundary

Proposed additions:

```text
src/pd_agent/
  product/
    models.py
    catalog.py
    projects.py
    execution.py
    evidence.py
    delivery.py

  web/
    app.py
    api/
      projects.py
      executions.py
      deliveries.py
    dto.py
    security.py

frontend/
  src/
  ...
```

Existing runtime-oriented packages remain structurally intact.

Dependency direction:

`frontend → HTTP → web → product/application → existing runtime`

Existing runtime must not import Web/product presentation modules.

No unnecessary v0.8 reorganization.

## 24. Test Architecture

### Python deterministic tests

Use pytest for:

- ProductCatalog schema;
- atomic writes;
- corruption/version handling;
- Project relationships;
- workspace registration;
- ExecutionService;
- capacity/concurrency policy;
- progress mapping;
- Human/Technical Evidence allowlists;
- Delivery validation;
- stale/current artifact behavior;
- HTTP/API validation;
- Host/Origin/CSRF;
- traversal/security;
- secret filtering;
- server-restart/degraded projections.

### Frontend deterministic tests

Use `Vitest + React Testing Library` for:

- navigation;
- Execution snapshots;
- repair/success/failure states;
- modal focus behavior;
- keyboard behavior;
- artifact action;
- stale/error handling.

### Browser integration

Use targeted `Playwright` for critical integrated Web flows only:

`Home → Project → Task → Execution → progress → result → Details → JAR action`

and critical accessibility/navigation behavior.

### Productive integration

Final v0.9 validation must prove real:

`Web/API → productive runtime`

Fake-backend-only tests cannot establish final v0.9 PASS.

Live provider/Minecraft validation remains controlled integration validation rather than default unit-test behavior.

v0.8 regression preservation remains mandatory before final v0.9 closure.

## 25. Alpha Evolution

v0.9 implementation details are replaceable while preserving product contracts:

| v0.9 | Future replacement | Preserved contract |
| --- | --- | --- |
| versioned JSON catalog | DB/cloud persistence | Project/Task/Execution/Delivery identities |
| ThreadPoolExecutor | worker infrastructure | Execution API/lifecycle observation contract |
| one active Execution | scheduler/concurrency | Execution semantics |
| polling | SSE/WebSocket | ExecutionSnapshot semantics |
| localhost deployment | Managed deployment | Web/application boundary |
| backend-served static frontend | separate deployment/CDN | frontend HTTP contracts |
| startup provider config | Managed routing | provider opacity |

No v0.9 decision requires fundamental redesign of the approved product model.

## 26. Dependencies

### Python product dependencies

Add only:

- `fastapi`
- `uvicorn`

Do not add:

- SQLAlchemy;
- Redis;
- Celery;
- WebSocket infrastructure.

### Frontend

Runtime:

- `react`
- `react-dom`

Build/dev/test:

- `typescript`
- `vite`
- Vite React plugin
- `vitest`
- React Testing Library

Targeted browser test dependency:

- Playwright

No large UI framework is required initially. PD Agent-owned components/CSS should implement the approved visual direction.

## 27. RFC Decisions / ADR Candidates

Closed decisions:

| Decision | Choice |
| --- | --- |
| HTTP framework | FastAPI |
| server | Uvicorn |
| frontend | React + TypeScript + Vite |
| application services | ProjectService / ExecutionService / EvidenceService / DeliveryService |
| background | ThreadPoolExecutor |
| productive capacity | one Execution globally |
| observation | polling |
| IDs | UUIDv4 |
| execution/run mapping | same opaque UUID in v0.9 |
| ProductCatalog | versioned JSON |
| writes | temp + flush + replace |
| locking | in-process RLock |
| workspace | explicit canonical registration |
| Delivery access | trusted Delivery IDs |
| local reveal | trusted server-side action |
| progress | RunState/RunEvent/evidence projection |
| evidence | explicit DTO allowlists |
| Web security | loopback + Host + Origin + CSRF + filesystem boundaries |
| package layout | product / web / frontend |
| tests | pytest + Vitest/RTL + targeted Playwright |

Potential later ADR candidates:

1. React/Vite frontend boundary.
2. ProductCatalog persistence strategy.
3. Execution dispatch/observation architecture.

These ADRs are documentation candidates, not separate v0.9 implementation systems.

## 28. DESIGN / AC Traceability

The RFC preserves `PD_AGENT_V0.9_DESIGN` and the Product/UX/UI AC-01..AC-25 without scope change.

| AC | RFC mechanism |
| --- | --- |
| AC-01 | React frontend preserves Alpha-aligned Home structure |
| AC-02 | Project Task creation accepts natural-language request |
| AC-03 | Project/Task/Execution ownership contracts |
| AC-04 | ExecutionService dispatches real RunController/productive runtime |
| AC-05 | snapshot/progress derives only from authoritative runtime facts/evidence |
| AC-06 | no percentage/time fake progress |
| AC-07 | human ExecutionSnapshot/UX independent of raw logs |
| AC-08 | repair projection only from real repair evidence |
| AC-09 | conditional and not implemented; requires future safe intervention backend |
| AC-10 | safe human Failure DTO/error UX |
| AC-11 | success requires CompletionGate/required validation |
| AC-12 | DeliveryService provides safe valid/current JAR download/location |
| AC-13 | HumanEvidenceDTO |
| AC-14 | TechnicalEvidenceDTO allowlist excludes chain-of-thought/secrets |
| AC-15 | stable Project distinct from Task/Execution |
| AC-16 | another Task may be created from same Project |
| AC-17 | ProductCatalog/history API |
| AC-18 | truthful minimal Settings only |
| AC-19 | provider/model/API keys remain opaque |
| AC-20 | no billing/credits endpoints or UI |
| AC-21 | frontend routes/context restoration |
| AC-22 | modal/back/close/Escape/focus/scroll contract |
| AC-23 | keyboard/accessibility architecture |
| AC-24 | React/CSS frontend implements approved PD Agent visual identity |
| AC-25 | replaceable infrastructure preserves stable product contracts toward Alpha |

No AC requires a Product Spec or DESIGN change.

## Deferred Capabilities

Outside v0.9:

- general cancellation;
- general resume;
- real human intervention lifecycle;
- distributed workers;
- general job scheduler;
- cloud persistence;
- SaaS accounts/authentication;
- collaboration;
- billing/credits;
- commercial Managed backend;
- provider/model selection UX;
- complete Settings;
- project branches/version manager;
- advanced delivery management;
- final Alpha polish;
- final mobile product;
- Multi-Agent;
- Paper;
- NeoForge;
- Velocity.

## Final Invariants

`RunState = only execution state machine`

`ExecutionService dispatches; it does not decide lifecycle`

`UI progress = derived projection`

`Project != Task != Execution`

`Project identity != workspace fingerprint`

`Success requires authoritative CompletionGate satisfaction`

`Delivery requires successful completion + VALID + current + ownership`

`RunStorage = runtime/evidence authority`

`ProductCatalog = product metadata/index authority`

`Frontend = presentation/client state only`

`Provider/model/API keys = opaque`

`No fake progress`

`No fake intervention`

`No fake cancellation`

## Final RFC Verdict

`V0_9_RFC_READY`

The approved RFC defines an implementable v0.9 architecture without changing the approved Product Spec or DESIGN, without introducing a second runtime lifecycle, and without overbuilding infrastructure beyond the internal Web/UI integration preview.
