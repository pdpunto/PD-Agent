from pathlib import Path

from fastapi.testclient import TestClient

from pd_agent.web import create_app


def test_production_frontend_dist_is_served_by_fastapi(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<main>PD Agent</main>", encoding="utf-8")
    app = create_app(frontend_dist=tmp_path, csrf_token="test-token")
    with TestClient(app) as client:
        response = client.get("/", headers={"host": "localhost"})
    assert response.status_code == 200
    assert response.text == "<main>PD Agent</main>"


def test_production_frontend_dist_supports_extensionless_client_routes(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<main>PD Agent SPA</main>", encoding="utf-8")
    app = create_app(frontend_dist=tmp_path, csrf_token="test-token")
    with TestClient(app) as client:
        response = client.get("/projects/example", headers={"host": "localhost"})
    assert response.status_code == 200
    assert response.text == "<main>PD Agent SPA</main>"


def test_frontend_dist_must_exist() -> None:
    try:
        create_app(frontend_dist=Path("missing-frontend-dist"), csrf_token="test-token")
    except ValueError as exc:
        assert str(exc) == "frontend_dist must be an existing directory"
    else:
        raise AssertionError("missing frontend dist should fail closed")
