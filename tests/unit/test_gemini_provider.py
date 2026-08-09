from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pd_agent.core import AgentMessage, AgentRequest, AgentResponse, ToolCall, ToolResult, ToolResultStatus
from pd_agent.core.errors import ConfigurationError, ProviderError
from pd_agent.providers import GeminiProvider


class _FakeModels:
    def __init__(self, response: object | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _FakeClient:
    def __init__(self, response: object | Exception) -> None:
        self.models = _FakeModels(response)


class _Usage:
    def __init__(self) -> None:
        self.prompt_token_count = 11
        self.candidates_token_count = 7
        self.total_token_count = 18
        self.cached_content_token_count = 2
        self.thoughts_token_count = 3
        self.tool_use_prompt_token_count = 4


class _Part:
    def __init__(self, *, text: str | None = None, function_call: object | None = None) -> None:
        self.text = text
        self.function_call = function_call


class _FunctionCall:
    def __init__(self, call_id: str | None, name: str, args: object) -> None:
        self.id = call_id
        self.name = name
        self.args = args


class _Candidate:
    def __init__(self, *parts: _Part, finish_reason: str = "STOP") -> None:
        self.content = SimpleNamespace(parts=list(parts))
        self.finish_reason = finish_reason


class _AuthenticationError(Exception):
    pass


class _RateLimitError(Exception):
    pass


class _APITimeoutError(Exception):
    pass


class _BadRequestError(Exception):
    pass


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
        client=client or _FakeClient(SimpleNamespace(text="ok", usage_metadata=_Usage())),
    )


def _request(
    *,
    messages: tuple[AgentMessage, ...] = (),
    tools=(),
    tool_calls=(),
    tool_results=(),
    model_config=None,
) -> AgentRequest:
    return AgentRequest(
        messages=messages,
        tools=tools,
        tool_calls=tool_calls,
        tool_results=tool_results,
        model_config=model_config or {},
    )


def test_repr_hides_secret() -> None:
    secret = "gm-secret-123"
    provider = _provider(api_key=secret)

    assert secret not in repr(provider)
    assert "GeminiProvider(" in repr(provider)


def test_client_http_options_control_timeout_and_retries() -> None:
    provider = _provider(timeout_seconds=12.5, provider_retry_limit=2)

    assert provider._client_http_options() == {
        "timeout": 12_500,
        "retry_options": {"attempts": 3},
    }


def test_messages_mapping_and_system_instruction() -> None:
    response = SimpleNamespace(text="done", usage_metadata=_Usage(), id="resp-1", model="gemini-test")
    client = _FakeClient(response)
    provider = _provider(client=client)

    result = provider.execute(
        _request(
            messages=(
                AgentMessage(role="system", content="sys"),
                AgentMessage(role="developer", content="dev"),
                AgentMessage(role="user", content="hello"),
                AgentMessage(role="assistant", content="model reply"),
            ),
            model_config={"model": "gemini-test"},
        )
    )

    call = client.models.calls[0]
    assert call["model"] == "gemini-test"
    assert call["config"]["automatic_function_calling"] == {"disable": True}
    assert call["config"]["system_instruction"] == "sys\ndev"
    assert call["contents"] == (
        {"role": "user", "parts": [{"text": "hello"}]},
        {"role": "model", "parts": [{"text": "model reply"}]},
    )
    assert result.assistant_message == "done"


def test_tool_declarations_and_auto_function_calling_disabled() -> None:
    response = SimpleNamespace(text="done", usage_metadata=_Usage(), id="resp-2", model="gemini-test")
    client = _FakeClient(response)
    provider = _provider(client=client)
    tools = (
        {
            "name": "read_file",
            "description": "Read file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
        {
            "name": "write_file",
            "description": "Write file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "text": {"type": "string"}}},
        },
    )

    provider.execute(
        _request(
            messages=(AgentMessage(role="user", content="do tools"),),
            tools=tools,
            model_config={"model": "gemini-test"},
        )
    )

    config = client.models.calls[0]["config"]
    assert config["automatic_function_calling"] == {"disable": True}
    assert len(config["tools"]) == 1
    declarations = config["tools"][0]["function_declarations"]
    assert [item["name"] for item in declarations] == ["read_file", "write_file"]
    assert declarations[0]["parameters_json_schema"]["properties"]["path"]["type"] == "string"
    assert declarations[1]["parameters_json_schema"]["properties"]["text"]["type"] == "string"


def test_function_call_response_maps_to_tool_calls_and_text() -> None:
    response = SimpleNamespace(
        candidates=[
            _Candidate(
                _Part(text="need tools"),
                _Part(function_call=_FunctionCall("call_1", "lookup", {"q": "alpha"})),
                _Part(function_call=_FunctionCall("call_2", "write", {"path": "a.txt", "text": "ok"})),
            )
        ],
        usage_metadata=_Usage(),
        id="resp-3",
        model="gemini-test",
    )
    provider = _provider(client=_FakeClient(response))

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="do it"),), model_config={"model": "gemini-test"}))

    assert result.assistant_message == "need tools"
    assert result.tool_calls == (
        ToolCall(call_id="call_1", tool_name="lookup", arguments={"q": "alpha"}),
        ToolCall(call_id="call_2", tool_name="write", arguments={"path": "a.txt", "text": "ok"}),
    )


def test_tool_call_id_must_exist() -> None:
    response = SimpleNamespace(
        candidates=[_Candidate(_Part(function_call=_FunctionCall(None, "lookup", {"q": "alpha"})))],
        usage_metadata=_Usage(),
        id="resp-4",
        model="gemini-test",
    )
    provider = _provider(client=_FakeClient(response))

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="do it"),), model_config={"model": "gemini-test"}))

    assert excinfo.value.kind == "protocol"


