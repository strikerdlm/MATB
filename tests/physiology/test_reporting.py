from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from matb_integration.physiology.reporting import (
    BundleImmutableError,
    build_session_bundle,
    compute_phase_reactivity,
)


def _phase(mean_hr: float, rmssd: float, lf: float, hf: float) -> dict:
    return {
        "quality": {"label": "excellent", "corrected_pct": 0.0},
        "time_domain": {
            "status": "ok",
            "metrics": {
                "mean_hr_bpm": mean_hr,
                "rmssd_ms": rmssd,
                "ln_rmssd": 3.0,
                "sdnn_ms": 40.0,
            },
        },
        "frequency_domain": {
            "status": "ok",
            "metrics": {
                "lf_power_ms2": lf,
                "hf_power_ms2": hf,
                "lf_hf_ratio": lf / hf,
            },
            "psd": [
                {"frequency_hz": 0.1, "power_ms2_per_hz": lf},
                {"frequency_hz": 0.2, "power_ms2_per_hz": hf},
            ],
        },
    }


def test_reactivity_is_reported_as_directional_descriptive_change() -> None:
    result = compute_phase_reactivity(
        {
            "baseline": _phase(60.0, 50.0, 500.0, 1000.0),
            "task": _phase(72.0, 35.0, 800.0, 600.0),
            "recovery": _phase(64.0, 45.0, 600.0, 900.0),
        }
    )

    assert result["baseline_to_task"]["mean_hr_bpm"] == 12.0
    assert result["baseline_to_task"]["rmssd_ms"] == -15.0
    assert result["task_to_recovery"]["mean_hr_bpm"] == -8.0
    assert result["task_to_recovery"]["hf_power_ms2"] == 300.0


def test_bundle_contains_bilingual_reports_raw_rr_psd_and_verified_checksums(
    tmp_path: Path,
) -> None:
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(
        "logtime,scenario_time,type,module,address,value\n",
        encoding="utf-8",
    )
    events = tmp_path / "source.events.jsonl"
    events.write_text('{"event":"scenario_started"}\n', encoding="utf-8")
    run_dir = tmp_path / "bundle"
    phases = {
        "baseline": _phase(60.0, 50.0, 500.0, 1000.0),
        "task": _phase(72.0, 35.0, 800.0, 600.0),
        "recovery": _phase(64.0, 45.0, 600.0, 900.0),
    }
    phases["task"]["frequency_domain"] = {
        "status": "not_computable",
        "reason_codes": ["beat_coverage_below_95pct", "bluetooth_disconnect"],
        "metrics": None,
        "psd": [],
    }
    rr_records = [
        {
            "session_id": "session-1",
            "phase": "baseline",
            "segment_id": "segment-1",
            "beat_index": 0,
            "notification_index": 0,
            "rr_index_in_notification": 0,
            "heart_rate_bpm": 60,
            "rr_ticks_1024": 1024,
            "rr_ms": 1000.0,
            "corrected_rr_ms": 990.0,
            "is_artifact": True,
            "notification_received_monotonic_ns": 2_000_000_000,
            "estimated_beat_monotonic_ns": 2_000_000_000,
            "timestamp_source": "host_rr_robust_offset_v1",
        }
    ]

    artifacts = build_session_bundle(
        run_dir,
        session={
            "session_id": "session-1",
            "participant_id": "P01",
            "visit_ordinal": 1,
            "workload_level": "LOW",
            "scenario_name": "military_aviation/low_workload.txt",
            "status": "COMPLETE",
            "task_validity": "valid",
            "physiology_quality": "excellent",
        },
        matb_metrics={"tracking": {"in_target_pct": 80.0}, "isa": {"mean": 2.0}},
        phase_results=phases,
        rr_records=rr_records,
        clock_anchors=[{"anchor_index": 0, "utc_ns": 10, "monotonic_midpoint_ns": 5}],
        openmatb_csv=source_csv,
        synchronized_events=events,
    )

    expected = {
        "report.en.md",
        "report.es.md",
        "session.json",
        "session-metrics.csv",
        "rr-intervals.csv",
        "rr-intervals.jsonl",
        "hrv-psd.csv",
        "openmatb-session.csv",
        "openmatb-events.jsonl",
        "clock-anchors.json",
        "manifest.json",
        "checksums.sha256",
    }
    assert {artifact.relative_path for artifact in artifacts} == expected
    assert "Research use only" in (run_dir / "report.en.md").read_text(encoding="utf-8")
    assert "Solo para uso en investigación" in (run_dir / "report.es.md").read_text(encoding="utf-8")
    assert "beat_coverage_below_95pct; bluetooth_disconnect" in (
        run_dir / "report.en.md"
    ).read_text(encoding="utf-8")
    english_report = (run_dir / "report.en.md").read_text(encoding="utf-8")
    assert "## Complete HRV metrics" in english_report
    assert "| baseline | time_domain | rmssd_ms | 50.0 | ok |" in english_report
    assert (
        "| baseline | frequency_domain | hf_power_ms2 | 1000.0 | ok |"
        in english_report
    )
    rr_json = json.loads((run_dir / "rr-intervals.jsonl").read_text())
    assert rr_json["rr_ticks_1024"] == 1024
    assert rr_json["notification_received_monotonic_ns"] == "2000000000"
    session_json = json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
    assert session_json["schema_version"] == "matb-classic-bundle-v2"
    assert session_json["contracts"]["rr"] == "polar-h10-rr-v2"
    assert session_json["contracts"]["nanoseconds"] == "decimal_string_v1"
    anchors_json = json.loads((run_dir / "clock-anchors.json").read_text())
    assert anchors_json["anchors"][0]["utc_ns"] == "10"
    with (run_dir / "session-metrics.csv").open(newline="", encoding="utf-8") as stream:
        metric_rows = list(csv.DictReader(stream))
    assert any(row["metric"] == "in_target_pct" and row["value"] == "80.0" for row in metric_rows)
    assert any(
        row["domain"] == "frequency_domain"
        and row["status"] == "not_computable"
        and row["reason_code"] == "beat_coverage_below_95pct;bluetooth_disconnect"
        for row in metric_rows
    )

    checksum_lines = (run_dir / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    for line in checksum_lines:
        digest, relative = line.split("  ", 1)
        assert hashlib.sha256((run_dir / relative).read_bytes()).hexdigest() == digest
    if os.name != "nt":
        assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE((run_dir / relative).stat().st_mode) == 0o600
            for relative in expected
        )


