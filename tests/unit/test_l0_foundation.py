from __future__ import annotations

from decimal import Decimal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from pd_agent import AppConfig, __version__, load_config
from pd_agent.bootstrap import build_runtime_bundle, create_provider
from pd_agent.core import ProviderContinuation
from pd_agent.core.errors import ConfigurationError
from pd_agent.reporting import RunStorage
from pd_agent.cli import build_parser, main
from pd_agent.providers import GeminiProvider, OpenAIProvider
from pd_agent.experimental import LunaBudgetGuard


ROOT = Path(__file__).resolve().parents[2]


def _luna_config() -> AppConfig:
    return AppConfig(
        provider="openai",
        model="gpt-5.6-luna",
        openai_api_key="sk-offline-test",
    )


def test_productive_runtime_injects_explicit_luna_budget_guard(tmp_path: Path) -> None:
    bundle = build_runtime_bundle(_luna_config(), storage=RunStorage(tmp_path), economic_budget_usd="0.50")
    assert isinstance(bundle.provider, OpenAIProvider)
    assert isinstance(bundle.provider.budget_guard, LunaBudgetGuard)
    assert bundle.provider.budget_guard.hard_budget_usd == Decimal("0.50")


@pytest.mark.parametrize("budget", ["0", "-0.01", "not-a-budget"])
def test_productive_budget_rejects_invalid_explicit_ceiling(tmp_path: Path, budget: str) -> None:
    with pytest.raises(ConfigurationError):
        build_runtime_bundle(_luna_config(), storage=RunStorage(tmp_path), economic_budget_usd=budget)


def test_productive_budget_rejects_unsupported_provider_pricing(tmp_path: Path) -> None:
    config = AppConfig(provider="gemini", model="gemini-test", gemini_api_key="gm-offline-test")
    with pytest.raises(ConfigurationError):
        build_runtime_bundle(config, storage=RunStorage(tmp_path), economic_budget_usd="0.50")


def test_package_imports() -> None:
    assert __version__ == "0.1.0"
    assert AppConfig().project_name == "PD Agent"
    assert AppConfig().provider == "openai"
    assert AppConfig().model is None
    assert AppConfig().openai_api_key is None
    assert AppConfig().gemini_api_key is None
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
            "GEMINI_API_KEY": "gm-test",
            "PD_AGENT_LOG_LEVEL": "debug",
            "PD_AGENT_RUNS_DIR": "custom-runs",
            "PD_AGENT_MAX_BUILD_ATTEMPTS": "7",
        }
    )
    assert custom_config.provider == "openai"
    assert custom_config.model == "gpt-test"
    assert custom_config.openai_api_key == "sk-test"
    assert custom_config.gemini_api_key == "gm-test"
    assert custom_config.log_level == "DEBUG"
    assert custom_config.runs_dir == Path("custom-runs")
    assert custom_config.execution_limits.max_build_attempts == 7


def test_config_loads_real_environment_when_env_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PD_AGENT_PROVIDER", "openai")
    monkeypatch.setenv("PD_AGENT_MODEL", "gpt-env")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-env")
    monkeypatch.setenv("PD_AGENT_LOG_LEVEL", "debug")
    monkeypatch.setenv("PD_AGENT_RUNS_DIR", "env-runs")
    monkeypatch.setenv("PD_AGENT_MAX_AGENT_STEPS", "41")
    monkeypatch.setenv("PD_AGENT_MAX_TOOL_CALLS", "121")
    monkeypatch.setenv("PD_AGENT_MAX_BUILD_ATTEMPTS", "6")
    monkeypatch.setenv("PD_AGENT_PROVIDER_RETRY_LIMIT", "3")
    monkeypatch.setenv("PD_AGENT_PROCESS_TIMEOUT_SECONDS", "601")
    monkeypatch.setenv("PD_AGENT_MAX_TOOL_OUTPUT_BYTES", "1001")
    monkeypatch.setenv("PD_AGENT_MAX_CONTEXT_BYTES", "2001")

    config = load_config()

    assert config.provider == "openai"
    assert config.model == "gpt-env"
    assert config.openai_api_key == "sk-env"
    assert config.gemini_api_key == "gm-env"
    assert config.log_level == "DEBUG"
    assert config.runs_dir == Path("env-runs")
    assert config.execution_limits.max_agent_steps == 41
    assert config.execution_limits.max_tool_calls == 121
    assert config.execution_limits.max_build_attempts == 6
    assert config.execution_limits.provider_retry_limit == 3
    assert config.execution_limits.process_timeout_seconds == 601
    assert config.execution_limits.max_tool_output_bytes == 1001
    assert config.execution_limits.max_context_bytes == 2001


def test_config_empty_mapping_stays_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PD_AGENT_PROVIDER", "openai")
    monkeypatch.setenv("PD_AGENT_MODEL", "gpt-env")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-env")

    config = load_config({})

    assert config.provider == "openai"
    assert config.model is None
    assert config.openai_api_key is None
    assert config.gemini_api_key is None


def test_bootstrap_selects_provider_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pd_agent.providers.gemini_provider.GeminiProvider._build_client", lambda self: object())

    openai_provider = create_provider(AppConfig(provider="openai", model="gpt-test", openai_api_key="sk-openai"))
    gemini_provider = create_provider(AppConfig(provider="gemini", model="gemini-test", gemini_api_key="gm-test"))

    assert isinstance(openai_provider, OpenAIProvider)
    assert isinstance(gemini_provider, GeminiProvider)

    with pytest.raises(ConfigurationError):
        create_provider(AppConfig(provider="other", model="gpt-test"))


