from __future__ import annotations

import importlib.util
from pathlib import Path


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


def test_live_requires_both_live_switch_and_authorization() -> None:
    args = driver.parse_args(["--mode", "live", "--seed-root", "s", "--seed-manifest", "m", "--knowledge-pack", "p", "--budget-state", "b", "--gradle-home", "g", "--launch-root", "l"])
    assert args.live is False
    assert args.authorize_i16 is False


def test_driver_does_not_own_benchmark_scheduler() -> None:
    source = (ROOT / "scripts" / "validation" / "run_i16.py").read_text(encoding="utf-8")
    assert "BenchmarkExecutor" not in source
    assert "BenchmarkFunctionalValidator" not in source
    assert "BenchmarkTask" not in source


def test_live_source_connects_shared_budget_guard_before_provider() -> None:
    source = (ROOT / "scripts" / "validation" / "run_i16.py").read_text(encoding="utf-8")
    assert "budget_session.guard(consumer_id=run_id)" in source
    assert "budget_guard=budget_guard" in source
