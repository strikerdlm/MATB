from __future__ import annotations


def _enroll(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})


def test_ingest_endpoint_and_tracker(client, sample_csv_bytes):
    _enroll(client)
    files = {"file": ("run1.csv", sample_csv_bytes(misses=(5.0, 25.0)), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    r = client.post("/ingest", files=files, data=data)
    assert r.status_code == 201, r.text
    assert r.json()["workload_level"] == "LOW"

    grid = client.get("/tracker").json()
    assert len(grid) == 18
    present = [c for c in grid if c["present"]]
    assert present and present[0]["workload_level"] == "LOW"


def test_ingest_duplicate_returns_409(client, sample_csv_bytes):
    _enroll(client)
    content = sample_csv_bytes()
    files = {"file": ("a.csv", content, "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201
    files2 = {"file": ("b.csv", content, "text/csv")}
    data2 = {"participant_id": "P01", "visit_ordinal": "2", "workload_level": "LOW"}
    r = client.post("/ingest", files=files2, data=data2)
    assert r.status_code == 409
