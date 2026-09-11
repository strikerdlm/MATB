"""KSS-first, visit-linked PVT endpoint guards and scoring."""

from __future__ import annotations

from tests.study_fixtures import study_post


def _enroll(client, participant_id: str = "P01") -> None:
    response = client.post(
        "/participants",
        json={"id": participant_id, "enrollment_date": "2026-06-01"},
    )
    assert response.status_code == 201


def _trial(index: int, rt_ms: float = 275.0) -> dict[str, object]:
    stimulus = 2_000.0 + index * 3_000
    return {
        "index": index,
        "wait_ms": 3_000,
        "stimulus_at_ms": stimulus,
        "response_at_ms": stimulus + rt_ms,
        "rt_ms": rt_ms,
        "outcome": "lapse" if rt_ms >= 500 else "response",
    }


def _payload(**overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "participant_id": "P01",
        "execution_purpose": "study",
        "visit_ordinal": 1,
        "kss_score": 6,
        "administered_at": "2026-09-04T14:00:00.000Z",
        "duration_ms": 600_000,
        "fast_mode": False,
        "trials": [_trial(0, 275), _trial(1, 620)],
    }
    payload.update(overrides)
    return payload


def test_pvt_stores_kss_and_standard_metrics_per_visit(client):
    _enroll(client)
    response = study_post(client, "/pvt", json=_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kss_score"] == 6
    assert body["protocol_valid"] is False  # Legacy two-trial evidence cannot validate ten minutes.
    assert "legacy_timing_evidence_missing" in body["timing_evidence"]["validity_reasons"]
    assert body["metrics"]["median_rt_ms"] == 447.5
    assert body["metrics"]["lapses"] == 1

    summary = client.get("/pvt?participant_id=P01").json()
    assert summary["protocol_duration_ms"] == 600_000
    assert len(summary["assessments"]) == 1


def test_pvt_requires_explicit_repeat_and_preserves_original(client):
    _enroll(client)
    assert study_post(client, "/pvt", json=_payload()).status_code == 201
    assert study_post(client, "/pvt", json=_payload()).status_code == 201
    assert study_post(client, "/pvt", json=_payload(kss_score=4)).status_code == 409
    replacement = _payload(kss_score=2, overwrite=True)
    response = study_post(client, "/pvt", json=replacement)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "final_payload_conflict"
    assert client.get("/pvt").json()["assessments"][0]["kss_score"] == 6


def test_pvt_rejects_short_production_run_and_bad_timing(client):
    _enroll(client)
    short = study_post(client, "/pvt", json=_payload(duration_ms=20_000))
    assert short.status_code == 201
    assert short.json()["protocol_valid"] is False
    bad_trial = _trial(0)
    bad_trial["wait_ms"] = 1_999
    malformed = study_post(client, "/pvt", json=_payload(trials=[bad_trial]))
    assert malformed.status_code == 422


def test_fast_mode_is_stored_as_non_protocol_data(client):
    _enroll(client)
    response = study_post(client,
        "/pvt",
        json=_payload(duration_ms=5_000, fast_mode=True, execution_purpose="practice", trials=[_trial(0)]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["protocol_valid"] is False


def test_pvt_requires_matching_participant_visit(client):
    response = study_post(client, "/pvt", json=_payload(participant_id="P99"))
    assert response.status_code == 404
