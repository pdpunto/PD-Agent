"""Filesystem tools for PD Agent L3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from pd_agent.core import (
    FileExistsToolValidationError,
    Tool,
    ToolExecutionError,
    ToolResult,
    ToolResultStatus,
    ToolValidationError,
)

from .context import ToolExecutionContext
from .security import SecurePathResolver


def _schema(
    properties: Mapping[str, Any],
    required: Sequence[str],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


def _utf8_prefix(text: str, limit_bytes: int) -> tuple[str, int]:
    if limit_bytes <= 0:
        return "", 0
    total = 0
    pieces: list[str] = []
    for char in text:
        char_size = len(char.encode("utf-8"))
        if total + char_size > limit_bytes:
            break
        pieces.append(char)
        total += char_size
    return "".join(pieces), total


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _sorted_entries(directory: Path) -> list[Path]:
    return sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name))


def _skip_search_path(path: Path) -> bool:
    noisy_names = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "build",
        "dist",
        "evidence",
        "runs",
    }
    return any(part in noisy_names for part in path.parts)


class ListDirectoryTool:
    name = "list_directory"
    description = "List directory contents within project_root. Missing directories are reported as an empty non-existent result."
    input_schema = _schema(
        {
            "path": {"type": "string", "minLength": 1},
        },
        ["path"],
    )

    def execute(self, context: ToolExecutionContext, arguments: Mapping[str, Any]) -> ToolResult:
        resolver = SecurePathResolver(context.project_root)
        directory = resolver.resolve_relative(arguments["path"])
        relative_path = str(directory.relative_to(context.project_root))
        if not directory.exists():
            output = {
                "path": relative_path,
                "exists": False,
                "entries": [],
                "entry_count": 0,
                "truncated": False,
                "limit_bytes": context.limits.max_tool_output_bytes,
            }
            return ToolResult(
                call_id=str(arguments["call_id"]),
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                output=output,
                metadata={"truncated": False, "exists": False},
            )
        if not directory.is_dir():
            raise ToolExecutionError(f"not a directory: {directory}")

        entries: list[dict[str, Any]] = []
        truncated = False
        for item in _sorted_entries(directory):
            entry = {
                "name": item.name,
                "path": str(item.relative_to(context.project_root)),
                "kind": "symlink"
                if item.is_symlink()
                else "directory"
                if item.is_dir()
                else "file",
            }
            if _json_size({"entries": entries + [entry]}) > context.limits.max_tool_output_bytes:
                truncated = True
                break
            entries.append(entry)

        output = {
            "path": relative_path,
            "exists": True,
            "entries": entries,
            "entry_count": len(entries),
            "truncated": truncated,
            "limit_bytes": context.limits.max_tool_output_bytes,
        }
        return ToolResult(
            call_id=str(arguments["call_id"]),
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            output=output,
            metadata={"truncated": truncated, "exists": True},
        )


class ReadFileTool:
    name = "read_file"
    description = "Read text file within project_root."
    input_schema = _schema(
        {
            "path": {"type": "string", "minLength": 1},
            "max_bytes": {"type": "integer", "minimum": 1},
        },
        ["path"],
    )

    def execute(self, context: ToolExecutionContext, arguments: Mapping[str, Any]) -> ToolResult:
        resolver = SecurePathResolver(context.project_root)
        file_path = resolver.resolve_existing_file(arguments["path"])
        raw = file_path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolExecutionError(f"binary file not supported: {file_path}") from exc

        limit_bytes = min(
            int(arguments.get("max_bytes", context.limits.max_tool_output_bytes)),
            context.limits.max_tool_output_bytes,
        )
        truncated = len(raw) > limit_bytes
        content, returned_bytes = (
            _utf8_prefix(text, limit_bytes) if truncated else (text, len(raw))
        )
        output = {
            "path": str(file_path.relative_to(context.project_root)),
            "content": content,
            "encoding": "utf-8",
            "bytes_total": len(raw),
            "bytes_returned": returned_bytes,
            "truncated": truncated,
            "limit_bytes": limit_bytes,
        }
        return ToolResult(
            call_id=str(arguments["call_id"]),
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            output=output,
            metadata={"truncated": truncated, "bytes_total": len(raw)},
        )


class SearchTextTool:
    name = "search_text"
    description = "Literal text search within project_root."
    input_schema = _schema(
        {
            "query": {"type": "string", "minLength": 1},
            "paths": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "max_results": {"type": "integer", "minimum": 1},
        },
        ["query"],
    )

    def execute(self, context: ToolExecutionContext, arguments: Mapping[str, Any]) -> ToolResult:
        resolver = SecurePathResolver(context.project_root)
        query = str(arguments["query"])
        max_results = int(arguments.get("max_results", 100))
        raw_paths = arguments.get("paths") or ["."]
        search_roots = [resolver.resolve_relative(raw_path) for raw_path in raw_paths]
        file_candidates: list[Path] = []
        for root in search_roots:
            if root.is_file():
                file_candidates.append(root)
            elif root.is_dir():
                file_candidates.extend(
                    sorted(
                        (
                            item
                            for item in root.rglob("*")
                            if item.is_file() and not _skip_search_path(item)
                        ),
                        key=lambda item: str(item.relative_to(context.project_root)).casefold(),
                    )
                )
            else:
                raise ToolExecutionError(f"search path is not readable: {root}")

        matches: list[dict[str, Any]] = []
        truncated = False
        for file_path in sorted(
            dict.fromkeys(file_candidates),
            key=lambda item: str(item.relative_to(context.project_root)).casefold(),
        ):
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ToolExecutionError(f"binary file not supported: {file_path}") from exc
            for line_number, line in enumerate(text.splitlines(), start=1):
                column = line.find(query)
                if column < 0:
                    continue
                match = {
                    "path": str(file_path.relative_to(context.project_root)),
                    "line": line_number,
                    "column": column + 1,
                    "text": line,
                }
                if _json_size({"matches": matches + [match]}) > context.limits.max_tool_output_bytes:
                    truncated = True
                    break
                matches.append(match)
                if len(matches) >= max_results:
                    truncated = True
                    break
            if truncated:
                break

        output = {
            "query": query,
            "paths": [str(path.relative_to(context.project_root)) for path in search_roots],
            "matches": matches,
            "match_count": len(matches),
            "truncated": truncated,
            "limit_bytes": context.limits.max_tool_output_bytes,
            "limit_results": max_results,
        }
        return ToolResult(
            call_id=str(arguments["call_id"]),
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            output=output,
            metadata={"truncated": truncated, "match_count": len(matches)},
        )


class WriteFileTool:
    name = "write_file"
    description = "Modify or replace an existing text file."
    input_schema = _schema(
        {
            "path": {"type": "string", "minLength": 1},
            "content": {"type": "string"},
        },
        ["path", "content"],
    )

    def execute(self, context: ToolExecutionContext, arguments: Mapping[str, Any]) -> ToolResult:
        resolver = SecurePathResolver(context.project_root)
        target = resolver.resolve_existing_file(arguments["path"])
        resolver.reject_protected_mutation(target)
        content = str(arguments["content"])
        if len(content.encode("utf-8")) > context.limits.max_tool_output_bytes:
            raise ToolValidationError("content too large")

        current = target.read_text(encoding="utf-8")
        changed = current != content
        if changed:
            target.write_text(content, encoding="utf-8", newline="\n")

        output = {
            "path": str(target.relative_to(context.project_root)),
            "changed": changed,
            "bytes_written": len(content.encode("utf-8")) if changed else 0,
        }
        return ToolResult(
            call_id=str(arguments["call_id"]),
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            output=output,
            metadata={"changed": changed, "path": str(target.relative_to(context.project_root))},
        )


class CreateFileTool:
    name = "create_file"
    description = "Create a new text file that does not already exist."
    input_schema = _schema(
        {
            "path": {"type": "string", "minLength": 1},
            "content": {"type": "string"},
        },
        ["path", "content"],
    )

    def execute(self, context: ToolExecutionContext, arguments: Mapping[str, Any]) -> ToolResult:
        resolver = SecurePathResolver(context.project_root)
        target, parent = resolver.resolve_parent_for_creation(arguments["path"])
        resolver.reject_protected_mutation(target)
        if target.exists():
            raise FileExistsToolValidationError(
                f"file already exists: {target}. create_file is only for new paths. use write_file to modify existing file."
            )
        content = str(arguments["content"])
        if len(content.encode("utf-8")) > context.limits.max_tool_output_bytes:
            raise ToolValidationError("content too large")
        parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        output = {
            "path": str(target.relative_to(context.project_root)),
            "changed": True,
            "bytes_written": len(content.encode("utf-8")),
        }
        return ToolResult(
            call_id=str(arguments["call_id"]),
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            output=output,
            metadata={"changed": True, "path": str(target.relative_to(context.project_root))},
        )


class DeleteFileTool:
    name = "delete_file"
    description = "Delete file within project_root."
    input_schema = _schema(
        {
            "path": {"type": "string", "minLength": 1},
        },
        ["path"],
    )

    def execute(self, context: ToolExecutionContext, arguments: Mapping[str, Any]) -> ToolResult:
        resolver = SecurePathResolver(context.project_root)
        target = resolver.resolve_relative(arguments["path"])
        if target == context.project_root:
            raise ToolValidationError("project_root cannot be deleted")
        if not target.exists():
            raise ToolValidationError(f"path does not exist: {target}")
        if not target.is_file():
            raise ToolExecutionError(f"not a file: {target}")
        resolver.reject_protected_mutation(target, delete=True)
        target.unlink()
        output = {
            "path": str(target.relative_to(context.project_root)),
            "changed": True,
        }
        return ToolResult(
            call_id=str(arguments["call_id"]),
            tool_name=self.name,
            status=ToolResultStatus.SUCCESS,
            output=output,
            metadata={"changed": True, "path": str(target.relative_to(context.project_root))},
        )


def create_filesystem_tools() -> tuple[Tool, ...]:
    return (
        ListDirectoryTool(),
        ReadFileTool(),
        SearchTextTool(),
        WriteFileTool(),
        CreateFileTool(),
        DeleteFileTool(),
    )
