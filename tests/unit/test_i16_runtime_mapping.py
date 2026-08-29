from __future__ import annotations

import importlib.util
from pathlib import Path

from pd_agent.minecraft import runtime_spec_from_requirement
from pd_agent.minecraft import MinecraftObservationType, ObservationRequest


REPO_ROOT = Path(__file__).parents[2]


def _driver_module():
    path = REPO_ROOT / "scripts" / "validation" / "run_i16.py"
    spec = importlib.util.spec_from_file_location("i16_runtime_driver", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_i16_runtime_mapping_uses_observation_request_contract() -> None:
    driver = _driver_module()
    task = driver._load_json(REPO_ROOT / "benchmarks" / "tasks" / "F6-T3-v5.json")

    contract = driver.build_contract(task, REPO_ROOT / "benchmarks" / "projects" / "v0_5_fabric_base")
    plan = runtime_spec_from_requirement(contract.validation_requirements[0])

    assert [item.observation_id for item in plan.observations] == ["F6-T3:primary", "F6-T3:item"]
    assert plan.observations[0].selector == {
        "kind": "registry",
        "registry_kind": "block",
        "identifier": "examplemod:server_core",
    }
    assert plan.observations[1].selector == {
        "kind": "registry",
        "registry_kind": "item",
        "identifier": "examplemod:server_core",
    }
    assert plan.observations[0].expected == {"present": True}
    assert plan.observations[0].parameters == {}
    assert plan.observation_requirements == {
        "F6-T3:primary": ("runtime",),
        "F6-T3:item": ("runtime",),
    }


def test_minecraft_spec_round_trip_preserves_all_observation_requests() -> None:
    from pd_agent.minecraft import MinecraftTestSpec

    requests = (
        ObservationRequest(
            observation_id="obs-primary",
            observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
            profile="registry_entry",
            selector={"kind": "registry", "registry_kind": "block", "identifier": "examplemod:server_core"},
            expected={"present": True},
        ),
        ObservationRequest(
            observation_id="obs-item",
            observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
            profile="registry_entry",
            selector={"kind": "registry", "registry_kind": "item", "identifier": "examplemod:server_core"},
            expected={"present": True},
        ),
    )
    spec = MinecraftTestSpec(
        target_jar=Path("target.jar"),
        target_mod_id="examplemod",
        minecraft_version="1.21.11",
        loader_version="0.19.3",
        test_id="runtime",
        timeout_seconds=30,
        observation_requests=requests,
    )

    restored = MinecraftTestSpec.from_dict(spec.to_dict())

    assert restored.observation_requests == requests
