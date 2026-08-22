from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pd_agent.benchmark import (
    BenchmarkAcceptanceSpec,
    BenchmarkCatalog,
    BenchmarkConfig,
    BenchmarkDataset,
    BenchmarkExecutor,
    BenchmarkFixtureReference,
    BenchmarkTask,
    BenchmarkTaskReference,
    BenchmarkValidationRequirements,
)
from pd_agent.benchmark.models import BenchmarkEnvironmentRequirements
from pd_agent.benchmark.workspace import FIXTURE_IDENTITY_ALGORITHM, compute_fixture_identity
from pd_agent.core import ArtifactResult, BuildResult, RunState, RunStatus
from pd_agent.reporting import FinalReport


ROOT = Path(__file__).resolve().parents[2]
PROJECT_BASE = ROOT / "benchmarks" / "projects" / "v0_5_fabric_base"


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _environment() -> BenchmarkEnvironmentRequirements:
    return BenchmarkEnvironmentRequirements(
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        loom_version="1.13.3",
        yarn_version="1.21.11+build.6",
        java_version="21",
        fabric_api_version="0.122.0+1.21.11",
        extra={"platform": "fabric"},
    )


def _validation() -> BenchmarkValidationRequirements:
    return BenchmarkValidationRequirements(build=True, artifact=True, minecraft=True, source_change=True)


def _synthetic_acceptance(*, family: str) -> BenchmarkAcceptanceSpec:
    families: dict[str, dict[str, object]] = {
        "A": {
            "project_base_ref": "projects/v0_5_fabric_base",
            "observation_type": "server_registry_presence",
            "expectations": {
                "observable": "registry_entry_present",
                "identifier": "example:feature",
            },
            "preservation_invariants": {
                "mod_id": "examplemod",
                "entrypoints": {"main": ["com.example.examplemod.ExampleMod"]},
            },
            "evidence_requirements": {
                "runtime": True,
                "artifact": True,
            },
        },
        "B": {
            "project_base_ref": "projects/v0_5_fabric_base",
            "observation_type": "source_plus_resource",
            "expectations": {
                "source_file": "src/main/java/com/example/examplemod/ExampleMod.java",
                "resource_file": "src/main/resources/fabric.mod.json",
            },
            "preservation_invariants": {
                "mod_id": "examplemod",
                "entrypoints": {"main": ["com.example.examplemod.ExampleMod"]},
                "resource_contract": "preserve existing metadata",
            },
            "evidence_requirements": {
                "runtime": True,
                "artifact": True,
                "changed_files": True,
            },
        },
        "C": {
            "project_base_ref": "projects/v0_5_fabric_base",
            "observation_type": "server_side_multi_file_behavior",
            "expectations": {
                "observable": "deterministic server-side state change",
                "files": ["src/main/java/com/example/examplemod/ExampleMod.java"],
            },
            "preservation_invariants": {
                "mod_id": "examplemod",
                "entrypoints": {"main": ["com.example.examplemod.ExampleMod"]},
                "preserve_unrelated_sources": True,
            },
            "evidence_requirements": {
                "runtime": True,
                "artifact": True,
                "multi_file": True,
            },
        },
    }
    return BenchmarkAcceptanceSpec(
        acceptance_type="fabric_feature",
        spec=families[family],
        notes=(f"synthetic-family-{family}",),
    )


