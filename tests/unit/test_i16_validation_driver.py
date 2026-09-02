from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("i16_driver", ROOT / "scripts" / "validation" / "run_i16.py")
assert SPEC and SPEC.loader
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def test_config_validation_accepts_frozen_config() -> None:
    config = driver._load_json(ROOT / "benchmarks/configs/openai-official-gpt-5.6-luna-brain-on.json")
    driver.validate_config(config)


def test_config_validation_rejects_provider_or_model_drift() -> None:
    config = driver._load_json(ROOT / "benchmarks/configs/openai-official-gpt-5.6-luna-brain-on.json")
    config["model"] = "other"
    try:
        driver.validate_config(config)
    except driver.PrecheckError:
        pass
    else:
        raise AssertionError("model drift must fail closed")


def test_current_explicit_baseline_passes_and_wrong_one_fails() -> None:
    state = {"head": "current", "origin_main": "current"}
    driver.validate_baseline("current", state)
    try:
        driver.validate_baseline("stale", state)
    except driver.PrecheckError:
        pass
    else:
        raise AssertionError("stale baseline must fail closed")


def test_redacted_manifest_never_persists_secret(tmp_path: Path, monkeypatch) -> None:
    secret = "secret-not-to-persist"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    args = type("Args", (), {"mode": "precheck", "authorize_i16": False})()
    config = {"config_id": "cfg", "provider": "openai", "model": "gpt-5.6-luna", "brain_enabled": True}
    task = {"task_id": "F6-T3"}
    driver._redacted_manifest(tmp_path / "manifest.json", args, config, task)
    assert secret not in (tmp_path / "manifest.json").read_text(encoding="utf-8")


def test_i16_manifest_defaults_to_official_flags(tmp_path: Path) -> None:
    args = driver.parse_args(["--seed-root", "s", "--seed-manifest", "m", "--knowledge-pack", "p", "--budget-state", "b", "--global-budget-ceiling", "0.35", "--gradle-home", "g", "--launch-root", "l"])
    config = {"config_id": "cfg", "provider": "openai", "model": "gpt-5.6-luna", "brain_enabled": True}
    task = {"task_id": "F6-T3"}

    driver._redacted_manifest(tmp_path / "manifest.json", args, config, task)
    payload = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert payload["experimental"] is False
    assert payload["non_official"] is False


def test_i16_manifest_preserves_explicit_non_official_flags(tmp_path: Path) -> None:
    args = driver.parse_args(["--seed-root", "s", "--seed-manifest", "m", "--knowledge-pack", "p", "--budget-state", "b", "--global-budget-ceiling", "0.35", "--gradle-home", "g", "--launch-root", "l", "--experimental", "--non-official"])
    config = {"config_id": "cfg", "provider": "openai", "model": "gpt-5.6-luna", "brain_enabled": True}
    task = {"task_id": "F6-T3"}

    driver._redacted_manifest(tmp_path / "manifest.json", args, config, task)
    payload = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert payload["experimental"] is True
    assert payload["non_official"] is True


def test_live_requires_both_live_switch_and_authorization() -> None:
    args = driver.parse_args(["--mode", "live", "--seed-root", "s", "--seed-manifest", "m", "--knowledge-pack", "p", "--budget-state", "b", "--gradle-home", "g", "--launch-root", "l", "--global-budget-ceiling", "0.30"])
    assert args.live is False
    assert args.authorize_i16 is False


def test_driver_does_not_own_benchmark_scheduler() -> None:
    source = (ROOT / "scripts" / "validation" / "run_i16.py").read_text(encoding="utf-8")
    assert "BenchmarkExecutor" not in source
    assert "BenchmarkFunctionalValidator" not in source
    assert "BenchmarkTask" not in source


def test_live_source_connects_shared_budget_guard_before_provider() -> None:
    source = (ROOT / "scripts" / "validation" / "run_i16.py").read_text(encoding="utf-8")
    assert "budget_session.guard(" in source
    assert "consumer_id=run_id" in source
    assert "budget_guard=budget_guard" in source
    assert "budget_guard.begin_attempt(" in source
    assert "ownership_root=launch / \"economic-ownership\"" in source
    assert "budget_guard.end_attempt()" in source


def test_live_source_propagates_execution_flags_to_provider_metadata() -> None:
    source = (ROOT / "scripts" / "validation" / "run_i16.py").read_text(encoding="utf-8")
    assert "experimental=bool(args.experimental)" in source
    assert "non_official=bool(args.non_official)" in source


def test_budget_precheck_rejects_consumed_active_attempt(tmp_path: Path) -> None:
    from decimal import Decimal

    from pd_agent.experimental import LunaEconomicState, LunaEconomicStateStore

    path = tmp_path / "economic.json"
    state = LunaEconomicState(
        execution_id="precheck",
        global_ceiling_usd=Decimal("0.30"),
        active_attempt_id="previous",
        attempt_accumulated_usd=Decimal("0.0629950500"),
    )
    LunaEconomicStateStore(state, path=path).persist()

    try:
        driver.validate_budget(path, "0.30")
    except driver.PrecheckError as error:
        assert str(error) == "shared I16 budget has an active consumed attempt"
    else:
        raise AssertionError("precheck must reject a consumed active attempt")


