"""Secure local FastAPI foundation for v0.9."""

from .app import WebServices, create_app
from .security import (
    CSRF_HEADER,
    DEFAULT_BIND_HOST,
    DEFAULT_HOSTS,
    DEFAULT_MAX_BODY_BYTES,
    LocalWebSecurityPolicy,
    policy_for_server_port,
    WebSecurityError,
)

__all__ = [
    "CSRF_HEADER",
    "DEFAULT_BIND_HOST",
    "DEFAULT_HOSTS",
    "DEFAULT_MAX_BODY_BYTES",
    "LocalWebSecurityPolicy",
    "policy_for_server_port",
    "WebSecurityError",
    "WebServices",
    "create_app",
]
