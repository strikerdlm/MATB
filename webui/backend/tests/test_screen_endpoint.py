"""POST /screen scoring+storage+guards; GET /screen summary with gate status."""
from __future__ import annotations

from tests.study_fixtures import study_post


def _payload(simple=300.0):
    return {
        "schema_version": 2,
        "seed": 12345,
        "administered_at": "2026-06-04T10:00:00+00:00",
        "simple_rt": {"trials": [{"rt_ms": simple, "responded": True}] * 30},
        "choice_rt": {"trials": [{"rt_ms": 420.0, "responded": True, "correct": True, "stimulus_side": "left", "response_side": "left"}] * 30},
        "nback": {"trials": [{"letter": "AB"[i % 2], "is_target": i >= 2, "responded": i >= 2, "shown_at_ms": i * 2500}
                              for i in range(60)], "soa_ms": 2500},
        "tracking": {"samples": [[i * 150, 10, 0, 0, 0] for i in range(601)],
                     "duration_ms": 90000, "n_expected_samples": 5400, "path_amplitude_px": 120.0},
    }


def _enroll(client, pid):
    client.post("/participants", json={"id": pid, "enrollment_date": "2026-06-01"})


def test_screen_post_scores_and_stores(client):
    _enroll(client, "P01")
    r = study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P01", "payload": _payload()})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["scores"]["simple_rt"]["median_ms"] == 300.0
    assert body["scores"]["nback"]["valid"] is True
    assert body["screen_version"] == 2


def test_screen_unknown_participant_404(client):
    r = study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P99", "payload": _payload()})
    assert r.status_code == 404


def test_screen_duplicate_guard_refuses_destructive_overwrite(client):
    _enroll(client, "P01")
    assert study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P01",
                                        "payload": _payload()}).status_code == 201
    r = study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P01", "payload": _payload()})
    assert r.status_code == 201
    assert study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P01", "payload": _payload(simple=270)}).status_code == 409
    r = study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P01",
                                     "payload": _payload(simple=280.0),
                                     "overwrite": True})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "final_payload_conflict"
    assert client.get("/screen").json()["screens"][0]["scores"]["simple_rt"]["median_ms"] == 300.0


def test_screen_summary_gate_status(client):
    for i, pid in enumerate(("P01", "P02"), start=1):
        _enroll(client, pid)
        study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": pid,
                                     "payload": _payload(simple=280.0 + i * 20)})
    s = client.get("/screen").json()
    assert s["n_screened"] == 2 and s["hcf_active"] is False  # < MIN_COHORT
    assert {e["participant_id"] for e in s["screens"]} == {"P01", "P02"}
    assert all(e["hcf_value"] is None for e in s["screens"])
    _enroll(client, "P03")
    study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P03",
                                 "payload": _payload(simple=360.0)})
    s = client.get("/screen").json()
    assert s["n_screened"] == 3 and s["hcf_active"] is True
    by_pid = {e["participant_id"]: e for e in s["screens"]}
    assert by_pid["P01"]["hcf_value"] > 1.0 > by_pid["P03"]["hcf_value"]


def test_screen_malformed_payload_422_not_500(client):
    _enroll(client, "P01")
    bad = _payload()
    bad["nback"]["trials"] = [{"responded": True}]   # missing is_target
    r = study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P01", "payload": bad})
    assert r.status_code == 422
    assert "malformed" in r.json()["detail"]
    bad2 = _payload()
    bad2["simple_rt"] = {"trials": None}             # trials not a list
    r2 = study_post(client, "/screen", json={"execution_purpose": "study", "participant_id": "P01", "payload": bad2})
    assert r2.status_code == 422
