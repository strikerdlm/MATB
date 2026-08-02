"""Component mission metric reduction tests."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from matb_integration.suas.recording import RecordKind, SessionRecord
from matb_integration.suas.metrics.mission import derive_block_metrics, mission_score


def _record(sequence: int, kind: RecordKind, payload: Mapping[str, object], *, time_ms: int = 0) -> SessionRecord:
    return SessionRecord(
        session_id="session-1",
        block_id="LOW",
        sequence=sequence,
        simulation_time_ms=time_ms,
        wall_time_utc="2026-08-01T12:00:00Z",
        state_version=sequence,
        kind=kind,
        payload=dict(payload),
    )


def metric_records() -> list[SessionRecord]:
    """Return one complete, ordered synthetic block recording.

    Payload codes are intentionally stable and domain-oriented.  The records
    cover lifecycle, coverage, contact workflow/reporting, command results,
    links, separation alerts, aircraft recovery, and required actions.
    """

    rows: list[tuple[RecordKind, Mapping[str, object], int]] = [
        (RecordKind.LIFECYCLE, {
            "event": "block_started",
            "active_aircraft": 4,
            "required_contacts": 5,
            "required_actions": 4,
        }, 0),
        (RecordKind.DOMAIN_EVENT, {
            "code": "coverage_updated",
            "covered_cells": 8,
            "eligible_cells": 10,
        }, 1_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "contact_reported",
            "contact_id": "C-01",
            "correct": True,
        }, 2_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "contact_reported",
            "contact_id": "C-02",
            "correct": True,
        }, 3_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "contact_reported",
            "contact_id": "C-03",
            "correct": True,
        }, 4_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "contact_reported",
            "contact_id": "C-04",
            "correct": False,
        }, 5_000),
        (RecordKind.COMMAND_RESULT, {"status": "accepted", "code": "accepted"}, 6_000),
        (RecordKind.COMMAND_RESULT, {"status": "accepted", "code": "accepted"}, 7_000),
        (RecordKind.COMMAND_RESULT, {"status": "accepted", "code": "accepted"}, 8_000),
        (RecordKind.COMMAND_RESULT, {"status": "accepted", "code": "accepted"}, 9_000),
        (RecordKind.COMMAND_RESULT, {"status": "accepted", "code": "accepted"}, 10_000),
        (RecordKind.COMMAND_RESULT, {"status": "rejected", "code": "invalid_mode"}, 11_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "link_lost",
            "aircraft_id": "UAS-01",
            "duration_ms": 10_000,
        }, 12_000),
        (RecordKind.ALERT, {
            "code": "separation_critical",
            "aircraft_ids": ["UAS-02", "UAS-03"],
        }, 13_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "aircraft_recovered",
            "aircraft_id": "UAS-01",
        }, 14_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "aircraft_recovered",
            "aircraft_id": "UAS-02",
        }, 15_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "aircraft_recovered",
            "aircraft_id": "UAS-03",
        }, 16_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "aircraft_failed",
            "aircraft_id": "UAS-04",
        }, 17_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "required_action",
            "action_id": "A-01",
            "on_time": True,
        }, 18_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "required_action",
            "action_id": "A-02",
            "on_time": True,
        }, 19_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "required_action",
            "action_id": "A-03",
            "on_time": True,
        }, 20_000),
        (RecordKind.DOMAIN_EVENT, {
            "code": "required_action",
            "action_id": "A-04",
            "on_time": False,
        }, 21_000),
        (RecordKind.LIFECYCLE, {
            "event": "block_finished",
        }, 22_000),
    ]
    return [_record(sequence, kind, payload, time_ms=time_ms) for sequence, (kind, payload, time_ms) in enumerate(rows, 1)]


def metric_manifest() -> dict[str, object]:
    # Targets are expressed as ppm so the test makes the normalization inputs
    # explicit.  Timeliness deliberately uses a positive target above 100% to
    # exercise a descriptive relative-to-target component (0.75 / 1.071429).
    return {
        "session_id": "session-1",
        "block_id": "LOW",
        "metric_thresholds": {
            "coverage_target_ppm": 1_000_000,
            "contact_effectiveness_target_ppm": 1_000_000,
            "asset_preservation_target_ppm": 833_333,
            "timeliness_target_ppm": 1_071_429,
        },
    }


def test_metrics_keep_every_component_and_compute_feedback_score() -> None:
    metrics = derive_block_metrics(metric_records(), metric_manifest())
    assert metrics.coverage.percent == 80.0
    assert metrics.contacts.correct_reports == 3
    assert metrics.contacts.false_reports == 1
    assert metrics.commands.accepted == 5
    assert metrics.commands.rejected == 1
    assert metrics.links.lost_duration_ms == 10_000
    assert metrics.separation.critical_violations == 1
    assert metrics.assets.recovered == 3
    assert metrics.timeliness.on_time_fraction == 0.75
    assert metrics.mission_score == 74.0


def test_metrics_reject_sequence_gap() -> None:
    records = metric_records()
    with pytest.raises(ValueError, match="sequence gap"):
        derive_block_metrics(records[:2] + records[3:], metric_manifest())


def test_composite_is_clamped_and_labeled_descriptive() -> None:
    assert mission_score(200.0, 200.0, 200.0, 200.0) == 100.0
    assert mission_score(-1.0, -1.0, -1.0, -1.0) == 0.0
