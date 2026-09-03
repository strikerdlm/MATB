"""Tests for plugins.communications - SDT and radio logic."""

import json
from pathlib import Path
from string import ascii_lowercase, digits
from unittest.mock import MagicMock, patch

import pytest

from plugins.communications import Communications
from core.event import Event


def _make_comms_with_radios():
    """Create a minimal Communications object for testing radio helper methods."""
    c = object.__new__(Communications)
    c.alias = "communications"
    c.parameters = {
        "automaticsolver": False,
        "taskupdatetime": 80,
        "maxresponsedelay": 6000,
        "radios": {
            0: {
                "name": "NAV_1",
                "currentfreq": 110.0,
                "targetfreq": None,
                "pos": 0,
                "response_time": 0,
                "is_active": True,
                "is_prompting": False,
                "_feedbacktimer": None,
                "_feedbacktype": None,
            },
            1: {
                "name": "NAV_2",
                "currentfreq": 120.0,
                "targetfreq": None,
                "pos": 1,
                "response_time": 0,
                "is_active": False,
                "is_prompting": False,
                "_feedbacktimer": None,
                "_feedbacktype": None,
            },
            2: {
                "name": "COM_1",
                "currentfreq": 125.0,
                "targetfreq": 130.0,
                "pos": 2,
                "response_time": 500,
                "is_active": False,
                "is_prompting": False,
                "_feedbacktimer": None,
                "_feedbacktype": None,
            },
            3: {
                "name": "COM_2",
                "currentfreq": 130.0,
                "targetfreq": None,
                "pos": 3,
                "response_time": 0,
                "is_active": False,
                "is_prompting": False,
                "_feedbacktimer": None,
                "_feedbacktype": None,
            },
        },
    }
    c.scenario_time = 0.5
    c.logger = MagicMock()
    return c


class TestGetSDTValue:
    """Test Signal Detection Theory classification - entirely pure function."""

    def _get_sdt(self):
        c = object.__new__(Communications)
        return c.get_sdt_value

    def test_hit(self):
        """Response to signal on correct radio → HIT."""
        sdt = self._get_sdt()
        assert sdt(response_needed=True, was_a_radio_responded=True, correct_radio=True, response_deviation=0) == "HIT"

    def test_miss(self):
        """No response to signal → MISS."""
        sdt = self._get_sdt()
        assert (
            sdt(response_needed=True, was_a_radio_responded=False, correct_radio=False, response_deviation=0) == "MISS"
        )

    def test_false_alarm(self):
        """Response when no signal → FA."""
        sdt = self._get_sdt()
        assert sdt(response_needed=False, was_a_radio_responded=True, correct_radio=True, response_deviation=0) == "FA"

    def test_bad_radio(self):
        """Response on wrong radio → BAD_RADIO."""
        sdt = self._get_sdt()
        assert (
            sdt(response_needed=True, was_a_radio_responded=True, correct_radio=False, response_deviation=0)
            == "BAD_RADIO"
        )

    def test_bad_freq(self):
        """Correct radio but wrong frequency → BAD_FREQ."""
        sdt = self._get_sdt()
        assert (
            sdt(response_needed=True, was_a_radio_responded=True, correct_radio=True, response_deviation=0.5)
            == "BAD_FREQ"
        )

    def test_bad_radio_freq(self):
        """Wrong radio and wrong frequency → BAD_RADIO_FREQ."""
        sdt = self._get_sdt()
        assert (
            sdt(response_needed=True, was_a_radio_responded=True, correct_radio=False, response_deviation=0.5)
            == "BAD_RADIO_FREQ"
        )


