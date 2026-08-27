from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.logger import Logger
from core.scheduler import Scheduler
from plugins.abstractplugin import AbstractPlugin
from plugins.communications import Communications
from plugins.resman import Resman
from plugins.sysmon import Sysmon
from plugins.track import Track


def test_abstract_plugin_exposes_schema_ready_lifecycle_and_automation_state() -> None:
    plugin = object.__new__(AbstractPlugin)
    plugin.alias = "track"
    plugin.alive = True
    plugin.paused = False
    plugin.parameters = {"automaticsolver": True}

    assert plugin.get_research_state() == {
        "tracking_alive": True,
        "automation_tracking": True,
    }


def test_uninstrumented_plugin_does_not_emit_unknown_sample_columns() -> None:
    plugin = object.__new__(AbstractPlugin)
    plugin.alias = "instructions"
    plugin.alive = True
    plugin.parameters = {}

    assert plugin.get_research_state() == {}


def test_tracking_snapshot_reports_raw_deviation_and_normalized_cursor() -> None:
    plugin = object.__new__(Track)
    plugin.alias = "track"
    plugin.alive = True
    plugin.parameters = {"automaticsolver": False}
    plugin.reticle = MagicMock()
    plugin.reticle.container.w = 200
    plugin.reticle.container.h = 100
    plugin.reticle.cursor_relative = (50, -25)
    plugin.reticle.return_deviation.return_value = 55.9
    plugin.reticle.is_cursor_in_target.return_value = False

    assert plugin.get_research_state() == {
        "tracking_alive": True,
        "automation_tracking": False,
        "tracking_cursor_x": 0.5,
        "tracking_cursor_y": -0.5,
        "tracking_deviation": 55.9,
        "tracking_in_target": False,
    }


def test_resman_snapshot_reports_target_tanks_and_all_pump_states() -> None:
    plugin = object.__new__(Resman)
    plugin.alias = "resman"
    plugin.alive = True
    plugin.parameters = {
        "automaticsolver": True,
        "toleranceradius": 250,
        "tank": {
            "a": {"level": 2200, "target": 2500, "_is_in_tolerance": False},
            "b": {"level": 2600, "target": 2500, "_is_in_tolerance": True},
        },
        "pump": {"1": {"state": "on"}, "2": {"state": "failure"}},
    }

    assert plugin.get_research_state() == {
        "resman_alive": True,
        "automation_resman": True,
        "tank_a_level": 2200.0,
        "tank_a_target": 2500.0,
        "tank_a_deviation": -300.0,
        "tank_a_in_tolerance": False,
        "tank_b_level": 2600.0,
        "tank_b_target": 2500.0,
        "tank_b_deviation": 100.0,
        "tank_b_in_tolerance": True,
        "pump_states_json": {"1": "on", "2": "failure"},
    }


def test_sysmon_snapshot_exposes_stable_pending_alert_ids() -> None:
    plugin = object.__new__(Sysmon)
    plugin.alias = "sysmon"
    plugin.alive = True
    plugin.parameters = {
        "automaticsolver": False,
        "scales": {"1": {"_onfailure": True, "_research_trial_id": "sysmon-000001"}},
        "lights": {"1": {"_onfailure": False}},
    }

    assert plugin.get_research_state() == {
        "sysmon_alive": True,
        "automation_sysmon": False,
        "load_sysmon": True,
        "sysmon_pending_ids_json": ["sysmon-000001"],
    }


def test_communications_snapshot_exposes_stable_pending_prompt_ids() -> None:
    plugin = object.__new__(Communications)
    plugin.alias = "communications"
    plugin.alive = True
    plugin.parameters = {
        "automaticsolver": False,
        "radios": {
            0: {"targetfreq": 121.5, "is_prompting": False, "_research_trial_id": "communications-000007"},
            1: {"targetfreq": None, "is_prompting": False},
        },
    }

    assert plugin.get_research_state() == {
        "communications_alive": True,
        "automation_communications": False,
        "load_communications": True,
        "communications_pending_ids_json": ["communications-000007"],
    }


def test_scheduler_forwards_one_merged_observation_to_research_recorder() -> None:
    scheduler = object.__new__(Scheduler)
    scheduler.research_recorder = MagicMock()
    scheduler.scenario_time = 4.5
    scheduler.pause_scenario_time = False
    scheduler.plugins = {
        "sysmon": MagicMock(get_research_state=MagicMock(return_value={
            "sysmon_alive": True,
            "automation_sysmon": False,
            "load_sysmon": True,
        })),
        "communications": MagicMock(get_research_state=MagicMock(return_value={
            "communications_alive": True,
            "automation_communications": False,
            "load_communications": True,
        })),
    }

    with patch("core.scheduler.perf_counter_ns", return_value=123_000_000), patch(
        "core.scheduler.get_logger"
    ) as logger:
        logger.return_value.event_sequence = 7
        scheduler._record_research_sample()

    scheduler.research_recorder.maybe_sample.assert_called_once_with(
        monotonic_ns=123_000_000,
        scenario_time_s=4.5,
        scenario_paused=False,
        event_sequence=7,
        state={
            "sysmon_alive": True,
            "automation_sysmon": False,
            "load_sysmon": True,
            "communications_alive": True,
            "automation_communications": False,
            "load_communications": True,
            "load_workload": False,
            "discrete_load_count": 2,
        },
    )


