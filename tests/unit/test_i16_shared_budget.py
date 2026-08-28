from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pd_agent.core.errors import ProviderError
from pd_agent.experimental import (
    ACCOUNTED,
    I16_SHARED_GLOBAL_CEILING_USD,
    RESERVED,
    UNCERTAIN_CONSUMED,
    LunaEconomicState,
    LunaEconomicStateStore,
    LunaSharedBudgetSession,
)


def _payload() -> dict[str, object]:
    return {"model": "gpt-5.6-luna", "messages": ["hello"], "max_output_tokens": 100}


def _usage() -> dict[str, object]:
    return {
        "input_tokens": 10,
        "output_tokens": 1,
        "total_tokens": 11,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }


def _account(guard, attempt_id: str) -> None:
    guard.begin_attempt(attempt_id)
    payload = _payload()
    record = guard.prepare_dispatch(payload, provider="openai", model="gpt-5.6-luna", retry_count=0)
    guard.before_request(payload, retry_count=0, dispatch_record=record)
    guard.account_response(_usage())
    guard.end_attempt()


def test_shared_session_uses_fixed_global_ceiling_and_separate_consumers(tmp_path: Path) -> None:
    session = LunaSharedBudgetSession.create(tmp_path / "economic.json")
    on = session.guard(consumer_id="brain-on")
    _account(on, "on-attempt")

    reopened = LunaSharedBudgetSession.load(tmp_path / "economic.json")
    off = reopened.guard(consumer_id="brain-off")
    metadata = off.metadata()
    assert metadata["hard_budget_usd"] == "0.25"
    assert reopened.state.global_remaining_usd < I16_SHARED_GLOBAL_CEILING_USD
    assert metadata["shared_session_id"] == session.session_id
    assert metadata["shared_consumption_by_consumer"]["brain-on"] != "0"


def test_shared_session_accepts_configurable_global_ceiling_and_expected_load(tmp_path: Path) -> None:
    path = tmp_path / "economic.json"
    session = LunaSharedBudgetSession.create(path, global_ceiling=Decimal("0.30"))
    reopened = LunaSharedBudgetSession.load(path, expected_global_ceiling=Decimal("0.30"))
    assert reopened.ceiling_usd == Decimal("0.30")
    assert reopened.state.attempt_ceiling_usd == Decimal("0.10")


def test_shared_session_rejects_expected_ceiling_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "economic.json"
    LunaSharedBudgetSession.create(path, global_ceiling=Decimal("0.30"))
    with pytest.raises(ValueError, match="shared economic ceiling mismatch"):
        LunaSharedBudgetSession.load(path, expected_global_ceiling=Decimal("0.25"))


def test_global_ceiling_migration_is_upward_only_and_preserves_history(tmp_path: Path) -> None:
    path = tmp_path / "economic.json"
    session = LunaSharedBudgetSession.create(path)
    _account(session.guard(consumer_id="brain-on"), "attempt")
    before = session.state.to_dict()
    result = session.migrate_global_ceiling(Decimal("0.30"))
    reopened = LunaSharedBudgetSession.load(path, expected_global_ceiling=Decimal("0.30"))
    assert result == {"previous": "0.25", "current": "0.30", "changed": "true"}
    assert reopened.state.global_accumulated_usd == Decimal(before["global_accumulated_usd"])
    assert reopened.state.physical_request_count == before["physical_request_count"]
    assert reopened.state.logical_provider_turn_count == before["logical_provider_turn_count"]
    assert reopened.state.attempt_ceiling_usd == Decimal("0.10")
    with pytest.raises(ValueError, match="upward-only"):
        reopened.migrate_global_ceiling(Decimal("0.20"))


def test_global_ceiling_migration_rejects_reservation_and_uncertainty(tmp_path: Path) -> None:
    path = tmp_path / "economic.json"
    session = LunaSharedBudgetSession.create(path)
    guard = session.guard(consumer_id="brain-on")
    guard.begin_attempt("attempt")
    payload = _payload()
    record = guard.prepare_dispatch(payload, provider="openai", model="gpt-5.6-luna", retry_count=0)
    guard.before_request(payload, retry_count=0, dispatch_record=record)
    with pytest.raises(ValueError, match="reservation or uncertainty"):
        session.migrate_global_ceiling(Decimal("0.30"))


def test_global_ceiling_rejects_non_positive_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        LunaSharedBudgetSession.create(tmp_path / "zero.json", global_ceiling=Decimal("0"))
    session = LunaSharedBudgetSession.create(tmp_path / "economic.json")
    with pytest.raises(ValueError, match="upward-only"):
        session.migrate_global_ceiling(Decimal("0"))


