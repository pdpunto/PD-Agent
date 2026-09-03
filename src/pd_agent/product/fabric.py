"""Product-facing boundary for deterministic Fabric task execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from pd_agent.core import (
    FabricKnowledgeSignal,
    FabricTaskContract,
)
from pd_agent.fabric import (
    FabricNormalOrchestrator,
    FabricOrchestrationResult,
    FabricPlatformResolutionStatus,
    FabricSupportRegistry,
    fabric_environment_constraints_from_profile,
    load_platform_registry,
    platform_observation_from_inspection,
)
from pd_agent.fabric.capabilities import CapabilityCandidate, CapabilityInstance
from pd_agent.fabric.planning import CapabilityPlanner, FabricContractContext, expand_plan_to_contract
from pd_agent.fabric.registry import foundation_capability_registry
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot

from .models import ExecutionRecord, ProjectRecord, TaskRecord


class ProductFabricTaskContractError(ValueError):
    """A product task cannot be resolved safely to a Fabric contract."""

    def __init__(self, message: str, *, code: str = "PRODUCT_TASK_INVALID") -> None:
        self.code = code
        super().__init__(message)


class ProductFabricTaskContractResolver:
    """Resolve the currently supported product Fabric task without benchmarks."""

    def __init__(
        self,
        *,
        platform_registry: FabricSupportRegistry | None = None,
        capability_registry: object | None = None,
    ) -> None:
        self.platform_registry = platform_registry or load_platform_registry(
            Path(__file__).resolve().parents[1] / "fabric" / "data" / "platform_profiles.json"
        )
        self.capability_registry = capability_registry or foundation_capability_registry()

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
        if not workspace.fabric_manifests or not workspace.source_roots or not workspace.resource_roots:
            raise ProductFabricTaskContractError("inspected workspace lacks Fabric metadata")
        mod_ids = tuple(dict.fromkeys(
            manifest.mod_id.strip()
            for manifest in workspace.fabric_manifests
            if isinstance(manifest.mod_id, str) and manifest.mod_id.strip()
        ))
        if len(mod_ids) != 1:
            raise ProductFabricTaskContractError("inspected workspace must expose exactly one Fabric mod id")
        missing_versions = tuple(
            name
            for keys, name in (
                (("minecraft", "minecraft_version"), "minecraft_version"),
                (("loader", "loader_version", "fabric_loader_version"), "loader_version"),
            )
            if not any(key in workspace.detected_versions for key in keys)
        )
        if missing_versions:
            raise ProductFabricTaskContractError(
                "workspace missing required Fabric versions: " + ", ".join(missing_versions),
                code="UNKNOWN_PLATFORM",
            )
        try:
            resolution = self.platform_registry.resolve(platform_observation_from_inspection(workspace))
        except Exception as exc:
            raise ProductFabricTaskContractError(
                "current Fabric platform profile is invalid",
                code="INVALID_PLATFORM_PROFILE",
            ) from exc
        status_codes = {
            FabricPlatformResolutionStatus.UNSUPPORTED: "UNSUPPORTED_PLATFORM",
            FabricPlatformResolutionStatus.UNKNOWN: "UNKNOWN_PLATFORM",
            FabricPlatformResolutionStatus.CONFLICT: "PLATFORM_CONFLICT",
        }
        if resolution.status is not FabricPlatformResolutionStatus.SUPPORTED or resolution.selected_profile is None:
            code = status_codes.get(resolution.status, "INSUFFICIENT_PLATFORM_EVIDENCE")
            raise ProductFabricTaskContractError(
                f"current Fabric platform is not supported: {resolution.reason_code}",
                code=code,
            )
        profile = resolution.selected_profile
        if not self._is_supported_server_core_request(task.request):
            raise ProductFabricTaskContractError("product Fabric task is not supported by this resolver")
        target_mod_id = mod_ids[0]
        lang_path = f"src/main/resources/assets/{target_mod_id}/lang/en_us.json"
        recipe_path = f"src/main/resources/data/{target_mod_id}/recipe/server_core.json"
        profile_constraints = fabric_environment_constraints_from_profile(profile)
        environment_constraints = replace(
            profile_constraints,
            extra={**profile_constraints.extra, "project_root": str(workspace.project_root)},
        )
        block = CapabilityCandidate(
            definition_id="fabric.block",
            parameters={
                "namespace": target_mod_id,
                "name": "server_core",
                "runtime_spec": {
                    "target_mod_id": target_mod_id,
                    "observations": [{
                        "observation_id": "server-core-registry",
                        "observation_type": "REGISTRY_ENTRY_PRESENT",
                        "profile": "registry",
                        "selector": {"kind": "registry", "registry_kind": "block", "identifier": f"{target_mod_id}:server_core"},
                        "expected": {"present": True},
                        "requirement_ids": ["$validation_id"],
                        "phase": "RUNTIME",
                    }],
                },
            },
        )
        block_instance = CapabilityInstance(definition_id="fabric.block", parameters=block.parameters)
        item = CapabilityCandidate(
            definition_id="fabric.block_item",
            parameters={
                "block_instance_id": block_instance.identity,
                "namespace": target_mod_id,
                "artifact_spec": {"required_paths": [lang_path, recipe_path]},
                "mutation_paths": [lang_path, recipe_path],
            },
        )
        item_instance = CapabilityInstance(definition_id="fabric.block_item", parameters=item.parameters)
        recipe = CapabilityCandidate(
            definition_id="fabric.recipe",
            parameters={"output_instance_id": item_instance.identity, "ingredients": []},
        )
        planner = CapabilityPlanner(self.capability_registry)
        plan = planner.plan((block, item, recipe))
        expansion = planner.expand_contract(
            plan,
            FabricContractContext(
                task_id=task.task_id,
                revision="product-1",
                goal=task.request,
                required_capabilities=("Fabric project", "craftable utility block"),
                completion_criteria=("source change", "build", "artifact", "minecraft"),
                knowledge_signals=(FabricKnowledgeSignal(
                signal_id="product-fabric-server-core",
                query="How do you add a craftable utility block with a matching block item and recipe/resource wiring in Fabric?",
                category="MAPPING",
                required=False,
                ),),
                environment_constraints=environment_constraints,
            ),
        )
        if not expansion.success or expansion.contract is None:
            failure = expansion.failure
            raise ProductFabricTaskContractError(
                f"{failure.code if failure is not None else 'INVALID_GENERATED_CONTRACT'}: "
                f"{failure.message if failure is not None else 'contract expansion failed'}",
                code=failure.code if failure is not None else "INVALID_GENERATED_CONTRACT",
            )
        return expansion.contract

    @staticmethod
    def _is_supported_server_core_request(request: str) -> bool:
        normalized = " ".join(request.casefold().split())
        if "server core" not in normalized:
            return False
        english = all(token in normalized for token in ("craftable", "utility", "block"))
        spanish = all(token in normalized for token in ("bloque", "utilitario", "craftable"))
        has_item_wiring = "block item" in normalized or "recursos en_us" in normalized
        has_recipe = "recipe" in normalized or "recet" in normalized
        return (english or spanish) and has_item_wiring and has_recipe

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

    def _inspect_and_resolve(self, project: ProjectRecord, task: TaskRecord) -> FabricTaskContract:
        inspector = self.inspector
        if inspector is None:
            from pd_agent.project import ProjectInspector

            inspector = ProjectInspector()
        snapshot = inspector.inspect(Path(project.workspace_ref))
        return self.resolver.resolve(project, task, snapshot)

    def preflight(self, project: ProjectRecord, task: TaskRecord) -> FabricTaskContract:
        """Resolve the contract before Product creates an execution record."""
        return self._inspect_and_resolve(project, task)

    def run(
        self,
        execution: ExecutionRecord,
        project: ProjectRecord,
        task: TaskRecord,
        *,
        contract: FabricTaskContract | None = None,
    ) -> FabricOrchestrationResult:
        if execution.execution_id != execution.run_id:
            raise ProductFabricTaskContractError("execution_id must equal run_id")
        if task.project_id != project.project_id or execution.task_id != task.task_id:
            raise ProductFabricTaskContractError("product ownership is invalid")
        inspector = self.inspector
        if inspector is None:
            from pd_agent.project import ProjectInspector

            inspector = ProjectInspector()
        snapshot = inspector.inspect(Path(project.workspace_ref))
        contract = contract or self.resolver.resolve(project, task, snapshot)
        return self.orchestrator.run(contract, snapshot.project_root, run_id=execution.run_id)


__all__ = [
    "FabricProductExecutionRunner",
    "ProductExecutionRunner",
    "ProductFabricTaskContractError",
    "ProductFabricTaskContractResolver",
]
