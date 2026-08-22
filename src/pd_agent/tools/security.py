"""Filesystem security boundary for PD Agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pd_agent.core import SecurityViolation, ToolExecutionError, ToolValidationError


MAX_RELATIVE_PATH_LENGTH = 4_096
PROTECTED_NAMES = {".git", "gradlew", "gradlew.bat"}


def _contains_protected_name(path: Path) -> bool:
    return any(part in PROTECTED_NAMES for part in path.parts)


def _is_absolute_external(path: Path) -> bool:
    return path.is_absolute() or path.drive != "" or path.anchor != ""


@dataclass(frozen=True, slots=True)
class SecurePathResolver:
    """Resolve tool paths against project_root with ancestry checks."""

    project_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", self.project_root.resolve(strict=True))
        if not self.project_root.is_dir():
            raise SecurityViolation("project_root must be an existing directory")

    def resolve_relative(self, raw_path: object) -> Path:
        if raw_path is None:
            raise ToolValidationError("path is required")
        if not isinstance(raw_path, (str, Path)):
            raise ToolValidationError("path must be a string")

        candidate = Path(raw_path)
        if not str(candidate):
            raise ToolValidationError("path is required")
        if len(str(candidate)) > MAX_RELATIVE_PATH_LENGTH:
            raise ToolValidationError("path too long")
        if _is_absolute_external(candidate):
            raise SecurityViolation("absolute paths are not allowed")

        resolved = (self.project_root / candidate).resolve(strict=False)
        if not self._is_within_root(resolved):
            raise SecurityViolation("path escapes project_root")
        return resolved

    def resolve_existing_file(self, raw_path: object) -> Path:
        target = self.resolve_relative(raw_path)
        if not target.exists():
            raise ToolValidationError(f"path does not exist: {raw_path!r}")
        if not target.is_file():
            raise ToolExecutionError(f"not a file: {raw_path!r}")
        return target

    def resolve_existing_directory(self, raw_path: object) -> Path:
        target = self.resolve_relative(raw_path)
        if not target.exists():
            raise ToolValidationError(f"path does not exist: {raw_path!r}")
        if not target.is_dir():
            raise ToolExecutionError(f"not a directory: {raw_path!r}")
        return target

    def resolve_parent_for_creation(self, raw_path: object) -> tuple[Path, Path]:
        target = self.resolve_relative(raw_path)
        parent = target.parent
        if parent.exists() and not parent.is_dir():
            raise ToolExecutionError(f"parent is not a directory: {parent}")
        if not self._is_within_root(parent.resolve(strict=False)):
            raise SecurityViolation("parent escapes project_root")
        return target, parent

    def reject_protected_mutation(self, target: Path, *, delete: bool = False) -> None:
        if target == self.project_root and delete:
            raise SecurityViolation("project_root cannot be deleted")
        if _contains_protected_name(target.relative_to(self.project_root)):
            raise SecurityViolation("protected path cannot be modified")

    def _is_within_root(self, target: Path) -> bool:
        try:
            target.relative_to(self.project_root)
        except ValueError:
            return False
        return True
