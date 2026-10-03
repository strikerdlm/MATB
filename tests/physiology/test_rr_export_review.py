from datetime import datetime, timezone
import csv
import json

import numpy as np
import pytest

from matb_integration.physiology.artifacts import ParquetCaptureWriter
from matb_integration.physiology.contracts import PolarArtifactManifestV1
from matb_integration.physiology.rr_export import RRExportError, export_rr_capture, sha256
from matb_integration.physiology.respiration import estimate_acc_respiration
from matb_integration.physiology.review import review_capture


def finalize(tmp_path, values, *, gaps=(), epochs=None, contact=True):
    identity = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    writer = ParquetCaptureWriter(tmp_path, identity)
    rows = []
    for i, ticks in enumerate(values):
        rows.append(dict(beat_index=i + 1, notification_index=i + 1, rr_ticks_1024=ticks,
                         rr_ms=ticks * 1000 / 1024, received_monotonic_ns=(i+1)*1_000_000_000,
                         beat_monotonic_ns=(i+1)*1_000_000_000, received_utc_ns=(i+1)*1_000_000_000,
                         heart_rate_bpm=60, contact_supported=True, contact_detected=contact,
                         gap_before=i in gaps, connection_epoch=epochs[i] if epochs else 0))
    writer.write_rows("rr", rows)
    now = datetime.now(timezone.utc)
    manifest = writer.finalize(PolarArtifactManifestV1(
        capture_id=identity, participant_pseudonym="P01", execution_purpose="practice",
        matb_session_kind="generic", matb_session_id="test", started_at_utc=now,
        ended_at_utc=now, requested_settings={}, resolved_settings={}, clock_model={},
        stream_counters={}, algorithm_versions={}, artifacts=(),
    ))
    return writer.capture_root, manifest


def test_rr_text_keeps_exact_ticks_units_and_original_artifacts(tmp_path):
    root, manifest = finalize(tmp_path, [1024, 1025, 1023], gaps=(0,))
    raw_hashes = {name: sha256(root / name) for name in ("rr.parquet", "ecg.parquet", "acc.parquet", "manifest.json")}
    result = export_rr_capture(root, manifest)
    assert result["rr_count"] == 3
    assert result["segment_count"] == 1
    segment = result["segments"][0]
    assert (root / "rr-export" / segment["txt_filename"]).read_text() == "1000\n1000.9765625\n999.0234375\n"
    assert (root / "rr-export" / segment["csv_filename"]).read_text() == "rr_ms\n1000\n1000.9765625\n999.0234375\n"
    assert "practice" in segment["txt_filename"]
    assert raw_hashes == {name: sha256(root / name) for name in raw_hashes}
    assert export_rr_capture(root, manifest) == result


def test_exports_split_gaps_epochs_and_invalid_values_without_dropping_trace(tmp_path):
    root, manifest = finalize(tmp_path, [1024, 1025, 1026, 0, 1027, 1028], gaps=(0, 2), epochs=[0, 0, 0, 0, 0, 1])
    result = export_rr_capture(root, manifest)
    assert result["segment_count"] == 4
    assert result["rr_count"] == 5
    assert result["excluded_nonpositive_or_nonfinite"] == 1
    trace = next(f for f in result["files"] if f["kind"] == "trace_csv")
    with (root / "rr-export" / trace["filename"]).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6 and rows[3]["rr_ms"] == "0.0" and rows[3]["exported"] == "0"
    assert sum(segment["rr_count"] for segment in result["segments"]) == 5


def test_tampered_raw_or_export_is_not_silently_redownloaded(tmp_path):
    root, manifest = finalize(tmp_path, [1024, 1025])
    result = export_rr_capture(root, manifest)
    (root / "rr-export" / result["segments"][0]["txt_filename"]).write_text("123\n")
    with pytest.raises(RRExportError, match="checksum"):
        export_rr_capture(root, manifest)
    with (root / "rr.parquet").open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(RRExportError, match="checksum"):
        export_rr_capture(root, manifest)


def test_empty_capture_exports_no_manufactured_rr_or_metrics(tmp_path):
    root, manifest = finalize(tmp_path, [])
    result = export_rr_capture(root, manifest)
    assert result["segments"] == [] and result["rr_count"] == 0
    reviewed = review_capture(root, manifest)
    assert reviewed["metrics"] is None
    assert reviewed["respiration"]["respiratory_rate_bpm"] is None
    json.dumps(reviewed, allow_nan=False)


@pytest.mark.parametrize("rate", [25, 50, 100, 200])
@pytest.mark.parametrize("brpm", [12, 18, 24, 30])
def test_synthetic_acc_respiration_frequency_and_rotation(rate, brpm):
    times = np.arange(0, 90, 1 / rate)
    rotation = 0.02 * np.sin(2 * np.pi * brpm / 60 * times)
    axes = np.column_stack([1000 * np.sin(rotation), np.zeros(len(times)), 1000 * np.cos(rotation)])
    result = estimate_acc_respiration(times, axes, np.zeros(len(times)), np.arange(len(times)), rate)
    assert result["status"] == "estimated"
    assert abs(result["respiratory_rate_bpm"] - brpm) < 1.1
    assert result["validated_against_reference"] is False and result["accuracy_bpm"] is None


@pytest.mark.parametrize("problem", ["short", "flat", "movement", "gap", "irregular_rate"])
def test_respiration_withholds_unsupported_signal(problem):
    rate = 50
    times = np.arange(0, 90, 1 / rate)
    axes = np.column_stack([20 * np.sin(2 * np.pi * 0.25 * times), np.zeros(len(times)), np.full(len(times), 1000)])
    epochs = np.zeros(len(times))
    if problem == "short":
        times, axes, epochs = times[:500], axes[:500], epochs[:500]
    elif problem == "flat":
        axes[:, 0] = 0
    elif problem == "movement":
        axes[:, 0] += 200 * np.sin(2 * np.pi * 2 * times)
    elif problem == "gap":
        epochs[len(times)//2:] = 1
    else:
        times *= 1.2
    result = estimate_acc_respiration(times, axes, epochs, np.arange(len(times)), rate)
    assert result["respiratory_rate_bpm"] is None


def test_review_short_window_keeps_time_metrics_and_withholds_spectrum(tmp_path):
    root, manifest = finalize(tmp_path, [1024 + int(20 * np.sin(i / 5)) for i in range(90)])
    result = review_capture(root, manifest)
    assert result["metrics"]["valid"]
    assert result["metrics"]["window_kind"] == "short_exploratory"
    assert result["metrics"]["lf_power_ms2"] is None and not result["metrics"].get("spectrum")
    assert len(result["poincare"]) > 0
    json.dumps(result, allow_nan=False)


def test_review_does_not_bridge_gaps_or_bad_contact(tmp_path):
    root, manifest = finalize(tmp_path, [1024] * 100, gaps=(0, 50), contact=False)
    result = review_capture(root, manifest)
    assert not result["metrics"]["valid"]
    assert result["poincare"] == []
    assert any(y is None for _, y in result["rr_tachogram"])
