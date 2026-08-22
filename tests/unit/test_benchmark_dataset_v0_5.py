from __future__ import annotations

import json
from pathlib import Path

from pd_agent.benchmark import BenchmarkCatalog, BenchmarkConfig, BenchmarkDataset, BenchmarkScheduler
from pd_agent.benchmark.workspace import compute_fixture_identity


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = ROOT / "benchmarks"
PROJECT_BASE = BENCHMARK_ROOT / "projects" / "v0_5_fabric_base"
EXPECTED_PROJECT_BASE_IDENTITY = "3c27fd809429bc57637b3d930733d5cc7c1891073e9307325d30d25058161396"
DATASET_ID = "PD_AGENT_BENCHMARK_DATASET_V0.5_5"
DATASET_VERSION = "0.5.5"
TASK_VERSION = "5"


def _catalog() -> BenchmarkCatalog:
    return BenchmarkCatalog.load(BENCHMARK_ROOT)


def _task_ids() -> tuple[str, ...]:
    return ("F6-T1", "F6-T2", "F6-T3")


def _config(config_id: str, *, brain_enabled: bool) -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id=config_id,
        provider="gemini",
        model="gemini-3.5-flash-lite",
        brain_enabled=brain_enabled,
        model_config={"temperature": 0.2},
        provider_config={"timeout_seconds": 60},
        knowledge_config={"offline": True},
        target_repetition_count=3,
    )


def test_v0_5_dataset_loads_with_exactly_three_tasks() -> None:
    catalog = _catalog()
    dataset = catalog.dataset_for(DATASET_ID, DATASET_VERSION)
    expected = BenchmarkDataset.from_dict(
        json.loads((BENCHMARK_ROOT / "datasets" / "PD_AGENT_BENCHMARK_DATASET_V0.5_5.json").read_text(encoding="utf-8"))
    )

    assert dataset == expected
    assert len(dataset.tasks) == 3
    assert tuple(reference.task_id for reference in dataset.tasks) == _task_ids()
    assert len({(reference.task_id, reference.task_version) for reference in dataset.tasks}) == 3
    assert dataset.dataset_version == "0.5.5"
    assert dataset.dataset_id == "PD_AGENT_BENCHMARK_DATASET_V0.5_5"


def test_v0_5_dataset_tasks_resolve_to_the_pinned_project_base() -> None:
    catalog = _catalog()
    expected_hash = compute_fixture_identity(PROJECT_BASE)

    for task_id in _task_ids():
        task = catalog.task_for(task_id, TASK_VERSION)

        assert task.fixture.fixture_ref == "projects/v0_5_fabric_base"
        assert task.fixture.identity_algorithm == "sha256-tree-v2"
        assert task.fixture.fixture_identity == expected_hash
        assert task.validation.build is True
        assert task.validation.artifact is True
        assert task.validation.minecraft is True
        assert task.validation.source_change is True
        assert task.acceptance.acceptance_type == "fabric_feature"
        assert task.acceptance.spec["project_base_ref"] == "projects/v0_5_fabric_base"
        assert task.acceptance.spec["observation_type"] == "REGISTRY_ENTRY_PRESENT"
        assert task.acceptance.spec["preservation_invariants"]["mod_id"] == "examplemod"
        assert task.acceptance.spec["preservation_invariants"]["entrypoints"]["main"] == ["com.example.examplemod.ExampleMod"]
        assert "solution" not in task.acceptance.spec
        assert "expected_class_name" not in task.acceptance.spec
        assert "target_method" not in task.acceptance.spec
        assert "api_signature" not in task.acceptance.spec
        assert task.acceptance.spec["knowledge_needs"][0]["environment"]["fabric_api_version"] == "0.141.6+1.21.11"
        if task_id == "F6-T1":
            assert task.acceptance.spec.get("required_resources", []) == []
            assert task.acceptance.spec.get("required_minecraft_observations", []) == []
        elif task_id == "F6-T2":
            assert len(task.acceptance.spec["required_minecraft_observations"]) == 1
            assert task.acceptance.spec["required_minecraft_observations"][0]["observation_params"] == {
                "registry_kind": "item",
                "identifier": "examplemod:marble_lantern",
            }
            assert task.acceptance.spec["required_resources"][0]["path"] == "assets/examplemod/lang/en_us.json"
        elif task_id == "F6-T3":
            assert len(task.acceptance.spec["required_minecraft_observations"]) == 1
            assert task.acceptance.spec["required_minecraft_observations"][0]["observation_params"] == {
                "registry_kind": "item",
                "identifier": "examplemod:server_core",
            }
            assert [resource["path"] for resource in task.acceptance.spec["required_resources"]] == [
                "assets/examplemod/lang/en_us.json",
                "data/examplemod/recipe/server_core.json",
            ]
        assert task.fixture.metadata["project_base"] == "benchmarks/projects/v0_5_fabric_base"


