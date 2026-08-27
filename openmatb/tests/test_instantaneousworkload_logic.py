from __future__ import annotations

from unittest.mock import MagicMock

from plugins.instantaneousworkload import Instantaneousworkload


def _make_prompt() -> Instantaneousworkload:
    plugin = object.__new__(Instantaneousworkload)
    plugin.alias = "instantaneousworkload"
    plugin.alive = False
    plugin.paused = True
    plugin.visible = False
    plugin.can_receive_keys = True
    plugin.can_execute_keys = True
    plugin.keys = {str(value) for value in range(10)}
    plugin.widgets = {}
    plugin.logger = MagicMock(event_sequence=10)
    plugin.scenario_time = 15.0
    plugin._research_trial_counter = 0
    plugin.parameters = {
        "minimum": 1,
        "maximum": 10,
        "timeoutms": 10_000,
        "taskupdatetime": 50,
    }
    plugin.filter_key = lambda key: key
    plugin.create_widgets = MagicMock()
    plugin.show = MagicMock()
    plugin.resume = MagicMock()
    plugin.hide = MagicMock()
    plugin.pause = MagicMock()
    return plugin


def test_prompt_is_nonblocking_and_reports_pending_state() -> None:
    plugin = _make_prompt()

    plugin.start()

    assert plugin.blocking is False
    assert plugin.get_research_state() == {
        "workload_alive": True,
        "load_workload": True,
        "workload_prompt_id": "workload-000001",
    }


def test_digit_zero_maps_to_isa_ten_and_records_latency() -> None:
    plugin = _make_prompt()
    plugin.start()
    plugin.scenario_time = 16.2
    plugin.logger.event_sequence = 14

    plugin.do_on_key("0", "press", False)

    trial = plugin.logger.record_research_trial.call_args.args[0]
    assert trial["raw_value"] == 10.0
    assert trial["raw_unit"] == "ISA_1_to_10"
    assert trial["rt_ms"] == 1_200.0
    assert trial["outcome"] == "response"
    assert trial["correct"] is None
    assert plugin.alive is False


def test_prompt_timeout_is_a_structured_trial_without_a_value() -> None:
    plugin = _make_prompt()
    plugin.start()
    plugin.scenario_time = 25.0

    plugin._finish(value=None, timeout=True)

    trial = plugin.logger.record_research_trial.call_args.args[0]
    assert trial["raw_value"] is None
    assert trial["response_s"] is None
    assert trial["outcome"] == "timeout"
    assert trial["timeout"] is True
    assert plugin.alive is False
