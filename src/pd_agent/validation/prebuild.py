"""Cheap deterministic validation for workspace resources."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from pd_agent.core import ValidationResult, ValidationStage, ValidationStatus, ValidationViolation
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot, resolve_logical_resource_path
from pd_agent.tools import SecurePathResolver

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


def _profile_violation(code: str, path: str, message: str, *, observed: Any = None, expected: Any = None) -> ValidationViolation:
    return ValidationViolation(
        code=code,
        requirement=path,
        observed=observed if observed is not None else {"path": path},
        expected=expected,
        actual=observed,
        message=message,
        phase="PRE_BUILD",
        evidence_refs=(f"workspace/{path}",),
    )


def _resource_paths(spec: Mapping[str, Any]) -> dict[str, str]:
    raw = spec.get("resource_paths", {})
    if not isinstance(raw, Mapping):
        return {}
    aliases = {"block-model": "block_model", "item-model": "item_model"}
    return {
        aliases.get(str(key), str(key)): str(value)
        for key, value in raw.items()
        if isinstance(value, str) and value.strip()
    }


def _vertical_a_violations(root: Path, spec: Mapping[str, Any], resource_roots: tuple[Path, ...] = ()) -> list[ValidationViolation]:
    """Validate the deliberately small Vertical A resource profile."""
    paths = _resource_paths(spec)
    namespace = str(spec.get("namespace", "")).strip()
    block_id = str(spec.get("block_id", "")).strip()
    item_id = str(spec.get("item_id", block_id)).strip()
    recipe_id = str(spec.get("recipe_id", "")).strip()
    asset_spec = any(key in spec for key in ("texture_strategy", "texture_reference", "blockstate", "block_model", "item_model"))
    expected = ({
        "blockstate": f"assets/{namespace}/blockstates/{block_id}.json",
        "block_model": f"assets/{namespace}/models/block/{block_id}.json",
        "item_model": f"assets/{namespace}/models/item/{item_id}.json",
        "recipe": f"data/{namespace}/recipes/{recipe_id}.json",
    } if asset_spec else {"recipe": f"data/{namespace}/recipes/{recipe_id}.json"})
    for key, value in expected.items():
        paths.setdefault(key, value)
    violations: list[ValidationViolation] = []
    parsed_files: dict[str, Any] = {}
    resource_keys = ("blockstate", "block_model", "item_model", "lang", "recipe") if asset_spec else ("recipe",)
    for key in resource_keys:
        path = paths.get(key)
        if not path:
            if key in {"blockstate", "block_model", "item_model", "recipe"}:
                violations.append(_profile_violation("VERTICAL_A_PATH_MISSING", key, f"Vertical A path is not declared: {key}"))
            continue
        try:
            relative = _relative_path(path)
            if not relative.startswith("src/main/resources/") and resource_roots:
                physical = resolve_logical_resource_path(
                    ProjectSnapshot(
                        project_root=root,
                        status=ProjectInspectionStatus.READY,
                        resource_roots=resource_roots,
                        target_subproject=root,
                    ),
                    relative,
                )
                candidate = (root / Path(physical)).resolve(strict=False)
            else:
                candidate = (root / Path(relative)).resolve(strict=False)
        except PreBuildValidationError:
            violations.append(_profile_violation("VERTICAL_A_PATH_INVALID", path, f"invalid Vertical A resource path: {path}"))
            continue
        if root not in candidate.parents:
            violations.append(_profile_violation("VERTICAL_A_PATH_INVALID", path, f"Vertical A resource escapes workspace: {path}"))
            continue
        if not candidate.is_file():
            violations.append(_profile_violation("RESOURCE_MISSING", path, f"required Vertical A resource is missing: {path}", observed={"path": path, "present": False}))
            continue
        try:
            parsed_files[key] = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            violations.append(_profile_violation("RESOURCE_INVALID_JSON", path, f"required Vertical A JSON is invalid: {path}"))

    blockstate = parsed_files.get("blockstate")
    if blockstate is not None:
        model_path = paths["block_model"].removeprefix("src/main/resources/").removesuffix(".json")
        model_parts = model_path.split("/")
        expected_model = f"{model_parts[1]}:block/{model_parts[-1]}" if len(model_parts) >= 4 and model_parts[0] == "assets" else model_path
        variants = blockstate.get("variants") if isinstance(blockstate, Mapping) else None
        models = [value.get("model") for value in variants.values() if isinstance(value, Mapping) and isinstance(value.get("model"), str)] if isinstance(variants, Mapping) else []
        if not isinstance(blockstate, Mapping) or not isinstance(variants, Mapping) or not models or not any(model == expected_model for model in models):
            violations.append(_profile_violation("VERTICAL_A_BLOCKSTATE_INVALID", paths["blockstate"], "blockstate must contain variants referencing the expected block model", observed=blockstate, expected=expected_model))

    block_model = parsed_files.get("block_model")
    if block_model is not None:
        parent = block_model.get("parent") if isinstance(block_model, Mapping) else None
        if not isinstance(block_model, Mapping) or not isinstance(parent, str) or not parent.strip():
            violations.append(_profile_violation("VERTICAL_A_BLOCK_MODEL_INVALID", paths["block_model"], "block model must declare a parent", observed=block_model, expected="parent"))

    item_model = parsed_files.get("item_model")
    if item_model is not None:
        parent = item_model.get("parent") if isinstance(item_model, Mapping) else None
        expected_parent = f"{namespace}:block/{block_id}"
        if not isinstance(item_model, Mapping) or not isinstance(parent, str) or parent not in {expected_parent, "minecraft:item/generated"}:
            violations.append(_profile_violation("VERTICAL_A_ITEM_MODEL_INVALID", paths["item_model"], "item model must reference the block model or item/generated", observed=item_model, expected=expected_parent))

    strategy = str(spec.get("texture_strategy", "REUSE")).upper()
    texture_reference = spec.get("texture_reference")
    if asset_spec:
        if strategy not in {"REUSE", "DERIVE"}:
            violations.append(_profile_violation("VERTICAL_A_TEXTURE_STRATEGY_UNSUPPORTED", "texture-reference", "GENERATE is not implemented for Vertical A", observed=strategy, expected=("REUSE", "DERIVE")))
        elif not isinstance(texture_reference, str) or ":" not in texture_reference or texture_reference.startswith(":") or texture_reference.endswith(":"):
            violations.append(_profile_violation("VERTICAL_A_TEXTURE_REFERENCE_INVALID", "texture-reference", "texture reference must be a namespace:path identifier", observed=texture_reference, expected="namespace:path"))
        elif strategy == "REUSE" and spec.get("texture_path"):
            violations.append(_profile_violation("VERTICAL_A_TEXTURE_REFERENCE_INVALID", "texture-reference", "REUSE must not require an owned texture file", observed=spec.get("texture_path"), expected=None))

    lang = parsed_files.get("lang")
    lang_key = spec.get("lang_key")
    if lang_key is not None and lang is not None:
        if not isinstance(lang, Mapping) or lang_key not in lang:
            violations.append(_profile_violation("VERTICAL_A_LANG_KEY_MISSING", paths["lang"], f"language key is missing: {lang_key}", observed=lang_key, expected=lang_key))
        elif "lang_value" in spec and lang[lang_key] != spec["lang_value"]:
            violations.append(_profile_violation("VERTICAL_A_LANG_VALUE_MISMATCH", paths["lang"], f"language value does not match: {lang_key}", observed=lang[lang_key], expected=spec["lang_value"]))

    recipe = parsed_files.get("recipe")
    if recipe is not None:
        recipe_type = spec.get("recipe_type")
        result_id = f"{namespace}:{item_id}"
        actual_result = recipe.get("result", {}).get("id", recipe.get("result", {}).get("item")) if isinstance(recipe, Mapping) and isinstance(recipe.get("result"), Mapping) else None
        if not isinstance(recipe, Mapping) or (recipe_type is not None and recipe.get("type") != recipe_type):
            violations.append(_profile_violation("VERTICAL_A_RECIPE_INVALID", paths["recipe"], "recipe type does not match the Vertical A contract", observed=recipe, expected=recipe_type))
        ingredients = spec.get("ingredients")
        actual_ingredients = recipe.get("key", recipe.get("ingredients")) if isinstance(recipe, Mapping) else None
        if ingredients is not None and actual_ingredients != ingredients:
            violations.append(_profile_violation("VERTICAL_A_RECIPE_INGREDIENT_MISMATCH", paths["recipe"], "recipe ingredients do not match the Vertical A contract", observed=actual_ingredients, expected=ingredients))
        if actual_result != result_id:
            violations.append(_profile_violation("VERTICAL_A_RECIPE_RESULT_MISMATCH", paths["recipe"], "recipe result does not match the BlockItem", observed=actual_result, expected=result_id))
        if "result_count" in spec and (not isinstance(recipe.get("result"), Mapping) or recipe["result"].get("count") != spec["result_count"]):
            violations.append(_profile_violation("VERTICAL_A_RECIPE_COUNT_MISMATCH", paths["recipe"], "recipe result count does not match the contract", observed=recipe.get("result") if isinstance(recipe, Mapping) else None, expected=spec["result_count"]))
    owned_texture = spec.get("texture_path") if asset_spec and strategy != "REUSE" else None
    if owned_texture:
        texture_candidate = (root / Path(_relative_path(owned_texture))).resolve(strict=False)
        if not texture_candidate.is_file():
            violations.append(_profile_violation("RESOURCE_MISSING", owned_texture, f"owned texture is missing: {owned_texture}"))
    return violations


def _vertical_b_candidate(root: Path, path: Any, resource_roots: tuple[Path, ...]) -> tuple[str, Path] | None:
    relative = _relative_path(path)
    resolver = SecurePathResolver(root)
    if relative.startswith("src/main/resources/") or relative.startswith("src/main/java/"):
        return relative, resolver.resolve_relative(relative)
    if resource_roots:
        logical = resolve_logical_resource_path(
            ProjectSnapshot(
                project_root=root,
                status=ProjectInspectionStatus.READY,
                resource_roots=resource_roots,
                target_subproject=root,
            ),
            relative,
        )
        return relative, resolver.resolve_relative(logical)
    return relative, resolver.resolve_relative(relative)


def _namespaced_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.count(":") == 1 and all(value.split(":"))


def _vertical_b_violations(root: Path, spec: Mapping[str, Any], resource_roots: tuple[Path, ...] = ()) -> list[ValidationViolation]:
    """Validate the bounded standalone-item and recipe resource profile."""
    namespace = str(spec.get("namespace", "")).strip()
    item_id = str(spec.get("item_id", "")).strip()
    if not namespace or not item_id:
        return [_profile_violation("VERTICAL_B_ID_INVALID", "vertical_b_resources_v1", "Vertical B requires namespace and item_id")]
    paths = _resource_paths(spec)
    violations: list[ValidationViolation] = []
    parsed: dict[str, Any] = {}
    source_path = spec.get("source_path")
    if source_path:
        try:
            source_info = _vertical_b_candidate(root, source_path, resource_roots)
            assert source_info is not None
            source_relative, source = source_info
            source_text = source.read_text(encoding="utf-8") if source.is_file() else ""
        except Exception as exc:
            source_relative, source, source_text = str(source_path), None, ""
            violations.append(_profile_violation("VERTICAL_B_PATH_INVALID", str(source_path), f"standalone item source path is unsafe: {exc}"))
        if source is not None and not source.is_file():
            violations.append(_profile_violation("VERTICAL_B_ITEM_SOURCE_MISSING", source_relative, "standalone item source is missing", observed={"path": source_relative, "present": False}))
        elif source is not None:
            namespaced = f"{namespace}:{item_id}"
            has_id = namespaced in source_text or (namespace in source_text and item_id in source_text)
            has_registration = bool(re.search(r"Registry\.register|registerItem|ITEM", source_text))
            has_constructor = "new Item" in source_text or "Item.Settings" in source_text
            if not has_id or not has_registration:
                violations.append(_profile_violation("VERTICAL_B_ITEM_REGISTRATION_MISSING", source_relative, "standalone item source must register the expected namespaced item", observed=source_text[:500], expected=namespaced))
            if not has_constructor:
                violations.append(_profile_violation("VERTICAL_B_ITEM_SETTINGS_MISSING", source_relative, "standalone item source must declare bounded Item.Settings or Item construction", observed=source_text[:500], expected="Item.Settings"))
            settings = spec.get("settings")
            if isinstance(settings, Mapping):
                for key, value in settings.items():
                    if str(value) not in source_text and str(key) not in source_text:
                        violations.append(_profile_violation("VERTICAL_B_ITEM_SETTINGS_MISMATCH", source_relative, f"item setting is not represented: {key}", observed=value, expected=key))

    model_path = paths.get("item_model", f"src/main/resources/assets/{namespace}/models/item/{item_id}.json")
    lang_path = paths.get("lang", f"src/main/resources/assets/{namespace}/lang/en_us.json")
    expected_model_suffix = f"assets/{namespace}/models/item/{item_id}.json"
    expected_lang_suffix = f"assets/{namespace}/lang/en_us.json"
    if not str(model_path).replace("\\", "/").endswith(expected_model_suffix):
        violations.append(_profile_violation("VERTICAL_B_ITEM_MODEL_PATH_MISMATCH", str(model_path), "item model path does not match the namespace and item identity", observed=model_path, expected=expected_model_suffix))
    if not str(lang_path).replace("\\", "/").endswith(expected_lang_suffix):
        violations.append(_profile_violation("VERTICAL_B_LANG_PATH_MISMATCH", str(lang_path), "language path does not match the namespace", observed=lang_path, expected=expected_lang_suffix))
    for kind, path in (("item_model", model_path), ("lang", lang_path)):
        try:
            info = _vertical_b_candidate(root, path, resource_roots)
            assert info is not None
            relative, candidate = info
        except Exception as exc:
            violations.append(_profile_violation("VERTICAL_B_PATH_INVALID", str(path), f"Vertical B resource path is unsafe: {exc}"))
            continue
        if not candidate.is_file():
            violations.append(_profile_violation("VERTICAL_B_RESOURCE_MISSING", relative, f"required standalone item resource is missing: {relative}", observed={"path": relative, "present": False}))
            continue
        try:
            parsed[kind] = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            violations.append(_profile_violation("VERTICAL_B_RESOURCE_INVALID_JSON", relative, f"required standalone item JSON is invalid: {relative}"))

    model = parsed.get("item_model")
    if model is not None:
        parent = model.get("parent") if isinstance(model, Mapping) else None
        if not isinstance(model, Mapping) or not isinstance(parent, str) or parent not in {"minecraft:item/generated", "minecraft:item/handheld", f"{namespace}:item/{item_id}"}:
            violations.append(_profile_violation("VERTICAL_B_ITEM_MODEL_INVALID", model_path, "item model must declare a supported parent", observed=parent, expected=("minecraft:item/generated", "minecraft:item/handheld")))
        textures = model.get("textures") if isinstance(model, Mapping) else None
        if textures is not None and (not isinstance(textures, Mapping) or any(not _namespaced_id(value) for value in textures.values())):
            violations.append(_profile_violation("VERTICAL_B_TEXTURE_REFERENCE_INVALID", model_path, "item model texture references must be namespaced identifiers", observed=textures, expected="namespace:path"))
    lang = parsed.get("lang")
    lang_key = str(spec.get("lang_key", f"item.{namespace}.{item_id}"))
    if not isinstance(lang, Mapping) or lang_key not in lang:
        violations.append(_profile_violation("VERTICAL_B_LANG_ENTRY_MISMATCH", lang_path, "item language entry is missing", observed=lang, expected=lang_key))
    elif "display_name" in spec and lang[lang_key] != spec["display_name"]:
        violations.append(_profile_violation("VERTICAL_B_LANG_ENTRY_MISMATCH", lang_path, "item language value does not match", observed=lang[lang_key], expected=spec["display_name"]))

    strategy = str(spec.get("texture_strategy", "REUSE")).upper()
    reference = spec.get("texture_reference")
    if strategy not in {"REUSE", "DERIVE", "GENERATE"} or not _namespaced_id(reference):
        violations.append(_profile_violation("VERTICAL_B_TEXTURE_REFERENCE_INVALID", "texture-reference", "texture strategy requires a namespaced resource reference", observed=reference, expected="namespace:path"))
    if strategy in {"DERIVE", "GENERATE"} and isinstance(spec.get("texture_path"), str):
        try:
            _, texture = _vertical_b_candidate(root, spec["texture_path"], resource_roots)
            if not texture.is_file():
                violations.append(_profile_violation("VERTICAL_B_TEXTURE_MISSING", str(spec["texture_path"]), "declared derived/generated texture is missing"))
        except Exception as exc:
            violations.append(_profile_violation("VERTICAL_B_PATH_INVALID", str(spec["texture_path"]), f"texture path is unsafe: {exc}"))

    recipe_path = paths.get("recipe")
    expected_output = spec.get("expected_output_id", f"{namespace}:{item_id}")
    expected_ingredients = spec.get("expected_ingredients", ())
    if recipe_path:
        try:
            info = _vertical_b_candidate(root, recipe_path, resource_roots)
            assert info is not None
            relative, candidate = info
            recipe_id = spec.get("recipe_id")
            if isinstance(recipe_id, str) and not relative.replace("\\", "/").endswith(f"data/{namespace}/recipes/{recipe_id}.json"):
                violations.append(_profile_violation("VERTICAL_B_RECIPE_PATH_MISMATCH", relative, "recipe path does not match the namespace and recipe identity", observed=relative, expected=f"data/{namespace}/recipes/{recipe_id}.json"))
            if not candidate.is_file():
                violations.append(_profile_violation("VERTICAL_B_RECIPE_MISSING", relative, "recipe resource is missing"))
            else:
                recipe = json.loads(candidate.read_text(encoding="utf-8"))
                recipe_type = recipe.get("type") if isinstance(recipe, Mapping) else None
                result = recipe.get("result") if isinstance(recipe, Mapping) else None
                actual_output = result.get("id", result.get("item")) if isinstance(result, Mapping) else None
                count = result.get("count", 1) if isinstance(result, Mapping) else None
                if recipe_type not in {"minecraft:crafting_shaped", "minecraft:crafting_shapeless"}:
                    violations.append(_profile_violation("VERTICAL_B_RECIPE_SCHEMA_INVALID", relative, "recipe must use a bounded crafting type", observed=recipe_type, expected=("minecraft:crafting_shaped", "minecraft:crafting_shapeless")))
                if actual_output != expected_output:
                    violations.append(_profile_violation("VERTICAL_B_RECIPE_OUTPUT_MISMATCH", relative, "recipe output does not match resolved item identity", observed=actual_output, expected=expected_output))
                if not isinstance(count, int) or not 1 <= count <= 64:
                    violations.append(_profile_violation("VERTICAL_B_RECIPE_COUNT_INVALID", relative, "recipe output count must be between 1 and 64", observed=count, expected="1..64"))
                expected_count = spec.get("result_count")
                if isinstance(expected_count, int) and count != expected_count:
                    violations.append(_profile_violation("VERTICAL_B_RECIPE_COUNT_MISMATCH", relative, "recipe output count does not match the contract", observed=count, expected=expected_count))
                actual_ingredients = list(recipe.get("ingredients", ())) if recipe_type == "minecraft:crafting_shapeless" else list((recipe.get("key") or {}).values())
                actual_ids = []
                for ingredient in actual_ingredients:
                    if isinstance(ingredient, Mapping):
                        actual_ids.append(ingredient.get("item", ingredient.get("id")))
                expected_ids = [item.get("item_id") for item in expected_ingredients if isinstance(item, Mapping)]
                if expected_ids and sorted(actual_ids) != sorted(expected_ids):
                    violations.append(_profile_violation("VERTICAL_B_RECIPE_INGREDIENT_MISMATCH", relative, "recipe ingredients do not match resolved vanilla/own-task identities", observed=actual_ids, expected=expected_ids))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, Exception) as exc:
            violations.append(_profile_violation("VERTICAL_B_RECIPE_INVALID", str(recipe_path), f"recipe resource is invalid: {exc}"))
    return violations


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

        for validation in data.get("validation_requirements", ()):
            if isinstance(validation, Mapping):
                profile = validation.get("spec", {}).get("profile") if isinstance(validation.get("spec"), Mapping) else None
                if profile == "vertical_a_resources_v1":
                    violations.extend(_vertical_a_violations(root, validation["spec"], self.resource_roots))
                if profile == "vertical_b_resources_v1":
                    violations.extend(_vertical_b_violations(root, validation["spec"], self.resource_roots))

        # A model or recipe path has one deterministic owner; shared lang files
        # intentionally remain valid for multiple item entries.
        resource_claims: dict[tuple[str, str], str] = {}
        for validation in data.get("validation_requirements", ()):
            if not isinstance(validation, Mapping) or not isinstance(validation.get("spec"), Mapping):
                continue
            spec = validation["spec"]
            if spec.get("profile") != "vertical_b_resources_v1":
                continue
            paths = _resource_paths(spec)
            for key in ("item_model", "recipe"):
                path = paths.get(key)
                if not path:
                    continue
                owner = (key, path)
                signature = json.dumps(
                    {"namespace": spec.get("namespace"), "item_id": spec.get("item_id"), "recipe_id": spec.get("recipe_id"), "expected": spec.get("expected_output_id")},
                    sort_keys=True,
                )
                previous = resource_claims.get(owner)
                if previous is not None and previous != signature:
                    violations.append(_profile_violation("VERTICAL_B_RESOURCE_PATH_CONFLICT", path, "incompatible Vertical B resource owners claim the same path", observed=signature, expected=previous))
                resource_claims[owner] = signature

        status = ValidationStatus.PASS if not violations else ValidationStatus.REPAIRABLE_FAIL
        summary = "pre-build requirements passed" if not violations else "pre-build requirements failed"
        return ValidationResult(
            stage=ValidationStage.PRE_BUILD,
            status=status,
            summary=summary,
            violations=tuple(violations),
            evidence_refs=tuple(dict.fromkeys(ref for violation in violations for ref in violation.evidence_refs)),
        )
