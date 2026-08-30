"""Secure local FastAPI foundation for v0.9."""

from .app import WebServices, create_app
from .security import (
    CSRF_HEADER,
    DEFAULT_BIND_HOST,
    DEFAULT_HOSTS,
    DEFAULT_MAX_BODY_BYTES,
    LocalWebSecurityPolicy,
    WebSecurityError,
)

__all__ = [
    "CSRF_HEADER",
    "DEFAULT_BIND_HOST",
    "DEFAULT_HOSTS",
    "DEFAULT_MAX_BODY_BYTES",
    "LocalWebSecurityPolicy",
    "WebSecurityError",
    "WebServices",
    "create_app",
]
