"""Deterministic short-term HRV analysis for Polar H10 RR intervals.

Raw intervals are never modified in storage.  This module produces a
length-preserving corrected analysis series and descriptive research metrics;
it does not make clinical or diagnostic interpretations.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import integrate, signal
from scipy.interpolate import interp1d


HRV_ANALYSIS_VERSION = "matb-hrv-analysis-v1"
FREQUENCY_BANDS_HZ = {
    "vlf": (0.0033, 0.04),
    "lf": (0.04, 0.15),
    "hf": (0.15, 0.40),
}


def _adaptive_threshold(values: np.ndarray, alpha: float, window: int) -> np.ndarray:
    series = pd.Series(np.abs(np.asarray(values, dtype=float)))
    q1 = series.rolling(window=window, center=True, min_periods=1).quantile(0.25)
    q3 = series.rolling(window=window, center=True, min_periods=1).quantile(0.75)
    return alpha * ((q3.to_numpy() - q1.to_numpy()) / 2.0)


def _lipponen_tarvainen_valid_mask(
    rr_ms: np.ndarray,
    *,
    alpha: float = 5.2,
    c1: float = 0.13,
    c2: float = 0.17,
    window_width: int = 91,
    median_filter_order: int = 11,
) -> np.ndarray:
    """Return a valid-beat mask using Lipponen & Tarvainen (2019)."""

    rr = np.asarray(rr_ms, dtype=float)
    count = rr.size
    if count < 3:
        return (rr >= 300.0) & (rr <= 2000.0) & np.isfinite(rr)

    differences = np.ediff1d(rr, to_begin=0.0)
    differences[0] = float(np.mean(differences[1:]))
    threshold1 = _adaptive_threshold(differences, alpha, window_width)
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized_differences = np.where(
            threshold1 != 0,
            differences / threshold1,
            np.nan,
        )

    padded = np.pad(normalized_differences, 2, "reflect")
    subspace1 = np.zeros(count)
    subspace2 = np.zeros(count)
    for padded_index in range(2, count + 2):
        index = padded_index - 2
        current = padded[padded_index]
        if current > 0:
            subspace1[index] = max(padded[padded_index - 1], padded[padded_index + 1])
        elif current < 0:
            subspace1[index] = min(padded[padded_index - 1], padded[padded_index + 1])
        if current >= 0:
            subspace2[index] = min(padded[padded_index + 1], padded[padded_index + 2])
        else:
            subspace2[index] = max(padded[padded_index + 1], padded[padded_index + 2])

    median_rr = (
        pd.Series(rr)
        .rolling(window=median_filter_order, center=True, min_periods=1)
        .median()
        .to_numpy()
    )
    median_difference = rr - median_rr
    median_difference[median_difference < 0] *= 2.0
    threshold2 = _adaptive_threshold(median_difference, alpha, window_width)
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized_median = np.where(
            threshold2 != 0,
            median_difference / threshold2,
            np.nan,
        )

    invalid_indices: set[int] = set()
    index = 0
    while index < count - 2:
        current = normalized_differences[index]
        if np.abs(current) <= 1:
            index += 1
            continue
        ectopic = (current > 1 and subspace1[index] < (-c1 * current - c2)) or (
            current < -1 and subspace1[index] > (-c1 * current + c2)
        )
        if ectopic:
            invalid_indices.add(index)
            index += 1
            continue
        if not (np.abs(current) > 1 or np.abs(normalized_median[index]) > 3):
            index += 1
            continue
        candidates = [index]
        if np.abs(normalized_differences[index + 1]) < np.abs(
            normalized_differences[index + 2]
        ):
            candidates.append(index + 1)
        matched = False
        for candidate in candidates:
            long_pattern = (
                normalized_differences[candidate] > 1 and subspace2[candidate] < -1
            )
            median_pattern = np.abs(normalized_median[candidate]) > 3
            short_pattern = (
                normalized_differences[candidate] < -1 and subspace2[candidate] > 1
            )
            if not (long_pattern or median_pattern or short_pattern):
                continue
            half_matches = (
                np.abs(rr[candidate] / 2.0 - median_rr[candidate])
                < threshold2[candidate]
            )
            pair_matches = (
                np.abs(rr[candidate] + rr[candidate + 1] - median_rr[candidate])
                < threshold2[candidate]
            )
            if (short_pattern and pair_matches) or (long_pattern and half_matches):
                invalid_indices.add(candidate)
            else:
                invalid_indices.add(candidate)
            matched = True
            break
        index += 1 if matched else 1

    valid = np.ones(count, dtype=bool)
    for invalid_index in invalid_indices:
        if 0 <= invalid_index < count:
            valid[invalid_index] = False
    return valid & (rr >= 300.0) & (rr <= 2000.0) & np.isfinite(rr)


def _interpolate_invalid(rr_ms: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    values = np.asarray(rr_ms, dtype=float).copy()
    if values.size == 0:
        return values
    valid_indices = np.flatnonzero(valid_mask)
    if valid_indices.size == 0 or valid_indices.size == values.size:
        return values
    invalid_indices = np.flatnonzero(~valid_mask)
    values[invalid_indices] = np.interp(
        invalid_indices.astype(float),
        valid_indices.astype(float),
        values[valid_indices],
    )
    return values


def _longest_invalid_run(valid_mask: np.ndarray) -> int:
    invalid = (~valid_mask).astype(np.int8)
    if not invalid.any():
        return 0
    edges = np.diff(np.concatenate(([0], invalid, [0])))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return int((ends - starts).max()) if starts.size else 0


def _quality_summary(rr_ms: np.ndarray, valid_mask: np.ndarray) -> dict[str, Any]:
    count = int(rr_ms.size)
    if count < 2:
        return {
            "score": 0.0,
            "label": "insufficient_data",
            "corrected_count": 0,
            "corrected_pct": 0.0,
            "max_artifact_run": 0,
            "out_of_bounds_pct": 0.0,
            "method": "lipponen_tarvainen_2019",
        }
    corrected_count = int(np.sum(~valid_mask))
    corrected_pct = corrected_count * 100.0 / count
    max_run = _longest_invalid_run(valid_mask)
    out_of_bounds = int(
        np.sum((rr_ms < 300.0) | (rr_ms > 2000.0) | ~np.isfinite(rr_ms))
    )
    out_of_bounds_pct = out_of_bounds * 100.0 / count
    levels = ["excellent", "good", "acceptable", "poor", "unusable"]
    if corrected_pct < 1.0:
        level_index = 0
    elif corrected_pct < 3.0:
        level_index = 1
    elif corrected_pct < 5.0:
        level_index = 2
    elif corrected_pct < 10.0:
        level_index = 3
    else:
        level_index = 4
    if max_run >= 5 or out_of_bounds_pct >= 2.0:
        level_index = min(level_index + 1, len(levels) - 1)
    burst_penalty = min(1.0, max_run / max(5.0, 0.1 * count))
    score = 1.0 - corrected_pct / 100.0 - 0.5 * burst_penalty - out_of_bounds_pct / 100.0
    return {
        "score": float(min(1.0, max(0.0, score))),
        "label": levels[level_index],
        "corrected_count": corrected_count,
        "corrected_pct": float(corrected_pct),
        "max_artifact_run": max_run,
        "out_of_bounds_pct": float(out_of_bounds_pct),
        "method": "lipponen_tarvainen_2019",
    }


def clean_rr_intervals(
    rr_ms: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Detect artifacts and return a length-preserving interpolated series."""

    raw = np.asarray(rr_ms, dtype=float)
    if raw.size == 0:
        return raw.copy(), np.asarray([], dtype=bool), _quality_summary(
            raw, np.asarray([], dtype=bool)
        )
    valid = _lipponen_tarvainen_valid_mask(raw)
    return _interpolate_invalid(raw, valid), valid, _quality_summary(raw, valid)


