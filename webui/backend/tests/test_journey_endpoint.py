from __future__ import annotations
from types import SimpleNamespace

import pytest
from app.main import app


@pytest.mark.parametrize("suas_available", [True, False])
def test_journey_begins_with_identity_then_kss(client, monkeypatch, suas_available):
    manifests = [SimpleNamespace(component_id="matb-suas")] if suas_available else []
    monkeypatch.setattr(app.state, "component_registry", SimpleNamespace(manifests=lambda: manifests))
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    response = client.get("/journey/P01/1")
    assert response.status_code == 200
    steps = response.json()["steps"]
    assert [step["id"] for step in steps] == [
        "welcome", "kss", "pvt", "polar", "briefing",
        "practice", "blocks", "workload", "complete",
    ]
    assert steps[0]["status"] == "complete"
    assert steps[1]["status"] == ("current" if suas_available else "unavailable")


def test_journey_rejects_unknown_visit(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert client.get("/journey/P01/99").status_code == 404
