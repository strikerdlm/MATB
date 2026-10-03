"""Experimental chest-ACC respiratory-frequency proxy with explicit abstention.

References: Schipper et al. 2021, doi:10.1088/1361-6579/abf01f;
"Comparison between Chest-Worn Accelerometer and Gyroscope Performance", 2022
(PMC9599933). This is a separate spectral
implementation, not a reproduction of their validated algorithms. Thresholds
below are engineering gates tested with synthetic signals, not clinical limits.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

ALGORITHM = "polar-acc-respiration-spectral-v1-experimental"
BAND_HZ = (0.10, 0.70)
WINDOW_SECONDS = 60.0
HOP_SECONDS = 30.0


def estimate_acc_respiration(times_s, axes_mg, epochs, sample_indices, nominal_rate_hz: float) -> dict:
    times = np.asarray(times_s, dtype=float)
    axes = np.asarray(axes_mg, dtype=float)
    epochs = np.asarray(epochs)
    indices = np.asarray(sample_indices)
    result = dict(
        algorithm=ALGORITHM, source="chest_accelerometer_xyz", status="unavailable",
        respiratory_rate_bpm=None, accuracy_bpm=None, validated_against_reference=False,
        band_hz=list(BAND_HZ), window_seconds=WINDOW_SECONDS, windows=[], waveform=[],
        accepted_windows=0, evaluated_windows=0, accepted_window_percent=0.0,
        reason="insufficient_contiguous_acceleration", interpretation="experimental_proxy_not_measured_respiration",
    )
    if times.ndim != 1 or axes.shape != (len(times), 3) or len(epochs) != len(times) or len(indices) != len(times):
        result["reason"] = "invalid_acceleration_shape"
        return result
    if len(times) < 2 or not np.all(np.isfinite(times)) or not np.all(np.isfinite(axes)):
        return result
    if not np.isfinite(nominal_rate_hz) or nominal_rate_hz < 5:
        result["reason"] = "unsupported_sample_rate"
        return result
    dt = np.diff(times)
    breaks = np.flatnonzero((dt <= 0) | (dt > 1.5 / nominal_rate_hz) |
                           (np.diff(epochs) != 0) | (np.diff(indices) != 1)) + 1
    for chunk in np.split(np.arange(len(times)), breaks):
        if len(chunk) < nominal_rate_hz * WINDOW_SECONDS:
            continue
        observed_rate = 1.0 / float(np.median(np.diff(times[chunk])))
        if abs(observed_rate / nominal_rate_hz - 1) > 0.05:
            continue
        length = int(round(WINDOW_SECONDS * observed_rate))
        hop = int(round(HOP_SECONDS * observed_rate))
        for offset in range(0, len(chunk) - length + 1, hop):
            window = chunk[offset:offset + length]
            raw = axes[window]
            record = dict(time_s=float(times[window[0]] - times[0]), rate_bpm=None,
                          accepted=False, reason=None, spectral_concentration=None, periodicity=None)
            result["windows"].append(record)
            # Axis dynamics preserve chest tilt; vector magnitude alone can cancel respiration.
            highpass = signal.sosfiltfilt(signal.butter(4, 1.0, "highpass", fs=observed_rate, output="sos"), raw, axis=0)
            if float(np.sqrt(np.mean(np.sum(highpass ** 2, axis=1)))) > 50.0 or np.max(np.abs(np.diff(raw, axis=0))) > 200.0:
                record["reason"] = "movement_contamination"
                continue
            uniform = np.arange(0.0, WINDOW_SECONDS - 1 / observed_rate, 0.2)
            local_times = times[window] - times[window[0]]
            lowpass = signal.sosfiltfilt(signal.butter(4, 1.5, "lowpass", fs=observed_rate, output="sos"), raw, axis=0)
            sampled = np.column_stack([np.interp(uniform, local_times, lowpass[:, axis]) for axis in range(3)])
            filtered = signal.sosfiltfilt(signal.butter(4, BAND_HZ, "bandpass", fs=5.0, output="sos"), sampled, axis=0)
            _, _, vectors = np.linalg.svd(filtered, full_matrices=False)
            waveform = filtered @ vectors[0]
            waveform = signal.detrend(waveform)
            if float(np.std(waveform)) < 0.5:
                record["reason"] = "respiratory_motion_too_small"
                continue
            frequencies, power = signal.periodogram(waveform, fs=5.0, window="hann", nfft=len(waveform))
            band = (frequencies >= BAND_HZ[0]) & (frequencies <= BAND_HZ[1])
            bins = np.flatnonzero(band)
            peak = bins[int(np.argmax(power[band]))]
            hz = float(frequencies[peak])
            concentration = float(np.sum(power[np.abs(frequencies - hz) <= 1.5 / WINDOW_SECONDS]) / np.sum(power[band]))
            correlation = signal.correlate(waveform, waveform, mode="full")[len(waveform) - 1:]
            lag = int(round(5.0 / hz))
            periodicity = float(correlation[lag] / correlation[0])
            record.update(spectral_concentration=concentration, periodicity=periodicity)
            if hz <= BAND_HZ[0] + 1 / WINDOW_SECONDS or hz >= BAND_HZ[1] - 1 / WINDOW_SECONDS:
                record["reason"] = "peak_at_search_boundary"
            elif concentration < 0.60 or periodicity < 0.50:
                record["reason"] = "no_stable_respiratory_peak"
            else:
                record.update(rate_bpm=round(hz * 60.0, 2), accepted=True)
                result["waveform"] = [[round(float(t), 3), round(float(value), 4)] for t, value in zip(
                    uniform + record["time_s"], waveform)]
    accepted = [window["rate_bpm"] for window in result["windows"] if window["accepted"]]
    result.update(evaluated_windows=len(result["windows"]), accepted_windows=len(accepted),
                  accepted_window_percent=100.0 * len(accepted) / len(result["windows"]) if result["windows"] else 0.0)
    if accepted:
        result.update(status="estimated", respiratory_rate_bpm=float(np.median(accepted)), reason=None)
    elif result["windows"]:
        result["reason"] = "no_usable_respiratory_windows"
    return result