def compute_time_domain(rr_ms: np.ndarray) -> dict[str, float | int]:
    """Compute prespecified short-term time-domain metrics."""

    rr = np.asarray(rr_ms, dtype=float)
    if rr.size < 2:
        raise ValueError("at_least_two_rr_intervals_required")
    differences = np.diff(rr)
    mean_nn = float(np.mean(rr))
    sdnn = float(np.std(rr, ddof=1))
    rmssd = float(np.sqrt(np.mean(np.square(differences))))
    sdsd = float(np.std(differences, ddof=1)) if differences.size > 1 else 0.0
    nn50 = int(np.sum(np.abs(differences) > 50.0))
    heart_rate = 60_000.0 / rr
    return {
        "mean_nn_ms": mean_nn,
        "sdnn_ms": sdnn,
        "rmssd_ms": rmssd,
        "ln_rmssd": float(math.log(rmssd)) if rmssd > 0 else 0.0,
        "sdsd_ms": sdsd,
        "cvnn": sdnn / mean_nn if mean_nn > 0 else 0.0,
        "nn50": nn50,
        "pnn50_pct": nn50 * 100.0 / differences.size,
        "mean_hr_bpm": float(np.mean(heart_rate)),
        "min_hr_bpm": float(np.min(heart_rate)),
        "max_hr_bpm": float(np.max(heart_rate)),
    }


