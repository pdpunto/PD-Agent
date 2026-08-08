"""Execution context for tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pd_agent.core import ExecutionLimits


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Minimal context shared by tools."""

    project_root: Path
    limits: ExecutionLimits
    run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", self.project_root.resolve(strict=True))

