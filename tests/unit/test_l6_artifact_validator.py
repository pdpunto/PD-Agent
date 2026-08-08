from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pd_agent import ArtifactClassification, ArtifactValidator
from pd_agent.core import BuildResult
from pd_agent.project import ProjectInspector
from pd_agent.reporting import RunEventType, RunStorage

from tests.fixtures.artifact_projects import (
    make_multimodule_artifact_project,
    make_simple_artifact_project,
    utc_now,
    write_corrupt_jar,
    write_empty_jar,
    write_jar,
    write_manifest_jar,
)


def _inspect(root: Path):
    return ProjectInspector().inspect(root)


def _build_result(started_at: datetime, exit_code: int = 0) -> BuildResult:
    return BuildResult(
        attempt=1,
        command_display="gradlew build",
        cwd=Path("C:/dev/project"),
        started_at=started_at,
        duration_seconds=1.0,
        exit_code=exit_code,
        stdout_log="build",
        stderr_log="",
    )


def test_valid_jar_emits_event(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "valid")
    snapshot = _inspect(root)
    started_at = utc_now()
    jar = write_manifest_jar(
        root / "build" / "libs" / "buildsimple-1.0.0.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "buildsimple",
                "version": "1.0.0",
                "environment": "*",
            }
        ),
        mtime=started_at + timedelta(seconds=5),
    )
    storage = RunStorage(root / "runs")
    validator = ArtifactValidator(reporting=storage)
    run_id = "11111111-1111-1111-1111-111111111111"

    result = validator.validate(snapshot, _build_result(started_at), run_id=run_id)

    assert result.classification == ArtifactClassification.VALID.value
    assert result.path == jar
    assert result.metadata["mod_id"] == "buildsimple"
    assert result.metadata["version"] == "1.0.0"
    assert result.metadata["valid"] is True
    assert result.metadata["candidate_count"] == 1
    assert result.metadata["jar_entries_checked"] >= 1

    events = [
        json.loads(line)
        for line in storage.paths_for(run_id).events_jsonl.read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["event_type"] == RunEventType.ARTIFACT_VALIDATED.value
    assert events[-1]["payload"]["valid"] is True
    assert events[-1]["payload"]["path"] == "build/libs/buildsimple-1.0.0.jar"


def test_empty_jar_is_invalid(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "empty")
    snapshot = _inspect(root)
    write_empty_jar(root / "build" / "libs" / "buildsimple-1.0.0.jar")

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.EMPTY.value
    assert result.size == 0


def test_corrupt_jar_is_invalid(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "corrupt")
    snapshot = _inspect(root)
    write_corrupt_jar(root / "build" / "libs" / "buildsimple-1.0.0.jar")

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.CORRUPT.value


def test_sources_only_is_missing(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "sources")
    snapshot = _inspect(root)
    write_manifest_jar(
        root / "build" / "libs" / "buildsimple-1.0.0-sources.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "buildsimple",
                "version": "1.0.0",
                "environment": "*",
            }
        ),
    )

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.MISSING.value
    assert result.path is None


def test_jar_without_fabric_mod_json_is_invalid(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "manifest")
    snapshot = _inspect(root)
    write_jar(
        root / "build" / "libs" / "buildsimple-1.0.0.jar",
        files={"META-INF/MANIFEST.MF": "Manifest-Version: 1.0\n"},
    )

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.INVALID_METADATA.value
    assert "missing root fabric.mod.json" in result.metadata["issues"]


def test_multiple_candidates_are_ambiguous(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "ambiguous")
    snapshot = _inspect(root)
    started_at = utc_now()
    for name in ("a.jar", "b.jar"):
        write_manifest_jar(
            root / "build" / "libs" / name,
            manifest=json.dumps(
                {
                    "schemaVersion": 1,
                    "id": "buildsimple",
                    "version": "1.0.0",
                    "environment": "*",
                }
            ),
            mtime=started_at + timedelta(seconds=5),
        )

    result = ArtifactValidator().validate(snapshot, _build_result(started_at))

    assert result.classification == ArtifactClassification.AMBIGUOUS.value
    assert result.path is None