@pytest.mark.parametrize("ceiling", ["0.30", "0.35"])
def test_budget_precheck_accepts_explicit_supported_ceiling(tmp_path: Path, ceiling: str) -> None:
    from pd_agent.experimental import LunaEconomicState, LunaEconomicStateStore

    path = tmp_path / "economic.json"
    state = LunaEconomicState(execution_id="precheck", global_ceiling_usd=Decimal(ceiling))
    LunaEconomicStateStore(state, path=path).persist()

    result = driver.validate_budget(path, ceiling)

    assert result["global_ceiling_usd"] == ceiling


@pytest.mark.parametrize(
    ("ledger_ceiling", "expected_ceiling"),
    [("0.35", "0.30"), ("0.30", "0.35")],
)
def test_budget_precheck_rejects_ceiling_mismatch(
    tmp_path: Path, ledger_ceiling: str, expected_ceiling: str
) -> None:
    from pd_agent.experimental import LunaEconomicState, LunaEconomicStateStore

    path = tmp_path / "economic.json"
    state = LunaEconomicState(execution_id="precheck", global_ceiling_usd=Decimal(ledger_ceiling))
    LunaEconomicStateStore(state, path=path).persist()

    with pytest.raises(ValueError, match="shared economic ceiling mismatch"):
        driver.validate_budget(path, expected_ceiling)


@pytest.mark.parametrize("value", ["not-a-decimal", "0", "-0.01", "NaN"])
def test_global_budget_ceiling_parser_fails_closed(value: str) -> None:
    with pytest.raises(Exception):
        driver._parse_global_budget_ceiling(value)


def test_precheck_and_live_parse_the_same_explicit_ceiling() -> None:
    args = driver.parse_args(
        [
            "--mode",
            "precheck",
            "--seed-root",
            "s",
            "--seed-manifest",
            "m",
            "--knowledge-pack",
            "p",
            "--budget-state",
            "b",
            "--gradle-home",
            "g",
            "--launch-root",
            "l",
            "--global-budget-ceiling",
            "0.35",
        ]
    )
    source = (ROOT / "scripts" / "validation" / "run_i16.py").read_text(encoding="utf-8")

    assert args.global_budget_ceiling == Decimal("0.35")
    assert "validate_budget(Path(args.budget_state).resolve(), args.global_budget_ceiling)" in source
    assert "expected_global_ceiling=args.global_budget_ceiling" in source


def _f6_t3() -> dict[str, object]:
    return json.loads((ROOT / "benchmarks/tasks/F6-T3-v5.json").read_text(encoding="utf-8"))


def test_i16_resolves_f6_t3_resource_targets_to_workspace_paths() -> None:
    task = _f6_t3()
    info = driver.validate_task(task, ROOT / "benchmarks/projects/v0_5_fabric_base")

    assert info["targets"] == (
        "role:source",
        "src/main/resources/assets/examplemod/lang/en_us.json",
        "src/main/resources/data/examplemod/recipe/server_core.json",
    )
    contract = driver.build_contract(task, ROOT / "benchmarks/projects/v0_5_fabric_base")
    assert [item.path for item in contract.mutation_expectations] == [
        "src/main/java",
        "src/main/resources/assets/examplemod/lang/en_us.json",
        "src/main/resources/data/examplemod/recipe/server_core.json",
    ]


def test_i16_prebuild_rejects_incomplete_lang_and_accepts_complete_lang(tmp_path: Path) -> None:
    from pd_agent.core import ValidationStatus
    from pd_agent.validation import PreBuildWorkspaceValidator

    root = tmp_path / "workspace"
    resource_root = root / "src/main/resources"
    lang = resource_root / "assets/examplemod/lang/en_us.json"
    recipe = resource_root / "data/examplemod/recipe/server_core.json"
    lang.parent.mkdir(parents=True)
    recipe.parent.mkdir(parents=True)
    lang.write_text('{"block.examplemod.server_core": "Server Core"}\n', encoding="utf-8")
    recipe.write_text(
        json.dumps({
            "type": "minecraft:crafting_shaped",
            "pattern": ["III", "ICI", "III"],
            "key": {"I": {"item": "minecraft:iron_ingot"}, "C": {"item": "minecraft:crafting_table"}},
            "result": {"id": "examplemod:server_core", "count": 1},
        }) + "\n",
        encoding="utf-8",
    )

    spec = _f6_t3()["acceptance"]["spec"]
    validator = PreBuildWorkspaceValidator(resource_roots=(resource_root,))
    incomplete = validator.validate(root, spec)
    assert incomplete.status is ValidationStatus.REPAIRABLE_FAIL
    assert any(item.requirement.endswith("/item.examplemod.server_core") for item in incomplete.violations)

    lang.write_text(
        '{"block.examplemod.server_core": "Server Core", "item.examplemod.server_core": "Server Core"}\n',
        encoding="utf-8",
    )
    complete = validator.validate(root, spec)
    assert complete.status is ValidationStatus.PASS