class TestRadioHelpers:
    def test_get_target_radios(self):
        """Returns only radios with a target frequency."""
        c = _make_comms_with_radios()
        targets = c.get_target_radios_list()
        assert len(targets) == 1
        assert targets[0]["name"] == "COM_1"

    def test_get_non_target_radios(self):
        """Returns radios without a target frequency."""
        c = _make_comms_with_radios()
        non_targets = c.get_non_target_radios_list()
        assert len(non_targets) == 3

    def test_get_active_radio(self):
        """Returns the currently active radio."""
        c = _make_comms_with_radios()
        active = c.get_active_radio_dict()
        assert active["name"] == "NAV_1"

    def test_get_max_min_pos(self):
        """Max and min positions span the radio list."""
        c = _make_comms_with_radios()
        assert c.get_max_pos() == 3
        assert c.get_min_pos() == 0

    def test_get_response_timers(self):
        """Returns list of non-zero response timers."""
        c = _make_comms_with_radios()
        timers = c.get_response_timers()
        assert timers == [500]

    def test_get_radios_by_key_value(self):
        """Filters radios by key-value pair."""
        c = _make_comms_with_radios()
        result = c.get_radios_by_key_value("name", "NAV_1")
        assert len(result) == 1
        assert result[0]["pos"] == 0

    def test_get_radio_dict_by_pos(self):
        """Finds a radio by its position index."""
        c = _make_comms_with_radios()
        result = c.get_radio_dict_by_pos(2)
        assert result["name"] == "COM_1"

    def test_disable_radio_target(self):
        """Clears target frequency and resets timer."""
        c = _make_comms_with_radios()
        radio = c.parameters["radios"][2]
        assert radio["targetfreq"] == 130.0
        c.disable_radio_target(radio)
        assert radio["targetfreq"] is None
        assert radio["response_time"] == 0

    def test_get_waiting_response_radios(self):
        """Returns radios awaiting a response."""
        c = _make_comms_with_radios()
        # COM_1 has a target and is not prompting
        waiting = c.get_waiting_response_radios()
        assert len(waiting) == 1
        assert waiting[0]["name"] == "COM_1"


def test_scheduler_queues_same_tick_prompts_until_communications_update():
    from core.scheduler import Scheduler
    from plugins.abstractplugin import AbstractPlugin

    communications = _make_comms_with_radios()
    communications._radioprompt_queue = []
    communications._comm_opportunity_counter = 0
    communications._active_comm_opportunity = None
    communications.log_performance = MagicMock()
    communications.parameters.update({
        "radioprompt": "",
        "callsignregex": "[A-Z]",
        "taskupdatetime": 80,
        "maxresponsedelay": 20_000,
        "automaticsolver": False,
        "airbandminMhz": 108.0,
        "airbandmaxMhz": 137.0,
    })
    communications.old_regex = "[A-Z]"
    communications.can_receive_keys = False
    communications.set_sample_sounds = MagicMock()
    communications._handle_radioprompt = MagicMock()
    communications.get_target_radios_list = MagicMock(return_value=[])
    communications.refresh_widgets = MagicMock()
    communications.update_can_receive_key = MagicMock()

    scheduler = object.__new__(Scheduler)
    scheduler.plugins = {"communications": communications}
    event_logger = MagicMock()
    with patch("core.scheduler.get_logger", return_value=event_logger):
        scheduler.execute_one_event(
            Event(1, 5, "communications", ["radioprompt", "own"])
        )
        scheduler.execute_one_event(
            Event(2, 5, "communications", ["radioprompt", "other"])
        )

    with patch.object(AbstractPlugin, "compute_next_plugin_state", return_value=True):
        communications.update(5.0)

    assert [call.args[0] for call in communications._handle_radioprompt.call_args_list] == ["own"]
    lifecycle_payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert [payload["phase"] for payload in lifecycle_payloads] == ["opened", "invalidated"]
    assert lifecycle_payloads[-1]["reason"] == "multiple_prompts_dispatched_in_one_update"
    assert communications._radioprompt_queue == []


def test_audio_failure_invalidates_opportunity_before_target_assignment():
    communications = _make_comms_with_radios()
    communications.parameters.update({
        "owncallsign": "ABC123",
        "airbandminvariationMhz": 5,
        "airbandmaxvariationMhz": 6,
        "radioprompt": "own",
    })
    communications.scenario_time = 1.0
    communications.logger = MagicMock()
    communications.log_performance = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("own")
    communications._active_comm_opportunity = opportunity
    communications.get_rand_frequency = MagicMock(return_value=115.5)
    communications.group_audio_files = MagicMock(side_effect=RuntimeError("bad wav"))

    presented = communications.prompt_for_a_new_target("own", "NAV_1", opportunity)

    assert presented is False
    assert communications.parameters["radios"][0]["targetfreq"] is None
    assert communications._active_comm_opportunity is None
    payloads = [json.loads(call.args[1]) for call in communications.log_performance.call_args_list]
    assert [payload["phase"] for payload in payloads] == ["opened", "invalidated"]
    assert payloads[-1]["reason"] == "presentation_failed"