def test_logger_forwards_structured_trial_without_changing_legacy_row_schema() -> None:
    logger = object.__new__(Logger)
    logger.research_recorder = MagicMock()
    logger.fields_list = ["logtime", "scenario_time", "type", "module", "address", "value"]
    trial = {"trial_id": "sysmon-000001", "task": "sysmon"}

    logger.record_research_trial(trial)

    logger.research_recorder.record_trial.assert_called_once_with(trial)
    assert logger.fields_list == ["logtime", "scenario_time", "type", "module", "address", "value"]


def test_logger_structured_trial_is_safe_when_research_recording_is_disabled() -> None:
    logger = object.__new__(Logger)
    logger.research_recorder = None

    logger.record_research_trial({"trial_id": "ignored"})


def test_logger_sequence_counts_written_legacy_rows() -> None:
    logger = object.__new__(Logger)
    logger.slot = lambda *values: values
    logger.queue = []
    logger.event_sequence = 0
    logger.write_row_queue = MagicMock()

    logger.write_single_slot([1.0, 0.0, "event", "track", "self", "start"])

    assert logger.event_sequence == 1


def test_runtime_factory_discovers_scenario_manifest_and_preserves_legacy_path(tmp_path: Path) -> None:
    from core.research import create_research_recorder

    scenario = tmp_path / "low.txt"
    scenario.write_text("0:00:00;track;start\n", encoding="utf-8")
    scenario.with_suffix(".txt.manifest.json").write_text(
        json.dumps({
            "manifest_version": 1,
            "seed": 42,
            "parameters": {"scientific_scoring": {"tracking_range": 100.0}},
        }),
        encoding="utf-8",
    )
    legacy = tmp_path / "4_260826_120000.csv"
    logger = MagicMock(path=legacy, session_id=4)

    recorder = create_research_recorder(
        logger=logger,
        scenario_path=scenario,
        enabled=True,
        sample_hz=20.0,
        start_monotonic_ns=100,
        start_utc_ns=200,
    )

    assert recorder is not None
    assert recorder.run_dir == tmp_path / "4_260826_120000.research"
    manifest = json.loads((recorder.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["scenario"]["filename"] == "low.txt"
    assert manifest["source"]["scenario_manifest"]["seed"] == 42
    assert manifest["score_configuration"] == {"tracking_range": 100.0}
    assert logger.path == legacy
    recorder._close_streams()


def test_runtime_factory_returns_none_when_disabled(tmp_path: Path) -> None:
    from core.research import create_research_recorder

    logger = MagicMock(path=tmp_path / "legacy.csv", session_id=5)

    assert create_research_recorder(
        logger=logger,
        scenario_path=None,
        enabled=False,
        sample_hz=20.0,
        start_monotonic_ns=0,
        start_utc_ns=0,
    ) is None


def test_scheduler_seals_research_recorder_and_detaches_logger(tmp_path: Path) -> None:
    scheduler = object.__new__(Scheduler)
    recorder = MagicMock()
    scheduler.research_recorder = recorder
    legacy = tmp_path / "legacy.csv"
    logger = MagicMock(path=legacy, research_recorder=recorder)

    with patch("core.scheduler.get_logger", return_value=logger):
        scheduler._seal_research(status="partial", reason="window_closed")

    recorder.seal.assert_called_once_with(
        events_csv=legacy,
        status="partial",
        reason="window_closed",
    )
    assert logger.research_recorder is None
    assert scheduler.research_recorder is None


def test_window_close_routes_through_reasoned_partial_exit() -> None:
    scheduler = object.__new__(Scheduler)
    scheduler.plugins = {}
    scheduler.events_queue = [MagicMock()]
    scheduler.scenario_time = 30.0
    scheduler._seal_research = MagicMock()
    scheduler.exit = MagicMock()

    with patch("core.scheduler.Window.MainWindow", MagicMock(alive=False)):
        scheduler.check_if_must_exit()

    scheduler._seal_research.assert_not_called()
    scheduler.exit.assert_called_once_with(
        completed=False,
        reason="window_closed",
    )


def test_research_sampling_failure_does_not_abort_task_loop() -> None:
    scheduler = object.__new__(Scheduler)
    scheduler.research_recorder = MagicMock()
    scheduler.research_recorder.maybe_sample.side_effect = RuntimeError("disk full")
    scheduler.plugins = {}
    scheduler.scenario_time = 5.0
    scheduler.pause_scenario_time = False
    scheduler._seal_research = MagicMock()

    with patch("core.scheduler.get_logger") as logger:
        logger.return_value.event_sequence = 2
        scheduler._record_research_sample()

    scheduler._seal_research.assert_called_once_with(
        status="partial",
        reason="recording_error:RuntimeError",
    )
    logger.return_value.log_manual_entry.assert_called_once()
