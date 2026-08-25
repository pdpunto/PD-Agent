"""Provider-neutral recovery contracts with fail-closed defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pd_agent.core import AgentResponse
from pd_agent.core.errors import ProviderError


RECOVERY_SCHEMA_VERSION = 1
CAPABILITY_NAMES = (
    "client_correlation",
    "response_id_capture",
    "response_retention",
    "response_retrieval",
    "lookup_by_client_request_id",
    "idempotent_create",
    "hidden_retry_control",
)
RECOVERY_UNSUPPORTED = "UNSUPPORTED"
RECOVERY_RECOVERED = "RECOVERED"
RECOVERY_NOT_FOUND = "NOT_FOUND"
RECOVERY_INVALID = "INVALID"


class ProviderRecoveryError(ProviderError):
    """Safe, typed failure for an unavailable or invalid recovery operation."""


@dataclass(frozen=True, slots=True)
class ProviderRecoveryCapabilities:
    """Explicit provider recovery capabilities; omitted support is false."""

    provider: str
    schema_version: int = RECOVERY_SCHEMA_VERSION
    client_correlation: bool = False
    response_id_capture: bool = False
    response_retention: bool = False
    response_retrieval: bool = False
    lookup_by_client_request_id: bool = False
    idempotent_create: bool = False
    hidden_retry_control: bool = False

    def __post_init__(self) -> None:
        provider = str(self.provider).strip()
        if not provider:
            raise ValueError("provider must not be empty")
        if self.schema_version != RECOVERY_SCHEMA_VERSION:
            raise ValueError("unsupported recovery capability schema version")
        object.__setattr__(self, "provider", provider)
        for name in CAPABILITY_NAMES:
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")

    @classmethod
    def none(cls, provider: str) -> "ProviderRecoveryCapabilities":
        return cls(provider=provider)

    def supports(self, capability: str) -> bool:
        return bool(getattr(self, capability, False)) if capability in CAPABILITY_NAMES else False

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_schema_version": self.schema_version,
            "provider": self.provider,
            **{name: getattr(self, name) for name in CAPABILITY_NAMES},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderRecoveryCapabilities":
        expected = {"recovery_schema_version", "provider", *CAPABILITY_NAMES}
        missing = sorted(key for key in expected if key not in data)
        if missing:
            raise ValueError(f"incomplete recovery capability schema: missing {', '.join(missing)}")
        unknown = sorted(key for key in data if key not in expected)
        if unknown:
            raise ValueError(f"unsupported recovery capability fields: {', '.join(unknown)}")
        return cls(
            schema_version=int(data["recovery_schema_version"]),
            provider=str(data["provider"]),
            **{name: data[name] for name in CAPABILITY_NAMES},
        )


@dataclass(frozen=True, slots=True)
class RecoveryLookupRequest:
    """Minimum durable identity accepted by a future recovery operation."""

    physical_request_id: str
    provider: str
    model: str
    provider_response_id: str | None = None
    provider_request_id: str | None = None
    client_correlation_id: str | None = None
    request_fingerprint: str | None = None
    logical_attempt_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("physical_request_id", "provider", "model"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            object.__setattr__(self, name, value)
        if not any((self.provider_response_id, self.provider_request_id, self.client_correlation_id)):
            raise ValueError("recovery lookup requires a provider or client correlation handle")
        for name in (
            "provider_response_id", "provider_request_id", "client_correlation_id",
            "request_fingerprint", "logical_attempt_id",
        ):
            value = getattr(self, name)
            if value is not None:
                value = str(value).strip()
                if not value:
                    raise ValueError(f"{name} must not be blank when provided")
                object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "physical_request_id": self.physical_request_id,
            "provider": self.provider,
            "model": self.model,
            "provider_response_id": self.provider_response_id,
            "provider_request_id": self.provider_request_id,
            "client_correlation_id": self.client_correlation_id,
            "request_fingerprint": self.request_fingerprint,
            "logical_attempt_id": self.logical_attempt_id,
        }


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Typed result that never fabricates an AgentResponse."""

    status: str
    provider: str
    model: str
    physical_request_id: str
    agent_response: AgentResponse | None = None
    provider_response_id: str | None = None
    provider_request_id: str | None = None
    response_status: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {RECOVERY_UNSUPPORTED, RECOVERY_RECOVERED, RECOVERY_NOT_FOUND, RECOVERY_INVALID}:
            raise ValueError("unsupported recovery result status")
        for name in ("provider", "model", "physical_request_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        if self.status == RECOVERY_RECOVERED and self.agent_response is None:
            raise ValueError("recovered result requires a real AgentResponse")
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def unsupported(cls, lookup: RecoveryLookupRequest, *, operation: str) -> "RecoveryResult":
        return cls(
            status=RECOVERY_UNSUPPORTED,
            provider=lookup.provider,
            model=lookup.model,
            physical_request_id=lookup.physical_request_id,
            metadata={"operation": operation},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_schema_version": RECOVERY_SCHEMA_VERSION,
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "physical_request_id": self.physical_request_id,
            "agent_response": self.agent_response.to_dict() if self.agent_response is not None else None,
            "provider_response_id": self.provider_response_id,
            "provider_request_id": self.provider_request_id,
            "response_status": self.response_status,
            "metadata": dict(self.metadata),
        }


def validate_recovered_result(lookup: RecoveryLookupRequest, result: RecoveryResult) -> AgentResponse:
    """Validate identity before a future consumer can use a recovered response."""

    if result.status != RECOVERY_RECOVERED or result.agent_response is None:
        raise ProviderRecoveryError(
            "recovery result does not contain a usable response",
            kind="recovery_invalid",
            provider=lookup.provider,
            details={"status": result.status},
        )
    if result.provider != lookup.provider or result.model != lookup.model:
        raise ProviderRecoveryError(
            "recovered response provider identity mismatch",
            kind="recovery_invalid",
            provider=lookup.provider,
        )
    if result.physical_request_id != lookup.physical_request_id:
        raise ProviderRecoveryError(
            "recovered response physical identity mismatch",
            kind="recovery_invalid",
            provider=lookup.provider,
        )
    if lookup.provider_response_id is not None and result.provider_response_id != lookup.provider_response_id:
        raise ProviderRecoveryError(
            "recovered response id mismatch",
            kind="recovery_invalid",
            provider=lookup.provider,
        )
    if lookup.provider_request_id is not None and result.provider_request_id != lookup.provider_request_id:
        raise ProviderRecoveryError(
            "recovered request id mismatch",
            kind="recovery_invalid",
            provider=lookup.provider,
        )
    return result.agent_response


class ProviderRecoveryAdapter:
    """Safe-negative default for providers without recovery implementation."""

    def recovery_capabilities(self) -> ProviderRecoveryCapabilities:
        return ProviderRecoveryCapabilities.none(getattr(self, "provider_name", self.__class__.__name__.lower()))

    def retrieve_response(self, lookup: RecoveryLookupRequest) -> RecoveryResult:
        return self._unsupported(lookup, "response_retrieval")

    def reconcile_remote_outcome(self, lookup: RecoveryLookupRequest) -> RecoveryResult:
        return self._unsupported(lookup, "remote_reconciliation")

    def _unsupported(self, lookup: RecoveryLookupRequest, operation: str) -> RecoveryResult:
        if self.recovery_capabilities().supports(
            "response_retrieval" if operation == "response_retrieval" else "response_retention"
        ):
            raise ProviderRecoveryError(
                f"{operation} is declared but has no implementation",
                kind="recovery_contract",
                provider=lookup.provider,
            )
        return RecoveryResult.unsupported(lookup, operation=operation)


__all__ = [
    "CAPABILITY_NAMES",
    "ProviderRecoveryAdapter",
    "ProviderRecoveryCapabilities",
    "ProviderRecoveryError",
    "RECOVERY_INVALID",
    "RECOVERY_NOT_FOUND",
    "RECOVERY_RECOVERED",
    "RECOVERY_SCHEMA_VERSION",
    "RECOVERY_UNSUPPORTED",
    "RecoveryLookupRequest",
    "RecoveryResult",
    "validate_recovered_result",
]
