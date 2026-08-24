from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types

from pd_agent.core import AgentMessage, AgentRequest, ToolCall, ToolResult, ToolResultStatus
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


class _Parts:
    @staticmethod
    def text(value: str) -> object:
        return types.Part.from_text(text=value)

    @staticmethod
    def function_call(*, call_id: str | None, name: str, args: dict[str, object], thought_signature: bytes | None = None) -> object:
        kwargs: dict[str, object] = {
            "functionCall": types.FunctionCall(id=call_id, name=name, args=args),
        }
        if thought_signature is not None:
            kwargs["thoughtSignature"] = thought_signature
        return types.Part(**kwargs)

    @staticmethod
    def function_response(*, call_id: str | None, name: str, response: dict[str, object]) -> object:
        return types.Part(functionResponse=types.FunctionResponse(id=call_id, name=name, response=response))


class _Candidate:
    def __init__(self, *parts: object, finish_reason: str = "STOP") -> None:
        self.content = types.Content(role="model", parts=list(parts))
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
    provider_continuations=(),
    model_config=None,
) -> AgentRequest:
    return AgentRequest(
        messages=messages,
        tools=tools,
        tool_calls=tool_calls,
        tool_results=tool_results,
        provider_continuations=provider_continuations,
        model_config=model_config or {},
    )


def _first_content(call: dict[str, object]) -> types.Content:
    contents = call["contents"]
    assert isinstance(contents, (list, tuple))
    return contents[0]


def test_sdk_types_construct_real_objects() -> None:
    declaration = types.FunctionDeclaration(
        name="lookup",
        description="Lookup data",
        parametersJsonSchema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    tool = types.Tool(functionDeclarations=[declaration])
    call_without_id = types.FunctionCall(name="lookup", args={"q": "alpha"})
    call_with_id = types.FunctionCall(id="call_1", name="lookup", args={"q": "alpha"})
    response_without_id = types.FunctionResponse(name="lookup", response={"output": "ok"})
    response_with_id = types.FunctionResponse(id="call_1", name="lookup", response={"output": "ok"})
    config = types.GenerateContentConfig(
        tools=[tool],
        automaticFunctionCalling=types.AutomaticFunctionCallingConfig(disable=True),
        httpOptions=types.HttpOptions(timeout=1000, retryOptions=types.HttpRetryOptions(attempts=1)),
    )

    assert call_without_id.id is None
    assert call_with_id.id == "call_1"
    assert response_without_id.id is None
    assert response_with_id.id == "call_1"
    assert tool.function_declarations[0].parameters_json_schema["type"] == "object"
    assert config.automatic_function_calling.disable is True
    assert config.http_options.timeout == 1000
    assert config.http_options.retry_options.attempts == 1


def test_repr_hides_secret() -> None:
    secret = "gm-secret-123"
    provider = _provider(api_key=secret)

    assert secret not in repr(provider)
    assert "GeminiProvider(" in repr(provider)


def test_client_http_options_real_types() -> None:
    provider = _provider(timeout_seconds=12.5, provider_retry_limit=2)
    http_options = provider._client_http_options(provider._types())

    assert http_options.timeout == 12_500
    assert http_options.retry_options.attempts == 3


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
            tool_calls=(ToolCall(call_id="call_1", tool_name="lookup", arguments={"q": "alpha"}),),
            tool_results=(
                ToolResult(
                    call_id="call_1",
                    tool_name="lookup",
                    status=ToolResultStatus.SUCCESS,
                    output={"value": "ok"},
                ),
            ),
            model_config={"model": "gemini-test"},
        )
    )

    call = client.models.calls[0]
    assert call["model"] == "gemini-test"
    config = call["config"]
    assert config.automatic_function_calling.disable is True
    assert config.system_instruction == "sys\ndev"
    assert len(call["contents"]) == 4
    assert call["contents"][0].role == "user"
    assert call["contents"][0].parts[0].text == "hello"
    assert call["contents"][1].role == "model"
    assert call["contents"][1].parts[0].text == "model reply"
    assert call["contents"][2].role == "model"
    assert call["contents"][2].parts[0].function_call.name == "lookup"
    assert call["contents"][3].role == "user"
    assert call["contents"][3].parts[0].function_response.name == "lookup"
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
    assert config.automatic_function_calling.disable is True
    assert config.http_options.timeout == 60_000
    assert config.http_options.retry_options.attempts == 3
    assert len(config.tools) == 1
    declarations = config.tools[0].function_declarations
    assert [item.name for item in declarations] == ["read_file", "write_file"]
    assert declarations[0].parameters_json_schema["properties"]["path"]["type"] == "string"
    assert declarations[1].parameters_json_schema["properties"]["text"]["type"] == "string"


