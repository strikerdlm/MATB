from __future__ import annotations

import hashlib
from datetime import date
from io import BytesIO
import json
from pathlib import Path
import zipfile

import pytest
from sqlmodel import Session, select

from app.bundle_ingestion import ingest_scientific_bundle
from app.ingestion import IngestionError
from app.models import BlockArtifact, BlockBundle, Participant, Visit
from matb_integration.scientific_data.schema import SAMPLE_FIELDS, TRIAL_FIELDS


def _bundle_bytes(*, tamper: bool = False) -> bytes:
    schema = "matb-scientific-bundle-v1"
    artifacts = {
        "events.csv": (
            "logtime,scenario_time,type,module,address,value\n"
            "1,1,performance,sysmon,signal_detection,HIT\n"
            "2,1,performance,sysmon,response_time,500\n"
        ).encode(),
        "samples.csv": (",".join(field.name for field in SAMPLE_FIELDS) + "\n").encode(),
        "samples.parquet": b"PAR1-test-fixture-PAR1",
        "trials.csv": (",".join(field.name for field in TRIAL_FIELDS) + "\n").encode(),
        "summary.json": json.dumps({
            "schema_version": schema,
            "status": "complete",
            "session_id": "S01",
            "timing_quality_status": "ok",
            "sysmon": {"raw": {"n_hits": 1}},
        }).encode(),
        "manifest.json": json.dumps({
            "schema_version": schema,
            "session_id": "S01",
            "source": {},
        }).encode(),
        "data_dictionary.json": json.dumps({"schema_version": schema, "tables": {}}).encode(),
        "quality.json": json.dumps({"status": "ok", "issues": []}).encode(),
    }
    checksums = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(artifacts.items())
    ).encode()
    artifacts["checksums.sha256"] = checksums
    if tamper:
        artifacts["summary.json"] += b" "
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in artifacts.items():
            archive.writestr(name, content)
    return output.getvalue()


def _seed(engine) -> None:
    with Session(engine) as session:
        session.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        session.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        session.commit()


def test_bundle_ingestion_validates_persists_metadata_and_keeps_samples_out_of_sql(engine, tmp_path: Path) -> None:
    _seed(engine)
    content = _bundle_bytes()

    with Session(engine) as session:
        bundle = ingest_scientific_bundle(
            session,
            content=content,
            filename="session.matb.zip",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            artifact_root=tmp_path / "bundles",
        )
        artifacts = session.exec(select(BlockArtifact).where(BlockArtifact.bundle_id == bundle.id)).all()

        assert isinstance(bundle, BlockBundle)
        assert bundle.schema_version == "matb-scientific-bundle-v1"
        assert bundle.quality_status == "ok"
        assert len(artifacts) == 9
        assert {artifact.name for artifact in artifacts} >= {"samples.csv", "samples.parquet", "summary.json"}
        assert (tmp_path / "bundles" / bundle.stored_filename).read_bytes() == content
        assert "samples_json" not in BlockBundle.model_fields


def test_bundle_ingestion_rejects_checksum_tampering_before_writing_database(engine, tmp_path: Path) -> None:
    _seed(engine)

    with Session(engine) as session:
        with pytest.raises(IngestionError, match="checksum_mismatch:summary.json"):
            ingest_scientific_bundle(
                session,
                content=_bundle_bytes(tamper=True),
                filename="session.matb.zip",
                participant_id="P01",
                visit_ordinal=1,
                workload_level="LOW",
                artifact_root=tmp_path / "bundles",
            )
        assert session.exec(select(BlockBundle)).all() == []
        assert not (tmp_path / "bundles").exists()


def test_bundle_sha_cannot_be_rebound_to_another_block(engine, tmp_path: Path) -> None:
    _seed(engine)
    content = _bundle_bytes()

    with Session(engine) as session:
        ingest_scientific_bundle(
            session,
            content=content,
            filename="session.matb.zip",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            artifact_root=tmp_path / "bundles",
        )
        with pytest.raises(IngestionError, match="bundle already ingested"):
            ingest_scientific_bundle(
                session,
                content=content,
                filename="copy.matb.zip",
                participant_id="P01",
                visit_ordinal=1,
                workload_level="LOW",
                artifact_root=tmp_path / "bundles",
            )


def test_bundle_http_ingest_lists_and_downloads_verified_artifacts(client, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MATB_OPENMATB_BUNDLE_DIR", str(tmp_path / "bundles"))
    assert client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"}).status_code == 201

    response = client.post(
        "/ingest-bundle",
        data={"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"},
        files={"file": ("session.matb.zip", _bundle_bytes(), "application/zip")},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    block_id = payload["block_id"]
    listing = client.get(f"/blocks/{block_id}/artifacts")
    assert listing.status_code == 200
    assert any(item["name"] == "summary.json" for item in listing.json())
    summary = client.get(f"/blocks/{block_id}/artifacts/summary.json")
    assert summary.status_code == 200
    assert summary.json()["session_id"] == "S01"
    download = client.get(f"/blocks/{block_id}/bundle")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == payload["bundle_sha256"]
