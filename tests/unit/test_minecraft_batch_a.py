from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pd_agent.core import SecurityViolation, ToolValidationError
from pd_agent.minecraft import (
    MinecraftEvidencePaths,
    MinecraftLaunchPlan,
    MinecraftProcessEvidence,
    MinecraftRuntimeEvidence,
    MinecraftTargetMetadata,
    MinecraftTestResult,
    MinecraftTestRunner,
    MinecraftTestSpec,
    MinecraftTestStatus,
    MinecraftTestValidationError,
    UnsupportedMinecraftEnvironmentError,
)
from tests.fixtures.artifact_projects import write_manifest_jar


def _make_jar(root: Path, name: str = "target.jar") -> Path:
    return write_manifest_jar(
        root / "build" / "libs" / name,
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "pdagentl11",
                "version": "1.0.0",
                "environment": "*",
                "entrypoints": {
                    "main": ["dev.pdpunto.l11.ExampleMod"],
                },
            }
        ),
    )


def _runner(root: Path) -> MinecraftTestRunner:
    return MinecraftTestRunner(project_root=root)


def test_status_enum_is_closed_and_terminal() -> None:
    assert [item.value for item in MinecraftTestStatus] == [
        "PASS",
        "FAIL",
        "CRASH",
        "TIMEOUT",
        "INFRA_ERROR",
    ]
    assert all(item.is_terminal() for item in MinecraftTestStatus)
    assert MinecraftTestStatus.PASS.is_pass
    assert not MinecraftTestStatus.INFRA_ERROR.is_pass


def test_spec_validation_and_round_trip(tmp_path: Path) -> None:
    jar = _make_jar(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )

    assert spec.to_dict() == {
        "target_jar": "build/libs/target.jar",
        "target_mod_id": "pdagentl11",
        "minecraft_version": "1.21.11",
        "loader_version": "0.19.3",
        "test_id": "batch-a",
        "timeout_seconds": 90,
        "expect_neighbor_update": False,
    }
    assert MinecraftTestSpec.from_dict(spec.to_dict()) == spec


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_mod_id": ""},
        {"target_mod_id": "BadMod"},
        {"minecraft_version": ""},
        {"loader_version": ""},
        {"test_id": ""},
        {"timeout_seconds": 0},
    ],
)
def test_spec_rejects_invalid_values(tmp_path: Path, kwargs: dict[str, object]) -> None:
    jar = _make_jar(tmp_path)
    payload = {
        "target_jar": Path("build/libs/target.jar"),
        "target_mod_id": "pdagentl11",
        "minecraft_version": "1.21.11",
        "loader_version": "0.19.3",
        "test_id": "batch-a",
        "timeout_seconds": 90,
    }
    payload.update(kwargs)

    with pytest.raises(ValueError):
        MinecraftTestSpec(**payload)


def test_target_metadata_hash_and_paths(tmp_path: Path) -> None:
    jar = _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )

    metadata = runner.validate_target(spec, java_version="21")

    assert metadata.path == jar
    assert metadata.size_bytes == jar.stat().st_size
    assert len(metadata.sha256) == 64
    assert metadata.mod_id == "pdagentl11"
    assert metadata.minecraft_version == "1.21.11"
    assert metadata.loader_version == "0.19.3"
    assert metadata.java_version == "21"
    assert MinecraftTargetMetadata.from_dict(metadata.to_dict()) == metadata


def test_target_absolute_path_is_rejected(tmp_path: Path) -> None:
    jar = _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=jar,
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )

    with pytest.raises(SecurityViolation):
        runner.validate_target(spec, java_version="21")


