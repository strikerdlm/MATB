from matb_integration.suas.domain.commands import AssignSector, ClassifyContact, CommandStatus, Hold
from matb_integration.suas.domain.enums import ContactEvidence, ContactWorkflow
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


def test_invalid_runtime_enum_value_is_rejected_not_raised(loaded_scenario) -> None:
    engine = SimulationEngine(loaded_scenario.definition, "LOW")
    contact = engine._state.contacts["C-01"]
    contact.evidence = ContactEvidence.INSPECTABLE
    contact.workflow = ContactWorkflow.INSPECTED
    result = engine.step([envelope(
        "bad-class", expected=0, command=ClassifyContact("C-01", "not-an-enum"),  # type: ignore[arg-type]
    )]).command_results[0]
    assert result.status is CommandStatus.REJECTED
    assert result.code == "invalid_command_value"
