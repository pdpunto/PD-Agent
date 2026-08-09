"""OpenAI Responses API adapter for PD Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    OpenAI,
    RateLimitError,
    UnprocessableEntityError,
)

from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ModelProvider, ToolCall
from pd_agent.core.errors import ConfigurationError, ProviderError
from pd_agent.reporting.redaction import Redactor, json_ready

_ALLOWED_REQUEST_CONFIG_KEYS = {
    "background",
    "include",
    "instructions",
    "max_output_tokens",
    "metadata",
    "parallel_tool_calls",
    "prompt_cache_key",
    "prompt_cache_options",
    "prompt_cache_retention",
    "reasoning",
    "safety_identifier",
    "service_tier",
    "store",
    "temperature",
    "text",
    "tool_choice",
    "top_p",
    "truncation",
    "user",
}

_VALID_MESSAGE_ROLES = {"system", "developer", "user", "assistant"}


class OpenAIProvider(ModelProvider):
    """Translate PD Agent requests into OpenAI Responses API calls."""

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
            "OpenAIProvider("
            f"model={self.model!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, "
            f"provider_retry_limit={self.provider_retry_limit!r}, "
            f"client={type(self._client).__name__}"
            ")"
        )

    def execute(self, request: AgentRequest) -> AgentResponse:
        model = self._effective_model(request)
        timeout_seconds = self._effective_timeout_seconds(request)
        retry_limit = self._effective_retry_limit(request)
        payload = self._build_request_payload(request, model=model)

        request_client = self._request_client(timeout_seconds)
        last_error: ProviderError | None = None
        for attempt in range(retry_limit + 1):
            try:
                response = request_client.responses.create(
                    timeout=timeout_seconds,
                    **payload,
                )
            except Exception as exc:  # pragma: no cover - normalized boundary
                last_error = self._normalize_error(exc, model=model)
                if not last_error.retryable or attempt >= retry_limit:
                    raise last_error from None
                continue
            return self._to_agent_response(response, model=model)
        assert last_error is not None  # pragma: no cover - defensive
        raise last_error

    def _build_client(self) -> OpenAI:
        if self.api_key is not None:
            return OpenAI(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=0,
            )
        return OpenAI(
            timeout=self.timeout_seconds,
            max_retries=0,
        )

    def _request_client(self, timeout_seconds: float) -> Any:
        client = self._client
        if hasattr(client, "with_options"):
            try:
                return client.with_options(max_retries=0, timeout=timeout_seconds)
            except TypeError:
                return client.with_options(max_retries=0)
        return client

    def _effective_model(self, request: AgentRequest) -> str:
        config_model = request.model_config.get("model")
        model = config_model if config_model is not None else self.model
        if not model:
            raise ConfigurationError("OpenAIProvider requires a model")
        return str(model)

    def _effective_timeout_seconds(self, request: AgentRequest) -> float:
        value = request.model_config.get("timeout_seconds")
        if value is None:
            return self.timeout_seconds
        timeout = float(value)
        if timeout <= 0:
            raise ConfigurationError("timeout_seconds must be positive")
        return timeout

    def _effective_retry_limit(self, request: AgentRequest) -> int:
        value = request.model_config.get("provider_retry_limit")
        if value is None:
            return self.provider_retry_limit
        retry_limit = int(value)
        if retry_limit < 0:
            raise ConfigurationError("provider_retry_limit must be non-negative")
        return retry_limit

    def _build_request_payload(self, request: AgentRequest, *, model: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "input": [self._message_to_input(message) for message in request.messages],
        }
        tools = [self._tool_to_param(tool) for tool in request.tools]
        if tools:
            payload["tools"] = tools
        for key in _ALLOWED_REQUEST_CONFIG_KEYS:
            if key in {"instructions"}:
                continue
            if key in request.model_config and request.model_config[key] is not None:
                payload[key] = request.model_config[key]
        payload["store"] = False
        instructions = request.model_config.get("instructions")
        if instructions is not None:
            payload["instructions"] = str(instructions)
        return payload

    def _message_to_input(self, message: AgentMessage) -> dict[str, Any]:
        if message.role not in _VALID_MESSAGE_ROLES:
            raise ProviderError(
                f"Unsupported message role: {message.role!r}",
                kind="protocol",
                provider="openai",
                details={"role": message.role},
            )
        return {
            "role": message.role,
            "content": message.content,
        }

    def _tool_to_param(self, tool: Mapping[str, Any]) -> dict[str, Any]:
        name = str(tool.get("name", "")).strip()
        if not name:
            raise ProviderError(
                "Tool definition missing name",
                kind="protocol",
                provider="openai",
            )
        schema = tool.get("input_schema", tool.get("parameters", {"type": "object"}))
        return {
            "type": "function",
            "name": name,
            "description": str(tool.get("description", "")),
            "parameters": json_ready(schema),
        }

    def _to_agent_response(self, response: Any, *, model: str) -> AgentResponse:
        assistant_texts: list[str] = []
        tool_calls: list[ToolCall] = []

        for item in getattr(response, "output", ()) or ():
            item_type = getattr(item, "type", None)
            if item_type == "message" and getattr(item, "role", None) == "assistant":
                assistant_texts.extend(self._extract_text_chunks(getattr(item, "content", ())))
                continue
            if item_type == "function_call":
                tool_calls.append(self._tool_call_from_output(item))

        if not assistant_texts:
            output_text = getattr(response, "output_text", None)
            if output_text:
                assistant_texts.append(str(output_text))

        usage = self._coerce_mapping(getattr(response, "usage", None))
        provider_metadata: dict[str, Any] = {
            "provider": "openai",
            "response_id": getattr(response, "id", None),
            "request_id": getattr(response, "_request_id", None),
            "model": getattr(response, "model", model),
            "status": getattr(response, "status", None),
            "output_count": len(getattr(response, "output", ()) or ()),
        }
        return AgentResponse(
            assistant_message="\n".join(assistant_texts) if assistant_texts else None,
            tool_calls=tuple(tool_calls),
            usage=usage,
            provider_metadata={key: value for key, value in provider_metadata.items() if value is not None},
        )

    def _extract_text_chunks(self, content: Any) -> list[str]:
        chunks: list[str] = []
        for item in content or ():
            item_type = getattr(item, "type", None)
            if item_type == "output_text":
                text = getattr(item, "text", "")
                if text:
                    chunks.append(str(text))
        return chunks

    def _tool_call_from_output(self, item: Any) -> ToolCall:
        arguments = self._parse_tool_arguments(getattr(item, "arguments", "{}"))
        return ToolCall(
            call_id=str(getattr(item, "call_id", "")),
            tool_name=str(getattr(item, "name", "")),
            arguments=arguments,
        )

    def _parse_tool_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, Mapping):
            arguments = dict(raw_arguments)
        elif isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    "OpenAI tool arguments are not valid JSON",
                    kind="protocol",
                    provider="openai",
                    details={"error": "invalid_json"},
                ) from exc
        else:
            raise ProviderError(
                "OpenAI tool arguments must be a JSON object",
                kind="protocol",
                provider="openai",
                details={"error": "invalid_arguments_type", "type": type(raw_arguments).__name__},
            )

        if not isinstance(arguments, dict):
            raise ProviderError(
                "OpenAI tool arguments must decode to an object",
                kind="protocol",
                provider="openai",
                details={"error": "non_object_arguments", "type": type(arguments).__name__},
            )
        return arguments

    def _coerce_mapping(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
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
        request_id = getattr(exc, "request_id", None) or getattr(exc, "_request_id", None)
        status_code = getattr(exc, "status_code", None)
        name = exc.__class__.__name__
        kind = "unavailable"
        retryable = False

        if isinstance(exc, AuthenticationError) or name in {"AuthenticationError", "PermissionDeniedError", "OAuthError"}:
            kind = "authentication"
        elif isinstance(exc, RateLimitError) or name == "RateLimitError":
            kind = "rate_limit"
            retryable = True
        elif isinstance(exc, (APITimeoutError, APIConnectionError)) or name in {"APITimeoutError", "APIConnectionError"}:
            kind = "timeout"
            retryable = True
        elif isinstance(exc, (BadRequestError, UnprocessableEntityError, APIResponseValidationError)) or name in {
            "BadRequestError",
            "UnprocessableEntityError",
            "APIResponseValidationError",
        }:
            kind = "protocol"
        elif isinstance(exc, (InternalServerError, ConflictError)) or name in {"InternalServerError", "ConflictError"}:
            kind = "unavailable"
            retryable = True
        elif isinstance(exc, APIStatusError):
            status_code = status_code if status_code is not None else getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {401, 403}:
                kind = "authentication"
            elif status_code == 429:
                kind = "rate_limit"
                retryable = True
            elif status_code in {408, 409} or (status_code is not None and status_code >= 500):
                kind = "unavailable"
                retryable = True
            else:
                kind = "protocol"
        elif name in {"APIConnectionError", "APITimeoutError"}:
            kind = "timeout"
            retryable = True

        message = self.redactor.redact_text(str(exc).strip() or f"OpenAI provider {kind} error")
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
            status_code=int(status_code) if status_code is not None else None,
            retryable=retryable,
            provider="openai",
            details=details,
        )
