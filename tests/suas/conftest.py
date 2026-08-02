"""Shared fixture for the strict bundled sUAS scenario."""

from __future__ import annotations

from pathlib import Path

import pytest

from matb_integration.suas.scenarios.loader import LoadedScenario, load_scenario


@pytest.fixture(scope="session")
def reference_scenario() -> Path:
    return Path("scenarios/suas/reference_area_search.yaml")


@pytest.fixture(scope="session")
def loaded_scenario(reference_scenario: Path) -> LoadedScenario:
    return load_scenario(reference_scenario)
