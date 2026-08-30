"""Product-facing boundary for deterministic Fabric task execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pd_agent.core import (
    FabricEnvironmentConstraints,
    FabricKnowledgeSignal,
    FabricMutationExpectation,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
)
from pd_agent.fabric import FabricNormalOrchestrator, FabricOrchestrationResult
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot

from .models import ExecutionRecord, ProjectRecord, TaskRecord


class ProductFabricTaskContractError(ValueError):
    """A product task cannot be resolved safely to a Fabric contract."""


class ProductFabricTaskContractResolver:
    """Resolve the currently supported product Fabric task without benchmarks."""

    def resolve(self, project: ProjectRecord, task: TaskRecord, workspace: ProjectSnapshot) -> FabricTaskContract:
        if not isinstance(project, ProjectRecord) or not isinstance(task, TaskRecord):
            raise ProductFabricTaskContractError("project and task records are required")
        if task.project_id != project.project_id:
            raise ProductFabricTaskContractError("task does not belong to project")
        if not isinstance(workspace, ProjectSnapshot):
            raise ProductFabricTaskContractError("an inspected Fabric workspace is required")
        if workspace.status is not ProjectInspectionStatus.READY:
            raise ProductFabricTaskContractError("workspace inspection is not ready")
        if workspace.project_root.resolve() != Path(project.workspace_ref).resolve():
            raise ProductFabricTaskContractError("workspace does not match project")
        if not self._is_supported_server_core_request(task.request):
            raise ProductFabricTaskContractError("product Fabric task is not supported by this resolver")
        if not workspace.fabric_manifests or not workspace.source_roots or not workspace.resource_roots:
            raise ProductFabricTaskContractError("inspected workspace lacks Fabric metadata")

        requirements = (
            FabricRequirement(requirement_id="source-change", description="a relevant source change is required"),
            FabricRequirement(requirement_id="resource-lang", description="the Server Core language resource is present"),
            FabricRequirement(requirement_id="resource-recipe", description="the Server Core recipe is present"),
            FabricRequirement(requirement_id="validation-build", description="the Fabric project builds successfully"),
            FabricRequirement(requirement_id="validation-artifact", description="the produced artifact is valid and current"),
            FabricRequirement(requirement_id="validation-minecraft", description="the Server Core block is present at runtime"),
        )
        validation_requirements = (
            FabricValidationRequirement(validation_requirement_id="validate-build", requirement_ids=("validation-build",), kind="build"),
            FabricValidationRequirement(
                validation_requirement_id="validate-artifact",
                requirement_ids=("validation-artifact", "resource-lang", "resource-recipe"),
                kind="artifact",
                spec={"required_paths": (
                    "src/main/resources/assets/examplemod/lang/en_us.json",
                    "src/main/resources/data/examplemod/recipe/server_core.json",
                )},
            ),
            FabricValidationRequirement(
                validation_requirement_id="validate-minecraft",
                requirement_ids=("validation-minecraft",),
                kind="minecraft",
                spec={"observations": ("examplemod:server_core",)},
            ),
        )
        environment = workspace.detected_versions
        return FabricTaskContract(
            task_id=task.task_id,
            revision="product-1",
            goal=task.request,
            requirements=requirements,
            required_capabilities=("Fabric project", "craftable utility block"),
            completion_criteria=("source change", "build", "artifact", "Minecraft runtime"),
            validation_requirements=validation_requirements,
            knowledge_signals=(FabricKnowledgeSignal(
                signal_id="product-fabric-server-core",
                query="How do you add a craftable utility block with a matching block item and recipe/resource wiring in Fabric?",
                category="MAPPING",
                required=False,
            ),),
            mutation_expectations=(
                FabricMutationExpectation(expectation_id="mutation-source", role="source"),
                FabricMutationExpectation(expectation_id="mutation-lang", role="resource", path="src/main/resources/assets/examplemod/lang/en_us.json"),
                FabricMutationExpectation(expectation_id="mutation-recipe", role="resource", path="src/main/resources/data/examplemod/recipe/server_core.json"),
            ),
            environment_constraints=FabricEnvironmentConstraints(
                minecraft_version=self._detected(environment, "minecraft_version"),
                loader_version=self._detected(environment, "loader_version"),
                fabric_api_version=self._detected(environment, "fabric_api_version"),
                yarn_version=self._detected(environment, "yarn_version"),
                java_version=self._detected(environment, "java_version"),
                extra={"project_root": str(workspace.project_root)},
            ),
        )

    @staticmethod
    def _is_supported_server_core_request(request: str) -> bool:
        normalized = " ".join(request.casefold().split())
        return "craftable utility block" in normalized and "server core" in normalized

    @staticmethod
    def _detected(values, key: str) -> str | None:  # noqa: ANN001
        detected = values.get(key)
        return detected.value if detected is not None else None


class ProductExecutionRunner(Protocol):
    """Product execution port used by a later application composition root."""

    def run(self, execution: ExecutionRecord, project: ProjectRecord, task: TaskRecord) -> FabricOrchestrationResult:
        ...


@dataclass(slots=True)
class FabricProductExecutionRunner:
    """Adapt product records to the existing Fabric orchestration boundary."""

    orchestrator: FabricNormalOrchestrator
    resolver: ProductFabricTaskContractResolver = field(default_factory=ProductFabricTaskContractResolver)
    inspector: object | None = None

    def run(self, execution: ExecutionRecord, project: ProjectRecord, task: TaskRecord) -> FabricOrchestrationResult:
        if execution.execution_id != execution.run_id:
            raise ProductFabricTaskContractError("execution_id must equal run_id")
        if task.project_id != project.project_id or execution.task_id != task.task_id:
            raise ProductFabricTaskContractError("product ownership is invalid")
        inspector = self.inspector
        if inspector is None:
            from pd_agent.project import ProjectInspector

            inspector = ProjectInspector()
        snapshot = inspector.inspect(Path(project.workspace_ref))
        contract = self.resolver.resolve(project, task, snapshot)
        return self.orchestrator.run(contract, snapshot.project_root, run_id=execution.run_id)


__all__ = [
    "FabricProductExecutionRunner",
    "ProductExecutionRunner",
    "ProductFabricTaskContractError",
    "ProductFabricTaskContractResolver",
]
