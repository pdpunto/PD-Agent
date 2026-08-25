"""Reusable Luna pricing, dual-budget state and request ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from pd_agent.core.errors import ProviderError


LUNA_EXPERIMENTAL_HARD_BUDGET_USD = Decimal("1.00")
LUNA_PER_ATTEMPT_HARD_BUDGET_USD = Decimal("0.10")
LUNA_ECONOMIC_SCHEMA_VERSION = 2
RESERVED = "RESERVED"
ACCOUNTED = "ACCOUNTED"
RELEASED = "RELEASED"
UNCERTAIN_CONSUMED = "UNCERTAIN_CONSUMED"
DISPATCH_SCHEMA_VERSION = 2
LEGACY_DISPATCH_SCHEMA_VERSION = 1
REQUEST_PREPARED = "REQUEST_PREPARED"
RESERVATION_COMMITTED = "RESERVATION_COMMITTED"
DISPATCH_STARTED = "DISPATCH_STARTED"
RESPONSE_OBSERVED = "RESPONSE_OBSERVED"
WAITING = "WAITING"
RESPONSE_AVAILABLE = "RESPONSE_AVAILABLE"
RESPONSE_RECOVERABLE = "RESPONSE_RECOVERABLE"
RESPONSE_MISSING = "RESPONSE_MISSING"
RECOVERED = "RECOVERED"
ABANDONED = "ABANDONED"
_FUNCTIONAL_STATES = {
    WAITING,
    RESPONSE_AVAILABLE,
    RESPONSE_RECOVERABLE,
    RESPONSE_MISSING,
    RECOVERED,
    ABANDONED,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dispatch_text(value: Any, *, field_name: str) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    return value


@dataclass(slots=True)
class DispatchRecord:
    """Versioned evidence for one physical provider dispatch."""

    physical_request_id: str
    logical_attempt_id: str
    provider: str
    model: str
    request_fingerprint: str
    client_correlation_id: str
    recovery_generation: int = 0
    recovery_of: str | None = None
    reservation_id: str | None = None
    reserved_cost: str | None = None
    provider_request_id: str | None = None
    provider_response_id: str | None = None
    response_status: str | None = None
    http_status: int | None = None
    sanitized_error: dict[str, Any] | None = None
    prepared_at: str = field(default_factory=_utc_now)
    reservation_committed_at: str | None = None
    dispatch_started_at: str | None = None
    completed_at: str | None = None
    dispatch_state: str = REQUEST_PREPARED
    functional_state: str = WAITING
    schema_version: int = DISPATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "physical_request_id", "logical_attempt_id", "provider", "model",
            "request_fingerprint", "client_correlation_id",
        ):
            setattr(self, field_name, _dispatch_text(getattr(self, field_name), field_name=field_name))
        if self.schema_version not in {LEGACY_DISPATCH_SCHEMA_VERSION, DISPATCH_SCHEMA_VERSION}:
            raise ValueError("unsupported dispatch schema version")
        if self.recovery_generation < 0:
            raise ValueError("recovery_generation must be non-negative")
        if self.recovery_generation == 0 and self.recovery_of is not None:
            raise ValueError("generation 0 cannot reference a recovery dispatch")
        if len(self.request_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.request_fingerprint.lower()
        ):
            raise ValueError("request_fingerprint must be a SHA-256 hex digest")
        if self.dispatch_state not in {REQUEST_PREPARED, RESERVATION_COMMITTED, DISPATCH_STARTED, RESPONSE_OBSERVED}:
            raise ValueError("unsupported dispatch state")
        if self.functional_state not in _FUNCTIONAL_STATES:
            raise ValueError("unsupported functional state")
        if self.dispatch_state in {RESERVATION_COMMITTED, DISPATCH_STARTED, RESPONSE_OBSERVED}:
            if not self.reservation_id or self.reservation_committed_at is None:
                raise ValueError("reserved dispatch requires reservation identity and timestamp")
        if self.dispatch_state in {DISPATCH_STARTED, RESPONSE_OBSERVED} and self.dispatch_started_at is None:
            raise ValueError("started dispatch requires dispatch timestamp")
        if self.http_status is not None and self.http_status < 100:
            raise ValueError("http_status must be a valid status code")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatch_schema_version": self.schema_version,
            "physical_request_id": self.physical_request_id,
            "logical_attempt_id": self.logical_attempt_id,
            "recovery_generation": self.recovery_generation,
            "recovery_of": self.recovery_of,
            "provider": self.provider,
            "model": self.model,
            "request_fingerprint": self.request_fingerprint,
            "client_correlation_id": self.client_correlation_id,
            "reservation_id": self.reservation_id,
            "reserved_cost": self.reserved_cost,
            "provider_request_id": self.provider_request_id,
            "provider_response_id": self.provider_response_id,
            "response_status": self.response_status,
            "http_status": self.http_status,
            "sanitized_error": self.sanitized_error,
            "prepared_at": self.prepared_at,
            "reservation_committed_at": self.reservation_committed_at,
            "dispatch_started_at": self.dispatch_started_at,
            "completed_at": self.completed_at,
            "dispatch_state": self.dispatch_state,
            "functional_state": self.functional_state,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DispatchRecord":
        required = {
            "dispatch_schema_version", "physical_request_id", "logical_attempt_id", "provider",
            "model", "request_fingerprint", "client_correlation_id", "recovery_generation",
            "recovery_of", "reservation_id", "reserved_cost", "provider_request_id",
            "provider_response_id", "response_status", "http_status", "sanitized_error",
            "prepared_at", "reservation_committed_at", "dispatch_started_at", "completed_at",
            "dispatch_state",
        }
        missing = sorted(key for key in required if key not in data)
        if missing:
            raise ValueError(f"incomplete dispatch schema: missing {', '.join(missing)}")
        sanitized_error = data["sanitized_error"]
        if sanitized_error is not None and not isinstance(sanitized_error, Mapping):
            raise ValueError("sanitized_error must be an object or null")
        schema_version = int(data["dispatch_schema_version"])
        if schema_version == LEGACY_DISPATCH_SCHEMA_VERSION:
            functional_state = str(data.get("functional_state", WAITING))
        else:
            if "functional_state" not in data:
                raise ValueError("incomplete dispatch schema: missing functional_state")
            functional_state = str(data["functional_state"])
        return cls(
            schema_version=schema_version,
            physical_request_id=str(data["physical_request_id"]),
            logical_attempt_id=str(data["logical_attempt_id"]),
            recovery_generation=int(data["recovery_generation"]),
            recovery_of=(str(data["recovery_of"]) if data["recovery_of"] is not None else None),
            provider=str(data["provider"]),
            model=str(data["model"]),
            request_fingerprint=str(data["request_fingerprint"]),
            client_correlation_id=str(data["client_correlation_id"]),
            reservation_id=(str(data["reservation_id"]) if data["reservation_id"] is not None else None),
            reserved_cost=(str(data["reserved_cost"]) if data["reserved_cost"] is not None else None),
            provider_request_id=(str(data["provider_request_id"]) if data["provider_request_id"] is not None else None),
            provider_response_id=(str(data["provider_response_id"]) if data["provider_response_id"] is not None else None),
            response_status=(str(data["response_status"]) if data["response_status"] is not None else None),
            http_status=(int(data["http_status"]) if data["http_status"] is not None else None),
            sanitized_error=dict(sanitized_error) if sanitized_error is not None else None,
            prepared_at=str(data["prepared_at"]),
            reservation_committed_at=(str(data["reservation_committed_at"]) if data["reservation_committed_at"] is not None else None),
            dispatch_started_at=(str(data["dispatch_started_at"]) if data["dispatch_started_at"] is not None else None),
            completed_at=(str(data["completed_at"]) if data["completed_at"] is not None else None),
            dispatch_state=str(data["dispatch_state"]),
            functional_state=functional_state,
        )


def _decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} must be Decimal-compatible") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return result


def _money(value: Decimal) -> str:
    """Serialize money without passing through a binary floating-point value."""
    return format(value, "f")


@dataclass(frozen=True, slots=True)
class LunaPricingSnapshot:
    """Frozen pricing rules shared by experimental and official wiring."""

    date: str = "2026-08-25"
    model: str = "gpt-5.6-luna"
    service_tier: str = "default"
    pricing_mode: str = "standard"
    short_context_input_per_million: Decimal = Decimal("0.20")
    short_context_cached_input_per_million: Decimal = Decimal("0.02")
    cache_write_multiplier: Decimal = Decimal("1.25")
    short_context_output_per_million: Decimal = Decimal("1.20")
    long_context_threshold_tokens: int = 272_000
    long_context_input_multiplier: Decimal = Decimal("2.0")
    long_context_output_multiplier: Decimal = Decimal("1.5")
    max_context_tokens: int = 1_050_000
    max_output_tokens: int = 128_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "model": self.model,
            "service_tier": self.service_tier,
            "pricing_mode": self.pricing_mode,
            "short_context_input_per_million": str(self.short_context_input_per_million),
            "short_context_cached_input_per_million": str(self.short_context_cached_input_per_million),
            "cache_write_multiplier": str(self.cache_write_multiplier),
            "short_context_output_per_million": str(self.short_context_output_per_million),
            "long_context_threshold_tokens": self.long_context_threshold_tokens,
            "long_context_input_multiplier": str(self.long_context_input_multiplier),
            "long_context_output_multiplier": str(self.long_context_output_multiplier),
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_tokens_billed_as": "output",
            "cache_write_policy": "disabled_explicit_mode_without_breakpoints",
            "hosted_tools_cost": "0; function tools only",
        }


@dataclass(slots=True)
class LunaEconomicState:
    """Serializable economic state for one candidate execution."""

    execution_id: str
    global_ceiling_usd: Decimal = LUNA_EXPERIMENTAL_HARD_BUDGET_USD
    attempt_ceiling_usd: Decimal = LUNA_PER_ATTEMPT_HARD_BUDGET_USD
    global_accumulated_usd: Decimal = Decimal("0")
    global_uncertain_consumed_usd: Decimal = Decimal("0")
    global_reserved_usd: Decimal = Decimal("0")
    active_attempt_id: str | None = None
    attempt_accumulated_usd: Decimal = Decimal("0")
    attempt_uncertain_consumed_usd: Decimal = Decimal("0")
    attempt_reserved_usd: Decimal = Decimal("0")
    physical_request_count: int = 0
    provider_retry_count: int = 0
    logical_provider_turn_count: int = 0
    ledger_version: int = 1
    reconciliation_state: str = "CLEAR"
    pause_reason: str | None = None
    pending_request_id: str | None = None
    ledger: dict[str, dict[str, Any]] = field(default_factory=dict)
    dispatch_records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.execution_id).strip():
            raise ValueError("execution_id must not be empty")
        self.global_ceiling_usd = _decimal(self.global_ceiling_usd, field_name="global_ceiling_usd")
        self.attempt_ceiling_usd = _decimal(self.attempt_ceiling_usd, field_name="attempt_ceiling_usd")
        self.global_accumulated_usd = _decimal(self.global_accumulated_usd, field_name="global_accumulated_usd")
        self.global_uncertain_consumed_usd = _decimal(self.global_uncertain_consumed_usd, field_name="global_uncertain_consumed_usd")
        self.global_reserved_usd = _decimal(self.global_reserved_usd, field_name="global_reserved_usd")
        self.attempt_accumulated_usd = _decimal(self.attempt_accumulated_usd, field_name="attempt_accumulated_usd")
        self.attempt_uncertain_consumed_usd = _decimal(self.attempt_uncertain_consumed_usd, field_name="attempt_uncertain_consumed_usd")
        self.attempt_reserved_usd = _decimal(self.attempt_reserved_usd, field_name="attempt_reserved_usd")
        if self.global_ceiling_usd <= 0 or self.attempt_ceiling_usd <= 0:
            raise ValueError("economic ceilings must be positive")
        if self.global_accumulated_usd + self.global_uncertain_consumed_usd + self.global_reserved_usd > self.global_ceiling_usd:
            raise ValueError("global economic reservation exceeds ceiling")
        if self.attempt_accumulated_usd + self.attempt_uncertain_consumed_usd + self.attempt_reserved_usd > self.attempt_ceiling_usd:
            raise ValueError("attempt economic reservation exceeds ceiling")
        if self.global_reserved_usd < 0 or self.attempt_reserved_usd < 0:
            raise ValueError("economic reservations must be non-negative")
        if self.physical_request_count < 0 or self.provider_retry_count < 0 or self.logical_provider_turn_count < 0:
            raise ValueError("economic counters must be non-negative")
        if not isinstance(self.dispatch_records, Mapping):
            raise ValueError("dispatch_records must be an object")
        for physical_request_id, record in self.dispatch_records.items():
            if str(physical_request_id) != str(record.get("physical_request_id")):
                raise ValueError("dispatch record identity mismatch")
            DispatchRecord.from_dict(record)

    @property
    def global_remaining_usd(self) -> Decimal:
        return self.global_ceiling_usd - self.global_accumulated_usd - self.global_uncertain_consumed_usd - self.global_reserved_usd

    @property
    def attempt_remaining_usd(self) -> Decimal:
        return self.attempt_ceiling_usd - self.attempt_accumulated_usd - self.attempt_uncertain_consumed_usd - self.attempt_reserved_usd

    def begin_attempt(self, attempt_id: str) -> None:
        attempt_id = str(attempt_id).strip()
        if not attempt_id:
            raise ValueError("attempt_id must not be empty")
        if self.active_attempt_id == attempt_id:
            return
        if self.active_attempt_id is not None and (
            self.attempt_reserved_usd
            or self.attempt_accumulated_usd
            or self.attempt_uncertain_consumed_usd
        ):
            raise ValueError("cannot replace an active economic attempt")
        self.active_attempt_id = attempt_id
        self.attempt_accumulated_usd = Decimal("0")
        self.attempt_uncertain_consumed_usd = Decimal("0")
        self.attempt_reserved_usd = Decimal("0")
        self.pending_request_id = None
        self.reconciliation_state = "CLEAR"
        self.pause_reason = None

    def end_attempt(self) -> None:
        if self.attempt_reserved_usd != 0:
            raise ValueError("cannot end an attempt with reserved cost")
        self.active_attempt_id = None
        self.pending_request_id = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "economic_schema_version": LUNA_ECONOMIC_SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "global_ceiling_usd": str(self.global_ceiling_usd),
            "global_accumulated_usd": str(self.global_accumulated_usd),
            "global_uncertain_consumed_usd": str(self.global_uncertain_consumed_usd),
            "global_reserved_usd": str(self.global_reserved_usd),
            "global_remaining_usd": str(self.global_remaining_usd),
            "active_attempt_id": self.active_attempt_id,
            "attempt_ceiling_usd": str(self.attempt_ceiling_usd),
            "attempt_accumulated_usd": str(self.attempt_accumulated_usd),
            "attempt_uncertain_consumed_usd": str(self.attempt_uncertain_consumed_usd),
            "attempt_reserved_usd": str(self.attempt_reserved_usd),
            "attempt_remaining_usd": str(self.attempt_remaining_usd),
            "physical_request_count": self.physical_request_count,
            "provider_retry_count": self.provider_retry_count,
            "logical_provider_turn_count": self.logical_provider_turn_count,
            "ledger_version": self.ledger_version,
            "reconciliation_state": self.reconciliation_state,
            "pause_reason": self.pause_reason,
            "pending_request_id": self.pending_request_id,
            "ledger": self.ledger,
            "dispatch_records": self.dispatch_records,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LunaEconomicState":
        required = {
            "economic_schema_version", "execution_id", "global_ceiling_usd", "global_accumulated_usd",
            "global_reserved_usd", "global_uncertain_consumed_usd", "active_attempt_id", "attempt_ceiling_usd", "attempt_accumulated_usd",
            "attempt_uncertain_consumed_usd",
            "attempt_reserved_usd", "physical_request_count", "provider_retry_count",
            "logical_provider_turn_count", "ledger_version", "reconciliation_state", "ledger",
            "global_remaining_usd", "attempt_remaining_usd",
        }
        missing = sorted(key for key in required if key not in data)
        if missing:
            raise ValueError(f"incomplete economic schema: missing {', '.join(missing)}")
        if int(data["economic_schema_version"]) != LUNA_ECONOMIC_SCHEMA_VERSION:
            raise ValueError("unsupported economic schema version")
        ledger = data["ledger"]
        if not isinstance(ledger, Mapping):
            raise ValueError("economic ledger must be an object")
        return cls(
            execution_id=str(data["execution_id"]),
            global_ceiling_usd=Decimal(str(data["global_ceiling_usd"])),
            global_accumulated_usd=Decimal(str(data["global_accumulated_usd"])),
            global_reserved_usd=Decimal(str(data["global_reserved_usd"])),
            global_uncertain_consumed_usd=Decimal(str(data["global_uncertain_consumed_usd"])),
            active_attempt_id=data.get("active_attempt_id"),
            attempt_ceiling_usd=Decimal(str(data["attempt_ceiling_usd"])),
            attempt_accumulated_usd=Decimal(str(data["attempt_accumulated_usd"])),
            attempt_uncertain_consumed_usd=Decimal(str(data["attempt_uncertain_consumed_usd"])),
            attempt_reserved_usd=Decimal(str(data["attempt_reserved_usd"])),
            physical_request_count=int(data["physical_request_count"]),
            provider_retry_count=int(data["provider_retry_count"]),
            logical_provider_turn_count=int(data["logical_provider_turn_count"]),
            ledger_version=int(data["ledger_version"]),
            reconciliation_state=str(data["reconciliation_state"]),
            pause_reason=data.get("pause_reason"),
            pending_request_id=data.get("pending_request_id"),
            ledger={str(key): dict(value) for key, value in ledger.items()},
            dispatch_records={
                str(key): dict(value)
                for key, value in dict(data.get("dispatch_records", {})).items()
            },
        )


class LunaEconomicStateStore:
    """Synchronous persistence boundary owned by the benchmark runner."""

    def __init__(self, state: LunaEconomicState, *, path: Path | None = None, persist_callback: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.state = state
        self.path = Path(path) if path is not None else None
        self.persist_callback = persist_callback

    def persist(self) -> None:
        payload = self.state.to_dict()
        if self.persist_callback is not None:
            self.persist_callback(payload)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            temporary.replace(self.path)

    @classmethod
    def load(cls, path: Path, *, persist_callback: Callable[[dict[str, Any]], None] | None = None) -> "LunaEconomicStateStore":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("economic state must be a JSON object")
        return cls(LunaEconomicState.from_dict(data), path=path, persist_callback=persist_callback)


@dataclass(slots=True)
class LunaBudgetGuard:
    """Fail-closed dual-ceiling guard for every physical Luna request."""

    hard_budget_usd: Decimal = LUNA_EXPERIMENTAL_HARD_BUDGET_USD
    pricing: LunaPricingSnapshot = field(default_factory=LunaPricingSnapshot)
    state: LunaEconomicState | None = None
    state_store: LunaEconomicStateStore | None = None
    experimental: bool = True
    non_official: bool = True
    last_reserve: Decimal | None = None
    last_decision: str | None = None
    abort_reason: str | None = None
    response_records: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.hard_budget_usd = _decimal(self.hard_budget_usd, field_name="hard_budget_usd")
        if self.state is None:
            self.state = LunaEconomicState(execution_id="unbound", global_ceiling_usd=self.hard_budget_usd)
        if self.state_store is None:
            self.state_store = LunaEconomicStateStore(self.state)
        if self.state_store.state is not self.state:
            self.state = self.state_store.state
        if self.state.global_ceiling_usd != self.hard_budget_usd:
            raise ValueError("state global ceiling does not match hard_budget_usd")

    @property
    def attempt_budget_usd(self) -> Decimal:
        return self.state.attempt_ceiling_usd

    @property
    def accumulated_cost_usd(self) -> Decimal:
        return self.state.global_accumulated_usd

    @property
    def attempt_accumulated_cost_usd(self) -> Decimal:
        return self.state.attempt_accumulated_usd

    @property
    def physical_request_count(self) -> int:
        return self.state.physical_request_count

    @property
    def provider_retry_count(self) -> int:
        return self.state.provider_retry_count

    @property
    def logical_provider_turn_count(self) -> int:
        return self.state.logical_provider_turn_count

    def begin_attempt(self, scheduled_attempt_id: str) -> None:
        self.state.begin_attempt(scheduled_attempt_id)
        self._persist()

    def end_attempt(self) -> None:
        self.state.end_attempt()
        self._persist()

    def begin_logical_turn(self) -> None:
        self.state.logical_provider_turn_count += 1
        self._persist()

    def prepare_dispatch(
        self,
        payload: Mapping[str, Any],
        *,
        provider: str,
        model: str,
        retry_count: int,
    ) -> DispatchRecord:
        """Persist REQUEST_PREPARED before reserving or crossing the provider boundary."""

        if self.abort_reason is not None:
            raise self._blocked(self.abort_reason)
        if self.state.active_attempt_id is None:
            self.begin_attempt("legacy-attempt")
        self._validate_state(retry_count=retry_count)
        physical_request_id = f"dispatch-{uuid4()}"
        record = DispatchRecord(
            physical_request_id=physical_request_id,
            logical_attempt_id=self.state.active_attempt_id,
            provider=provider,
            model=model,
            request_fingerprint=self._request_fingerprint(payload),
            client_correlation_id=f"corr-{uuid4()}",
        )
        self.state.dispatch_records[physical_request_id] = record.to_dict()
        self._persist()
        return record

    def before_request(
        self,
        payload: Mapping[str, Any],
        *,
        retry_count: int,
        dispatch_record: DispatchRecord | None = None,
    ) -> dict[str, Any]:
        if self.abort_reason is not None:
            raise self._blocked(self.abort_reason)
        if self.state.active_attempt_id is None:
            self.begin_attempt("legacy-attempt")
        if dispatch_record is None:
            dispatch_record = self.prepare_dispatch(
                payload,
                provider="unknown",
                model=str(payload.get("model", "unknown")),
                retry_count=retry_count,
            )
        self._validate_dispatch_record(dispatch_record)
        self._validate_state(retry_count=retry_count)
        input_tokens = self._conservative_input_tokens(payload)
        if input_tokens > self.pricing.max_context_tokens:
            raise self._abort("CONTEXT_BOUND_UNDETERMINED")
        reserve = self._worst_case_cost(input_tokens, payload)
        attempt_remaining = self.state.attempt_remaining_usd
        global_remaining = self.state.global_remaining_usd
        self.last_reserve = reserve
        allowed = reserve <= attempt_remaining and reserve <= global_remaining
        self.last_decision = "ALLOW" if allowed else "BLOCK"
        if not allowed:
            raise self._abort("BUDGET_BLOCKED")
        request_id = self._request_id(retry_count)
        self.state.ledger[request_id] = {
            "status": RESERVED,
            "attempt_id": self.state.active_attempt_id,
            "logical_turn": self.state.logical_provider_turn_count,
            "retry_ordinal": retry_count,
            "reservation_usd": str(reserve),
        }
        self.state.pending_request_id = request_id
        self.state.attempt_reserved_usd += reserve
        self.state.global_reserved_usd += reserve
        self.state.physical_request_count += 1
        self.state.provider_retry_count = max(self.state.provider_retry_count, retry_count)
        dispatch_record.reservation_id = request_id
        dispatch_record.reserved_cost = str(reserve)
        dispatch_record.reservation_committed_at = _utc_now()
        dispatch_record.dispatch_state = RESERVATION_COMMITTED
        self.state.dispatch_records[dispatch_record.physical_request_id] = dispatch_record.to_dict()
        self._persist()
        return {
            "request_id": request_id,
            "physical_request_id": dispatch_record.physical_request_id,
            "client_correlation_id": dispatch_record.client_correlation_id,
            "physical_request_count": self.state.physical_request_count,
            "provider_retry_count": self.state.provider_retry_count,
            "input_tokens_estimate": input_tokens,
            "projected_worst_case_cost_usd": str(reserve),
            "attempt_accumulated_usd": str(self.state.attempt_accumulated_usd),
            "attempt_remaining_usd": str(self.state.attempt_remaining_usd),
            "global_accumulated_usd": str(self.state.global_accumulated_usd),
            "global_remaining_usd": str(self.state.global_remaining_usd),
            "remaining_budget_usd": _money(self.state.global_remaining_usd),
            "decision": self.last_decision,
        }

    def mark_dispatch_started(self, dispatch_record: DispatchRecord) -> None:
        """Persist DISPATCH_STARTED immediately before crossing the SDK boundary."""

        self._validate_dispatch_record(dispatch_record)
        if dispatch_record.reservation_id is None or dispatch_record.dispatch_state != RESERVATION_COMMITTED:
            raise self._abort("DISPATCH_RESERVATION_NOT_COMMITTED")
        dispatch_record.dispatch_started_at = _utc_now()
        dispatch_record.dispatch_state = DISPATCH_STARTED
        self.state.dispatch_records[dispatch_record.physical_request_id] = dispatch_record.to_dict()
        self._persist()

    def abandon_pre_dispatch(self, dispatch_record: DispatchRecord, *, reason: str) -> None:
        """Record a proven pre-dispatch abandonment without touching accounting."""

        self._validate_dispatch_record(dispatch_record)
        if dispatch_record.dispatch_state != REQUEST_PREPARED or dispatch_record.reservation_id is not None:
            raise self._abort("DISPATCH_ALREADY_COMMITTED")
        self._transition_functional(dispatch_record, ABANDONED)
        dispatch_record.sanitized_error = {"kind": "pre_dispatch", "reason": str(reason)}
        dispatch_record.completed_at = _utc_now()
        self.state.dispatch_records[dispatch_record.physical_request_id] = dispatch_record.to_dict()
        self._persist()

    def record_dispatch_result(
        self,
        dispatch_record: DispatchRecord,
        *,
        provider_request_id: str | None = None,
        provider_response_id: str | None = None,
        response_status: str | None = None,
        http_status: int | None = None,
        sanitized_error: Mapping[str, Any] | None = None,
        completed: bool = False,
    ) -> None:
        """Persist provider metadata without changing economic settlement."""

        self._validate_dispatch_record(dispatch_record)
        if dispatch_record.dispatch_state not in {DISPATCH_STARTED, RESPONSE_OBSERVED}:
            raise self._abort("DISPATCH_NOT_STARTED")
        dispatch_record.provider_request_id = provider_request_id
        dispatch_record.provider_response_id = provider_response_id
        dispatch_record.response_status = response_status
        dispatch_record.http_status = http_status
        dispatch_record.sanitized_error = dict(sanitized_error) if sanitized_error is not None else None
        dispatch_record.completed_at = _utc_now() if completed else dispatch_record.completed_at
        dispatch_record.dispatch_state = RESPONSE_OBSERVED if completed else DISPATCH_STARTED
        self._transition_functional(dispatch_record, RESPONSE_AVAILABLE if completed else RESPONSE_MISSING)
        self.state.dispatch_records[dispatch_record.physical_request_id] = dispatch_record.to_dict()
        self._persist()

    def account_response(self, usage: Any, *, response_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        request_id = self.state.pending_request_id
        if request_id is None or request_id not in self.state.ledger:
            raise self._abort("UNKNOWN_RESERVED_REQUEST")
        entry = self.state.ledger[request_id]
        if entry.get("status") == ACCOUNTED:
            return dict(entry.get("settlement", {}))
        if entry.get("status") != RESERVED:
            raise self._abort("ECONOMIC_STATE_UNCERTAIN")
        normalized = self._usage_mapping(usage)
        input_tokens = self._required_int(normalized, "input_tokens")
        output_tokens = self._required_int(normalized, "output_tokens")
        total_tokens = self._required_int(normalized, "total_tokens")
        if total_tokens != input_tokens + output_tokens:
            raise self._abort("INCOHERENT_USAGE")
        cached_tokens = self._nested_int(normalized, "input_tokens_details", "cached_tokens")
        cache_write_tokens = self._nested_int(normalized, "input_tokens_details", "cache_write_tokens")
        if cached_tokens is None:
            cached_tokens = normalized.get("cached_input_tokens")
        if cache_write_tokens is None:
            cache_write_tokens = normalized.get("cache_write_tokens")
        reasoning_tokens = self._nested_int(normalized, "output_tokens_details", "reasoning_tokens")
        if reasoning_tokens is None:
            reasoning_tokens = normalized.get("reasoning_tokens", 0)
        if not isinstance(cached_tokens, int) or not isinstance(cache_write_tokens, int) or not isinstance(reasoning_tokens, int):
            raise self._abort("INCOHERENT_USAGE")
        if cached_tokens < 0 or cache_write_tokens < 0 or cached_tokens + cache_write_tokens > input_tokens or reasoning_tokens < 0 or reasoning_tokens > output_tokens:
            raise self._abort("INCOHERENT_USAGE")
        long_context = input_tokens > self.pricing.long_context_threshold_tokens
        input_rate = self.pricing.short_context_input_per_million
        cached_rate = self.pricing.short_context_cached_input_per_million
        output_rate = self.pricing.short_context_output_per_million
        cache_write_rate = input_rate * self.pricing.cache_write_multiplier
        if long_context:
            input_rate *= self.pricing.long_context_input_multiplier
            cached_rate *= self.pricing.long_context_input_multiplier
            cache_write_rate *= self.pricing.long_context_input_multiplier
            output_rate *= self.pricing.long_context_output_multiplier
        uncached_tokens = input_tokens - cached_tokens - cache_write_tokens
        derived = (
            Decimal(uncached_tokens) / Decimal(1_000_000) * input_rate
            + Decimal(cached_tokens) / Decimal(1_000_000) * cached_rate
            + Decimal(cache_write_tokens) / Decimal(1_000_000) * cache_write_rate
            + Decimal(output_tokens) / Decimal(1_000_000) * output_rate
        )
        reservation = Decimal(str(entry["reservation_usd"]))
        if derived > reservation:
            raise self._abort("RESERVATION_UNDERESTIMATED")
        projected_global = self.state.global_accumulated_usd + derived
        projected_attempt = self.state.attempt_accumulated_usd + derived
        if projected_global > self.state.global_ceiling_usd or projected_attempt > self.state.attempt_ceiling_usd:
            raise self._abort("ACCUMULATED_COST_EXCEEDED")
        self.state.global_reserved_usd -= reservation
        self.state.attempt_reserved_usd -= reservation
        self.state.global_accumulated_usd = projected_global
        self.state.attempt_accumulated_usd = projected_attempt
        record = {
            "request_id": request_id,
            "input_tokens": input_tokens,
            "cached_tokens": cached_tokens,
            "cache_write_tokens": cache_write_tokens,
            "uncached_input_tokens": uncached_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
            "long_context": long_context,
            "derived_cost_usd": _money(derived),
            "attempt_accumulated_usd": str(self.state.attempt_accumulated_usd),
            "attempt_remaining_usd": str(self.state.attempt_remaining_usd),
            "global_accumulated_usd": str(self.state.global_accumulated_usd),
            "global_remaining_usd": str(self.state.global_remaining_usd),
            "remaining_budget_usd": _money(self.state.global_remaining_usd),
        }
        entry["status"] = ACCOUNTED
        entry["actual_billed_cost_usd"] = str(derived)
        entry["conservative_budget_consumed_usd"] = str(reservation)
        if response_metadata:
            entry["response"] = {
                str(key): value
                for key, value in response_metadata.items()
                if key in {"response_id", "response_status", "service_tier"} and value is not None
            }
        entry["settlement"] = record
        self.state.pending_request_id = None
        self.state.reconciliation_state = "CLEAR"
        self.response_records.append(record)
        self._persist()
        return record

    def release_reservation(self, *, reason: str) -> dict[str, Any]:
        """Release only a reservation proven not to have reached the provider."""
        request_id = self.state.pending_request_id
        if not request_id or request_id not in self.state.ledger:
            raise self._abort("UNKNOWN_RESERVED_REQUEST")
        entry = self.state.ledger[request_id]
        if entry.get("status") != RESERVED:
            raise self._abort("ECONOMIC_STATE_UNCERTAIN")
        reservation = Decimal(str(entry["reservation_usd"]))
        self.state.global_reserved_usd -= reservation
        self.state.attempt_reserved_usd -= reservation
        entry["status"] = RELEASED
        entry["actual_billed_cost_usd"] = "0"
        entry["conservative_budget_consumed_usd"] = "0"
        entry["release_reason"] = str(reason)
        self.state.pending_request_id = None
        self.state.reconciliation_state = "CLEAR"
        self._persist()
        return {"request_id": request_id, "status": RELEASED, "released_usd": str(reservation)}

    def on_failure_without_usage(self, *, retry_count: int, failure: Mapping[str, Any] | None = None) -> None:
        """Settle a dispatched request conservatively when billable usage is unknown."""
        self.state.provider_retry_count = max(self.state.provider_retry_count, retry_count)
        if self.state.pending_request_id is not None:
            entry = self.state.ledger[self.state.pending_request_id]
            if entry.get("status") == RESERVED:
                reservation = Decimal(str(entry["reservation_usd"]))
                self.state.global_reserved_usd -= reservation
                self.state.attempt_reserved_usd -= reservation
                self.state.global_uncertain_consumed_usd += reservation
                self.state.attempt_uncertain_consumed_usd += reservation
                entry["status"] = UNCERTAIN_CONSUMED
                entry["actual_billed_cost_usd"] = None
                entry["conservative_budget_consumed_usd"] = str(reservation)
                if failure:
                    entry["sanitized_failure"] = dict(failure)
            self.state.reconciliation_state = "UNCERTAIN_CONSUMED"
            self.state.pause_reason = "ECONOMIC_BUDGET_BLOCKED"
            self.state.pending_request_id = None
            self._persist()
        error = self._abort("UNKNOWN_BILLABLE_USAGE")
        if failure:
            error.details["original_failure"] = dict(failure)
        raise error

    def metadata(self) -> dict[str, Any]:
        pricing_payload = json.dumps(self.pricing.to_dict(), sort_keys=True, separators=(",", ":"))
        settlements = [
            dict(entry["settlement"])
            for entry in self.state.ledger.values()
            if entry.get("status") == "ACCOUNTED" and isinstance(entry.get("settlement"), Mapping)
        ]
        return {
            "experimental": self.experimental,
            "non_official": self.non_official,
            "hard_budget_usd": _money(self.state.global_ceiling_usd),
            "attempt_budget_usd": _money(self.state.attempt_ceiling_usd),
            "pricing_snapshot": self.pricing.to_dict(),
            "pricing_snapshot_hash": hashlib.sha256(pricing_payload.encode("utf-8")).hexdigest(),
            "economic_schema_version": LUNA_ECONOMIC_SCHEMA_VERSION,
            "execution_id": self.state.execution_id,
            "active_attempt_id": self.state.active_attempt_id,
            "logical_provider_turn_count": self.state.logical_provider_turn_count,
            "physical_request_count": self.state.physical_request_count,
            "provider_retry_count": self.state.provider_retry_count,
            "accumulated_cost_usd": _money(self.state.global_accumulated_usd),
            "actual_billed_cost_usd": _money(self.state.global_accumulated_usd),
            "conservative_budget_consumed_usd": _money(self.state.global_accumulated_usd + self.state.global_uncertain_consumed_usd),
            "global_uncertain_consumed_usd": _money(self.state.global_uncertain_consumed_usd),
            "remaining_budget_usd": _money(self.state.global_remaining_usd),
            "attempt_accumulated_usd": _money(self.state.attempt_accumulated_usd),
            "attempt_remaining_usd": _money(self.state.attempt_remaining_usd),
            "global_reserved_usd": _money(self.state.global_reserved_usd),
            "attempt_reserved_usd": _money(self.state.attempt_reserved_usd),
            "attempt_uncertain_consumed_usd": _money(self.state.attempt_uncertain_consumed_usd),
            "last_reserve_usd": _money(self.last_reserve) if self.last_reserve is not None else None,
            "last_budget_decision": self.last_decision,
            "abort_reason": self.abort_reason,
            "reconciliation_state": self.state.reconciliation_state,
            "economic_settlement_count": len(settlements),
            "economic_settlements": settlements,
            "dispatch_records": [dict(record) for record in self.state.dispatch_records.values()],
        }

    def _persist(self) -> None:
        if self.state_store is None:
            raise self._abort("ECONOMIC_STATE_STORE_MISSING")
        try:
            self.state_store.persist()
        except Exception as exc:
            self.abort_reason = "ECONOMIC_STATE_PERSISTENCE_FAILED"
            raise ProviderError(
                "Luna economic state persistence failed before provider access",
                kind="budget_blocked",
                provider="openai",
                retryable=False,
                details={"abort_reason": self.abort_reason},
            ) from exc

    def _request_id(self, retry_count: int) -> str:
        return f"{self.state.execution_id}:{self.state.active_attempt_id}:{self.state.logical_provider_turn_count}:{self.state.physical_request_count + 1}:{retry_count}"

    def _request_fingerprint(self, payload: Mapping[str, Any]) -> str:
        try:
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise self._abort("REQUEST_FINGERPRINT_UNSERIALIZABLE") from exc
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _validate_dispatch_record(self, dispatch_record: DispatchRecord) -> None:
        if not isinstance(dispatch_record, DispatchRecord):
            raise self._abort("DISPATCH_RECORD_INVALID")
        stored = self.state.dispatch_records.get(dispatch_record.physical_request_id)
        if stored is None:
            raise self._abort("DISPATCH_RECORD_MISSING")
        try:
            persisted = DispatchRecord.from_dict(stored)
        except (TypeError, ValueError) as exc:
            raise self._abort("DISPATCH_RECORD_INVALID") from exc
        if persisted.to_dict() != dispatch_record.to_dict():
            raise self._abort("DISPATCH_RECORD_IDENTITY_MISMATCH")

    def _transition_functional(self, dispatch_record: DispatchRecord, target: str) -> None:
        if target not in _FUNCTIONAL_STATES:
            raise self._abort("FUNCTIONAL_STATE_INVALID")
        allowed = {
            WAITING: {RESPONSE_AVAILABLE, RESPONSE_MISSING, ABANDONED},
        }
        if target not in allowed.get(dispatch_record.functional_state, set()):
            raise self._abort("FUNCTIONAL_STATE_TRANSITION_INVALID")
        dispatch_record.functional_state = target

    def _conservative_input_tokens(self, payload: Mapping[str, Any]) -> int:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return len(encoded)

    def _worst_case_cost(self, input_tokens: int, payload: Mapping[str, Any] | None = None) -> Decimal:
        long_context = input_tokens > self.pricing.long_context_threshold_tokens
        input_rate = self.pricing.short_context_input_per_million
        output_rate = self.pricing.short_context_output_per_million
        cache_write_rate = input_rate * self.pricing.cache_write_multiplier
        if long_context:
            input_rate *= self.pricing.long_context_input_multiplier
            cache_write_rate *= self.pricing.long_context_input_multiplier
            output_rate *= self.pricing.long_context_output_multiplier
        output_limit = self.pricing.max_output_tokens
        if payload is not None and isinstance(payload.get("max_output_tokens"), int) and not isinstance(payload.get("max_output_tokens"), bool):
            output_limit = payload["max_output_tokens"]
        if output_limit < 0:
            raise self._abort("UNKNOWN_OUTPUT_LIMIT")
        return (
            Decimal(input_tokens) / Decimal(1_000_000) * max(input_rate, cache_write_rate)
            + Decimal(output_limit) / Decimal(1_000_000) * output_rate
        )

    def _validate_state(self, *, retry_count: int) -> None:
        if retry_count < 0 or retry_count > self.state.physical_request_count:
            raise self._abort("PHYSICAL_COUNTER_INCOHERENT")
        if self.state.global_accumulated_usd < 0 or self.state.global_accumulated_usd > self.state.global_ceiling_usd:
            raise self._abort("ACCUMULATED_COST_EXCEEDED")
        if self.state.attempt_accumulated_usd < 0 or self.state.attempt_accumulated_usd > self.state.attempt_ceiling_usd:
            raise self._abort("ACCUMULATED_COST_EXCEEDED")

    def _usage_mapping(self, usage: Any) -> dict[str, Any]:
        if isinstance(usage, Mapping):
            return dict(usage)
        if hasattr(usage, "model_dump") and callable(usage.model_dump):
            dumped = usage.model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        if hasattr(usage, "to_dict") and callable(usage.to_dict):
            dumped = usage.to_dict()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        raise self._abort("UNKNOWN_BILLABLE_USAGE")

    def _nested_int(self, value: Mapping[str, Any], parent: str, key: str) -> int | None:
        child = value.get(parent)
        if isinstance(child, Mapping):
            raw = child.get(key)
            return raw if isinstance(raw, int) and not isinstance(raw, bool) else None
        return None

    def _required_int(self, value: Mapping[str, Any], key: str) -> int:
        raw = value.get(key)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            raise self._abort("UNKNOWN_BILLABLE_USAGE")
        return raw

    def _abort(self, reason: str) -> ProviderError:
        self.abort_reason = reason
        return ProviderError(
            f"Luna budget guard blocked: {reason}",
            kind="budget_blocked",
            provider="openai",
            retryable=False,
            details={
                "experimental": self.experimental,
                "non_official": self.non_official,
                "abort_reason": reason,
                "economic_pause": reason == "BUDGET_BLOCKED",
            },
        )

    def _blocked(self, reason: str) -> ProviderError:
        return self._abort(reason)


def build_luna_experimental_manifest(
    *,
    execution_id: str,
    run_id: str,
    launch_root: str,
    task_id: str,
    task_version: str,
    hard_budget_usd: Decimal = LUNA_EXPERIMENTAL_HARD_BUDGET_USD,
    attempt_budget_usd: Decimal = LUNA_PER_ATTEMPT_HARD_BUDGET_USD,
    pricing: LunaPricingSnapshot = LunaPricingSnapshot(),
) -> dict[str, Any]:
    """Build safe, non-official identity metadata for a future smoke."""

    return {
        "schema_version": 1,
        "economic_schema_version": LUNA_ECONOMIC_SCHEMA_VERSION,
        "execution_id": execution_id,
        "run_id": run_id,
        "launch_root": launch_root,
        "dataset_id": "PD_AGENT_BENCHMARK_DATASET_V0.5_5",
        "task_id": task_id,
        "task_version": task_version,
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "medium",
        "experimental": True,
        "non_official": True,
        "hard_budget_usd": _money(_decimal(hard_budget_usd, field_name="hard_budget_usd")),
        "attempt_budget_usd": _money(_decimal(attempt_budget_usd, field_name="attempt_budget_usd")),
        "service_tier_requested": pricing.service_tier,
        "pricing_mode": pricing.pricing_mode,
        "pricing_snapshot_date": pricing.date,
        "pricing_snapshot": pricing.to_dict(),
        "cache_write_policy": "disabled_explicit_mode_without_breakpoints",
        "official_repetition": None,
        "official_attempt": None,
        "replacement": False,
    }