def _frequency_domain(
    rr_ms: np.ndarray,
    *,
    sampling_rate_hz: float = 4.0,
) -> tuple[dict[str, float | None], list[dict[str, float]]]:
    rr_seconds = rr_ms / 1000.0
    peak_times = np.concatenate(([0.0], np.cumsum(rr_seconds)))
    interval_times = (peak_times[:-1] + peak_times[1:]) / 2.0
    regular_times = np.arange(0.0, peak_times[-1], 1.0 / sampling_rate_hz)
    interpolation = interp1d(
        interval_times,
        rr_ms,
        kind="cubic" if rr_ms.size >= 4 else "linear",
        bounds_error=False,
        fill_value="extrapolate",
    )
    detrended = signal.detrend(interpolation(regular_times))
    frequencies, power = signal.welch(
        detrended,
        fs=sampling_rate_hz,
        window="hann",
        nperseg=min(256, max(16, len(detrended) // 4)),
    )

    def band(name: str) -> tuple[float, float | None]:
        lower, upper = FREQUENCY_BANDS_HZ[name]
        mask = (frequencies >= lower) & (frequencies < upper)
        if np.count_nonzero(mask) < 2:
            return 0.0, None
        band_frequencies = frequencies[mask]
        band_power = power[mask]
        integral = float(integrate.trapezoid(band_power, band_frequencies))
        peak = float(band_frequencies[int(np.argmax(band_power))]) if integral > 0 else None
        return integral, peak

    vlf, vlf_peak = band("vlf")
    lf, lf_peak = band("lf")
    hf, hf_peak = band("hf")
    total = vlf + lf + hf
    normalized_denominator = lf + hf
    metrics: dict[str, float | None] = {
        "vlf_power_ms2": vlf,
        "lf_power_ms2": lf,
        "hf_power_ms2": hf,
        "total_power_ms2": total,
        "lf_nu": 100.0 * lf / normalized_denominator if normalized_denominator > 0 else None,
        "hf_nu": 100.0 * hf / normalized_denominator if normalized_denominator > 0 else None,
        "lf_hf_ratio": lf / hf if hf > 0 else None,
        "vlf_peak_hz": vlf_peak,
        "lf_peak_hz": lf_peak,
        "hf_peak_hz": hf_peak,
        "resampling_rate_hz": sampling_rate_hz,
    }
    psd = [
        {"frequency_hz": float(frequency), "power_ms2_per_hz": float(value)}
        for frequency, value in zip(frequencies, power, strict=True)
        if frequency <= FREQUENCY_BANDS_HZ["hf"][1]
    ]
    return metrics, psd


def analyze_rr_phase(
    rr_ms: np.ndarray,
    *,
    nominal_duration_s: float,
    coverage_fraction: float,
    disconnect_count: int = 0,
    queue_overflow_count: int = 0,
    contact_loss_detected: bool = False,
) -> dict[str, Any]:
    """Clean and analyze one already-delimited baseline/task/recovery phase."""

    raw = np.asarray(rr_ms, dtype=float)
    cleaned, valid_mask, quality = clean_rr_intervals(raw)
    quality = dict(quality)
    quality["signal_quality_label"] = quality["label"]
    quality["coverage_fraction"] = float(coverage_fraction)
    quality["reason_codes"] = []
    if coverage_fraction < 0.95:
        quality["label"] = "insufficient_data"
        quality["score"] = min(float(quality["score"]), max(0.0, coverage_fraction))
        quality["reason_codes"].append("beat_coverage_below_95pct")

    if disconnect_count:
        time_domain: dict[str, Any] = {
            "status": "not_computable",
            "reason_code": "discontinuous_rr_segments",
            "metrics": None,
        }
    elif cleaned.size >= 2 and quality["signal_quality_label"] != "unusable":
        time_domain: dict[str, Any] = {
            "status": "ok",
            "metrics": compute_time_domain(cleaned),
        }
    else:
        reason = (
            "rr_quality_unusable"
            if quality["signal_quality_label"] == "unusable"
            else "insufficient_rr"
        )
        time_domain = {"status": "not_computable", "reason_code": reason, "metrics": None}

    frequency_reasons: list[str] = []
    if nominal_duration_s < 300.0:
        frequency_reasons.append("phase_duration_below_300s")
    if coverage_fraction < 0.95:
        frequency_reasons.append("beat_coverage_below_95pct")
    if quality["signal_quality_label"] not in {"excellent", "good", "acceptable"}:
        frequency_reasons.append("rr_quality_below_acceptable")
    if disconnect_count:
        frequency_reasons.append("bluetooth_disconnect")
    if queue_overflow_count:
        frequency_reasons.append("acquisition_queue_overflow")
    if contact_loss_detected:
        frequency_reasons.append("sensor_contact_loss")

    if frequency_reasons:
        frequency_domain: dict[str, Any] = {
            "status": "not_computable",
            "reason_codes": frequency_reasons,
            "metrics": None,
            "psd": [],
        }
    else:
        metrics, psd = _frequency_domain(cleaned)
        frequency_domain = {"status": "ok", "metrics": metrics, "psd": psd}

    return {
        "schema_version": HRV_ANALYSIS_VERSION,
        "raw_rr_count": int(raw.size),
        "analyzed_rr_count": int(cleaned.size),
        "nominal_duration_s": float(nominal_duration_s),
        "coverage_fraction": float(coverage_fraction),
        "quality": quality,
        "valid_mask": valid_mask.tolist(),
        "corrected_rr_ms": cleaned.tolist(),
        "time_domain": time_domain,
        "frequency_domain": frequency_domain,
    }


__all__ = [
    "FREQUENCY_BANDS_HZ",
    "HRV_ANALYSIS_VERSION",
    "analyze_rr_phase",
    "clean_rr_intervals",
    "compute_time_domain",
]
