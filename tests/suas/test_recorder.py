"""Tests for durable, append-only sUAS session recording."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from matb_integration.suas.domain.serialization import canonical_sha256
from matb_integration.suas.recording.recorder import (
    RecordKind,
    RecordingError,
    SessionRecord,
    SessionRecorder,
)
from matb_integration.suas.recording.checkpoints import load_checkpoint
from matb_integration.suas.scenarios.loader import load_scenario


def manifest() -> dict[str, object]:
    loaded = load_scenario(Path("scenarios/suas/reference_area_search.yaml"))
    return {
        "manifest_version": 1,
        "scenario_id": loaded.definition.scenario_id,
        "scenario_sha256": loaded.sha256,
    }


def scenario_yaml() -> str:
    return load_scenario(Path("scenarios/suas/reference_area_search.yaml")).normalized_yaml


def record(*, sequence: int, kind: RecordKind = RecordKind.LIFECYCLE) -> SessionRecord:
    return SessionRecord(
        session_id="session-1",
        block_id="LOW",
        sequence=sequence,
        simulation_time_ms=0,
        wall_time_utc="2026-08-01T12:00:00Z",
        state_version=0,
        kind=kind,
        payload={"event": "started"},
    )


def snapshot(*, version: int, simulation_time_ms: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "engine_version": "0.1.0",
        "scenario_id": "reference-area-search",
        "scenario_sha256": "a" * 64,
        "block_id": "LOW",
        "clock": {"tick_ms": 100, "simulation_time_ms": simulation_time_ms, "paused": False},
        "tick": 0,
        "simulation_time_ms": simulation_time_ms,
        "state_version": version,
        "world": {},
        "sensor_prng": {},
        "sensor_reports": {},
        "link_applied_event_ids": [],
        "conflict_applied_event_ids": [],
        "conflict_pending_releases": {},
        "sensor_due_times": {},
        "coverage_cells": [],
        "separation": {},
        "command_results": {},
    }
    return {**payload, "authoritative_state_sha256": canonical_sha256(payload)}


def test_recorder_appends_canonical_lines_and_flushes(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    recorder.append(record(sequence=1, kind=RecordKind.LIFECYCLE))
    recorder.append(record(sequence=2, kind=RecordKind.DOMAIN_EVENT))
    lines = (tmp_path / "run/events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["sequence"] for line in lines] == [1, 2]
    assert all(" " not in line for line in lines)


def test_recorder_rejects_non_monotonic_sequence(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    recorder.append(record(sequence=2))
    with pytest.raises(RecordingError, match="strictly increasing"):
        recorder.append(record(sequence=2))


def test_checkpoint_round_trip_and_atomic_name(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    artifact = recorder.checkpoint(snapshot(version=50, simulation_time_ms=5_000))
    restored = load_checkpoint(artifact.path)
    assert artifact.path.name == "checkpoint-00000001.json.gz"
    assert restored["checkpoint_version"] == 1
    assert restored["record_sequence"] == 0
    assert restored["engine"]["state_version"] == 50
    assert not list((tmp_path / "run/checkpoints").glob("*.tmp"))


def test_write_failure_is_not_hidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = SessionRecorder(tmp_path / "run", manifest(), scenario_yaml())
    monkeypatch.setattr(recorder, "_write_line", Mock(side_effect=OSError("disk full")))
    with pytest.raises(RecordingError, match="disk full"):
        recorder.append(record(sequence=1))


@pytest.mark.parametrize("mutation", [lambda data: data.rstrip(b"\n"), lambda data: data.replace(b"\n", b"\r\n")])
def test_open_existing_rejects_incomplete_or_noncanonical_jsonl_line(
    tmp_path: Path, mutation,
) -> None:
    run_dir = tmp_path / "run"
    recorder = SessionRecorder(run_dir, manifest(), scenario_yaml())
    recorder.append(record(sequence=1))
    recorder.close()
    events_path = run_dir / "events.jsonl"
    events_path.write_bytes(mutation(events_path.read_bytes()))

    with pytest.raises(RecordingError):
        SessionRecorder.open_existing(run_dir)


def test_constructor_validates_and_persists_normalized_manifest_scenario_pair(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    normalized = scenario_yaml()
    source_yaml = Path("scenarios/suas/reference_area_search.yaml").read_text(encoding="utf-8")
    recorder = SessionRecorder(run_dir, manifest(), source_yaml)
    recorder.close()

    assert (run_dir / "scenario.yaml").read_text(encoding="utf-8") == normalized
    assert SessionRecorder.open_existing(run_dir)

    with pytest.raises(RecordingError, match="manifest does not match"):
        SessionRecorder(tmp_path / "mismatch", {**manifest(), "scenario_sha256": "0" * 64}, normalized)
    assert not (tmp_path / "mismatch").exists()


def test_open_existing_rejects_orphan_checkpoint_temporary_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    recorder = SessionRecorder(run_dir, manifest(), scenario_yaml())
    recorder.close()
    (run_dir / "checkpoints/checkpoint-00000001.json.gz.tmp").write_bytes(b"partial")

    with pytest.raises(RecordingError, match="partial checkpoint"):
        SessionRecorder.open_existing(run_dir)