def test_bootstrap_validates_gemini_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pd_agent.providers.gemini_provider.GeminiProvider._build_client", lambda self: object())

    with pytest.raises(ConfigurationError, match="Gemini model is required"):
        create_provider(AppConfig(provider="gemini", gemini_api_key="gm-test"))

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is required"):
        create_provider(AppConfig(provider="gemini", model="gemini-test"))


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


def test_cli_reads_environment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    from pd_agent.bootstrap import RuntimeBundle
    from pd_agent.core import ArtifactResult, BuildResult, RunState, RunStatus
    from pd_agent.reporting import FinalReport, RunEvent, RunEventType, RunStorage
    from pd_agent.artifacts import ArtifactValidator
    from pd_agent.build import GradleBuildRunner
    from pd_agent.context import ContextManager
    from pd_agent.runtime import RunController
    from pd_agent.tools import ToolExecutor, create_filesystem_tools

    project_root = ROOT / "tests" / "fixtures" / "l11_fabric_fixture"
    runs_root = Path(tempfile.mkdtemp())
    secret = "sk-test-pd-agent-v011-redaction"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("PD_AGENT_MODEL", "gpt-env-cli")

    captured = {}

    def runtime_factory(config: AppConfig) -> RuntimeBundle:
        captured["config"] = config
        storage = RunStorage(runs_root, secrets=(config.openai_api_key,) if config.openai_api_key else ())
        run_id = "11111111-1111-4111-8111-111111111111"
        started_at = RunState().started_at
        build = BuildResult(
            attempt=1,
            command_display="gradlew build",
            cwd=project_root,
            started_at=started_at,
            duration_seconds=1.0,
            exit_code=0,
            stdout_log="BUILD SUCCESSFUL",
            stderr_log="",
        )
        artifact = ArtifactResult(
            path=project_root / "build" / "libs" / "fixture.jar",
            size=123,
            timestamp=started_at,
            classification="VALID",
            metadata={"valid": True},
        )
        run_state = RunState(
            run_id=run_id,
            project_root=project_root,
            task="repair",
            state=RunStatus.COMPLETED,
            build_results=(build,),
            build_attempt_count=1,
            artifact_result=artifact,
            termination_reason="completed",
        )
        report = FinalReport(
            run_id=run_id,
            final_state=RunStatus.COMPLETED,
            summary=f"summary {secret}",
            project=str(project_root),
            requested_task="repair",
            build_attempts=(build,),
            final_build=build,
            artifact=artifact,
            termination_reason=f"reason {secret}",
        )
        storage.write_run_state(run_state)
        storage.write_final_report(report)
        storage.event_writer(run_id).append(
            RunEvent(run_id=run_id, event_type=RunEventType.RUN_STARTED, payload={"secret": secret})
        )

        class _Controller:
            def run(self, project_root: Path, task: str):
                return run_state, report

        return RuntimeBundle(config=config, storage=storage, controller=_Controller(), provider=object())

    code = main(
        [
            "run",
            "--project",
            str(project_root),
            "--task",
            "repair",
            "--model",
            "gpt-cli",
        ],
        runtime_factory=runtime_factory,
    )

    assert code == 0
    assert captured["config"].openai_api_key == secret
    assert captured["config"].model == "gpt-cli"
    run_dir = runs_root / "11111111-1111-4111-8111-111111111111"
    for path in (
        run_dir / "run.json",
        run_dir / "events.jsonl",
        run_dir / "final-report.json",
        run_dir / "final-report.md",
    ):
        assert secret not in path.read_text(encoding="utf-8")


def test_bootstrap_preserves_injected_storage_and_adds_secret_redaction() -> None:
    openai_secret = "sk-test-pd-agent-v011-redaction"
    gemini_secret = "gm-test-pd-agent-v011-redaction"
    with tempfile.TemporaryDirectory() as temp_dir:
        injected_storage = RunStorage(Path(temp_dir))

        bundle = build_runtime_bundle(
            AppConfig(
                model="gpt-test",
                openai_api_key=openai_secret,
                gemini_api_key=gemini_secret,
            ),
            provider_factory=lambda config: object(),
            storage=injected_storage,
            controller_factory=lambda **kwargs: type(
                "Controller",
                (),
                {"run": lambda self, project_root, task: None},
            )(),
        )

        assert bundle.storage is injected_storage
        assert openai_secret in bundle.storage.redactor.secrets
        assert gemini_secret in bundle.storage.redactor.secrets


def test_source_tree_keeps_google_genai_outside_gemini_provider() -> None:
    src_root = ROOT / "src" / "pd_agent"
    files = [path for path in src_root.rglob("*.py") if path.name != "gemini_provider.py"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "google.genai" not in text
        assert "from google import genai" not in text
        assert "import google.genai" not in text


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


def test_provider_continuation_round_trip() -> None:
    item = ProviderContinuation(
        provider="gemini",
        kind="thought_signature",
        target_type="function_call",
        target_id="call_1",
        position=0,
        payload={"thought_signature_b64": "YWJj"},
    )

    data = item.to_dict()
    rebuilt = ProviderContinuation.from_dict(data)

    assert data["provider"] == "gemini"
    assert data["payload"] == {"thought_signature_b64": "YWJj"}
    assert rebuilt == item
