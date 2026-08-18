from __future__ import annotations

import json

import numpy as np

from matb_integration.analysis.liftoff import (
    run_liftoff_analysis,
    select_count_family,
)


def synthetic_liftoff_cohort(participants: int = 12):
    rows = []
    context = []
    visits = (("T0", 0.0), ("DM8", -2.0), ("DM15", -4.0))
    for index in range(participants):
        participant_id = f"P{index + 1:02d}"
        sequence = "MATB_LIFTOFF" if index % 2 == 0 else "LIFTOFF_MATB"
        context.append({
            "participant_id": participant_id,
            "sequence": sequence,
            "prior_fpv_hours": float(index),
        })
        for visit_code, visit_effect in visits:
            rows.append({
                "participant_id": participant_id,
                "visit_code": visit_code,
                "metric": "median_lap_time_s",
                "value": 65.0 + index * 0.4 + visit_effect,
            })
            rows.append({
                "participant_id": participant_id,
                "visit_code": visit_code,
                "metric": "valid_laps",
                "value": 8 + index % 3 + int(-visit_effect / 2),
            })
    return rows, context


def test_liftoff_analysis_runs_three_visit_mixed_model():
    rows, context = synthetic_liftoff_cohort()

    artifact = run_liftoff_analysis(rows, context)

    assert artifact["analysis_version"] == "liftoff-analysis-v1"
    assert artifact["status"] == "ok"
    assert artifact["continuous"]["median_lap_time_s"]["formula"] == (
        "value ~ C(visit_code) + C(sequence) + prior_fpv_experience"
    )
    assert [contrast["name"] for contrast in artifact["continuous"]["median_lap_time_s"]["contrasts"]] == [
        "T0_vs_DM8", "T0_vs_DM15", "DM8_vs_DM15",
    ]
    assert "classifier" not in json.dumps(artifact).lower()


def test_overdispersed_counts_select_negative_binomial():
    assert select_count_family(np.array([0, 0, 1, 1, 2, 12, 15])) == "negative_binomial"
    assert select_count_family(np.array([4, 5, 5, 6, 5, 4])) == "poisson"


def test_insufficient_data_requires_three_participants_with_repeated_visits():
    rows, context = synthetic_liftoff_cohort(participants=2)

    artifact = run_liftoff_analysis(rows, context)

    assert artifact["status"] == "insufficient_data"
    assert artifact["missingness"]["imputed_values"] == 0
