"""Regression tests for experiment access and practice/study isolation."""
import pytest
import json
from sqlmodel import Session, select

from app.routers.pvt import PvtAssessmentIn, PvtTrialIn


def full_pvt(**overrides):
    body = dict(execution_purpose="study", participant_id="P01", visit_ordinal=1, kss_score=3,
                administered_at="2026-09-04T12:00:00Z", duration_ms=600000,
                timing_version=2, max_frame_gap_ms=17, terminal_phase="waiting",
                trials=[dict(index=i, wait_ms=2000, stimulus_at_ms=2000 + i * 2200,
                             response_at_ms=2200 + i * 2200, rt_ms=200, outcome="response")
                        for i in range(272)])
    return {**body, **overrides}


def test_full_pvt_independent_reference_and_quality_gates(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    result = client.post("/pvt", json=full_pvt())
    assert result.status_code == 201, result.text
    assert result.json()["protocol_valid"] is True
    assert result.json()["metrics"]["median_rt_ms"] == 200
    assert result.json()["metrics"]["mean_reciprocal_rt_per_s"] == 5
    assert client.get("/journey/P01/1?experiment=pvt").json()["steps"][-1]["complete"]
    assert PvtAssessmentIn(**full_pvt(interruption_count=1)).validity_reasons()
    assert PvtAssessmentIn(**full_pvt(duration_ms=599999)).validity_reasons()
    assert PvtAssessmentIn(**full_pvt(max_frame_gap_ms=250)).validity_reasons() == []
    assert PvtAssessmentIn(**full_pvt(max_frame_gap_ms=250.001)).validity_reasons()


@pytest.mark.parametrize("rt,outcome", [(99.999, "false_start"), (100, "response"),
                                        (499.999, "response"), (500, "lapse")])
def test_pvt_exact_protocol_boundaries(rt, outcome):
    assert PvtTrialIn(index=0, wait_ms=2000, stimulus_at_ms=2000,
                      response_at_ms=2000 + rt, rt_ms=rt, outcome=outcome).outcome == outcome


def test_practice_cannot_overwrite_study_and_retakes_are_archived(client, engine):
    from app.models import ArchivedAssessment, PracticeResult
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    study = client.post("/pvt", json=full_pvt()).json()
    practice = client.post("/pvt", json=full_pvt(execution_purpose="practice", overwrite=True, kss_score=9))
    assert practice.status_code == 201
    assert client.get("/pvt").json()["assessments"][0] == study
    assert client.post("/pvt", json=full_pvt(overwrite=True, kss_score=5)).status_code == 201
    with Session(engine) as db:
        archive = db.exec(select(ArchivedAssessment)).one()
        assert json.loads(archive.snapshot_json)["kss_score"] == 3
        assert len(db.exec(select(PracticeResult)).all()) == 1


def test_study_pvt_gate_rejects_legacy_and_practice(engine, client):
    from app.experiment_catalog import require_study_pvt
    from fastapi import HTTPException
    from app.models import PvtAssessment
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    with Session(engine) as db:
        row = PvtAssessment(participant_id="P01", visit_id=1, kss_score=3,
            administered_at="2026-09-04T12:00:00Z", duration_ms=600000, pvt_version=1,
            protocol_valid=True, raw_trials_json="[]", metrics_json="{}")
        db.add(row); db.commit()
        with pytest.raises(HTTPException): require_study_pvt(db, 1)
        row.pvt_version = 2; row.execution_purpose = "practice"; db.add(row); db.commit()
        with pytest.raises(HTTPException): require_study_pvt(db, 1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0])
def test_liftoff_rejects_nonfinite_or_nonpositive_laps(value):
    from app.liftoff_schemas import VisibleResultsRequest
    with pytest.raises(ValueError):
        VisibleResultsRequest(valid_lap_times_s=[value], invalid_laps=0,
                              observer_restart_count=0, screenshot_sha256="a" * 64)


def test_pvt_rejects_inconsistent_false_start():
    with pytest.raises(ValueError):
        PvtTrialIn(index=0, wait_ms=2000, stimulus_at_ms=2000,
                   response_at_ms=9000, rt_ms=50, outcome="false_start")


def test_pvt_rejects_events_after_session_end():
    with pytest.raises(ValueError):
        PvtAssessmentIn(execution_purpose="study", participant_id="P01", visit_ordinal=1, kss_score=3,
                        administered_at="2026-09-04T12:00:00Z", duration_ms=600000,
                        trials=[dict(index=0, wait_ms=2000, stimulus_at_ms=900000,
                                     response_at_ms=900200, rt_ms=200, outcome="response")])


def test_catalog_includes_all_families(client):
    response = client.get("/experiments/catalog")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["experiments"]} == {
        "openmatb", "suas", "liftoff", "screen", "pvt", "physiology",
    }


def test_practice_pvt_does_not_complete_or_replace_study_visit(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    response = client.post("/pvt", json={
        "participant_id": "P01", "visit_ordinal": 1, "kss_score": 3,
        "administered_at": "2026-09-04T12:00:00Z", "duration_ms": 12000,
        "fast_mode": True, "execution_purpose": "practice",
        "trials": [{"index": 0, "wait_ms": 2000, "stimulus_at_ms": 2000,
                    "response_at_ms": 2200, "rt_ms": 200, "outcome": "response"}],
    })
    assert response.status_code == 201
    assert response.json()["execution_purpose"] == "practice"
    assert client.get("/pvt").json()["assessments"] == []
    steps = client.get("/journey/P01/1").json()["steps"]
    assert not next(step for step in steps if step["id"] == "pvt")["complete"]
