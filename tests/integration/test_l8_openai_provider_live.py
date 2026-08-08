from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)


def test_live_openai_adapter_opt_in() -> None:
    """Placeholder opt-in live test."""

    assert True
