from __future__ import annotations

import json

import pytest

from app import body_limits


async def _drain_body(scope, receive, send) -> None:
    del scope
    while True:
        message = await receive()
        if not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def _invoke_ingest_limit(
    monkeypatch: pytest.MonkeyPatch,
    *,
    headers: list[tuple[bytes, bytes]],
    chunks: list[dict[str, object]],
) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr(body_limits, "MAX_INGEST_BODY_BYTES", 8)
    middleware = body_limits.ScientificRequestBodyLimitMiddleware(_drain_body)
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return chunks.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/ingest",
            "headers": headers,
        },
        receive,
        send,
    )
    status = next(int(item["status"]) for item in sent if item["type"] == "http.response.start")
    body = b"".join(
        bytes(item.get("body", b"")) for item in sent if item["type"] == "http.response.body"
    )
    return status, json.loads(body)


@pytest.mark.anyio
async def test_ingest_rejects_dishonest_declared_oversize_before_multipart_parsing(monkeypatch):
    status, payload = await _invoke_ingest_limit(
        monkeypatch,
        headers=[(b"content-length", b"9")],
        chunks=[{"type": "http.request", "body": b"", "more_body": False}],
    )

    assert status == 413
    assert payload["detail"]["code"] == "ingest_request_too_large"


@pytest.mark.anyio
async def test_ingest_rejects_chunked_oversize_before_upload_spooling(monkeypatch):
    status, payload = await _invoke_ingest_limit(
        monkeypatch,
        headers=[(b"transfer-encoding", b"chunked")],
        chunks=[
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": False},
        ],
    )

    assert status == 413
    assert payload["detail"]["code"] == "ingest_request_too_large"


@pytest.mark.anyio
async def test_research_bundle_rejects_chunked_oversize_before_json_parsing(monkeypatch):
    monkeypatch.setattr(body_limits, "MAX_RESEARCH_BUNDLE_BODY_BYTES", 8)
    middleware = body_limits.ScientificRequestBodyLimitMiddleware(_drain_body)
    sent: list[dict[str, object]] = []
    chunks: list[dict[str, object]] = [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"6789", "more_body": False},
    ]

    async def receive() -> dict[str, object]:
        return chunks.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/exports/research-bundle",
            "headers": [(b"transfer-encoding", b"chunked")],
        },
        receive,
        send,
    )
    status = next(int(item["status"]) for item in sent if item["type"] == "http.response.start")
    body = b"".join(
        bytes(item.get("body", b""))
        for item in sent
        if item["type"] == "http.response.body"
    )

    assert status == 413
    assert json.loads(body)["detail"]["code"] == "research_bundle_request_too_large"