def test_target_missing_and_non_jar_are_rejected(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    missing = MinecraftTestSpec(
        target_jar=Path("build/libs/missing.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )
    text_file = tmp_path / "build" / "libs" / "target.txt"
    text_file.parent.mkdir(parents=True, exist_ok=True)
    text_file.write_text("not a jar", encoding="utf-8")
    not_jar = MinecraftTestSpec(
        target_jar=Path("build/libs/target.txt"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )

    with pytest.raises(ToolValidationError):
        runner.validate_target(missing, java_version="21")
    with pytest.raises(MinecraftTestValidationError):
        runner.validate_target(not_jar, java_version="21")


def test_evidence_paths_are_isolated_by_run_id(tmp_path: Path) -> None:
    paths_a = MinecraftEvidencePaths.for_run(tmp_path / "evidence" / "minecraft", "run-a")
    paths_b = MinecraftEvidencePaths.for_run(tmp_path / "evidence" / "minecraft", "run-b")

    assert paths_a.root != paths_b.root
    assert paths_a.spec_json.name == "spec.json"
    assert paths_a.target_json.name == "target.json"
    assert paths_a.crash_reports_dir.name == "crash-reports"
    assert paths_a.root.exists()
    assert paths_a.crash_reports_dir.exists()
    assert paths_b.root.exists()


def test_launch_plan_serialization(tmp_path: Path) -> None:
    jar = _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )

    plan = runner.build_launch_plan(spec, run_id="run-a", java_version="21")

    assert plan.run_id == "run-a"
    assert plan.evidence_paths.root.name == "run-a"
    assert dict(plan.system_properties)["pd.agent.minecraft.target_mod_id"] == "pdagentl11"
    assert dict(plan.system_properties)["pd.agent.targetEntrypointClass"] == "dev.pdpunto.l11.ExampleMod"
    assert dict(plan.system_properties)["pd.agent.minecraft.expect_neighbor_update"] == "false"
    assert MinecraftLaunchPlan.from_dict(plan.to_dict()) == plan


def test_process_and_runtime_evidence_serialization(tmp_path: Path) -> None:
    started = datetime.now(timezone.utc)
    finished = started + timedelta(microseconds=1)
    process = MinecraftProcessEvidence(
        command_display="gradlew.bat",
        cwd=tmp_path,
        started_at=started,
        finished_at=finished,
        duration_seconds=1.5,
        exit_code=0,
        timed_out=False,
        stdout_log=tmp_path / "stdout.log",
        stderr_log=tmp_path / "stderr.log",
        metadata={"ok": True},
    )
    runtime = MinecraftRuntimeEvidence(
        harness_result_path=tmp_path / "harness-result.json",
        latest_log_path=tmp_path / "latest.log",
        crash_reports_dir=tmp_path / "crash-reports",
        metadata={"phase": "batch-a"},
    )

    assert MinecraftProcessEvidence.from_dict(process.to_dict()) == process
    assert MinecraftRuntimeEvidence.from_dict(runtime.to_dict()) == runtime


def test_result_serialization_and_pass_property(tmp_path: Path) -> None:
    jar = _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )
    target = runner.validate_target(spec, java_version="21")
    evidence_paths = runner.build_evidence_paths("run-a")
    launch_plan = runner.build_launch_plan(spec, run_id="run-a", java_version="21")
    result = MinecraftTestResult(
        run_id="run-a",
        status=MinecraftTestStatus.INFRA_ERROR,
        reason="not launched",
        spec=spec,
        target=target,
        evidence_paths=evidence_paths,
        launch_plan=launch_plan,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        duration_seconds=0.0,
        metadata={"phase": "batch-a"},
    )

    encoded = result.to_dict()
    assert encoded["status"] == "INFRA_ERROR"
    assert encoded["spec"]["target_mod_id"] == "pdagentl11"
    assert encoded["target"]["sha256"] == target.sha256
    assert not result.passed
    assert MinecraftTestResult.from_dict(encoded) == result
    assert json.dumps(encoded, sort_keys=True) == json.dumps(result.to_dict(), sort_keys=True)


def test_runner_prepares_contracts_without_launching_minecraft(tmp_path: Path) -> None:
    jar = _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )

    result = runner.prepare_run(spec, run_id="run-a", java_version="21")

    assert result.status is MinecraftTestStatus.INFRA_ERROR
    assert result.reason == "Minecraft runtime launch not implemented in Batch A"
    assert result.evidence_paths.spec_json.exists()
    assert result.evidence_paths.target_json.exists()
    assert not result.evidence_paths.result_json.exists()


def test_runner_rejects_unsupported_environment(tmp_path: Path) -> None:
    jar = _make_jar(tmp_path)
    runner = _runner(tmp_path)
    spec = MinecraftTestSpec(
        target_jar=Path("build/libs/target.jar"),
        target_mod_id="pdagentl11",
        minecraft_version="1.20.1",
        loader_version="0.19.3",
        test_id="batch-a",
        timeout_seconds=90,
    )

    with pytest.raises(UnsupportedMinecraftEnvironmentError):
        runner.validate_spec(spec, java_version="21")
