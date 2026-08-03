from pathlib import Path

import pytest

from matb_integration.suas.adapters.synthetic import SyntheticVehicleBackend
from matb_integration.suas.domain.enums import Locale, WorkloadProfile
from matb_integration.suas.research.probes import load_suas_probe_bank, render_probe
from matb_integration.suas.research.scoring import (
    aggregate_sagat,
    score_bedford,
    score_isa,
    score_nasa_tlx,
    score_probe_answer,
)
from matb_integration.suas.scenarios.manifest import build_session_manifest


@pytest.mark.parametrize("value", [0, 11, 2.5, "high", True])
def test_isa_rejects_non_integer_or_out_of_range(value) -> None:
    with pytest.raises(ValueError, match="ISA"):
        score_isa(value)


def test_tlx_and_bedford_scoring() -> None:
    tlx = score_nasa_tlx({
        "mental_demand": 8,
        "physical_demand": 1,
        "temporal_demand": 7,
        "performance": 4,
        "effort": 8,
        "frustration": 2,
    })

    assert tlx.raw_tlx == 30.0
    assert tlx.subscales["mental_demand"] == 8.0
    assert score_bedford(7).value == 7


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {
            "mental_demand": 8, "physical_demand": 1, "temporal_demand": 7,
            "performance": 4, "effort": 8, "frustration": 2, "extra": 1,
        },
        {
            "mental_demand": 8, "physical_demand": 1, "temporal_demand": 7,
            "performance": 4, "effort": 8, "frustration": 11,
        },
        {
            "mental_demand": 8, "physical_demand": 1, "temporal_demand": 7,
            "performance": 4, "effort": True, "frustration": 2,
        },
    ],
)
def test_tlx_rejects_wrong_shape_or_values(answers) -> None:
    with pytest.raises(ValueError, match="NASA-TLX"):
        score_nasa_tlx(answers)


@pytest.mark.parametrize("value", [0, 11, 3.5, "7", True])
def test_bedford_rejects_non_integer_or_out_of_range(value) -> None:
    with pytest.raises(ValueError, match="Bedford"):
        score_bedford(value)


def test_sagat_scoring_normalizes_only_surrounding_whitespace(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    state = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["LOW"])
    rendered = render_probe(load_suas_probe_bank(Locale.EN)["suas_l1_lost_links"], state)

    correct = score_probe_answer(rendered, " 0 ", latency_ms=1_250)
    wrong_case = score_probe_answer(rendered, "unknown", latency_ms=500)
    timeout = score_probe_answer(rendered, None, latency_ms=15_000, timed_out=True)
    aggregate = aggregate_sagat((correct, wrong_case, timeout))

    assert correct.correct is True
    assert wrong_case.correct is False
    assert timeout.timed_out is True
    assert aggregate.overall.correct == 1
    assert aggregate.overall.total == 3
    assert aggregate.overall.accuracy == pytest.approx(1 / 3)
    assert aggregate.by_level[1].total == 3


def test_native_instrument_assets_and_manifest_are_separate(loaded_scenario) -> None:
    questionnaires = Path("matb_integration/questionnaires")
    for name in ("isa_suas_en.txt", "isa_suas_es.txt"):
        assert (questionnaires / name).read_text(encoding="utf-8").strip().endswith(";1/10/5")
    for name in ("nasatlx_en.txt", "nasatlx_es.txt"):
        rows = (questionnaires / name).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 6
        assert all(row.endswith(";0/10/5") for row in rows)

    manifest = build_session_manifest(
        loaded_scenario,
        participant_id="P03",
        visit_ordinal=1,
        locale=Locale.EN,
        block_order=(WorkloadProfile.LOW, WorkloadProfile.MEDIUM, WorkloadProfile.HIGH),
        ui_version="test",
    )
    assert set(manifest["questionnaire_assets"]) == {
        "sagat_suas_en.yaml", "sagat_suas_es.yaml", "isa_suas_en.txt",
        "isa_suas_es.txt", "nasatlx_en.txt", "nasatlx_es.txt",
        "bedford_en.txt", "bedford_es.txt",
    }
    assert "sagat_generic_en.txt" in manifest["legacy_questionnaire_assets"]
