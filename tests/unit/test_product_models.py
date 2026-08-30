from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

import pytest

from pd_agent.product import DeliveryRecord, ExecutionRecord, ProjectRecord, TaskRecord


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
SHA256 = "a" * 64


def test_project_record_defaults_identity_and_round_trips() -> None:
    record = ProjectRecord(name="Demo", workspace_ref="workspace/demo", created_at=NOW, updated_at=NOW)
    restored = ProjectRecord.from_dict(record.to_dict())
    assert record.project_id != ""
    assert restored == record
    assert record.canonical_json() == json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_task_record_preserves_project_ownership_and_ids() -> None:
    project_id = uuid4()
    execution_id = uuid4()
    record = TaskRecord(
        project_id=project_id,
        request="Add a persistent item",
        created_at=NOW,
        execution_ids=(execution_id,),
    )
    assert record.project_id == str(project_id)
    assert record.execution_ids == (str(execution_id),)
    assert TaskRecord.from_dict(record.to_dict()) == record


def test_execution_record_keeps_execution_and_run_contract_distinct() -> None:
    task_id = uuid4()
    execution_id = uuid4()
    record = ExecutionRecord(execution_id=execution_id, task_id=task_id, run_id=execution_id, created_at=NOW)
    assert record.execution_id == record.run_id
    assert ExecutionRecord.from_dict(record.to_dict()) == record


def test_delivery_record_validates_artifact_identity_and_round_trips() -> None:
    record = DeliveryRecord(
        project_id=uuid4(),
        task_id=uuid4(),
        execution_id=uuid4(),
        artifact_sha256=SHA256,
        artifact_ref="trusted-delivery/one.jar",
        created_at=NOW,
    )
    assert DeliveryRecord.from_dict(record.to_dict()) == record


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (ProjectRecord, {"name": "", "workspace_ref": "workspace", "created_at": NOW, "updated_at": NOW}),
        (TaskRecord, {"project_id": uuid4(), "request": "", "created_at": NOW}),
        (ExecutionRecord, {"execution_id": "not-a-uuid", "task_id": uuid4(), "created_at": NOW}),
        (DeliveryRecord, {"project_id": uuid4(), "task_id": uuid4(), "execution_id": uuid4(), "artifact_sha256": "bad", "artifact_ref": "jar", "created_at": NOW}),
    ],
)
def test_malformed_product_records_are_rejected(factory, kwargs) -> None:  # noqa: ANN001
    with pytest.raises(ValueError):
        factory(**kwargs)


def test_product_models_do_not_import_runtime_state() -> None:
    import pd_agent.product.models as models

    assert "pd_agent.core.state" not in models.__dict__
