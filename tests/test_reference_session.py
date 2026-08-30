from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from matb_integration.qualification.reference import build_reference_session, export_bids_events


def _metadata() -> dict:
    return {
        "session_id": "session-001",
        "participant_pseudonym": "P001",
        "locale": {"language": "es-CO", "instrument_version": "functional-pending-validation"},
        "scenario": {"profile_id": "MATB-EXTENDED-2.0", "sha256": "a" * 64, "manifest_sha256": "b" * 64},
        "runtime": {"source_commit": "deadbeef", "version": "1.4.5"},
        "metrics": {"schema_version": "2.0", "eligibility": "mixed"},
        "timing": {"rig_id": "rig-a", "qualification_status": "NOT_MEASURED", "session_qc_status": "PASS"},
    }


def test_reference_session_hashes_artifacts_and_rejects_identifiers(tmp_path: Path) -> None:
    artifact = tmp_path / "events.jsonl"
    artifact.write_text("{}\n", encoding="utf-8")
    result = build_reference_session(_metadata(), artifact_paths=[artifact], session_root=tmp_path)
    assert result["schema_version"] == "1.0"
    assert result["artifacts"][0]["path"] == "events.jsonl"
    assert len(result["artifacts"][0]["sha256"]) == 64
    identified = _metadata() | {"email": "participant@example.test"}
    with pytest.raises(ValueError, match="identifiers are forbidden"):
        build_reference_session(identified, artifact_paths=[artifact], session_root=tmp_path)


def test_bids_export_preserves_native_clock_boundary(tmp_path: Path) -> None:
    native = tmp_path / "session.events.jsonl"
    native.write_text(
        json.dumps(
            {
                "event_schema_version": "1.0",
                "sequence": 1,
                "scenario_time_s": 10.2,
                "record_type": "event",
                "module": "sysmon",
                "address": "F5-failure",
                "value": "1",
                "scheduled_scenario_time_s": 10.0,
                "dispatch_lateness_ms": 200.0,
                "clock_domain": "python.perf_counter",
            }
        ) + "\n",
        encoding="utf-8",
    )
    tsv = tmp_path / "events.tsv"
    sidecar = tmp_path / "events.json"
    export_bids_events(
        native,
        tsv,
        sidecar,
        profile_id="MATB-EXTENDED-2.0",
        scenario_sha256="a" * 64,
        source_commit="deadbeef",
        timing_qualification_status="NOT_MEASURED",
    )
    with tsv.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert rows[0]["onset"] == "10.2"
    assert rows[0]["trial_type"] == "event.sysmon.F5-failure"
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "not physical onset" in metadata["onset"]["Description"]
