"""Pure deterministic composition planning for M1."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping

from .capabilities import (
    CapabilityCandidate,
    CapabilityInstance,
    CapabilityModelError,
    PlanningFailure,
    canonical_capability_json,
)
from .registry import CapabilityRegistry, UnsupportedCapabilityError


_TYPE_NAMES = {"string", "integer", "number", "boolean", "array", "object"}


@dataclass(frozen=True, slots=True, kw_only=True)
class DependencyEdge:
    """One dependent-to-prerequisite relation."""

    dependent_instance_id: str
    prerequisite_instance_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "dependent_instance_id": self.dependent_instance_id,
            "prerequisite_instance_id": self.prerequisite_instance_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanningResult:
    """Immutable data-only result of one planning attempt."""

    instances: tuple[CapabilityInstance, ...] = ()
    dependency_edges: tuple[DependencyEdge, ...] = ()
    failure: PlanningFailure | None = None

    @property
    def success(self) -> bool:
        return self.failure is None

    @property
    def plan_fingerprint(self) -> str | None:
        if not self.success:
            return None
        payload = {
            "instances": [item.to_dict(include_identity=True) for item in self.instances],
            "dependency_edges": [edge.to_dict() for edge in self.dependency_edges],
        }
        return hashlib.sha256(canonical_capability_json(payload).encode("utf-8")).hexdigest()

    @property
    def identity(self) -> str | None:
        return self.plan_fingerprint

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "instances": [item.to_dict() for item in self.instances],
            "dependency_edges": [edge.to_dict() for edge in self.dependency_edges],
            "failure": self.failure.to_dict() if self.failure else None,
            "plan_fingerprint": self.plan_fingerprint,
        }


def _failure(code: str, message: str, **details: Any) -> PlanningResult:
    return PlanningResult(failure=PlanningFailure(code=code, message=message, details=details))


def _matches_type(value: Any, type_name: str) -> bool:
    return {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }.get(type_name, False)


def _validate_parameters(candidate: CapabilityCandidate, definition: Any) -> dict[str, Any]:
    schema = definition.parameter_schema
    parameters = dict(candidate.parameters)
    unknown = sorted(set(parameters) - set(schema))
    if unknown:
        raise CapabilityModelError(f"unknown capability parameters: {', '.join(unknown)}")
    for key, specification in schema.items():
        if not isinstance(specification, Mapping):
            raise CapabilityModelError(f"parameter schema for {key} must be a mapping")
        if key not in parameters:
            if key in definition.parameter_defaults:
                parameters[key] = definition.parameter_defaults[key]
            elif specification.get("required", True):
                raise CapabilityModelError(f"missing required capability parameter: {key}")
        if key not in parameters:
            continue
        type_name = specification.get("type")
        if type_name not in _TYPE_NAMES or not _matches_type(parameters[key], type_name):
            raise CapabilityModelError(f"invalid type for capability parameter: {key}")
        if specification.get("format") == "identifier":
            if not isinstance(parameters[key], str) or not parameters[key] or any(char in parameters[key] for char in "/\\"):
                raise CapabilityModelError(f"invalid identifier parameter: {key}")
    return parameters


class CapabilityPlanner:
    """Stateless planner with no execution or persistence authority."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def plan(self, candidates: Iterable[CapabilityCandidate]) -> PlanningResult:
        if isinstance(candidates, (str, bytes)):
            return _failure("INVALID_PARAMETERS", "candidate input must be a sequence of capability candidates")
        try:
            values = tuple(candidates)
        except TypeError:
            return _failure("INVALID_PARAMETERS", "candidate input must be iterable")
        if any(not isinstance(item, CapabilityCandidate) for item in values):
            return _failure("INVALID_PARAMETERS", "candidate input contains a non-candidate value")

        instances_by_identity: dict[str, CapabilityInstance] = {}
        try:
            for candidate in values:
                definition = self.registry.get(candidate.definition_id)
                parameters = _validate_parameters(candidate, definition)
                instance = CapabilityInstance(
                    definition_id=definition.definition_id,
                    definition_schema_version=definition.schema_version,
                    parameters=parameters,
                )
                instances_by_identity.setdefault(instance.identity, instance)
        except UnsupportedCapabilityError as exc:
            return _failure("UNSUPPORTED_CAPABILITY", str(exc), definition_id=str(getattr(exc, "args", [""])[0]))
        except CapabilityModelError as exc:
            return _failure("INVALID_PARAMETERS", str(exc))

        edges: set[tuple[str, str]] = set()
        for instance in instances_by_identity.values():
            definition = self.registry.get(instance.definition_id)
            for declaration in definition.prerequisites:
                if not isinstance(declaration, Mapping):
                    return _failure("INVALID_PREREQUISITE", "prerequisite declaration must be an object")
                target = self._resolve_prerequisite(declaration, instance, instances_by_identity)
                if isinstance(target, PlanningResult):
                    return target
                edges.add((instance.identity, target.identity))

        cycle = self._find_cycle(instances_by_identity, edges)
        if cycle:
            return _failure("DEPENDENCY_CYCLE", "capability dependency cycle detected", cycle=cycle)
        ordered = self._topological_order(instances_by_identity, edges)
        ordered_edges = tuple(DependencyEdge(dependent_instance_id=a, prerequisite_instance_id=b) for a, b in sorted(edges))
        return PlanningResult(instances=ordered, dependency_edges=ordered_edges)

    def _resolve_prerequisite(
        self,
        declaration: Mapping[str, Any],
        dependent: CapabilityInstance,
        instances: Mapping[str, CapabilityInstance],
    ) -> CapabilityInstance | PlanningResult:
        reference = declaration.get("reference")
        if reference is not None:
            if not isinstance(reference, str) or reference not in dependent.parameters:
                return _failure("INVALID_PREREQUISITE", "prerequisite reference is not a declared parameter", dependent=dependent.identity)
            target_id = dependent.parameters[reference]
            if not isinstance(target_id, str):
                return _failure("INVALID_PREREQUISITE", "prerequisite reference must contain an instance identity")
            target = instances.get(target_id)
        else:
            target = None
            capability = declaration.get("capability")
            matches = [item for item in instances.values() if capability is None or item.definition_id == capability]
            if len(matches) == 1:
                target = matches[0]
            elif len(matches) > 1:
                return _failure("INVALID_PREREQUISITE", "prerequisite capability reference is ambiguous")
        if target is None:
            return _failure("UNRESOLVED_PREREQUISITE", "prerequisite instance was not found", dependent=dependent.identity)
        expected = declaration.get("capability")
        if expected is not None and target.definition_id != expected:
            return _failure("INVALID_PREREQUISITE", "prerequisite capability does not match", expected=expected, actual=target.definition_id)
        return target

    @staticmethod
    def _find_cycle(instances: Mapping[str, CapabilityInstance], edges: set[tuple[str, str]]) -> list[str] | None:
        graph: dict[str, list[str]] = {identity: [] for identity in instances}
        for dependent, prerequisite in edges:
            graph[dependent].append(prerequisite)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str, path: list[str]) -> list[str] | None:
            if node in visiting:
                return path[path.index(node) :] + [node]
            if node in visited:
                return None
            visiting.add(node)
            for child in sorted(graph[node]):
                found = visit(child, path + [child])
                if found:
                    return found
            visiting.remove(node)
            visited.add(node)
            return None

        for identity in sorted(instances):
            found = visit(identity, [identity])
            if found:
                return found
        return None

    @staticmethod
    def _topological_order(instances: Mapping[str, CapabilityInstance], edges: set[tuple[str, str]]) -> tuple[CapabilityInstance, ...]:
        prerequisites: dict[str, set[str]] = {identity: set() for identity in instances}
        dependents: dict[str, set[str]] = {identity: set() for identity in instances}
        for dependent, prerequisite in edges:
            prerequisites[dependent].add(prerequisite)
            dependents[prerequisite].add(dependent)
        ready = sorted(identity for identity, required in prerequisites.items() if not required)
        result: list[CapabilityInstance] = []
        while ready:
            identity = ready.pop(0)
            result.append(instances[identity])
            for dependent in sorted(dependents[identity]):
                prerequisites[dependent].discard(identity)
                if not prerequisites[dependent] and dependent not in ready and instances[dependent] not in result:
                    ready.append(dependent)
                    ready.sort()
        return tuple(result)


def plan_capabilities(candidates: Iterable[CapabilityCandidate], registry: CapabilityRegistry) -> PlanningResult:
    """Convenience boundary for one stateless planning operation."""
    return CapabilityPlanner(registry).plan(candidates)


__all__ = ["CapabilityPlanner", "DependencyEdge", "PlanningResult", "plan_capabilities"]
