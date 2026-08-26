"""Descriptive, direction-explicit summaries for scientific MATB bundles."""

from __future__ import annotations

from dataclasses import asdict
import math
import statistics
from typing import Any, Iterable, Mapping

from .schema import BUNDLE_SCHEMA_VERSION
from .scoring import (
    ScoreResult,
    communication_element_accuracy,
    resource_scores,
    rt_efficiency_score,
    tracking_scores,
)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _truth(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "TRUE"):
        return True
    if value in (0, "0", "false", "False", "FALSE"):
        return False
    return None


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return round(statistics.mean(valid), 6) if valid else None


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 6) if denominator else None


def _score_dict(score: ScoreResult) -> dict[str, Any]:
    return asdict(score)


def _aggregate_score(scores: list[ScoreResult], *, formula_id: str) -> ScoreResult:
    if not scores:
        return ScoreResult(None, "no_trials", formula_id, "higher_is_better")
    failures = [score for score in scores if score.status != "ok"]
    if failures:
        return ScoreResult(None, failures[0].status, formula_id, "higher_is_better")
    values = [score.value for score in scores if score.value is not None]
    return ScoreResult(_mean(values), "ok", formula_id, "higher_is_better")


def _deadline_ms(trial: Mapping[str, Any]) -> float | None:
    onset = _number(trial.get("onset_s"))
    deadline = _number(trial.get("deadline_s"))
    if onset is None or deadline is None:
        return None
    return (deadline - onset) * 1000.0


def _discrete_task_summary(trials: list[Mapping[str, Any]], task: str) -> dict[str, Any]:
    task_trials = [trial for trial in trials if trial.get("task") == task]
    signal_trials = [trial for trial in task_trials if trial.get("trial_type") != "false_alarm"]
    outcomes = [str(trial.get("outcome", "")).upper() for trial in task_trials]
    hit_rts = [
        _number(trial.get("rt_ms"))
        for trial in signal_trials
        if str(trial.get("outcome", "")).upper() == "HIT"
    ]
    rt_scores = [
        rt_efficiency_score(
            rt_ms=_number(trial.get("rt_ms")),
            timeout_ms=_deadline_ms(trial),
            outcome=str(trial.get("outcome", "")),
        )
        for trial in signal_trials
    ]
    hits = outcomes.count("HIT")
    misses = outcomes.count("MISS") + outcomes.count("TIMEOUT")
    false_alarms = outcomes.count("FA")
    denominator = hits + misses + false_alarms
    canonical = _aggregate_score(rt_scores, formula_id=f"{task}-mean-rt-efficiency-v1")
    compatible = _aggregate_score(rt_scores, formula_id=f"usaarl-{task}-mean-rt-score-v1")
    return {
        "raw": {
            "n_trials": len(task_trials),
            "n_signals": len(signal_trials),
            "n_hits": hits,
            "n_misses": misses,
            "n_false_alarms": false_alarms,
            "accuracy_pct": _percent(hits, denominator),
            "mean_hit_rt_ms": _mean(hit_rts),
        },
        "scores": {
            "canonical_rt_efficiency": _score_dict(canonical),
            "usaarl_rt_score": _score_dict(compatible),
        },
    }


def _communication_summary(trials: list[Mapping[str, Any]]) -> dict[str, Any]:
    summary = _discrete_task_summary(trials, "communications")
    prompt_trials = [
        trial
        for trial in trials
        if trial.get("task") == "communications" and trial.get("trial_type") != "false_alarm"
    ]
    available = sum(value for trial in prompt_trials if (value := _integer(trial.get("elements_available"))) is not None)
    correct = sum(value for trial in prompt_trials if (value := _integer(trial.get("elements_correct"))) is not None)
    element_score = communication_element_accuracy(correct=correct, available=available, require_three=False)
    if prompt_trials and all(_integer(trial.get("elements_available")) == 3 for trial in prompt_trials):
        compatible = communication_element_accuracy(correct=correct, available=available, require_three=False)
    else:
        compatible = ScoreResult(
            None,
            "not_computable",
            "usaarl-communication-three-element-accuracy-v1",
            "higher_is_better",
        )
    summary["raw"].update(
        elements_available=available,
        elements_correct=correct,
        element_accuracy_pct=element_score.value,
    )
    summary["scores"]["canonical_element_accuracy"] = _score_dict(element_score)
    summary["scores"]["usaarl_three_element_accuracy"] = _score_dict(compatible)
    return summary


def _tracking_summary(samples: list[Mapping[str, Any]], tracking_range: float | None) -> dict[str, Any]:
    deviations = [_number(sample.get("tracking_deviation")) for sample in samples]
    valid_deviations = [value for value in deviations if value is not None]
    in_target = [_truth(sample.get("tracking_in_target")) for sample in samples]
    valid_target = [value for value in in_target if value is not None]
    mean_deviation = _mean(valid_deviations)
    rmse = (
        round(math.sqrt(statistics.mean(value * value for value in valid_deviations)), 6)
        if valid_deviations
        else None
    )
    if mean_deviation is None:
        scores = {
            "canonical_performance": ScoreResult(
                None,
                "no_samples",
                "tracking-performance-v1",
                "higher_is_better",
            ),
            "usaarl_scaled_error": ScoreResult(
                None,
                "no_samples",
                "usaarl-tracking-scaled-error-v1",
                "lower_is_better",
            ),
        }
    else:
        scores = tracking_scores(deviation=mean_deviation, tracking_range=tracking_range)
    return {
        "raw": {
            "n_samples": len(valid_deviations),
            "mean_deviation": mean_deviation,
            "rmse_deviation": rmse,
            "in_target_pct": _percent(sum(valid_target), len(valid_target)),
        },
        "scores": {name: _score_dict(score) for name, score in scores.items()},
    }


