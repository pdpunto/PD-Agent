from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pd_agent.bootstrap import build_runtime_bundle
from pd_agent.cli import main
from pd_agent.config import AppConfig
from pd_agent.core.errors import ConfigurationError
from pd_agent.experimental import LunaEconomicState, LunaEconomicStateStore, LunaSharedBudgetSession
from pd_agent.product import ExecutionService, ProductCatalog, build_product_application
from pd_agent.product.models import ExecutionRecord, ProjectRecord, TaskRecord
from pd_agent.reporting import RunStorage
from pd_agent.web import WebServices


def _session(tmp_path: Path, *, ceiling: str = "0.50") -> LunaSharedBudgetSession:
    return LunaSharedBudgetSession.create(tmp_path / "economic.json", session_id="shared-test", global_ceiling=ceiling)


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        provider="openai",
        model="gpt-5.6-luna",
        openai_api_key="sk-offline-r12",
        runs_dir=tmp_path / "runs",
    )


def test_shared_session_is_the_only_productive_budget_authority(tmp_path: Path) -> None:
    session = _session(tmp_path)
    bundle = build_runtime_bundle(
        _config(tmp_path),
        storage=RunStorage(tmp_path / "runs"),
        economic_budget_usd="0.50",
        economic_session=session,
    )

    guard = bundle.provider.budget_guard
    assert guard.state is session.state
    assert guard.shared_session_id == "shared-test"
    assert guard.attempt_budget_usd == Decimal("0.10")
    assert bundle.economic_session is session


def test_product_application_forwards_shared_session_without_parallel_guard(tmp_path: Path) -> None:
    session = _session(tmp_path)
    application = build_product_application(
        _config(tmp_path),
        economic_budget_usd="0.50",
        economic_session=session,
        product_data_root=tmp_path / "product-data",
    )
    try:
        assert application.runtime.economic_session is session
        assert application.runtime.provider.budget_guard.state is session.state
        assert application.runtime.provider.budget_guard.attempt_budget_usd == Decimal("0.10")
    finally:
        application.shutdown()


def test_web_cli_loads_shared_state_and_fails_closed_for_unusable_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session(tmp_path)
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict[str, object] = {}

    class Application:
        web_services = WebServices()

        def shutdown(self) -> None:
            pass

    monkeypatch.setenv("OPENAI_API_KEY", "sk-offline-r12")
    monkeypatch.setenv("PD_AGENT_MODEL", "gpt-5.6-luna")
    result = main(
        [
            "web",
            "--frontend-dist", str(frontend),
            "--economic-state", str(session.path),
            "--economic-budget-usd", "0.50",
            "--port", "8765",
        ],
        application_factory=lambda _config, **kwargs: (captured.update(kwargs) or Application()),
        server_runner=lambda _app, **kwargs: captured.update(server=kwargs),
    )
    assert result == 0
    loaded = captured["economic_session"]
    assert isinstance(loaded, LunaSharedBudgetSession)
    assert loaded.state is not session.state
    assert loaded.state.global_ceiling_usd == Decimal("0.50")

    bad_state = LunaEconomicState(
        execution_id="bad",
        global_ceiling_usd=Decimal("0.50"),
        active_attempt_id="active",
        attempt_lifecycle="ACTIVE",
    )
    bad_path = tmp_path / "bad.json"
    LunaEconomicStateStore(bad_state, path=bad_path).persist()
    blocked = main(
        ["web", "--frontend-dist", str(frontend), "--economic-state", str(bad_path), "--economic-budget-usd", "0.50"],
        application_factory=lambda *_args, **_kwargs: pytest.fail("unusable state was composed"),
        server_runner=lambda *_args, **_kwargs: None,
    )
    assert blocked == 2


def test_execution_service_claims_and_completes_shared_ownership(tmp_path: Path) -> None:
    session = _session(tmp_path)
    storage = RunStorage(tmp_path / "runs")
    guard = session.guard(consumer_id="web", experimental=True, non_official=True)
    observed: dict[str, object] = {}

    class Runner:
        def run(self, execution, _project, _task):  # noqa: ANN001
            observed["execution_id"] = execution.execution_id
            observed["ownership"] = dict(guard.state.attempt_ownership or {})
            return SimpleNamespace(run_id=execution.run_id)

    service = ExecutionService(
        ProductCatalog(tmp_path / "product-data"),
        SimpleNamespace(provider=SimpleNamespace(budget_guard=guard), storage=storage),
        product_runner=Runner(),
    )
    execution = ExecutionRecord(task_id=str(uuid4()))
    project = ProjectRecord(name="test", workspace_ref=str(tmp_path))
    task = TaskRecord(project_id=project.project_id, task_id=execution.task_id, request="test")
    try:
        service._run_worker(execution, task, project)  # noqa: SLF001
        assert observed["execution_id"] == execution.execution_id
        assert observed["ownership"]["run_id"] == execution.run_id
        assert guard.state.attempt_lifecycle == "COMPLETED"
        assert guard.state.active_attempt_id is None
        assert guard._ownership is None  # noqa: SLF001
    finally:
        service.shutdown()


