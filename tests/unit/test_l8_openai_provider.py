from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from pd_agent import ContextBundle, ContextItem
from pd_agent.context import ContextManager
from pd_agent.core import (
    AgentMessage,
    AgentRequest,
    AgentResponse,
    ProviderContinuation,
    ToolCall,
    ToolResult,
    ToolResultStatus,
)
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


class _Reasoning:
    type = "reasoning"

    def __init__(self, item_id: str, encrypted_content: str, *, position_summary: str = "summary") -> None:
        self.id = item_id
        self.summary = [SimpleNamespace(type="summary_text", text=position_summary)]
        self.encrypted_content = encrypted_content
        self.status = "completed"


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _NestedUsage:
    def __init__(self) -> None:
        self.input_tokens = 11
        self.output_tokens = 7
        self.total_tokens = 18
        self.input_tokens_details = SimpleNamespace(cached_tokens=5)
        self.output_tokens_details = SimpleNamespace(reasoning_tokens=3)


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


def _request(
    *,
    messages: tuple[AgentMessage, ...] = (),
    tools=(),
    provider_continuations=(),
    model_config=None,
) -> AgentRequest:
    return AgentRequest(messages=messages, tools=tools, provider_continuations=provider_continuations, model_config=model_config or {})


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
                "physical_request_count": 1,
                "provider_retry_count": 0,
            },
    )


