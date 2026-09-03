"""Conservative HRV descriptors ported from the pinned HRV research revision.

Source: strikerdlm/HRV@ef086092cfc57c74171f9ac9374b8ba24ceb0e6a
License: MIT (see LICENSES/HRV-MIT.txt)

Raw intervals are never edited. Lipponen--Tarvainen detection supplies a valid
mask for a derived series. This Release A implementation rejects flagged beats
and breaks successive-pair continuity; it intentionally does not claim the
upstream structural edit policy identifier.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy import signal
from scipy.interpolate import interp1d


HRV_ALGORITHM_VERSIONS = {
    "artifact_detection": "lipponen-tarvainen-rejection-v1",
    "live_time_domain": "polar-live-time-domain-v2",
    "offline_metrics": "astra-hrv-metrics-1.0.0",
    "source_revision": "ef086092cfc57c74171f9ac9374b8ba24ceb0e6a",
}
_TRAPZ = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


def _threshold(values: np.ndarray, alpha: float = 5.2, window: int = 91) -> np.ndarray:
    series = pd.Series(np.abs(np.asarray(values, dtype=float)))
    q1 = series.rolling(window=window, center=True, min_periods=1).quantile(0.25).to_numpy()
    q3 = series.rolling(window=window, center=True, min_periods=1).quantile(0.75).to_numpy()
    return alpha * ((q3 - q1) / 2.0)


def lipponen_tarvainen_valid_mask(rr_ms: Sequence[float]) -> np.ndarray:
    """Return True for beats not flagged by Lipponen--Tarvainen (2019)."""

    rr = np.asarray(rr_ms, dtype=float)
    if rr.ndim != 1:
        raise ValueError("rr_ms must be one-dimensional")
    if rr.size < 3:
        return np.isfinite(rr) & (rr >= 300.0) & (rr <= 2000.0)
    drr = np.ediff1d(rr, to_begin=0.0)
    drr[0] = float(np.mean(drr[1:]))
    th1 = _threshold(drr)
    with np.errstate(divide="ignore", invalid="ignore"):
        drr = np.where(th1 != 0, drr / th1, np.nan)
    padded = np.pad(drr, 2, "reflect")
    s12 = np.zeros(rr.size)
    s22 = np.zeros(rr.size)
    for pos in range(2, rr.size + 2):
        value = padded[pos]
        if value > 0:
            s12[pos - 2] = max(padded[pos - 1], padded[pos + 1])
        elif value < 0:
            s12[pos - 2] = min(padded[pos - 1], padded[pos + 1])
        if value >= 0:
            s22[pos - 2] = min(padded[pos + 1], padded[pos + 2])
        else:
            s22[pos - 2] = max(padded[pos + 1], padded[pos + 2])
    medrr = pd.Series(rr).rolling(window=11, center=True, min_periods=1).median().to_numpy()
    mrr = rr - medrr
    mrr[mrr < 0] *= 2.0
    th2 = _threshold(mrr)
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized_mrr = np.where(th2 != 0, mrr / th2, np.nan)
    invalid: set[int] = set()
    index = 0
    while index < rr.size - 2:
        if abs(drr[index]) <= 1:
            index += 1
            continue
        eq1 = drr[index] > 1 and s12[index] < (-0.13 * drr[index] - 0.17)
        eq2 = drr[index] < -1 and s12[index] > (-0.13 * drr[index] + 0.17)
        if eq1 or eq2:
            invalid.add(index)
            index += 1
            continue
        if not (abs(drr[index]) > 1 or abs(normalized_mrr[index]) > 3):
            index += 1
            continue
        candidates = [index]
        if abs(drr[index + 1]) < abs(drr[index + 2]):
            candidates.append(index + 1)
        for candidate in candidates:
            eq3 = drr[candidate] > 1 and s22[candidate] < -1
            eq4 = abs(normalized_mrr[candidate]) > 3
            eq5 = drr[candidate] < -1 and s22[candidate] > 1
            if not (eq3 or eq4 or eq5):
                continue
            eq6 = abs(rr[candidate] / 2.0 - medrr[candidate]) < th2[candidate]
            eq7 = abs(rr[candidate] + rr[candidate + 1] - medrr[candidate]) < th2[candidate]
            if (eq5 and eq7) or (eq3 and eq6) or eq4:
                invalid.add(candidate)
        index += 1
    valid = np.ones(rr.size, dtype=bool)
    if invalid:
        valid[list(invalid)] = False
    return valid & np.isfinite(rr) & (rr >= 300.0) & (rr <= 2000.0)


def _null_metrics(reason: str, n: int, duration_s: float) -> dict[str, Any]:
    return {
        "valid": False,
        "reason": reason,
        "n_intervals": n,
        "duration_s": duration_s,
        "mean_instantaneous_hr_bpm": None,
        "sdnn_ms": None,
        "rmssd_ms": None,
        "ln_rmssd": None,
        "pnn50_percent": None,
        "lf_power_ms2": None,
        "hf_power_ms2": None,
        "lf_hf_ratio": None,
    }


def _frequency(rr: np.ndarray) -> dict[str, Any]:
    duration_s = float(np.sum(rr) / 1000.0)
    if duration_s < 60.0 or rr.size < 3:
        return {"lf_power_ms2": None, "hf_power_ms2": None, "lf_hf_ratio": None,
                "spectral_reason": "duration_below_60_s"}
    rr_seconds = rr / 1000.0
    peaks = np.concatenate(([0.0], np.cumsum(rr_seconds)))
    timestamps = (peaks[:-1] + peaks[1:]) / 2.0
    regular = np.arange(timestamps[0], timestamps[-1], 0.25)
    if regular.size < 40:
        return {"lf_power_ms2": None, "hf_power_ms2": None, "lf_hf_ratio": None,
                "spectral_reason": "interpolation_failed"}
    kind = "cubic" if rr.size >= 4 else "linear"
    interpolated = interp1d(timestamps, rr, kind=kind, bounds_error=True)(regular)
    half = interpolated.size // 2
    global_sd = float(np.std(interpolated, ddof=1))
    mean_shift = abs(float(np.mean(interpolated[:half]) - np.mean(interpolated[-half:])))
    mean_shift_z = mean_shift / global_sd if global_sd > np.finfo(float).eps else 0.0
    variances = (float(np.var(interpolated[:half], ddof=1)), float(np.var(interpolated[-half:], ddof=1)))
    if max(variances) <= np.finfo(float).eps:
        variance_ratio = 1.0
    elif min(variances) <= np.finfo(float).eps:
        variance_ratio = math.inf
    else:
        variance_ratio = max(variances) / min(variances)
    if mean_shift_z > 0.5 or variance_ratio > 2.0:
        return {"lf_power_ms2": None, "hf_power_ms2": None, "lf_hf_ratio": None,
                "spectral_reason": "nonstationary_rr_tachogram"}
    detrended = signal.detrend(interpolated, type="linear")
    nperseg = min(detrended.size, max(256, 1000))
    freqs, psd = signal.welch(
        detrended, fs=4.0, window="hann", nperseg=nperseg,
        noverlap=nperseg // 2 if detrended.size > nperseg else 0,
        detrend="constant", scaling="density", return_onesided=True,
    )
    def integrate(low: float, high: float) -> float:
        inside = (freqs > low) & (freqs < high)
        x = np.concatenate(([low], freqs[inside], [high]))
        y = np.interp(x, freqs, psd)
        return float(_TRAPZ(y, x))
    lf = integrate(0.04, 0.15)
    hf = integrate(0.15, 0.40)
    lf_available = duration_s >= 120.0
    hf_resolved = hf > max(np.finfo(float).eps, float(np.var(detrended)) * 1e-12)
    ratio = lf / hf if lf_available and hf_resolved else None
    return {
        "lf_power_ms2": lf if lf_available else None,
        "hf_power_ms2": hf,
        "lf_hf_ratio": ratio,
        "lf_hf_interpretation": "neutral_mathematical_ratio_not_sympathovagal_balance",
        "spectral_reason": (
            None
            if ratio is not None
            else "duration_below_120_s_for_lf"
            if not lf_available
            else "hf_power_zero_or_unresolved"
        ),
    }


def analyze_rr_window(
    rr_ms: Sequence[float],
    *,
    continuity: Sequence[bool] | None = None,
    external_valid: Sequence[bool] | None = None,
    minimum_duration_s: float = 300.0,
    minimum_sqi: float = 0.8,
) -> dict[str, Any]:
    """Analyze one RR window, returning null-with-reason when gates fail."""

    raw = np.asarray(rr_ms, dtype=float)
    duration_s = float(np.sum(raw[np.isfinite(raw) & (raw > 0)]) / 1000.0)
    if raw.ndim != 1 or np.any(~np.isfinite(raw)) or np.any(raw <= 0):
        return _null_metrics("invalid_rr_intervals", int(raw.size), duration_s)
    valid = lipponen_tarvainen_valid_mask(raw)
    if external_valid is not None:
        support = np.asarray(external_valid, dtype=bool)
        if support.size != raw.size:
            raise ValueError("external_valid must have len(rr_ms) entries")
        valid &= support
    sqi = float(np.mean(valid)) if raw.size else 0.0
    base_continuity = np.ones(max(0, raw.size - 1), dtype=bool)
    if continuity is not None:
        base_continuity = np.asarray(continuity, dtype=bool)
        if base_continuity.size != max(0, raw.size - 1):
            raise ValueError("continuity must have len(rr_ms) - 1 entries")
    pairs = base_continuity & valid[:-1] & valid[1:]
    accepted = raw[valid]
    if duration_s < minimum_duration_s:
        result = _null_metrics("duration_below_required_window", int(raw.size), duration_s)
        result.update({
            "sqi": sqi,
            "artifact_burden_percent": 100.0 * (1.0 - sqi),
            "usable_duration_s": float(np.sum(accepted) / 1000.0),
        })
        return result
    if external_valid is not None and not bool(np.all(np.asarray(external_valid, dtype=bool))):
        result = _null_metrics("contact_requirement_failed", int(raw.size), duration_s)
        result.update({
            "sqi": sqi,
            "artifact_burden_percent": 100.0 * (1.0 - sqi),
            "usable_duration_s": float(np.sum(accepted) / 1000.0),
        })
        return result
    if accepted.size < 2 or int(np.sum(pairs)) < 1:
        result = _null_metrics("insufficient_contiguous_nn_intervals", int(raw.size), duration_s)
        result.update({
            "sqi": sqi,
            "artifact_burden_percent": 100.0 * (1.0 - sqi),
            "usable_duration_s": float(np.sum(accepted) / 1000.0),
        })
        return result
    if sqi < minimum_sqi:
        result = _null_metrics("signal_quality_below_threshold", int(raw.size), duration_s)
        result.update({
            "sqi": sqi,
            "artifact_burden_percent": 100.0 * (1.0 - sqi),
            "usable_duration_s": float(np.sum(accepted) / 1000.0),
        })
        return result
    diffs = np.diff(raw)[pairs]
    rmssd = float(np.sqrt(np.mean(diffs ** 2)))
    result: dict[str, Any] = {
        "valid": True,
        "reason": None,
        "n_intervals": int(raw.size),
        "n_accepted_intervals": int(accepted.size),
        "n_contiguous_pairs": int(diffs.size),
        "duration_s": duration_s,
        "usable_duration_s": float(np.sum(accepted) / 1000.0),
        "sqi": sqi,
        "artifact_burden_percent": 100.0 * (1.0 - sqi),
        "mean_instantaneous_hr_bpm": float(np.mean(60000.0 / accepted)),
        "sdnn_ms": float(np.std(accepted, ddof=1)),
        "rmssd_ms": rmssd,
        "ln_rmssd": math.log(rmssd) if rmssd > 0 else None,
        "pnn50_percent": float(100.0 * np.mean(np.abs(diffs) > 50.0)),
    }
    # PSD is only defensible when every beat in the window is accepted and no
    # acquisition boundary is crossed; excluded beats are never bridged.
    if bool(np.all(valid)) and bool(np.all(base_continuity)):
        result.update(_frequency(raw))
    else:
        result.update({"lf_power_ms2": None, "hf_power_ms2": None, "lf_hf_ratio": None,
                       "spectral_reason": "discontinuous_or_artifact_affected_window"})
    return result


def workload_response(baseline: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    """Return descriptive task-minus-baseline changes; never a workload class."""

    if not baseline.get("valid") or not task.get("valid"):
        return {"valid": False, "reason": "baseline_or_task_window_invalid",
                "delta_ln_rmssd": None, "delta_mean_hr_bpm": None}
    if baseline.get("ln_rmssd") is None or task.get("ln_rmssd") is None:
        return {"valid": False, "reason": "ln_rmssd_unavailable",
                "delta_ln_rmssd": None, "delta_mean_hr_bpm": None}
    return {
        "valid": True,
        "reason": None,
        "delta_ln_rmssd": float(task["ln_rmssd"] - baseline["ln_rmssd"]),
        "delta_mean_hr_bpm": float(
            task["mean_instantaneous_hr_bpm"] - baseline["mean_instantaneous_hr_bpm"]
        ),
        "interpretation": "descriptive_response_only_no_workload_classification",
    }
