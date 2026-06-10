"""Subtest scoring for the baseline neurocognitive screen.

Stdlib-only (like log_converter). Raw trials come from the browser; all
scoring decisions live here so they are testable and re-derivable. Validity
rules are pre-registered in the spec (>=80% usable trials; Choice RT also
needs accuracy >= 0.6).
"""
from __future__ import annotations

import math
import statistics
from typing import Any

# Reuse the Hautus log-linear d' used for SYSMON/COMM — single-sourced math.
from matb_integration.log_converter import _d_prime

MIN_RT_MS = 150.0          # below this a simple-RT response is an anticipation
USABLE_FRACTION = 0.8
MIN_CHOICE_ACCURACY = 0.6
GAP_DRIFT_MS = 250.0       # SOA drift threshold above which a trial is gap-flagged


def _base(n_trials: int, n_usable: int) -> dict[str, Any]:
    return {"n_trials": n_trials, "n_usable": n_usable,
            "valid": n_trials > 0 and (n_usable / n_trials) >= USABLE_FRACTION}


def score_simple_rt(trials: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [t["rt_ms"] for t in trials
              if t.get("responded") and float(t["rt_ms"]) >= MIN_RT_MS]
    out = _base(len(trials), len(usable))
    out["median_ms"] = float(statistics.median(usable)) if usable else None
    return out


def score_choice_rt(trials: list[dict[str, Any]]) -> dict[str, Any]:
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
    return out


def score_screen(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Score all four subtests from the raw browser payload."""
    return {
        "simple_rt": score_simple_rt(payload["simple_rt"]["trials"]),
        "choice_rt": score_choice_rt(payload["choice_rt"]["trials"]),
        "nback": score_nback(payload["nback"]["trials"], soa_ms=payload["nback"].get("soa_ms")),
        "tracking": score_tracking(payload["tracking"]),
    }
