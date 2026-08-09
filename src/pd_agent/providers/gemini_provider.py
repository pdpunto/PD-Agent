"""Gemini adapter for PD Agent v0.1.1."""

from __future__ import annotations

from typing import Any, Mapping

from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ModelProvider
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
        self._reject_tool_protocol(request)
        system_instruction, contents = self._build_contents(request.messages)
        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=self._build_generate_config(system_instruction=system_instruction),
        )
        return self._to_agent_response(response, model=model)

    def _build_client(self) -> Any:
        try:
            from google import genai
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency path
            raise ConfigurationError("google-genai is required for GeminiProvider") from exc

        return genai.Client(
            api_key=self.api_key,
            http_options=self._client_http_options(),
        )

    def _client_http_options(self) -> dict[str, Any]:
        return {
            "timeout": max(1, int(self.timeout_seconds * 1000)),
            "retry_options": {"attempts": self.provider_retry_limit + 1},
        }

    def _build_generate_config(self, *, system_instruction: str | None) -> dict[str, Any]:
        config: dict[str, Any] = {
            "automatic_function_calling": {"disable": True},
        }
        if system_instruction:
            config["system_instruction"] = system_instruction
        return config

    def _effective_model(self, request: AgentRequest) -> str:
        config_model = request.model_config.get("model")
        model = config_model if config_model is not None else self.model
        if not model:
            raise ConfigurationError("GeminiProvider requires a model")
        return str(model)

    def _reject_tool_protocol(self, request: AgentRequest) -> None:
        if request.tools or request.tool_calls or request.tool_results:
            raise ProviderError(
                "GeminiProvider v0.1.1 does not support tool protocol yet",
                kind="protocol",
                provider="gemini",
                details={
                    "tools": len(request.tools),
                    "tool_calls": len(request.tool_calls),
                    "tool_results": len(request.tool_results),
                },
            )

    def _build_contents(self, messages: tuple[AgentMessage, ...]) -> tuple[str | None, tuple[dict[str, Any], ...]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for message in messages:
            if message.role in {"system", "developer"}:
                if message.content:
                    system_parts.append(message.content)
                continue
            role = self._normalize_role(message.role)
            contents.append(
                {
                    "role": role,
                    "parts": [{"text": message.content}],
                }
            )
        system_instruction = "\n".join(system_parts) if system_parts else None
        return system_instruction, tuple(contents)

    def _normalize_role(self, role: str) -> str:
        normalized = role.strip().lower()
        if normalized == "user":
            return "user"
        if normalized == "assistant":
            return "model"
        raise ProviderError(
            f"Unsupported Gemini message role: {role!r}",
            kind="protocol",
            provider="gemini",
            details={"role": role},
        )

    def _to_agent_response(self, response: Any, *, model: str) -> AgentResponse:
        assistant_message = self._extract_text(response)
        usage = self._coerce_mapping(
            getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
        )
        provider_metadata: dict[str, Any] = {
            "provider": "gemini",
            "model": getattr(response, "model", model),
            "response_id": getattr(response, "id", None),
            "response_type": type(response).__name__,
        }
        return AgentResponse(
            assistant_message=assistant_message,
            tool_calls=(),
            usage=usage,
            provider_metadata={key: value for key, value in provider_metadata.items() if value is not None},
        )

    def _extract_text(self, response: Any) -> str | None:
        text = getattr(response, "text", None)
        if text:
            return str(text)
        candidates = getattr(response, "candidates", None) or ()
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or ()
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return str(part_text)
        return None

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

