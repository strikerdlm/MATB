from uuid import uuid4
import hashlib
import json
import zipfile

import pytest

from sqlmodel import Session, select

from app.evidence_models import EvidenceCapture, EvidenceRun
from app.evidence_service import recover_evidence_runs
from matb_integration.evidence.contracts import canonical_bytes, strict_json
from matb_integration.evidence.reference import synthetic_capture
from matb_integration.evidence.__main__ import verify_bundle


def upload(client, bundle):
    return client.post("/ingest/evidence", files={k: (f"{k}.json", v, "application/octet-stream") for k, v in bundle.items()})


def test_capture_discovery_keeps_suite_practice_and_reports_review_states(client, seeded_participant, tmp_path):
    suite_id = str(uuid4())
    capture_ids = []
    for purpose in ("study", "practice"):
        bundle = synthetic_capture(tmp_path / purpose, purpose=purpose, identity=purpose)
        manifest = strict_json(bundle["capture_manifest"])
        manifest["parent_session_id"] = suite_id
        bundle["capture_manifest"] = canonical_bytes(manifest)
        response = upload(client, bundle)
        assert response.status_code == 201, response.text
        capture_ids.append(response.json()["id"])
    page = client.get("/evidence/captures", params={"purpose": "all", "session": suite_id, "q": "p01", "limit": 1}).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    item = page["items"][0]
    assert item["parent_session_id"] == suite_id
    assert item["visit_ordinal"] == 1
    assert item["created_at"]  # Registration time, not claimed acquisition time.
    assert item["created_at"].endswith(("Z", "+00:00"))
    assert item["capture_status"] in {"reconciled", "partially_excluded"}
    assert item["qualification"]["physical_timing"] == "not_qualified"
    assert item["qualification"]["protocol_eligibility"]["status"] == "not_assessed"
    assert not ({"manifest_json", "manifest", "metrics", "runs", "reconciliation"} & item.keys())
    assert client.get("/evidence/captures", params={"purpose": "all", "session": str(uuid4())}).json()["total"] == 0
    assert client.get("/evidence/captures", params={"purpose": "all", "q": capture_ids[0]}).json()["total"] == 1
    assert client.get("/evidence/captures", params={"purpose": "all", "q": "%"}).json()["total"] == 0
    assert client.get(f"/evidence/captures/{capture_ids[1]}").json()["id"] == capture_ids[1]


def test_round_trip_inspector_and_offline_recomputation(client, engine, seeded_participant, tmp_path):
    bundle = synthetic_capture(tmp_path / "source")
    response = upload(client, bundle)
    assert response.status_code == 201, response.text
    capture = response.json()
    assert capture["reconciliation"]["issues"] == []
    cid = capture["id"]
    assert upload(client, bundle).status_code == 200
    assert client.get("/evidence/captures").json()["total"] == 1
    metric = next(m for m in capture["metrics"] if m["metric"] == "track_rmse_deviation")
    records = client.get(f"/evidence/captures/{cid}/records", params={"metric_id": metric["id"], "limit": 2}).json()
    assert records["total"] > 2 and len(records["items"]) == 2
    eid = records["items"][0]["event_id"]
    timing = client.get(f"/evidence/captures/{cid}/records", params={"event_id": eid, "stream": "timing"}).json()
    assert timing["items"][0]["kind"] == "software_receipt"
    assert timing["raw_items"][0].encode() in bundle["timing"].splitlines(keepends=True)
    assert client.get(f"/evidence/captures/{cid}/metrics/{metric['id']}").json()["value"] == metric["value"]
    exported = client.get(f"/evidence/captures/{cid}/export")
    assert exported.status_code == 200
    assert exported.content == client.get(f"/evidence/captures/{cid}/export").content
    path = tmp_path / "bundle.zip"
    path.write_bytes(exported.content)
    result = verify_bundle(str(path))
    assert result["fingerprint"] == capture["reconciliation"]["fingerprint"]
    # An intact source bundle must not validate a report with altered links,
    # even when its file-level checksums have been recomputed.
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    report = strict_json(files["report.json"])
    report["metrics"][0]["sources"] = []
    files["report.json"] = canonical_bytes(report)
    files["checksums.json"] = canonical_bytes({name: hashlib.sha256(content).hexdigest()
                                              for name, content in files.items() if name != "checksums.json"})
    tampered = tmp_path / "altered-links.zip"
    with zipfile.ZipFile(tampered, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError, match="source links differ"):
        verify_bundle(str(tampered))
    selected = client.post("/evidence/analysis-inputs", json={"metric_ids": [metric["id"]]})
    assert selected.status_code == 200, selected.text
    assert client.get(f"/evidence/analysis-inputs/{selected.json()['id']}").json() == selected.json()
    comm = next(m for m in capture["metrics"] if m["metric"] == "comm_d_prime")
    assert client.post("/evidence/analysis-inputs", json={"metric_ids": [comm["id"]]}).status_code == 409
    with Session(engine) as db:
        assert len(db.exec(select(EvidenceCapture)).all()) == 1