def test_shared_session_never_allows_global_ceiling_overrun(tmp_path: Path) -> None:
    session = LunaSharedBudgetSession.create(tmp_path / "economic.json")
    session.state.global_accumulated_usd = Decimal("0.24999")
    session.store.persist()
    guard = session.guard(consumer_id="brain-off")
    guard.begin_attempt("off-attempt")
    payload = _payload()
    record = guard.prepare_dispatch(payload, provider="openai", model="gpt-5.6-luna", retry_count=0)
    with pytest.raises(ProviderError) as error:
        guard.before_request(payload, retry_count=0, dispatch_record=record)
    assert error.value.details["abort_reason"] == "BUDGET_BLOCKED"
    assert guard.state.physical_request_count == 0


def test_shared_retry_uses_same_global_authority(tmp_path: Path) -> None:
    session = LunaSharedBudgetSession.create(tmp_path / "economic.json")
    guard = session.guard(consumer_id="brain-on")
    guard.begin_attempt("attempt")
    payload = _payload()
    first = guard.prepare_dispatch(payload, provider="openai", model="gpt-5.6-luna", retry_count=0)
    guard.before_request(payload, retry_count=0, dispatch_record=first)
    guard.mark_dispatch_started(first)
    guard.account_response(_usage())
    second = guard.prepare_dispatch(payload, provider="openai", model="gpt-5.6-luna", retry_count=1)
    guard.before_request(payload, retry_count=1, dispatch_record=second)
    assert guard.state.ledger[second.reservation_id]["status"] == RESERVED
    assert guard.state.global_reserved_usd > 0


def test_shared_uncertain_consumption_is_preserved_on_reopen(tmp_path: Path) -> None:
    path = tmp_path / "economic.json"
    session = LunaSharedBudgetSession.create(path)
    guard = session.guard(consumer_id="brain-on")
    guard.begin_attempt("attempt")
    payload = _payload()
    record = guard.prepare_dispatch(payload, provider="openai", model="gpt-5.6-luna", retry_count=0)
    guard.before_request(payload, retry_count=0, dispatch_record=record)
    with pytest.raises(ProviderError) as error:
        guard.on_failure_without_usage(retry_count=0, failure={"kind": "transport"})
    assert error.value.details["abort_reason"] == "UNKNOWN_BILLABLE_USAGE"
    reopened = LunaSharedBudgetSession.load(path)
    assert reopened.state.global_uncertain_consumed_usd > 0
    assert next(iter(reopened.state.ledger.values()))["status"] == UNCERTAIN_CONSUMED


def test_shared_accounting_is_idempotent_and_does_not_double_count(tmp_path: Path) -> None:
    session = LunaSharedBudgetSession.create(tmp_path / "economic.json")
    guard = session.guard(consumer_id="brain-on")
    guard.begin_attempt("attempt")
    payload = _payload()
    record = guard.prepare_dispatch(payload, provider="openai", model="gpt-5.6-luna", retry_count=0)
    guard.before_request(payload, retry_count=0, dispatch_record=record)
    first = guard.account_response(_usage())
    accumulated = guard.state.global_accumulated_usd
    guard.state_store.persist()
    second = guard.state.global_accumulated_usd
    assert first["derived_cost_usd"] == str(accumulated)
    assert second == accumulated
    assert next(iter(guard.state.ledger.values()))["status"] == ACCOUNTED


def test_shared_state_reopen_does_not_reset_consumption(tmp_path: Path) -> None:
    path = tmp_path / "economic.json"
    session = LunaSharedBudgetSession.create(path)
    _account(session.guard(consumer_id="brain-on"), "on-attempt")
    consumed = session.state.global_accumulated_usd
    reopened = LunaSharedBudgetSession.load(path)
    assert reopened.state.global_accumulated_usd == consumed
    assert reopened.state.global_accumulated_usd > 0


def test_shared_state_persistence_failure_is_fail_closed(tmp_path: Path) -> None:
    state = LunaEconomicState(execution_id="session", global_ceiling_usd=Decimal("0.25"))
    store = LunaEconomicStateStore(state, persist_callback=lambda _: (_ for _ in ()).throw(OSError("disk")))
    session = LunaSharedBudgetSession("session", state, store)
    guard = session.guard(consumer_id="brain-on")
    with pytest.raises(ProviderError) as error:
        guard.begin_attempt("attempt")
    assert error.value.details["abort_reason"] == "ECONOMIC_STATE_PERSISTENCE_FAILED"


def test_shared_state_rejects_wrong_ceiling(tmp_path: Path) -> None:
    path = tmp_path / "economic.json"
    state = LunaEconomicState(execution_id="session", global_ceiling_usd=Decimal("0.30"))
    LunaEconomicStateStore(state, path=path).persist()
    with pytest.raises(ValueError, match="shared economic ceiling mismatch"):
        LunaSharedBudgetSession.load(path, expected_global_ceiling=Decimal("0.25"))
