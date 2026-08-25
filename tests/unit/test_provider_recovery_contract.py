from __future__ import annotations

from decimal import Decimal

import pytest

from pd_agent.core import AgentResponse
from pd_agent.core.errors import ProviderError
from pd_agent.providers import (
    GeminiProvider,
    OpenAIProvider,
    ProviderRecoveryAdapter,
    ProviderRecoveryCapabilities,
    ProviderRecoveryError,
    RecoveryLookupRequest,
    RecoveryResult,
    validate_recovered_result,
)
from pd_agent.providers.recovery import (
    RECOVERY_RECOVERED,
    RECOVERY_UNSUPPORTED,
)


def _lookup(**overrides) -> RecoveryLookupRequest:
    values = {
        "physical_request_id": "dispatch-1",
        "provider": "fake",
        "model": "model-1",
        "provider_response_id": "response-1",
    }
    values.update(overrides)
    return RecoveryLookupRequest(**values)


def test_default_provider_adapter_is_safe_negative() -> None:
    adapter = ProviderRecoveryAdapter()
    lookup = _lookup()

    capabilities = adapter.recovery_capabilities()
    assert all(not capabilities.supports(name) for name in capabilities.to_dict() if name not in {"provider", "recovery_schema_version"})
    assert adapter.retrieve_response(lookup).status == RECOVERY_UNSUPPORTED
    assert adapter.reconcile_remote_outcome(lookup).status == RECOVERY_UNSUPPORTED


def test_capabilities_round_trip_and_unknown_capability_is_negative() -> None:
    capabilities = ProviderRecoveryCapabilities(
        provider="fake",
        response_id_capture=True,
        hidden_retry_control=True,
    )
    restored = ProviderRecoveryCapabilities.from_dict(capabilities.to_dict())

    assert restored == capabilities
    assert restored.supports("response_id_capture") is True
    assert restored.supports("future_capability") is False

    malformed = capabilities.to_dict()
    malformed.pop("response_id_capture")
    with pytest.raises(ValueError, match="incomplete recovery capability schema"):
        ProviderRecoveryCapabilities.from_dict(malformed)


def test_malformed_capability_is_fail_closed() -> None:
    with pytest.raises(ValueError):
        ProviderRecoveryCapabilities(provider="fake", response_id_capture=1)

    with pytest.raises(ValueError, match="unsupported recovery capability fields"):
        ProviderRecoveryCapabilities.from_dict(
            {
                **ProviderRecoveryCapabilities.none("fake").to_dict(),
                "optimistic_unknown": True,
            }
        )


def test_lookup_requires_correlation_handle() -> None:
    with pytest.raises(ValueError, match="requires a provider or client"):
        RecoveryLookupRequest(physical_request_id="dispatch-1", provider="fake", model="m")


def test_unsupported_operations_do_not_create_response_or_touch_accounting() -> None:
    adapter = ProviderRecoveryAdapter()
    lookup = _lookup()
    result = adapter.retrieve_response(lookup)

    assert result.agent_response is None
    assert result.status == RECOVERY_UNSUPPORTED
    assert result.metadata["operation"] == "response_retrieval"


class _RetrievalProvider(ProviderRecoveryAdapter):
    def recovery_capabilities(self) -> ProviderRecoveryCapabilities:
        return ProviderRecoveryCapabilities(provider="fake", response_retrieval=True)

    def retrieve_response(self, lookup: RecoveryLookupRequest) -> RecoveryResult:
        return RecoveryResult(
            status=RECOVERY_RECOVERED,
            provider=lookup.provider,
            model=lookup.model,
            physical_request_id=lookup.physical_request_id,
            provider_response_id=lookup.provider_response_id,
            agent_response=AgentResponse(assistant_message="recovered"),
            metadata={"source": "fake"},
        )


def test_fake_provider_can_declare_and_expose_real_retrieval_contract() -> None:
    provider = _RetrievalProvider()
    lookup = _lookup()
    result = provider.retrieve_response(lookup)

    assert provider.recovery_capabilities().supports("response_retrieval") is True
    assert validate_recovered_result(lookup, result).assistant_message == "recovered"


def test_declared_capability_without_operation_implementation_fails_closed() -> None:
    class DeclaredOnly(ProviderRecoveryAdapter):
        def recovery_capabilities(self) -> ProviderRecoveryCapabilities:
            return ProviderRecoveryCapabilities(provider="fake", response_retrieval=True)

    with pytest.raises(ProviderRecoveryError, match="declared but has no implementation"):
        DeclaredOnly().retrieve_response(_lookup())


def test_recovered_result_identity_mismatch_fails_closed() -> None:
    lookup = _lookup()
    result = RecoveryResult(
        status=RECOVERY_RECOVERED,
        provider="fake",
        model="model-1",
        physical_request_id="other-dispatch",
        provider_response_id="response-1",
        agent_response=AgentResponse(assistant_message="recovered"),
    )

    with pytest.raises(ProviderError, match="physical identity mismatch"):
        validate_recovered_result(lookup, result)


def test_recovered_result_requires_real_agent_response() -> None:
    with pytest.raises(ValueError, match="requires a real AgentResponse"):
        RecoveryResult(
            status=RECOVERY_RECOVERED,
            provider="fake",
            model="model-1",
            physical_request_id="dispatch-1",
        )


def test_openai_capabilities_are_conservative_and_correlation_is_not_idempotency() -> None:
    provider = object.__new__(OpenAIProvider)
    capabilities = provider.recovery_capabilities()

    assert capabilities.provider == "openai"
    assert capabilities.client_correlation is True
    assert capabilities.response_id_capture is True
    assert capabilities.hidden_retry_control is True
    assert capabilities.response_retrieval is False
    assert capabilities.response_retention is False
    assert capabilities.lookup_by_client_request_id is False
    assert capabilities.idempotent_create is False


def test_gemini_capabilities_are_all_unsupported() -> None:
    provider = object.__new__(GeminiProvider)
    capabilities = provider.recovery_capabilities()

    assert capabilities.provider == "gemini"
    assert capabilities.to_dict() == {
        "recovery_schema_version": 1,
        "provider": "gemini",
        "client_correlation": False,
        "response_id_capture": False,
        "response_retention": False,
        "response_retrieval": False,
        "lookup_by_client_request_id": False,
        "idempotent_create": False,
        "hidden_retry_control": False,
    }


def test_capability_declaration_does_not_change_economic_values() -> None:
    from pd_agent.experimental import LunaBudgetGuard, LunaEconomicState

    state = LunaEconomicState(execution_id="capability-only", global_accumulated_usd=Decimal("0.02"))
    before = state.to_dict()
    _ = ProviderRecoveryCapabilities(provider="fake", response_id_capture=True)

    assert state.to_dict() == before
