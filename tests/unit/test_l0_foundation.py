from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from pd_agent import AppConfig, __version__, load_config
from pd_agent.cli import build_parser, main


ROOT = Path(__file__).resolve().parents[2]


def test_package_imports() -> None:
    assert __version__ == "0.1.0"
    assert AppConfig().project_name == "PD Agent"
    assert AppConfig().provider == "openai"
    assert AppConfig().model is None
    assert AppConfig().openai_api_key is None
    assert AppConfig().execution_limits.max_build_attempts == 5
    assert callable(main)
    assert callable(build_parser)


def test_config_load_defaults_and_env() -> None:
    default_config = load_config({})
    assert default_config.log_level == "INFO"
    assert default_config.runs_dir == Path("runs")

    custom_config = load_config(
        {
            "PD_AGENT_PROVIDER": "openai",
            "PD_AGENT_MODEL": "gpt-test",
            "OPENAI_API_KEY": "sk-test",
            "PD_AGENT_LOG_LEVEL": "debug",
            "PD_AGENT_RUNS_DIR": "custom-runs",
            "PD_AGENT_MAX_BUILD_ATTEMPTS": "7",
        }
    )
    assert custom_config.provider == "openai"
    assert custom_config.model == "gpt-test"
    assert custom_config.openai_api_key == "sk-test"
    assert custom_config.log_level == "DEBUG"
    assert custom_config.runs_dir == Path("custom-runs")
    assert custom_config.execution_limits.max_build_attempts == 7


def test_cli_help_prints_usage() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pd_agent", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert result.stderr == ""


def test_real_pytest_runs_passing_temp_suite() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        empty_root = Path(temp_dir)
        test_file = empty_root / "test_sample.py"
        test_file.write_text(
            "def test_sample():\n    assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(empty_root)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0
    assert "1 passed" in result.stdout.lower()
    assert result.stderr == ""
