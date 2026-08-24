from __future__ import annotations

import argparse
import inspect
import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.benchmark.run_luna_experimental import (
    _load_one_config,
    _positive_budget,
    build_parser,
    initialize_experimental_roots,
    validate_experimental_prelaunch_paths,
)
from pd_agent.benchmark import BenchmarkGradleEnvironment
from pd_agent.providers import OpenAIProvider


def _config_payload() -> list[dict]:
    return [
        {
            "schema_version": 1,
            "config_id": "luna-experimental-test",
            "provider": "openai",
            "model": "gpt-5.6-luna",
            "brain_enabled": True,
            "model_config": {"reasoning": {"effort": "medium"}},
            "provider_config": {"provider_retry_limit": 2, "timeout_seconds": 60},
            "execution_limits": {
                "max_agent_steps": 25,
                "max_tool_calls": 50,
                "max_build_attempts": 5,
                "max_context_bytes": 2_000_000,
                "max_tool_output_bytes": 1_000_000,
                "process_timeout_seconds": 600,
                "provider_retry_limit": 2,
            },
            "knowledge_config": {"offline": False},
            "target_repetition_count": 1,
        }
    ]


def test_new_launch_root_creates_execution_dir_before_gradle(tmp_path: Path) -> None:
    launch_root = tmp_path / "new-launch"
    execution_id, execution_root = initialize_experimental_roots(launch_root)

    assert launch_root.is_dir()
    assert execution_root.is_dir()
    assert execution_root.parent == launch_root / "ExecutionRoot"
    assert execution_root.name == execution_id


def test_gradle_prepare_precondition_is_satisfied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _execution_id, execution_root = initialize_experimental_roots(tmp_path / "launch")
    observed: dict[str, Path] = {}

    def fake_prepare(*, seed_root, execution_root, seed_manifest_path, offline):  # noqa: ANN001
        observed["execution_root"] = Path(execution_root)
        assert observed["execution_root"].is_dir()
        assert offline is True
        return object()

    monkeypatch.setattr(BenchmarkGradleEnvironment, "prepare", fake_prepare)
    BenchmarkGradleEnvironment.prepare(
        seed_root=tmp_path / "seed",
        execution_root=execution_root,
        seed_manifest_path=tmp_path / "seed-manifest.json",
        offline=True,
    )
    assert observed["execution_root"] == execution_root


def test_existing_launch_root_is_rejected(tmp_path: Path) -> None:
    launch_root = tmp_path / "existing-launch"
    launch_root.mkdir()

    with pytest.raises(ValueError, match="new and unused"):
        initialize_experimental_roots(launch_root)


def test_preflight_keeps_launch_root_absent_with_external_config(tmp_path: Path) -> None:
    launch_root = tmp_path / "future-launch"
    config_path = tmp_path / "staging" / "runtime-configs.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(_config_payload()), encoding="utf-8")

    validated_launch, validated_config = validate_experimental_prelaunch_paths(launch_root, config_path)

    assert validated_launch == launch_root.resolve()
    assert validated_config == config_path.resolve()
    assert not launch_root.exists()
    assert _load_one_config(validated_config).model == "gpt-5.6-luna"


def test_preflight_rejects_config_inside_future_launch_root(tmp_path: Path) -> None:
    launch_root = tmp_path / "future-launch"
    config_path = launch_root / "runtime-configs.json"
    with pytest.raises(ValueError, match="staged outside"):
        validate_experimental_prelaunch_paths(launch_root, config_path)


def test_preflight_rejects_missing_external_config(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="runtime config does not exist"):
        validate_experimental_prelaunch_paths(tmp_path / "future-launch", tmp_path / "missing.json")


def test_existing_nonempty_launch_root_is_rejected(tmp_path: Path) -> None:
    launch_root = tmp_path / "existing-launch"
    launch_root.mkdir()
    (launch_root / "stale.txt").write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="new and unused"):
        validate_experimental_prelaunch_paths(launch_root, tmp_path / "runtime-configs.json")


def test_config_list_with_one_element_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "configs.json"
    path.write_text(json.dumps(_config_payload()), encoding="utf-8")

    assert _load_one_config(path).model == "gpt-5.6-luna"


def test_config_object_root_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "configs.json"
    path.write_text(json.dumps(_config_payload()[0]), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one config"):
        _load_one_config(path)


def test_runner_has_budget_guard_injection_seam_without_network() -> None:
    assert "budget_guard" in inspect.signature(OpenAIProvider.__init__).parameters
    assert "LunaBudgetGuard" in Path("scripts/benchmark/run_luna_experimental.py").read_text(encoding="utf-8")


def test_runner_does_not_reference_f9_scheduler_or_execution_dir() -> None:
    source = Path("scripts/benchmark/run_luna_experimental.py").read_text(encoding="utf-8")
    assert "BenchmarkExecutionRunner" not in source
    assert "RATE_LIMIT_PAUSED" not in source


def test_cli_accepts_configurable_budget() -> None:
    args = build_parser().parse_args([
        "--catalog-root", "benchmarks",
        "--configs-json", "configs.json",
        "--launch-root", "launch",
        "--gradle-seed-root", "seed",
        "--gradle-seed-manifest", "seed.json",
        "--pd-agent-commit", "commit",
        "--hard-budget-usd", "0.25",
    ])

    assert args.hard_budget_usd == Decimal("0.25")


@pytest.mark.parametrize("value", ["0", "-0.25", "NaN", "Infinity", "-Infinity", "not-money"])
def test_cli_rejects_invalid_budget(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_budget(value)
