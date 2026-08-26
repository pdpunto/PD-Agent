"""Model providers for PD Agent."""

from __future__ import annotations

from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider
from .recovery import (
    CAPABILITY_NAMES,
    ProviderRecoveryAdapter,
    ProviderRecoveryCapabilities,
    ProviderRecoveryError,
    RecoveryLookupRequest,
    RecoveryResult,
    validate_recovered_result,
)
from .recovery_coordinator import (
    RECOVERY_BUDGET_BLOCKED,
    RECOVERY_DISPATCH_UNCERTAIN,
    RECOVERY_EXISTING_RESPONSE,
    RECOVERY_IDENTITY_INVALID,
    RECOVERY_LIMIT_EXHAUSTED,
    RECOVERY_PRE_DISPATCH_FAILED,
    RECOVERY_PROVIDER_FAILURE,
    RECOVERY_RECONCILIATION_UNSUPPORTED,
    RECOVERY_REISSUE_SUCCEEDED,
    RecoveryCoordinator,
    RecoveryCoordinatorResult,
)

__all__ = [
    "CAPABILITY_NAMES",
    "GeminiProvider",
    "OpenAIProvider",
    "ProviderRecoveryAdapter",
    "ProviderRecoveryCapabilities",
    "ProviderRecoveryError",
    "RecoveryLookupRequest",
    "RecoveryResult",
    "validate_recovered_result",
    "RecoveryCoordinator",
    "RecoveryCoordinatorResult",
    "RECOVERY_BUDGET_BLOCKED",
    "RECOVERY_DISPATCH_UNCERTAIN",
    "RECOVERY_EXISTING_RESPONSE",
    "RECOVERY_IDENTITY_INVALID",
    "RECOVERY_LIMIT_EXHAUSTED",
    "RECOVERY_PRE_DISPATCH_FAILED",
    "RECOVERY_PROVIDER_FAILURE",
    "RECOVERY_RECONCILIATION_UNSUPPORTED",
    "RECOVERY_REISSUE_SUCCEEDED",
]
