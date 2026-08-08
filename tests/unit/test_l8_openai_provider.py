from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from pd_agent import ContextBundle, ContextItem
from pd_agent.context import ContextManager
from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ToolCall
from pd_agent.core.errors import ProviderError
from pd_agent.providers import OpenAIProvider
from pd_agent.reporting import Redactor


class _Text:
    type = "output_text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Message:
    type = "message"

    def __init__(self, *parts: _Text) -> None:
        self.role = "assistant"
        self.content = list(parts)


class _FunctionCall:
    type = "function_call"

    def __init__(self, call_id: str, name: str, arguments: str, *, response_id: str = "out-1") -> None:
        self.call_id = call_id
        self.name = name
        self.arguments = arguments
        self.id = response_id
        self.status = "completed"


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponses:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.responses = _FakeResponses(outcomes)
        self.with_options_calls: list[dict[str, object]] = []

    def with_options(self, **kwargs):
        self.with_options_calls.append(kwargs)
        return self


class AuthenticationError(Exception):
    pass


class RateLimitError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class BadRequestError(Exception):
    pass


class InternalServerError(Exception):
    pass


def _provider(
    *,
    client: _FakeClient | None = None,
    model: str | None = "gpt-test",
    retry_limit: int = 2,
    api_key: str | None = None,
    redactor: Redactor | None = None,
) -> OpenAIProvider:
    return OpenAIProvider(
        model=model,
        api_key=api_key,
        provider_retry_limit=retry_limit,
        client=client or _FakeClient([]),
        redactor=redactor,
    )


def _request(*, messages: tuple[AgentMessage, ...] = (), tools=(), model_config=None) -> AgentRequest:
    return AgentRequest(messages=messages, tools=tools, model_config=model_config or {})


def test_request_mapping_and_response_mapping() -> None:
    response = SimpleNamespace(
        id="resp_1",
        model="gpt-test",
        status="completed",
        _request_id="req_1",
        usage=_Usage(11, 7),
        output=[_Message(_Text("hello"))],
    )
    client = _FakeClient([response])
    provider = _provider(client=client)
    request = _request(
        messages=(
            AgentMessage(role="system", content="ctx"),
            AgentMessage(role="user", content="hello"),
        ),
        tools=(
            {
                "name": "lookup",
                "description": "Lookup data",
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        ),
        model_config={
            "model": "gpt-test",
            "instructions": "be brief",
            "temperature": 0.2,
            "top_p": 0.8,
            "max_output_tokens": 42,
            "metadata": {"suite": "l8"},
            "user": "tester",
            "parallel_tool_calls": False,
            "store": False,
            "truncation": "disabled",
            "reasoning": {"effort": "low"},
            "service_tier": "auto",
            "unsupported": "ignored",
        },
    )

    result = provider.execute(request)

    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["instructions"] == "be brief"
    assert call["temperature"] == 0.2
    assert call["top_p"] == 0.8
    assert call["max_output_tokens"] == 42
    assert call["metadata"] == {"suite": "l8"}
    assert call["user"] == "tester"
    assert call["parallel_tool_calls"] is False
    assert call["store"] is False
    assert call["truncation"] == "disabled"
    assert call["reasoning"] == {"effort": "low"}
    assert call["service_tier"] == "auto"
    assert "unsupported" not in call
    assert call["input"][0]["role"] == "system"
    assert call["input"][1]["content"] == "hello"
    assert call["tools"][0]["type"] == "function"
    assert call["tools"][0]["name"] == "lookup"

    assert result == AgentResponse(
        assistant_message="hello",
        tool_calls=(),
        usage={"input_tokens": 11, "output_tokens": 7},
        provider_metadata={
            "provider": "openai",
            "response_id": "resp_1",
            "request_id": "req_1",
            "model": "gpt-test",
            "status": "completed",
            "output_count": 1,
        },
    )


def test_tool_call_mapping_and_multiple_calls() -> None:
    response = SimpleNamespace(
        id="resp_2",
        model="gpt-test",
        status="completed",
        _request_id="req_2",
        usage=None,
        output=[
            _Message(_Text("need tools")),
            _FunctionCall("call_1", "lookup", "{\"q\": \"alpha\"}"),
            _FunctionCall("call_2", "write", "{\"path\": \"a.txt\", \"text\": \"ok\"}"),
        ],
    )
    provider = _provider(client=_FakeClient([response]))

    result = provider.execute(
        _request(messages=(AgentMessage(role="user", content="do it"),), tools=())
    )

    assert result.assistant_message == "need tools"
    assert result.tool_calls == (
        ToolCall(call_id="call_1", tool_name="lookup", arguments={"q": "alpha"}),
        ToolCall(call_id="call_2", tool_name="write", arguments={"path": "a.txt", "text": "ok"}),
    )


def test_text_only_and_no_tools() -> None:
    response = SimpleNamespace(
        id="resp_3",
        model="gpt-test",
        status="completed",
        _request_id="req_3",
        usage=None,
        output=[_Message(_Text("only text"))],
    )
    provider = _provider(client=_FakeClient([response]))

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="say hi"),)))

    assert result.assistant_message == "only text"
    assert result.tool_calls == ()