def _resource_tank_summary(
    samples: list[Mapping[str, Any]], letter: str, resource_range: float | None
) -> dict[str, Any]:
    pairs = [
        (level, target)
        for sample in samples
        if (level := _number(sample.get(f"tank_{letter}_level"))) is not None
        and (target := _number(sample.get(f"tank_{letter}_target"))) is not None
    ]
    levels = [level for level, _ in pairs]
    targets = [target for _, target in pairs]
    deviations = [level - target for level, target in pairs]
    target = targets[0] if targets and all(math.isclose(value, targets[0]) for value in targets) else None
    mean_level = _mean(levels)
    mean_deviation = _mean(deviations)
    mean_abs_deviation = _mean([abs(value) for value in deviations])
    in_tolerance = [
        value
        for sample in samples
        if (value := _truth(sample.get(f"tank_{letter}_in_tolerance"))) is not None
    ]
    if target is None or mean_level is None or mean_abs_deviation is None:
        canonical = ScoreResult(None, "no_samples", "resource-performance-v1", "higher_is_better")
        compatible = ScoreResult(None, "no_samples", "usaarl-resource-signed-v1", "target_is_better")
    else:
        canonical = resource_scores(
            level=target + mean_abs_deviation,
            target=target,
            resource_range=resource_range,
        )["canonical_performance"]
        compatible = resource_scores(
            level=mean_level,
            target=target,
            resource_range=resource_range,
        )["usaarl_signed_scaled"]
    return {
        "raw": {
            "n_samples": len(pairs),
            "target": target,
            "mean_level": mean_level,
            "mean_signed_deviation": mean_deviation,
            "mean_absolute_deviation": mean_abs_deviation,
            "in_tolerance_pct": _percent(sum(in_tolerance), len(in_tolerance)),
        },
        "scores": {
            "canonical_performance": _score_dict(canonical),
            "usaarl_signed_scaled": _score_dict(compatible),
        },
    }


def _subjective_workload_summary(trials: list[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for trial in trials:
        if trial.get("task") != "subjective_workload":
            continue
        trial_type = str(trial.get("trial_type", "generic_scale"))
        title = str(trial.get("stimulus_id", ""))
        value = _number(trial.get("raw_value"))
        if value is None:
            continue
        instrument = grouped.setdefault(trial_type, {"values": {}, "mean_rt_ms": None})
        instrument["values"][title] = value
    for trial_type, instrument in grouped.items():
        relevant = [
            trial
            for trial in trials
            if trial.get("task") == "subjective_workload" and str(trial.get("trial_type")) == trial_type
        ]
        instrument["mean_rt_ms"] = _mean([_number(trial.get("rt_ms")) for trial in relevant])
        if trial_type == "NASA-TLX":
            values = list(instrument["values"].values())
            complete = len(values) == 6
            instrument["n_subscales_completed"] = len(values)
            instrument["raw_tlx_legacy_sum_0_60"] = round(sum(values), 6) if complete else None
            instrument["raw_tlx_mean_0_10"] = _mean(values) if complete else None
            instrument["raw_tlx_0_100"] = (
                round(float(instrument["raw_tlx_mean_0_10"]) * 10.0, 6)
                if complete
                else None
            )
    return grouped


def summarize_rows(
    *,
    samples: Iterable[Mapping[str, Any]],
    trials: Iterable[Mapping[str, Any]],
    score_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build descriptive task summaries without a composite readiness score."""
    config = dict(score_config or {})
    if "global_weights" in config:
        raise ValueError("global composite scores are outside the scientific-data v1 contract")
    sample_rows = list(samples)
    trial_rows = list(trials)
    workload_trials = [
        trial for trial in trial_rows if trial.get("task") == "workload" and _number(trial.get("raw_value")) is not None
    ]
    automation = {}
    for task in ("sysmon", "communications", "tracking", "resman"):
        values = [
            value
            for sample in sample_rows
            if (value := _truth(sample.get(f"automation_{task}"))) is not None
        ]
        automation[task] = round(sum(values) / len(values), 6) if values else None
    load_counts = [_number(sample.get("discrete_load_count")) for sample in sample_rows]
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "scope": "descriptive_research_metrics_only",
        "sysmon": _discrete_task_summary(trial_rows, "sysmon"),
        "communications": _communication_summary(trial_rows),
        "tracking": _tracking_summary(sample_rows, _number(config.get("tracking_range"))),
        "resource_management": {
            "tank_a": _resource_tank_summary(sample_rows, "a", _number(config.get("resource_range"))),
            "tank_b": _resource_tank_summary(sample_rows, "b", _number(config.get("resource_range"))),
        },
        "workload": {
            "n_completed": len(workload_trials),
            "mean_isa_1_to_10": _mean([_number(trial.get("raw_value")) for trial in workload_trials]),
            "mean_rt_ms": _mean([_number(trial.get("rt_ms")) for trial in workload_trials]),
        },
        "subjective_workload": _subjective_workload_summary(trial_rows),
        "task_load": {"mean_discrete_task_count": _mean(load_counts)},
        "automation_exposure_fraction": automation,
        "score_configuration": {
            "tracking_range": _number(config.get("tracking_range")),
            "resource_range": _number(config.get("resource_range")),
        },
    }


__all__ = ["summarize_rows"]
