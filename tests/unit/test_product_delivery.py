from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from pd_agent.core import (
    ArtifactIdentity,
    ArtifactResult,
    BuildAttemptIdentity,
    BuildResult,
    FabricRequirement,
    FabricTaskContract,
    RunState,
    RunStatus,
    SourceRevision,
    TaskProgressLedger,
    compute_source_revision,
)
from pd_agent.product import DeliveryError, DeliveryService, ExecutionRecord, ProductCatalog, ProjectService
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _setup(tmp_path: Path, *, status: RunStatus = RunStatus.COMPLETED):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "src").mkdir()
    (workspace / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
    catalog = ProductCatalog(tmp_path / "data")
    projects = ProjectService(catalog)
    project = projects.register_project("Demo", workspace)
    task = projects.create_task(project.project_id, "build the feature")
    execution_id = str(uuid4())
    projects.attach_execution(ExecutionRecord(execution_id=execution_id, task_id=task.task_id, run_id=execution_id, created_at=NOW, status="SUCCEEDED"))
    storage = RunStorage(tmp_path / "data" / "runs")
    contract = FabricTaskContract(task_id=task.task_id, revision="1", goal="build the feature", requirements=(FabricRequirement(requirement_id="r1", description="feature"),))
    jar = workspace / "build" / "libs" / "demo.jar"
    jar.parent.mkdir(parents=True)
    jar.write_bytes(b"trusted artifact")
    source = compute_source_revision(workspace).revision
    build = BuildAttemptIdentity(build_attempt_id="build-1", source_revision=source, contract_identity=contract.identity(), success=True)
    digest = hashlib.sha256(jar.read_bytes()).hexdigest()
    identity = ArtifactIdentity(artifact_identity=digest, sha256=digest, producing_build_attempt_id="build-1", source_revision=source, contract_identity=contract.identity())
    artifact = ArtifactResult(path=jar, size=jar.stat().st_size, timestamp=NOW, classification="VALID", metadata={"sha256": digest})
    ledger = TaskProgressLedger(contract_identity=contract.identity(), satisfied_requirement_ids=("r1",), evidence_by_requirement={"r1": ("evidence/r1.json",)})
    state = RunState(run_id=execution_id, project_root=workspace, task=task.task_id, state=status, task_contract=contract, progress_ledger=ledger, source_revision=None if status is not RunStatus.COMPLETED else SourceRevision(source), build_identities=(build,), artifact_identity=identity, artifact_result=artifact, build_results=(BuildResult(attempt=1, command_display="gradle build", cwd=workspace, started_at=NOW, duration_seconds=1.0, exit_code=0, stdout_log="", stderr_log=""),))
    storage.write_run_state(state)
    storage.append_event(RunEvent(run_id=execution_id, event_type=RunEventType.RUN_STARTED))
    storage.write_final_report(FinalReport(run_id=execution_id, final_state=status, summary="done", final_build=state.build_results[-1], artifact=artifact, completion_status="PASS"))
    return catalog, storage, project, task, execution_id, jar


def test_valid_completed_execution_creates_and_resolves_delivery(tmp_path: Path) -> None:
    catalog, storage, project, task, execution_id, jar = _setup(tmp_path)
    service = DeliveryService(catalog, storage)
    delivery = service.create(execution_id)
    resolved = service.resolve(delivery.delivery_id)
    assert delivery.project_id == project.project_id and delivery.task_id == task.task_id
    assert resolved.path == jar.resolve()
    assert resolved.filename == "demo.jar"
    assert resolved.sha256 == delivery.artifact_sha256


def test_delivery_is_persisted_as_metadata_only(tmp_path: Path) -> None:
    catalog, storage, _, _, execution_id, _ = _setup(tmp_path)
    delivery = DeliveryService(catalog, storage).create(execution_id)
    payload = catalog.snapshot()["deliveries"][delivery.delivery_id]
    assert set(payload) == {"delivery_id", "project_id", "task_id", "execution_id", "artifact_sha256", "artifact_ref", "created_at"}
    assert "trusted artifact" not in str(payload)


def test_incomplete_or_completion_gate_failure_is_rejected(tmp_path: Path) -> None:
    catalog, storage, _, _, execution_id, _ = _setup(tmp_path, status=RunStatus.BUILDING)
    with pytest.raises(DeliveryError, match="COMPLETION_REQUIRED"):
        DeliveryService(catalog, storage).create(execution_id)

    catalog, storage, _, _, execution_id, _ = _setup(tmp_path / "gate")
    state = storage.read_run_state(execution_id)
    state.progress_ledger = None
    storage.write_run_state(state)
    with pytest.raises(DeliveryError, match="COMPLETION_REQUIRED"):
        DeliveryService(catalog, storage).create(execution_id)


@pytest.mark.parametrize("mutation", ["missing", "hash", "stale"])
def test_later_resolution_rechecks_artifact_integrity_and_currentness(tmp_path: Path, mutation: str) -> None:
    catalog, storage, _, _, execution_id, jar = _setup(tmp_path)
    service = DeliveryService(catalog, storage)
    delivery = service.create(execution_id)
    if mutation == "missing":
        jar.unlink()
        expected = "ARTIFACT_UNAVAILABLE"
    elif mutation == "hash":
        jar.write_bytes(b"changed bytes")
        expected = "ARTIFACT_NOT_CURRENT"
    else:
        (jar.parent.parent.parent / "src" / "Main.java").write_text("changed", encoding="utf-8")
        expected = "ARTIFACT_NOT_CURRENT"
    with pytest.raises(DeliveryError, match=expected):
        service.resolve(delivery.delivery_id)


def test_forged_delivery_reference_and_sha_are_rejected(tmp_path: Path) -> None:
    catalog, storage, project, task, execution_id, _ = _setup(tmp_path)
    service = DeliveryService(catalog, storage)
    delivery = service.create(execution_id)
    raw = catalog.path.read_text(encoding="utf-8")
    raw = raw.replace(delivery.artifact_ref, "../../outside.jar")
    catalog.path.write_text(raw, encoding="utf-8")
    catalog.reload()
    with pytest.raises(DeliveryError, match="SECURITY_REJECTED"):
        service.resolve(delivery.delivery_id)
    assert project.project_id and task.task_id


def test_unknown_delivery_and_wrong_ownership_are_rejected(tmp_path: Path) -> None:
    catalog, storage, _, _, execution_id, _ = _setup(tmp_path)
    service = DeliveryService(catalog, storage)
    with pytest.raises(DeliveryError, match="DELIVERY_NOT_FOUND"):
        service.resolve(str(uuid4()))
    delivery = service.create(execution_id)
    raw = catalog.path.read_text(encoding="utf-8").replace(delivery.project_id, str(uuid4()), 1)
    catalog.path.write_text(raw, encoding="utf-8")
    with pytest.raises(Exception):
        ProductCatalog(tmp_path / "data")


def test_reveal_uses_delivery_id_and_fixed_argument_vector(tmp_path: Path) -> None:
    catalog, storage, _, _, execution_id, _ = _setup(tmp_path)
    service = DeliveryService(catalog, storage)
    delivery = service.create(execution_id)
    action = service.reveal(delivery.delivery_id)
    assert action.target == service.resolve(delivery.delivery_id).path
    assert action.command[0].lower() in {"explorer.exe", "open", "xdg-open"}
    assert "shell=True" not in repr(action.command)


def test_absolute_and_traversal_references_cannot_be_created(tmp_path: Path) -> None:
    catalog, storage, _, _, execution_id, _ = _setup(tmp_path)
    service = DeliveryService(catalog, storage)
    state = storage.read_run_state(execution_id)
    outside = tmp_path / "outside.jar"
    outside.write_bytes(b"outside")
    state.artifact_result = ArtifactResult(path=outside, size=outside.stat().st_size, timestamp=NOW, classification="VALID")
    storage.write_run_state(state)
    with pytest.raises(DeliveryError):
        service.create(execution_id)
