"""Frozen allocation and manifest helpers for MATB workload calibration."""

from __future__ import annotations

import itertools
import math
from typing import Any, Mapping

CONDITIONS = ("LOW", "MEDIUM", "HIGH")
COMPLETE_ORDERS = tuple(itertools.permutations(CONDITIONS))
STUDY_MANIFEST_VERSION = "1.0"


def calibration_orders(participant_sequence: int, *, sessions: int = 3) -> tuple[tuple[str, ...], ...]:
    """Return three distinct, population-balanced orders for one participant.

    Consecutive groups of six participants contain every permutation once in
    every session.  The two-position session rotation gives each participant
    distinct orders without changing that balance.
    """

    if participant_sequence < 1:
        raise ValueError("participant_sequence must be >= 1")
    if sessions < 1 or sessions > 3:
        raise ValueError("the v1 calibration contract supports one to three sessions")
    base = participant_sequence - 1
    return tuple(COMPLETE_ORDERS[(base + 2 * session) % len(COMPLETE_ORDERS)] for session in range(sessions))


def recruitment_target(powered_complete_n: int, *, attrition_fraction: float) -> int:
    """Inflate the powered completer count and preserve six-order balance."""

    if powered_complete_n < 6:
        raise ValueError("powered_complete_n must be at least six")
    if not 0 <= attrition_fraction < 0.5:
        raise ValueError("attrition_fraction must be in [0, 0.5)")
    inflated = math.ceil(powered_complete_n / (1.0 - attrition_fraction))
    return int(math.ceil(inflated / 6) * 6)


def build_calibration_study_manifest(
    *,
    source_commit: str,
    compatibility_profile_id: str,
    scenario_hashes: Mapping[str, str],
    metrics_schema_version: str = "2.0",
    locale: str = "es-CO",
) -> dict[str, Any]:
    if set(scenario_hashes) != set(CONDITIONS):
        raise ValueError("scenario_hashes must contain exactly LOW, MEDIUM and HIGH")
    if not all(isinstance(value, str) and len(value) == 64 for value in scenario_hashes.values()):
        raise ValueError("every scenario hash must be a 64-character SHA-256")
    return {
        "study_manifest_version": STUDY_MANIFEST_VERSION,
        "status": "DRAFT_PENDING_PREREGISTRATION_AND_ETHICS",
        "population": "military_aviation_personnel",
        "claim_boundary": "non_diagnostic_non_fitness_research",
        "source_commit": source_commit,
        "compatibility_profile_id": compatibility_profile_id,
        "scenario_hashes": dict(sorted(scenario_hashes.items())),
        "metrics_schema_version": metrics_schema_version,
        "locale": {"language": locale, "validation_status": "PENDING"},
        "pilot": {"n": 12, "participants_per_order": 2, "included_in_confirmatory_inference": False},
        "confirmatory": {
            "sample_size_method": "simulation_based_repeated_measures_power_from_pilot_variance",
            "target_multiple": 6,
            "sessions": 3,
            "session_interval_days": {"target": 7, "tolerance": 2},
            "same_time_of_day_required": True,
            "counterbalancing": "complete_six_orders_each_session_with_two_position_rotation",
        },
        "primary_families": {
            "subjective": ["nasatlx.rtlx_mean_0_100"],
            "task_performance": [
                "sysmon.hit_rate",
                "sysmon.mean_rt_ms",
                "communications.d_prime",
                "communications.mean_rt_ms",
                "track.rmse_deviation",
                "track.percent_time_in_target",
                "resman.mean_absolute_deviation",
                "resman.percent_time_in_tolerance",
            ],
        },
        "secondary_or_exploratory": ["ISA", "Bedford", "SAGAT", "strategy", "legacy_estimated_metrics"],
        "prohibited_primary_endpoint": "universal_composite_score",
    }
