"""Bounded, provider-neutral post-dispatch recovery coordination."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from pd_agent.core import AgentRequest, AgentResponse
from pd_agent.core.errors import ProviderError
from pd_agent.experimental import (
    ABANDONED,
    DISPATCH_STARTED,
    RESPONSE_AVAILABLE,
    RESPONSE_MISSING,
    UNCERTAIN_CONSUMED,
    DispatchRecord,
    LunaBudgetGuard,
)

from .recovery import (
    RECOVERY_RECOVERED,
    RECOVERY_UNSUPPORTED,
    ProviderRecoveryAdapter,
    ProviderRecoveryCapabilities,
    ProviderRecoveryError,
    RecoveryLookupRequest,
    RecoveryResult,
    validate_recovered_result,
)


RECOVERY_EXISTING_RESPONSE = "RECOVERED_EXISTING_RESPONSE"
RECOVERY_REISSUE_SUCCEEDED = "RECOVERY_REISSUE_SUCCEEDED"
RECOVERY_RECONCILIATION_UNSUPPORTED = "RECOVERY_RECONCILIATION_UNSUPPORTED"
RECOVERY_BUDGET_BLOCKED = "RECOVERY_BUDGET_BLOCKED"
RECOVERY_LIMIT_EXHAUSTED = "RECOVERY_LIMIT_EXHAUSTED"
RECOVERY_IDENTITY_INVALID = "RECOVERY_IDENTITY_INVALID"
RECOVERY_DISPATCH_UNCERTAIN = "RECOVERY_DISPATCH_UNCERTAIN"
RECOVERY_PRE_DISPATCH_FAILED = "RECOVERY_PRE_DISPATCH_FAILED"
RECOVERY_PROVIDER_FAILURE = "RECOVERY_PROVIDER_FAILURE"


@dataclass(frozen=True, slots=True)
class RecoveryCoordinatorResult:
    """Serializable outcome of one bounded recovery decision."""

    status: str
    original_physical_request_id: str
    logical_attempt_id: str
    recovery_generation: int
    response: AgentResponse | None = None
    recovery_physical_request_id: str | None = None
    strategy: str = "none"
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        allowed = {
            RECOVERY_EXISTING_RESPONSE,
            RECOVERY_REISSUE_SUCCEEDED,
            RECOVERY_RECONCILIATION_UNSUPPORTED,
            RECOVERY_BUDGET_BLOCKED,
            RECOVERY_LIMIT_EXHAUSTED,
            RECOVERY_IDENTITY_INVALID,
            RECOVERY_DISPATCH_UNCERTAIN,
            RECOVERY_PRE_DISPATCH_FAILED,
            RECOVERY_PROVIDER_FAILURE,
        }
        if self.status not in allowed:
            raise ValueError("unsupported recovery coordinator status")
        if not str(self.original_physical_request_id).strip() or not str(self.logical_attempt_id).strip():
            raise ValueError("recovery result requires original dispatch identity")
        if self.recovery_generation < 0:
            raise ValueError("recovery_generation must be non-negative")
        if self.status in {RECOVERY_EXISTING_RESPONSE, RECOVERY_REISSUE_SUCCEEDED} and self.response is None:
            raise ValueError("successful recovery requires a real AgentResponse")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_coordinator_schema_version": 1,
            "status": self.status,
            "original_physical_request_id": self.original_physical_request_id,
            "logical_attempt_id": self.logical_attempt_id,
            "recovery_generation": self.recovery_generation,
            "response": self.response.to_dict() if self.response is not None else None,
            "recovery_physical_request_id": self.recovery_physical_request_id,
            "strategy": self.strategy,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


class RecoveryCoordinator:
    """Reconciliation-first recovery with at most one bounded reissue."""

    def __init__(
        self,
        provider: Any,
        *,
        budget_guard: LunaBudgetGuard | None = None,
        max_recovery_generation: int = 1,
        allow_reissue: bool = True,
    ) -> None:
        if max_recovery_generation < 0:
            raise ValueError("max_recovery_generation must be non-negative")
        self.provider = provider
        self.budget_guard = budget_guard
        self.max_recovery_generation = max_recovery_generation
        self.allow_reissue = allow_reissue
        if budget_guard is not None and hasattr(provider, "budget_guard") and getattr(provider, "budget_guard") is None:
            provider.budget_guard = budget_guard

    def recover(self, original: DispatchRecord, request: AgentRequest) -> RecoveryCoordinatorResult:
        invalid = self._validate_original(original)
        if invalid is not None:
            return invalid
        lookup = self._lookup(original)
        capabilities = self._capabilities()

        if capabilities.supports("response_retrieval"):
            retrieval = self._retrieve(lookup)
            if retrieval is not None:
                return retrieval
        else:
            reconciliation_reason = "response retrieval is not declared"

        if not self.allow_reissue:
            return self._result(
                original,
                RECOVERY_RECONCILIATION_UNSUPPORTED,
                strategy="reconciliation",
                reason=locals().get("reconciliation_reason", "reconciliation unavailable"),
            )
        if self.budget_guard is None:
            return self._result(
                original,
                RECOVERY_BUDGET_BLOCKED,
                strategy="reissue",
                reason="reissue requires the economic budget guard",
            )
        return self._reissue(original, request)

    def _validate_original(self, original: DispatchRecord) -> RecoveryCoordinatorResult | None:
        if not isinstance(original, DispatchRecord):
            return self._invalid_identity("dispatch record is malformed")
        stored = self.budget_guard.state.dispatch_records.get(original.physical_request_id) if self.budget_guard else None
        if stored is None or dict(stored) != original.to_dict():
            return self._invalid_identity("dispatch evidence is missing or inconsistent", original)
        if original.dispatch_state != DISPATCH_STARTED or original.functional_state != RESPONSE_MISSING:
            return self._invalid_identity("dispatch is not an uncertain response-missing operation", original)
        if original.recovery_generation != 0 or original.recovery_of is not None:
            return self._result(original, RECOVERY_LIMIT_EXHAUSTED, reason="recovery generation already consumed")
        if not original.reservation_id:
            return self._invalid_identity("dispatch has no reservation identity", original)
        if self.budget_guard is None:
            return self._result(original, RECOVERY_BUDGET_BLOCKED, reason="economic state is unavailable")
        ledger = self.budget_guard.state.ledger.get(original.reservation_id)
        if not ledger or ledger.get("status") != UNCERTAIN_CONSUMED:
            return self._invalid_identity("economic settlement is not UNCERTAIN_CONSUMED", original)
        try:
            provider = self._capabilities().provider
        except (AttributeError, ValueError):
            return self._invalid_identity("provider recovery contract is unavailable", original)
        if provider != original.provider:
            return self._invalid_identity("provider identity mismatch", original)
        if original.recovery_generation >= self.max_recovery_generation:
            return self._result(original, RECOVERY_LIMIT_EXHAUSTED, reason="recovery limit exhausted")
        return None

    def _capabilities(self) -> ProviderRecoveryCapabilities:
        method = getattr(self.provider, "recovery_capabilities", None)
        if not callable(method):
            return ProviderRecoveryCapabilities.none(self.provider.__class__.__name__.lower())
        capabilities = method()
        if not isinstance(capabilities, ProviderRecoveryCapabilities):
            raise ProviderRecoveryError("malformed provider recovery capabilities", kind="recovery_contract")
        return capabilities

    def _lookup(self, original: DispatchRecord) -> RecoveryLookupRequest:
        return RecoveryLookupRequest(
            physical_request_id=original.physical_request_id,
            provider=original.provider,
            model=original.model,
            provider_response_id=original.provider_response_id,
            provider_request_id=original.provider_request_id,
            client_correlation_id=original.client_correlation_id,
            request_fingerprint=original.request_fingerprint,
            logical_attempt_id=original.logical_attempt_id,
        )

    def _retrieve(self, lookup: RecoveryLookupRequest) -> RecoveryCoordinatorResult | None:
        try:
            result = self.provider.retrieve_response(lookup)
        except (ProviderError, AttributeError) as exc:
            return self._result_from_lookup_failure(lookup, "retrieval failed", exc)
        if not isinstance(result, RecoveryResult):
            return self._result_from_lookup_failure(lookup, "retrieval returned malformed result", None)
        if result.status == RECOVERY_UNSUPPORTED:
            return None
        try:
            response = validate_recovered_result(lookup, result)
        except ProviderError as exc:
            return self._result_from_lookup_failure(lookup, str(exc), exc)
        return RecoveryCoordinatorResult(
            status=RECOVERY_EXISTING_RESPONSE,
            original_physical_request_id=lookup.physical_request_id,
            logical_attempt_id=lookup.logical_attempt_id or "unknown",
            recovery_generation=0,
            response=response,
            strategy="retrieval",
            metadata={"provider_response_id": result.provider_response_id},
        )

    def _reissue(self, original: DispatchRecord, request: AgentRequest) -> RecoveryCoordinatorResult:
        config = dict(request.model_config)
        config["_recovery_generation"] = original.recovery_generation + 1
        config["_recovery_of"] = original.physical_request_id
        recovery_request = replace(request, model_config=config)
        try:
            response = self.provider.execute(recovery_request)
        except ProviderError as exc:
            abort_reason = exc.details.get("abort_reason")
            if abort_reason == "BUDGET_BLOCKED":
                return self._result(
                    original,
                    RECOVERY_BUDGET_BLOCKED,
                    strategy="reissue",
                    reason=str(exc),
                )
            recovery_record = self._latest_recovery_record(original)
            if recovery_record is not None and recovery_record.functional_state == RESPONSE_MISSING:
                return self._result(
                    original,
                    RECOVERY_DISPATCH_UNCERTAIN,
                    recovery_generation=recovery_record.recovery_generation,
                    recovery_physical_request_id=recovery_record.physical_request_id,
                    strategy="reissue",
                    reason=str(exc),
                )
            if recovery_record is not None and recovery_record.functional_state == ABANDONED:
                return self._result(
                    original,
                    RECOVERY_PRE_DISPATCH_FAILED,
                    recovery_generation=recovery_record.recovery_generation,
                    recovery_physical_request_id=recovery_record.physical_request_id,
                    strategy="reissue",
                    reason=str(exc),
                )
            reason = str(exc)
            if abort_reason == "UNKNOWN_BILLABLE_USAGE":
                status = RECOVERY_BUDGET_BLOCKED
            else:
                status = RECOVERY_PROVIDER_FAILURE
            return self._result(original, status, strategy="reissue", reason=reason)
        if not isinstance(response, AgentResponse):
            return self._result(original, RECOVERY_PROVIDER_FAILURE, strategy="reissue", reason="provider returned no AgentResponse")
        recovery_record = self._latest_recovery_record(original)
        if recovery_record is None or recovery_record.functional_state != RESPONSE_AVAILABLE:
            return self._result(original, RECOVERY_IDENTITY_INVALID, strategy="reissue", reason="reissue evidence is missing")
        return self._result(
            original,
            RECOVERY_REISSUE_SUCCEEDED,
            recovery_generation=recovery_record.recovery_generation,
            recovery_physical_request_id=recovery_record.physical_request_id,
            response=response,
            strategy="reissue",
        )

    def _latest_recovery_record(self, original: DispatchRecord) -> DispatchRecord | None:
        if self.budget_guard is None:
            return None
        records = []
        for data in self.budget_guard.state.dispatch_records.values():
            try:
                record = DispatchRecord.from_dict(data)
            except (TypeError, ValueError):
                continue
            if record.recovery_of == original.physical_request_id:
                records.append(record)
        return max(records, key=lambda item: item.recovery_generation, default=None)

    def _result_from_lookup_failure(self, lookup: RecoveryLookupRequest, reason: str, error: Exception | None) -> RecoveryCoordinatorResult:
        return RecoveryCoordinatorResult(
            status=RECOVERY_IDENTITY_INVALID if error is not None else RECOVERY_RECONCILIATION_UNSUPPORTED,
            original_physical_request_id=lookup.physical_request_id,
            logical_attempt_id=lookup.logical_attempt_id or "unknown",
            recovery_generation=0,
            strategy="reconciliation",
            reason=reason,
        )

    def _invalid_identity(self, reason: str, original: DispatchRecord | None = None) -> RecoveryCoordinatorResult:
        return self._result(original, RECOVERY_IDENTITY_INVALID, reason=reason)

    def _result(self, original: DispatchRecord | None, status: str, **kwargs: Any) -> RecoveryCoordinatorResult:
        if original is None:
            return RecoveryCoordinatorResult(
                status=status,
                original_physical_request_id="unknown",
                logical_attempt_id="unknown",
                recovery_generation=0,
                **kwargs,
            )
        return RecoveryCoordinatorResult(
            status=status,
            original_physical_request_id=original.physical_request_id,
            logical_attempt_id=original.logical_attempt_id,
            recovery_generation=kwargs.pop("recovery_generation", original.recovery_generation),
            **kwargs,
        )


__all__ = [
    "RECOVERY_BUDGET_BLOCKED",
    "RECOVERY_DISPATCH_UNCERTAIN",
    "RECOVERY_EXISTING_RESPONSE",
    "RECOVERY_IDENTITY_INVALID",
    "RECOVERY_LIMIT_EXHAUSTED",
    "RECOVERY_PRE_DISPATCH_FAILED",
    "RECOVERY_PROVIDER_FAILURE",
    "RECOVERY_RECONCILIATION_UNSUPPORTED",
    "RECOVERY_REISSUE_SUCCEEDED",
    "RecoveryCoordinator",
    "RecoveryCoordinatorResult",
]