def test_conflict_integrity_and_identity_are_explicit(client, seeded_participant, tmp_path):
    bundle = synthetic_capture(tmp_path)
    assert upload(client, bundle).status_code == 201
    modified = strict_json(bundle["capture_manifest"])
    modified["condition"] = "CHANGED"
    assert upload(client, {**bundle, "capture_manifest": canonical_bytes(modified)}).status_code == 409
    assert upload(client, {**bundle, "events": bundle["events"] + b"\n"}).status_code == 422
    modified["capture_id"] = str(uuid4())
    modified["participant_id"] = "UNKNOWN"
    assert upload(client, {**bundle, "capture_manifest": canonical_bytes(modified)}).status_code == 422


def test_practice_and_repeated_blocks_are_separate(client, seeded_participant, tmp_path):
    first = upload(client, synthetic_capture(tmp_path / "a", tasks=("track",), identity="a")).json()
    second = upload(client, synthetic_capture(tmp_path / "b", tasks=("track",), identity="b")).json()
    practice = upload(client, synthetic_capture(tmp_path / "p", purpose="practice", identity="p")).json()
    assert first["block_instance_id"] != second["block_instance_id"]
    assert client.get("/evidence/captures").json()["total"] == 2
    assert client.get("/evidence/captures", params={"purpose": "practice"}).json()["total"] == 1
    mid = practice["metrics"][0]["id"]
    assert client.post("/evidence/analysis-inputs", json={"metric_ids": [mid]}).status_code == 409
    assert client.get(f"/evidence/captures/{first['id']}/metrics/{mid}").status_code == 404


def test_failed_derivation_recovery_and_retry(client, engine, seeded_participant, tmp_path):
    bundle = synthetic_capture(tmp_path, completion="interrupted")
    capture = upload(client, bundle).json()
    assert capture["reconciliation"]["status"] == "failed"
    with Session(engine) as db:
        db.add(EvidenceRun(id="crashed", capture_id=capture["id"], version="test"))
        db.commit()
    recover_evidence_runs(engine)
    with Session(engine) as db:
        assert db.get(EvidenceRun, "crashed").reason == "interrupted_processing"
    assert client.post(f"/evidence/captures/{capture['id']}/reconcile").status_code == 200
    report = client.get(f"/evidence/captures/{capture['id']}").json()
    assert len(report["runs"]) == 3
    assert not any(m["confirmatory_eligible"] for m in report["metrics"])


def test_new_tables_do_not_change_legacy_long_metrics(client, seeded_participant, tmp_path):
    before = client.get("/metrics/long").json()
    assert upload(client, synthetic_capture(tmp_path)).status_code == 201
    assert client.get("/metrics/long").json() == before


def test_request_limit_applies_before_multipart_parsing(client):
    response = client.post("/ingest/evidence", content=b"", headers={"Content-Length": str(1024 * 1024 * 1024)})
    assert response.status_code == 413


def test_inspector_preserves_original_text_and_large_clock_values(client, seeded_participant, tmp_path):
    bundle = synthetic_capture(tmp_path)
    rows = [strict_json(line) for line in bundle["timing"].splitlines()]
    for index, row in enumerate(rows):
        row["value"] = 2**53 + index * 2 + 1
    # Noncanonical whitespace and unsafe JavaScript integers are source evidence.
    bundle["timing"] = b"".join((json.dumps(row, separators=(", ", ": ")) + "\n").encode() for row in rows)
    manifest = strict_json(bundle["capture_manifest"])
    manifest["artifacts"]["timing"].update(sha256=hashlib.sha256(bundle["timing"]).hexdigest(), size_bytes=len(bundle["timing"]))
    bundle["capture_manifest"] = canonical_bytes(manifest)
    response = upload(client, bundle)
    assert response.status_code == 201, response.text
    page = client.get(f"/evidence/captures/{response.json()['id']}/records", params={"stream": "timing"}).json()
    assert page["raw_items"][0].encode() == bundle["timing"].splitlines(keepends=True)[0]
    assert page["value_texts"][0] == str(2**53 + 1)


def test_imported_capture_links_unknown_purpose_without_rewriting_manifest(client, engine, seeded_participant, tmp_path):
    bundle = synthetic_capture(tmp_path / 'external')
    response = upload(client, bundle)
    assert response.status_code == 201, response.text
    capture_id = response.json()['id']
    association = client.get(f'/assessments/sources/evidence_capture/{capture_id}')
    assert association.status_code == 200, association.text
    a = association.json()
    history = client.get(f"/purpose-provenance/{a['purpose_provenance_id']}").json()
    assert history['current']['classification'] == 'unknown'
    assert history['current']['actor'] == 'system:migration'
    assert upload(client, bundle).status_code == 200
    assert client.get(f'/assessments/sources/evidence_capture/{capture_id}').json()['id'] == a['id']
    with Session(engine) as db:
        assert db.get(EvidenceCapture, capture_id).manifest_json.encode() == bundle['capture_manifest']
