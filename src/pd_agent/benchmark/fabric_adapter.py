"""Adapter from benchmark task data to the normal Fabric product contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pd_agent.core import (
    FabricEnvironmentConstraints,
    FabricKnowledgeSignal,
    FabricMutationExpectation,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
)
from pd_agent.fabric import FabricNormalOrchestrator, FabricOrchestrationResult

from .models import BenchmarkConfig, BenchmarkTask


class BenchmarkFabricTaskAdapterError(ValueError):
    """Task cannot be translated without changing its semantics."""


@dataclass(frozen=True, slots=True)
class BenchmarkFabricTaskAdapter:
    """Translate a benchmark definition without leaking benchmark-only data."""

    def to_contract(self, task: BenchmarkTask) -> FabricTaskContract:
        if not isinstance(task, BenchmarkTask):
            raise BenchmarkFabricTaskAdapterError("adapter requires a BenchmarkTask")

        spec = task.acceptance.spec if isinstance(task.acceptance.spec, Mapping) else {}
        requirements: list[FabricRequirement] = []
        validation_ids: dict[str, str] = {}
        mutation_expectations: list[FabricMutationExpectation] = []

        if task.validation.source_change:
            requirements.append(FabricRequirement(requirement_id="source-change", description="a relevant source change is required"))
        for kind, enabled in (
            ("build", task.validation.build),
            ("artifact", task.validation.artifact),
            ("minecraft", task.validation.minecraft),
        ):
            if enabled:
                requirement_id = f"validation-{kind}"
                requirements.append(FabricRequirement(requirement_id=requirement_id, description=f"{kind} validation must pass"))
                validation_ids[kind] = requirement_id

        raw_resources = spec.get("required_resources", ())
        if "required_resources" in spec and raw_resources is None:
            raise BenchmarkFabricTaskAdapterError("required_resources must be a sequence")
        if not isinstance(raw_resources, (list, tuple)):
            raise BenchmarkFabricTaskAdapterError("required_resources must be a sequence")
        for index, resource in enumerate(raw_resources or (), start=1):
            if not isinstance(resource, Mapping):
                raise BenchmarkFabricTaskAdapterError("required resource must be an object")
            path = resource.get("path")
            if not isinstance(path, str) or not path.strip():
                raise BenchmarkFabricTaskAdapterError("required resource path is missing")
            requirement_id = f"resource-{index}"
            requirements.append(FabricRequirement(requirement_id=requirement_id, description=f"required resource exists: {path}"))
            mutation_expectations.append(
                FabricMutationExpectation(
                    expectation_id=f"mutation-{index}",
                    role="resource",
                    path=path,
                    required=bool(resource.get("required", True)),
                )
            )

        if not requirements:
            raise BenchmarkFabricTaskAdapterError("task has no product requirements")

        validation_requirements = tuple(
            FabricValidationRequirement(
                validation_requirement_id=f"validate-{kind}",
                requirement_ids=(requirement_id,),
                kind=kind,
                spec=self._validation_spec(spec, kind),
            )
            for kind, requirement_id in validation_ids.items()
        )
        knowledge_signals = self._knowledge_signals(spec)
        environment = task.environment
        return FabricTaskContract(
            task_id=task.task_id,
            revision=task.task_version,
            goal=task.description,
            requirements=tuple(requirements),
            validation_requirements=validation_requirements,
            knowledge_signals=knowledge_signals,
            mutation_expectations=tuple(mutation_expectations),
            environment_constraints=FabricEnvironmentConstraints(
                minecraft_version=environment.minecraft_version,
                loader_version=environment.loader_version,
                fabric_api_version=environment.fabric_api_version,
                yarn_version=environment.yarn_version,
                java_version=environment.java_version,
                extra={},
            ),
        )

    def execute_product(
        self,
        task: BenchmarkTask,
        config: BenchmarkConfig,
        *,
        project_root: Path,
        orchestrator: FabricNormalOrchestrator,
    ) -> FabricOrchestrationResult:
        """Run exactly one product flow; benchmark repetition remains external."""

        if not isinstance(config, BenchmarkConfig):
            raise BenchmarkFabricTaskAdapterError("adapter requires a BenchmarkConfig")
        return orchestrator.run(
            self.to_contract(task),
            Path(project_root),
            brain_enabled=bool(config.brain_enabled),
        )

    def _validation_spec(self, acceptance: Mapping[str, Any], kind: str) -> dict[str, Any]:
        """Keep only structural validation metadata, never benchmark answers."""

        if kind == "artifact":
            resources = acceptance.get("required_resources", ())
            paths = tuple(
                str(item.get("path"))
                for item in resources
                if isinstance(item, Mapping) and isinstance(item.get("path"), str)
            )
            return {"required_paths": paths}
        if kind == "minecraft":
            observations = acceptance.get("required_minecraft_observations", ())
            return {"required_observation_count": len(observations) if isinstance(observations, (list, tuple)) else 0}
        return {}

    def _knowledge_signals(self, acceptance: Mapping[str, Any]) -> tuple[FabricKnowledgeSignal, ...]:
        raw = acceptance.get("knowledge_needs", acceptance.get("knowledge_need", ()))
        if isinstance(raw, Mapping):
            raw = (raw,)
        if not isinstance(raw, (list, tuple)):
            return ()
        signals: list[FabricKnowledgeSignal] = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, Mapping) or not str(item.get("query", "")).strip():
                raise BenchmarkFabricTaskAdapterError("knowledge signal must contain a query")
            signals.append(
                FabricKnowledgeSignal(
                    signal_id=str(item.get("id", f"knowledge-{index}")),
                    query=str(item["query"]),
                    category=str(item["type"]) if item.get("type") is not None else None,
                    required=False,
                )
            )
        return tuple(signals)


def benchmark_task_to_fabric_contract(task: BenchmarkTask) -> FabricTaskContract:
    """Functional adapter entry point."""

    return BenchmarkFabricTaskAdapter().to_contract(task)


__all__ = [
    "BenchmarkFabricTaskAdapter",
    "BenchmarkFabricTaskAdapterError",
    "benchmark_task_to_fabric_contract",
]