def test_stop_invalidates_an_open_comm_opportunity():
    from plugins.abstractplugin import AbstractPlugin

    communications = _make_comms_with_radios()
    communications.log_performance = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("own")
    opportunity["radio"] = communications.parameters["radios"][2]
    communications._active_comm_opportunity = opportunity

    with patch.object(AbstractPlugin, "stop") as parent_stop:
        communications.stop()

    assert communications.parameters["radios"][2]["targetfreq"] is None
    assert communications._active_comm_opportunity is None
    payloads = [json.loads(call.args[1]) for call in communications.log_performance.call_args_list]
    assert [payload["phase"] for payload in payloads] == ["opened", "invalidated"]
    parent_stop.assert_called_once_with()


def test_stop_invalidates_queued_prompt_and_stops_audio_backend():
    from plugins.abstractplugin import AbstractPlugin

    communications = _make_comms_with_radios()
    communications.log_performance = MagicMock()
    communications._radioprompt_queue = ["own"]
    communications._comm_opportunity_counter = 0
    communications._active_comm_opportunity = None
    communications.player = MagicMock()

    with patch.object(AbstractPlugin, "stop") as parent_stop:
        communications.stop()

    payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert [payload["phase"] for payload in payloads] == ["opened", "invalidated"]
    assert payloads[-1]["reason"] == "task_stopped_before_presentation"
    assert communications._radioprompt_queue == []
    communications.player.pause.assert_called_once_with()
    communications.player.delete.assert_called_once_with()
    parent_stop.assert_called_once_with()


def test_stop_closes_parent_lifecycle_even_when_audio_cleanup_fails():
    from plugins.abstractplugin import AbstractPlugin

    communications = _make_comms_with_radios()
    communications.log_performance = MagicMock()
    communications._radioprompt_queue = []
    communications._active_comm_opportunity = None
    communications.player = MagicMock()
    communications.player.pause.side_effect = RuntimeError("device lost")

    with patch.object(AbstractPlugin, "stop") as parent_stop, pytest.raises(
        RuntimeError, match="audio backend cleanup"
    ):
        communications.stop()

    communications.player.delete.assert_called_once_with()
    parent_stop.assert_called_once_with()


def test_late_prompt_dispatch_is_rejected_before_it_can_enter_the_queue():
    communications = _make_comms_with_radios()
    communications.log_performance = MagicMock()
    communications._radioprompt_queue = []
    communications._comm_opportunity_counter = 0
    communications.scenario_time = 2.0
    communications.parameters["radioprompt"] = ""
    communications._scenario_dispatch_context = {
        "scheduled_time_s": 1.0,
        "source_line": 7,
    }

    communications.set_parameter("radioprompt", "own")

    payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert communications._radioprompt_queue == []
    assert [payload["phase"] for payload in payloads] == ["opened", "invalidated"]
    assert payloads[-1]["reason"] == "prompt_command_dispatched_after_observable_onset"


def test_incorrect_target_response_closes_valid_signal_trial_as_miss():
    communications = _make_comms_with_radios()
    communications.parameters["radios"][2]["is_active"] = True
    communications.parameters["radios"][0]["is_active"] = False
    communications.parameters["radios"][2]["currentfreq"] = 129.5
    communications.log_performance = MagicMock()
    communications.set_feedback = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("own")
    opportunity.update({
        "presentation_started": True,
        "response_window_open": True,
        "response_window_opened_scenario_time_s": 0.0,
        "response_deadline_s": 6.0,
        "radio": communications.parameters["radios"][2],
    })
    communications._active_comm_opportunity = opportunity

    communications.confirm_response()

    payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert payloads[-1]["phase"] == "closed"
    assert payloads[-1]["outcome"] == "MISS"
    assert payloads[-1]["response_classification"] == "BAD_FREQ"


def test_automatic_comm_response_is_explicitly_attributed():
    communications = _make_comms_with_radios()
    communications.parameters["automaticsolver"] = True
    communications.log_performance = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("own")
    communications._active_comm_opportunity = opportunity

    communications._close_active_opportunity(
        "HIT", 400.0, response_actor="automation"
    )

    payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert payloads[0]["automation_active"] is True
    assert payloads[-1]["automation_active"] is True
    assert payloads[-1]["response_actor"] == "automation"


