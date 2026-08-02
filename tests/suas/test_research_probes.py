from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from matb_integration.suas.adapters.synthetic import SyntheticVehicleBackend
from matb_integration.suas.domain.enums import AircraftMode, LinkState, Locale
from matb_integration.suas.research.probes import (
    load_suas_probe_bank,
    render_probe,
)


@pytest.fixture
def private_freeze_state(loaded_scenario):
    scenario = loaded_scenario.definition
    state = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["MEDIUM"])
    state.aircraft["UAS-02"].link = LinkState.LOST
    for aircraft_id, margin in {
        "UAS-01": 8_000,
        "UAS-02": 6_000,
        "UAS-03": 1_000,
        "UAS-04": 4_000,
    }.items():
        aircraft = state.aircraft[aircraft_id]
        aircraft.mode = AircraftMode.SEARCH
        aircraft.energy_units = 50_000
        aircraft.predicted_home_reserve_units = 50_000 - margin
    return state


def test_dynamic_probe_answer_comes_from_freeze_state(private_freeze_state) -> None:
    template = load_suas_probe_bank(Locale.EN)["suas_l1_lost_links"]
    rendered = render_probe(template, private_freeze_state)

    assert rendered.options == (
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "Unknown",
    )
    assert rendered.correct_answer == "1"
    assert "truth" not in rendered.to_public_dict()
    assert "correct_answer" not in rendered.to_public_dict()


def test_projection_probe_uses_current_energy_and_routes(private_freeze_state) -> None:
    rendered = render_probe(
        load_suas_probe_bank(Locale.EN)["suas_l3_reserve_first"],
        private_freeze_state,
    )

    assert rendered.correct_answer == "UAS-03"
    assert rendered.unscorable_reason is None


def test_unsupported_projection_is_explicitly_unscorable(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    state = SyntheticVehicleBackend().initialize(scenario, scenario.blocks["PRACTICE"])

    rendered = render_probe(
        load_suas_probe_bank(Locale.ES_CO)["suas_l3_next_sector"], state,
    )

    assert rendered.correct_answer == "No sé"
    assert rendered.unscorable_reason
    assert rendered.correct_answer in rendered.options


def test_bilingual_probe_banks_have_strict_matching_contracts() -> None:
    english = load_suas_probe_bank(Locale.EN)
    spanish = load_suas_probe_bank(Locale.ES_CO)

    assert set(english) == set(spanish)
    assert len(english) == 9
    assert [sum(item.sa_level == level for item in english.values()) for level in (1, 2, 3)] == [3, 3, 3]
    for probe_id in english:
        assert english[probe_id].answer_evaluator == spanish[probe_id].answer_evaluator
        assert english[probe_id].option_source == spanish[probe_id].option_source


def test_probe_bank_rejects_unknown_row_key(tmp_path: Path) -> None:
    source = Path("matb_integration/questionnaires")
    for name in ("sagat_suas_en.yaml", "sagat_suas_es.yaml"):
        document = yaml.safe_load((source / name).read_text(encoding="utf-8"))
        if name.endswith("_en.yaml"):
            document["probes"][0]["truth"] = "1"
        (tmp_path / name).write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8",
        )

    with pytest.raises(ValueError, match="unknown keys"):
        load_suas_probe_bank(Locale.EN, questionnaire_dir=tmp_path)


def test_probe_bank_rejects_boolean_integer_fields(tmp_path: Path) -> None:
    source = Path("matb_integration/questionnaires")
    for name in ("sagat_suas_en.yaml", "sagat_suas_es.yaml"):
        document = yaml.safe_load((source / name).read_text(encoding="utf-8"))
        if name.endswith("_en.yaml"):
            document["format_version"] = True
        (tmp_path / name).write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8",
        )

    with pytest.raises(ValueError, match="format"):
        load_suas_probe_bank(Locale.EN, questionnaire_dir=tmp_path)


def test_reference_blocks_render_only_declared_options(loaded_scenario) -> None:
    scenario = loaded_scenario.definition
    for locale in Locale:
        bank = load_suas_probe_bank(locale)
        for block in scenario.blocks.values():
            state = SyntheticVehicleBackend().initialize(scenario, block)
            for probe_id in block.sagat.probe_ids:
                rendered = render_probe(bank[probe_id], state)
                assert rendered.correct_answer in rendered.options
