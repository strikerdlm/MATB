"""ASGI request-size guards applied before FastAPI parses request bodies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

from matb_integration.contracts import MAX_EXPERIMENT_BODY_BYTES


class _ExperimentBodyTooLarge(Exception):
    pass


MAX_SESSION_CSV_BYTES = 64 * 1024 * 1024
MAX_SESSION_MANIFEST_BYTES = 2 * 1024 * 1024
# A multipart envelope needs room for boundaries and the four small form
# fields, but it must remain bounded before Starlette spools any UploadFile.
MAX_INGEST_MULTIPART_OVERHEAD_BYTES = 1 * 1024 * 1024
MAX_INGEST_BODY_BYTES = (
    MAX_SESSION_CSV_BYTES
    + MAX_SESSION_MANIFEST_BYTES
    + MAX_INGEST_MULTIPART_OVERHEAD_BYTES
)
MAX_RESEARCH_BUNDLE_BODY_BYTES = 5 * 1024 * 1024


class _RequestBodyTooLarge(Exception):
    pass


class ScientificRequestBodyLimitMiddleware:
    """Bound scientific POST bodies even for chunked or dishonest requests."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    @staticmethod
    def _response(status_code: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": {"code": code, "message": message}},
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        route = (scope.get("method"), scope.get("path"))
        if scope.get("type") != "http" or route[0] != "POST":
            await self.app(scope, receive, send)
            return
        if route == ("POST", "/experiments/compile"):
            limit = MAX_EXPERIMENT_BODY_BYTES
            too_large_code = "experiment_request_too_large"
            noun = "experiment request"
        elif route == ("POST", "/ingest"):
            limit = MAX_INGEST_BODY_BYTES
            too_large_code = "ingest_request_too_large"
            noun = "ingest multipart request"
        elif route == ("POST", "/ingest/evidence"):
            from matb_integration.evidence.contracts import MAX_STREAM_BYTES
            limit = 2 * MAX_STREAM_BYTES + MAX_SESSION_CSV_BYTES + 2 * MAX_SESSION_MANIFEST_BYTES + MAX_INGEST_MULTIPART_OVERHEAD_BYTES
            too_large_code = "evidence_request_too_large"
            noun = "evidence multipart request"
        elif route == ("POST", "/evidence/analysis-inputs"):
            limit = 128 * 1024
            too_large_code = "evidence_selection_too_large"
            noun = "evidence analysis selection"
        elif route == ("POST", "/exports/research-bundle"):
            limit = MAX_RESEARCH_BUNDLE_BODY_BYTES
            too_large_code = "research_bundle_request_too_large"
            noun = "research bundle request"
        else:
            await self.app(scope, receive, send)
            return

        content_lengths = [
            value
            for key, value in scope.get("headers", [])
            if key.lower() == b"content-length"
        ]
        if len(content_lengths) > 1:
            response = self._response(400, "invalid_content_length", "conflicting Content-Length headers")
            await response(scope, receive, send)
            return
        if content_lengths:
            try:
                declared = int(content_lengths[0].decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                declared = -1
            if declared < 0:
                response = self._response(400, "invalid_content_length", "invalid Content-Length header")
                await response(scope, receive, send)
                return
            if declared > limit:
                response = self._response(
                    413,
                    too_large_code,
                    f"{noun} exceeds {limit} bytes",
                )
                await response(scope, receive, send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            response = self._response(
                413,
                too_large_code,
                f"{noun} exceeds {limit} bytes",
            )
            await response(scope, receive, send)


# Compatibility name for downstream imports from the first release candidate.
ExperimentCompileBodyLimitMiddleware = ScientificRequestBodyLimitMiddleware