def test_tool_results_serialize_to_function_response_parts() -> None:
    response = SimpleNamespace(text="done", usage_metadata=_Usage(), id="resp-5", model="gemini-test")
    client = _FakeClient(response)
    provider = _provider(client=client)
    tool_calls = (
        ToolCall(call_id="call_a", tool_name="read_file", arguments={"path": "a.txt"}),
        ToolCall(call_id="call_b", tool_name="write_file", arguments={"path": "b.txt", "text": "ok"}),
        ToolCall(call_id="call_c", tool_name="delete_file", arguments={"path": "c.txt"}),
        ToolCall(call_id="call_d", tool_name="wait", arguments={"seconds": 1}),
    )
    tool_results = (
        ToolResult(
            call_id="call_b",
            tool_name="write_file",
            status=ToolResultStatus.ERROR,
            output=None,
            error="boom",
            metadata={"attempt": 1},
        ),
        ToolResult(
            call_id="call_a",
            tool_name="read_file",
            status=ToolResultStatus.SUCCESS,
            output={"content": "alpha"},
        ),
        ToolResult(
            call_id="call_d",
            tool_name="wait",
            status=ToolResultStatus.TIMEOUT,
            output=None,
            error="slow",
        ),
        ToolResult(
            call_id="call_c",
            tool_name="delete_file",
            status=ToolResultStatus.REJECTED,
            output=None,
            error="blocked",
        ),
    )

    provider.execute(
        _request(
            messages=(AgentMessage(role="user", content="continue"),),
            tool_calls=tool_calls,
            tool_results=tool_results,
            model_config={"model": "gemini-test"},
        )
    )

    contents = client.models.calls[0]["contents"]
    assert contents[0] == {"role": "user", "parts": [{"text": "continue"}]}
    assert contents[1]["role"] == "model"
    assert [part["function_call"]["id"] for part in contents[1]["parts"]] == ["call_a", "call_b", "call_c", "call_d"]
    assert [part["function_call"]["name"] for part in contents[1]["parts"]] == ["read_file", "write_file", "delete_file", "wait"]
    assert contents[2]["role"] == "user"
    response_parts = contents[2]["parts"]
    assert [part["function_response"]["id"] for part in response_parts] == ["call_b", "call_a", "call_d", "call_c"]
    assert response_parts[0]["function_response"]["name"] == "write_file"
    assert response_parts[1]["function_response"]["name"] == "read_file"
    assert response_parts[2]["function_response"]["name"] == "wait"
    assert response_parts[3]["function_response"]["name"] == "delete_file"
    assert response_parts[0]["function_response"]["response"]["status"] == "error"
    assert response_parts[0]["function_response"]["response"]["error"] == "boom"
    assert response_parts[0]["function_response"]["response"]["metadata"] == {"attempt": 1}
    assert response_parts[1]["function_response"]["response"]["status"] == "success"
    assert response_parts[1]["function_response"]["response"]["output"] == {"content": "alpha"}
    assert response_parts[2]["function_response"]["response"]["status"] == "timeout"
    assert response_parts[3]["function_response"]["response"]["status"] == "rejected"


def test_usage_and_provider_metadata_are_mapped() -> None:
    response = SimpleNamespace(
        candidates=[_Candidate(_Part(text="done"), finish_reason="STOP")],
        usage_metadata=_Usage(),
        id="resp-6",
        model="gemini-test",
    )
    provider = _provider(client=_FakeClient(response))

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gemini-test"}))

    assert result.usage == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
        "cached_content_token_count": 2,
        "thoughts_token_count": 3,
        "tool_use_prompt_token_count": 4,
    }
    assert result.provider_metadata == {
        "provider": "gemini",
        "model": "gemini-test",
        "response_id": "resp-6",
        "finish_reason": "STOP",
    }


@pytest.mark.parametrize(
    "error, expected_kind, retryable",
    [
        (_AuthenticationError("boom"), "authentication", False),
        (_RateLimitError("boom"), "rate_limit", True),
        (_APITimeoutError("boom"), "timeout", True),
        (_BadRequestError("boom"), "protocol", False),
    ],
)
def test_error_normalization_by_exception_name(error: Exception, expected_kind: str, retryable: bool) -> None:
    provider = _provider(client=_FakeClient(error))

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gemini-test"}))

    assert excinfo.value.kind == expected_kind
    assert excinfo.value.retryable is retryable


def test_timeout_and_retry_configuration_stays_under_control() -> None:
    response = SimpleNamespace(text="done", usage_metadata=_Usage())
    provider = _provider(client=_FakeClient(response), timeout_seconds=3.25, provider_retry_limit=4)

    provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gemini-test"}))

    call = provider._client.models.calls[0]
    assert call["config"]["automatic_function_calling"] == {"disable": True}
    assert provider._client_http_options() == {
        "timeout": 3_250,
        "retry_options": {"attempts": 5},
    }


def test_provider_rejects_missing_model() -> None:
    provider = _provider(model=None)

    with pytest.raises(ConfigurationError, match="GeminiProvider requires a model"):
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),)))


def test_no_gemini_imports_outside_adapter() -> None:
    src_root = Path(__file__).resolve().parents[2] / "src" / "pd_agent"
    for path in src_root.rglob("*.py"):
        if path.name == "gemini_provider.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "google.genai" not in text
        assert "from google import genai" not in text
