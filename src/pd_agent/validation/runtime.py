"""Product-owned functional validation boundary for normal Fabric runs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from pd_agent.artifacts import ArtifactClassification
from pd_agent.core import (
    ArtifactResult,
    BuildAttemptIdentity,
    FabricTaskContract,
    RunState,
    SourceRevision,
    ValidationResult,
    ValidationStage,
    ValidationStatus,
    ValidationViolation,
    SecurityViolation,
    artifact_identity_from_result,
    compute_source_revision,
)
from pd_agent.minecraft import (
    FabricRuntimeOrchestrator,
    MinecraftObservationType,
    MinecraftTestRunner,
    MinecraftTestSpec,
    runtime_spec_from_requirement,
)
from pd_agent.tools import SecurePathResolver


def _runtime_requirement(contract: FabricTaskContract) -> Any | None:
    return next(
        (
            item
            for item in contract.validation_requirements
            if item.required and item.kind in {"runtime", "minecraft", "observation"}
        ),
        None,
    )


def _artifact_reference(project_root: Path, artifact_path: Path) -> Path:
    """Convert an internal physical artifact path to a confined reference."""

    resolver = SecurePathResolver(Path(project_root))
    raw_path = Path(artifact_path)
    if raw_path.is_absolute() or raw_path.drive or raw_path.anchor:
        physical_path = raw_path.resolve(strict=False)
        try:
            relative_path = physical_path.relative_to(resolver.project_root)
        except ValueError as exc:
            raise SecurityViolation("artifact path escapes project_root") from exc
    else:
        relative_path = raw_path
    resolver.resolve_existing_file(relative_path)
    return relative_path


def _minecraft_spec(
    project_root: Path,
    contract: FabricTaskContract,
    requirement: Any,
    artifact: ArtifactResult,
    *,
    runtime_mod_jars: tuple[Path, ...] = (),
) -> MinecraftTestSpec:
    spec = dict(requirement.spec)
    environment = contract.environment_constraints
    target_mod_id = spec.get("target_mod_id")
    if not isinstance(target_mod_id, str) or not target_mod_id.strip():
        raise ValueError("runtime validation spec requires target_mod_id")
    return MinecraftTestSpec(
        target_jar=_artifact_reference(project_root, Path(artifact.path)) if artifact.path is not None else Path("."),
        runtime_mod_jars=tuple(Path(item) for item in spec.get("runtime_mod_jars", runtime_mod_jars)),
        observation_requests=runtime_spec_from_requirement(requirement).observations,
        target_mod_id=target_mod_id,
        minecraft_version=str(spec.get("minecraft_version", environment.minecraft_version)),
        loader_version=str(spec.get("loader_version", environment.loader_version)),
        test_id=str(spec.get("test_id", requirement.validation_requirement_id)),
        timeout_seconds=int(spec.get("timeout_seconds", 600)),
        observation_type=MinecraftObservationType(str(spec.get("observation_type", MinecraftObservationType.LEGACY_BLOCK_STATE))),
        observation_params=dict(spec.get("observation_params", {})),
        expect_neighbor_update=bool(spec.get("expect_neighbor_update", False)),
    )


@dataclass(slots=True)
class ProductiveMinecraftFunctionalValidator:
    """Adapt the generic functional-validator port to the runtime boundary."""

    contract: FabricTaskContract
    runner: MinecraftTestRunner
    runtime_root_factory: Callable[[str], Path] | None = None
    last_results: tuple[ValidationResult, ...] = ()
    last_runtime_result: Any | None = None
    _run_state: RunState | None = None
    gradle_user_home: Path | None = None

    def bind_run_state(self, run_state: RunState) -> None:
        self._run_state = run_state

    def validate(self, project_root: Path, artifact: ArtifactResult, contract: Any, run_id: str) -> ValidationResult:
        del contract
        requirement = _runtime_requirement(self.contract)
        if requirement is None:
            result = ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.PASS, summary="runtime validation not required")
            self.last_results = (result,)
            return result
        if artifact.classification != ArtifactClassification.VALID.value or artifact.path is None:
            result = ValidationResult(
                stage=ValidationStage.RUNTIME,
                status=ValidationStatus.BLOCKED,
                summary="runtime validation requires a valid artifact",
                violations=(ValidationViolation(
                    code="RUNTIME_ARTIFACT_NOT_CURRENT",
                    requirement=requirement.validation_requirement_id,
                    observed={"classification": artifact.classification},
                    expected=ArtifactClassification.VALID.value,
                    message="Minecraft runner was not invoked for an invalid artifact",
                    phase="RUNTIME",
                ),),
            )
            self.last_results = (result,)
            return result
        if self._run_state is None:
            raise RuntimeError("productive runtime validator must be bound to RunState")

        source = compute_source_revision(Path(project_root)).revision
        build_result = self._run_state.build_results[-1] if self._run_state.build_results else None
        if build_result is None:
            result = ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.BLOCKED, summary="runtime validation requires a recorded build")
            self.last_results = (result,)
            return result
        contract_identity = self.contract.identity()
        build_identity = next(
            (item for item in reversed(self._run_state.build_identities) if item.result_ref == f"builds/{build_result.attempt}"),
            None,
        )
        if build_identity is None:
            build_identity = BuildAttemptIdentity(
                build_attempt_id=f"normal-build-{run_id}-{build_result.attempt}",
                source_revision=source,
                contract_identity=contract_identity,
                result_ref=f"builds/{build_result.attempt}",
                success=build_result.success,
            )
            self._run_state.build_identities = (*self._run_state.build_identities, build_identity)
        artifact_identity = artifact_identity_from_result(
            artifact,
            producing_build_attempt_id=build_identity.build_attempt_id,
            source_revision=source,
            contract_identity=contract_identity,
        )
        self._run_state.source_revision = SourceRevision(source)
        # A successful repair produces a new validated artifact. Publish it as
        # current before runtime validation while retaining prior runtime facts.
        self._run_state.artifact_identity = artifact_identity
        runtime_mod_jars: tuple[Path, ...] = ()
        if self.gradle_user_home is not None:
            try:
                from pd_agent.benchmark.dependencies import (
                    RuntimeModDependencyResolutionError,
                    resolve_runtime_mod_dependencies,
                )
                dependencies = resolve_runtime_mod_dependencies(
                    project_root,
                    gradle_user_home=self.gradle_user_home,
                )
            except RuntimeModDependencyResolutionError as exc:
                result = ValidationResult(
                    stage=ValidationStage.RUNTIME,
                    status=ValidationStatus.BLOCKED,
                    summary="runtime dependencies could not be resolved",
                    violations=(ValidationViolation(
                        code="RUNTIME_DEPENDENCY_UNAVAILABLE",
                        requirement=requirement.validation_requirement_id,
                        observed={"error": str(exc)},
                        expected="all declared runtime mod dependencies are available",
                        actual=str(exc),
                        message="Minecraft runner was not invoked because a runtime dependency is unavailable",
                        phase="RUNTIME",
                    ),),
                )
                self.last_results = (result,)
                return result
            runtime_mod_jars = tuple(item.path for item in dependencies)
        spec = _minecraft_spec(
            project_root,
            self.contract,
            requirement,
            artifact,
            runtime_mod_jars=runtime_mod_jars,
        )
        runtime_root = self.runtime_root_factory(run_id) if self.runtime_root_factory is not None else None
        outcome = FabricRuntimeOrchestrator(self.runner).validate(
            contract=self.contract,
            run_state=self._run_state,
            artifact=artifact_identity,
            source_revision=source,
            minecraft_spec=spec,
            runtime_root=runtime_root,
            java_version=self.contract.environment_constraints.java_version,
            authorized_runtime_roots=(
                (Path(project_root), self.gradle_user_home)
                if self.gradle_user_home is not None
                else (Path(project_root),)
            ),
        )
        self.last_runtime_result = outcome.runtime_result
        result = outcome.validation_result or ValidationResult(stage=ValidationStage.RUNTIME, status=ValidationStatus.BLOCKED, summary="runtime validation did not produce a result")
        if result.status is ValidationStatus.PASS and self._run_state.progress_ledger is not None:
            requirement_ids = tuple(dict.fromkeys(requirement.requirement_ids))
            ledger = self._run_state.progress_ledger
            satisfied = tuple(dict.fromkeys((*ledger.satisfied_requirement_ids, *requirement_ids)))
            self._run_state.progress_ledger = replace(ledger, satisfied_requirement_ids=satisfied)
            if outcome.runtime_identity is not None:
                from pd_agent.runtime.repair import FailureReconciler

                reconciler = FailureReconciler()
                for failure in tuple(self._run_state.progress_ledger.failures):
                    if failure.status.value != "ACTIVE":
                        continue
                    if not set(failure.requirement_ids).intersection(requirement_ids):
                        continue
                    reconciler.reconcile_runtime(
                        self._run_state,
                        failure,
                        runtime=outcome,
                        artifact=artifact_identity,
                        requirement_ids=requirement_ids,
                        validation_revision=outcome.runtime_identity.validation_revision,
                    )
        self.last_results = (result,)
        return result


__all__ = ["ProductiveMinecraftFunctionalValidator"]
