"""Validated, declarative Fabric project templates."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping


TEMPLATE_SCHEMA_VERSION = 1
_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN = re.compile(r"(?i)(?:api[_ -]?key|secret|password|token|bearer|command|executable|process|shell|script|credential)")


class FabricProjectTemplateError(ValueError):
    """Raised when declarative template data is invalid."""


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FabricProjectTemplateError(f"{field_name} must be a bounded identifier")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or _FORBIDDEN.search(value):
        raise FabricProjectTemplateError(f"{field_name} is invalid")
    return value.strip()


@dataclass(frozen=True, slots=True)
class FabricProjectTemplate:
    """Data-only template compatibility declaration."""

    template_id: str
    template_revision: str
    platform_ids: tuple[str, ...]
    schema_version: int = TEMPLATE_SCHEMA_VERSION
    seed_identity: str | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != TEMPLATE_SCHEMA_VERSION:
            raise FabricProjectTemplateError("unsupported template schema version")
        object.__setattr__(self, "template_id", _identifier(self.template_id, "template_id"))
        object.__setattr__(self, "template_revision", _text(self.template_revision, "template_revision"))
        platforms = tuple(_identifier(value, "platform_id") for value in self.platform_ids)
        if not platforms:
            raise FabricProjectTemplateError("platform_ids must not be empty")
        if len(set(platforms)) != len(platforms):
            raise FabricProjectTemplateError("duplicate platform IDs")
        object.__setattr__(self, "platform_ids", platforms)
        if self.seed_identity is not None and not isinstance(self.seed_identity, str):
            raise FabricProjectTemplateError("seed_identity must be a SHA-256 string")
        if self.seed_identity is not None and not _SHA256.fullmatch(self.seed_identity):
            raise FabricProjectTemplateError("seed_identity must be a SHA-256 string")
        evidence = tuple(_text(value, "evidence") for value in self.evidence)
        if any(value.startswith(("/", "\\")) or "://" in value or ":\\" in value for value in evidence):
            raise FabricProjectTemplateError("evidence must use relative declarative references")
        if len(set(evidence)) != len(evidence):
            raise FabricProjectTemplateError("duplicate evidence")
        object.__setattr__(self, "evidence", tuple(sorted(evidence)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "template_id": self.template_id,
            "template_revision": self.template_revision,
            "platform_ids": list(self.platform_ids),
            "seed_identity": self.seed_identity,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FabricProjectTemplate":
        allowed = {"schema_version", "template_id", "template_revision", "platform_ids", "seed_identity", "evidence"}
        if not isinstance(data, Mapping) or set(data) - allowed:
            raise FabricProjectTemplateError("invalid template fields")
        return cls(
            schema_version=data.get("schema_version", TEMPLATE_SCHEMA_VERSION),
            template_id=data.get("template_id"),
            template_revision=data.get("template_revision"),
            platform_ids=tuple(data.get("platform_ids", ())),
            seed_identity=data.get("seed_identity"),
            evidence=tuple(data.get("evidence", ())),
        )


def load_project_templates(path: Path) -> tuple[FabricProjectTemplate, ...]:
    """Load source-controlled templates without network or executable data."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FabricProjectTemplateError("template document is unreadable or malformed") from exc
    if not isinstance(data, Mapping) or data.get("schema_version") != TEMPLATE_SCHEMA_VERSION or not isinstance(data.get("templates"), list):
        raise FabricProjectTemplateError("invalid template document schema")
    try:
        templates = tuple(FabricProjectTemplate.from_dict(item) for item in data["templates"])
    except (TypeError, KeyError) as exc:
        raise FabricProjectTemplateError("invalid template declaration") from exc
    if len({item.template_id for item in templates}) != len(templates):
        raise FabricProjectTemplateError("duplicate template IDs")
    return tuple(sorted(templates, key=lambda item: item.template_id))


__all__ = [
    "FabricProjectTemplate",
    "FabricProjectTemplateError",
    "TEMPLATE_SCHEMA_VERSION",
    "load_project_templates",
]