def test_store_is_forced_false_even_if_requested_true() -> None:
    response = SimpleNamespace(
        id="resp_store",
        model="gpt-test",
        status="completed",
        _request_id="req_store",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([response])
    provider = _provider(client=client)

    provider.execute(
        _request(
            messages=(AgentMessage(role="user", content="hi"),),
            model_config={"model": "gpt-test", "store": True},
        )
    )

    assert client.responses.calls[0]["store"] is False


def test_luna_model_and_medium_reasoning_request_encrypted_content() -> None:
    response = SimpleNamespace(
        id="resp_reasoning",
        model="gpt-5.6-luna",
        status="completed",
        _request_id="req_reasoning",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([response])
    provider = _provider(client=client, model="gpt-5.6-luna")

    provider.execute(
        _request(
            model_config={
                "model": "gpt-5.6-luna",
                "reasoning": {"effort": "medium"},
                "include": ["some.other.include", "reasoning.encrypted_content"],
            }
        )
    )

    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.6-luna"
    assert call["reasoning"] == {"effort": "medium"}
    assert call["include"] == ["some.other.include", "reasoning.encrypted_content"]
    assert call["store"] is False
    assert "previous_response_id" not in call


def test_reasoning_output_becomes_opaque_provider_continuation() -> None:
    encrypted = "opaque-encrypted-reasoning"
    response = SimpleNamespace(
        id="resp_reasoning_output",
        model="gpt-5.6-luna",
        status="completed",
        _request_id="req_reasoning_output",
        usage=None,
        output=[_Reasoning("rs_1", encrypted)],
    )
    result = _provider(client=_FakeClient([response]), model="gpt-5.6-luna").execute(_request())

    assert len(result.provider_continuations) == 1
    continuation = result.provider_continuations[0]
    assert continuation.provider == "openai"
    assert continuation.kind == "reasoning_output"
    assert continuation.target_type == "reasoning"
    assert continuation.target_id == "rs_1"
    assert continuation.position == 0
    assert continuation.payload["encrypted_content"] == encrypted
    assert continuation.payload["summary"][0]["text"] == "summary"
    assert encrypted not in json.dumps(result.provider_metadata or {})


def test_reasoning_replay_preserves_order_before_multiple_function_calls_and_outputs() -> None:
    response = SimpleNamespace(
        id="resp_replay",
        model="gpt-5.6-luna",
        status="completed",
        _request_id="req_replay",
        usage=None,
        output=[_Reasoning("rs_2", "enc-2"), _FunctionCall("call_a", "lookup", "{}"), _FunctionCall("call_b", "write", "{}")],
    )
    provider = _provider(client=_FakeClient([response]), model="gpt-5.6-luna")
    first = provider.execute(_request(model_config={"reasoning": {"effort": "medium"}}))

    provider._client = _FakeClient([SimpleNamespace(output=[_Message(_Text("done"))], usage=None)])
    provider.execute(
        AgentRequest(
            messages=(AgentMessage(role="user", content="continue"),),
            provider_continuations=first.provider_continuations,
            tool_calls=first.tool_calls,
            tool_results=(
                ToolResult(call_id="call_a", tool_name="lookup", status=ToolResultStatus.SUCCESS, output="a"),
                ToolResult(call_id="call_b", tool_name="write", status=ToolResultStatus.SUCCESS, output="b"),
            ),
            model_config={"reasoning": {"effort": "medium"}},
        )
    )

    replay = provider._client.responses.calls[0]["input"]
    assert [item.get("type", item.get("role")) for item in replay] == [
        "user",
        "reasoning",
        "function_call",
        "function_call",
        "function_call_output",
        "function_call_output",
    ]
    assert replay[1]["id"] == "rs_2"
    assert replay[2]["call_id"] == "call_a"
    assert replay[3]["call_id"] == "call_b"
    assert [item["call_id"] for item in replay[4:]] == ["call_a", "call_b"]


def test_multiple_reasoning_continuations_replay_by_position() -> None:
    response = SimpleNamespace(
        id="resp_many_reasoning",
        model="gpt-5.6-luna",
        status="completed",
        _request_id="req_many_reasoning",
        usage=None,
        output=[_Reasoning("rs_3", "enc-3", position_summary="first"), _Reasoning("rs_4", "enc-4", position_summary="second")],
    )
    provider = _provider(client=_FakeClient([response]), model="gpt-5.6-luna")
    first = provider.execute(_request())
    provider._client = _FakeClient([SimpleNamespace(output=[], usage=None)])
    provider.execute(AgentRequest(provider_continuations=tuple(reversed(first.provider_continuations))))

    replay = provider._client.responses.calls[0]["input"]
    assert [item["id"] for item in replay] == ["rs_3", "rs_4"]


def test_foreign_continuation_is_not_consumed_by_openai() -> None:
    response = SimpleNamespace(id="resp_foreign", model="gpt-test", status="completed", usage=None, output=[])
    continuation = ProviderContinuation(
        provider="gemini",
        kind="thought_signature",
        target_type="function_call",
        target_id="call-1",
        position=0,
        payload={"thought_signature_b64": "sig"},
    )
    client = _FakeClient([response])
    _provider(client=client).execute(_request(provider_continuations=(continuation,)))
    assert "input" not in client.responses.calls[0] or client.responses.calls[0]["input"] == []


@pytest.mark.parametrize(
    "continuation",
    [
        ProviderContinuation(provider="openai", kind="reasoning_output", target_type="reasoning", target_id="rs", position=0, payload={"type": "wrong", "id": "rs", "summary": []}),
        ProviderContinuation(provider="openai", kind="reasoning_output", target_type="reasoning", target_id="rs", position=0, payload={"type": "reasoning", "id": "other", "summary": []}),
    ],
)
def test_incompatible_openai_continuation_is_protocol_error(continuation: ProviderContinuation) -> None:
    with pytest.raises(ProviderError) as excinfo:
        _provider(client=_FakeClient([SimpleNamespace(output=[], usage=None)])).execute(
            _request(provider_continuations=(continuation,))
        )
    assert excinfo.value.kind == "protocol"


def test_openai_usage_normalizes_cached_and_reasoning_tokens() -> None:
    response = SimpleNamespace(
        id="resp_usage",
        model="gpt-test",
        status="completed",
        usage=_NestedUsage(),
        output=[],
    )
    result = _provider(client=_FakeClient([response])).execute(_request())
    assert result.usage["input_tokens"] == 11
    assert result.usage["output_tokens"] == 7
    assert result.usage["total_tokens"] == 18
    assert result.usage["cached_input_tokens"] == 5
    assert result.usage["reasoning_tokens"] == 3


def test_physical_request_metadata_counts_retries() -> None:
    response = SimpleNamespace(id="resp_physical", model="gpt-test", status="completed", usage=None, output=[])
    client = _FakeClient([RateLimitError("rl"), response])
    result = _provider(client=client, retry_limit=1).execute(_request())
    assert result.provider_metadata["physical_request_count"] == 2
    assert result.provider_metadata["provider_retry_count"] == 1


def test_exhausted_retry_error_reports_physical_attempts_without_payload() -> None:
    secret = "sk-secret-physical"
    client = _FakeClient([RateLimitError(f"bad {secret}"), RateLimitError(f"bad {secret}")])
    with pytest.raises(ProviderError) as excinfo:
        _provider(client=client, retry_limit=1, api_key=secret, redactor=Redactor((secret,))).execute(_request())
    assert excinfo.value.details["physical_request_count"] == 2
    assert excinfo.value.details["provider_retry_count"] == 1
    assert secret not in str(excinfo.value.details)


def test_empty_provider_continuations_are_ignored() -> None:
    response = SimpleNamespace(
        id="resp_empty",
        model="gpt-test",
        status="completed",
        _request_id="req_empty",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([response])
    provider = _provider(client=client)

    provider.execute(
        _request(
            messages=(AgentMessage(role="user", content="hi"),),
            provider_continuations=(),
            model_config={"model": "gpt-test"},
        )
    )

    assert "provider_continuations" not in client.responses.calls[0]


def test_tool_continuation_serializes_function_call_and_output() -> None:
    response = SimpleNamespace(
        id="resp_tool",
        model="gpt-test",
        status="completed",
        _request_id="req_tool",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([response])
    provider = _provider(client=client)
    tool_call = ToolCall(call_id="call_123", tool_name="read_file", arguments={"path": "alpha.txt"})
    tool_result = ToolResult(
        call_id="call_123",
        tool_name="read_file",
        status=ToolResultStatus.SUCCESS,
        output={"content": "hello"},
        metadata={"changed": False},
    )

    provider.execute(
        AgentRequest(
            messages=(AgentMessage(role="user", content="continue"),),
            tool_calls=(tool_call,),
            tool_results=(tool_result,),
            model_config={"model": "gpt-test"},
        )
    )

    input_items = client.responses.calls[0]["input"]
    call_item = next(item for item in input_items if item.get("type") == "function_call")
    output_item = next(item for item in input_items if item.get("type") == "function_call_output")
    assert call_item["call_id"] == "call_123"
    assert call_item["name"] == "read_file"
    assert json.loads(call_item["arguments"]) == {"path": "alpha.txt"}
    assert output_item["call_id"] == "call_123"
    payload = json.loads(output_item["output"])
    assert payload["call_id"] == "call_123"
    assert payload["tool_name"] == "read_file"
    assert payload["status"] == "success"
    assert payload["output"] == {"content": "hello"}


def test_multiple_tool_results_serialized_in_order() -> None:
    response = SimpleNamespace(
        id="resp_multi",
        model="gpt-test",
        status="completed",
        _request_id="req_multi",
        usage=None,
        output=[_Message(_Text("ok"))],
    )
    client = _FakeClient([response])
    provider = _provider(client=client)
    tool_calls = (
        ToolCall(call_id="call_a", tool_name="read_file", arguments={"path": "alpha.txt"}),
        ToolCall(call_id="call_b", tool_name="write_file", arguments={"path": "beta.txt", "text": "ok"}),
    )

    provider.execute(
        AgentRequest(
            messages=(AgentMessage(role="user", content="continue"),),
            tool_calls=tool_calls,
            tool_results=(
                ToolResult(
                    call_id="call_a",
                    tool_name="read_file",
                    status=ToolResultStatus.SUCCESS,
                    output="alpha",
                ),
                ToolResult(
                    call_id="call_b",
                    tool_name="write_file",
                    status=ToolResultStatus.ERROR,
                    error="boom",
                ),
            ),
            model_config={"model": "gpt-test"},
        )
    )

    input_items = client.responses.calls[0]["input"]
    call_items = [item for item in input_items if item.get("type") == "function_call"]
    output_items = [item for item in input_items if item.get("type") == "function_call_output"]
    assert [item["call_id"] for item in call_items] == ["call_a", "call_b"]
    assert json.loads(call_items[0]["arguments"]) == {"path": "alpha.txt"}
    assert json.loads(call_items[1]["arguments"]) == {"path": "beta.txt", "text": "ok"}
    assert [item["call_id"] for item in output_items] == ["call_a", "call_b"]
    first = json.loads(output_items[0]["output"])
    second = json.loads(output_items[1]["output"])
    assert first["status"] == "success"
    assert first["output"] == "alpha"
    assert second["status"] == "error"
    assert second["error"] == "boom"


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
