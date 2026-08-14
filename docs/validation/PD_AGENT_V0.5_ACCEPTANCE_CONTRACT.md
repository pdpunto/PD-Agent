# PD Agent v0.5 Acceptance Contract Validation

Status: PASS
Date: 2026-08-14

## Repository

- Repository: `pdpunto/PD-Agent`
- Branch: `main`
- Baseline commit: `a84b183667dcf6ae51fc766b817e82840bc3a72c`
- HEAD: `a84b183667dcf6ae51fc766b817e82840bc3a72c`
- origin/main: `a84b183667dcf6ae51fc766b817e82840bc3a72c`

## Working Tree

- Tracked tree: clean before this F2 change
- Preexisting untracked diagnostics: `scripts/benchmark/diagnostics/`

## Audit Scope

Audited against:

- `src/pd_agent/benchmark/models.py`
- `src/pd_agent/benchmark/catalog.py`
- `src/pd_agent/benchmark/executor.py`
- `src/pd_agent/benchmark/classifier.py`
- `src/pd_agent/benchmark/collector.py`
- `src/pd_agent/benchmark/scheduler.py`
- `src/pd_agent/benchmark/runner.py`
- current datasets and tasks
- benchmark unit tests

## Inventory of Existing Contracts

### BenchmarkTask

- Requirement user-facing: EXISTS via `prompt`
- Project/fixture ref: EXISTS via `fixture.fixture_ref`
- Project identity: EXISTS via `fixture.fixture_identity` and `identity_algorithm`
- Behavioral acceptance: EXISTS via `acceptance`
- Runtime observation contract: PARTIAL if interpreted as a dedicated field on `MinecraftTestSpec`; EXISTS in practice via generic `BenchmarkAcceptanceSpec.spec`
- Preservation invariants: EXISTS via `BenchmarkAcceptanceSpec.spec` and task metadata
- Required changed-file behavior: EXISTS via `BenchmarkValidationRequirements.source_change` and run evidence
- Runtime PASS/FAIL: EXISTS via `BenchmarkTaskOutcome`
- Artifact requirement: EXISTS via `BenchmarkValidationRequirements.artifact`
- Minecraft requirement: EXISTS via `BenchmarkValidationRequirements.minecraft`
- Evidence requirements: EXISTS via `BenchmarkRun.evidence_refs`, `BenchmarkCollection`, `FinalReport`
- Versions: EXISTS via `BenchmarkEnvironmentRequirements`
- Task version: EXISTS via `task_version`
- Dataset version: EXISTS via `BenchmarkDataset.dataset_version`

### BenchmarkAcceptanceSpec

- Behavioral contract container: EXISTS
- Solution leakage boundary: EXISTS by design because prompt and acceptance are separate fields
- Generic runtime observation payload: EXISTS via `spec: Mapping[str, Any]`
- Notes / metadata: EXISTS

### BenchmarkConfig

- Provider/model identity: EXISTS
- Brain mode: EXISTS
- Execution limits: EXISTS
- Repetition target: EXISTS

### BenchmarkRun / BenchmarkExecutionResult / BenchmarkCollection

- Persisted evidence: EXISTS
- Logical provider request accounting: EXISTS
- Failure taxonomy mapping: EXISTS
- Runtime usage / metrics: EXISTS

### MinecraftTestSpec

- Concrete harness contract: EXISTS
- Target jar / mod id / versions / test id / timeout / neighbor expectation: EXISTS
- Generic observation contract: PARTIAL in the sense that it is concrete and harness-facing, but v0.5 does not require a new generic enum or schema field because the acceptance layer already carries extensible observation metadata.

## Decision

Decision A selected:

- NO CODE CHANGE required in core benchmark models for F2.
- Existing contracts already express the needed v0.5 separation between user-facing requirement and acceptance metadata.
- The extensibility point for future v0.5 families is `BenchmarkAcceptanceSpec.spec`, not a new enum or a large schema extension.

## Project Base Reference Behavior

Confirmed:

- `fixture_ref` can reference `benchmarks/projects/v0_5_fabric_base`
- `BenchmarkCatalog` resolves the reference relative to benchmark root
- identity hashing remains stable and reproducible
- no new special-case path handling is required

## Starting-State Strategy

Recommended strategy for future tasks:

- keep the pinned project base as the common root
- use optional task metadata to describe a reproducible starting-state variant when needed
- if a future task needs a physically distinct starting tree, give it its own fixture identity

This keeps F2 generic and avoids copying the whole base for every task.

## Failure Taxonomy Mapping

Preserved mapping:

- PASS -> `COMPLETED + PASS`
- FUNCTIONAL_FAIL -> `COMPLETED + FAIL`
- AGENT_FAIL -> `failure_origin=AGENT`
- BLOCKED -> `BLOCKED`
- INVALID -> `INVALID`

No new enum is needed.

## Synthetic Families Covered

The contract can represent, without creating official tasks yet:

- Family A: registry/content, server-observable
- Family B: source + resource/data
- Family C: multi-file server-side behavior

## Tests Executed

- `python -m compileall src scripts tests`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q tests\\unit\\test_v0_5_acceptance_contract.py tests\\unit\\test_benchmark_models.py tests\\unit\\test_benchmark_catalog.py tests\\unit\\test_benchmark_classifier.py tests\\unit\\test_benchmark_executor.py tests\\unit\\test_benchmark_dataset_v0_4.py tests\\unit\\test_v0_5_project_base.py`
- `.\\.venv-l0fix\\Scripts\\python.exe -m pytest -q`

## Results

- Compile: PASS
- Focused tests: PASS
- Full suite: PASS

## Risks / Limitations

- `scripts/benchmark/diagnostics/` remains preexisting and untracked.
- F2 does not create the official v0.5 tasks yet.
- F2 intentionally avoids harness changes and live API calls.

## Final Verdict

F2 accepted as the dataset / acceptance contract for PD Agent v0.5.
