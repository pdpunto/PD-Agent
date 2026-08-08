"""PD Agent foundation package."""

from __future__ import annotations

__version__ = "0.1.0"

from .cli import main
from .config import AppConfig, load_config
from .logging import configure_logging
from .project import ProjectInspector, ProjectInspectionStatus, ProjectSnapshot

__all__ = [
    "__version__",
    "AppConfig",
    "ProjectInspector",
    "ProjectInspectionStatus",
    "ProjectSnapshot",
    "configure_logging",
    "load_config",
    "main",
]
