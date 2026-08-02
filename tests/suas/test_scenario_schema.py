from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from matb_integration.scenario_builder import block_order_for_participant as legacy_block_order
from matb_integration.suas.domain.enums import Locale, WorkloadProfile
from matb_integration.suas.scenarios.loader import load_scenario, load_scenario_text
from matb_integration.suas.scenarios.manifest import build_session_manifest
from matb_integration.suas.scenarios.profiles import block_order_for_participant

REFERENCE = Path("scenarios/suas/reference_area_search.yaml")


def test_reference_scenario_normalizes_all_profiles() -> None:
    loaded = load_scenario(REFERENCE)
    assert loaded.definition.scenario_id == "reference_area_search"
    assert set(loaded.definition.blocks) == {profile.value for profile in WorkloadProfile}
    assert len(loaded.definition.aircraft) == 8
    assert len(loaded.definition.contacts) == 12
    assert loaded.normalized_yaml.endswith("\n")
    assert len(loaded.sha256) == 64


def test_unknown_key_fails_closed() -> None:
    raw = REFERENCE.read_text(encoding="utf-8") + "unexpected_root_key: true\n"
    with pytest.raises(ValidationError, match="unexpected_root_key"):
        load_scenario_text(raw)


def test_cross_reference_and_energy_feasibility_are_validated() -> None:
    raw = REFERENCE.read_text(encoding="utf-8").replace("UAS-08", "UAS-99", 1)
    with pytest.raises(ValueError, match="unknown aircraft"):
        load_scenario_text(raw)


def test_session_manifest_is_stable_and_session_specific() -> None:
    loaded = load_scenario(REFERENCE)
    order = (WorkloadProfile.LOW, WorkloadProfile.MEDIUM, WorkloadProfile.HIGH)
    manifest = build_session_manifest(
        loaded, participant_id="P01", visit_ordinal=1, locale=Locale.ES_CO,
        block_order=order, ui_version="0.1.0",
    )
    assert manifest["scenario_sha256"] == loaded.sha256
    assert manifest["participant_id"] == "P01"
    assert manifest["locale"] == "es-CO"
    assert manifest["block_order"] == ["LOW", "MEDIUM", "HIGH"]


def test_native_latin_order_matches_existing_repository_contract() -> None:
    for number in range(100):
        participant_id = f"P{number:02d}"
        native = tuple(item.value for item in block_order_for_participant(participant_id))
        legacy = tuple(item.value.upper() for item in legacy_block_order(participant_id))
        assert native == legacy
