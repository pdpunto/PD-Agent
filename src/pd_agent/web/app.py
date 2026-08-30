"""FastAPI application foundation; product routes belong to I8."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import hmac
import json
import secrets
from typing import Any, AsyncIterator, Mapping

from fastapi import FastAPI

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

    app.add_middleware(_ErrorBoundaryMiddleware)
    app.add_middleware(_SecurityMiddleware, policy=security, csrf_token=token)
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


async def _send_error(send: Any, status: int, code: str, message: str, request_id: str) -> None:
    body = json.dumps(
        {"error": {"code": code, "message": message, "request_id": request_id}},
        separators=(",", ":"),
    ).encode("utf-8")
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]})
    await send({"type": "http.response.body", "body": body})


__all__ = ["WebServices", "create_app"]
