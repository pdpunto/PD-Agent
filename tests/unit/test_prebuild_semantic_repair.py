from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_agent.benchmark import BenchmarkAcceptanceSpec, build_public_validation_contract
from pd_agent.core import AgentResponse, FabricRequirement, FabricTaskContract, FabricValidationRequirement, ToolCall, ValidationStatus, ValidationViolation
from pd_agent.validation import PreBuildValidationError, PreBuildWorkspaceValidator
from pd_agent.runtime.engine import _format_validation_feedback_value, _format_validation_violation
from tests.unit.test_l9_runtime import ScriptedProvider, _controller, _runtime_project


def _contract(*resources: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "required_resources": list(resources)}


def _json_resource(path: str, *assertions: dict[str, object]) -> dict[str, object]:
    return {"path": path, "resource_type": "json", "assertions": list(assertions)}


def test_validation_feedback_formats_json_values_deterministically_and_bounded() -> None:
    violation = ValidationViolation(
        code="CHECK",
        requirement="generic requirement",
        observed=[1, True, {"z": 2, "a": None}],
        message="diagnostic",
        expected=7,
        actual=False,
        evidence_refs=("evidence/ref",),
    )

    lines = _format_validation_violation(violation)
    rendered = "\n".join(lines)
    assert 'expected: 7' in rendered
    assert 'actual: false' in rendered
    assert 'observed: [1,true,{"a":null,"z":2}]' in rendered
    assert 'evidence_refs: ["evidence/ref"]' in rendered
    assert _format_validation_feedback_value("x" * 3000) == "[truncated: 3002 bytes]"


def test_prebuild_passes_without_resources(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "no-resources", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="edit",
                tool_calls=(
                    ToolCall(
                        call_id="1",
                        tool_name="write_file",
                        arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod { int x; }\n"},
                    ),
                ),
            )
        ]
    )
    controller, storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    run_state, _report = controller.run(root, "T1-like", validation_contract=_contract())

    assert run_state.state.value == "COMPLETED"
    assert run_state.build_attempt_count == 1
    assert run_state.validation_results[-1].status is ValidationStatus.PASS
    assert any(event.event_type.value == "VALIDATION_COMPLETED" for event in storage.read_events(run_state.run_id))


def test_prebuild_reports_missing_invalid_pointer_and_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    validator = PreBuildWorkspaceValidator()

    missing = validator.validate(root, _contract(_json_resource("assets/lang.json")))
    assert missing.status is ValidationStatus.REPAIRABLE_FAIL
    assert missing.violations[0].code == "RESOURCE_MISSING"

    path = root / "assets" / "lang.json"
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    invalid = validator.validate(root, _contract(_json_resource("assets/lang.json")))
    assert invalid.violations[0].code == "RESOURCE_INVALID_JSON"

    path.write_text(json.dumps({"item.example": "Wrong"}), encoding="utf-8")
    pointer = _json_resource(
        "assets/lang.json",
        {"kind": "json_pointer_present", "path": "/item.missing"},
        {"kind": "json_pointer_equals", "path": "/item.example", "value": "Expected"},
    )
    failed = validator.validate(root, _contract(pointer))
    assert [item.code for item in failed.violations] == ["JSON_POINTER_MISSING", "JSON_POINTER_MISMATCH"]


