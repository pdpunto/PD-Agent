from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from pd_agent.core import RunStatus
from pd_agent.product import (
    DeliveryRecord,
    ExecutionRecord,
    HumanEvidenceDTO as ProductHumanEvidenceDTO,
    ProductCatalog,
    ProductExecutionStatus,
    ProjectService,
    TechnicalEvidenceDTO as ProductTechnicalEvidenceDTO,
)
from pd_agent.product.execution import ExecutionSnapshot
from pd_agent.web import CSRF_HEADER, WebServices, create_app


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


class FakeExecutionService:
    def __init__(self, catalog: ProductCatalog, project: object, task: object) -> None:
        self.catalog = catalog
        self.project = project
        self.task = task
        self.started: list[str] = []

    def start(self, task_id: str):
        assert task_id == self.task.task_id
        execution = ExecutionRecord(task_id=task_id, created_at=NOW)
        self.catalog.add_execution(execution)
        self.started.append(execution.execution_id)
        return ExecutionSnapshot(execution, ProductExecutionStatus.RUNNING)

    def get(self, execution_id: str):
        execution = self.catalog.get_execution(execution_id)
        return ExecutionSnapshot(execution, ProductExecutionStatus.SUCCEEDED, terminal=True)


class FakeEvidenceService:
    def human_evidence(self, execution_id: str) -> ProductHumanEvidenceDTO:
        return ProductHumanEvidenceDTO(execution_id=execution_id, status="RUNNING", changes=("src/Main.java",))

    def technical_evidence(self, execution_id: str) -> ProductTechnicalEvidenceDTO:
        return ProductTechnicalEvidenceDTO(execution_id=execution_id, run_id=execution_id, status="RUNNING")


class FakeDeliveryService:
    def __init__(self, delivery: DeliveryRecord, artifact: Path) -> None:
        self.delivery = delivery
        self.artifact = artifact
        self.revealed: list[str] = []

    def get(self, delivery_id: str) -> DeliveryRecord:
        if delivery_id != self.delivery.delivery_id:
            from pd_agent.product import DeliveryError
            raise DeliveryError("DELIVERY_NOT_FOUND", "delivery was not found")
        return self.delivery

    def resolve(self, delivery_id: str):
        from pd_agent.product import DeliveryArtifact
        if delivery_id != self.delivery.delivery_id:
            from pd_agent.product import DeliveryError
            raise DeliveryError("DELIVERY_NOT_FOUND", "delivery was not found")
        return DeliveryArtifact(delivery_id, self.artifact.name, self.artifact, self.delivery.artifact_sha256, self.artifact.stat().st_size)

    def execute_reveal(self, delivery_id: str):
        self.revealed.append(delivery_id)
        return type("Action", (), {"target": self.artifact})()


