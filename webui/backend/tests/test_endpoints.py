from __future__ import annotations

import io
import json
import zipfile

from sqlmodel import Session, select

from app.liftoff_models import LiftoffSession
from app.models import Visit


def _enroll(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})


def test_ingest_endpoint_and_tracker(client, sample_csv_bytes):
    _enroll(client)
    files = {"file": ("run1.csv", sample_csv_bytes(misses=(5.0, 25.0)), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    r = client.post("/ingest", files=files, data=data)
    assert r.status_code == 201, r.text
    assert r.json()["workload_level"] == "LOW"
    assert r.json()["validation"]["status"] == "missing_manifest"

    grid = client.get("/tracker").json()
    assert len(grid) == 9
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


def test_ingest_endpoint_accepts_valid_manifest(client, sample_csv_bytes):
    _enroll(client)
    manifest = {
        "manifest_version": 2,
        "metrics_schema_version": "2.0",
        "workload_label_status": "engineering_preset_pending_human_calibration",
        "participant_id": "P01",
        "visit_ordinal": 1,
        "workload_level": "LOW",
        "block_duration_sec": 900,
        "scenario": {"filename": "run1.txt", "sha256": "abc"},
        "questionnaires": {"include_nasatlx": True},
        "expected": {"isa_probe_times_sec": [], "sagat_freezes": 0},
    }
    files = {
        "file": ("run1.csv", sample_csv_bytes(misses=(5.0, 25.0)), "text/csv"),
        "manifest": ("run1.txt.manifest.json", json.dumps(manifest).encode("utf-8"), "application/json"),
    }
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    r = client.post("/ingest", files=files, data=data)
    assert r.status_code == 201, r.text
    assert r.json()["validation"]["status"] == "ok"


def test_block_detail_endpoint(client, sample_csv_bytes):
    _enroll(client)
    files = {"file": ("run1.csv", sample_csv_bytes(misses=(5.0, 25.0)), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201
    r = client.get("/block", params={"participant_id": "P01", "visit_ordinal": 1, "workload_level": "LOW"})
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["sysmon"]["n_misses"] == 2
    assert "_raw_sysmon_rows" not in body["metrics"]
    assert body["depdf_fit"] is None  # only LOW ingested, no full-visit fit
    assert body["provenance"]["validation_status"] == "missing_manifest"


def test_block_detail_404_when_absent(client):
    _enroll(client)
    r = client.get("/block", params={"participant_id": "P01", "visit_ordinal": 2, "workload_level": "HIGH"})
    assert r.status_code == 404


def test_research_context_and_bundle_exports(client, sample_csv_bytes):
    _enroll(client)
    files = {"file": ("run1.csv", sample_csv_bytes(misses=(5.0, 25.0)), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201

    ctx = client.get("/exports/research-context")
    assert ctx.status_code == 200
    body = ctx.json()
    assert body["bundle_version"] == "research-bundle-v1"
    assert body["counts"]["participants"] == 1
    assert body["block_provenance"][0]["validation_status"] == "missing_manifest"

    r = client.post("/exports/research-bundle", json={
        "figures": [{"name": "q1-test", "option": {"xAxis": {"type": "value"}}}],
    })
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "metrics_long.json" in names
        assert "provenance/block_validations.json" in names
        assert "figures/q1-test.option.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["figure_count"] == 1


def test_research_context_includes_liftoff_three_visit_grid(client, engine):
    _enroll(client)
    with Session(engine) as session:
        visit = session.exec(select(Visit).where(Visit.participant_id == "P01", Visit.visit_ordinal == 1)).one()
        session.add(LiftoffSession(
            id="liftoff-valid",
            participant_id="P01",
            visit_id=visit.id,
            attempt_number=1,
            protocol_id="astra-2026",
            protocol_version="1.0.0",
            liftoff_build="test",
            configuration_sha256="a" * 64,
            track_id="track",
            telemetry_profile="liftoff-telemetry-all-v1",
            manifest_json='{"visit_code":"T0","visit_ordinal":1}',
            status="FINISHED",
            validity="valid",
            artifact_root="/tmp/valid",
            controller_lease_hash="b" * 64,
            hrv_measurement_id="hrv-123",
            sync_quality="good",
            metrics_json='{"metrics_version":"liftoff-metrics-v1","primary":{"median_lap_time_s":61.2,"valid_laps":3},"telemetry":{"active_duration_s":900.0}}',
        ))
        session.commit()

    context = client.get("/exports/research-context").json()
    assert len(context["liftoff_tracker"]) == 3
    assert context["liftoff_tracker"][0]["visit_code"] == "T0"
    assert context["liftoff_tracker"][0]["present"] is True
    assert context["liftoff_metrics_long"]
    assert context["liftoff_tracker"][0]["hrv_measurement_id"] == "hrv-123"
