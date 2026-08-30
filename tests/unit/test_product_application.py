from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from threading import Event

from pd_agent.config import AppConfig
from pd_agent.core import ArtifactResult, BuildResult, FabricRequirement, FabricTaskContract, RunState, RunStatus, TaskProgressLedger
from pd_agent.product import (
    ExecutionService,
    ProductCatalog,
    ProductExecutionStatus,
    ProjectService,
    build_product_application,
)
from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage


REQUEST = "Add a craftable utility block called Server Core to Example Mod"


def test_build_product_application_is_composed_without_starting_work(tmp_path: Path) -> None:
    config = AppConfig(provider="openai", model="offline-test", runs_dir=tmp_path / "runs")
    application = build_product_application(
        config,
        provider_factory=lambda _config: object(),
        product_data_root=tmp_path / "product-data",
    )
    try:
        assert application.web_services.project is application.project_service
        assert application.web_services.execution is application.execution_service
        assert application.execution_service.product_runner is application.fabric_runner
        assert application.execution_service.delivery_service is application.delivery_service
        assert application.catalog.snapshot()["executions"] == {}
    finally:
        application.shutdown()
        application.shutdown()


def test_product_runner_result_is_reconciled_from_run_storage(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    catalog = ProductCatalog(tmp_path / "product-data")
    projects = ProjectService(catalog)
    project = projects.register_project("Demo", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    storage = RunStorage(tmp_path / "runs")
    contract = FabricTaskContract(
        task_id=task.task_id,
        revision="1",
        goal=task.request,
        requirements=(FabricRequirement(requirement_id="source", description="source changed"),),
    )
    now = datetime.now(timezone.utc)
    build = BuildResult(1, "build", workspace, now, 0.1, 0, "", "")
    artifact = ArtifactResult(workspace / "build" / "libs" / "mod.jar", 1, now, "VALID")

    class Runner:
        def run(self, execution, received_project, received_task):  # noqa: ANN001
            assert execution.execution_id == execution.run_id
            assert received_project.project_id == project.project_id
            assert received_task.task_id == task.task_id
            assert received_task.project_id == task.project_id
            state = RunState(
                    run_id=execution.run_id,
                    project_root=workspace,
                    task=task.request,
                state=RunStatus.COMPLETED,
                task_contract=contract,
                progress_ledger=TaskProgressLedger(
                    contract_identity=contract.identity(),
                    satisfied_requirement_ids=("source",),
                    evidence_by_requirement={"source": ("evidence/source.json",)},
                ),
                    build_results=(build,),
                    artifact_result=artifact,
            )
            report = FinalReport(
                    run_id=execution.run_id,
                    final_state=RunStatus.COMPLETED,
                    summary="authoritative success",
                completion_status="PASS",
                    build_attempts=(build,),
                    final_build=build,
                    artifact=artifact,
            )
            storage.write_run_state(state)
            storage.write_final_report(report)
            storage.append_event(RunEvent(run_id=execution.run_id, event_type=RunEventType.RUN_STARTED, payload={}))
            return SimpleNamespace(run_id=execution.run_id)

    class Delivery:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def create(self, execution_id: str) -> None:
            self.calls.append(execution_id)

    delivery = Delivery()
    service = ExecutionService(
        catalog,
        SimpleNamespace(storage=storage),
        projects,
        product_runner=Runner(),
        delivery_service=delivery,
    )
    try:
        started = service.start(task.task_id)
        for _ in range(100):
            if service.get(started.execution_id).status is ProductExecutionStatus.SUCCEEDED:
                break
            Event().wait(0.01)
        assert service.get(started.execution_id).status is ProductExecutionStatus.SUCCEEDED
        assert delivery.calls == [started.execution_id]
        assert catalog.get_execution(started.execution_id).run_id == started.execution_id
    finally:
        service.shutdown()


def test_product_execution_failure_does_not_create_delivery(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    catalog = ProductCatalog(tmp_path / "product-data")
    projects = ProjectService(catalog)
    project = projects.register_project("Demo", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    finished = Event()

    class Runner:
        def run(self, execution, _project, _task):  # noqa: ANN001
            finished.set()
            return SimpleNamespace(run_id=execution.run_id)

    class Delivery:
        def create(self, _execution_id: str) -> None:
            raise AssertionError("delivery must not be created for missing evidence")

    service = ExecutionService(
        catalog,
        SimpleNamespace(storage=RunStorage(tmp_path / "runs")),
        projects,
        product_runner=Runner(),
        delivery_service=Delivery(),
    )
    try:
        started = service.start(task.task_id)
        assert finished.wait(timeout=2)
        for _ in range(100):
            if service.get(started.execution_id).terminal:
                break
            Event().wait(0.01)
        assert service.get(started.execution_id).status is ProductExecutionStatus.FAILED
    finally:
        service.shutdown()


def test_application_execution_identity_contract_is_product_metadata_only(tmp_path: Path) -> None:
    catalog = ProductCatalog(tmp_path / "product-data")
    projects = ProjectService(catalog)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = projects.register_project("Demo", workspace)
    task = projects.create_task(project.project_id, REQUEST)
    assert catalog.snapshot()["projects"][project.project_id]["task_ids"] == [task.task_id]
    assert "events" not in catalog.snapshot()
