from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

from matb_integration.liftoff.metrics import (
    METRICS_VERSION,
    VisibleResults,
    compute_metrics,
)
from matb_integration.liftoff.protocol import decode_packet
from matb_integration.liftoff.records import TelemetryRecord
from tests.liftoff.test_protocol import valid_payload


def deterministic_records(*, sample_rate: int, seconds: int, constant_input: float | None = None):
    base_packet = decode_packet(valid_payload())
    started = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    records = []
    for index in range(sample_rate * seconds):
        simulator_time = index / sample_rate
        input_value = constant_input if constant_input is not None else math.sin(simulator_time * 2.0)
        packet = replace(
            base_packet,
            simulator_time=simulator_time,
            position_native=(simulator_time, simulator_time * 0.5, 0.0),
            velocity_native=(1.0, 0.5, 0.0),
            angular_rate_native=(0.1, 0.2, 0.3),
            processed_input=(input_value, -input_value, input_value / 2.0, 0.0),
        )
        records.append(
            TelemetryRecord(
                session_id="12345678-1234-5678-1234-567812345678",
                sequence=index + 1,
                received_monotonic_ns=index * round(1_000_000_000 / sample_rate),
                received_utc=(started + timedelta(seconds=simulator_time)).isoformat().replace("+00:00", "Z"),
                packet=packet,
            )
        )
    return records


def test_metrics_keep_component_outcomes_separate():
    records = deterministic_records(sample_rate=60, seconds=10)
    visible = VisibleResults(
        valid_lap_times_s=(61.2, 63.0, 60.8),
        invalid_laps=1,
        observer_restart_count=2,
    )

    result = compute_metrics(records, visible)

    assert METRICS_VERSION == "liftoff-metrics-v1"
    assert result["metrics_version"] == "liftoff-metrics-v1"
    assert result["primary"]["valid_laps"] == 3
    assert result["primary"]["median_lap_time_s"] == 61.2
    assert result["primary"]["best_lap_time_s"] == 60.8
    assert result["primary"]["lap_completion_proportion"] == 0.75
    assert "composite_score" not in result
    assert 0.0 <= result["telemetry"]["input_saturation_fraction"] <= 1.0


def test_zero_completed_laps_and_constant_inputs_are_explicit():
    result = compute_metrics(
        deterministic_records(sample_rate=60, seconds=1, constant_input=0.25),
        VisibleResults(valid_lap_times_s=(), invalid_laps=0, observer_restart_count=0),
    )

    assert result["primary"]["median_lap_time_s"] is None
    assert result["primary"]["lap_completion_proportion"] is None
    assert result["telemetry"]["input_entropy"] == 0.0
    assert result["telemetry"]["control_reversal_rate_per_min"] == 0.0
    assert result["telemetry"]["smoothness"]["status"] == "ok"


def test_irregular_time_and_missing_reference_are_not_computable():
    records = deterministic_records(sample_rate=10, seconds=1)

    result = compute_metrics(
        records,
        VisibleResults(valid_lap_times_s=(10.0,), invalid_laps=0, observer_restart_count=0),
        coordinate_units_validated=True,
    )

    assert result["telemetry"]["smoothness"] == {
        "status": "not_computable",
        "reason_code": "sampling_rate_below_20_hz",
    }
    assert result["telemetry"]["path_deviation"] == {
        "status": "not_computable",
        "reason_code": "reference_path_missing",
    }


def test_unvalidated_coordinates_block_path_metrics():
    result = compute_metrics(
        deterministic_records(sample_rate=60, seconds=1),
        VisibleResults(valid_lap_times_s=(10.0,), invalid_laps=0, observer_restart_count=0),
        reference_positions=[(0.0, 0.0, 0.0), (1.0, 0.5, 0.0)],
    )

    assert result["telemetry"]["path_length"]["reason_code"] == "coordinate_units_unvalidated"
    assert result["telemetry"]["path_deviation"]["reason_code"] == "coordinate_units_unvalidated"


def test_restart_discrepancy_remains_a_component_deviation():
    records = deterministic_records(sample_rate=20, seconds=1)[:5]
    reset_times = [0.0, 0.1, 0.2, 0.05, 0.15]
    records = [
        replace(record, packet=replace(record.packet, simulator_time=reset_time))
        for record, reset_time in zip(records, reset_times)
    ]

    result = compute_metrics(
        records,
        VisibleResults(valid_lap_times_s=(10.0,), invalid_laps=0, observer_restart_count=0),
    )

    assert result["primary"]["telemetry_restart_candidates"] == 1
    assert result["primary"]["restart_discrepancy"] == -1


def test_metric_output_is_deterministic():
    records = deterministic_records(sample_rate=60, seconds=2)
    visible = VisibleResults(valid_lap_times_s=(61.2, 63.0, 60.8), invalid_laps=1, observer_restart_count=0)

    outputs = [compute_metrics(records, visible), compute_metrics(records, visible)]
    hashes = [
        hashlib.sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        for output in outputs
    ]

    assert hashes[0] == hashes[1]
