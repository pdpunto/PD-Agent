"""Tool execution and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from pd_agent.core import (
    SecurityViolation,
    Tool,
    ToolCall,
    ToolExecutionError,
    ToolResult,
    ToolResultStatus,
    ToolValidationError,
)
from pd_agent.reporting.events import RunEvent, RunEventType

from .context import ToolExecutionContext


class EventSink(Protocol):
    def append(self, event: RunEvent) -> Any:
        """Append run event."""


def _type_name(value: Any) -> str:
    return type(value).__name__


class SchemaValidator:
    """Very small JSON-schema subset validator."""

    def validate(self, schema: Mapping[str, Any], data: Mapping[str, Any]) -> None:
        self._validate_node(schema, data, path="$")

    def _validate_node(self, schema: Mapping[str, Any], value: Any, *, path: str) -> None:
        schema_type = schema.get("type")
        if schema_type == "object":
            self._validate_object(schema, value, path=path)
        elif schema_type == "array":
            self._validate_array(schema, value, path=path)
        elif schema_type == "string":
            self._validate_string(schema, value, path=path)
        elif schema_type == "integer":
            self._validate_integer(schema, value, path=path)
        elif schema_type == "boolean":
            if not isinstance(value, bool):
                raise ToolValidationError(f"{path} must be boolean")
        elif schema_type is None:
            return
        else:
            raise ToolValidationError(f"unsupported schema type: {schema_type!r}")

        enum_values = schema.get("enum")
        if enum_values is not None and value not in enum_values:
            raise ToolValidationError(f"{path} must be one of {list(enum_values)!r}")

    def _validate_object(self, schema: Mapping[str, Any], value: Any, *, path: str) -> None:
        if not isinstance(value, Mapping):
            raise ToolValidationError(f"{path} must be object, got {_type_name(value)}")
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        additional = schema.get("additionalProperties", True)

        missing = [name for name in required if name not in value]
        if missing:
            raise ToolValidationError(f"{path} missing required field(s): {missing}")

        if not additional:
            unknown = [name for name in value if name not in properties]
            if unknown:
                raise ToolValidationError(f"{path} contains unknown field(s): {unknown}")

        for name, child_schema in properties.items():
            if name in value:
                self._validate_node(child_schema, value[name], path=f"{path}.{name}")

    def _validate_array(self, schema: Mapping[str, Any], value: Any, *, path: str) -> None:
        if not isinstance(value, list):
            raise ToolValidationError(f"{path} must be array, got {_type_name(value)}")
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < min_items:
            raise ToolValidationError(f"{path} requires at least {min_items} item(s)")
        if max_items is not None and len(value) > max_items:
            raise ToolValidationError(f"{path} allows at most {max_items} item(s)")
        child_schema = schema.get("items")
        if child_schema is not None:
            for index, item in enumerate(value):
                self._validate_node(child_schema, item, path=f"{path}[{index}]")

    def _validate_string(self, schema: Mapping[str, Any], value: Any, *, path: str) -> None:
        if not isinstance(value, str):
            raise ToolValidationError(f"{path} must be string, got {_type_name(value)}")
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if min_length is not None and len(value) < min_length:
            raise ToolValidationError(f"{path} requires at least {min_length} character(s)")
        if max_length is not None and len(value) > max_length:
            raise ToolValidationError(f"{path} allows at most {max_length} character(s)")

    def _validate_integer(self, schema: Mapping[str, Any], value: Any, *, path: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ToolValidationError(f"{path} must be integer, got {_type_name(value)}")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise ToolValidationError(f"{path} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise ToolValidationError(f"{path} must be <= {maximum}")


@dataclass(slots=True)
class ToolExecutor:
    """Register, validate and run tools under the security boundary."""

    event_sink: EventSink | None = None
    tools: tuple[Tool, ...] = ()
    _tools: dict[str, Tool] = field(init=False, repr=False)
    _validator: SchemaValidator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_tools", {})
        object.__setattr__(self, "_validator", SchemaValidator())
        for tool in self.tools:
            self.register_tool(tool)

    def register_tool(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolValidationError(f"duplicate tool registered: {tool.name}")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolValidationError(f"unknown tool: {name}") from exc

    def execute(self, call: ToolCall, context: ToolExecutionContext) -> ToolResult:
        self._emit(context, RunEventType.TOOL_REQUESTED, call.to_dict())
        try:
            tool = self.get_tool(call.tool_name)
            arguments = self._validate_arguments(tool, call.arguments)
            result = tool.execute(context, {**arguments, "call_id": call.call_id})
            self._emit(
                context,
                RunEventType.TOOL_EXECUTED,
                {
                    "call": call.to_dict(),
                    "result": result.to_dict(),
                },
            )
            if result.status == ToolResultStatus.SUCCESS and result.metadata.get("changed"):
                self._emit(
                    context,
                    RunEventType.FILE_CHANGED,
                    {
                        "call_id": call.call_id,
                        "tool_name": call.tool_name,
                        "output": result.output,
                    },
                )
            return result
        except (ToolValidationError, SecurityViolation) as exc:
            rejection_metadata = self._rejection_metadata(exc)
            self._emit(
                context,
                RunEventType.TOOL_REJECTED,
                {
                    "call": call.to_dict(),
                    "reason": str(exc),
                    **rejection_metadata,
                },
            )
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=ToolResultStatus.REJECTED,
                error=str(exc),
                metadata=rejection_metadata,
            )
        except ToolExecutionError as exc:
            result = ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=ToolResultStatus.ERROR,
                error=str(exc),
            )
            self._emit(
                context,
                RunEventType.TOOL_EXECUTED,
                {"call": call.to_dict(), "result": result.to_dict()},
            )
            return result
        except Exception as exc:  # pragma: no cover - defensive guard
            result = ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=ToolResultStatus.ERROR,
                error=f"{type(exc).__name__}: {exc}",
            )
            self._emit(
                context,
                RunEventType.TOOL_EXECUTED,
                {"call": call.to_dict(), "result": result.to_dict()},
            )
            return result

    def _validate_arguments(self, tool: Tool, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ToolValidationError("arguments must be an object")
        self._validator.validate(tool.input_schema, arguments)
        return dict(arguments)

    def _emit(self, context: ToolExecutionContext, event_type: RunEventType, payload: Mapping[str, Any]) -> None:
        if self.event_sink is None or context.run_id is None:
            return
        self.event_sink.append(
            RunEvent(
                run_id=context.run_id,
                event_type=event_type,
                payload=dict(payload),
            )
        )

    @staticmethod
    def _rejection_metadata(exc: Exception) -> dict[str, Any]:
        rejection_code = getattr(exc, "rejection_code", None)
        recoverable = bool(getattr(exc, "recoverable", False))
        metadata: dict[str, Any] = {"recoverable": recoverable}
        if rejection_code is not None:
            metadata["rejection_code"] = str(rejection_code)
        return metadata


def build_tool_executor(
    *,
    event_sink: EventSink | None = None,
    tools: tuple[Tool, ...] = (),
) -> ToolExecutor:
    """Convenience builder for L3 tests and bootstraps."""

    return ToolExecutor(event_sink=event_sink, tools=tools)
