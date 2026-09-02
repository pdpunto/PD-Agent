"""Cheap deterministic validation for workspace resources."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from pd_agent.core import ValidationResult, ValidationStage, ValidationStatus, ValidationViolation
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot, resolve_logical_resource_path

from .fabric import FabricBlockIdentityValidator


class PreBuildValidationError(ValueError):
    """Malformed validator contract or unsafe workspace requirement."""


def _json_pointer_get(value: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise KeyError(f"invalid JSON pointer: {pointer!r}")
    current = value
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise KeyError(pointer)
            current = current[token]
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise KeyError(pointer) from exc
        else:
            raise KeyError(pointer)
    return current


def _relative_path(value: Any) -> str:
    path = str(value).strip().replace("\\", "/")
    if not path:
        raise PreBuildValidationError("resource path must not be empty")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise PreBuildValidationError(f"resource path escapes workspace: {path!r}")
    return parsed.as_posix()


def _contract_mapping(contract: Any) -> Mapping[str, Any]:
    if hasattr(contract, "to_dict") and callable(contract.to_dict):
        contract = contract.to_dict()
    if not isinstance(contract, Mapping):
        raise PreBuildValidationError("pre-build contract must be a mapping")
    return contract


def _recipe_violation(path: str, parsed: Any) -> ValidationViolation | None:
    """Reject JSON recipes that cannot be decoded by the recipe manager."""
    if "/recipe/" not in f"/{path}" or not isinstance(parsed, Mapping):
        return None
    recipe_type = parsed.get("type")
    result = parsed.get("result")
    invalid = not isinstance(recipe_type, str) or not recipe_type.strip() or not isinstance(result, Mapping)
    if not invalid and isinstance(result, Mapping):
        result_id = result.get("id", result.get("item"))
        invalid = not isinstance(result_id, str) or not result_id.strip()
    if not invalid and recipe_type.endswith("crafting_shaped"):
        invalid = not isinstance(parsed.get("pattern"), list) or not isinstance(parsed.get("key"), Mapping)
    if not invalid and recipe_type.endswith("crafting_shapeless"):
        invalid = not isinstance(parsed.get("ingredients"), list)
    if not invalid:
        return None
    return ValidationViolation(
        code="RECIPE_SCHEMA_INVALID",
        requirement=path,
        observed={"category": "invalid_recipe_schema", "type": recipe_type},
        expected="a typed recipe with a result and valid shaped/shapeless fields",
        actual=parsed,
        message=f"required recipe is not compatible with the supported recipe schema: {path}",
        phase="PRE_BUILD",
        evidence_refs=(f"workspace/{path}",),
    )


class PreBuildWorkspaceValidator:
    """Validate only required files and JSON pointer requirements."""

    def __init__(
        self,
        *,
        resource_roots: tuple[Path, ...] = (),
        semantic_validators: tuple[object, ...] | None = None,
    ) -> None:
        self.resource_roots = tuple(Path(root) for root in resource_roots)
        self.semantic_validators = semantic_validators if semantic_validators is not None else (FabricBlockIdentityValidator(),)

    def validate(self, project_root: Path, contract: Any) -> ValidationResult:
        data = _contract_mapping(contract)
        raw_resources = data.get("required_resources")
        if raw_resources is None:
            raw_resources = tuple(
                {"path": path, "resource_type": "json"}
                for validation in data.get("validation_requirements", ())
                if isinstance(validation, Mapping)
                and validation.get("kind") == "artifact"
                for path in validation.get("spec", {}).get("required_paths", ())
            )
        if not isinstance(raw_resources, (list, tuple)):
            raise PreBuildValidationError("required_resources must be a sequence")

        violations: list[ValidationViolation] = []
        root = Path(project_root).resolve(strict=True)
        for index, raw_resource in enumerate(raw_resources):
            if not isinstance(raw_resource, Mapping):
                raise PreBuildValidationError(f"required_resources[{index}] must be an object")
            path = _relative_path(raw_resource.get("path"))
            resource_type = str(raw_resource.get("resource_type", raw_resource.get("type", "json"))).strip().casefold()
            if resource_type not in {"json", "text"}:
                raise PreBuildValidationError(f"unsupported resource type: {resource_type}")
            if path.startswith("src/main/resources/"):
                candidate = (root / Path(path)).resolve(strict=False)
            elif self.resource_roots:
                try:
                    physical_path = resolve_logical_resource_path(
                        ProjectSnapshot(
                            project_root=root,
                            status=ProjectInspectionStatus.READY,
                            resource_roots=self.resource_roots,
                            target_subproject=root,
                        ),
                        path,
                    )
                except ValueError as exc:
                    raise PreBuildValidationError(str(exc)) from exc
                candidate = (root / Path(physical_path)).resolve(strict=False)
            else:
                candidate = (root / Path(path)).resolve(strict=False)
            if root not in candidate.parents and candidate != root:
                raise PreBuildValidationError(f"resource path escapes workspace: {path!r}")
            evidence_ref = f"workspace/{path}"
            if not candidate.is_file():
                violations.append(
                    ValidationViolation(
                        code="RESOURCE_MISSING",
                        requirement=path,
                        observed={"category": "missing", "present": False},
                        message=f"required resource is missing: {path}",
                        evidence_refs=(evidence_ref,),
                    )
                )
                continue
            if resource_type != "json":
                continue
            try:
                parsed = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                violations.append(
                    ValidationViolation(
                        code="RESOURCE_INVALID_JSON",
                        requirement=path,
                        observed={"category": "invalid_json"},
                        message=f"required JSON resource is invalid: {path}",
                        evidence_refs=(evidence_ref,),
                    )
                )
                continue
            recipe_violation = _recipe_violation(path, parsed)
            if recipe_violation is not None:
                violations.append(recipe_violation)
            assertions = raw_resource.get("assertions", ())
            if not isinstance(assertions, (list, tuple)):
                raise PreBuildValidationError(f"{path}.assertions must be a sequence")
            for assertion_index, raw_assertion in enumerate(assertions):
                if not isinstance(raw_assertion, Mapping):
                    raise PreBuildValidationError(
                        f"{path}.assertions[{assertion_index}] must be an object"
                    )
                kind = str(raw_assertion.get("kind", "")).strip()
                pointer = str(raw_assertion.get("path", "")).strip()
                if kind not in {"json_pointer_present", "json_pointer_equals"}:
                    raise PreBuildValidationError(f"unsupported JSON assertion kind: {kind}")
                try:
                    actual = _json_pointer_get(parsed, pointer)
                except KeyError:
                    violations.append(
                        ValidationViolation(
                            code="JSON_POINTER_MISSING",
                            requirement=f"{path}:{pointer}",
                            observed={"category": "missing", "present": False},
                            message=f"required JSON value is missing: {path} {pointer}",
                            evidence_refs=(evidence_ref,),
                        )
                    )
                    continue
                if kind == "json_pointer_equals" and actual != raw_assertion.get("value"):
                    violations.append(
                        ValidationViolation(
                            code="JSON_POINTER_MISMATCH",
                            requirement=f"{path}:{pointer}",
                            observed={"category": "mismatch", "actual": actual},
                            message=f"required JSON value does not match: {path} {pointer}",
                            evidence_refs=(evidence_ref,),
                        )
                    )

        for validator in self.semantic_validators:
            result = validator.validate(root, data)
            if not isinstance(result, ValidationResult):
                raise TypeError("semantic validator must return ValidationResult")
            violations.extend(result.violations)

        status = ValidationStatus.PASS if not violations else ValidationStatus.REPAIRABLE_FAIL
        summary = "pre-build requirements passed" if not violations else "pre-build requirements failed"
        return ValidationResult(
            stage=ValidationStage.PRE_BUILD,
            status=status,
            summary=summary,
            violations=tuple(violations),
            evidence_refs=tuple(dict.fromkeys(ref for violation in violations for ref in violation.evidence_refs)),
        )
