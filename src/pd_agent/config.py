"""Typed configuration for PD Agent foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .core import ExecutionLimits


VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Minimal typed application config."""

    project_name: str = "PD Agent"
    version: str = "0.1.0"
    provider: str = "openai"
    model: str | None = None
    openai_api_key: str | None = None
    log_level: str = "INFO"
    runs_dir: Path = Path("runs")
    execution_limits: ExecutionLimits = field(default_factory=ExecutionLimits)

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        if not provider:
            raise ValueError("provider cannot be empty")
        object.__setattr__(self, "provider", provider)
        normalized = self.log_level.upper()
        if normalized not in VALID_LOG_LEVELS:
            raise ValueError(f"Unsupported log level: {self.log_level}")
        object.__setattr__(self, "log_level", normalized)


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Load config from environment-like mapping."""

    source = env or {}
    provider = source.get("PD_AGENT_PROVIDER", "openai")
    model = source.get("PD_AGENT_MODEL")
    api_key = source.get("OPENAI_API_KEY")
    runs_dir = Path(source.get("PD_AGENT_RUNS_DIR", "runs"))
    log_level = source.get("PD_AGENT_LOG_LEVEL", "INFO")
    execution_limits = ExecutionLimits.from_dict(
        {
            "max_agent_steps": int(source.get("PD_AGENT_MAX_AGENT_STEPS", 40)),
            "max_tool_calls": int(source.get("PD_AGENT_MAX_TOOL_CALLS", 120)),
            "max_build_attempts": int(source.get("PD_AGENT_MAX_BUILD_ATTEMPTS", 5)),
            "provider_retry_limit": int(source.get("PD_AGENT_PROVIDER_RETRY_LIMIT", 2)),
            "process_timeout_seconds": int(source.get("PD_AGENT_PROCESS_TIMEOUT_SECONDS", 600)),
            "max_tool_output_bytes": int(source.get("PD_AGENT_MAX_TOOL_OUTPUT_BYTES", 1_000_000)),
            "max_context_bytes": int(source.get("PD_AGENT_MAX_CONTEXT_BYTES", 2_000_000)),
        }
    )
    return AppConfig(
        provider=provider,
        model=model,
        openai_api_key=api_key,
        log_level=log_level,
        runs_dir=runs_dir,
        execution_limits=execution_limits,
    )
