from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

import pytest

from matb_integration.liftoff.metrics import VisibleResults
from matb_integration.liftoff.session import (
    LIFTOFF_PROFILE,
    LiftoffSessionRecorder,
    SessionLifecycleError,
)
from matb_integration.recording.artifacts import verify_checksum_file
from tests.liftoff.test_protocol import valid_payload


def _canonical(payload) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def manifest() -> dict[str, object]:
    configuration = {
        "track_id": "astra-neutral-time-trial-v1",
        "camera_angle_deg": 25,
        "rates_profile": "astra-v1",
    }
    return {
        "schema_version": "liftoff-session-manifest-v1",
        "session_id": "12345678-1234-5678-1234-567812345678",
        "participant_id": "P01",
        "visit_code": "T0",
        "attempt_number": 1,
        "protocol_id": "astra-2026",
        "protocol_version": "1.0.0",
        "liftoff_build": "synthetic-test-build",
        "track_id": "astra-neutral-time-trial-v1",
        "telemetry_profile": "liftoff-telemetry-all-v1",
        "expected_rate_hz": 60.0,
        "configuration_sha256": hashlib.sha256(_canonical(configuration)).hexdigest(),
        "configuration": configuration,
    }


def visible_results() -> VisibleResults:
    return VisibleResults(
        valid_lap_times_s=(61.2, 63.0, 60.8),
        invalid_laps=1,
        observer_restart_count=0,
    )


def questionnaires() -> dict[str, object]:
    return {"kss": 4, "nasa_tlx_raw": 52.5}


def complete_phases(recorder: LiftoffSessionRecorder) -> None:
    recorder.mark("recording_started")
    recorder.mark("baseline_started")
    recorder.mark("baseline_finished")
    recorder.mark("task_started")
    recorder.mark("task_finished")
    recorder.mark("recovery_started")
    recorder.mark("recovery_finished")
    recorder.mark("recording_finished")


def test_recorder_requires_ordered_phases_and_seals(tmp_path):
    recorder = LiftoffSessionRecorder.prepare(tmp_path, manifest=manifest())
    recorder.mark("recording_started")
    recorder.mark("baseline_started")
    with pytest.raises(SessionLifecycleError, match="task_before_baseline_finished"):
        recorder.mark("task_started")
    recorder.mark("baseline_finished")
    recorder.mark("task_started")
    recorder.mark("task_finished")
    recorder.mark("recovery_started")
    recorder.mark("recovery_finished")
    recorder.mark("recording_finished")
    recorder.attach_physiology_link({"status": "missing", "sync_quality": "missing"})

    artifacts = recorder.seal(results=visible_results(), questionnaires=questionnaires())

    assert (tmp_path / "checksums.sha256").is_file()
    assert verify_checksum_file(tmp_path, profile=LIFTOFF_PROFILE) == ()
    assert {artifact.path.name for artifact in artifacts} >= {
        "results.json",
        "questionnaires.json",
        "telemetry-quality.json",
        "metrics.json",
        "debrief.json",
        "checksums.sha256",
    }
    assert "composite_score" not in (tmp_path / "metrics.json").read_text(encoding="utf-8")
    with pytest.raises(SessionLifecycleError, match="session_sealed"):
        recorder.mark("amendment")


def test_raw_and_canonical_telemetry_append_as_one_frame(tmp_path):
    recorder = LiftoffSessionRecorder.prepare(tmp_path, manifest=manifest(), batch_size=2)
    recorder.mark("recording_started")
    recorder.mark("baseline_started")
    received_utc = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)

    recorder.append_packet(
        valid_payload(),
        received_monotonic_ns=123,
        received_utc=received_utc,
    )
    recorder.mark("baseline_finished")

    raw = (tmp_path / "telemetry.raw").read_bytes()
    magic, sequence, monotonic_ns, utc_ns, payload_length = struct.unpack("<4sQQqH", raw[:30])
    assert magic == b"LFT1"
    assert sequence == 1
    assert monotonic_ns == 123
    assert utc_ns == 1_786_975_200_000_000_000
    assert payload_length == 97
    assert raw[30:] == valid_payload()
    canonical = json.loads((tmp_path / "telemetry.jsonl").read_text(encoding="utf-8"))
    assert canonical["sequence"] == 1
    assert canonical["simulator_time"] == 0.0


def test_partial_seal_preserves_evidence_without_complete_debrief(tmp_path):
    recorder = LiftoffSessionRecorder.prepare(tmp_path, manifest=manifest())
    recorder.mark("recording_started")
    recorder.append_packet(
        valid_payload(),
        received_monotonic_ns=123,
        received_utc=datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc),
    )

    artifacts = recorder.seal_partial("liftoff_crash")

    assert (tmp_path / "partial-run.json").is_file()
    assert not (tmp_path / "debrief.json").exists()
    assert verify_checksum_file(tmp_path, profile=LIFTOFF_PROFILE) == ()
    assert any(artifact.kind == "partial_unverified" for artifact in artifacts)
    with pytest.raises(SessionLifecycleError, match="session_sealed"):
        recorder.append_packet(
            valid_payload(),
            received_monotonic_ns=124,
            received_utc=datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc),
        )


def test_prepare_rejects_nonempty_directory_and_configuration_mismatch(tmp_path):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "existing.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(SessionLifecycleError, match="run_directory_not_empty"):
        LiftoffSessionRecorder.prepare(occupied, manifest=manifest())

    bad_manifest = {**manifest(), "configuration_sha256": "0" * 64}
    with pytest.raises(SessionLifecycleError, match="configuration_hash_mismatch"):
        LiftoffSessionRecorder.prepare(tmp_path / "bad", manifest=bad_manifest)
    assert not (tmp_path / "bad").exists()
