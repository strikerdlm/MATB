from __future__ import annotations

import pytest
from sqlmodel import SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.study_models import ensure_study_binding
from app.study_protocol import get_protocol, selected_protocol


def test_astra_protocol_has_three_canonical_visits():
    protocol = get_protocol("astra-2026")

    assert [(visit.ordinal, visit.code, visit.scheduled_day) for visit in protocol.visits] == [
        (1, "T0", 0),
        (2, "DM8", 8),
        (3, "DM15", 15),
    ]


def test_database_binding_rejects_conflicting_profile():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    ensure_study_binding(engine, get_protocol("astra-2026"))

    with pytest.raises(RuntimeError, match="study_protocol_mismatch"):
        ensure_study_binding(engine, get_protocol("matb-longitudinal-6-visit-v1"))


def test_selected_protocol_rejects_blank_environment_value(monkeypatch):
    monkeypatch.setenv("MATB_STUDY_PROTOCOL", "   ")

    with pytest.raises(ValueError, match="MATB_STUDY_PROTOCOL"):
        selected_protocol()


def test_get_protocol_rejects_unknown_identifier():
    with pytest.raises(ValueError, match="unknown study protocol"):
        get_protocol("unknown")


def test_study_protocol_endpoint_exposes_selected_schedule(client):
    response = client.get("/study/protocol")

    assert response.status_code == 200
    assert response.json() == {
        "protocol_id": "astra-2026",
        "protocol_version": "1.0.0",
        "schedule_sha256": "15a1ca82563ae8cc238f4579e5a5b68949c4a251091ef0c15e50a44f2eb87da8",
        "visits": [
            {"ordinal": 1, "code": "T0", "scheduled_day": 0},
            {"ordinal": 2, "code": "DM8", "scheduled_day": 8},
            {"ordinal": 3, "code": "DM15", "scheduled_day": 15},
        ],
    }
