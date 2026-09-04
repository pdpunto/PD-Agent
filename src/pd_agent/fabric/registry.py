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
    parameter_schema={
        "namespace": {"type": "string", "format": "identifier"},
        "block_id": {"type": "string", "format": "identifier", "required": False},
        "name": {"type": "string", "format": "identifier", "required": False},
        "display_name": {"type": "string", "required": False},
        "runtime_spec": {"type": "object", "required": False},
    },
    requirements=(
        {"key": "source", "description": "a relevant source change is present for the block"},
        {"key": "block-registration", "description": "the block runtime declaration is present"},
    ),
    validations=(
        {"key": "build", "kind": "build", "requirement_keys": ("source",)},
        {"key": "runtime", "kind": "minecraft", "requirement_keys": ("block-registration",), "required_parameter": "runtime_spec", "spec": {"$parameter": "runtime_spec"}},
    ),
    mutation_expectations=({"key": "source", "role": "source"},),
)
BLOCK_ITEM_DEFINITION = _definition(
    "fabric.block_item",
    parameter_schema={
        "block_instance_id": {"type": "string"},
        "namespace": {"type": "string", "format": "identifier"},
        "item_id": {"type": "string", "format": "identifier", "required": False},
        "display_name": {"type": "string", "required": False},
        "artifact_spec": {"type": "object", "required": False},
        "mutation_paths": {"type": "array", "required": False},
    },
    prerequisites=({"capability": "fabric.block", "reference": "block_instance_id"},),
    requirements=(
        {"key": "item-source", "description": "the BlockItem source declaration is present"},
        {"key": "block-item-association", "description": "the BlockItem association is declared"},
        {"key": "artifact", "description": "the produced artifact contains the declared resources"},
    ),
    validations=(
        {
            "key": "artifact",
            "kind": "artifact",
            "requirement_keys": ("item-source", "block-item-association", "artifact"),
            "required_parameter": "artifact_spec",
            "spec": {"$parameter": "artifact_spec"},
        },
    ),
    mutation_expectations=({"key": "resource", "role": "resource", "paths_parameter": "mutation_paths"},),
)
BLOCK_ASSETS_DEFINITION = _definition(
    "fabric.block_assets",
    parameter_schema={
        "block_instance_id": {"type": "string"},
        "block_item_instance_id": {"type": "string"},
        "namespace": {"type": "string", "format": "identifier"},
        "block_id": {"type": "string", "format": "identifier"},
        "item_id": {"type": "string", "format": "identifier"},
        "display_name": {"type": "string", "required": False},
        "texture_strategy": {"type": "string", "enum": ("REUSE", "DERIVE", "GENERATE")},
        "texture_reference": {"type": "string", "required": False},
        "texture_path": {"type": "string", "required": False},
        "resource_paths": {"type": "object"},
    },
    prerequisites=(
        {"capability": "fabric.block", "reference": "block_instance_id"},
        {"capability": "fabric.block_item", "reference": "block_item_instance_id"},
    ),
    requirements=(
        {"key": "blockstate", "description": "the blockstate resource is present"},
        {"key": "block-model", "description": "the block model resource is present"},
        {"key": "item-model", "description": "the item model resource is present"},
        {"key": "lang", "description": "the language resource is present", "required": False},
        {"key": "texture-reference", "description": "the texture strategy is declared"},
    ),
    validations=({
        "key": "artifact", "kind": "artifact", "requirement_keys": ("blockstate", "block-model", "item-model", "lang", "texture-reference"),
        "spec": {
            "profile": "vertical_a_resources_v1",
            "namespace": {"$parameter": "namespace"},
            "block_id": {"$parameter": "block_id"},
            "item_id": {"$parameter": "item_id"},
            "texture_strategy": {"$parameter": "texture_strategy"},
            "texture_reference": {"$parameter": "texture_reference"},
            "texture_path": {"$parameter": "texture_path"},
            "resource_paths": {"$parameter": "resource_paths"},
        },
    },),
)
RECIPE_DEFINITION = _definition(
    "fabric.recipe",
    parameter_schema={
        "output_instance_id": {"type": "string"},
        "namespace": {"type": "string", "format": "identifier", "required": False},
        "recipe_id": {"type": "string", "format": "identifier", "required": False},
        "recipe_type": {"type": "string", "format": "identifier", "required": False},
        "ingredients": {"type": "array"},
        "result_item_id": {"type": "string", "format": "identifier", "required": False},
        "result_count": {"type": "integer", "required": False, "minimum": 1},
        "resource_path": {"type": "string", "required": False},
    },
    prerequisites=({"capability": "fabric.block_item", "reference": "output_instance_id"},),
    requirements=({"key": "recipe-resource", "description": "the recipe resource is declared"},),
    validations=(
        {
            "key": "artifact", "kind": "artifact", "requirement_keys": ("recipe-resource",),
            "required_parameter": "resource_path",
            "spec": {
                "profile": "vertical_a_resources_v1",
                "namespace": {"$parameter": "namespace"},
                "block_id": {"$parameter": "result_item_id"},
                "item_id": {"$parameter": "result_item_id"},
                "recipe_id": {"$parameter": "recipe_id"},
                "recipe_type": {"$parameter": "recipe_type"},
                "ingredients": {"$parameter": "ingredients"},
                "result_count": {"$parameter": "result_count"},
                "resource_paths": {"recipe": {"$parameter": "resource_path"}},
            },
        },
    ),
)

FOUNDATION_DEFINITIONS = (BLOCK_DEFINITION, BLOCK_ITEM_DEFINITION, BLOCK_ASSETS_DEFINITION, RECIPE_DEFINITION)


def foundation_capability_registry() -> CapabilityRegistry:
    """Return a fresh frozen registry containing only M1 foundation kinds."""
    return CapabilityRegistry(FOUNDATION_DEFINITIONS).freeze()


__all__ = [
    "BLOCK_ASSETS_DEFINITION",
    "BLOCK_DEFINITION",
    "BLOCK_ITEM_DEFINITION",
    "CapabilityRegistry",
    "DuplicateCapabilityError",
    "FOUNDATION_DEFINITIONS",
    "RECIPE_DEFINITION",
    "UnsupportedCapabilityError",
    "foundation_capability_registry",
]
