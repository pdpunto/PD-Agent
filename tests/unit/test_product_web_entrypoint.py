from __future__ import annotations

from pathlib import Path

import pytest

from pd_agent.cli import EXIT_CONFIG_ERROR, EXIT_OK, main
from pd_agent.web import WebServices, create_app


def test_web_entrypoint_constructs_product_application_and_does_not_run_task(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<main>PD Agent</main>", encoding="utf-8")
    calls: list[tuple[object, str, int]] = []
    shutdowns: list[int] = []

    class Application:
        web_services = WebServices()

        def shutdown(self) -> None:
            shutdowns.append(1)

    def factory(config, **kwargs):  # noqa: ANN001
        assert config.provider == "openai"
        assert kwargs["economic_budget_usd"] is None
        assert kwargs["attempt_ceiling_usd"] is None
        return Application()

    def server(app, *, host: str, port: int) -> None:  # noqa: ANN001
        calls.append((app, host, port))

    result = main(
        ["web", "--frontend-dist", str(frontend), "--port", "8765"],
        application_factory=factory,
        server_runner=server,
    )

    assert result == EXIT_OK
    assert calls[0][1:] == ("127.0.0.1", 8765)
    assert shutdowns == [1]


@pytest.mark.parametrize("argv", [["web", "--host", "0.0.0.0"], ["web", "--port", "0"]])
def test_web_entrypoint_rejects_unsafe_or_invalid_network_config(argv: list[str], tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    assert main([*argv, "--frontend-dist", str(frontend)], application_factory=lambda *_args, **_kwargs: None, server_runner=lambda *_args, **_kwargs: None) == EXIT_CONFIG_ERROR


def test_web_entrypoint_rejects_missing_frontend_before_construction(tmp_path: Path) -> None:
    constructed: list[bool] = []

    def factory(*_args, **_kwargs):  # noqa: ANN001
        constructed.append(True)
        raise AssertionError("application must not be constructed")

    assert main(["web", "--frontend-dist", str(tmp_path / "missing")], application_factory=factory, server_runner=lambda *_args, **_kwargs: None) == EXIT_CONFIG_ERROR
    assert constructed == []


def test_create_app_owns_product_application_shutdown_once() -> None:
    shutdowns: list[int] = []

    class Application:
        def shutdown(self) -> None:
            shutdowns.append(1)

    services = WebServices(application=Application())
    app = create_app(services=services, csrf_token="test-token")
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        assert client.get("/api/v1/health", headers={"host": "localhost"}).status_code == 200
    assert shutdowns == [1]
