from __future__ import annotations

from fastapi.testclient import TestClient

from pd_agent.web import CSRF_HEADER, LocalWebSecurityPolicy, WebServices, create_app, policy_for_server_port


def _client(*, max_body_bytes: int = 1_000_000, services: WebServices | None = None) -> TestClient:
    app = create_app(
        services=services,
        policy=LocalWebSecurityPolicy(max_body_bytes=max_body_bytes),
        csrf_token="test-token",
    )
    return TestClient(app)


def _mutation(app):
    called = {"count": 0}

    @app.post("/test/mutation")
    async def mutation() -> dict[str, bool]:
        called["count"] += 1
        return {"accepted": True}

    return called


def test_factory_is_isolated_and_defaults_to_loopback() -> None:
    first = create_app(csrf_token="one")
    second = create_app(csrf_token="two")
    assert first is not second
    assert first.state.bind_host == "127.0.0.1"
    assert first.state.csrf_token != second.state.csrf_token


def test_trusted_hosts_and_ports_are_accepted() -> None:
    app = create_app(csrf_token="token")
    with TestClient(app) as client:
        assert client.get("/api/v1/health", headers={"host": "localhost"}).status_code == 200
        assert client.get("/api/v1/health", headers={"host": "127.0.0.1:8000"}).status_code == 200


def test_untrusted_and_malformed_hosts_fail_before_handler() -> None:
    app = create_app(csrf_token="token")
    with TestClient(app) as client:
        for host in ("evil.example", "localhost.evil.example", "127.0.0.1.evil.example", "[::1]", "localhost:bad"):
            response = client.get("/api/v1/health", headers={"host": host})
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "HOST_NOT_ALLOWED"


def test_csrf_token_is_obtained_without_query_string() -> None:
    with _client() as client:
        response = client.get("/api/v1/security/csrf", headers={"host": "localhost"})
        assert response.status_code == 200
        assert response.json() == {"csrf_token": "test-token"}
        assert "?" not in str(response.request.url)


def test_mutation_requires_csrf_and_accepts_valid_same_origin() -> None:
    app = create_app(csrf_token="test-token")
    called = _mutation(app)
    with TestClient(app) as client:
        base = {"host": "localhost", "origin": "http://localhost"}
        assert client.post("/test/mutation", headers=base).status_code == 403
        assert client.post("/test/mutation", headers={**base, CSRF_HEADER: "wrong"}).status_code == 403
        response = client.post("/test/mutation", headers={**base, CSRF_HEADER: "test-token"}, json={"ok": True})
        assert response.status_code == 200
        assert called["count"] == 1


def test_server_port_policy_accepts_exact_loopback_origins_only() -> None:
    app = create_app(policy=policy_for_server_port(8000), csrf_token="test-token")
    called = _mutation(app)
    with TestClient(app) as client:
        headers = {"host": "127.0.0.1:8000", "origin": "http://127.0.0.1:8000", CSRF_HEADER: "test-token"}
        assert client.post("/test/mutation", headers=headers).status_code == 200
        localhost_headers = {**headers, "origin": "http://localhost:8000", "host": "localhost:8000"}
        assert client.post("/test/mutation", headers=localhost_headers).status_code == 200
        for origin in ("http://127.0.0.1:8001", "https://127.0.0.1:8000", "http://evil.example:8000"):
            response = client.post("/test/mutation", headers={**headers, "origin": origin})
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert called["count"] == 2


def test_server_port_policy_accepts_browser_default_port_origin() -> None:
    app = create_app(policy=policy_for_server_port(80), csrf_token="test-token")
    called = _mutation(app)
    with TestClient(app) as client:
        headers = {"host": "127.0.0.1", "origin": "http://127.0.0.1", CSRF_HEADER: "test-token"}
        response = client.post("/test/mutation", headers=headers)
        assert response.status_code == 200
    assert called["count"] == 1


def test_server_port_policy_rejects_invalid_ports() -> None:
    for port in (0, 65_536, True, "8000"):
        try:
            policy_for_server_port(port)  # type: ignore[arg-type]
        except ValueError:
            continue
        raise AssertionError("invalid server port was accepted")


def test_foreign_origin_is_rejected_and_absent_origin_uses_csrf_policy() -> None:
    app = create_app(csrf_token="test-token")
    called = _mutation(app)
    with TestClient(app) as client:
        assert client.post("/test/mutation", headers={"host": "localhost", "origin": "https://evil.example", CSRF_HEADER: "test-token"}).status_code == 403
        assert client.post("/test/mutation", headers={"host": "localhost", CSRF_HEADER: "test-token"}).status_code == 200
        assert client.post("/test/mutation", headers={"host": "localhost", "origin": "null", CSRF_HEADER: "test-token"}).status_code == 403
        assert called["count"] == 1


def test_origin_suffix_and_wildcard_cors_are_not_allowed() -> None:
    app = create_app(csrf_token="test-token")
    _mutation(app)
    with TestClient(app) as client:
        response = client.post("/test/mutation", headers={"host": "localhost", "origin": "http://localhost.evil.example", CSRF_HEADER: "test-token"})
        assert response.status_code == 403
        assert "access-control-allow-origin" not in {key.lower() for key in response.headers}


def test_body_limit_rejects_oversized_request_before_handler() -> None:
    app = create_app(policy=LocalWebSecurityPolicy(max_body_bytes=4), csrf_token="test-token")
    called = _mutation(app)
    with TestClient(app) as client:
        response = client.post("/test/mutation", headers={"host": "localhost", CSRF_HEADER: "test-token", "content-length": "5"}, content=b"12345")
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
        assert called["count"] == 0


def test_internal_error_is_safe_and_unknown_route_is_bounded() -> None:
    app = create_app(csrf_token="test-token")

    @app.get("/test/error")
    async def error() -> None:
        raise RuntimeError(r"secret token at C:\private\traceback.py")

    with TestClient(app) as client:
        response = client.get("/test/error", headers={"host": "localhost"})
        assert response.status_code == 500
        body = response.json()["error"]
        assert body["code"] == "INTERNAL_ERROR"
        assert "secret" not in response.text and "traceback" not in response.text and "C:\\private" not in response.text
        assert client.get("/not-a-product-route", headers={"host": "localhost"}).status_code == 404
        response = client.get("/api/v1/projects", headers={"host": "localhost"})
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_lifespan_closes_each_injected_service_once_without_starting_work() -> None:
    class Service:
        def __init__(self) -> None:
            self.closed = 0

        def close(self) -> None:
            self.closed += 1

    service = Service()
    app = create_app(services=WebServices(execution=service, evidence=service), csrf_token="test-token")
    with TestClient(app) as client:
        assert client.get("/api/v1/health", headers={"host": "localhost"}).status_code == 200
    assert service.closed == 1


def test_policy_rejects_lan_default_and_invalid_configuration() -> None:
    try:
        LocalWebSecurityPolicy(bind_host="0.0.0.0")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("LAN bind must be rejected")
