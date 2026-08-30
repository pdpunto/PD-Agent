from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest

from pd_agent.product import CatalogError, DeliveryRecord, ExecutionRecord, ProductCatalog, ProjectService


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
SHA = "b" * 64


def _service(tmp_path: Path) -> tuple[ProductCatalog, ProjectService, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    catalog = ProductCatalog(tmp_path / "data")
    return catalog, ProjectService(catalog), workspace


def test_empty_catalog_bootstraps_schema(tmp_path: Path) -> None:
    catalog, _, _ = _service(tmp_path)
    assert catalog.snapshot() == {"schema_version": 1, "projects": {}, "tasks": {}, "executions": {}, "deliveries": {}}
    assert catalog.path == tmp_path / "data" / "product" / "catalog-v1.json"


def test_project_task_execution_delivery_persist_and_reopen(tmp_path: Path) -> None:
    catalog, service, workspace = _service(tmp_path)
    project = service.register_project("Demo", workspace)
    task = service.create_task(project.project_id, "Build a feature")
    execution_id = uuid4()
    execution = service.attach_execution(ExecutionRecord(execution_id=execution_id, task_id=task.task_id, run_id=execution_id, created_at=NOW))
    delivery = service.attach_delivery(DeliveryRecord(project_id=project.project_id, task_id=task.task_id, execution_id=execution.execution_id, artifact_sha256=SHA, artifact_ref="trusted/one.jar", created_at=NOW))
    reopened = ProductCatalog(tmp_path / "data")
    assert reopened.get_project(project.project_id).task_ids == (task.task_id,)
    assert reopened.get_execution(execution.execution_id).task_id == task.task_id
    assert reopened.get_delivery(delivery.delivery_id).project_id == project.project_id
    assert service.project_history(project.project_id)["deliveries"]


def test_project_identity_is_not_derived_from_workspace(tmp_path: Path) -> None:
    _, service, workspace = _service(tmp_path)
    first = service.register_project("One", workspace)
    second = service.register_project("Two", workspace)
    assert first.project_id != second.project_id


def test_ownership_is_rejected(tmp_path: Path) -> None:
    catalog, service, workspace = _service(tmp_path)
    first = service.register_project("One", workspace)
    second = service.register_project("Two", workspace)
    task = service.create_task(first.project_id, "Task")
    other_task = service.create_task(second.project_id, "Other task")
    with pytest.raises(CatalogError, match="OWNERSHIP_INVALID"):
        catalog.add_execution(ExecutionRecord(task_id=uuid4(), created_at=NOW))
    with pytest.raises(CatalogError, match="OWNERSHIP_INVALID"):
        catalog.add_delivery(
            DeliveryRecord(
                project_id=second.project_id,
                task_id=task.task_id,
                execution_id=uuid4(),
                artifact_sha256=SHA,
                artifact_ref="trusted/wrong.jar",
                created_at=NOW,
            )
        )
    assert other_task.project_id == second.project_id


def test_corrupt_and_future_catalog_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "data" / "product"
    root.mkdir(parents=True)
    path = root / "catalog-v1.json"
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(CatalogError, match="CATALOG_CORRUPT"):
        ProductCatalog(tmp_path / "data")
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(CatalogError, match="CATALOG_VERSION_UNSUPPORTED"):
        ProductCatalog(tmp_path / "data")


def test_structurally_invalid_catalog_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "data" / "product"
    root.mkdir(parents=True)
    (root / "catalog-v1.json").write_text(json.dumps({"schema_version": 1, "projects": [], "tasks": {}, "executions": {}, "deliveries": {}}), encoding="utf-8")
    with pytest.raises(CatalogError, match="CATALOG_CORRUPT"):
        ProductCatalog(tmp_path / "data")


def test_failed_atomic_replace_preserves_previous_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog, service, workspace = _service(tmp_path)
    project = service.register_project("Before", workspace)
    original = catalog.path.read_bytes()
    import pd_agent.product.catalog as module

    def fail_replace(source, destination):  # noqa: ANN001
        raise OSError("simulated interruption")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(CatalogError, match="CATALOG_WRITE_FAILED"):
        service.create_task(project.project_id, "never committed")
    assert catalog.path.read_bytes() == original
    assert not list(catalog.path.parent.glob("*.tmp"))


def test_concurrent_mutations_are_serialized(tmp_path: Path) -> None:
    catalog, service, workspace = _service(tmp_path)
    project = service.register_project("Concurrent", workspace)
    errors: list[Exception] = []

    def add(index: int) -> None:
        try:
            service.create_task(project.project_id, f"Task {index}")
        except Exception as exc:  # pragma: no cover - diagnostic assertion
            errors.append(exc)

    threads = [Thread(target=add, args=(index,)) for index in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(catalog.get_project(project.project_id).task_ids) == 12


def test_missing_or_moved_workspace_fails_closed(tmp_path: Path) -> None:
    _, service, workspace = _service(tmp_path)
    project = service.register_project("Moved", workspace)
    workspace.rename(tmp_path / "moved")
    with pytest.raises(CatalogError, match="WORKSPACE_UNAVAILABLE"):
        service.reopen_project(project.project_id)


def test_registration_canonicalizes_traversal_and_symlink(tmp_path: Path) -> None:
    _, service, workspace = _service(tmp_path)
    project = service.register_project("Canonical", workspace / ".." / "workspace")
    assert project.workspace_ref == str(workspace.resolve())
    link = tmp_path / "workspace-link"
    try:
        link.symlink_to(workspace, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    linked = service.register_project("Link", link)
    assert linked.workspace_ref == str(workspace.resolve())


def test_catalog_has_metadata_only_not_runtime_evidence(tmp_path: Path) -> None:
    catalog, service, workspace = _service(tmp_path)
    project = service.register_project("Metadata", workspace)
    payload = catalog.snapshot()
    assert "events" not in payload and "evidence" not in payload and "jar_contents" not in payload
    assert json.dumps(project.workspace_ref) in json.dumps(payload)
