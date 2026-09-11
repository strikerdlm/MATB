from __future__ import annotations

import io
import csv
import hashlib
import json
import zipfile

import pytest

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


def test_ingest_rejects_csv_over_the_explicit_file_cap(client, monkeypatch):
    monkeypatch.setattr("app.routers.ingest.MAX_SESSION_CSV_BYTES", 16)
    response = client.post(
        "/ingest",
        files={"file": ("oversized.csv", b"x" * 17, "text/csv")},
        data={
            "participant_id": "P01",
            "visit_ordinal": "1",
            "workload_level": "LOW",
        },
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "session_csv_too_large"


def test_ingest_rejects_manifest_over_the_explicit_file_cap(client, monkeypatch, sample_csv_bytes):
    monkeypatch.setattr("app.routers.ingest.MAX_SESSION_MANIFEST_BYTES", 16)
    response = client.post(
        "/ingest",
        files={
            "file": ("session.csv", sample_csv_bytes(), "text/csv"),
            "manifest": ("session.manifest.json", b"x" * 17, "application/json"),
        },
        data={
            "participant_id": "P01",
            "visit_ordinal": "1",
            "workload_level": "LOW",
        },
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "session_manifest_too_large"


def test_ingest_endpoint_accepts_valid_manifest(client, sample_csv_bytes):
    _enroll(client)
    scenario_sha256 = "a" * 64
    manifest = {
            "manifest_version": 3,
            "metrics_schema_version": "2.0",
            "generated_by": {
                "component": "matb_integration.scenario_builder",
                "version": "3.0.0",
                "source_commit": "b" * 40,
                "source_dirty": False,
                "provenance_status": "complete",
            },
        "workload_label_status": "engineering_preset_pending_human_calibration",
        "artifact_scope": "session_bound",
        "participant_id": "P01",
        "visit_ordinal": 1,
        "workload_level": "LOW",
        "block_duration_sec": 900,
        "seed": 42,
        "scenario": {"filename": "run1.txt", "sha256": scenario_sha256},
        "questionnaires": {
            "isa": "isa_en.txt",
            "nasatlx": "nasatlx_en.txt",
            "bedford": "bedford_en.txt",
            "include_nasatlx": True,
            "include_bedford": False,
        },
            "expected": {
                "sysmon_target_opportunities": 0,
                "sysmon_nontarget_opportunities": 0,
                "comm_events": 0,
                "isa_probe_times_sec": [],
            "sagat_freezes": 0,
        },
    }
    manifest_content = json.dumps(manifest).encode("utf-8")
    generated_by = manifest["generated_by"]
    evidence = {
        "schema_version": "1.0",
        "status": "verified",
        "scenario_sha256": scenario_sha256,
        "adjacent_manifest_filename": "run1.txt.manifest.json",
        "scenario_manifest_sha256": hashlib.sha256(manifest_content).hexdigest(),
        "manifest_identity": {
            "manifest_schema_version": "3",
            "metrics_schema_version": "2.0",
            "experiment_spec_sha256": None,
            "experiment_seed": 42,
            "scenario_compiler_id": generated_by["component"],
            "scenario_compiler_version": generated_by["version"],
            "manifest_source_commit": generated_by["source_commit"],
            "manifest_source_dirty": False,
            "manifest_provenance_status": "complete",
        },
    }
    runtime_rows = io.StringIO()
    writer = csv.writer(runtime_rows, lineterminator="\n")
    writer.writerow([0, 0, "scenario_path", "", "", "run1.txt"])
    writer.writerow([0, 0, "scenario_sha256", "", "", scenario_sha256])
    writer.writerow([
        0, 0, "scenario_manifest_evidence", "", "",
        json.dumps(evidence, sort_keys=True),
    ])
    content = sample_csv_bytes(misses=(5.0, 25.0)) + runtime_rows.getvalue().encode()
    files = {
        "file": ("run1.csv", content, "text/csv"),
        "manifest": ("run1.txt.manifest.json", manifest_content, "application/json"),
    }
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    r = client.post("/ingest", files=files, data=data)
    assert r.status_code == 201, r.text
    assert r.json()["validation"]["status"] == "ok", r.json()


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


@pytest.mark.parametrize(
    "payload",
    [
        {"figures": [None]},
        {"figures": [{"name": "missing-option"}]},
        {"figures": [{"name": "x", "option": {}, "extra": True}]},
        {"figures": [{"name": "same name", "option": {}}, {"name": "same-name", "option": {}}]},
        {"figures": [{"name": f"figure-{index}", "option": {}} for index in range(17)]},
    ],
)
def test_research_bundle_rejects_ambiguous_or_unbounded_figure_sets(client, payload):
    response = client.post("/exports/research-bundle", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"


def test_research_bundle_rejects_nonfinite_or_oversized_figure_options(client):
    nonfinite = client.post(
        "/exports/research-bundle",
        content=b'{"figures":[{"name":"bad","option":{"value":NaN}}]}',
        headers={"content-type": "application/json"},
    )
    oversized = client.post(
        "/exports/research-bundle",
        json={"figures": [{"name": "large", "option": {"value": "x" * 300_000}}]},
    )

    assert nonfinite.status_code == 422
    assert nonfinite.json()["detail"]["code"] == "invalid_request"
    assert oversized.status_code == 413
    assert oversized.json()["detail"]["code"] == "station_queue_payload_too_large"


def test_research_exports_omit_stale_inference_after_new_ingest(client, sample_csv_bytes):
    stale = client.post("/analysis/run").json()
    _enroll(client)
    files = {"file": ("new.csv", sample_csv_bytes(misses=(7.0,)), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201

    context = client.get("/exports/research-context").json()

    assert context["analysis_latest"] is None
    assert context["analysis_status"] == "stale_artifact_omitted"
    assert context["current_data_fingerprint"] != stale["provenance"]["fingerprint"]

    bundle = client.post("/exports/research-bundle", json={})
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["analysis_status"] == "stale_artifact_omitted"
        assert manifest["current_data_fingerprint"] == context["current_data_fingerprint"]
        assert json.loads(archive.read("analysis_latest.json")) is None