def test_function_call_response_maps_to_tool_calls_and_text() -> None:
    response = SimpleNamespace(
        candidates=[
            _Candidate(
                _Parts.text("need tools"),
                _Parts.function_call(call_id="call_1", name="lookup", args={"q": "alpha"}),
                _Parts.function_call(call_id="call_2", name="write", args={"path": "a.txt", "text": "ok"}),
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


def test_model_ending_request_is_rejected_before_sdk_call() -> None:
    client = _FakeClient(SimpleNamespace(text="unused", usage_metadata=_Usage()))
    provider = _provider(client=client)

    with pytest.raises(ProviderError, match="Gemini request cannot end with a model turn") as excinfo:
        provider.execute(
            _request(
                messages=(
                    AgentMessage(role="user", content="continue"),
                    AgentMessage(role="assistant", content="finished this turn"),
                ),
                model_config={"model": "gemini-test"},
            )
        )

    assert excinfo.value.kind == "protocol"
    assert excinfo.value.provider == "gemini"
    assert client.models.calls == []


def test_thought_signature_continuation_round_trip_and_replay() -> None:
    response_1 = SimpleNamespace(
        candidates=[
            _Candidate(
                _Parts.function_call(call_id="call_1", name="lookup", args={"q": "alpha"}, thought_signature=b"sig-1"),
                _Parts.function_call(call_id="call_2", name="write", args={"path": "a.txt"}, thought_signature=b"sig-2"),
            )
        ],
        usage_metadata=_Usage(),
        id="resp-3a",
        model="gemini-3.5-flash",
    )
    response_2 = SimpleNamespace(text="done", usage_metadata=_Usage(), id="resp-3b", model="gemini-3.5-flash")
    client = _FakeClient(response_1)
    client.models.response = [response_1, response_2]

    def _sequential_generate_content(**kwargs):
        client.models.calls.append(kwargs)
        return client.models.response.pop(0)

    client.models.generate_content = _sequential_generate_content  # type: ignore[method-assign]
    provider = _provider(client=client, model="gemini-3.5-flash")

    first = provider.execute(_request(messages=(AgentMessage(role="user", content="do it"),), model_config={"model": "gemini-3.5-flash"}))

    assert [item.target_id for item in first.provider_continuations] == ["call_1", "call_2"]
    assert [item.position for item in first.provider_continuations] == [0, 1]
    assert base64.b64decode(first.provider_continuations[0].payload["thought_signature_b64"]) == b"sig-1"
    assert base64.b64decode(first.provider_continuations[1].payload["thought_signature_b64"]) == b"sig-2"

    provider.execute(
        _request(
            messages=(AgentMessage(role="user", content="continue"),),
            tool_calls=first.tool_calls,
            tool_results=(
                ToolResult(call_id="call_1", tool_name="lookup", status=ToolResultStatus.SUCCESS, output={"content": "alpha"}),
                ToolResult(call_id="call_2", tool_name="write", status=ToolResultStatus.SUCCESS, output={"changed": True}),
            ),
            provider_continuations=first.provider_continuations,
            model_config={"model": "gemini-3.5-flash"},
        )
    )

    replay_contents = client.models.calls[1]["contents"]
    replay_parts = replay_contents[1].parts
    assert replay_parts[0].function_call.id == "call_1"
    assert replay_parts[0].function_call.name == "lookup"
    assert replay_parts[0].thought_signature == b"sig-1"
    assert replay_parts[1].function_call.id == "call_2"
    assert replay_parts[1].function_call.name == "write"
    assert replay_parts[1].thought_signature == b"sig-2"
    assert [part.function_response.id for part in replay_contents[2].parts] == ["call_1", "call_2"]


def test_function_call_without_id_gets_local_id() -> None:
    response = SimpleNamespace(
        candidates=[_Candidate(_Parts.function_call(call_id=None, name="lookup", args={"q": "alpha"}))],
        usage_metadata=_Usage(),
        id="resp-4",
        model="gemini-test",
    )
    provider = _provider(client=_FakeClient(response))

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="do it"),), model_config={"model": "gemini-test"}))

    assert result.tool_calls[0].call_id.startswith("gemini-local:")
    assert result.tool_calls[0].tool_name == "lookup"
    assert result.tool_calls[0].arguments == {"q": "alpha"}


