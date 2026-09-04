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
    derive_capability_output_id,
)
from pd_agent.core.contracts import (
    FabricEnvironmentConstraints,
    FabricKnowledgeSignal,
    FabricMutationExpectation,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
)
from .registry import CapabilityRegistry, UnsupportedCapabilityError


_TYPE_NAMES = {"string", "integer", "number", "boolean", "array", "object"}
SUPPORTED_VALIDATION_KINDS = frozenset({"build", "artifact", "minecraft"})


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


@dataclass(frozen=True, slots=True, kw_only=True)
class FabricContractContext:
    """Minimal non-Product context needed to build an existing contract."""

    task_id: str
    revision: str
    goal: str
    environment_constraints: FabricEnvironmentConstraints = FabricEnvironmentConstraints()
    required_capabilities: tuple[str, ...] = ()
    completion_criteria: tuple[str, ...] = ()
    knowledge_signals: tuple[FabricKnowledgeSignal, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ContractExpansionResult:
    """Contract plus plan provenance, without evidence or execution state."""

    contract: FabricTaskContract | None = None
    failure: PlanningFailure | None = None
    capability_requirement_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    capability_validation_requirement_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def success(self) -> bool:
        return self.contract is not None and self.failure is None

    def requirements_for(self, capability_instance_id: str) -> tuple[str, ...]:
        return dict(self.capability_requirement_ids).get(capability_instance_id, ())

    def validations_for(self, capability_instance_id: str) -> tuple[str, ...]:
        return dict(self.capability_validation_requirement_ids).get(capability_instance_id, ())

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "contract": self.contract.to_dict() if self.contract else None,
            "failure": self.failure.to_dict() if self.failure else None,
            "capability_requirement_ids": {key: list(value) for key, value in self.capability_requirement_ids},
            "capability_validation_requirement_ids": {key: list(value) for key, value in self.capability_validation_requirement_ids},
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
        allowed_values = specification.get("enum")
        if allowed_values is not None and parameters[key] not in allowed_values:
            raise CapabilityModelError(f"invalid value for capability parameter: {key}")
        minimum = specification.get("minimum")
        if minimum is not None and parameters[key] < minimum:
            raise CapabilityModelError(f"capability parameter is below minimum: {key}")
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

    def expand_contract(self, plan: PlanningResult, context: FabricContractContext) -> ContractExpansionResult:
        return expand_plan_to_contract(plan, self.registry, context)

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


def _expansion_failure(code: str, message: str, **details: Any) -> ContractExpansionResult:
    return ContractExpansionResult(failure=PlanningFailure(code=code, message=message, details=details))


def expand_plan_to_contract(
    plan: PlanningResult,
    registry: CapabilityRegistry,
    context: FabricContractContext,
) -> ContractExpansionResult:
    """Expand a successful normalized plan into the existing Fabric contract."""
    if not isinstance(plan, PlanningResult) or not plan.success:
        return _expansion_failure("INVALID_GENERATED_CONTRACT", "a successful planning result is required")
    if not isinstance(context, FabricContractContext):
        return _expansion_failure("INVALID_GENERATED_CONTRACT", "contract context is invalid")

    requirements: list[FabricRequirement] = []
    validations: list[FabricValidationRequirement] = []
    mutations: list[FabricMutationExpectation] = []
    requirement_trace: list[tuple[str, tuple[str, ...]]] = []
    validation_trace: list[tuple[str, tuple[str, ...]]] = []
    requirement_by_instance: dict[str, dict[str, str]] = {}
    try:
        for instance in plan.instances:
            definition = registry.get(instance.definition_id)
            local_requirements: dict[str, str] = {}
            for declaration in definition.requirements:
                if not isinstance(declaration, Mapping):
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "requirement declaration must be an object")
                key = declaration.get("key")
                description = declaration.get("description")
                if not isinstance(key, str) or not key or not isinstance(description, str) or not description:
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "requirement declaration is malformed")
                requirement_id = f"requirement:{derive_capability_output_id(instance, key)}"
                requirements.append(FabricRequirement(requirement_id=requirement_id, description=description, required=bool(declaration.get("required", True))))
                local_requirements[key] = requirement_id
            if not local_requirements and definition.requirements != ():
                return _expansion_failure("INVALID_GENERATED_CONTRACT", "capability requirement expansion is malformed")
            requirement_by_instance[instance.identity] = local_requirements
            requirement_trace.append((instance.identity, tuple(local_requirements.values())))

            local_validations: list[str] = []
            for declaration in definition.validations:
                if not isinstance(declaration, Mapping):
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "validation declaration must be an object")
                key = declaration.get("key")
                kind = declaration.get("kind")
                if not isinstance(key, str) or not key or not isinstance(kind, str) or not kind.strip():
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "validation declaration is malformed")
                normalized_kind = kind.casefold()
                required_parameter = declaration.get("required_parameter")
                if required_parameter is not None and required_parameter not in instance.parameters:
                    continue
                if normalized_kind not in SUPPORTED_VALIDATION_KINDS:
                    return _expansion_failure("UNSUPPORTED_VALIDATION", "required validation kind is not supported", kind=normalized_kind)
                raw_keys = declaration.get("requirement_keys", tuple(local_requirements))
                if not isinstance(raw_keys, (list, tuple)) or not raw_keys or any(key not in local_requirements for key in raw_keys):
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "validation has invalid requirement correlation")
                correlated = tuple(local_requirements[key] for key in raw_keys)
                spec = _resolve_declaration_value(declaration.get("spec", {}), instance.parameters)
                if not isinstance(spec, Mapping):
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "validation spec must be a mapping")
                validation_id = f"validation:{derive_capability_output_id(instance, key)}"
                spec = _bind_validation_id(spec, validation_id)
                validations.append(FabricValidationRequirement(
                    validation_requirement_id=validation_id,
                    requirement_ids=correlated,
                    kind=normalized_kind,
                    required=bool(declaration.get("required", True)),
                    spec=spec,
                ))
                local_validations.append(validation_id)
            validation_trace.append((instance.identity, tuple(local_validations)))

            for declaration in definition.mutation_expectations:
                if not isinstance(declaration, Mapping):
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "mutation declaration must be an object")
                key = declaration.get("key")
                role = declaration.get("role")
                if not isinstance(key, str) or not key or not isinstance(role, str) or not role:
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "mutation declaration is malformed")
                paths_parameter = declaration.get("paths_parameter")
                paths = instance.parameters.get(paths_parameter, ()) if paths_parameter else (declaration.get("path"),)
                if paths_parameter and not isinstance(paths, (list, tuple)):
                    return _expansion_failure("INVALID_GENERATED_CONTRACT", "mutation paths must be a sequence")
                for index, path in enumerate(paths):
                    mutations.append(FabricMutationExpectation(
                        expectation_id=f"mutation:{derive_capability_output_id(instance, key + ':' + str(index))}",
                        role=role,
                        path=path,
                        required=bool(declaration.get("required", True)),
                    ))
    except (CapabilityModelError, UnsupportedCapabilityError, ValueError) as exc:
        return _expansion_failure("INVALID_GENERATED_CONTRACT", str(exc))

    try:
        contract = FabricTaskContract(
            task_id=context.task_id,
            revision=context.revision,
            goal=context.goal,
            requirements=tuple(requirements),
            required_capabilities=context.required_capabilities,
            completion_criteria=context.completion_criteria,
            knowledge_signals=context.knowledge_signals,
            validation_requirements=tuple(validations),
            mutation_expectations=tuple(mutations),
            environment_constraints=context.environment_constraints,
        )
    except (TypeError, ValueError) as exc:
        return _expansion_failure("INVALID_GENERATED_CONTRACT", str(exc))
    return ContractExpansionResult(
        contract=contract,
        capability_requirement_ids=tuple(requirement_trace),
        capability_validation_requirement_ids=tuple(validation_trace),
    )


def _resolve_declaration_value(value: Any, parameters: Mapping[str, Any]) -> Any:
    if isinstance(value, Mapping):
        if set(value) == {"$parameter"}:
            return parameters.get(value["$parameter"], {})
        return {key: _resolve_declaration_value(item, parameters) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_declaration_value(item, parameters) for item in value]
    return value


def _bind_validation_id(value: Any, validation_id: str) -> Any:
    if isinstance(value, Mapping):
        return {key: _bind_validation_id(item, validation_id) for key, item in value.items()}
    if isinstance(value, list):
        if value == ["$validation_id"]:
            return [validation_id]
        return [_bind_validation_id(item, validation_id) for item in value]
    return value


__all__ = [
    "CapabilityPlanner",
    "ContractExpansionResult",
    "DependencyEdge",
    "FabricContractContext",
    "PlanningResult",
    "SUPPORTED_VALIDATION_KINDS",
    "expand_plan_to_contract",
    "plan_capabilities",
]
