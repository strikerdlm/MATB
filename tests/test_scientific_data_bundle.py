from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

import pyarrow.parquet as pq

from matb_integration.scientific_data.bundle import validate_bundle, write_checksums
from matb_integration.scientific_data.recorder import ResearchRecorder


def _legacy_events(path: Path) -> Path:
    path.write_text(
        "logtime,scenario_time,type,module,address,value\n"
        "1.0,0.05,event,track,self,start\n",
        encoding="utf-8",
    )
    return path


def test_recorder_seals_a_checksum_verified_csv_json_parquet_bundle(tmp_path: Path) -> None:
    run_dir = tmp_path / "session.research"
    recorder = ResearchRecorder(
        session_id="S001",
        run_dir=run_dir,
        sample_hz=20.0,
        start_monotonic_ns=0,
        start_utc_ns=1_800_000_000_000_000_000,
        manifest={"scenario": {"filename": "low.txt", "sha256": "abc"}},
        score_config={"tracking_range": 100.0},
    )
    assert recorder.maybe_sample(
        monotonic_ns=50_000_000,
        scenario_time_s=0.05,
        scenario_paused=False,
        event_sequence=2,
        state={
            "tracking_alive": True,
            "tracking_cursor_x": 0.1,
            "tracking_cursor_y": -0.2,
            "tracking_deviation": 12.5,
            "tracking_in_target": False,
        },
    )
    recorder.record_trial({
        "trial_id": "sysmon-000001",
        "task": "sysmon",
        "trial_type": "signal",
        "stimulus_id": "F5",
        "onset_s": 0.0,
        "deadline_s": 10.0,
        "response_s": 0.5,
        "rt_ms": 500.0,
        "outcome": "HIT",
        "correct": True,
        "timeout": False,
        "actor": "manual",
        "automation_active": False,
        "target_json": {"indicator": "F5"},
        "response_json": {"button": "F5"},
    })

    bundle_path = recorder.seal(events_csv=_legacy_events(tmp_path / "legacy.csv"))

    assert bundle_path == tmp_path / "session.matb.zip"
    assert bundle_path.is_file()
    assert validate_bundle(bundle_path)["status"] == "ok"
    expected = {
        "events.csv",
        "samples.csv",
        "samples.parquet",
        "trials.csv",
        "summary.json",
        "manifest.json",
        "data_dictionary.json",
        "quality.json",
        "checksums.sha256",
    }
    assert expected == {path.name for path in run_dir.iterdir()}

    with (run_dir / "samples.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    parquet_rows = pq.read_table(run_dir / "samples.parquet").to_pylist()
    assert len(csv_rows) == len(parquet_rows) == 1
    assert float(csv_rows[0]["tracking_deviation"]) == parquet_rows[0]["tracking_deviation"] == 12.5
    assert json.loads(csv_rows[0]["sysmon_pending_ids_json"]) == []

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["sysmon"]["scores"]["canonical_rt_efficiency"]["value"] == 95.0
    assert summary["tracking"]["scores"]["canonical_performance"]["value"] == 87.5
    assert summary["timing_quality_status"] == "ok"
    assert "global_score" not in summary

    with zipfile.ZipFile(bundle_path) as archive:
        assert set(archive.namelist()) == expected


def test_bundle_validation_detects_tampering(tmp_path: Path) -> None:
    run_dir = tmp_path / "session.research"
    recorder = ResearchRecorder(
        session_id="S002",
        run_dir=run_dir,
        sample_hz=20.0,
        start_monotonic_ns=0,
        start_utc_ns=0,
    )
    recorder.maybe_sample(
        monotonic_ns=50_000_000,
        scenario_time_s=0.05,
        scenario_paused=False,
        event_sequence=0,
        state={},
    )
    recorder.seal(events_csv=_legacy_events(tmp_path / "legacy.csv"))
    (run_dir / "samples.csv").write_text("tampered\n", encoding="utf-8")

    result = validate_bundle(run_dir)

    assert result["status"] == "error"
    assert "checksum_mismatch:samples.csv" in result["codes"]


def test_partial_seal_is_explicit_and_recoverable(tmp_path: Path) -> None:
    run_dir = tmp_path / "aborted.research"
    recorder = ResearchRecorder(
        session_id="S003",
        run_dir=run_dir,
        sample_hz=20.0,
        start_monotonic_ns=0,
        start_utc_ns=0,
    )
    recorder.maybe_sample(
        monotonic_ns=220_000_000,
        scenario_time_s=0.22,
        scenario_paused=False,
        event_sequence=0,
        state={},
    )

    bundle_path = recorder.seal(
        events_csv=_legacy_events(tmp_path / "legacy.csv"),
        status="partial",
        reason="window_closed",
    )

    partial = json.loads((run_dir / "partial-run.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert partial == {"reason": "window_closed", "status": "partial"}
    assert summary["status"] == "partial"
    assert validate_bundle(bundle_path)["status"] == "ok"


def test_bundle_validation_checks_semantics_beyond_checksums(tmp_path: Path) -> None:
    run_dir = tmp_path / "semantic.research"
    recorder = ResearchRecorder(
        session_id="S004",
        run_dir=run_dir,
        sample_hz=20.0,
        start_monotonic_ns=0,
        start_utc_ns=0,
    )
    recorder.maybe_sample(
        monotonic_ns=50_000_000,
        scenario_time_s=0.05,
        scenario_paused=False,
        event_sequence=0,
        state={},
    )
    recorder.seal(events_csv=_legacy_events(tmp_path / "legacy.csv"))

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] = "unknown-v99"
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "samples.parquet").write_bytes(b"not-parquet")
    write_checksums(run_dir)

    result = validate_bundle(run_dir)

    assert result["status"] == "error"
    assert "schema_mismatch:manifest.json" in result["codes"]
    assert "parquet_magic_invalid:samples.parquet" in result["codes"]


def test_sample_stream_uses_configured_flush_and_fsync_cadence(tmp_path: Path) -> None:
    recorder = ResearchRecorder(
        session_id="S005",
        run_dir=tmp_path / "cadence.research",
        sample_hz=20.0,
        start_monotonic_ns=0,
        start_utc_ns=0,
        flush_interval_sec=1.0,
        fsync_interval_sec=5.0,
    )
    with patch("matb_integration.scientific_data.recorder.os.fsync") as fsync:
        recorder.maybe_sample(
            monotonic_ns=50_000_000,
            scenario_time_s=0.05,
            scenario_paused=False,
            event_sequence=0,
            state={},
        )
        recorder.maybe_sample(
            monotonic_ns=1_050_000_000,
            scenario_time_s=1.05,
            scenario_paused=False,
            event_sequence=0,
            state={},
        )
        assert recorder._last_flush_ns == 1_050_000_000
        assert fsync.call_count == 0
        recorder.maybe_sample(
            monotonic_ns=5_050_000_000,
            scenario_time_s=5.05,
            scenario_paused=False,
            event_sequence=0,
            state={},
        )
        assert recorder._last_fsync_ns == 5_050_000_000
        assert fsync.call_count == 1
        recorder._close_streams()
