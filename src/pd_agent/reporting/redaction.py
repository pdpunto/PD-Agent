"""Basic secret redaction for reporting artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from collections.abc import Sequence


REDACTION_TOKEN = "[REDACTED]"


def json_ready(value: Any) -> Any:
    """Convert common Python types into JSON-friendly values."""

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return json_ready(value.to_dict())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, set):
        return [json_ready(item) for item in sorted(value, key=repr)]
    return value


@dataclass(frozen=True, slots=True)
class Redactor:
    """Redact configured secrets from nested data or plain text."""

    secrets: tuple[str, ...] = ()
    replacement: str = REDACTION_TOKEN

    def redact_text(self, text: str) -> str:
        redacted = text
        for secret in self._unique_secrets():
            if secret:
                redacted = redacted.replace(secret, self.replacement)
        return redacted

    def redact_data(self, value: Any) -> Any:
        return self._redact_value(json_ready(value))

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {
                self._redact_value(key): self._redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._redact_value(item) for item in value]
        return value

    def _unique_secrets(self) -> tuple[str, ...]:
        seen: set[str] = set()
        unique: list[str] = []
        for secret in self.secrets:
            if secret and secret not in seen:
                seen.add(secret)
                unique.append(secret)
        return tuple(unique)