def _task(*, family: str) -> BenchmarkTask:
    return BenchmarkTask(
        task_id=f"F2-{family}",
        task_version="1",
        description=f"Synthetic v0.5 family {family}",
        prompt="Implement the requested Fabric feature for the project base.",
        fixture=BenchmarkFixtureReference(
            fixture_ref="projects/v0_5_fabric_base",
            fixture_identity=None,
            identity_algorithm=FIXTURE_IDENTITY_ALGORITHM,
            metadata={"starting_state_strategy": "pinned_base"},
        ),
        validation=_validation(),
        acceptance=_synthetic_acceptance(family=family),
        environment=_environment(),
        tags=("v0.5", "synthetic"),
        notes=("contract-only",),
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


class _PromptCapturingController:
    last_init: dict[str, object] = {}
    last_run: dict[str, object] = {}

    def __init__(self, **kwargs: object) -> None:
        self.storage = kwargs["storage"]
        self.last_init = dict(kwargs)
        _PromptCapturingController.last_init = self.last_init

    def run(self, project_root: Path, task: str, *, external_context=(), model_config=None, pending_mutation_targets=()):  # noqa: ANN001
        _PromptCapturingController.last_run = {
            "project_root": project_root,
            "task": task,
            "external_context": tuple(external_context),
            "model_config": dict(model_config or {}),
        }
        artifact_path = project_root / "build" / "libs" / "mod.jar"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("jar", encoding="utf-8")
        build = BuildResult(
            attempt=1,
            command_display="gradlew build",
            cwd=project_root,
            started_at=_utc("2026-08-14T10:00:10"),
            duration_seconds=2.0,
            exit_code=0,
            stdout_log="BUILD SUCCESSFUL",
            stderr_log="",
        )
        run_state = RunState(
            run_id="11111111-1111-4111-8111-111111111111",
            project_root=project_root,
            task=task,
            state=RunStatus.COMPLETED,
            started_at=_utc("2026-08-14T10:00:00"),
            changed_files=("src/main/java/com/example/examplemod/ExampleMod.java",),
            build_results=(build,),
            artifact_result=ArtifactResult(
                path=artifact_path,
                size=123,
                timestamp=_utc("2026-08-14T10:00:11"),
                classification="VALID",
                metadata={"sha256": "abc"},
            ),
            termination_reason="completed",
        )
        final_report = FinalReport(
            run_id=run_state.run_id,
            final_state=RunStatus.COMPLETED,
            summary="ok",
            project=str(project_root),
            requested_task=task,
            files_changed=run_state.changed_files,
            build_attempts=run_state.build_results,
            final_build=build,
            artifact=run_state.artifact_result,
            termination_reason="completed",
            evidence_refs=(),
            generated_at=_utc("2026-08-14T10:00:12"),
        )
        return run_state, final_report


def test_v0_5_contract_round_trips_and_keeps_prompt_separate_from_acceptance() -> None:
    task = _task(family="A")
    payload = task.to_dict()

    assert task.prompt == "Implement the requested Fabric feature for the project base."
    assert payload["prompt"] == task.prompt
    assert payload["acceptance"]["spec"]["project_base_ref"] == "projects/v0_5_fabric_base"
    assert payload["acceptance"]["spec"]["observation_type"] == "server_registry_presence"
    assert payload["acceptance"]["spec"]["preservation_invariants"]["mod_id"] == "examplemod"
    assert "runtime_observation" not in task.prompt
    assert "target_class" not in payload["acceptance"]["spec"]
    assert "method_name" not in payload["acceptance"]["spec"]
    assert BenchmarkTask.from_dict(payload) == task


def test_v0_5_project_base_reference_resolves_through_catalog(tmp_path: Path) -> None:
    benchmark_root = tmp_path / "benchmarks"
    project_base = benchmark_root / "projects" / "v0_5_fabric_base"
    shutil.copytree(PROJECT_BASE, project_base)
    fixture_identity = compute_fixture_identity(project_base)

    dataset = BenchmarkDataset(
        dataset_id="pd-agent-fabric-v0-5",
        dataset_version="0.5.0",
        tasks=(BenchmarkTaskReference(task_id="F2-A", task_version="1"),),
        description="v0.5 contract dataset",
        tags=("v0.5",),
    )
    task = BenchmarkTask.from_dict(
        {
            **_task(family="A").to_dict(),
            "fixture": {
                "schema_version": 1,
                "fixture_ref": "projects/v0_5_fabric_base",
                "fixture_identity": fixture_identity,
                "identity_algorithm": FIXTURE_IDENTITY_ALGORITHM,
                "metadata": {"starting_state_strategy": "pinned_base"},
            },
        }
    )
    _write_json(benchmark_root / "datasets" / "pd-agent-fabric-v0-5.json", dataset.to_dict())
    _write_json(benchmark_root / "tasks" / "F2-A.json", task.to_dict())

    catalog = BenchmarkCatalog.load(benchmark_root)

    assert catalog.fixture_paths[("F2-A", "1")] == project_base.resolve()
    assert catalog.fixture_identities[("F2-A", "1")] == fixture_identity
    assert catalog.task_for("F2-A", "1").fixture.fixture_ref == "projects/v0_5_fabric_base"


@pytest.mark.parametrize("family", ["A", "B", "C"])
def test_v0_5_synthetic_families_round_trip_without_solution_specific_fields(family: str) -> None:
    task = _task(family=family)
    acceptance_spec = task.acceptance.spec

    assert task.acceptance.acceptance_type == "fabric_feature"
    assert task.task_version == "1"
    assert task.to_dict()["fixture"]["fixture_ref"] == "projects/v0_5_fabric_base"
    assert task.to_dict()["acceptance"]["spec"] == acceptance_spec
    assert "solution" not in acceptance_spec
    assert "expected_class_name" not in acceptance_spec
    assert "target_method" not in acceptance_spec
    assert "api_signature" not in acceptance_spec
    assert BenchmarkTask.from_dict(task.to_dict()) == task


def test_v0_5_acceptance_is_not_leaked_into_provider_prompt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pd_agent.benchmark.executor.RunController", _PromptCapturingController)
    executor = BenchmarkExecutor(provider=object(), build_runner=object(), artifact_validator=object())
    task = BenchmarkTask.from_dict(
        {
            **_task(family="B").to_dict(),
            "validation": {
                "schema_version": 1,
                "build": True,
                "artifact": True,
                "minecraft": False,
                "source_change": True,
            },
        }
    )
    config = BenchmarkConfig(
        config_id="cfg-v0-5",
        provider="gemini",
        model="gemini-3.5-flash-lite",
        brain_enabled=False,
        model_config={"temperature": 0.2},
        provider_config={"timeout_seconds": 60},
        knowledge_config={},
        target_repetition_count=1,
    )
    scheduled_attempt = type(
        "Attempt",
        (),
        {"scheduled_attempt_id": "attempt-v0-5", "attempt_index": 1, "repetition_index": 0},
    )()

    result = executor.execute(
        task,
        config,
        scheduled_attempt,
        fixture_root=PROJECT_BASE,
        execution_root=tmp_path / "exec",
    )

    assert _PromptCapturingController.last_run["task"] == task.prompt
    assert task.acceptance.spec["project_base_ref"] not in _PromptCapturingController.last_run["task"]
    assert _PromptCapturingController.last_run["external_context"] == ()
    assert result.collection.tool_call_count == 0
