from __future__ import annotations

from pathlib import Path

import pytest

from pd_agent.benchmark import (
    BenchmarkAcceptanceSpec,
    BenchmarkConfig,
    BenchmarkEnvironmentRequirements,
    BenchmarkFabricTaskAdapter,
    BenchmarkFabricTaskAdapterError,
    BenchmarkFixtureReference,
    BenchmarkTask,
    BenchmarkValidationRequirements,
)
from pd_agent.core import FabricTaskContract


def _task(*, version: str = "5", description: str = "Implement the server feature", acceptance: dict | None = None) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="F6-T3",
        task_version=version,
        description=description,
        prompt="Create the implementation using the available tools.",
        fixture=BenchmarkFixtureReference(fixture_ref="fixture", fixture_identity="fixture-sha", identity_algorithm="sha256-tree-v2"),
        validation=BenchmarkValidationRequirements(build=True, artifact=True, minecraft=True, source_change=True),
        acceptance=BenchmarkAcceptanceSpec(
            acceptance_type="minecraft_harness",
            spec=acceptance or {
                "target_mod_id": "examplemod",
                "required_resources": [{"path": "assets/examplemod/lang/en_us.json", "assertions": [{"kind": "text_contains", "value": "Server Core"}]}],
                "required_minecraft_observations": [{"type": "server", "expected": "pass"}],
                "knowledge_needs": [{"id": "k1", "query": "Fabric server registration", "type": "API"}],
                "oracle": "must-not-enter-contract",
            },
        ),
        environment=BenchmarkEnvironmentRequirements(
            minecraft_version="1.21.11", loader_version="0.19.3", loom_version="1.13.3",
            yarn_version="1.21.11+build.6", java_version="21", fabric_api_version="0.141.6+1.21.11",
        ),
        tags=("fabric", "brain"),
    )


def _config(*, brain: bool = True) -> BenchmarkConfig:
    return BenchmarkConfig(config_id="cfg", provider="fake", model="fake-model", brain_enabled=brain)


def test_maps_task_to_contract_without_prompt_or_oracle_leakage() -> None:
    contract = BenchmarkFabricTaskAdapter().to_contract(_task())

    assert isinstance(contract, FabricTaskContract)
    assert contract.task_id == "F6-T3"
    assert contract.revision == "5"
    assert contract.goal == "Implement the server feature"
    assert "Create the implementation" not in contract.canonical_json()
    assert "oracle" not in contract.canonical_json()
    assert "Server Core" not in contract.canonical_json()
    assert "text_contains" not in contract.canonical_json()


def test_same_revision_is_deterministic_and_repetition_is_not_identity() -> None:
    adapter = BenchmarkFabricTaskAdapter()
    first = adapter.to_contract(_task())
    second = adapter.to_contract(_task())

    assert first.identity() == second.identity()
    assert first.revision == "5"


def test_material_task_revision_changes_identity() -> None:
    adapter = BenchmarkFabricTaskAdapter()
    assert adapter.to_contract(_task(version="5")).identity() != adapter.to_contract(_task(version="6")).identity()


def test_maps_requirements_validation_mutations_and_environment() -> None:
    contract = BenchmarkFabricTaskAdapter().to_contract(_task())
    requirement_ids = {item.requirement_id for item in contract.requirements}

    assert {"source-change", "validation-build", "validation-artifact", "validation-minecraft", "resource-1"} <= requirement_ids
    assert {item.kind for item in contract.validation_requirements} == {"build", "artifact", "minecraft"}
    assert contract.validation_requirements[1].spec == {"required_paths": ["assets/examplemod/lang/en_us.json"]}
    assert contract.mutation_expectations[0].role == "resource"
    assert contract.mutation_expectations[0].path == "assets/examplemod/lang/en_us.json"
    assert contract.environment_constraints.minecraft_version == "1.21.11"
    assert contract.environment_constraints.fabric_api_version == "0.141.6+1.21.11"


def test_maps_knowledge_signals_without_expected_answers() -> None:
    contract = BenchmarkFabricTaskAdapter().to_contract(_task())
    assert len(contract.knowledge_signals) == 1
    assert contract.knowledge_signals[0].query == "Fabric server registration"
    assert "expected" not in contract.canonical_json()


def test_brain_flag_is_forwarded_to_the_normal_product_path() -> None:
    calls: list[bool] = []

    class FakeOrchestrator:
        def run(self, _contract, _root, *, brain_enabled):
            calls.append(brain_enabled)
            return "result"

    adapter = BenchmarkFabricTaskAdapter()
    assert adapter.execute_product(_task(), _config(brain=True), project_root=Path("."), orchestrator=FakeOrchestrator()) == "result"
    assert adapter.execute_product(_task(), _config(brain=False), project_root=Path("."), orchestrator=FakeOrchestrator()) == "result"
    assert calls == [True, False]


@pytest.mark.parametrize("raw", [None, "not-a-list", ["bad"]])
def test_ambiguous_resources_fail_closed(raw) -> None:
    acceptance = {"required_resources": raw}
    with pytest.raises(BenchmarkFabricTaskAdapterError):
        BenchmarkFabricTaskAdapter().to_contract(_task(acceptance=acceptance))


def test_missing_product_obligations_fail_closed() -> None:
    task = BenchmarkTask(
        task_id="empty", task_version="1", description="empty", prompt="prompt",
        fixture=BenchmarkFixtureReference(fixture_ref="fixture"),
        validation=BenchmarkValidationRequirements(),
        acceptance=BenchmarkAcceptanceSpec(acceptance_type="empty", spec={}),
        environment=BenchmarkEnvironmentRequirements(),
    )
    with pytest.raises(BenchmarkFabricTaskAdapterError):
        BenchmarkFabricTaskAdapter().to_contract(task)


def test_benchmark_executor_exposes_explicit_product_route() -> None:
    from pd_agent.benchmark.executor import BenchmarkExecutor

    assert hasattr(BenchmarkExecutor, "execute_product_path")


def test_adapter_does_not_import_benchmark_into_product_path() -> None:
    product_files = [
        Path(__file__).parents[2] / "src/pd_agent/fabric/orchestration.py",
        Path(__file__).parents[2] / "src/pd_agent/bootstrap.py",
    ]
    assert all("pd_agent.benchmark" not in path.read_text(encoding="utf-8") for path in product_files)
