"""Repository shim so `python -m pd_agent` works before installation."""

from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parent
_SRC_PACKAGE = _ROOT.parent / "src" / "pd_agent"

__path__ = [str(_SRC_PACKAGE)]

__version__ = "0.1.0"

from .cli import main  # noqa: E402
from .config import AppConfig, load_config  # noqa: E402
from .logging import configure_logging  # noqa: E402

__all__ = ["__version__", "AppConfig", "configure_logging", "load_config", "main"]
