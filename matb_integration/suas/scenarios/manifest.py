"""Immutable session-manifest construction for the native sUAS product."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from matb_integration.scenario_manifest import sha256_file
from matb_integration.suas.domain.enums import Locale, WorkloadProfile
from matb_integration.suas.domain.serialization import canonical_data

from .loader import LoadedScenario

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_QUESTIONNAIRES = _REPOSITORY_ROOT / "matb_integration" / "questionnaires"


def _asset_hashes(names: Iterable[str]) -> dict[str, str]:
    return {name: sha256_file(_QUESTIONNAIRES / name) for name in names}


def build_session_manifest(
    loaded: LoadedScenario,
    *,
    participant_id: str,
    visit_ordinal: int,
    locale: Locale,
    block_order: Iterable[WorkloadProfile],
    ui_version: str,
    engine_version: str = "0.1.0",
) -> dict[str, Any]:
    """Build a deterministic, session-specific inventory before launch."""

    order = tuple(WorkloadProfile(item) for item in block_order)
    if set(order) != {WorkloadProfile.LOW, WorkloadProfile.MEDIUM, WorkloadProfile.HIGH} or len(order) != 3:
        raise ValueError("block_order must contain LOW, MEDIUM, and HIGH exactly once")
    definition = loaded.definition
    native_assets = _asset_hashes((
        "sagat_suas_en.yaml", "sagat_suas_es.yaml", "isa_suas_en.txt",
        "isa_suas_es.txt", "nasatlx_en.txt", "nasatlx_es.txt",
        "bedford_en.txt", "bedford_es.txt",
    ))
    legacy_assets = _asset_hashes((
        "sagat_generic_en.txt", "sagat_generic_es.txt", "isa_en.txt",
        "isa_es.txt", "nasatlx_en.txt", "nasatlx_es.txt", "bedford_en.txt",
        "bedford_es.txt",
    ))
    block_ids = (WorkloadProfile.PRACTICE, *order)
    return {
        "manifest_version": 1,
        "scenario_id": definition.scenario_id,
        "schema_version": definition.schema_version,
        "engine_version": engine_version,
        "ui_version": ui_version,
        "scenario_sha256": loaded.sha256,
        "participant_id": participant_id,
        "visit_ordinal": visit_ordinal,
        "locale": Locale(locale).value,
        "block_order": [profile.value for profile in order],
        "metric_thresholds": canonical_data(definition.metric_thresholds),
        "block_parameters": {
            profile.value: canonical_data(definition.blocks[profile.value]) for profile in block_ids
        },
        "questionnaire_assets": native_assets,
        "legacy_questionnaire_assets": legacy_assets,
    }


def build_technical_session_manifest(
    loaded: LoadedScenario,
    *,
    block_id: WorkloadProfile | str,
    locale: Locale,
    ui_version: str,
    engine_version: str = "0.1.0",
) -> dict[str, Any]:
    """Build a one-block manifest that can never represent study data."""

    profile = WorkloadProfile(block_id)
    definition = loaded.definition
    if profile.value not in definition.blocks:
        raise ValueError(f"scenario is missing block {profile.value}")
    native_assets = _asset_hashes((
        "sagat_suas_en.yaml", "sagat_suas_es.yaml", "isa_suas_en.txt",
        "isa_suas_es.txt", "nasatlx_en.txt", "nasatlx_es.txt",
        "bedford_en.txt", "bedford_es.txt",
    ))
    legacy_assets = _asset_hashes((
        "sagat_generic_en.txt", "sagat_generic_es.txt", "isa_en.txt",
        "isa_es.txt", "nasatlx_en.txt", "nasatlx_es.txt", "bedford_en.txt",
        "bedford_es.txt",
    ))
    # ``block_order`` is intentionally absent. Replay validation treats an
    # omitted order as a one-block technical run and therefore cannot confuse
    # this artifact with the four-block research protocol.
    return {
        "manifest_version": 1,
        "session_mode": "interactive_technical",
        "record_class": "technical_only",
        "validity": "technical_only",
        "selected_block_id": profile.value,
        "scenario_id": definition.scenario_id,
        "schema_version": definition.schema_version,
        "engine_version": engine_version,
        "ui_version": ui_version,
        "scenario_sha256": loaded.sha256,
        "locale": Locale(locale).value,
        "metric_thresholds": canonical_data(definition.metric_thresholds),
        "block_parameters": {
            profile.value: canonical_data(definition.blocks[profile.value]),
        },
        "questionnaire_assets": native_assets,
        "legacy_questionnaire_assets": legacy_assets,
    }
