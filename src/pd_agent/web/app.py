"""FastAPI application foundation; product routes belong to I8."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import hmac
import json
from pathlib import Path
import secrets
from typing import Any, AsyncIterator, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from pd_agent.product import CatalogError, DeliveryError, ExecutionServiceError
from .security import CSRF_HEADER, LocalWebSecurityPolicy, WebSecurityError, header_value, is_mutation


@dataclass(frozen=True, slots=True)
class WebServices:
    """Explicit dependency container for future application routes."""

    project: Any | None = None
    execution: Any | None = None
    evidence: Any | None = None
    delivery: Any | None = None


def create_app(
    *,
    services: WebServices | None = None,
    policy: LocalWebSecurityPolicy | None = None,
    csrf_token: str | None = None,
    frontend_dist: Path | None = None,
) -> FastAPI:
    """Create an isolated app without constructing or starting product work."""

    security = policy or LocalWebSecurityPolicy()
    token = csrf_token or secrets.token_urlsafe(32)
    if not token or not isinstance(token, str):
        raise ValueError("csrf_token must be non-empty text")
    owned = services or WebServices()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = owned
        try:
            yield
        finally:
            closed: set[int] = set()
            for service in (owned.project, owned.execution, owned.evidence, owned.delivery):
                if service is None or id(service) in closed:
                    continue
                closed.add(id(service))
                shutdown = getattr(service, "shutdown", None) or getattr(service, "close", None)
                if shutdown is None:
                    continue
                result = shutdown()
                if hasattr(result, "__await__"):
                    await result

    app = FastAPI(title="PD Agent local Web foundation", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.security_policy = security
    app.state.csrf_token = token
    app.state.bind_host = security.bind_host
    app.state.services = owned

    @app.get("/api/v1/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/security/csrf", include_in_schema=False)
    async def csrf() -> dict[str, str]:
        return {"csrf_token": app.state.csrf_token}

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_REQUEST", "message": "request validation failed", "request_id": _request_id(request.scope)}})

    async def product_error(request: Request, exc: Exception) -> JSONResponse:
        code = getattr(exc, "code", "PRODUCT_ERROR")
        status = _error_status(code)
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": _safe_domain_message(code), "request_id": _request_id(request.scope)}})

    for exception_type in (CatalogError, ExecutionServiceError, DeliveryError):
        app.add_exception_handler(exception_type, product_error)

    app.add_middleware(_ErrorBoundaryMiddleware)
    app.add_middleware(_SecurityMiddleware, policy=security, csrf_token=token)
    from .api import register_routes

    register_routes(app)
    if frontend_dist is not None:
        dist = Path(frontend_dist).resolve()
        if not dist.is_dir():
            raise ValueError("frontend_dist must be an existing directory")
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


class _SecurityMiddleware:
    def __init__(self, app: Any, *, policy: LocalWebSecurityPolicy, csrf_token: str) -> None:
        self.app = app
        self.policy = policy
        self.csrf_token = csrf_token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            headers = scope.get("headers", ())
            self.policy.validate_host(header_value(headers, "host"))
            origin = header_value(headers, "origin")
            if is_mutation(scope.get("method", "GET")):
                self.policy.validate_origin(origin)
                supplied = header_value(headers, CSRF_HEADER)
                if supplied is None or not hmac.compare_digest(supplied, self.csrf_token):
                    raise WebSecurityError("CSRF_INVALID", "csrf token is missing or invalid", 403)
            content_length = header_value(headers, "content-length")
            if content_length is not None:
                try:
                    size = int(content_length)
                except ValueError as exc:
                    raise WebSecurityError("PAYLOAD_TOO_LARGE", "request body exceeds the configured limit", 413) from exc
                if size < 0 or size > self.policy.max_body_bytes:
                    raise WebSecurityError("PAYLOAD_TOO_LARGE", "request body exceeds the configured limit", 413)
        except WebSecurityError as exc:
            await _send_error(send, exc.status_code, exc.code, exc.message, _request_id(scope))
            return

        received = 0
        complete = False

        async def bounded_receive() -> dict[str, Any]:
            nonlocal received, complete
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                received += len(chunk)
                if received > self.policy.max_body_bytes:
                    raise WebSecurityError("PAYLOAD_TOO_LARGE", "request body exceeds the configured limit", 413)
                complete = not message.get("more_body", False)
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except WebSecurityError as exc:
            if not complete:
                await _send_error(send, exc.status_code, exc.code, exc.message, _request_id(scope))
            else:
                raise


class _ErrorBoundaryMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        try:
            await self.app(scope, receive, send)
        except Exception:
            await _send_error(send, 500, "INTERNAL_ERROR", "an internal error occurred", _request_id(scope))


def _request_id(scope: Mapping[str, Any]) -> str:
    value = header_value(scope.get("headers", ()), "x-request-id")
    return value if value and len(value) <= 128 and all(char.isalnum() or char in "-_." for char in value) else secrets.token_hex(16)


def _error_status(code: str) -> int:
    if code.endswith("NOT_FOUND"):
        return 404
    if code in {"EXECUTION_CAPACITY_REACHED", "PAYLOAD_TOO_LARGE"}:
        return 409 if code != "PAYLOAD_TOO_LARGE" else 413
    if code in {"SECURITY_REJECTED", "CSRF_INVALID", "ORIGIN_NOT_ALLOWED", "ARTIFACT_NOT_CURRENT", "ARTIFACT_UNAVAILABLE", "COMPLETION_REQUIRED"}:
        return 403 if code in {"CSRF_INVALID", "ORIGIN_NOT_ALLOWED", "SECURITY_REJECTED"} else 409
    return 400


def _safe_domain_message(code: str) -> str:
    messages = {
        "PROJECT_NOT_FOUND": "project was not found",
        "TASK_NOT_FOUND": "task was not found",
        "EXECUTION_NOT_FOUND": "execution was not found",
        "DELIVERY_NOT_FOUND": "delivery was not found",
        "EXECUTION_CAPACITY_REACHED": "execution capacity is currently full",
        "ARTIFACT_NOT_CURRENT": "artifact is not currently deliverable",
        "ARTIFACT_UNAVAILABLE": "artifact is unavailable",
        "SECURITY_REJECTED": "request was rejected by the security boundary",
    }
    return messages.get(code, "product operation could not be completed")


async def _send_error(send: Any, status: int, code: str, message: str, request_id: str) -> None:
    body = json.dumps(
        {"error": {"code": code, "message": message, "request_id": request_id}},
        separators=(",", ":"),
    ).encode("utf-8")
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]})
    await send({"type": "http.response.body", "body": body})


__all__ = ["WebServices", "create_app"]
