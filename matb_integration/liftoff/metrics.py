"""Versioned component metrics for Liftoff research sessions."""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Sequence

import numpy as np
from scipy.spatial import cKDTree

from .records import TelemetryRecord

METRICS_VERSION = "liftoff-metrics-v1"


@dataclass(frozen=True, slots=True)
class VisibleResults:
    valid_lap_times_s: tuple[float, ...]
    invalid_laps: int
    observer_restart_count: int

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in self.valid_lap_times_s
        ):
            raise ValueError("valid_lap_times_s must contain positive finite values")
        for value, name in (
            (self.invalid_laps, "invalid_laps"),
            (self.observer_restart_count, "observer_restart_count"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


def _normalized_entropy(values: np.ndarray, bins: int = 16) -> float:
    counts, _ = np.histogram(values, bins=bins, range=(-1.0, 1.0))
    probabilities = counts[counts > 0] / max(1, counts.sum())
    entropy = float(-(probabilities * np.log2(probabilities)).sum() / np.log2(bins))
    return max(0.0, entropy)


def _reversal_rate(values: np.ndarray, duration_min: float, deadband: float = 0.02) -> float:
    changes = np.diff(values)
    signs = np.sign(np.where(np.abs(changes) >= deadband, changes, 0.0))
    nonzero = signs[signs != 0]
    reversals = np.count_nonzero((nonzero[1:] * nonzero[:-1]) < 0)
    return float(reversals / max(duration_min, 1e-9))


def _not_computable(reason_code: str) -> dict[str, str]:
    return {"status": "not_computable", "reason_code": reason_code}


def _smoothness(times: np.ndarray, positions: np.ndarray) -> dict[str, object]:
    if len(times) < 9:
        return _not_computable("insufficient_samples")
    deltas = np.diff(times)
    if np.any(deltas <= 0):
        return _not_computable("simulator_time_nonmonotonic")
    median_interval = float(np.median(deltas))
    if median_interval <= 0:
        return _not_computable("simulator_time_nonmonotonic")
    sampling_rate_hz = 1.0 / median_interval
    if sampling_rate_hz < 20.0:
        return _not_computable("sampling_rate_below_20_hz")

    kernel = np.ones(5, dtype=float) / 5.0
    smoothed = np.column_stack([
        np.convolve(positions[:, axis], kernel, mode="valid")
        for axis in range(positions.shape[1])
    ])
    smoothed_times = times[2:-2]
    velocity = np.diff(smoothed, axis=0) / np.diff(smoothed_times)[:, None]
    velocity_times = (smoothed_times[1:] + smoothed_times[:-1]) / 2.0
    acceleration = np.diff(velocity, axis=0) / np.diff(velocity_times)[:, None]
    acceleration_times = (velocity_times[1:] + velocity_times[:-1]) / 2.0
    jerk = np.diff(acceleration, axis=0) / np.diff(acceleration_times)[:, None]
    jerk_magnitude = np.linalg.norm(jerk, axis=1)
    return {
        "status": "ok",
        "jerk_rms_native_s3": float(np.sqrt(np.mean(np.square(jerk_magnitude)))),
        "median_sampling_rate_hz": sampling_rate_hz,
        "filter": "centered_moving_average_5",
    }


def _path_metrics(
    positions: np.ndarray,
    reference_positions: Sequence[tuple[float, float, float]] | None,
    *,
    coordinate_units_validated: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    if not coordinate_units_validated:
        unavailable = _not_computable("coordinate_units_unvalidated")
        return unavailable, dict(unavailable)
    segment_lengths = np.linalg.norm(np.diff(positions, axis=0), axis=1)
    path_length = {
        "status": "ok",
        "path_length_native": float(segment_lengths.sum()),
    }
    if reference_positions is None:
        return path_length, _not_computable("reference_path_missing")
    reference = np.asarray(reference_positions, dtype=float)
    if reference.ndim != 2 or reference.shape[1] != 3 or len(reference) == 0:
        raise ValueError("reference_positions must be a nonempty sequence of 3D points")
    if not np.all(np.isfinite(reference)):
        raise ValueError("reference_positions must be finite")
    distances, _ = cKDTree(reference).query(positions, k=1)
    return path_length, {
        "status": "ok",
        "mean_nearest_distance_native": float(np.mean(distances)),
        "p95_nearest_distance_native": float(np.percentile(distances, 95)),
        "maximum_nearest_distance_native": float(np.max(distances)),
    }


def _primary_results(visible: VisibleResults, times: np.ndarray) -> dict[str, object]:
    valid_laps = len(visible.valid_lap_times_s)
    attempted_laps = valid_laps + visible.invalid_laps
    telemetry_restarts = int(np.count_nonzero(np.diff(times) < 0)) if len(times) > 1 else 0
    return {
        "valid_laps": valid_laps,
        "invalid_laps": visible.invalid_laps,
        "median_lap_time_s": (
            float(statistics.median(visible.valid_lap_times_s))
            if visible.valid_lap_times_s
            else None
        ),
        "best_lap_time_s": min(visible.valid_lap_times_s, default=None),
        "lap_completion_proportion": (
            valid_laps / attempted_laps if attempted_laps else None
        ),
        "lap_time_cv": (
            float(statistics.pstdev(visible.valid_lap_times_s) / statistics.mean(visible.valid_lap_times_s))
            if len(visible.valid_lap_times_s) >= 2
            else None
        ),
        "observer_restart_count": visible.observer_restart_count,
        "telemetry_restart_candidates": telemetry_restarts,
        "restart_discrepancy": visible.observer_restart_count - telemetry_restarts,
    }


def compute_metrics(
    records: Sequence[TelemetryRecord],
    visible_results: VisibleResults,
    reference_positions: Sequence[tuple[float, float, float]] | None = None,
    *,
    coordinate_units_validated: bool = False,
) -> dict[str, object]:
    if not isinstance(visible_results, VisibleResults):
        raise ValueError("visible_results must be a VisibleResults")
    if any(not isinstance(record, TelemetryRecord) for record in records):
        raise ValueError("records must contain TelemetryRecord values")

    times = np.asarray([record.packet.simulator_time for record in records], dtype=float)
    primary = _primary_results(visible_results, times)
    if not records:
        return {
            "metrics_version": METRICS_VERSION,
            "primary": primary,
            "telemetry": {
                "status": "not_computable",
                "reason_code": "no_telemetry",
                "path_length": _not_computable("no_telemetry"),
                "path_deviation": _not_computable("no_telemetry"),
                "smoothness": _not_computable("no_telemetry"),
            },
        }

    positions = np.asarray([record.packet.position_native for record in records], dtype=float)
    velocities = np.asarray([record.packet.velocity_native for record in records], dtype=float)
    angular_rates = np.asarray([record.packet.angular_rate_native for record in records], dtype=float)
    inputs = np.asarray([record.packet.processed_input for record in records], dtype=float)
    positive_deltas = np.diff(times)
    active_duration_s = float(positive_deltas[positive_deltas > 0].sum())
    speed = np.linalg.norm(velocities, axis=1)
    angular_magnitude = np.linalg.norm(angular_rates, axis=1)
    input_rms_by_channel = np.sqrt(np.mean(np.square(inputs), axis=0))
    duration_min = active_duration_s / 60.0
    reversal_rates = [
        _reversal_rate(inputs[:, channel], duration_min)
        for channel in range(inputs.shape[1])
    ]
    input_entropy_by_channel = [
        _normalized_entropy(inputs[:, channel])
        for channel in range(inputs.shape[1])
    ]
    path_length, path_deviation = _path_metrics(
        positions,
        reference_positions,
        coordinate_units_validated=coordinate_units_validated,
    )
    telemetry = {
        "status": "ok",
        "active_duration_s": active_duration_s,
        "mean_speed_native": float(np.mean(speed)),
        "p95_speed_native": float(np.percentile(speed, 95)),
        "angular_rate_rms_native": float(np.sqrt(np.mean(np.square(angular_magnitude)))),
        "angular_rate_p95_native": float(np.percentile(angular_magnitude, 95)),
        "input_rms": float(np.sqrt(np.mean(np.square(inputs)))),
        "input_rms_by_channel": [float(value) for value in input_rms_by_channel],
        "input_saturation_fraction": float(np.mean(np.abs(inputs) >= 0.95)),
        "input_entropy": float(np.mean(input_entropy_by_channel)),
        "input_entropy_by_channel": input_entropy_by_channel,
        "control_reversal_rate_per_min": float(np.mean(reversal_rates)),
        "control_reversal_rate_by_channel_per_min": reversal_rates,
        "smoothness": _smoothness(times, positions),
        "path_length": path_length,
        "path_deviation": path_deviation,
    }
    return {
        "metrics_version": METRICS_VERSION,
        "primary": primary,
        "telemetry": telemetry,
    }


__all__ = ["METRICS_VERSION", "VisibleResults", "compute_metrics"]