def test_other_prompt_false_alarm_uses_opportunity_timer_and_round_trips(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from matb_integration.log_converter import _comm_metrics

    communications = _make_comms_with_radios()
    # This test starts from a clean non-signal trial, not the helper's target.
    communications.parameters["radios"][2]["targetfreq"] = None
    communications.parameters.update({"taskupdatetime": 80, "maxresponsedelay": 20_000})
    communications.log_performance = MagicMock()
    communications.logger = MagicMock()
    communications.set_feedback = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("other")
    opportunity.update({
        "presentation_started": True,
        "response_window_open": True,
        "response_time_ms": 240,
        "response_window_opened_scenario_time_s": 0.0,
        "response_deadline_s": 20.0,
    })
    communications.scenario_time = 0.24
    communications._log_opportunity(
        opportunity,
        "presentation_started",
        software_play_invoked=True,
        physical_onset_measured=False,
    )
    communications._log_opportunity(opportunity, "response_window_opened")
    communications._active_comm_opportunity = opportunity

    communications.confirm_response()

    rows = [
        {
            "type": "performance",
            "module": "communications",
            "address": call.args[0],
            "value": str(call.args[1]),
        }
        for call in communications.log_performance.call_args_list
    ]
    payloads = [
        json.loads(row["value"])
        for row in rows
        if row["address"] == "comm_opportunity_v1"
    ]
    assert payloads[-1]["outcome"] == "FA"
    assert payloads[-1]["response_time_ms"] == 240.0

    metrics = _comm_metrics(rows, expected_opportunities=1)
    assert metrics["observed_opportunity_status"] == "complete"
    assert metrics["n_false_alarms"] == 1
    assert metrics["mean_rt_ms"] == 240.0


def test_comm_response_time_uses_scenario_clock_after_a_frame_stall():
    communications = _make_comms_with_radios()
    communications.parameters.update({"taskupdatetime": 80, "maxresponsedelay": 20_000})
    communications.parameters["radios"][2]["targetfreq"] = None
    communications.log_performance = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("other")
    opportunity.update({
        "presentation_started": True,
        "response_window_open": True,
        "response_window_opened_scenario_time_s": 10.0,
        "response_deadline_s": 30.0,
    })
    communications._active_comm_opportunity = opportunity
    communications.scenario_time = 11.0

    communications._update_active_response_timing()

    assert opportunity["response_time_ms"] == 1000


def test_comm_response_window_stall_invalidates_corrected_lifecycle():
    communications = _make_comms_with_radios()
    communications.parameters.update({"taskupdatetime": 80, "maxresponsedelay": 20_000})
    communications.parameters["radios"][2]["targetfreq"] = None
    communications.log_performance = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("other")
    opportunity.update({
        "presentation_started": True,
        "response_window_open": True,
        "response_window_opened_scenario_time_s": 10.0,
        "response_deadline_s": 30.0,
    })
    communications._active_comm_opportunity = opportunity
    communications.scenario_time = 31.0

    communications._update_active_response_timing()

    payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert payloads[-1]["phase"] == "invalidated"
    assert payloads[-1]["reason"] == "response_window_closed_after_update_stall"
    assert payloads[-1]["lateness_ms"] == 1000
    assert communications._active_comm_opportunity is None


def test_delayed_audio_completion_invalidates_before_response_window_opens():
    communications = _make_comms_with_radios()
    communications.parameters.update({"taskupdatetime": 80, "maxresponsedelay": 20_000})
    communications.log_performance = MagicMock()
    communications.logger = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("other")
    opportunity.update({
        "presentation_started": True,
        "presentation_started_scenario_time_s": 2.0,
        "presentation_expected_end_scenario_time_s": 12.0,
    })
    communications._active_comm_opportunity = opportunity
    communications.player = MagicMock(source=None)
    communications.scenario_time = 13.0

    communications._complete_presentation_if_ready()

    payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert payloads[-1]["phase"] == "invalidated"
    assert payloads[-1]["reason"] == "response_window_opened_after_update_stall"
    assert payloads[-1]["lateness_ms"] == 1000
    assert communications._active_comm_opportunity is None


def test_early_audio_source_disappearance_invalidates_instead_of_opening_window():
    communications = _make_comms_with_radios()
    communications.parameters.update({"taskupdatetime": 80, "maxresponsedelay": 20_000})
    communications.log_performance = MagicMock()
    communications.logger = MagicMock()
    communications._comm_opportunity_counter = 0
    opportunity = communications._new_opportunity("other")
    opportunity.update({
        "presentation_started": True,
        "presentation_started_scenario_time_s": 2.0,
        "presentation_expected_end_scenario_time_s": 12.0,
    })
    communications._active_comm_opportunity = opportunity
    communications.player = MagicMock(source=None)
    communications.scenario_time = 10.0

    communications._complete_presentation_if_ready()

    payloads = [
        json.loads(call.args[1])
        for call in communications.log_performance.call_args_list
        if call.args[0] == "comm_opportunity_v1"
    ]
    assert payloads[-1]["phase"] == "invalidated"
    assert payloads[-1]["reason"] == "presentation_completed_before_expected_duration"
    assert communications._active_comm_opportunity is None


def _make_comms_for_voice():
    """Create a minimal Communications object for testing voice/sound methods."""
    c = object.__new__(Communications)
    c.alias = "communications"
    c.parameters = {
        "voiceidiom": "french",
        "voicegender": "female",
        "promptlist": ["NAV_1", "NAV_2", "COM_1", "COM_2"],
    }
    c.sound_path = None
    c.logger = MagicMock()
    return c


class TestVoiceSwitching:
    """Test voice language/gender switching logic."""

    def test_get_sounds_path_uses_current_parameters(self):
        """get_sounds_path() reflects current voicegender/voiceidiom values."""
        from core.constants import PATHS as P

        c = _make_comms_for_voice()
        result = c.get_sounds_path()
        assert result == P["SOUNDS"] / "french" / "female"

        c.parameters["voiceidiom"] = "english"
        c.parameters["voicegender"] = "male"
        result = c.get_sounds_path()
        assert result == P["SOUNDS"] / "english" / "male"

    def test_set_sample_sounds_updates_path_on_change(self, tmp_path):
        """set_sample_sounds() updates sound_path when parameters change."""
        c = _make_comms_for_voice()
        # Create a fake sounds directory with the expected wav files
        voice_dir = tmp_path / "french" / "female"
        voice_dir.mkdir(parents=True)
        expected_names = (
            [s for s in digits + ascii_lowercase]
            + [r.lower() for r in c.parameters["promptlist"]]
            + ["radio", "point", "frequency", "empty"]
        )
        for name in expected_names:
            (voice_dir / f"{name}.wav").touch()

        with patch.object(Communications, "get_sounds_path", return_value=voice_dir):
            c.set_sample_sounds()

        assert c.sound_path == voice_dir
        assert len(c.samples_path) == len(expected_names)

    def test_set_sample_sounds_skips_when_unchanged(self):
        """set_sample_sounds() is a no-op when path hasn't changed."""
        c = _make_comms_for_voice()
        fake_path = Path("/fake/french/female")
        c.sound_path = fake_path

        with patch.object(Communications, "get_sounds_path", return_value=fake_path):
            c.set_sample_sounds()

        # sound_path should remain the same, no samples_path attribute set
        assert c.sound_path == fake_path
        assert not hasattr(c, "samples_path")

    def test_set_sample_sounds_skips_invalid_path(self, tmp_path):
        """set_sample_sounds() warns and bails for non-existent idiom/gender combo."""
        c = _make_comms_for_voice()
        nonexistent = tmp_path / "english" / "female"  # Does not exist

        with patch.object(Communications, "get_sounds_path", return_value=nonexistent):
            c.set_sample_sounds()

        # sound_path should NOT be updated
        assert c.sound_path is None
        c.logger.log_manual_entry.assert_called_once()
        logged_msg = c.logger.log_manual_entry.call_args[0][0]
        assert "Warning" in logged_msg
        assert "does not exist" in logged_msg

    def test_prompt_sound_ids_prefer_contextual_radio_fragment(self, tmp_path):
        c = _make_comms_for_voice()
        c.sound_path = tmp_path
        (tmp_path / "com_1_frequency.wav").touch()

        sound_ids = c._prompt_sound_ids("AB1", "COM_1", 123.4)

        assert sound_ids == (
            ["empty"] * 20
            + ["a", "b", "1", "a", "b", "1"]
            + ["com_1_frequency"]
            + ["1", "2", "3", "point", "4", "empty"]
        )

    def test_prompt_sound_ids_retain_legacy_fragment_fallback(self, tmp_path):
        c = _make_comms_for_voice()
        c.sound_path = tmp_path

        sound_ids = c._prompt_sound_ids("AB1", "COM_1", 123.4)

        assert sound_ids[26:29] == ["radio", "com_1", "frequency"]
