"""Fail-closed product delivery for validated runtime artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import os
import subprocess

from pd_agent.core import RunStatus, ToolValidationError, artifact_identity_from_result, compute_source_revision
from pd_agent.pass_policy import evaluate_pass
from pd_agent.reporting import RunStorage
from pd_agent.tools import SecurePathResolver
from pd_agent.validation import CompletionGate

from .catalog import CatalogError, ProductCatalog
from .models import DeliveryRecord, ExecutionRecord


class DeliveryError(ValueError):
    """Safe product error suitable for later HTTP mapping."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class DeliveryArtifact:
    """Trusted descriptor returned after all delivery checks pass."""

    delivery_id: str
    filename: str
    path: Path
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class RevealAction:
    """Platform command metadata; execution is deliberately explicit."""

    delivery_id: str
    command: tuple[str, ...]
    target: Path


class DeliveryService:
    """Create and resolve deliveries from trusted catalog/runtime authorities."""

    def __init__(self, catalog: ProductCatalog, storage: RunStorage, completion_gate: CompletionGate | None = None) -> None:
        self.catalog = catalog
        self.storage = storage
        self.completion_gate = completion_gate or CompletionGate()

    def create(self, execution_id: str) -> DeliveryRecord:
        execution, project_id, task_id = self._ownership(execution_id)
        artifact = self._validated_artifact(execution, project_id, task_id)
        reference = self._reference(artifact.path, self.catalog.get_project(project_id).workspace_ref)
        delivery = DeliveryRecord(
            project_id=project_id,
            task_id=task_id,
            execution_id=execution.execution_id,
            artifact_sha256=artifact.sha256,
            artifact_ref=reference,
        )
        try:
            return self.catalog.add_delivery(delivery)
        except CatalogError as exc:
            raise DeliveryError(exc.code, "delivery could not be persisted") from exc

    create_delivery = create

    def get(self, delivery_id: str) -> DeliveryRecord:
        try:
            delivery = self.catalog.get_delivery(delivery_id)
        except CatalogError as exc:
            if exc.code == "DELIVERY_NOT_FOUND":
                raise DeliveryError("DELIVERY_NOT_FOUND", "delivery was not found") from exc
            raise DeliveryError("DELIVERY_INVALID", "delivery metadata is invalid") from exc
        self._validated_artifact_for_delivery(delivery)
        return delivery

    def resolve(self, delivery_id: str) -> DeliveryArtifact:
        delivery = self.get(delivery_id)
        artifact = self._validated_artifact_for_delivery(delivery)
        path = artifact.path.resolve(strict=True)
        return DeliveryArtifact(delivery.delivery_id, path.name, path, delivery.artifact_sha256, path.stat().st_size)

    download = resolve

    def reveal(self, delivery_id: str) -> RevealAction:
        artifact = self.resolve(delivery_id)
        # Explorer receives a fixed argument vector, never caller-controlled text.
        if os.name == "nt":
            command = ("explorer.exe", "/select,", str(artifact.path))
        else:
            command = ("open", str(artifact.path.parent)) if sys_platform_is_darwin() else ("xdg-open", str(artifact.path.parent))
        return RevealAction(delivery_id, command, artifact.path)

    def execute_reveal(self, delivery_id: str) -> RevealAction:
        """Perform the already validated reveal action without a shell."""
        action = self.reveal(delivery_id)
        try:
            subprocess.Popen(action.command, shell=False)  # noqa: S603
        except OSError as exc:
            raise DeliveryError("REVEAL_FAILED", "artifact reveal could not be started") from exc
        return action

    def _ownership(self, execution_id: str) -> tuple[ExecutionRecord, str, str]:
        try:
            execution = self.catalog.get_execution(execution_id)
            task = self.catalog.get_task(execution.task_id)
            project = self.catalog.get_project(task.project_id)
        except CatalogError as exc:
            raise DeliveryError("OWNERSHIP_INVALID", "delivery ownership is invalid") from exc
        if task.project_id != project.project_id or execution.task_id != task.task_id or execution.execution_id != execution_id:
            raise DeliveryError("OWNERSHIP_INVALID", "delivery ownership is invalid")
        return execution, project.project_id, task.task_id

    def _validated_artifact(self, execution: ExecutionRecord, project_id: str, task_id: str):
        try:
            state = self.storage.read_run_state(execution.run_id)
            report = self.storage.read_final_report(execution.run_id)
        except Exception as exc:
            raise DeliveryError("ARTIFACT_UNAVAILABLE", "authoritative runtime evidence is unavailable") from exc
        if state.run_id != execution.run_id or report.run_id != execution.run_id or state.state is not RunStatus.COMPLETED:
            raise DeliveryError("COMPLETION_REQUIRED", "execution did not complete authoritatively")
        evaluation = evaluate_pass(self.storage, execution.run_id)
        if not evaluation.passed:
            raise DeliveryError("COMPLETION_REQUIRED", "authoritative completion was not satisfied")
        contract = state.task_contract
        if contract is None or contract.task_id != task_id:
            raise DeliveryError("COMPLETION_REQUIRED", "completion contract is unavailable")
        completion = self.completion_gate.evaluate(contract, state.progress_ledger, state)
        if not completion.complete:
            raise DeliveryError("COMPLETION_REQUIRED", "completion gate was not satisfied")
        artifact = state.artifact_result
        identity = state.artifact_identity
        if artifact is None or identity is None or artifact.classification != "VALID" or artifact.path is None:
            raise DeliveryError("ARTIFACT_NOT_CURRENT", "artifact is not valid and current")
        if report.artifact is None or report.artifact.to_dict() != artifact.to_dict():
            raise DeliveryError("ARTIFACT_NOT_CURRENT", "artifact evidence does not match runtime state")
        build = next((item for item in reversed(state.build_identities) if item.build_attempt_id == identity.producing_build_attempt_id), None)
        # Recompute at use time so source edits cannot leave an old delivery usable.
        source = self._source_revision(state.project_root)
        if build is None or source is None or not identity.is_current(build, source_revision=source, contract_identity=contract.identity()):
            raise DeliveryError("ARTIFACT_NOT_CURRENT", "artifact currentness is not established")
        try:
            path = self._confined_path(artifact.path, self.catalog.get_project(project_id).workspace_ref)
            digest = _sha256(path)
        except DeliveryError:
            raise
        except (OSError, ValueError, ToolValidationError) as exc:
            raise DeliveryError("ARTIFACT_UNAVAILABLE", "artifact is unavailable") from exc
        if digest != identity.sha256.lower() or digest != artifact_identity_from_result(artifact, producing_build_attempt_id=identity.producing_build_attempt_id, source_revision=source, contract_identity=contract.identity()).sha256 or digest != identity.artifact_identity.lower():
            raise DeliveryError("ARTIFACT_NOT_CURRENT", "artifact identity does not match")
        return _ValidatedArtifact(path, digest)

    def _validated_artifact_for_delivery(self, delivery: DeliveryRecord) -> _ValidatedArtifact:
        execution, project_id, task_id = self._ownership(delivery.execution_id)
        if delivery.project_id != project_id or delivery.task_id != task_id:
            raise DeliveryError("OWNERSHIP_INVALID", "delivery ownership is invalid")
        artifact = self._validated_artifact(execution, project_id, task_id)
        try:
            reference = self._reference(artifact.path, self.catalog.get_project(project_id).workspace_ref)
        except (ValueError, DeliveryError) as exc:
            raise DeliveryError("SECURITY_REJECTED", "artifact reference is invalid") from exc
        if delivery.artifact_ref != reference or delivery.artifact_sha256 != artifact.sha256:
            raise DeliveryError("SECURITY_REJECTED", "delivery metadata does not match authoritative artifact")
        return artifact

    def _confined_path(self, path: Path, workspace: str) -> Path:
        resolver = SecurePathResolver(Path(workspace))
        try:
            relative = Path(path).resolve(strict=False).relative_to(resolver.project_root)
        except ValueError as exc:
            raise DeliveryError("SECURITY_REJECTED", "artifact is outside the trusted workspace") from exc
        return resolver.resolve_existing_file(relative)

    def _reference(self, path: Path | None, workspace: str) -> str:
        if path is None:
            raise ValueError("artifact path is required")
        physical = self._confined_path(path, workspace)
        relative = physical.relative_to(Path(workspace).resolve(strict=True)).as_posix()
        parsed = PurePosixPath(relative)
        if parsed.is_absolute() or ".." in parsed.parts or not relative or "\\" in relative:
            raise ValueError("artifact reference is unsafe")
        return relative

    @staticmethod
    def _source_revision(project_root: Path | None) -> str | None:
        if project_root is None:
            return None
        try:
            return compute_source_revision(project_root).revision
        except (OSError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class _ValidatedArtifact:
    path: Path
    sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sys_platform_is_darwin() -> bool:
    return os.sys.platform == "darwin"


__all__ = ["DeliveryArtifact", "DeliveryError", "DeliveryService", "RevealAction"]
