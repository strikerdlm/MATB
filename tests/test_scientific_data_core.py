from __future__ import annotations

import math

import pytest

from matb_integration.scientific_data.quality import assess_timing_quality
from matb_integration.scientific_data.sampling import DeadlineSampler
from matb_integration.scientific_data.schema import (
    BUNDLE_SCHEMA_VERSION,
    SAMPLE_FIELDS,
    TRIAL_FIELDS,
    data_dictionary,
)
from matb_integration.scientific_data.scoring import (
    communication_element_accuracy,
    resource_scores,
    rt_efficiency_score,
    tracking_scores,
)


def test_deadline_sampler_emits_twenty_real_observations_in_one_second() -> None:
    sampler = DeadlineSampler(sample_hz=20.0, start_monotonic_ns=0)

    observations = [sampler.observe(step * 50_000_000) for step in range(1, 21)]

    assert all(observation is not None for observation in observations)
    assert [observation.sample_index for observation in observations if observation] == list(range(20))
    assert sum(observation.missed_ticks for observation in observations if observation) == 0


def test_deadline_sampler_reports_missed_ticks_without_fabricating_samples() -> None:
    sampler = DeadlineSampler(sample_hz=20.0, start_monotonic_ns=0)

    delayed = sampler.observe(220_000_000)

    assert delayed is not None
    assert delayed.sample_index == 0
    assert delayed.scheduled_monotonic_ns == 200_000_000
    assert delayed.lateness_ms == pytest.approx(20.0)
    assert delayed.missed_ticks == 3
    assert sampler.observe(230_000_000) is None


def test_data_dictionary_is_generated_from_versioned_field_specs() -> None:
    dictionary = data_dictionary()

    assert dictionary["schema_version"] == BUNDLE_SCHEMA_VERSION
    assert [field["name"] for field in dictionary["tables"]["samples"]] == [
        field.name for field in SAMPLE_FIELDS
    ]
    assert [field["name"] for field in dictionary["tables"]["trials"]] == [
        field.name for field in TRIAL_FIELDS
    ]
    assert dictionary["tables"]["samples"][0]["unit"] == "1"
    assert dictionary["score_definitions"]["rt-efficiency-v1"]["direction"] == "higher_is_better"
    assert dictionary["score_definitions"]["usaarl-tracking-scaled-error-v1"]["direction"] == "lower_is_better"
    assert dictionary["compatibility_notes"]["communications_elements_available"] == 2


@pytest.mark.parametrize(
    ("rt_ms", "timeout_ms", "outcome", "expected"),
    [
        (0.0, 10_000.0, "HIT", 100.0),
        (2_500.0, 10_000.0, "HIT", 75.0),
        (10_000.0, 10_000.0, "HIT", 0.0),
        (12_000.0, 10_000.0, "HIT", 0.0),
        (math.nan, 10_000.0, "MISS", 0.0),
    ],
)
def test_rt_efficiency_score_is_bounded_and_timeout_aware(
    rt_ms: float, timeout_ms: float, outcome: str, expected: float
) -> None:
    score = rt_efficiency_score(rt_ms=rt_ms, timeout_ms=timeout_ms, outcome=outcome)

    assert score.status == "ok"
    assert score.value == expected
    assert score.direction == "higher_is_better"


def test_scores_report_missing_threshold_instead_of_guessing() -> None:
    score = rt_efficiency_score(rt_ms=500.0, timeout_ms=None, outcome="HIT")

    assert score.value is None
    assert score.status == "missing_threshold"


def test_tracking_exports_canonical_performance_and_usaarl_scaled_error() -> None:
    scores = tracking_scores(deviation=25.0, tracking_range=100.0)

    assert scores["canonical_performance"].value == 75.0
    assert scores["usaarl_scaled_error"].value == 25.0
    assert scores["usaarl_scaled_error"].direction == "lower_is_better"


def test_resource_usaarl_score_requires_the_published_target_configuration() -> None:
    incompatible = resource_scores(level=2_250.0, target=2_500.0, resource_range=1_000.0)
    compatible = resource_scores(level=2_250.0, target=2_000.0, resource_range=1_000.0)

    assert incompatible["usaarl_signed_scaled"].status == "incompatible_configuration"
    assert incompatible["usaarl_signed_scaled"].value is None
    assert compatible["usaarl_signed_scaled"].value == 25.0
    assert compatible["canonical_performance"].value == 75.0


def test_three_element_communication_accuracy_is_not_approximated() -> None:
    current = communication_element_accuracy(correct=2, available=2, require_three=True)
    general = communication_element_accuracy(correct=1, available=2, require_three=False)

    assert current.status == "not_computable"
    assert current.value is None
    assert general.value == 50.0


def test_timing_quality_warns_at_approved_thresholds() -> None:
    report = assess_timing_quality(
        sample_hz=20.0,
        observed_intervals_ms=[50.0, 50.0, 80.0],
        lateness_ms=[1.0, 2.0, 12.0],
        missed_ticks=1,
        observed_samples=99,
        non_monotonic_timestamps=0,
    )

    assert report["status"] == "warning"
    assert report["completeness"] == pytest.approx(0.99)
    assert {issue["code"] for issue in report["issues"]} == {
        "timing_lateness_p95",
    }


def test_timing_quality_rejects_non_monotonic_time() -> None:
    report = assess_timing_quality(
        sample_hz=20.0,
        observed_intervals_ms=[50.0],
        lateness_ms=[0.0],
        missed_ticks=0,
        observed_samples=2,
        non_monotonic_timestamps=1,
    )

    assert report["status"] == "error"
    assert report["issues"][0]["code"] == "non_monotonic_timestamp"
