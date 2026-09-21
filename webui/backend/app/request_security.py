"""Loopback API request-origin and DNS-rebinding defenses."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _single_header(scope: dict[str, Any], name: bytes) -> str | None:
    values = [
        value
        for key, value in scope.get("headers", [])
        if key.lower() == name
    ]
    if len(values) != 1:
        return None
    try:
        return values[0].decode("latin-1")
    except UnicodeDecodeError:
        return None


def _host_name(host_header: str) -> str | None:
    try:
        parsed = urlsplit("//" + host_header)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        return None
    return parsed.hostname.lower()


class LoopbackRequestSecurityMiddleware:
    """Reject DNS rebinding and cross-site state-changing browser requests.

    Browser requests authenticate their context with the unforgeable ``Origin``
    header.  Non-browser tools omit Origin and therefore require the configured
    bearer token; this prevents a hostile web page from using a no-CORS form or
    fetch to mutate the loopback research service.
    """

    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        *,
        settings: Any,
    ) -> None:
        self.app = app
        self.settings = settings

    @staticmethod
    def _response(status_code: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": {"code": code, "message": message}},
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        host = _single_header(scope, b"host")
        hostname = _host_name(host) if host is not None else None
        if hostname not in self.settings.allowed_hosts:
            response = self._response(400, "untrusted_host", "request Host is not allowed")
            await response(scope, receive, send)
            return

        method = str(scope.get("method", "")).upper()
        if method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        origin_headers = [
            value
            for key, value in scope.get("headers", [])
            if key.lower() == b"origin"
        ]
        if origin_headers:
            origin = _single_header(scope, b"origin")
            try:
                decoded_origin = origin if origin is not None else ""
            except UnicodeDecodeError:
                decoded_origin = ""
            if decoded_origin not in self.settings.frontend_origins:
                response = self._response(
                    403,
                    "untrusted_request_origin",
                    "state-changing browser request Origin is not allowed",
                )
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        expected_token = self.settings.api_token
        authorization = _single_header(scope, b"authorization")
        prefix = "Bearer "
        supplied_token = (
            authorization[len(prefix):]
            if authorization is not None and authorization.startswith(prefix)
            else ""
        )
        if (
            expected_token is None
            or not supplied_token
            or not secrets.compare_digest(
                supplied_token.encode("utf-8"), expected_token.encode("utf-8")
            )
        ):
            response = self._response(
                403,
                "cli_authentication_required",
                "Origin-less state-changing requests require the MATB API bearer token",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
