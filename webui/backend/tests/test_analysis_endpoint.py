"""POST /analysis/run + GET /analysis/latest: caching by fingerprint, statuses."""
from __future__ import annotations


def test_analysis_run_on_empty_db(client):
    r = client.post("/analysis/run")
    assert r.status_code == 200
    art = r.json()
    assert art["cached"] is False
    assert art["confirmatory"]["family_size_actual"] == 0
    assert all(v["status"] == "insufficient_data" for v in art["q1"].values())


def test_analysis_run_caches_by_fingerprint(client):
    first = client.post("/analysis/run").json()
    second = client.post("/analysis/run").json()
    assert first["cached"] is False and second["cached"] is True
    assert first["provenance"]["fingerprint"] == second["provenance"]["fingerprint"]


def test_analysis_latest(client):
    assert client.get("/analysis/latest").status_code == 404
    client.post("/analysis/run")
    r = client.get("/analysis/latest")
    assert r.status_code == 200
    assert r.json()["engine_version"]


def test_analysis_reruns_after_new_ingest(client, ingest_one_block):
    """Ingesting data changes the fingerprint -> a fresh (non-cached) run."""
    before = client.post("/analysis/run").json()
    ingest_one_block(participant_id="P01", visit_ordinal=1, workload_level="LOW")
    after = client.post("/analysis/run").json()
    assert after["cached"] is False
    assert after["provenance"]["fingerprint"] != before["provenance"]["fingerprint"]
