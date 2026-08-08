"""Typed configuration for PD Agent foundation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Minimal typed application config."""

    project_name: str = "PD Agent"
    version: str = "0.1.0"
    log_level: str = "INFO"
    runs_dir: Path = Path("runs")

    def __post_init__(self) -> None:
        normalized = self.log_level.upper()
        if normalized not in VALID_LOG_LEVELS:
            raise ValueError(f"Unsupported log level: {self.log_level}")
        object.__setattr__(self, "log_level", normalized)


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Load config from environment-like mapping."""

    source = env or {}
    runs_dir = Path(source.get("PD_AGENT_RUNS_DIR", "runs"))
    log_level = source.get("PD_AGENT_LOG_LEVEL", "INFO")
    return AppConfig(log_level=log_level, runs_dir=runs_dir)

