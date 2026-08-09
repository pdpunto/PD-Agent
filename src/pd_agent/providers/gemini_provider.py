"""Gemini adapter for PD Agent v0.1.1."""

from __future__ import annotations

import json
from typing import Any, Mapping

from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ModelProvider, ToolCall, ToolResult
from pd_agent.core.errors import ConfigurationError, ProviderError
from pd_agent.reporting.redaction import Redactor, json_ready


class GeminiProvider(ModelProvider):
    """Translate PD Agent requests into Gemini SDK calls."""

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        provider_retry_limit: int = 2,
        client: Any | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if provider_retry_limit < 0:
            raise ValueError("provider_retry_limit must be non-negative")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.provider_retry_limit = provider_retry_limit
        self.redactor = redactor or Redactor((api_key,) if api_key else ())
        self._client = client or self._build_client()

    def __repr__(self) -> str:
        return (
            "GeminiProvider("
            f"model={self.model!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, "
            f"provider_retry_limit={self.provider_retry_limit!r}, "
            f"client={type(self._client).__name__}"
            ")"
        )

    def execute(self, request: AgentRequest) -> AgentResponse:
        model = self._effective_model(request)
        system_instruction, contents = self._build_contents(request)
        config = self._build_generate_config(
            tools=self._build_tools(request.tools),
            system_instruction=system_instruction,
        )
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:  # pragma: no cover - normalized boundary
            raise self._normalize_error(exc, model=model) from None
        return self._to_agent_response(response, model=model)

    def _build_client(self) -> Any:
        try:
            from google import genai
            from google.genai import types
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency path
            raise ConfigurationError("google-genai is required for GeminiProvider") from exc

        return genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(**self._client_http_options()),
        )

    def _client_http_options(self) -> dict[str, Any]:
        return {
            "timeout": int(self.timeout_seconds * 1000),
            "retry_options": {"attempts": self.provider_retry_limit + 1},
        }

    def _build_generate_config(self, *, tools: list[dict[str, Any]], system_instruction: str | None) -> dict[str, Any]:
        config: dict[str, Any] = {
            "automatic_function_calling": {"disable": True},
        }
        if tools:
            config["tools"] = tools
        if system_instruction:
            config["system_instruction"] = system_instruction
        return config

    def _build_tools(self, tools: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
        declarations = [self._tool_declaration(tool) for tool in tools]
        return [{"function_declarations": declarations}] if declarations else []

    def _tool_declaration(self, tool: Mapping[str, Any]) -> dict[str, Any]:
        name = str(tool.get("name", "")).strip()
        if not name:
            raise ProviderError(
                "Gemini tool declaration missing name",
                kind="protocol",
                provider="gemini",
            )
        schema = tool.get("input_schema", tool.get("parameters", {"type": "object"}))
        return {
            "name": name,
            "description": str(tool.get("description", "")),
            "parameters_json_schema": json_ready(schema),
        }

    def _effective_model(self, request: AgentRequest) -> str:
        config_model = request.model_config.get("model")
        model = config_model if config_model is not None else self.model
        if not model:
            raise ConfigurationError("GeminiProvider requires a model")
        return str(model)

    def _build_contents(self, request: AgentRequest) -> tuple[str | None, tuple[dict[str, Any], ...]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for message in request.messages:
            normalized_role = message.role.strip().lower()
            if normalized_role in {"system", "developer"}:
                if message.content:
                    system_parts.append(message.content)
                continue
            if normalized_role not in {"user", "assistant", "model"}:
                raise ProviderError(
                    f"Unsupported Gemini message role: {message.role!r}",
                    kind="protocol",
                    provider="gemini",
                    details={"role": message.role},
                )
            contents.append(
                {
                    "role": "model" if normalized_role in {"assistant", "model"} else "user",
                    "parts": [{"text": message.content}],
                }
            )

        if request.tool_calls:
            contents.append(
                {
                    "role": "model",
                    "parts": [self._function_call_part(call) for call in request.tool_calls],
                }
            )

        if request.tool_results:
            tool_name_by_call_id = {call.call_id: call.tool_name for call in request.tool_calls}
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        self._function_response_part(result, tool_name_by_call_id.get(result.call_id, result.tool_name))
                        for result in request.tool_results
                    ],
                }
            )

        system_instruction = "\n".join(system_parts) if system_parts else None
        return system_instruction, tuple(contents)

    def _function_call_part(self, call: ToolCall) -> dict[str, Any]:
        call_id = self._require_call_id(call.call_id)
        return {
            "function_call": {
                "id": call_id,
                "name": call.tool_name,
                "args": json_ready(call.arguments),
            }
        }

    def _function_response_part(self, result: ToolResult, tool_name: str) -> dict[str, Any]:
        call_id = self._require_call_id(result.call_id)
        response_payload: dict[str, Any] = {
            "output": json_ready(result.output),
            "status": result.status.value,
        }
        if result.error is not None:
            response_payload["error"] = result.error
        metadata = json_ready(dict(result.metadata))
        if metadata:
            response_payload["metadata"] = metadata
        return {
            "function_response": {
                "id": call_id,
                "name": tool_name,
                "response": response_payload,
            }
        }

    def _require_call_id(self, call_id: str) -> str:
        value = call_id.strip()
        if not value:
            raise ProviderError(
                "Gemini function call id is required",
                kind="protocol",
                provider="gemini",
                details={"error": "missing_call_id"},
            )
        return value

    def _to_agent_response(self, response: Any, *, model: str) -> AgentResponse:
        assistant_texts: list[str] = []
        tool_calls: list[ToolCall] = []

        for part in self._response_parts(response):
            text = self._part_text(part)
            if text:
                assistant_texts.append(text)
            function_call = self._part_function_call(part)
            if function_call is not None:
                tool_calls.append(function_call)

        if not assistant_texts:
            response_text = getattr(response, "text", None)
            if response_text:
                assistant_texts.append(str(response_text))

        usage = self._usage_from_response(response)
        provider_metadata = self._provider_metadata(response, model=model)
        return AgentResponse(
            assistant_message="\n".join(assistant_texts) if assistant_texts else None,
            tool_calls=tuple(tool_calls),
            usage=usage,
            provider_metadata=provider_metadata,
        )

    def _response_parts(self, response: Any) -> tuple[Any, ...]:
        candidates = getattr(response, "candidates", None) or ()
        parts: list[Any] = []
        candidate_has_function_call = False
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            candidate_parts = getattr(content, "parts", None) if content is not None else None
            if candidate_parts:
                parts.extend(candidate_parts)
                if any(self._part_function_call(part) is not None for part in candidate_parts):
                    candidate_has_function_call = True

        if not candidate_has_function_call:
            function_calls = getattr(response, "function_calls", None)
            if function_calls:
                parts.extend(function_calls)
        return tuple(parts)

    def _part_text(self, part: Any) -> str | None:
        value = self._part_value(part, "text")
        if value:
            return str(value)
        return None

    def _part_function_call(self, part: Any) -> ToolCall | None:
        function_call = self._part_value(part, "function_call")
        if function_call is None:
            function_call = self._part_value(part, "functionCall")
        if function_call is None:
            return None

        call_id = self._call_value(function_call, "id")
        if not call_id:
            raise ProviderError(
                "Gemini function_call missing id",
                kind="protocol",
                provider="gemini",
                details={"error": "missing_function_call_id"},
            )
        name = self._call_value(function_call, "name")
        if not name:
            raise ProviderError(
                "Gemini function_call missing name",
                kind="protocol",
                provider="gemini",
                details={"error": "missing_function_call_name"},
            )
        args = self._call_value(function_call, "args")
        if args is None:
            args = self._call_value(function_call, "arguments")
        return ToolCall(
            call_id=str(call_id),
            tool_name=str(name),
            arguments=self._parse_arguments(args),
        )

    def _parse_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if raw_arguments is None:
            return {}
        if isinstance(raw_arguments, Mapping):
            return dict(raw_arguments)
        if isinstance(raw_arguments, str):
            try:
                decoded = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    "Gemini function_call arguments are not valid JSON",
                    kind="protocol",
                    provider="gemini",
                    details={"error": "invalid_json"},
                ) from exc
            if not isinstance(decoded, dict):
                raise ProviderError(
                    "Gemini function_call arguments must decode to an object",
                    kind="protocol",
                    provider="gemini",
                    details={"error": "non_object_arguments", "type": type(decoded).__name__},
                )
            return decoded
        raise ProviderError(
            "Gemini function_call arguments must be an object",
            kind="protocol",
            provider="gemini",
            details={"error": "invalid_arguments_type", "type": type(raw_arguments).__name__},
        )

    def _usage_from_response(self, response: Any) -> dict[str, Any] | None:
        usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
        if usage is None:
            return None

        data = self._coerce_mapping(usage)
        result: dict[str, Any] = {}
        input_tokens = self._first_present(data, "prompt_token_count", "input_tokens", "input_token_count")
        output_tokens = self._first_present(
            data,
            "candidates_token_count",
            "output_tokens",
            "output_token_count",
            "response_token_count",
        )
        total_tokens = self._first_present(data, "total_token_count", "total_tokens")

        if input_tokens is not None:
            result["input_tokens"] = input_tokens
        if output_tokens is not None:
            result["output_tokens"] = output_tokens
        if total_tokens is not None:
            result["total_tokens"] = total_tokens

        for source_name in ("cached_content_token_count", "thoughts_token_count", "tool_use_prompt_token_count"):
            if source_name in data:
                result[source_name] = data[source_name]

        return result or None

    def _provider_metadata(self, response: Any, *, model: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "provider": "gemini",
            "model": getattr(response, "model", model),
            "response_id": getattr(response, "id", None),
        }
        finish_reason = self._first_present(
            self._coerce_mapping(getattr(response, "candidates", [{}])[0] if getattr(response, "candidates", None) else {}),
            "finish_reason",
            "finishReason",
        )
        if finish_reason is None:
            finish_reason = getattr(response, "finish_reason", None) or getattr(response, "finishReason", None)
        if finish_reason is not None:
            metadata["finish_reason"] = finish_reason
        return {key: value for key, value in metadata.items() if value is not None}

    def _coerce_mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if hasattr(value, "model_dump") and callable(value.model_dump):
            dumped = value.model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        if hasattr(value, "to_dict") and callable(value.to_dict):
            dumped = value.to_dict()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        if hasattr(value, "__dict__"):
            return {
                key: json_ready(item)
                for key, item in value.__dict__.items()
                if not key.startswith("_")
            }
        return {"value": json_ready(value)}

    def _normalize_error(self, exc: Exception, *, model: str) -> ProviderError:
        name = exc.__class__.__name__
        lowered_name = name.lower()
        status_code = self._first_present(
            self._coerce_mapping(exc),
            "status_code",
            "status",
            "code",
        )
        if status_code is None:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)

        kind = "unavailable"
        retryable = False
        if name in {"AuthenticationError", "PermissionDeniedError", "UnauthenticatedError", "OAuthError"} or "auth" in lowered_name or "permission" in lowered_name:
            kind = "authentication"
        elif name in {"RateLimitError", "TooManyRequestsError"} or "rate_limit" in lowered_name or "ratelimit" in lowered_name or "too_many" in lowered_name or status_code == 429:
            kind = "rate_limit"
            retryable = True
        elif name in {"APITimeoutError", "TimeoutError", "DeadlineExceededError"} or "timeout" in lowered_name or "deadline" in lowered_name:
            kind = "timeout"
            retryable = True
        elif name in {"BadRequestError", "InvalidArgumentError", "ResponseValidationError", "ValidationError"} or "badrequest" in lowered_name or "invalidargument" in lowered_name or "validation" in lowered_name or "schema" in lowered_name or status_code in {400, 404, 422}:
            kind = "protocol"
        elif name in {"InternalServerError", "ServiceUnavailableError", "UnavailableError", "ConflictError"} or "unavailable" in lowered_name or "servererror" in lowered_name or (
            isinstance(status_code, int) and status_code >= 500
        ):
            kind = "unavailable"
            retryable = True

        if status_code in {401, 403}:
            kind = "authentication"
        elif status_code == 429:
            kind = "rate_limit"
            retryable = True

        request_id = self._first_present(
            self._coerce_mapping(exc),
            "request_id",
            "_request_id",
        )
        message = self.redactor.redact_text(str(exc).strip() or f"Gemini provider {kind} error")
        details = {
            "exception_type": name,
            "model": model,
        }
        if request_id is not None:
            details["request_id"] = request_id
        if status_code is not None:
            details["status_code"] = status_code

        return ProviderError(
            message,
            kind=kind,
            request_id=str(request_id) if request_id is not None else None,
            status_code=int(status_code) if isinstance(status_code, int) else None,
            retryable=retryable,
            provider="gemini",
            details=details,
        )

    def _part_value(self, part: Any, key: str) -> Any:
        if isinstance(part, Mapping):
            if key in part:
                return part[key]
            camel_key = self._snake_to_camel(key)
            return part.get(camel_key)
        if hasattr(part, key):
            return getattr(part, key)
        camel_key = self._snake_to_camel(key)
        if hasattr(part, camel_key):
            return getattr(part, camel_key)
        return None

    def _call_value(self, call: Any, key: str) -> Any:
        if isinstance(call, Mapping):
            if key in call:
                return call[key]
            camel_key = self._snake_to_camel(key)
            return call.get(camel_key)
        if hasattr(call, key):
            return getattr(call, key)
        camel_key = self._snake_to_camel(key)
        if hasattr(call, camel_key):
            return getattr(call, camel_key)
        return None

    def _first_present(self, mapping: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in mapping and mapping[key] is not None:
                return mapping[key]
        return None

    def _snake_to_camel(self, value: str) -> str:
        head, *tail = value.split("_")
        return head + "".join(piece.title() for piece in tail)