def test_invalid_json_arguments_raise_protocol_error() -> None:
    response = SimpleNamespace(
        id="resp_4",
        model="gpt-test",
        status="completed",
        _request_id="req_4",
        usage=None,
        output=[_FunctionCall("call_4", "lookup", "{not-json}")],
    )
    provider = _provider(client=_FakeClient([response]))

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))

    assert excinfo.value.kind == "protocol"
    assert excinfo.value.retryable is False


def test_non_object_arguments_raise_protocol_error() -> None:
    response = SimpleNamespace(
        id="resp_5",
        model="gpt-test",
        status="completed",
        _request_id="req_5",
        usage=None,
        output=[_FunctionCall("call_5", "lookup", "[1, 2, 3]")],
    )
    provider = _provider(client=_FakeClient([response]))

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))

    assert excinfo.value.kind == "protocol"
    assert excinfo.value.retryable is False


def test_authentication_error_has_no_retry_and_redacts_key() -> None:
    secret = "sk-secret-123"
    client = _FakeClient([AuthenticationError(f"bad key {secret}")])
    provider = _provider(client=client, api_key=secret, redactor=Redactor((secret,)))

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))

    error = excinfo.value
    assert error.kind == "authentication"
    assert error.retryable is False
    assert secret not in str(error)
    assert secret not in str(error.to_dict())
    assert secret not in repr(provider)
    assert client.responses.calls and len(client.responses.calls) == 1


def test_rate_limit_retries_until_limit() -> None:
    response = SimpleNamespace(
        id="resp_6",
        model="gpt-test",
        status="completed",
        _request_id="req_6",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([RateLimitError("rl1"), RateLimitError("rl2"), response])
    provider = _provider(client=client, retry_limit=2)

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))

    assert result.assistant_message == "ok"
    assert len(client.responses.calls) == 3


def test_timeout_and_connection_retry() -> None:
    response = SimpleNamespace(
        id="resp_7",
        model="gpt-test",
        status="completed",
        _request_id="req_7",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([APITimeoutError("slow"), response])
    provider = _provider(client=client, retry_limit=1)

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))

    assert result.assistant_message == "ok"
    assert len(client.responses.calls) == 2


def test_protocol_error_does_not_retry() -> None:
    client = _FakeClient([BadRequestError("bad request")])
    provider = _provider(client=client, retry_limit=3)

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))

    assert excinfo.value.kind == "protocol"
    assert len(client.responses.calls) == 1


def test_server_error_retries_and_maps_metadata() -> None:
    response = SimpleNamespace(
        id="resp_8",
        model="gpt-override",
        status="completed",
        _request_id="req_8",
        usage=_Usage(3, 4),
        output=[_Message(_Text("done"))],
    )
    client = _FakeClient([InternalServerError("oops"), response])
    provider = _provider(client=client, retry_limit=1, model="gpt-default")

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gpt-override"}))

    assert result.assistant_message == "done"
    assert result.provider_metadata["model"] == "gpt-override"
    assert result.usage == {"input_tokens": 3, "output_tokens": 4}
    assert len(client.responses.calls) == 2


def test_context_messages_and_fake_provider_swap() -> None:
    bundle = ContextBundle(
        items=(
            ContextItem.from_text(source="project", priority=10, content="ctx"),
        )
    )
    manager = ContextManager()
    request = _request(
        messages=bundle.to_messages() + (AgentMessage(role="user", content="hello"),),
        tools=(),
        model_config={"model": "gpt-test"},
    )
    response = SimpleNamespace(
        id="resp_9",
        model="gpt-test",
        status="completed",
        _request_id="req_9",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([response])
    provider = _provider(client=client)

    result = provider.execute(request)

    assert client.responses.calls[0]["input"][0]["role"] == "system"
    assert result.assistant_message == "ok"
    assert manager.build_context().to_messages() == ()


def test_openai_types_do_not_escape_provider() -> None:
    response = SimpleNamespace(
        id="resp_10",
        model="gpt-test",
        status="completed",
        _request_id="req_10",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    provider = _provider(client=_FakeClient([response]))
    result = provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))

    assert type(result).__module__.startswith("pd_agent.core")
    assert all(type(item).__module__.startswith("pd_agent.core") for item in result.tool_calls)
    assert "openai" in result.provider_metadata["provider"]
