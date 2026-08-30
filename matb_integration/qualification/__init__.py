"""Fail-closed scientific qualification and conformance contracts."""

from .contracts import (
    evaluate_conformance,
    evaluate_release_eligibility,
    evaluate_timing_qualification,
    list_profiles,
    load_profile,
    validate_compatibility_profile,
)
from .reference import build_reference_session, export_bids_events
from .study import build_calibration_study_manifest, calibration_orders, recruitment_target
from .golden import run_scenario_builder_golden

__all__ = [
    "evaluate_conformance",
    "evaluate_release_eligibility",
    "evaluate_timing_qualification",
    "list_profiles",
    "load_profile",
    "validate_compatibility_profile",
    "build_reference_session",
    "export_bids_events",
    "build_calibration_study_manifest",
    "calibration_orders",
    "recruitment_target",
    "run_scenario_builder_golden",
]
