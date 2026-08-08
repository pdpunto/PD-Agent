"""Base logging helpers for PD Agent foundation."""

from __future__ import annotations

import logging


def configure_logging(level: str | int = "INFO") -> logging.Logger:
    """Configure a small, predictable logging setup."""

    if isinstance(level, str):
        level_value = getattr(logging, level.upper(), logging.INFO)
    else:
        level_value = level

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level_value,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    else:
        logging.getLogger().setLevel(level_value)

    logger = logging.getLogger("pd_agent")
    logger.setLevel(level_value)
    return logger