def test_t2_and_t3_contracts_pass_prebuild_from_fabric_resource_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    resource_root = root / "src/main/resources"
    (resource_root / "assets/examplemod/lang").mkdir(parents=True)
    (resource_root / "data/examplemod/recipe").mkdir(parents=True)
    (resource_root / "assets/examplemod/lang/en_us.json").write_text(
        json.dumps(
            {
                "block.examplemod.marble_lantern": "Marble Lantern",
                "item.examplemod.marble_lantern": "Marble Lantern",
                "block.examplemod.server_core": "Server Core",
                "item.examplemod.server_core": "Server Core",
            }
        ),
        encoding="utf-8",
    )
    (resource_root / "data/examplemod/recipe/server_core.json").write_text(
        json.dumps({
            "type": "minecraft:crafting_shaped",
            "pattern": ["III", "ICI", "III"],
            "key": {"I": {"item": "minecraft:iron_ingot"}, "C": {"item": "minecraft:crafting_table"}},
            "result": {"id": "examplemod:server_core", "count": 1},
        }),
        encoding="utf-8",
    )
    validator = PreBuildWorkspaceValidator(resource_roots=(resource_root,))
    for task_id in ("F6-T2", "F6-T3"):
        task = json.loads((Path("benchmarks/tasks") / f"{task_id}-v5.json").read_text(encoding="utf-8"))
        contract = build_public_validation_contract(BenchmarkAcceptanceSpec.from_dict(task["acceptance"]))
        result = validator.validate(root, contract)
        assert result.status is ValidationStatus.PASS


def test_prebuild_rejects_structurally_invalid_recipe(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    resource_root = root / "src/main/resources/data/examplemod/recipe"
    resource_root.mkdir(parents=True)
    recipe = resource_root / "server_core.json"
    recipe.write_text(json.dumps({"result": {"id": "examplemod:server_core", "count": 1}}), encoding="utf-8")

    result = PreBuildWorkspaceValidator(resource_roots=(root / "src/main/resources",)).validate(
        root,
        _contract(_json_resource("data/examplemod/recipe/server_core.json")),
    )

    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert [item.code for item in result.violations] == ["RECIPE_SCHEMA_INVALID"]


def test_product_contract_cannot_build_with_invalid_recipe(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    recipe = root / "src/main/resources/data/examplemod/recipe/server_core.json"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(json.dumps({"result": {"id": "examplemod:server_core"}}), encoding="utf-8")
    contract = FabricTaskContract(
        task_id="server-core",
        revision="product-1",
        goal="add Server Core",
        requirements=(FabricRequirement(requirement_id="artifact", description="artifact"),),
        validation_requirements=(FabricValidationRequirement(
            validation_requirement_id="validate-artifact",
            requirement_ids=("artifact",),
            kind="artifact",
            spec={"required_paths": ("src/main/resources/data/examplemod/recipe/server_core.json",)},
        ),),
    )

    result = PreBuildWorkspaceValidator().validate(root, contract)

    assert result.status is ValidationStatus.REPAIRABLE_FAIL
    assert result.violations[0].code == "RECIPE_SCHEMA_INVALID"


def test_repair_feedback_allows_write_then_build_and_rechecks(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "repair", build_state="pass")
    lang_path = "assets/examplemod/lang/en_us.json"
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="source",
                tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"}),),
            ),
            AgentResponse(
                assistant_message="repair resource",
                tool_calls=(ToolCall(call_id="2", tool_name="create_file", arguments={"path": lang_path, "content": '{"item.example": "Example"}\n'}),),
            ),
        ]
    )
    controller, storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    contract = _contract(_json_resource(lang_path, {"kind": "json_pointer_present", "path": "/item.example"}))
    run_state, report = controller.run(
        root,
        "repair resource",
        validation_contract=contract,
    )

    assert run_state.state.value == "COMPLETED"
    assert report.validation_results[-1].status is ValidationStatus.PASS
    assert any(item.status is ValidationStatus.REPAIRABLE_FAIL for item in run_state.validation_results)
    assert run_state.build_attempt_count == 1
    events = storage.read_events(run_state.run_id)
    assert any(event.event_type.value == "SEMANTIC_REPAIR_FEEDBACK" for event in events)
    assert any(event.event_type.value == "BUILD_STARTED" for event in events)
    feedback = next(event.payload["feedback"] for event in events if event.event_type.value == "SEMANTIC_REPAIR_FEEDBACK")
    assert "class " not in feedback
    assert "Fabric" not in feedback
    diagnostics = next(event.payload["diagnostics"] for event in events if event.event_type.value == "SEMANTIC_REPAIR_FEEDBACK")
    assert diagnostics[0]["code"] == "RESOURCE_MISSING"
    assert "expected" not in feedback
    assert any("Semantic validation failed before build:" in message.content for request in provider.requests for message in request.messages)


