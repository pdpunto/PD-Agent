"""Minecraft test harness errors."""

from __future__ import annotations

from pd_agent.core.errors import PDAgentError


class MinecraftTestError(PDAgentError):
    """Base error for Minecraft test harness contracts."""


class MinecraftTestValidationError(MinecraftTestError):
    """Invalid Minecraft test spec, target or contract."""


class UnsupportedMinecraftEnvironmentError(MinecraftTestError):
    """Requested Minecraft execution environment is not supported."""
