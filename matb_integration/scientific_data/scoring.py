"""Transparent canonical and USAARL-paper-compatible score transforms."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class ScoreResult:
    value: float | None
    status: str
    formula_id: str
    direction: str
    unit: str = "percent"


def _missing(formula_id: str, status: str, direction: str) -> ScoreResult:
    return ScoreResult(None, status, formula_id, direction)


def _percent(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 6)


def rt_efficiency_score(*, rt_ms: float | None, timeout_ms: float | None, outcome: str) -> ScoreResult:
    formula = "rt-efficiency-v1"
    if timeout_ms is None or not math.isfinite(timeout_ms) or timeout_ms <= 0:
        return _missing(formula, "missing_threshold", "higher_is_better")
    if outcome.upper() in {"MISS", "TIMEOUT"} or rt_ms is None or not math.isfinite(rt_ms):
        value = 0.0
    else:
        value = _percent(100.0 * (timeout_ms - rt_ms) / timeout_ms)
    return ScoreResult(value, "ok", formula, "higher_is_better")


def tracking_scores(*, deviation: float, tracking_range: float | None) -> dict[str, ScoreResult]:
    if tracking_range is None or not math.isfinite(tracking_range) or tracking_range <= 0:
        return {
            "canonical_performance": _missing("tracking-performance-v1", "missing_threshold", "higher_is_better"),
            "usaarl_scaled_error": _missing("usaarl-tracking-scaled-error-v1", "missing_threshold", "lower_is_better"),
        }
    scaled_error = _percent(100.0 * deviation / tracking_range)
    return {
        "canonical_performance": ScoreResult(
            round(100.0 - scaled_error, 6), "ok", "tracking-performance-v1", "higher_is_better"
        ),
        "usaarl_scaled_error": ScoreResult(
            scaled_error, "ok", "usaarl-tracking-scaled-error-v1", "lower_is_better"
        ),
    }


def resource_scores(
    *, level: float, target: float, resource_range: float | None
) -> dict[str, ScoreResult]:
    if resource_range is None or not math.isfinite(resource_range) or resource_range <= 0:
        return {
            "canonical_performance": _missing("resource-performance-v1", "missing_threshold", "higher_is_better"),
            "usaarl_signed_scaled": _missing("usaarl-resource-signed-v1", "missing_threshold", "target_is_better"),
        }
    signed = 100.0 * (level - target) / resource_range
    canonical = 100.0 - _percent(abs(signed))
    usaarl = (
        ScoreResult(round(signed, 6), "ok", "usaarl-resource-signed-v1", "target_is_better")
        if math.isclose(target, 2_000.0)
        else _missing("usaarl-resource-signed-v1", "incompatible_configuration", "target_is_better")
    )
    return {
        "canonical_performance": ScoreResult(
            round(canonical, 6), "ok", "resource-performance-v1", "higher_is_better"
        ),
        "usaarl_signed_scaled": usaarl,
    }


def communication_element_accuracy(
    *, correct: int, available: int, require_three: bool
) -> ScoreResult:
    formula = "communication-element-accuracy-v1"
    if require_three and available != 3:
        return _missing(formula, "not_computable", "higher_is_better")
    if available <= 0 or correct < 0 or correct > available:
        return _missing(formula, "invalid_denominator", "higher_is_better")
    return ScoreResult(_percent(100.0 * correct / available), "ok", formula, "higher_is_better")


__all__ = [
    "ScoreResult",
    "communication_element_accuracy",
    "resource_scores",
    "rt_efficiency_score",
    "tracking_scores",
]
