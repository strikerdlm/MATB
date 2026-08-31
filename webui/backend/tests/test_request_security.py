from __future__ import annotations

import asyncio

import httpx

from app.main import app


def _raw_request(method: str, path: str, *, headers=None):
    async def send():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, headers=headers)

    return asyncio.run(send())


def test_state_change_accepts_only_configured_browser_origin(client):
    allowed = client.post(
        "/analysis/run", headers={"Origin": "http://localhost:3100"}
    )
    hostile = client.post(
        "/analysis/run", headers={"Origin": "https://attacker.example"}
    )

    assert allowed.status_code == 200
    assert hostile.status_code == 403
    assert hostile.json()["detail"]["code"] == "untrusted_request_origin"


def test_no_origin_cli_requires_constant_time_bearer_token(monkeypatch):
    monkeypatch.setattr(app.state, "api_token", "x" * 32)

    missing = _raw_request("POST", "/token-probe")
    wrong = _raw_request(
        "POST", "/token-probe", headers={"Authorization": "Bearer " + "y" * 32}
    )
    accepted = _raw_request(
        "POST", "/token-probe", headers={"Authorization": "Bearer " + "x" * 32}
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert accepted.status_code == 404


def test_host_allowlist_blocks_dns_rebinding(client):
    response = client.get("/health", headers={"Host": "attacker.example"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "untrusted_host"
