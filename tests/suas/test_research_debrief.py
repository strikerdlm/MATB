"""Research reduction and public-debrief privacy gates."""

from __future__ import annotations

from pathlib import Path

from matb_integration.suas.metrics.debrief import build_public_debrief
from matb_integration.suas.metrics.research import derive_research_metrics
from matb_integration.suas.recording.records import RecordKind, SessionRecord
from matb_integration.suas.recording.replay import ReplayResult, ReplayStatus
from matb_integration.suas.scenarios.loader import load_scenario


def _record(sequence: int, kind: RecordKind, payload: dict[str, object], block: str = "PRACTICE") -> SessionRecord:
    return SessionRecord(
        "sim-1", block, sequence, 0, "2026-08-01T12:00:00Z", 0, kind, payload,
    )


def test_research_metrics_are_explicit_about_missingness() -> None:
    metrics = derive_research_metrics([
        _record(1, RecordKind.QUESTIONNAIRE, {"instrument": "ISA", "rating": 6}),
        _record(2, RecordKind.QUESTIONNAIRE, {"instrument": "SAGAT", "sa_level": 1, "correct": True, "timed_out": False, "unscorable_reason": None}),
        _record(3, RecordKind.QUESTIONNAIRE, {"instrument": "NASA_TLX", "raw_tlx": 30}),
    ]).to_dict()
    assert metrics["isa"]["mean"] == 6.0
    assert metrics["sagat"]["accuracy"] == 1.0
    assert metrics["nasa_tlx"]["raw_tlx"] == 30.0
    assert metrics["bedford"]["status"] == "missing"
    assert "correct_answer" not in str(metrics)


def test_public_debrief_excludes_answers_and_truth(loaded_scenario, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "scenario.yaml").write_text(loaded_scenario.normalized_yaml, encoding="utf-8")
    records = (
        _record(1, RecordKind.LIFECYCLE, {"event": "block_started", "active_aircraft": 1, "required_contacts": 0}),
        _record(2, RecordKind.QUESTIONNAIRE, {
            "instrument": "SAGAT", "probe_id": "sagat:1", "sa_level": 1,
            "answer": "secret answer", "correct_answer": "private truth", "correct": False,
            "timed_out": False, "unscorable_reason": None,
        }),
        _record(3, RecordKind.LIFECYCLE, {"event": "block_finished"}),
    )
    manifest = {
        "session_id": "sim-1",
        "scenario_id": loaded_scenario.definition.scenario_id,
        "scenario_sha256": loaded_scenario.sha256,
        "engine_version": "1.0.0",
        "metric_thresholds": {
            "coverage_target_ppm": 800_000,
            "contact_effectiveness_target_ppm": 800_000,
            "asset_preservation_target_ppm": 900_000,
            "timeliness_target_ppm": 800_000,
        },
    }
    replay = ReplayResult(ReplayStatus.MATCH, "a" * 64, "a" * 64, "b" * 64, "b" * 64, 3, 0, ())
    public, private = build_public_debrief(
        run_dir, manifest, replay, records,
        live_frames=({"block_id": "PRACTICE", "simulation_time_ms": 0, "state_version": 0, "truth": "hidden"},),
    )
    rendered = str(public)
    assert "secret answer" not in rendered
    assert "private truth" not in rendered
    assert '"truth"' not in rendered
    assert private["visibility"] == "server_private"
    assert "private truth" in str(private)