def test_repair_feedback_allows_inspection_before_next_mutation(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multiturn-repair", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="source",
                tool_calls=(ToolCall(
                    call_id="1",
                    tool_name="write_file",
                    arguments={
                        "path": "src/main/java/com/example/ExampleMod.java",
                        "content": "class ExampleMod {}\n",
                    },
                ),),
            ),
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(ToolCall(
                    call_id="2",
                    tool_name="read_file",
                    arguments={"path": "src/main/java/com/example/ExampleMod.java"},
                ),),
            ),
            AgentResponse(
                assistant_message="repair resource",
                tool_calls=(ToolCall(
                    call_id="3",
                    tool_name="create_file",
                    arguments={
                        "path": "assets/examplemod/lang/en_us.json",
                        "content": '{"item.example": "Example"}\n',
                    },
                ),),
            ),
        ]
    )
    controller, _storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()

    state, _report = controller.run(
        root,
        "repair after inspection",
        validation_contract=_contract(_json_resource("assets/examplemod/lang/en_us.json", {"kind": "json_pointer_present", "path": "/item.example"})),
    )

    assert state.state.value == "COMPLETED"
    assert state.build_attempt_count == 1
    assert len(provider.requests) == 3


def test_semantic_repair_inspection_stall_is_bounded_without_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "multiturn-stall", build_state="pass")
    inspections = [
        AgentResponse(
            assistant_message=f"inspect {index}",
            tool_calls=(ToolCall(
                call_id=str(index),
                tool_name="read_file",
                arguments={"path": "src/main/java/com/example/ExampleMod.java"},
            ),),
        )
        for index in range(1, 9)
    ]
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="source",
                tool_calls=(ToolCall(
                    call_id="source",
                    tool_name="write_file",
                    arguments={
                        "path": "src/main/java/com/example/ExampleMod.java",
                        "content": "class ExampleMod {}\n",
                    },
                ),),
            ),
            *inspections,
        ]
    )
    controller, _storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()

    state, _report = controller.run(
        root,
        "bounded repair stall",
        validation_contract=_contract(_json_resource("assets/missing.json")),
    )

    assert state.state.value == "FAILED"
    assert state.termination_reason == "semantic repair produced no mutation"
    assert state.build_attempt_count == 0
    assert len(provider.requests) == 3


def test_repeated_same_failure_stops_without_build(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "stall", build_state="pass")
    provider = ScriptedProvider(
        [
            AgentResponse(
                assistant_message="source",
                tool_calls=(ToolCall(call_id="1", tool_name="write_file", arguments={"path": "src/main/java/com/example/ExampleMod.java", "content": "class ExampleMod {}\n"}),),
            ),
            AgentResponse(
                assistant_message="inspect",
                tool_calls=(ToolCall(
                    call_id="2",
                    tool_name="read_file",
                    arguments={"path": "src/main/java/com/example/ExampleMod.java"},
                ),),
            ),
            AgentResponse(
                assistant_message="inspect again",
                tool_calls=(ToolCall(
                    call_id="3",
                    tool_name="read_file",
                    arguments={"path": "src/main/java/com/example/ExampleMod.java"},
                ),),
            ),
        ]
    )
    controller, _storage = _controller(root, provider)
    controller.pre_build_validator = PreBuildWorkspaceValidator()
    run_state, _report = controller.run(
        root,
        "stall",
        validation_contract=_contract(_json_resource("assets/missing.json")),
    )

    assert run_state.state.value == "FAILED"
    assert run_state.termination_reason == "semantic repair produced no mutation"
    assert run_state.build_attempt_count == 0
    assert run_state.validation_repeat_count == 0


def test_malformed_contract_is_not_agent_repair_feedback(tmp_path: Path) -> None:
    root = tmp_path / "malformed"
    root.mkdir()
    with pytest.raises(PreBuildValidationError):
        PreBuildWorkspaceValidator().validate(root, {"required_resources": "invalid"})