def test_bundle_refuses_to_overwrite_a_finalized_artifact(tmp_path: Path) -> None:
    run_dir = tmp_path / "bundle"
    run_dir.mkdir()
    (run_dir / "session.json").write_text("{}", encoding="utf-8")
    source_csv = tmp_path / "source.csv"
    source_csv.write_text("header\n", encoding="utf-8")

    with pytest.raises(BundleImmutableError, match="artifact_immutable:session.json"):
        build_session_bundle(
            run_dir,
            session={"session_id": "session-1"},
            matb_metrics={},
            phase_results={},
            rr_records=[],
            clock_anchors=[],
            openmatb_csv=source_csv,
        )


def test_bundle_publish_rolls_back_every_visible_artifact_on_replace_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "bundle"
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(
        "logtime,scenario_time,type,module,address,value\n",
        encoding="utf-8",
    )
    original_replace = __import__("os").replace
    calls = 0

    def fail_during_publish(source, destination):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("injected_publish_failure")
        return original_replace(source, destination)

    monkeypatch.setattr("matb_integration.physiology.reporting.os.replace", fail_during_publish)

    with pytest.raises(OSError, match="injected_publish_failure"):
        build_session_bundle(
            run_dir,
            session={"session_id": "session-rollback"},
            matb_metrics={},
            phase_results={},
            rr_records=[],
            clock_anchors=[],
            openmatb_csv=source_csv,
        )

    assert not any((run_dir / name).exists() for name in {
        "session.json",
        "session-metrics.csv",
        "rr-intervals.csv",
        "rr-intervals.jsonl",
        "hrv-psd.csv",
        "openmatb-session.csv",
        "openmatb-events.jsonl",
        "clock-anchors.json",
        "report.en.md",
        "report.es.md",
        "manifest.json",
        "checksums.sha256",
    })


def test_bundle_publication_fsyncs_commit_and_rollback_directory_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_csv = tmp_path / "source.csv"
    source_csv.write_text("logtime,scenario_time,type,module,address,value\n", encoding="utf-8")
    successful = tmp_path / "successful"
    synced: list[Path] = []
    monkeypatch.setattr(
        "matb_integration.physiology.reporting._fsync_directory",
        lambda path: synced.append(Path(path)),
    )

    build_session_bundle(
        successful,
        session={"session_id": "session-durable"},
        matb_metrics={},
        phase_results={},
        rr_records=[],
        clock_anchors=[],
        openmatb_csv=source_csv,
    )

    assert successful in synced
    synced.clear()
    failing = tmp_path / "failing"
    original_replace = __import__("os").replace
    calls = 0

    def fail_after_one_publish(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("publish failed")
        return original_replace(source, destination)

    monkeypatch.setattr("matb_integration.physiology.reporting.os.replace", fail_after_one_publish)
    with pytest.raises(OSError, match="publish failed"):
        build_session_bundle(
            failing,
            session={"session_id": "session-rollback-durable"},
            matb_metrics={},
            phase_results={},
            rr_records=[],
            clock_anchors=[],
            openmatb_csv=source_csv,
        )

    assert failing in synced
