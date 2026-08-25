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

from pd_agent.core import (
    AgentMessage,
    AgentRequest,
    AgentResponse,
    ModelProvider,
    ProviderContinuation,
    ToolCall,
)
from pd_agent.core import ToolResult, ToolResultStatus
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
        budget_guard: Any | None = None,
        service_tier: str | None = None,
        prompt_cache_options: Mapping[str, Any] | None = None,
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
        self.budget_guard = budget_guard
        self.service_tier = service_tier
        self.prompt_cache_options = dict(prompt_cache_options) if prompt_cache_options is not None else None
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
        physical_request_count = 0
        if self.budget_guard is not None:
            self.budget_guard.begin_logical_turn()
        for attempt in range(retry_limit + 1):
            if self.budget_guard is not None:
                self.budget_guard.before_request(payload, retry_count=attempt)
            physical_request_count += 1
            try:
                response = request_client.responses.create(
                    timeout=timeout_seconds,
                    **payload,
                )
            except Exception as exc:  # pragma: no cover - normalized boundary
                if self.budget_guard is not None:
                    self.budget_guard.on_failure_without_usage(retry_count=attempt)
                last_error = self._normalize_error(exc, model=model)
                if not last_error.retryable or attempt >= retry_limit:
                    last_error.details.update(
                        {
                            "physical_request_count": physical_request_count,
                            "provider_retry_count": physical_request_count - 1,
                        }
                    )
                    raise last_error from None
                continue
            budget_metadata = None
            if self.budget_guard is not None:
                normalized_usage = self._normalize_usage(getattr(response, "usage", None))
                budget_metadata = self.budget_guard.account_response(normalized_usage)
                if isinstance(normalized_usage, dict):
                    normalized_usage.update(budget_metadata)
                    try:
                        response.usage = normalized_usage
                    except Exception:
                        pass
            return self._to_agent_response(
                response,
                model=model,
                physical_request_count=physical_request_count,
                budget_metadata=budget_metadata,
            )
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
        input_items: list[dict[str, Any]] = [self._message_to_input(message) for message in request.messages]
        input_items.extend(self._continuations_to_input(request.provider_continuations))
        input_items.extend(self._tool_call_to_input(call) for call in request.tool_calls)
        input_items.extend(self._tool_result_to_input(result) for result in request.tool_results)
        payload: dict[str, Any] = {
            "model": model,
            "input": input_items,
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
        if self.service_tier is not None and "service_tier" not in payload:
            payload["service_tier"] = self.service_tier
        if self.prompt_cache_options is not None and "prompt_cache_options" not in payload:
            payload["prompt_cache_options"] = dict(self.prompt_cache_options)
        if request.model_config.get("reasoning"):
            payload["include"] = self._merge_reasoning_include(request.model_config.get("include"))
        instructions = request.model_config.get("instructions")
        if instructions is not None:
            payload["instructions"] = str(instructions)
        return payload

    def _merge_reasoning_include(self, configured: Any) -> list[str]:
        if configured is None:
            include: list[str] = []
        elif isinstance(configured, (list, tuple)):
            if not all(isinstance(item, str) for item in configured):
                raise ProviderError(
                    "OpenAI include must contain only strings",
                    kind="protocol",
                    provider="openai",
                )
            include = list(configured)
        else:
            raise ProviderError(
                "OpenAI include must be a sequence of strings",
                kind="protocol",
                provider="openai",
            )
        if "reasoning.encrypted_content" not in include:
            include.append("reasoning.encrypted_content")
        return list(dict.fromkeys(include))

    def _continuations_to_input(
        self,
        continuations: tuple[ProviderContinuation, ...],
    ) -> list[dict[str, Any]]:
        owned = [
            continuation
            for continuation in continuations
            if continuation.provider.casefold() == "openai"
        ]
        if not owned:
            return []

        seen_ids: set[str] = set()
        seen_positions: set[int] = set()
        items: list[tuple[int, dict[str, Any]]] = []
        for continuation in owned:
            if continuation.kind != "reasoning_output" or continuation.target_type != "reasoning":
                raise ProviderError(
                    "OpenAI continuation has unsupported ownership metadata",
                    kind="protocol",
                    provider="openai",
                )
            if continuation.position is None:
                raise ProviderError(
                    "OpenAI reasoning continuation requires a position",
                    kind="protocol",
                    provider="openai",
                )
            if continuation.target_id in seen_ids or continuation.position in seen_positions:
                raise ProviderError(
                    "OpenAI reasoning continuations contain a conflict",
                    kind="protocol",
                    provider="openai",
                )
            payload = dict(continuation.payload)
            if payload.get("type") != "reasoning" or payload.get("id") != continuation.target_id:
                raise ProviderError(
                    "OpenAI reasoning continuation payload is inconsistent",
                    kind="protocol",
                    provider="openai",
                )
            summary = payload.get("summary")
            if not isinstance(summary, list):
                raise ProviderError(
                    "OpenAI reasoning continuation summary is invalid",
                    kind="protocol",
                    provider="openai",
                )
            encrypted_content = payload.get("encrypted_content")
            if encrypted_content is not None and not isinstance(encrypted_content, str):
                raise ProviderError(
                    "OpenAI reasoning continuation encrypted content is invalid",
                    kind="protocol",
                    provider="openai",
                )
            item: dict[str, Any] = {
                "type": "reasoning",
                "id": continuation.target_id,
                "summary": summary,
            }
            if encrypted_content is not None:
                item["encrypted_content"] = encrypted_content
            if payload.get("content") is not None:
                item["content"] = payload["content"]
            if payload.get("status") is not None:
                item["status"] = payload["status"]
            seen_ids.add(continuation.target_id)
            seen_positions.add(continuation.position)
            items.append((continuation.position, item))
        return [item for _position, item in sorted(items, key=lambda entry: entry[0])]

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

    def _tool_call_to_input(self, call: ToolCall) -> dict[str, Any]:
        return {
            "type": "function_call",
            "call_id": call.call_id,
            "name": call.tool_name,
            "arguments": json.dumps(json_ready(call.arguments), ensure_ascii=False, sort_keys=True),
        }

    def _tool_result_to_input(self, result: ToolResult) -> dict[str, Any]:
        return {
            "type": "function_call_output",
            "call_id": result.call_id,
            "output": self.redactor.redact_text(self._tool_result_output(result)),
        }

    def _to_agent_response(
        self,
        response: Any,
        *,
        model: str,
        physical_request_count: int = 1,
        budget_metadata: Mapping[str, Any] | None = None,
    ) -> AgentResponse:
        assistant_texts: list[str] = []
        tool_calls: list[ToolCall] = []
        continuations: list[ProviderContinuation] = []

        for position, item in enumerate(getattr(response, "output", ()) or ()):
            item_type = getattr(item, "type", None)
            if item_type == "reasoning":
                continuations.append(self._reasoning_continuation_from_output(item, position=position))
                continue
            if item_type == "message" and getattr(item, "role", None) == "assistant":
                assistant_texts.extend(self._extract_text_chunks(getattr(item, "content", ())))
                continue
            if item_type == "function_call":
                tool_calls.append(self._tool_call_from_output(item))

        if not assistant_texts:
            output_text = getattr(response, "output_text", None)
            if output_text:
                assistant_texts.append(str(output_text))

        usage = self._normalize_usage(getattr(response, "usage", None))
        provider_metadata: dict[str, Any] = {
            "provider": "openai",
            "response_id": getattr(response, "id", None),
            "request_id": getattr(response, "_request_id", None),
            "model": getattr(response, "model", model),
            "status": getattr(response, "status", None),
            "output_count": len(getattr(response, "output", ()) or ()),
            "physical_request_count": physical_request_count,
            "provider_retry_count": physical_request_count - 1,
        }
        if self.budget_guard is not None:
            provider_metadata.update(self.budget_guard.metadata())
        if budget_metadata is not None:
            provider_metadata["budget_last_response"] = dict(budget_metadata)
        return AgentResponse(
            assistant_message="\n".join(assistant_texts) if assistant_texts else None,
            tool_calls=tuple(tool_calls),
            provider_continuations=tuple(continuations),
            usage=usage,
            provider_metadata={key: value for key, value in provider_metadata.items() if value is not None},
        )

    def _reasoning_continuation_from_output(self, item: Any, *, position: int) -> ProviderContinuation:
        target_id = str(getattr(item, "id", "")).strip()
        summary = getattr(item, "summary", None)
        if not target_id or summary is None:
            raise ProviderError(
                "OpenAI reasoning output item is missing continuation metadata",
                kind="protocol",
                provider="openai",
            )
        payload: dict[str, Any] = {
            "type": "reasoning",
            "id": target_id,
            "summary": self._json_ready_reasoning(summary),
        }
        content = getattr(item, "content", None)
        if content is not None:
            payload["content"] = self._json_ready_reasoning(content)
        encrypted_content = getattr(item, "encrypted_content", None)
        if encrypted_content is not None:
            if not isinstance(encrypted_content, str):
                raise ProviderError(
                    "OpenAI reasoning encrypted content is invalid",
                    kind="protocol",
                    provider="openai",
                )
            payload["encrypted_content"] = encrypted_content
        status = getattr(item, "status", None)
        if status is not None:
            payload["status"] = str(status)
        return ProviderContinuation(
            provider="openai",
            kind="reasoning_output",
            target_type="reasoning",
            target_id=target_id,
            position=position,
            payload=payload,
        )

    def _json_ready_reasoning(self, value: Any) -> Any:
        """Normalize SDK reasoning models without exposing provider types."""

        if hasattr(value, "to_dict") and callable(value.to_dict):
            return self._json_ready_reasoning(value.to_dict())
        if isinstance(value, Mapping):
            return {str(key): self._json_ready_reasoning(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_ready_reasoning(item) for item in value]
        if hasattr(value, "__dict__"):
            return {
                str(key): self._json_ready_reasoning(item)
                for key, item in vars(value).items()
                if not str(key).startswith("_")
            }
        return json_ready(value)

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

    def _tool_result_output(self, result: ToolResult) -> str:
        payload: dict[str, Any] = {
            "call_id": result.call_id,
            "tool_name": result.tool_name,
            "status": result.status.value,
            "output": json_ready(result.output),
            "error": result.error,
            "metadata": json_ready(dict(result.metadata)),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

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

    def _normalize_usage(self, value: Any) -> dict[str, Any] | None:
        usage = self._coerce_mapping(value)
        if usage is None:
            return None
        input_details = self._coerce_mapping(usage.get("input_tokens_details")) or {}
        output_details = self._coerce_mapping(usage.get("output_tokens_details")) or {}
        if "cached_input_tokens" not in usage and isinstance(input_details.get("cached_tokens"), int):
            usage["cached_input_tokens"] = input_details["cached_tokens"]
        if "cache_write_tokens" not in usage and isinstance(input_details.get("cache_write_tokens"), int):
            usage["cache_write_tokens"] = input_details["cache_write_tokens"]
        if "reasoning_tokens" not in usage and isinstance(output_details.get("reasoning_tokens"), int):
            usage["reasoning_tokens"] = output_details["reasoning_tokens"]
        return usage

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
