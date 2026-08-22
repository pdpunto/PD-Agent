"""Canonical mutation paths derived from inspected project layout."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from .models import ProjectSnapshot


class MutationPathResolutionError(ValueError):
    """Raised when a logical resource path cannot be resolved safely."""


def resolve_logical_resource_path(snapshot: ProjectSnapshot, logical_path: str) -> str:
    """Resolve a logical JAR resource path to a physical project-relative path."""

    raw = str(logical_path).strip()
    logical = PurePosixPath(raw)
    if (
        not raw
        or logical.is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or any(part in {"", ".", ".."} for part in logical.parts)
        or "\\" in raw
    ):
        raise MutationPathResolutionError(f"invalid logical resource path: {logical_path!r}")

    project_root = snapshot.project_root.resolve(strict=False)
    roots = _candidate_resource_roots(snapshot, project_root)
    if not roots:
        raise MutationPathResolutionError("project has no resource root")

    candidates = [(root / Path(*logical.parts)).resolve(strict=False) for root in roots]
    contained = [candidate for candidate in candidates if _within(candidate, project_root)]
    if len(contained) != len(candidates):
        raise MutationPathResolutionError("resolved resource path escapes project_root")
    if len(contained) != 1:
        raise MutationPathResolutionError("logical resource path has ambiguous resource roots")

    return contained[0].relative_to(project_root).as_posix()


def _candidate_resource_roots(snapshot: ProjectSnapshot, project_root: Path) -> tuple[Path, ...]:
    roots = tuple(
        sorted(
            {
                root.resolve(strict=False)
                for root in snapshot.resource_roots
                if _within(root.resolve(strict=False), project_root)
            },
            key=lambda path: path.as_posix().casefold(),
        )
    )
    if snapshot.target_subproject is None:
        return roots

    target_subproject = snapshot.target_subproject.resolve(strict=False)
    scoped = tuple(root for root in roots if _within(root, target_subproject))
    return scoped or roots


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = ["MutationPathResolutionError", "resolve_logical_resource_path"]