def test_v0_5_dataset_prompts_do_not_leak_benchmark_solution_hints() -> None:
    catalog = _catalog()
    expected_names = {
        "F6-T1": "Signal Charm",
        "F6-T2": "Marble Lantern",
        "F6-T3": "Server Core",
    }
    forbidden_tokens = {
        "Registry.register",
        "Identifier.of",
        "FabricBlockSettings",
        "BlockItem",
        "Items",
        "Registries.BLOCK",
    }

    for task_id in _task_ids():
        task = catalog.task_for(task_id, TASK_VERSION)

        assert "B001" not in task.prompt
        assert "B002" not in task.prompt
        assert "B003" not in task.prompt
        assert "TargetBridge" not in task.prompt
        assert "ExampleModClient" not in task.prompt
        assert expected_names[task_id] in task.prompt
        assert task.acceptance.spec["observation_params"]["identifier"].startswith("examplemod:")
        for hint in task.acceptance.spec["knowledge_needs"][0]["hints"]:
            assert hint not in forbidden_tokens


def test_v0_5_dataset_acceptance_knows_the_expected_knowledge_levels() -> None:
    catalog = _catalog()
    expected = {
        "F6-T1": "LOW",
        "F6-T2": "LOW",
        "F6-T3": "MATERIAL",
    }

    for task_id, level in expected.items():
        task = catalog.task_for(task_id, TASK_VERSION)
        need = task.acceptance.spec["knowledge_needs"][0]
        assert task.acceptance.spec["knowledge_need_level"] == level
        assert need["environment"]["minecraft_version"] == "1.21.11"
        assert need["environment"]["loader_version"] == "0.19.3"
        assert need["environment"]["loom_version"] == "1.13.3"
        assert need["environment"]["mappings_version"] == "1.21.11+build.6"
        assert need["environment"]["java_version"] == "21"
        assert need["query"]
        assert all("Registry.register" not in hint for hint in need["hints"])
        assert all("Identifier.of" not in hint for hint in need["hints"])


def test_v0_5_dataset_is_scheduler_compatible() -> None:
    catalog = _catalog()
    tasks = tuple(catalog.task_for(task_id, TASK_VERSION) for task_id in _task_ids())
    configs = (
        _config("cfg-off", brain_enabled=False),
        _config("cfg-on", brain_enabled=True),
    )

    schedule = BenchmarkScheduler().create_initial_schedule(
        tasks,
        configs,
        target_valid_repetitions=3,
        max_attempts_per_cell=5,
        scheduling_seed=17,
    )

    assert len(schedule.cells) == 6
    assert {cell.task_id for cell in schedule.cells} == set(_task_ids())
    assert {cell.config_id for cell in schedule.cells} == {"cfg-off", "cfg-on"}
    assert all(cell.target_valid_repetitions == 3 for cell in schedule.cells)
    assert all(cell.max_attempts_per_cell == 5 for cell in schedule.cells)
    assert len(schedule.attempts) > 0


def test_v0_5_dataset_has_stable_fixture_identity() -> None:
    expected = compute_fixture_identity(PROJECT_BASE)

    assert expected == EXPECTED_PROJECT_BASE_IDENTITY
    assert expected == compute_fixture_identity(PROJECT_BASE)
    assert _catalog().fixture_identities[("F6-T1", TASK_VERSION)] == expected
    assert _catalog().fixture_identities[("F6-T2", TASK_VERSION)] == expected
    assert _catalog().fixture_identities[("F6-T3", TASK_VERSION)] == expected


def test_v0_5_legacy_dataset_remains_historical_but_not_official() -> None:
    catalog = _catalog()
    legacy = catalog.dataset_for("PD_AGENT_BENCHMARK_DATASET_V0.5_1", "0.5.1")
    historical = catalog.dataset_for("PD_AGENT_BENCHMARK_DATASET_V0.5_3", "0.5.3")
    superseded = catalog.dataset_for("PD_AGENT_BENCHMARK_DATASET_V0.5_4", "0.5.4")

    assert legacy.dataset_id == "PD_AGENT_BENCHMARK_DATASET_V0.5_1"
    assert legacy.dataset_version == "0.5.1"
    assert historical.dataset_id == "PD_AGENT_BENCHMARK_DATASET_V0.5_3"
    assert historical.dataset_version == "0.5.3"
    assert superseded.dataset_id == "PD_AGENT_BENCHMARK_DATASET_V0.5_4"
    assert superseded.dataset_version == "0.5.4"
    assert DATASET_ID == "PD_AGENT_BENCHMARK_DATASET_V0.5_5"
