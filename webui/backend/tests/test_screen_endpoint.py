"""POST /screen scoring+storage+guards; GET /screen summary with gate status."""
from __future__ import annotations


def _payload(simple=300.0):
    return {
        "seed": 12345,
        "administered_at": "2026-06-04T10:00:00+00:00",
        "simple_rt": {"trials": [{"rt_ms": simple, "responded": True}] * 30},
        "choice_rt": {"trials": [{"rt_ms": 420.0, "responded": True, "correct": True}] * 30},
        "nback": {"trials": [{"is_target": i % 3 == 0, "responded": i % 3 == 0, "gap": False}
                              for i in range(60)]},
        "tracking": {"samples": [[i * 16, 10, 0, 0, 0] for i in range(200)],
                     "n_expected_samples": 200, "path_amplitude_px": 120.0},
    }


def _enroll(client, pid):
    client.post("/participants", json={"id": pid, "enrollment_date": "2026-06-01"})


def test_screen_post_scores_and_stores(client):
    _enroll(client, "P01")
    r = client.post("/screen", json={"participant_id": "P01", "payload": _payload()})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["scores"]["simple_rt"]["median_ms"] == 300.0
    assert body["scores"]["nback"]["valid"] is True
    assert body["screen_version"] == 1


def test_screen_unknown_participant_404(client):
    r = client.post("/screen", json={"participant_id": "P99", "payload": _payload()})
    assert r.status_code == 404


def test_screen_duplicate_guard_and_overwrite(client):
    _enroll(client, "P01")
    assert client.post("/screen", json={"participant_id": "P01",
                                        "payload": _payload()}).status_code == 201
    r = client.post("/screen", json={"participant_id": "P01", "payload": _payload()})
    assert r.status_code == 409
    r = client.post("/screen", json={"participant_id": "P01",
                                     "payload": _payload(simple=280.0),
                                     "overwrite": True})
    assert r.status_code == 201
    assert r.json()["scores"]["simple_rt"]["median_ms"] == 280.0


def test_screen_summary_gate_status(client):
    for i, pid in enumerate(("P01", "P02"), start=1):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=280.0 + i * 20)})
    s = client.get("/screen").json()
    assert s["n_screened"] == 2 and s["hcf_active"] is False  # < MIN_COHORT
    assert {e["participant_id"] for e in s["screens"]} == {"P01", "P02"}
    assert all(e["hcf_value"] is None for e in s["screens"])
    _enroll(client, "P03")
    client.post("/screen", json={"participant_id": "P03",
                                 "payload": _payload(simple=360.0)})
    s = client.get("/screen").json()
    assert s["n_screened"] == 3 and s["hcf_active"] is True
    by_pid = {e["participant_id"]: e for e in s["screens"]}
    assert by_pid["P01"]["hcf_value"] > 1.0 > by_pid["P03"]["hcf_value"]
