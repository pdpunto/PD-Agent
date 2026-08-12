from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.benchmark import BenchmarkConfig
from pd_agent.core import ExecutionLimits


def _load_runner():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "benchmark" / "run_v0_4.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _config(*, config_id: str, brain_enabled: bool) -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id=config_id,
        provider="gemini",
        model="gemini-3.1-flash-lite",
        brain_enabled=brain_enabled,
        model_config={"temperature": 0.2, "top_p": 0.95},
        provider_config={"timeout_seconds": 60, "provider_retry_limit": 2},
        execution_limits=ExecutionLimits(max_agent_steps=25, max_tool_calls=50),
        knowledge_config={"offline": False},
        target_repetition_count=3,
        notes=("benchmark",),
    )


def _write_configs(path: Path, *configs: BenchmarkConfig) -> None:
    path.write_text(json.dumps([config.to_dict() for config in configs], ensure_ascii=False, indent=2), encoding="utf-8")


def test_validate_configs_accepts_brain_off_and_on_variants() -> None:
    runner = _load_runner()
    off = _config(config_id="cfg-off", brain_enabled=False)
    on = _config(config_id="cfg-on", brain_enabled=True)

    canonical = runner._validate_configs((off, on))

    assert canonical == off
    assert runner._build_knowledge_source((off,)) is None
    assert runner._build_knowledge_source((off, on)) is not None


def test_validate_configs_rejects_mixed_provider_settings() -> None:
    runner = _load_runner()
    off = _config(config_id="cfg-off", brain_enabled=False)
    mixed = BenchmarkConfig(
        config_id="cfg-other",
        provider="openai",
        model="gpt-test",
        brain_enabled=True,
        model_config=off.model_config,
        provider_config=off.provider_config,
        execution_limits=off.execution_limits,
        knowledge_config=off.knowledge_config,
        target_repetition_count=off.target_repetition_count,
    )

    with pytest.raises(ValueError, match="same provider"):
        runner._validate_configs((off, mixed))


def test_main_wires_real_brain_source_for_brain_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _load_runner()
    off = _config(config_id="cfg-off", brain_enabled=False)
    on = _config(config_id="cfg-on", brain_enabled=True)
    configs_json = tmp_path / "configs.json"
    _write_configs(configs_json, off, on)

    catalog = SimpleNamespace(
        dataset_for=lambda dataset_id, dataset_version: SimpleNamespace(dataset_id=dataset_id, dataset_version=dataset_version),
        task_for=lambda task_id, task_version: SimpleNamespace(task_id=task_id, task_version=task_version),
    )

    class FakeExecutor:
        last_init: dict[str, object] = {}

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = dict(kwargs)
            FakeExecutor.last_init = self.kwargs

    class FakeRunner:
        last_init: dict[str, object] = {}
        last_run: dict[str, object] = {}

        def __init__(self, **kwargs: object) -> None:
            self.kwargs = dict(kwargs)
            FakeRunner.last_init = self.kwargs

        def run(self, catalog_arg, *, dataset_id: str, dataset_version: str, configs, execution_root: Path, pd_agent_commit=None):  # noqa: ANN001
            FakeRunner.last_run = {
                "catalog": catalog_arg,
                "dataset_id": dataset_id,
                "dataset_version": dataset_version,
                "configs": tuple(configs),
                "execution_root": execution_root,
                "pd_agent_commit": pd_agent_commit,
            }
            return SimpleNamespace(comparison_json_path=execution_root / "comparison.json")

    monkeypatch.setattr(runner, "BenchmarkCatalog", SimpleNamespace(load=lambda path: catalog))
    monkeypatch.setattr(runner, "BenchmarkExecutor", FakeExecutor)
    monkeypatch.setattr(runner, "BenchmarkExecutionRunner", FakeRunner)
    monkeypatch.setattr(runner, "_build_provider", lambda config: "provider")
    monkeypatch.setattr(runner, "_wrap_provider_for_benchmark", lambda provider, pacer: provider)

    code = runner.main(
        [
            "--catalog-root",
            str(tmp_path / "catalog"),
            "--dataset-id",
            "pd-agent-fabric-brain",
            "--dataset-version",
            "0.4.1",
            "--configs-json",
            str(configs_json),
            "--execution-root",
            str(tmp_path / "executions"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "comparison.json" in captured.out
    assert FakeExecutor.last_init["knowledge_source"] is not None
    assert "context_manager_factory" not in FakeExecutor.last_init
    assert len(FakeRunner.last_run["configs"]) == 2
    assert FakeRunner.last_run["configs"][0].brain_enabled is False
    assert FakeRunner.last_run["configs"][1].brain_enabled is True
