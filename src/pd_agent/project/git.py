"""Read-only git baseline inspection."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import GitBaseline, GitDiffSnapshot


@dataclass(frozen=True, slots=True)
class GitInspector:
    """Read git metadata without mutating repo."""

    project_root: Path

    def inspect(self) -> GitBaseline:
        root = self.project_root.resolve(strict=True)
        if not root.exists():
            raise FileNotFoundError(root)

        if not self._is_git_repo(root):
            return GitBaseline(present=False, repo_root=None, error="not a git repository")

        repo_root = self._git_text(root, ["rev-parse", "--show-toplevel"]).strip()
        head = self._git_optional(root, ["rev-parse", "HEAD"])
        branch = self._git_optional(root, ["symbolic-ref", "--short", "HEAD"])
        status_text = self._git_text(root, ["status", "--porcelain=v1"])
        diff_text = self._git_text(root, ["diff", "--no-ext-diff", "--no-color"])
        cached_diff_text = self._git_text(
            root, ["diff", "--cached", "--no-ext-diff", "--no-color"]
        )

        status_lines = tuple(line for line in status_text.splitlines() if line.strip())
        return GitBaseline(
            present=True,
            repo_root=Path(repo_root),
            head=head.strip() if head else None,
            branch=branch.strip() if branch else None,
            status_porcelain=status_lines,
            diff=GitDiffSnapshot(
                text=diff_text,
                truncated=False,
                line_count=len(diff_text.splitlines()),
            ),
            cached_diff=GitDiffSnapshot(
                text=cached_diff_text,
                truncated=False,
                line_count=len(cached_diff_text.splitlines()),
            ),
            working_tree_clean=not status_lines,
        )

    def _is_git_repo(self, root: Path) -> bool:
        proc = self._run_git(root, ["rev-parse", "--is-inside-work-tree"])
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _git_optional(self, root: Path, args: list[str]) -> str | None:
        proc = self._run_git(root, args)
        if proc.returncode != 0:
            return None
        return proc.stdout

    def _git_text(self, root: Path, args: list[str]) -> str:
        proc = self._run_git(root, args)
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
        return proc.stdout

    def _run_git(self, root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
        )

