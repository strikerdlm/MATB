"""Descriptive, quality-gated review of a finalized Polar capture."""
from __future__ import annotations

import numpy as np
import pyarrow.parquet as pq

from .analysis import HRV_ALGORITHM_VERSIONS, analyze_rr_window, lipponen_tarvainen_valid_mask
from .respiration import estimate_acc_respiration
from .rr_export import RRExportError, sha256


def review_capture(root, manifest) -> dict:
    for name in ("rr.parquet", "acc.parquet"):
        path = (root / name).resolve()
        entry = next((item for item in manifest.artifacts if item.relative_path == name), None)
        if path.parent != root or entry is None or not path.is_file() or sha256(path) != entry.sha256:
            raise RRExportError("polar_artifact_checksum_failed")
    rr = pq.read_table(root / "rr.parquet").to_pydict()
    acc = pq.read_table(root / "acc.parquet", columns=["sensor_timestamp_ns", "x_mg", "y_mg", "z_mg", "connection_epoch", "sample_index", "sample_rate_hz"]).to_pydict()
    values = np.asarray(rr["rr_ms"], dtype=float)
    indices = np.asarray(rr["beat_index"], dtype=np.int64)
    epochs = np.asarray(rr["connection_epoch"], dtype=int)
    gaps = np.asarray(rr["gap_before"], dtype=bool)
    valid_numeric = np.isfinite(values) & (values > 0)
    contiguous = (np.diff(indices) == 1) & (np.diff(epochs) == 0) & ~gaps[1:]
    contact = np.asarray([not supported or detected is True for supported, detected in zip(rr["contact_supported"], rr["contact_detected"])])
    metrics = None
    poincare = []
    window_start = window_end = None
    if len(values):
        # Never interpolate across acquisition boundaries. Choose the longest
        # numeric continuous span, then the last <= five minutes of that span.
        breaks = np.flatnonzero(~contiguous | ~valid_numeric[:-1] | ~valid_numeric[1:]) + 1
        chunks = [chunk for chunk in np.split(np.arange(len(values)), breaks) if len(chunk) and np.all(valid_numeric[chunk])]
        if chunks:
            selected = max(chunks, key=lambda chunk: float(np.sum(values[chunk])))
            durations = np.cumsum(values[selected][::-1]) / 1000.0
            count = min(len(selected), int(np.searchsorted(durations, 300.0)) + 1)
            selected = selected[-count:]
            raw = values[selected]
            duration = float(np.sum(raw) / 1000.0)
            metrics = analyze_rr_window(raw, external_valid=contact[selected], minimum_duration_s=60.0,
                                        include_spectrum=duration >= 300.0)
            metrics["window_kind"] = "five_minute" if duration >= 300 else "short_exploratory"
            window_start, window_end = int(indices[selected[0]]), int(indices[selected[-1]])
            if duration < 300:
                for key in ("lf_power_ms2", "hf_power_ms2", "lf_hf_ratio"):
                    metrics[key] = None
                metrics.pop("spectrum", None)
                metrics["spectral_reason"] = "five_minute_window_required_for_review"
            if metrics["valid"]:
                accepted = lipponen_tarvainen_valid_mask(raw) & contact[selected]
                pairs = np.flatnonzero(accepted[:-1] & accepted[1:])
                poincare = [[float(raw[i]), float(raw[i + 1])] for i in pairs]
    trace = []
    if len(values):
        # Host-reconstructed times keep observed gaps visible; indices retain
        # the exact acquisition order even if an arrival timestamp regresses.
        times = np.asarray(rr["beat_monotonic_ns"], dtype=np.int64)
        step = max(1, int(np.ceil(len(values) / 2000)))
        for i in range(len(values)):
            if i and not contiguous[i - 1]:
                trace.append([float((times[i] - times[0]) / 1e9), None])
            if i % step == 0 or i == len(values) - 1:
                trace.append([float((times[i] - times[0]) / 1e9), float(values[i]) if valid_numeric[i] else None])
    acc_ns = np.asarray(acc["sensor_timestamp_ns"], dtype=np.int64)
    rates = set(acc["sample_rate_hz"])
    respiration = estimate_acc_respiration(
        (acc_ns - acc_ns[0]) / 1e9 if len(acc_ns) else [],
        np.column_stack([acc["x_mg"], acc["y_mg"], acc["z_mg"]]),
        acc["connection_epoch"], acc["sample_index"], float(next(iter(rates))) if len(rates) == 1 else 0,
    )
    return dict(schema_version="1.0", capture_id=manifest.capture_id, execution_purpose=manifest.execution_purpose,
                algorithm_versions=HRV_ALGORITHM_VERSIONS, metrics=metrics, rr_tachogram=trace,
                poincare=poincare, analysis_first_beat=window_start, analysis_last_beat=window_end,
                respiration=respiration, incomplete_reasons=list(manifest.incomplete_reasons),
                interpretation="descriptive_only_no_diagnosis_or_readiness_score")
