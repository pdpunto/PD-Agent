"""Product-facing boundary for deterministic Fabric task execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

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
from pd_agent.fabric.capabilities import (
    CapabilityCandidate,
    CapabilityInstance,
    CapabilityModelError,
    CapabilityRecipeIngredient,
    DeclarativeCapabilityReference,
    VanillaRecipeIngredient,
)
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
        target_mod_id = mod_ids[0]
        vertical_b = self._parse_vertical_b_request(task.request)
        if vertical_b is not None:
            try:
                return self._resolve_vertical_b(project, task, workspace, profile, target_mod_id, vertical_b)
            except CapabilityModelError as exc:
                raise ProductFabricTaskContractError(str(exc), code="INVALID_VERTICAL_B_REQUEST") from exc
        request = self._parse_vertical_a_request(task.request)
        if request is None:
            raise ProductFabricTaskContractError("product Fabric task is not supported by this resolver")
        block_id = request["block_id"]
        display_name = request["display_name"]
        item_id = request["item_id"]
        recipe_id = request["recipe_id"]
        class_name = "".join(part.capitalize() for part in block_id.split("_"))
        block_source_path = f"src/main/java/{target_mod_id}/{class_name}Block.java"
        item_source_path = f"src/main/java/{target_mod_id}/{class_name}BlockItem.java"
        resource_paths = {
            "blockstate": f"src/main/resources/assets/{target_mod_id}/blockstates/{block_id}.json",
            "block_model": f"src/main/resources/assets/{target_mod_id}/models/block/{block_id}.json",
            "item_model": f"src/main/resources/assets/{target_mod_id}/models/item/{item_id}.json",
            "lang": f"src/main/resources/assets/{target_mod_id}/lang/en_us.json",
            "recipe": f"src/main/resources/data/{target_mod_id}/recipes/{recipe_id}.json",
        }
        profile_constraints = fabric_environment_constraints_from_profile(profile)
        environment_constraints = replace(
            profile_constraints,
            extra={**profile_constraints.extra, "project_root": str(workspace.project_root)},
        )
        block = CapabilityCandidate(
            definition_id="fabric.block",
            parameters={
                "namespace": target_mod_id,
                "block_id": block_id,
                "name": block_id,
                "display_name": display_name,
                "source_path": block_source_path,
                "runtime_spec": {
                    "target_mod_id": target_mod_id,
                    "platform_id": profile.platform_id,
                    "observations": self._runtime_observations(target_mod_id, block_id, item_id),
                },
            },
        )
        block_instance = CapabilityInstance(definition_id="fabric.block", parameters=block.parameters)
        item = CapabilityCandidate(
            definition_id="fabric.block_item",
            parameters={
                "block_instance_id": block_instance.identity,
                "namespace": target_mod_id,
                "item_id": item_id,
                "display_name": display_name,
                "source_path": item_source_path,
                "artifact_spec": {"required_paths": [resource_paths["lang"], resource_paths["recipe"]]},
                "mutation_paths": [resource_paths["lang"], resource_paths["recipe"]],
            },
        )
        item_instance = CapabilityInstance(definition_id="fabric.block_item", parameters=item.parameters)
        assets = CapabilityCandidate(
            definition_id="fabric.block_assets",
            parameters={
                "block_instance_id": block_instance.identity,
                "block_item_instance_id": item_instance.identity,
                "namespace": target_mod_id,
                "block_id": block_id,
                "item_id": item_id,
                "display_name": display_name,
                "texture_strategy": request["texture_strategy"],
                "texture_reference": "minecraft:block/stone",
                "resource_paths": resource_paths,
                "mutation_paths": [resource_paths[key] for key in ("blockstate", "block_model", "item_model", "lang")],
            },
        )
        recipe = CapabilityCandidate(
            definition_id="fabric.recipe",
            parameters={
                "output_instance_id": item_instance.identity,
                "namespace": target_mod_id,
                "recipe_id": recipe_id,
                "recipe_type": "minecraft:crafting_shapeless",
                "ingredients": [{"item": "minecraft:iron_ingot"}],
                "result_item_id": item_id,
                "result_count": 1,
                "resource_path": resource_paths["recipe"],
            },
        )
        planner = CapabilityPlanner(self.capability_registry)
        plan = planner.plan((block, item, assets, recipe))
        expansion = planner.expand_contract(
            plan,
            FabricContractContext(
                task_id=task.task_id,
                revision="product-1",
                goal=task.request,
                required_capabilities=("Fabric project", "craftable utility block"),
                completion_criteria=("source change", "build", "artifact", "minecraft"),
                knowledge_signals=(FabricKnowledgeSignal(
                signal_id="product-fabric-vertical-a",
                query="How do you compose a Fabric block, BlockItem, assets and recipe for the requested project?",
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

    def _resolve_vertical_b(
        self,
        project: ProjectRecord,
        task: TaskRecord,
        workspace: ProjectSnapshot,
        profile: Any,
        target_mod_id: str,
        request: Mapping[str, Any],
    ) -> FabricTaskContract:
        """Resolve one bounded declarative item/recipe composition."""
        items = tuple(request["items"])
        recipes = tuple(request.get("recipes", ()))
        item_keys: set[str] = set()
        productive_item_ids: set[str] = set()
        recipe_ids: set[str] = set()
        item_ids_by_key: dict[str, str] = {}
        candidates: list[CapabilityCandidate] = []

        for raw in items:
            key = raw["declaration_key"]
            item_id = raw["item_id"]
            if key in item_keys or item_id in productive_item_ids:
                raise ProductFabricTaskContractError(
                    "duplicate standalone item declaration or productive ID",
                    code="DUPLICATE_ITEM_ID",
                )
            item_keys.add(key)
            productive_item_ids.add(item_id)
            item_ids_by_key[key] = item_id
            item_path = f"src/main/java/{target_mod_id}/{_java_class_name(item_id)}Item.java"
            asset_paths = {
                "item_model": f"src/main/resources/assets/{target_mod_id}/models/item/{item_id}.json",
                "lang": f"src/main/resources/assets/{target_mod_id}/lang/en_us.json",
            }
            item_parameters: dict[str, Any] = {
                "namespace": target_mod_id,
                "item_id": item_id,
                "display_name": raw.get("display_name", item_id.replace("_", " ").title()),
                "settings": dict(raw.get("settings", {})),
                "source_path": item_path,
            }
            candidates.append(CapabilityCandidate(
                definition_id="fabric.item",
                declaration_key=key,
                parameters=item_parameters,
            ))
            assets = raw.get("assets", raw.get("item_assets"))
            if assets is not None:
                if not isinstance(assets, Mapping):
                    raise ProductFabricTaskContractError("item assets must be an object", code="INVALID_ITEM_ASSETS")
                asset_key = assets.get("declaration_key", f"{key}-assets")
                if not isinstance(asset_key, str) or asset_key in item_keys:
                    raise ProductFabricTaskContractError("duplicate item assets declaration", code="DUPLICATE_DECLARATION_KEY")
                item_keys.add(asset_key)
                resource_paths = dict(assets.get("resource_paths", asset_paths))
                mutation_paths = list(dict.fromkeys(resource_paths.values()))
                asset_parameters = {
                    "namespace": target_mod_id,
                    "item_id": item_id,
                    "texture_strategy": assets.get("texture_strategy", "REUSE"),
                    "texture_reference": assets.get("texture_reference", "minecraft:item/iron_ingot"),
                    "resource_paths": resource_paths,
                    "mutation_paths": mutation_paths,
                }
                candidates.append(CapabilityCandidate(
                    definition_id="fabric.item_assets",
                    declaration_key=asset_key,
                    parameters=asset_parameters,
                    references=(DeclarativeCapabilityReference(
                        capability_id="fabric.item", declaration_key=key, role="item"
                    ),),
                ))

        for raw in recipes:
            recipe_key = raw["declaration_key"]
            recipe_id = raw["recipe_id"]
            if recipe_key in item_keys or recipe_id in recipe_ids:
                raise ProductFabricTaskContractError("duplicate recipe declaration or resource ID", code="DUPLICATE_RECIPE_ID")
            item_keys.add(recipe_key)
            recipe_ids.add(recipe_id)
            output_key = raw.get("output_declaration_key", raw.get("output"))
            if not isinstance(output_key, str):
                raise ProductFabricTaskContractError("recipe output declaration is required", code="MISSING_OUTPUT_REFERENCE")
            references = [DeclarativeCapabilityReference(
                capability_id="fabric.item", declaration_key=output_key, role="output"
            )]
            ingredients: list[dict[str, Any]] = []
            for ingredient in raw.get("ingredients", ()):
                if not isinstance(ingredient, Mapping):
                    raise ProductFabricTaskContractError("recipe ingredient must be an object", code="INVALID_INGREDIENT")
                kind = ingredient.get("kind")
                if kind == "capability":
                    ingredient_key = ingredient.get("declaration_key")
                    if not isinstance(ingredient_key, str):
                        raise ProductFabricTaskContractError("ingredient declaration is required", code="MISSING_INGREDIENT_REFERENCE")
                    references.append(DeclarativeCapabilityReference(
                        capability_id=str(ingredient.get("capability_id", "fabric.item")),
                        declaration_key=ingredient_key,
                        role="ingredient",
                    ))
                    ingredients.append(CapabilityRecipeIngredient(
                        capability_id=str(ingredient.get("capability_id", "fabric.item")),
                        declaration_key=ingredient_key,
                        quantity=ingredient.get("quantity", 1),
                    ).to_dict())
                else:
                    item_id = ingredient.get("item_id", ingredient.get("item"))
                    ingredients.append(VanillaRecipeIngredient(
                        item_id=item_id,
                        quantity=ingredient.get("quantity", 1),
                    ).to_dict())
            if not ingredients:
                raise ProductFabricTaskContractError("recipe ingredients are required", code="INVALID_INGREDIENT")
            recipe_path = f"src/main/resources/data/{target_mod_id}/recipes/{recipe_id}.json"
            candidates.append(CapabilityCandidate(
                definition_id="fabric.recipe",
                declaration_key=recipe_key,
                parameters={
                    "namespace": target_mod_id,
                    "recipe_id": recipe_id,
                    "recipe_type": raw.get("recipe_type", "minecraft:crafting_shapeless"),
                    "ingredients": ingredients,
                    "result_item_id": raw.get("result_item_id", item_ids_by_key.get(output_key, output_key)),
                    "result_count": raw.get("result_count", 1),
                    "resource_path": recipe_path,
                },
                references=tuple(references),
            ))

        planner = CapabilityPlanner(self.capability_registry)
        plan = planner.plan(candidates)
        if not plan.success:
            failure = plan.failure
            raise ProductFabricTaskContractError(
                f"{failure.code if failure else 'INVALID_PLAN'}: {failure.message if failure else 'capability planning failed'}",
                code=failure.code if failure else "INVALID_PLAN",
            )
        constraints = fabric_environment_constraints_from_profile(profile)
        constraints = replace(constraints, extra={**constraints.extra, "project_root": str(workspace.project_root)})
        canonical_goal = json.dumps(
            {
                "items": sorted(items, key=lambda item: item["declaration_key"]),
                "recipes": sorted(recipes, key=lambda item: item["declaration_key"]),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        expansion = planner.expand_contract(
            plan,
            FabricContractContext(
                task_id=task.task_id,
                revision="product-2",
                goal=canonical_goal,
                required_capabilities=(
                    "Fabric project", "standalone items and recipes",
                    "fabric.item", "fabric.item_assets", "fabric.recipe",
                ),
                completion_criteria=("source change", "build", "artifact"),
                knowledge_signals=(),
                environment_constraints=constraints,
            ),
        )
        if not expansion.success or expansion.contract is None:
            failure = expansion.failure
            raise ProductFabricTaskContractError(
                f"{failure.code if failure else 'INVALID_GENERATED_CONTRACT'}: {failure.message if failure else 'contract expansion failed'}",
                code=failure.code if failure else "INVALID_GENERATED_CONTRACT",
            )
        return self._add_resolved_reference_provenance(expansion.contract, plan, expansion)

    @staticmethod
    def _add_resolved_reference_provenance(
        contract: FabricTaskContract,
        plan: Any,
        expansion: Any,
    ) -> FabricTaskContract:
        """Expose planner identities in declarative validation specs."""
        by_instance = {item.identity: item for item in plan.instances}
        resolved = [item.to_dict() for item in plan.resolved_references]
        validations = []
        for validation in contract.validation_requirements:
            instance_id = next(
                (identity for identity, ids in expansion.capability_validation_requirement_ids if validation.validation_requirement_id in ids),
                None,
            )
            spec = dict(validation.spec)
            if instance_id is not None and by_instance[instance_id].definition_id == "fabric.recipe":
                recipe = by_instance[instance_id]
                item_parameters = {
                    (item.parameters.get("namespace"), item.parameters.get("item_id")): item.identity
                    for item in by_instance.values()
                    if item.definition_id == "fabric.item"
                }
                output = item_parameters.get((recipe.parameters.get("namespace"), recipe.parameters.get("result_item_id")))
                ingredient_keys = {
                    item.get("declaration_key")
                    for item in recipe.parameters.get("ingredients", ())
                    if isinstance(item, Mapping) and item.get("kind") == "capability"
                }
                relevant = [item for item in resolved if item["declaration_key"] in ingredient_keys]
                ingredients = [item["instance_identity"] for item in relevant if item["role"] == "ingredient"]
                output_ref = next((item for item in resolved if item["instance_identity"] == output and item["role"] == "output"), None)
                recipe_refs = ([output_ref] if output_ref is not None else []) + relevant
                spec["output_instance_id"] = output
                spec["ingredient_instance_ids"] = ingredients
                spec["resolved_references"] = recipe_refs
            validations.append(replace(validation, spec=spec))
        return replace(contract, fingerprint=None, validation_requirements=tuple(validations))

    @staticmethod
    def _parse_vertical_b_request(request: str) -> dict[str, Any] | None:
        """Parse only the bounded JSON request shape owned by Vertical B."""
        if not isinstance(request, str):
            return None
        try:
            value = json.loads(request)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(value, Mapping) or "items" not in value:
            return None
        items = value.get("items")
        recipes = value.get("recipes", ())
        if isinstance(items, Mapping):
            items = (items,)
        if isinstance(recipes, Mapping):
            recipes = (recipes,)
        if not isinstance(items, (list, tuple)) or not items or not isinstance(recipes, (list, tuple)):
            raise ProductFabricTaskContractError("Vertical B items/recipes must be sequences", code="INVALID_VERTICAL_B_REQUEST")
        normalized_items = []
        for item in items:
            if not isinstance(item, Mapping) or not isinstance(item.get("declaration_key"), str) or not isinstance(item.get("item_id"), str):
                raise ProductFabricTaskContractError("Vertical B item declaration is invalid", code="INVALID_VERTICAL_B_REQUEST")
            normalized_items.append(dict(item))
        normalized_recipes = []
        for recipe in recipes:
            if not isinstance(recipe, Mapping) or not isinstance(recipe.get("declaration_key"), str) or not isinstance(recipe.get("recipe_id"), str):
                raise ProductFabricTaskContractError("Vertical B recipe declaration is invalid", code="INVALID_VERTICAL_B_REQUEST")
            normalized_recipes.append(dict(recipe))
        return {"items": tuple(normalized_items), "recipes": tuple(normalized_recipes)}


    @staticmethod
    def _parse_vertical_a_request(request: str) -> dict[str, str] | None:
        """Extract bounded Vertical A intent without capability-specific names."""
        if not isinstance(request, str):
            return None
        normalized = " ".join(request.casefold().split())
        has_block = bool(re.search(r"\bblock\b|\bbloque\b", normalized))
        has_item = bool(re.search(r"block\s*item|blockitem|item\s+asociad|recursos\s+en_us", normalized))
        has_recipe = bool(re.search(r"\brecipe\b|\brecet\w*\b|crafting", normalized))
        has_assets = bool(re.search(r"asset\w*|resource\w*|recurso\w*|blockstate|model", normalized))
        if not (has_block and has_item and has_recipe and has_assets):
            return None
        match = re.search(
            r"(?:called|named|llamad[oa])\s+[\"“']?([a-z0-9][a-z0-9 _-]{1,62}?)[\"”']?(?=\s+(?:to|for|with|including|incluyendo|,|while|preservando|preserving)|[.,]|$)",
            request,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        display_name = " ".join(match.group(1).split()).strip(" -_")
        block_id = re.sub(r"[^a-z0-9]+", "_", display_name.casefold()).strip("_")
        if not display_name or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", block_id):
            return None
        return {
            "display_name": display_name,
            "block_id": block_id,
            "item_id": block_id,
            "recipe_id": block_id,
            "texture_strategy": "REUSE",
        }

    @staticmethod
    def _runtime_observations(namespace: str, block_id: str, item_id: str) -> list[dict[str, object]]:
        block = f"{namespace}:{block_id}"
        item = f"{namespace}:{item_id}"
        return [
            {
                "observation_id": "vertical-a-block-registry",
                "observation_type": "REGISTRY_ENTRY_PRESENT",
                "profile": "registry",
                "selector": {"kind": "registry", "registry_kind": "block", "identifier": block},
                "expected": {"present": True},
                "requirement_ids": ["$validation_id"],
                "phase": "RUNTIME",
            },
            {
                "observation_id": "vertical-a-item-registry",
                "observation_type": "REGISTRY_ENTRY_PRESENT",
                "profile": "registry",
                "selector": {"kind": "registry", "registry_kind": "item", "identifier": item},
                "expected": {"present": True},
                "requirement_ids": ["$validation_id"],
                "phase": "RUNTIME",
            },
            {
                "observation_id": "vertical-a-block-item-association",
                "observation_type": "BLOCK_ITEM_ASSOCIATION",
                "profile": "block_item_association",
                "selector": {"kind": "block_item_association", "item_id": item, "block_id": block},
                "expected": {"associated": True},
                "requirement_ids": ["$validation_id"],
                "phase": "RUNTIME",
            },
        ]

def _java_class_name(identifier: str) -> str:
    return "".join(part.capitalize() for part in identifier.split("_"))


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
