"""Deterministic acceptance helpers for benchmark tasks."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from pd_agent.minecraft import MinecraftTestSpec


def _normalize_jar_path(value: object) -> str:
    path = str(value).replace("\\", "/").strip()
    if not path:
        raise ValueError("resource path cannot be empty")
    if path.startswith("/") or path.startswith("../") or "/../" in path:
        raise ValueError(f"resource path escapes jar root: {path!r}")
    return path


def _json_pointer_get(value: Any, pointer: str) -> Any:
    if pointer in {"", "/"}:
        return value
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer: {pointer!r}")

    current = value
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise KeyError(token)
            current = current[token]
            continue
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            if token == "-":
                raise KeyError(token)
            index = int(token)
            current = current[index]
            continue
        raise KeyError(token)
    return current


def _override_text(value: object, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


@dataclass(frozen=True, slots=True)
class AcceptanceResourceEvaluation:
    """Structured result for resource-level acceptance checks."""

    passed: bool
    required_resources: tuple[dict[str, Any], ...] = ()
    violations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "required_resources": [
                {
                    **entry,
                    "assertions": [dict(assertion) for assertion in entry.get("assertions", [])],
                }
                for entry in self.required_resources
            ],
            "violations": list(self.violations),
        }


@dataclass(frozen=True, slots=True)
class AcceptanceMinecraftObservationEvaluation:
    """Structured result for required Minecraft observation checks."""

    passed: bool
    required_observations: tuple[MinecraftTestSpec, ...] = ()
    violations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "required_observations": [spec.to_dict() for spec in self.required_observations],
            "violations": list(self.violations),
        }


def evaluate_required_resources(
    artifact_path: Path | None,
    acceptance_spec: Mapping[str, Any] | None,
) -> AcceptanceResourceEvaluation:
    """Evaluate required artifact resources declared in acceptance metadata."""

    if acceptance_spec is None:
        return AcceptanceResourceEvaluation(passed=True)

    raw_requirements = acceptance_spec.get("required_resources", [])
    if not isinstance(raw_requirements, Sequence) or isinstance(raw_requirements, (str, bytes, bytearray)):
        return AcceptanceResourceEvaluation(
            passed=False,
            violations=("required_resources must be a sequence",),
        )

    requirements: list[dict[str, Any]] = []
    violations: list[str] = []
    if not raw_requirements:
        return AcceptanceResourceEvaluation(passed=True, required_resources=())

    if artifact_path is None:
        for index, resource in enumerate(raw_requirements, start=1):
            path = str(resource.get("path", "<missing>")) if isinstance(resource, Mapping) else "<invalid>"
            violations.append(f"resource[{index}] missing artifact jar for {path}")
        return AcceptanceResourceEvaluation(passed=False, violations=tuple(violations))

    try:
        with zipfile.ZipFile(artifact_path) as jar:
            names = set(jar.namelist())
            for index, raw_resource in enumerate(raw_requirements, start=1):
                resource: Mapping[str, Any]
                if isinstance(raw_resource, Mapping):
                    resource = raw_resource
                else:
                    requirements.append(
                        {
                            "index": index,
                            "path": None,
                            "type": None,
                            "present": False,
                            "passed": False,
                            "issues": ["resource entry must be an object"],
                            "assertions": [],
                        }
                    )
                    violations.append(f"resource[{index}] entry must be an object")
                    continue

                path = _normalize_jar_path(resource.get("path"))
                resource_type = str(resource.get("type", "json")).strip().casefold()
                issues: list[str] = []
                assertion_results: list[dict[str, Any]] = []
                present = path in names
                payload_text: str | None = None
                parsed_json: Any = None

                if not present:
                    issues.append(f"missing resource: {path}")
                elif resource_type == "json":
                    try:
                        payload_text = jar.read(path).decode("utf-8")
                    except (KeyError, UnicodeDecodeError, OSError, zipfile.BadZipFile) as exc:
                        issues.append(f"failed to read json resource {path}: {exc}")
                    else:
                        try:
                            parsed_json = json.loads(payload_text)
                        except json.JSONDecodeError as exc:
                            issues.append(f"invalid JSON resource {path}: {exc.msg}")
                elif resource_type == "text":
                    try:
                        payload_text = jar.read(path).decode("utf-8")
                    except (KeyError, UnicodeDecodeError, OSError, zipfile.BadZipFile) as exc:
                        issues.append(f"failed to read text resource {path}: {exc}")
                else:
                    issues.append(f"unsupported resource type: {resource_type}")

                assertions = resource.get("assertions", [])
                if not isinstance(assertions, Sequence) or isinstance(assertions, (str, bytes, bytearray)):
                    issues.append(f"resource[{index}] assertions must be a sequence")
                    assertions = ()

                if present and resource_type == "json" and parsed_json is not None:
                    for assertion in assertions:
                        if not isinstance(assertion, Mapping):
                            assertion_results.append(
                                {
                                    "kind": None,
                                    "passed": False,
                                    "issues": ["assertion must be an object"],
                                }
                            )
                            issues.append(f"{path}: assertion must be an object")
                            continue
                        kind = str(assertion.get("kind", "")).strip()
                        if kind == "json_pointer_equals":
                            json_pointer = str(assertion.get("path", "")).strip()
                            expected = assertion.get("value")
                            try:
                                actual = _json_pointer_get(parsed_json, json_pointer)
                            except Exception as exc:
                                assertion_results.append(
                                    {
                                        "kind": kind,
                                        "path": json_pointer,
                                        "expected": expected,
                                        "passed": False,
                                        "issues": [str(exc)],
                                    }
                                )
                                issues.append(f"{path}: missing JSON value at {json_pointer}")
                                continue
                            passed = actual == expected
                            assertion_results.append(
                                {
                                    "kind": kind,
                                    "path": json_pointer,
                                    "expected": expected,
                                    "actual": actual,
                                    "passed": passed,
                                    "issues": [] if passed else [f"expected {expected!r}, got {actual!r}"],
                                }
                            )
                            if not passed:
                                issues.append(f"{path}: JSON pointer {json_pointer} expected {expected!r}, got {actual!r}")
                        elif kind == "json_pointer_present":
                            json_pointer = str(assertion.get("path", "")).strip()
                            try:
                                actual = _json_pointer_get(parsed_json, json_pointer)
                            except Exception as exc:
                                assertion_results.append(
                                    {
                                        "kind": kind,
                                        "path": json_pointer,
                                        "passed": False,
                                        "issues": [str(exc)],
                                    }
                                )
                                issues.append(f"{path}: missing JSON value at {json_pointer}")
                                continue
                            assertion_results.append(
                                {
                                    "kind": kind,
                                    "path": json_pointer,
                                    "actual": actual,
                                    "passed": True,
                                    "issues": [],
                                }
                            )
                        else:
                            assertion_results.append(
                                {
                                    "kind": kind or None,
                                    "passed": False,
                                    "issues": [f"unsupported assertion kind: {kind or '<empty>'}"],
                                }
                            )
                            issues.append(f"{path}: unsupported assertion kind {kind or '<empty>'}")
                elif present and resource_type == "text":
                    text_assertions = tuple(assertions)
                    for assertion in text_assertions:
                        if not isinstance(assertion, Mapping):
                            assertion_results.append(
                                {
                                    "kind": None,
                                    "passed": False,
                                    "issues": ["assertion must be an object"],
                                }
                            )
                            issues.append(f"{path}: assertion must be an object")
                            continue
                        kind = str(assertion.get("kind", "")).strip()
                        if kind == "text_contains":
                            expected = str(assertion.get("value", ""))
                            passed = expected in (payload_text or "")
                            assertion_results.append(
                                {
                                    "kind": kind,
                                    "expected": expected,
                                    "passed": passed,
                                    "issues": [] if passed else [f"missing substring {expected!r}"],
                                }
                            )
                            if not passed:
                                issues.append(f"{path}: missing substring {expected!r}")
                        elif kind == "text_equals":
                            expected = str(assertion.get("value", ""))
                            actual = payload_text or ""
                            passed = actual == expected
                            assertion_results.append(
                                {
                                    "kind": kind,
                                    "expected": expected,
                                    "actual": actual,
                                    "passed": passed,
                                    "issues": [] if passed else [f"expected exact text {expected!r}, got {actual!r}"],
                                }
                            )
                            if not passed:
                                issues.append(f"{path}: expected exact text {expected!r}, got {actual!r}")
                        else:
                            assertion_results.append(
                                {
                                    "kind": kind or None,
                                    "passed": False,
                                    "issues": [f"unsupported assertion kind: {kind or '<empty>'}"],
                                }
                            )
                            issues.append(f"{path}: unsupported assertion kind {kind or '<empty>'}")

                passed = present and not issues and all(assertion.get("passed", False) for assertion in assertion_results or ({"passed": True},))
                requirements.append(
                    {
                        "index": index,
                        "path": path,
                        "type": resource_type,
                        "present": present,
                        "passed": passed,
                        "issues": issues,
                        "assertions": assertion_results,
                    }
                )
                if not passed:
                    violations.extend(issues or [f"{path}: resource requirements not satisfied"])
    except (zipfile.BadZipFile, OSError) as exc:
        return AcceptanceResourceEvaluation(
            passed=False,
            violations=(f"failed to inspect artifact jar: {exc}",),
        )

    return AcceptanceResourceEvaluation(
        passed=not violations,
        required_resources=tuple(requirements),
        violations=tuple(violations),
    )


def _observation_requirement_sequence(acceptance_spec: Mapping[str, Any] | None) -> Sequence[Any]:
    if acceptance_spec is None:
        return ()
    raw_requirements = acceptance_spec.get("required_minecraft_observations", [])
    if not isinstance(raw_requirements, Sequence) or isinstance(raw_requirements, (str, bytes, bytearray)):
        return ("required_minecraft_observations must be a sequence",)
    return raw_requirements


def build_required_minecraft_observation_spec(
    base_spec: MinecraftTestSpec,
    requirement: Mapping[str, Any],
) -> MinecraftTestSpec:
    """Build a normalized Minecraft spec for an additional required observation."""

    raw_observation_params = requirement.get("observation_params", base_spec.observation_params)
    if raw_observation_params is None:
        raw_observation_params = base_spec.observation_params
    if not isinstance(raw_observation_params, Mapping):
        raise ValueError("observation_params must be a mapping")

    timeout_seconds = requirement.get("timeout_seconds", base_spec.timeout_seconds)
    if timeout_seconds is None:
        timeout_seconds = base_spec.timeout_seconds

    target_mod_id = _override_text(requirement.get("target_mod_id"), base_spec.target_mod_id)
    minecraft_version = _override_text(requirement.get("minecraft_version"), base_spec.minecraft_version)
    loader_version = _override_text(requirement.get("loader_version"), base_spec.loader_version)
    test_id = _override_text(requirement.get("test_id") or requirement.get("label"), base_spec.test_id)
    observation_type = _override_text(requirement.get("observation_type"), base_spec.observation_type.value)
    expect_neighbor_update = requirement.get("expect_neighbor_update", base_spec.expect_neighbor_update)
    if expect_neighbor_update is None:
        expect_neighbor_update = base_spec.expect_neighbor_update

    return MinecraftTestSpec(
        target_jar=base_spec.target_jar,
        target_mod_id=target_mod_id,
        minecraft_version=minecraft_version,
        loader_version=loader_version,
        test_id=test_id,
        observation_type=observation_type,
        observation_params=dict(raw_observation_params),
        timeout_seconds=int(timeout_seconds),
        expect_neighbor_update=bool(expect_neighbor_update),
    )


def evaluate_required_minecraft_observations(
    base_spec: MinecraftTestSpec,
    acceptance_spec: Mapping[str, Any] | None,
) -> AcceptanceMinecraftObservationEvaluation:
    """Normalize additional Minecraft observation specs declared by acceptance metadata."""

    if acceptance_spec is None:
        return AcceptanceMinecraftObservationEvaluation(passed=True)

    raw_requirements = _observation_requirement_sequence(acceptance_spec)
    if raw_requirements and isinstance(raw_requirements[0], str):
        return AcceptanceMinecraftObservationEvaluation(
            passed=False,
            violations=(str(raw_requirements[0]),),
        )
    if not raw_requirements:
        return AcceptanceMinecraftObservationEvaluation(passed=True, required_observations=())

    normalized: list[MinecraftTestSpec] = []
    violations: list[str] = []
    for index, raw_requirement in enumerate(raw_requirements, start=1):
        if not isinstance(raw_requirement, Mapping):
            violations.append(f"required_minecraft_observations[{index}] must be an object")
            continue
        try:
            normalized.append(build_required_minecraft_observation_spec(base_spec, raw_requirement))
        except Exception as exc:  # noqa: BLE001
            violations.append(f"required_minecraft_observations[{index}]: {exc}")

    return AcceptanceMinecraftObservationEvaluation(
        passed=not violations,
        required_observations=tuple(normalized),
        violations=tuple(violations),
    )