def test_unresolved_provider_failure_releases_lock_but_preserves_recovery_state(tmp_path: Path) -> None:
    session = _session(tmp_path)
    storage = RunStorage(tmp_path / "runs")
    guard = session.guard(consumer_id="web", experimental=True, non_official=True)

    class Runner:
        def run(self, *_args):
            guard.state.attempt_uncertain_consumed_usd = Decimal("0.01")
            guard.state.global_uncertain_consumed_usd = Decimal("0.01")
            guard.state_store.persist()
            raise RuntimeError("provider transport")

    service = ExecutionService(
        ProductCatalog(tmp_path / "product-data"),
        SimpleNamespace(provider=SimpleNamespace(budget_guard=guard), storage=storage),
        product_runner=Runner(),
    )
    execution = ExecutionRecord(task_id=str(uuid4()))
    project = ProjectRecord(name="test", workspace_ref=str(tmp_path))
    task = TaskRecord(project_id=project.project_id, task_id=execution.task_id, request="test")
    with pytest.raises(RuntimeError):
        service._run_worker(execution, task, project)  # noqa: SLF001
    try:
        assert guard.state.active_attempt_id == execution.execution_id
        assert guard.state.attempt_lifecycle == "ACTIVE"
        assert guard._ownership is None  # noqa: SLF001
    finally:
        service.shutdown()


def test_shared_ceiling_mismatch_is_rejected_before_composition(tmp_path: Path) -> None:
    session = _session(tmp_path, ceiling="0.50")
    with pytest.raises(ConfigurationError, match="ceiling"):
        build_runtime_bundle(_config(tmp_path), economic_budget_usd="0.70", economic_session=session)


def test_web_shared_state_keeps_attempt_ceiling_separate_from_global(tmp_path: Path) -> None:
    session = _session(tmp_path, ceiling="0.70")
    bundle = build_runtime_bundle(_config(tmp_path), economic_session=session)
    guard = bundle.provider.budget_guard
    preview = guard.preview_budget(input_tokens=1, output_limit=1)
    assert guard.hard_budget_usd == Decimal("0.70")
    assert guard.attempt_budget_usd == Decimal("0.10")
    assert Decimal(preview["attempt_remaining_usd"]) == Decimal("0.10")


def test_web_attempt_ceiling_is_configured_and_reopened_without_history_change(tmp_path: Path) -> None:
    session = _session(tmp_path, ceiling="0.70")
    before = (session.state.global_accumulated_usd, len(session.state.ledger), len(session.state.dispatch_records))
    bundle = build_runtime_bundle(
        _config(tmp_path),
        economic_budget_usd="0.70",
        economic_session=session,
        attempt_ceiling_usd="0.09",
    )
    assert bundle.provider.budget_guard.attempt_budget_usd == Decimal("0.09")
    reopened = LunaSharedBudgetSession.load(session.path, expected_global_ceiling="0.70")
    assert reopened.state.attempt_ceiling_usd == Decimal("0.09")
    assert (reopened.state.global_accumulated_usd, len(reopened.state.ledger), len(reopened.state.dispatch_records)) == before
    guard = reopened.guard(consumer_id="r22-r1", experimental=True, non_official=True)
    guard.begin_attempt("r22-r1-attempt")
    guard.end_attempt()
    assert LunaSharedBudgetSession.load(session.path).state.attempt_ceiling_usd == Decimal("0.09")


def test_web_attempt_ceiling_cannot_exceed_global_remaining(tmp_path: Path) -> None:
    session = LunaSharedBudgetSession.create(
        tmp_path / "economic.json",
        session_id="shared-test",
        global_ceiling="0.70",
    )
    session.state.global_accumulated_usd = Decimal("0.62")
    session.store.persist()
    with pytest.raises(ConfigurationError, match="remaining global"):
        build_runtime_bundle(
            _config(tmp_path),
            economic_budget_usd="0.70",
            economic_session=session,
            attempt_ceiling_usd="0.09",
        )


@pytest.mark.parametrize("value", ["0", "-0.01", "NaN", "Infinity", "-Infinity", "not-money"])
def test_web_attempt_ceiling_rejects_invalid_values(tmp_path: Path, value: str) -> None:
    session = _session(tmp_path, ceiling="0.70")
    with pytest.raises(ConfigurationError):
        build_runtime_bundle(
            _config(tmp_path),
            economic_budget_usd="0.70",
            economic_session=session,
            attempt_ceiling_usd=value,
        )
    assert session.state.attempt_ceiling_usd == Decimal("0.10")


def test_web_cli_forwards_attempt_ceiling_to_product_composition(tmp_path: Path) -> None:
    session = _session(tmp_path, ceiling="0.70")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    captured: dict[str, object] = {}

    class Application:
        web_services = WebServices()

        def shutdown(self) -> None:
            pass

    result = main(
        [
            "web",
            "--frontend-dist", str(frontend),
            "--economic-state", str(session.path),
            "--economic-budget-usd", "0.70",
            "--attempt-ceiling-usd", "0.09",
        ],
        application_factory=lambda _config, **kwargs: (captured.update(kwargs) or Application()),
        server_runner=lambda _app, **kwargs: None,
    )
    assert result == 0
    assert captured["attempt_ceiling_usd"] == "0.09"