def test_no_id_tool_call_replay_omits_id_and_preserves_association() -> None:
    response_1 = SimpleNamespace(
        candidates=[_Candidate(_Parts.function_call(call_id=None, name="lookup", args={"q": "alpha"}))],
        usage_metadata=_Usage(),
        id="resp-5",
        model="gemini-test",
    )
    response_2 = SimpleNamespace(text="done", usage_metadata=_Usage(), id="resp-6", model="gemini-test")
    client = _FakeClient(response_1)
    client.models.response = [response_1, response_2]

    def _sequential_generate_content(**kwargs):
        client.models.calls.append(kwargs)
        return client.models.response.pop(0)

    client.models.generate_content = _sequential_generate_content  # type: ignore[method-assign]
    provider = _provider(client=client)

    first = provider.execute(_request(messages=(AgentMessage(role="user", content="do it"),), model_config={"model": "gemini-test"}))
    provider.execute(
        _request(
            messages=(AgentMessage(role="user", content="continue"),),
            tool_calls=(first.tool_calls[0],),
            tool_results=(
                ToolResult(
                    call_id=first.tool_calls[0].call_id,
                    tool_name="lookup",
                    status=ToolResultStatus.SUCCESS,
                    output={"content": "alpha"},
                ),
            ),
            model_config={"model": "gemini-test"},
        )
    )

    replay_contents = client.models.calls[1]["contents"]
    assert replay_contents[1].parts[0].function_call.id is None
    assert replay_contents[2].parts[0].function_response.id is None
    assert replay_contents[1].parts[0].function_call.name == "lookup"
    assert replay_contents[2].parts[0].function_response.name == "lookup"


def test_tool_results_serialize_to_function_response_parts() -> None:
    response = SimpleNamespace(text="done", usage_metadata=_Usage(), id="resp-7", model="gemini-test")
    client = _FakeClient(response)
    provider = _provider(client=client)
    tool_calls = (
        ToolCall(call_id="call_a", tool_name="read_file", arguments={"path": "a.txt"}),
        ToolCall(call_id="gemini-local:1:abc123", tool_name="write_file", arguments={"path": "b.txt", "text": "ok"}),
    )
    tool_results = (
        ToolResult(
            call_id="gemini-local:1:abc123",
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
    assert contents[0].role == "user"
    assert contents[1].role == "model"
    assert contents[1].parts[0].function_call.id == "call_a"
    assert contents[1].parts[1].function_call.id is None
    assert contents[2].role == "user"
    assert contents[2].parts[0].function_response.id is None
    assert contents[2].parts[1].function_response.id == "call_a"
    assert contents[2].parts[0].function_response.response["status"] == "error"
    assert contents[2].parts[1].function_response.response["status"] == "success"


def test_multiple_calls_without_id_get_distinct_local_ids() -> None:
    response = SimpleNamespace(
        candidates=[
            _Candidate(
                _Parts.function_call(call_id=None, name="lookup", args={"q": "alpha"}),
                _Parts.function_call(call_id=None, name="lookup", args={"q": "beta"}),
            )
        ],
        usage_metadata=_Usage(),
        id="resp-8",
        model="gemini-test",
    )
    provider = _provider(client=_FakeClient(response))

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="go"),), model_config={"model": "gemini-test"}))

    assert result.tool_calls[0].call_id != result.tool_calls[1].call_id
    assert result.tool_calls[0].call_id.startswith("gemini-local:")
    assert result.tool_calls[1].call_id.startswith("gemini-local:")


def test_mixed_real_and_local_ids_round_trip() -> None:
    response = SimpleNamespace(
        candidates=[
            _Candidate(
                _Parts.function_call(call_id="call_real", name="lookup", args={"q": "alpha"}),
                _Parts.function_call(call_id=None, name="write", args={"path": "a.txt"}),
            )
        ],
        usage_metadata=_Usage(),
        id="resp-9",
        model="gemini-test",
    )
    provider = _provider(client=_FakeClient(response))

    result = provider.execute(_request(messages=(AgentMessage(role="user", content="go"),), model_config={"model": "gemini-test"}))

    assert result.tool_calls[0].call_id == "call_real"
    assert result.tool_calls[1].call_id.startswith("gemini-local:")


def test_usage_and_provider_metadata_are_mapped() -> None:
    response = SimpleNamespace(
        candidates=[_Candidate(_Parts.text("done"), finish_reason="STOP")],
        usage_metadata=_Usage(),
        id="resp-10",
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
        "response_id": "resp-10",
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


def test_resource_exhausted_message_is_rate_limit_without_overmatching_generic_quota_errors() -> None:
    provider = _provider(client=_FakeClient(Exception("429 RESOURCE_EXHAUSTED: quota exceeded for generate_content")))

    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gemini-test"}))

    assert excinfo.value.kind == "rate_limit"
    assert excinfo.value.retryable is True

    provider = _provider(client=_FakeClient(Exception("quota exceeded for generate_content")))
    with pytest.raises(ProviderError) as excinfo:
        provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gemini-test"}))

    assert excinfo.value.kind == "unavailable"


def test_timeout_and_retry_configuration_stays_under_control() -> None:
    response = SimpleNamespace(text="done", usage_metadata=_Usage())
    provider = _provider(client=_FakeClient(response), timeout_seconds=3.25, provider_retry_limit=4)

    provider.execute(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gemini-test"}))

    config = provider._build_generate_config(_request(messages=(AgentMessage(role="user", content="hi"),), model_config={"model": "gemini-test"}), provider._types(), system_instruction=None)
    assert config.automatic_function_calling.disable is True
    assert config.http_options.timeout == 3_250
    assert config.http_options.retry_options.attempts == 5


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
