from __future__ import annotations

from datetime import datetime, timezone
import json

import pyarrow.parquet as pq

from matb_integration.physiology.artifacts import ParquetCaptureWriter
from matb_integration.physiology.contracts import PolarArtifactManifestV1


def test_parquet_artifacts_finalize_atomically_with_hashes(tmp_path) -> None:
    capture_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    writer = ParquetCaptureWriter(tmp_path, capture_id)
    writer.write_rows("rr", [{
        "notification_index": 1, "beat_index": 1, "received_monotonic_ns": 10,
        "received_utc_ns": 20, "beat_monotonic_ns": 10, "rr_ticks_1024": 1024,
        "rr_ms": 1000.0, "heart_rate_bpm": 60, "contact_supported": True,
        "contact_detected": True, "gap_before": True, "connection_epoch": 0,
    }])
    now = datetime.now(timezone.utc)
    manifest = writer.finalize(PolarArtifactManifestV1(
        capture_id=capture_id, participant_pseudonym="P01",
        matb_session_kind="generic", matb_session_id="test", started_at_utc=now,
        ended_at_utc=now, requested_settings={}, resolved_settings={}, clock_model={},
        stream_counters={}, algorithm_versions={}, artifacts=(),
    ))

    root = tmp_path / capture_id
    assert not list(root.glob("*.partial"))
    assert pq.read_table(root / "rr.parquet").num_rows == 1
    ecg_table = pq.read_table(root / "ecg.parquet")
    acc_table = pq.read_table(root / "acc.parquet")
    assert ecg_table.num_rows == 0
    assert acc_table.num_rows == 0
    assert "reconstructed_monotonic_ns" in ecg_table.column_names
    assert "reconstructed_monotonic_ns" in acc_table.column_names
    assert len(manifest.artifacts) == 3
    on_disk = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["artifacts"][0]["sha256"] == manifest.artifacts[0].sha256


def test_abort_retains_partial_files(tmp_path) -> None:
    writer = ParquetCaptureWriter(tmp_path, "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    writer.abort()
    assert len(list(writer.capture_root.glob("*.partial"))) == 3
