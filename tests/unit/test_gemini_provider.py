from __future__ import annotations

from types import SimpleNamespace

import pytest

from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ToolCall, ToolResult, ToolResultStatus
from pd_agent.core.errors import ConfigurationError, ProviderError
from pd_agent.providers import GeminiProvider


class _FakeModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeClient:
    def __init__(self, response: object) -> None:
        self.models = _FakeModels(response)


def _provider(
    *,
    client: _FakeClient | None = None,
    model: str | None = "gemini-test",
    api_key: str | None = None,
    timeout_seconds: float = 60.0,
    provider_retry_limit: int = 2,
) -> GeminiProvider:
    return GeminiProvider(
        model=model,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        provider_retry_limit=provider_retry_limit,
        client=client or _FakeClient(SimpleNamespace(text="ok", usage_metadata={"input_tokens": 1, "output_tokens": 2})),
    )


def test_repr_hides_secret() -> None:
    secret = "gm-secret-123"
    provider = _provider(api_key=secret)

    assert secret not in repr(provider)
    assert "GeminiProvider(" in repr(provider)


def test_execute_text_only_disables_automatic_function_calling_and_uses_client_config() -> None:
    response = SimpleNamespace(
        id="gemini-resp-1",
        model="gemini-test",
        text="hello",
        usage_metadata={"input_tokens": 11, "output_tokens": 7},
    )
    client = _FakeClient(response)
    provider = _provider(client=client, api_key="gm-secret", timeout_seconds=12.5, provider_retry_limit=2)

    result = provider.execute(
        AgentRequest(
            messages=(AgentMessage(role="user", content="say hi"),),
            model_config={"model": "gemini-test"},
        )
    )

    call = client.models.calls[0]
    assert call["model"] == "gemini-test"
    assert call["contents"] == ({"role": "user", "parts": [{"text": "say hi"}]},)
    assert call["config"]["automatic_function_calling"] == {"disable": True}
    assert call["config"] == provider._build_generate_config(system_instruction=None)
    assert provider._client_http_options()["timeout"] == 12_500
    assert provider._client_http_options()["retry_options"]["attempts"] == 3
    assert result == AgentResponse(
        assistant_message="hello",
        tool_calls=(),
        usage={"input_tokens": 11, "output_tokens": 7},
        provider_metadata={
            "provider": "gemini",
            "model": "gemini-test",
            "response_id": "gemini-resp-1",
            "response_type": "SimpleNamespace",
        },
    )


def test_execute_rejects_tool_protocol_until_supported() -> None:
    provider = _provider()

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(
            AgentRequest(
                messages=(AgentMessage(role="user", content="hi"),),
                tool_calls=(ToolCall(call_id="call_1", tool_name="read_file", arguments={"path": "a.txt"}),),
                tool_results=(
                    ToolResult(
                        call_id="call_1",
                        tool_name="read_file",
                        status=ToolResultStatus.SUCCESS,
                        output="ok",
                    ),
                ),
            )
        )

    assert excinfo.value.kind == "protocol"
    assert excinfo.value.provider == "gemini"


def test_missing_model_raises_configuration_error() -> None:
    provider = _provider(model=None)

    with pytest.raises(ConfigurationError, match="GeminiProvider requires a model"):
        provider.execute(AgentRequest(messages=(AgentMessage(role="user", content="hi"),)))


def test_unsupported_message_role_raises_protocol_error() -> None:
    provider = _provider()

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(AgentRequest(messages=(AgentMessage(role="tool", content="hi"),)))

    assert excinfo.value.kind == "protocol"


def test_system_instruction_is_preserved_in_generate_config() -> None:
    response = SimpleNamespace(text="done")
    client = _FakeClient(response)
    provider = _provider(client=client)

    provider.execute(
        AgentRequest(
            messages=(
                AgentMessage(role="system", content="ctx 1"),
                AgentMessage(role="developer", content="ctx 2"),
                AgentMessage(role="user", content="hello"),
            ),
            model_config={"model": "gemini-test"},
        )
    )

    assert client.models.calls[0]["config"]["system_instruction"] == "ctx 1\nctx 2"

