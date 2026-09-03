"""Small declarative M1 capability registry."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import Any

from .capabilities import CapabilityDefinition, CapabilityModelError


class DuplicateCapabilityError(CapabilityModelError):
    """Raised when a definition ID is registered more than once."""


class UnsupportedCapabilityError(CapabilityModelError):
    """Raised when a definition ID is not present in the registry."""


class CapabilityRegistry:
    """Deterministic data registry, frozen before it is used by a planner."""

    def __init__(self, definitions: Iterable[CapabilityDefinition] = ()) -> None:
        values: dict[str, CapabilityDefinition] = {}
        for definition in definitions:
            if definition.definition_id in values:
                raise DuplicateCapabilityError(f"duplicate capability definition: {definition.definition_id}")
            values[definition.definition_id] = definition
        self._definitions = values
        self._frozen = False

    def register(self, definition: CapabilityDefinition) -> "CapabilityRegistry":
        if self._frozen:
            raise CapabilityModelError("capability registry is frozen")
        if not isinstance(definition, CapabilityDefinition):
            raise CapabilityModelError("registry accepts CapabilityDefinition values only")
        if definition.definition_id in self._definitions:
            raise DuplicateCapabilityError(f"duplicate capability definition: {definition.definition_id}")
        self._definitions[definition.definition_id] = definition
        return self

    def freeze(self) -> "CapabilityRegistry":
        self._definitions = dict(self._definitions)
        self._frozen = True
        return self

    def get(self, definition_id: str) -> CapabilityDefinition:
        try:
            return self._definitions[definition_id]
        except KeyError as exc:
            raise UnsupportedCapabilityError(f"unsupported capability: {definition_id}") from exc

    lookup = get

    @property
    def definition_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._definitions[key] for key in self.definition_ids)

    def snapshot(self) -> MappingProxyType[str, CapabilityDefinition]:
        return MappingProxyType(dict(self._definitions))


def _definition(
    definition_id: str,
    *,
    parameter_schema: dict[str, Any],
    prerequisites: tuple[dict[str, Any], ...] = (),
    requirements: tuple[dict[str, Any], ...] = (),
    validations: tuple[dict[str, Any], ...] = (),
    mutation_expectations: tuple[dict[str, Any], ...] = (),
) -> CapabilityDefinition:
    return CapabilityDefinition(
        definition_id=definition_id,
        parameter_schema=parameter_schema,
        prerequisites=prerequisites,
        requirements=requirements,
        validations=validations,
        mutation_expectations=mutation_expectations,
    )


BLOCK_DEFINITION = _definition(
    "fabric.block",
    parameter_schema={"namespace": {"type": "string"}, "name": {"type": "string"}},
    requirements=({"key": "source", "description": "the block source declaration is present"},),
    validations=({"key": "build", "kind": "build", "requirement_keys": ("source",)},),
    mutation_expectations=({"key": "source", "role": "source"},),
)
BLOCK_ITEM_DEFINITION = _definition(
    "fabric.block_item",
    parameter_schema={"block_instance_id": {"type": "string"}, "namespace": {"type": "string"}},
    prerequisites=({"capability": "fabric.block", "reference": "block_instance_id"},),
    requirements=({"key": "source", "description": "the block item source declaration is present"},),
    validations=({"key": "artifact", "kind": "artifact", "requirement_keys": ("source",)},),
    mutation_expectations=({"key": "source", "role": "source"},),
)
RECIPE_DEFINITION = _definition(
    "fabric.recipe",
    parameter_schema={"output_instance_id": {"type": "string"}, "ingredients": {"type": "array"}},
    prerequisites=({"capability": "fabric.block_item", "reference": "output_instance_id"},),
    requirements=({"key": "source", "description": "the recipe source declaration is present"},),
    validations=({"key": "artifact", "kind": "artifact", "requirement_keys": ("source",)},),
    mutation_expectations=({"key": "source", "role": "resource"},),
)

FOUNDATION_DEFINITIONS = (BLOCK_DEFINITION, BLOCK_ITEM_DEFINITION, RECIPE_DEFINITION)


def foundation_capability_registry() -> CapabilityRegistry:
    """Return a fresh frozen registry containing only M1 foundation kinds."""
    return CapabilityRegistry(FOUNDATION_DEFINITIONS).freeze()


__all__ = [
    "BLOCK_DEFINITION",
    "BLOCK_ITEM_DEFINITION",
    "CapabilityRegistry",
    "DuplicateCapabilityError",
    "FOUNDATION_DEFINITIONS",
    "RECIPE_DEFINITION",
    "UnsupportedCapabilityError",
    "foundation_capability_registry",
]
