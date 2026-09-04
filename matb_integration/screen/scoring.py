"""Subtest scoring for the baseline neurocognitive screen.

Stdlib-only (like log_converter). Raw trials come from the browser; all
scoring decisions live here so they are testable and re-derivable. Validity
rules are pre-registered in the spec (>=80% usable trials; Choice RT also
needs accuracy >= 0.6).
"""
from __future__ import annotations

import math
import statistics
from numbers import Real
from typing import Any

# Reuse the Hautus log-linear d' used for SYSMON/COMM — single-sourced math.
from matb_integration.log_converter import _d_prime

MIN_RT_MS = 150.0          # below this a simple-RT response is an anticipation
USABLE_FRACTION = 0.8
MIN_CHOICE_ACCURACY = 0.6
GAP_DRIFT_MS = 250.0       # SOA drift threshold above which a trial is gap-flagged
MAX_TRACKING_GAP_MS = 250.0


def _number(value: Any, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return float(value)


def _trials(trials: Any) -> None:
    if not isinstance(trials, list) or len(trials) > 10000:
        raise ValueError("trials must be a bounded list")
    for trial in trials:
        if not isinstance(trial, dict) or type(trial.get("responded")) is not bool:
            raise ValueError("each trial requires a boolean responded field")


def _rt_trials(trials: Any) -> None:
    _trials(trials)
    for trial in trials:
        if trial["responded"]:
            _number(trial.get("rt_ms"), "rt_ms", 0)
        elif trial.get("rt_ms") is not None:
            raise ValueError("an unanswered trial cannot have a reaction time")


def _base(n_trials: int, n_usable: int) -> dict[str, Any]:
    return {"n_trials": n_trials, "n_usable": n_usable,
            "valid": n_trials > 0 and (n_usable / n_trials) >= USABLE_FRACTION}


def score_simple_rt(trials: list[dict[str, Any]]) -> dict[str, Any]:
    _rt_trials(trials)
    usable = [t["rt_ms"] for t in trials
              if t.get("responded") and float(t["rt_ms"]) >= MIN_RT_MS]
    out = _base(len(trials), len(usable))
    out["median_ms"] = float(statistics.median(usable)) if usable else None
    return out


def score_choice_rt(trials: list[dict[str, Any]]) -> dict[str, Any]:
    _rt_trials(trials)
    for trial in trials:
        if type(trial.get("correct")) is not bool:
            raise ValueError("correct must be a boolean")
        if not trial["responded"] and trial["correct"]:
            raise ValueError("an unanswered trial cannot be correct")
        if "stimulus_side" in trial or "response_side" in trial:
            if trial.get("stimulus_side") not in {"left", "right"}:
                raise ValueError("stimulus_side must be left or right")
            if trial["responded"] and trial.get("response_side") not in {"left", "right"}:
                raise ValueError("a response requires response_side")
            correct = trial["responded"] and trial.get("response_side") == trial["stimulus_side"]
            if trial["correct"] != correct:
                raise ValueError("correct does not match recorded stimuli and response")
    usable = [t for t in trials if t.get("responded")]
    correct = [float(t["rt_ms"]) for t in usable if t.get("correct")]
    out = _base(len(trials), len(usable))
    accuracy = (len(correct) / len(usable)) if usable else None
    out["accuracy"] = accuracy
    out["median_ms"] = float(statistics.median(correct)) if correct else None
    if out["valid"] and (accuracy is None or accuracy < MIN_CHOICE_ACCURACY):
        out["valid"] = False
    return out


def score_nback(trials: list[dict[str, Any]], soa_ms: float | None = None) -> dict[str, Any]:
    _trials(trials)
    if soa_ms is not None:
        _number(soa_ms, "soa_ms", 1)
    previous_time = None
    has_letters = any("letter" in row for row in trials)
    for index, trial in enumerate(trials):
        if type(trial.get("is_target")) is not bool:
            raise ValueError("is_target must be a boolean")
        if has_letters:
            if not isinstance(trial.get("letter"), str) or len(trial["letter"]) != 1:
                raise ValueError("every stimulus must include its letter")
            expected = index >= 2 and trial["letter"] == trials[index - 2]["letter"]
            if trial["is_target"] != expected:
                raise ValueError("is_target does not match the recorded 2-back sequence")
        if trial.get("shown_at_ms") is not None:
            timestamp = _number(trial["shown_at_ms"], "shown_at_ms", 0)
            if previous_time is not None and timestamp <= previous_time:
                raise ValueError("stimulus timestamps must increase")
            previous_time = timestamp
    have_ts = soa_ms and trials and all(t.get("shown_at_ms") is not None for t in trials)
    if have_ts:
        gaps = [False]
        for prev, cur in zip(trials, trials[1:]):
            drift = abs((float(cur["shown_at_ms"]) - float(prev["shown_at_ms"])) - soa_ms)
            gaps.append(drift > GAP_DRIFT_MS)
        usable = [t for t, g in zip(trials, gaps) if not g]
    else:
        usable = [t for t in trials if not t.get("gap")]
    hits = sum(1 for t in usable if t["is_target"] and t.get("responded"))
    misses = sum(1 for t in usable if t["is_target"] and not t.get("responded"))
    fa = sum(1 for t in usable if not t["is_target"] and t.get("responded"))
    cr = sum(1 for t in usable if not t["is_target"] and not t.get("responded"))
    out = _base(len(trials), len(usable))
    out["d_prime"] = _d_prime(hits, misses, fa, cr) if usable else None
    out.update({"hits": hits, "misses": misses, "fa": fa, "cr": cr})
    return out


def score_tracking(block: dict[str, Any]) -> dict[str, Any]:
    samples = block.get("samples", [])
    if not isinstance(samples, list) or len(samples) > 200000:
        raise ValueError("samples must be a bounded list")
    previous_time = None
    for sample in samples:
        if not isinstance(sample, (list, tuple)) or len(sample) != 5:
            raise ValueError("tracking sample must contain time and four coordinates")
        for value in sample:
            _number(value, "tracking sample")
        timestamp = _number(sample[0], "tracking timestamp", 0)
        if previous_time is not None and timestamp <= previous_time:
            raise ValueError("tracking timestamps must increase")
        previous_time = timestamp
    _number(block.get("n_expected_samples", 0), "n_expected_samples", 0)
    _number(block.get("path_amplitude_px", 0), "path_amplitude_px", 0)
    n_expected = int(block.get("n_expected_samples") or 0)
    amplitude = float(block.get("path_amplitude_px") or 0.0)
    out = {"n_samples": len(samples), "n_expected_samples": n_expected,
           "valid": n_expected > 0 and amplitude > 0
                    and (len(samples) / n_expected) >= USABLE_FRACTION}
    if samples and amplitude > 0:
        sq = [(s[1] - s[3]) ** 2 + (s[2] - s[4]) ** 2 for s in samples]
        out["rms_norm"] = math.sqrt(sum(sq) / len(sq)) / amplitude
    else:
        out["rms_norm"] = None
    if "duration_ms" in block:
        duration = _number(block["duration_ms"], "duration_ms", 1)
        if samples and samples[-1][0] > duration + MAX_TRACKING_GAP_MS:
            raise ValueError("tracking samples extend past the recording window")
        # Integrate over observed time, excluding gaps. A high-refresh display
        # must not outweigh a low-refresh display or conceal a recording gap.
        intervals = [(a, b, min(b[0], duration) - a[0]) for a, b in zip(samples, samples[1:])
                     if 0 < b[0] - a[0] <= MAX_TRACKING_GAP_MS and a[0] < duration]
        coverage = sum(dt for _, _, dt in intervals)
        squared_integral = sum(
            dt * (((a[1] - a[3]) ** 2 + (a[2] - a[4]) ** 2)
                  + ((b[1] - b[3]) ** 2 + (b[2] - b[4]) ** 2)) / 2
            for a, b, dt in intervals
        )
        out.update({"coverage_fraction": coverage / duration,
                    "metric_version": "tracking-time-weighted-v2",
                    "valid": amplitude > 0 and coverage / duration >= USABLE_FRACTION,
                    "rms_norm": math.sqrt(squared_integral / coverage) / amplitude
                    if coverage > 0 and amplitude > 0 else None})
    return out


def score_screen(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Score all four subtests from the raw browser payload."""
    if payload.get("schema_version") == 2:
        if any("stimulus_side" not in row for row in payload["choice_rt"]["trials"]):
            raise ValueError("version 2 requires recorded choice stimuli")
        if any("letter" not in row or row.get("shown_at_ms") is None for row in payload["nback"]["trials"]):
            raise ValueError("version 2 requires recorded 2-back letters and onset times")
        if "duration_ms" not in payload["tracking"]:
            raise ValueError("version 2 requires the tracking recording duration")
    return {
        "simple_rt": score_simple_rt(payload["simple_rt"]["trials"]),
        "choice_rt": score_choice_rt(payload["choice_rt"]["trials"]),
        "nback": score_nback(payload["nback"]["trials"], soa_ms=payload["nback"].get("soa_ms")),
        "tracking": score_tracking(payload["tracking"]),
    }