def test_metadata_incompatible_is_invalid(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "incompatible")
    snapshot = _inspect(root)
    write_manifest_jar(
        root / "build" / "libs" / "buildsimple-1.0.0.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "other-mod",
                "version": "9.9.9",
                "environment": "*",
            }
        ),
    )

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.INVALID_METADATA.value
    assert "mod id mismatch" in result.metadata["issues"]
    assert "version mismatch" in result.metadata["issues"]


def test_invalid_json_is_invalid(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "invalid-json")
    snapshot = _inspect(root)
    write_manifest_jar(
        root / "build" / "libs" / "invalid-json.jar",
        manifest="{ not json",
    )

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.INVALID_METADATA.value
    assert "invalid fabric.mod.json JSON" in result.metadata["issues"]


def test_id_absent_is_invalid(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "missing-id")
    snapshot = _inspect(root)
    write_manifest_jar(
        root / "build" / "libs" / "missing-id.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "version": "1.0.0",
                "environment": "*",
            }
        ),
    )

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.INVALID_METADATA.value
    assert "missing id" in result.metadata["issues"]


def test_version_absent_is_invalid(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "missing-version")
    snapshot = _inspect(root)
    write_manifest_jar(
        root / "build" / "libs" / "missing-version.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "buildsimple",
                "environment": "*",
            }
        ),
    )

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now()))

    assert result.classification == ArtifactClassification.INVALID_METADATA.value
    assert "missing version" in result.metadata["issues"]


def test_target_subproject_is_respected_and_other_module_ignored(tmp_path: Path) -> None:
    root = make_multimodule_artifact_project(tmp_path / "multi")
    snapshot = _inspect(root)
    assert snapshot.target_subproject is not None
    started_at = utc_now()
    write_manifest_jar(
        root / "mod-a" / "build" / "libs" / "moda-1.0.0.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "moda",
                "version": "1.0.0",
                "environment": "*",
            }
        ),
        mtime=started_at + timedelta(seconds=5),
    )
    write_manifest_jar(
        root / "lib" / "build" / "libs" / "lib-1.0.0.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "lib",
                "version": "1.0.0",
                "environment": "*",
            }
        ),
        mtime=started_at + timedelta(seconds=5),
    )

    result = ArtifactValidator().validate(snapshot, _build_result(started_at))

    assert result.classification == ArtifactClassification.VALID.value
    assert result.path == root / "mod-a" / "build" / "libs" / "moda-1.0.0.jar"


def test_stale_jar_is_detected(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "stale")
    snapshot = _inspect(root)
    started_at = utc_now()
    write_manifest_jar(
        root / "build" / "libs" / "buildsimple-1.0.0.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "buildsimple",
                "version": "1.0.0",
                "environment": "*",
            }
        ),
        mtime=started_at - timedelta(minutes=10),
    )

    result = ArtifactValidator().validate(snapshot, _build_result(started_at))

    assert result.classification == ArtifactClassification.STALE.value
    assert "stale artifact" in result.metadata["issues"]


def test_build_failed_never_yields_valid_artifact(tmp_path: Path) -> None:
    root = make_simple_artifact_project(tmp_path / "failed")
    snapshot = _inspect(root)
    write_manifest_jar(
        root / "build" / "libs" / "buildsimple-1.0.0.jar",
        manifest=json.dumps(
            {
                "schemaVersion": 1,
                "id": "buildsimple",
                "version": "1.0.0",
                "environment": "*",
            }
        ),
    )

    result = ArtifactValidator().validate(snapshot, _build_result(utc_now(), exit_code=1))

    assert result.classification == ArtifactClassification.BUILD_FAILED.value
    assert result.metadata["valid"] is False


def test_no_subprocess_or_extraction_in_validator_source() -> None:
    import pd_agent.artifacts.validator as validator_module

    source = inspect.getsource(validator_module)
    lower = source.lower()

    assert "subprocess" not in lower
    assert "extractall" not in lower
    assert ".extract(" not in lower
