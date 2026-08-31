"""Security boundary for the local v0.9 Web foundation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
from urllib.parse import urlsplit


DEFAULT_HOSTS = ("localhost", "127.0.0.1")
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_MAX_BODY_BYTES = 1_000_000
CSRF_HEADER = "x-csrf-token"


class WebSecurityError(Exception):
    """Safe rejection raised before a protected handler is called."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class LocalWebSecurityPolicy:
    """Explicit loopback and bounded-request policy."""

    allowed_hosts: tuple[str, ...] = DEFAULT_HOSTS
    allowed_origins: tuple[str, ...] = ("http://localhost", "http://127.0.0.1")
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    bind_host: str = DEFAULT_BIND_HOST

    def __post_init__(self) -> None:
        hosts = tuple(item.casefold() for item in self.allowed_hosts if _valid_host_name(item))
        origins = tuple(item.rstrip("/") for item in self.allowed_origins if _valid_origin(item))
        if not hosts or not origins:
            raise ValueError("local security policy must have trusted hosts and origins")
        if self.max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        if self.bind_host != DEFAULT_BIND_HOST:
            raise ValueError("the default local boundary must bind to 127.0.0.1")
        object.__setattr__(self, "allowed_hosts", hosts)
        object.__setattr__(self, "allowed_origins", origins)

    def validate_host(self, value: str | None) -> None:
        host = _host_without_port(value)
        if host not in self.allowed_hosts:
            raise WebSecurityError("HOST_NOT_ALLOWED", "request host is not allowed", 400)

    def validate_origin(self, value: str | None) -> None:
        # Native/non-browser clients may omit Origin; CSRF remains mandatory.
        if value is None:
            return
        origin = value.rstrip("/")
        if origin not in self.allowed_origins:
            raise WebSecurityError("ORIGIN_NOT_ALLOWED", "request origin is not allowed", 403)


def policy_for_server_port(port: int) -> LocalWebSecurityPolicy:
    """Build the exact loopback origins served by the local Web process."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65_535:
        raise ValueError("server port must be between 1 and 65535")
    return LocalWebSecurityPolicy(
        allowed_origins=(f"http://localhost:{port}", f"http://127.0.0.1:{port}"),
    )


def _host_without_port(value: str | None) -> str:
    if value is None or not value.strip():
        raise WebSecurityError("HOST_NOT_ALLOWED", "request host is not allowed", 400)
    raw = value.strip().casefold()
    if raw.startswith("[") or raw.count(":") > 1:
        raise WebSecurityError("HOST_NOT_ALLOWED", "request host is not allowed", 400)
    host, separator, port = raw.partition(":")
    if separator and (not port.isdigit() or not 0 < int(port) <= 65535):
        raise WebSecurityError("HOST_NOT_ALLOWED", "request host is not allowed", 400)
    if not re.fullmatch(r"[a-z0-9.-]+", host) or host.startswith(".") or host.endswith("."):
        raise WebSecurityError("HOST_NOT_ALLOWED", "request host is not allowed", 400)
    return host


def _valid_host_name(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9.-]+", value.casefold())) and value.casefold() in DEFAULT_HOSTS


def _valid_origin(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value.rstrip("/"))
    return parsed.scheme == "http" and parsed.hostname in DEFAULT_HOSTS and (parsed.path, parsed.query, parsed.fragment) == ("", "", "")


def is_mutation(method: str) -> bool:
    return method.upper() not in {"GET", "HEAD", "OPTIONS", "TRACE"}


def header_value(headers: Iterable[tuple[bytes, bytes]], name: str) -> str | None:
    wanted = name.casefold().encode("ascii")
    for key, value in headers:
        if key.lower() == wanted:
            return value.decode("latin-1")
    return None


__all__ = [
    "CSRF_HEADER",
    "DEFAULT_BIND_HOST",
    "DEFAULT_HOSTS",
    "DEFAULT_MAX_BODY_BYTES",
    "LocalWebSecurityPolicy",
    "policy_for_server_port",
    "WebSecurityError",
    "header_value",
    "is_mutation",
]