def _app(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    catalog = ProductCatalog(tmp_path / "data")
    projects = ProjectService(catalog)
    project = projects.register_project("Demo", workspace)
    task = projects.create_task(project.project_id, "build feature")
    execution = ExecutionRecord(task_id=task.task_id, created_at=NOW)
    catalog.add_execution(execution)
    artifact = tmp_path / "demo.jar"
    artifact.write_bytes(b"jar")
    import hashlib
    delivery = DeliveryRecord(project_id=project.project_id, task_id=task.task_id, execution_id=execution.execution_id, artifact_sha256=hashlib.sha256(b"jar").hexdigest(), artifact_ref="build/libs/demo.jar", created_at=NOW)
    catalog.add_delivery(delivery)
    execution_service = FakeExecutionService(catalog, project, task)
    delivery_service = FakeDeliveryService(delivery, artifact)
    app = create_app(services=WebServices(project=projects, execution=execution_service, evidence=FakeEvidenceService(), delivery=delivery_service), csrf_token="test-token")
    return app, catalog, projects, project, task, execution, delivery, execution_service, delivery_service


def _headers(*, mutation: bool = False) -> dict[str, str]:
    headers = {"host": "localhost"}
    if mutation:
        headers.update({"origin": "http://localhost", CSRF_HEADER: "test-token"})
    return headers


def test_project_and_task_routes_use_explicit_dtos(tmp_path: Path) -> None:
    app, _, projects, project, _, _, _, _, _ = _app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/projects", headers=_headers())
        assert response.status_code == 200 and response.json()[0]["name"] == "Demo"
        created = client.post("/api/v1/projects", headers=_headers(mutation=True), json={"name": "Second", "workspace": str(tmp_path / "workspace")})
        assert created.status_code == 201 and "workspace_ref" not in created.json()
        task = client.post(f"/api/v1/projects/{project.project_id}/tasks", headers=_headers(mutation=True), json={"request": "another feature"})
        assert task.status_code == 201 and task.json()["project_id"] == project.project_id
        assert projects.get_project(project.project_id).project_id == project.project_id


def test_project_and_task_errors_are_canonical(tmp_path: Path) -> None:
    app, _, _, _, _, _, _, _, _ = _app(tmp_path)
    with TestClient(app) as client:
        missing = client.get(f"/api/v1/projects/{uuid4()}", headers=_headers())
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"
        malformed = client.get("/api/v1/projects/not-a-uuid", headers=_headers())
        assert malformed.status_code == 422
        assert malformed.json()["error"]["code"] == "INVALID_REQUEST"
        unknown = client.post(f"/api/v1/projects/{uuid4()}/tasks", headers=_headers(mutation=True), json={"request": "x"})
        assert unknown.status_code == 404
        assert unknown.json()["error"]["request_id"]


def test_execution_start_is_immediate_and_identity_is_preserved(tmp_path: Path) -> None:
    app, _, _, _, task, _, _, execution_service, _ = _app(tmp_path)
    with TestClient(app) as client:
        response = client.post(f"/api/v1/tasks/{task.task_id}/executions", headers=_headers(mutation=True))
        assert response.status_code == 202
        assert response.json()["status"] == "RUNNING"
        assert response.json()["execution_id"] == response.json()["run_id"]
        assert len(execution_service.started) == 1


def test_execution_and_evidence_are_allowlisted(tmp_path: Path) -> None:
    app, _, _, _, _, execution, _, _, _ = _app(tmp_path)
    with TestClient(app) as client:
        observed = client.get(f"/api/v1/executions/{execution.execution_id}", headers=_headers())
        assert observed.status_code == 200 and observed.json()["terminal"] is True
        human = client.get(f"/api/v1/executions/{execution.execution_id}/evidence/human", headers=_headers())
        technical = client.get(f"/api/v1/executions/{execution.execution_id}/evidence/technical", headers=_headers())
        assert human.status_code == technical.status_code == 200
        assert "path" not in human.text and "events" not in technical.text


def test_history_and_delivery_endpoints_do_not_expose_paths(tmp_path: Path) -> None:
    app, _, _, project, _, _, delivery, _, _ = _app(tmp_path)
    with TestClient(app) as client:
        history = client.get(f"/api/v1/projects/{project.project_id}/history", headers=_headers())
        metadata = client.get(f"/api/v1/deliveries/{delivery.delivery_id}", headers=_headers())
        assert history.status_code == metadata.status_code == 200
        assert "workspace_ref" not in history.text and "artifact_ref" not in metadata.text and str(tmp_path) not in metadata.text


def test_download_is_delivery_id_only_and_uses_safe_filename(tmp_path: Path) -> None:
    app, _, _, _, _, _, delivery, _, _ = _app(tmp_path)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/deliveries/{delivery.delivery_id}/artifact", headers=_headers())
        assert response.status_code == 200
        assert response.content == b"jar"
        assert "demo.jar" in response.headers["content-disposition"]
        assert str(tmp_path) not in response.headers["content-disposition"]
        assert client.get("/api/v1/deliveries/../../outside.jar", headers=_headers()).status_code in {404, 422}


def test_reveal_accepts_only_delivery_id(tmp_path: Path) -> None:
    app, _, _, _, _, _, delivery, _, delivery_service = _app(tmp_path)
    with TestClient(app) as client:
        response = client.post(f"/api/v1/deliveries/{delivery.delivery_id}/reveal", headers=_headers(mutation=True))
        assert response.status_code == 200 and response.json()["revealed"] is True
        assert delivery_service.revealed == [delivery.delivery_id]
        assert client.post(f"/api/v1/deliveries/{delivery.delivery_id}/reveal?path=C:\\outside.jar", headers=_headers(mutation=True)).status_code == 200


def test_unknown_routes_and_forbidden_mutation_routes_are_safe(tmp_path: Path) -> None:
    app, _, _, _, _, _, _, _, _ = _app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/projects", headers={"host": "evil.example"}).status_code == 400
        assert client.post("/api/v1/cancel", headers=_headers(mutation=True)).status_code == 404
        assert client.post("/api/v1/projects", headers={"host": "localhost"}, json={"name": "x", "workspace": str(tmp_path)}).status_code == 403
