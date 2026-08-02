from matb_integration.suas.domain.commands import AssignSector, CommandStatus, Hold
from matb_integration.suas.engine.runtime import SimulationEngine
from .helpers import envelope


def test_command_applies_at_next_tick_and_rejects_stale_version(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    first = engine.step([envelope("cmd-1", expected=0, command=AssignSector("UAS-01", "sector_alpha"))])
    assert first.command_results[0].status is CommandStatus.ACCEPTED
    assert first.command_results[0].applied_tick == 1
    second = engine.step([envelope("cmd-2", expected=0, command=Hold("UAS-01"))])
    assert second.command_results[0].code == "stale_state_version"


def test_duplicate_returns_first_result_without_another_epoch(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    command = envelope("same", expected=0, command=Hold("UAS-01"))
    first = engine.step([command]).command_results[0]
    version = engine.snapshot()["state_version"]
    duplicate = engine.step([command]).command_results[0]
    assert duplicate.status is CommandStatus.DUPLICATE
    assert duplicate.code == first.code
    assert engine.snapshot()["state_version"] == version
