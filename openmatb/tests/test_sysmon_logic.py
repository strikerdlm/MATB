"""Tests for plugins.sysmon - Gauge logic, failure flow, and color changes.

Tests the actual Sysmon plugin methods (determine_light_color, start_failure,
stop_failure, etc.) using object.__new__() to bypass __init__.
"""

from unittest.mock import MagicMock, patch
import json

from core.constants import COLORS as C
from plugins.sysmon import Sysmon


def _make_sysmon(**overrides):
    """Create a Sysmon instance bypassing __init__, with realistic gauge state."""
    s = object.__new__(Sysmon)
    s.alias = "sysmon"
    s.scenario_time = 0
    s.moving_seed = 1
    s.alive = True
    s.paused = False
    s.visible = True
    s.can_receive_keys = True
    s.can_execute_keys = True
    s.keys = {"F1", "F2", "F3", "F4", "F5", "F6"}
    s.performance = {}
    s.logger = MagicMock()

    s.parameters = dict(
        taskupdatetime=200,
        alerttimeout=10000,
        automaticsolver=False,
        automaticsolverdelay=1000,
        feedbackduration=1500,
        feedbacks=dict(
            positive=dict(active=True, color=C["GREEN"]),
            negative=dict(active=True, color=C["RED"]),
        ),
        lights={
            "1": dict(
                name="F5",
                failure=False,
                default="on",
                oncolor=C["GREEN"],
                key="F5",
                on=True,
                _failuretimer=None,
                _onfailure=False,
                _milliresponsetime=0,
                _freezetimer=None,
            ),
            "2": dict(
                name="F6",
                failure=False,
                default="off",
                oncolor=C["RED"],
                key="F6",
                on=False,
                _failuretimer=None,
                _onfailure=False,
                _milliresponsetime=0,
                _freezetimer=None,
            ),
        },
        scales={
            "1": dict(
                name="F1",
                failure=False,
                side=0,
                key="F1",
                _failuretimer=None,
                _onfailure=False,
                _milliresponsetime=0,
                _freezetimer=None,
                _pos=5,
                _zone=0,
                _feedbacktimer=None,
                _feedbacktype=None,
            ),
            "2": dict(
                name="F2",
                failure=False,
                side=0,
                key="F2",
                _failuretimer=None,
                _onfailure=False,
                _milliresponsetime=0,
                _freezetimer=None,
                _pos=5,
                _zone=0,
                _feedbacktimer=None,
                _feedbacktype=None,
            ),
            "3": dict(
                name="F3",
                failure=False,
                side=0,
                key="F3",
                _failuretimer=None,
                _onfailure=False,
                _milliresponsetime=0,
                _freezetimer=None,
                _pos=5,
                _zone=0,
                _feedbacktimer=None,
                _feedbacktype=None,
            ),
            "4": dict(
                name="F4",
                failure=False,
                side=0,
                key="F4",
                _failuretimer=None,
                _onfailure=False,
                _milliresponsetime=0,
                _freezetimer=None,
                _pos=5,
                _zone=0,
                _feedbacktimer=None,
                _feedbacktype=None,
            ),
        },
    )
    s.scale_zones = {1: list(range(3)), 0: list(range(3, 8)), -1: list(range(8, 11))}
    s.__dict__.update(overrides)
    return s


# ──────────────────────────────────────────────
# determine_light_color - The actual method
# ──────────────────────────────────────────────
class TestDetermineLightColor:
    """Test the actual Sysmon.determine_light_color() method."""

    def test_light_on_returns_oncolor(self):
        """Light ON returns its configured on-color."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]  # default='on', on=True
        assert s.determine_light_color(light) == C["GREEN"]

    def test_light_off_returns_background(self):
        """Light OFF returns background color."""
        s = _make_sysmon()
        light = s.parameters["lights"]["2"]  # default='off', on=False
        assert s.determine_light_color(light) == C["BACKGROUND"]

    def test_toggled_light_changes_color(self):
        """Toggling ON->OFF changes GREEN->BACKGROUND."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        # Light 1 is default='on', so on=True → GREEN
        assert s.determine_light_color(light) == C["GREEN"]
        # Toggle off
        light["on"] = False
        assert s.determine_light_color(light) == C["BACKGROUND"]

    def test_toggled_off_light_turns_on(self):
        """Toggling OFF->ON changes BACKGROUND->RED."""
        s = _make_sysmon()
        light = s.parameters["lights"]["2"]
        # Light 2 is default='off', so on=False → BACKGROUND
        assert s.determine_light_color(light) == C["BACKGROUND"]
        # Toggle on
        light["on"] = True
        assert s.determine_light_color(light) == C["RED"]


# ──────────────────────────────────────────────
# start_failure - Full failure initiation
# ──────────────────────────────────────────────
class TestStartFailure:
    """Test the actual Sysmon.start_failure() method."""

    def test_light_default_on_turns_off(self):
        """Default-on light toggles off on failure."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]  # default='on', on=True
        light["failure"] = True
        s.start_failure(light)
        assert light["on"] is False
        assert light["_onfailure"] is True
        assert light["failure"] is False  # Consumed

    def test_on_time_command_is_rejected_if_next_update_opens_after_a_stall(self):
        s = _make_sysmon()
        s.scenario_time = 10.0
        s._scenario_dispatch_context = {
            "scheduled_time_s": 10.0,
            "dispatch_time_s": 10.0,
            "source_line": 7,
        }
        s.set_parameter("lights-1-failure", True)
        s.scenario_time = 12.0

        with patch("plugins.abstractplugin.AbstractPlugin.compute_next_plugin_state", return_value=True):
            s.compute_next_plugin_state()

        light = s.parameters["lights"]["1"]
        assert light["_onfailure"] is False
        rejected = json.loads(s.performance["opportunity"][-1])
        assert rejected["phase"] == "rejected"
        assert rejected["outcome"] == "INVALID_STALLED_WINDOW"
        assert rejected["reason"] == "target_window_opened_after_update_stall"

    def test_light_default_off_turns_on(self):
        """Default-off light toggles on on failure."""
        s = _make_sysmon()
        light = s.parameters["lights"]["2"]  # default='off', on=False
        light["failure"] = True
        s.start_failure(light)
        assert light["on"] is True
        assert light["_onfailure"] is True

    def test_scale_failure_sets_zone(self):
        """Scale failure with side=1 sets _zone to 1."""
        s = _make_sysmon()
        scale = s.parameters["scales"]["1"]
        scale["failure"] = True
        scale["side"] = 1
        s.start_failure(scale)
        assert scale["_zone"] == 1
        assert scale["_onfailure"] is True

    def test_scale_failure_negative_side(self):
        """Scale failure with side=-1 sets _zone to -1."""
        s = _make_sysmon()
        scale = s.parameters["scales"]["2"]
        scale["failure"] = True
        scale["side"] = -1
        s.start_failure(scale)
        assert scale["_zone"] == -1
        assert scale["_onfailure"] is True

    def test_failure_sets_timer(self):
        """Failure timer starts at alerttimeout value."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        assert light["_failuretimer"] == 10000  # alerttimeout

    def test_failure_timer_uses_autosolver_delay(self):
        """With autosolver, timer uses shorter delay."""
        s = _make_sysmon()
        s.parameters["automaticsolver"] = True
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        assert light["_failuretimer"] == 1000  # automaticsolverdelay

    def test_double_failure_does_not_re_toggle(self):
        """Second failure on same gauge keeps state."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        assert light["on"] is False  # Toggled from on to off
        # Second failure call on same gauge (already on failure)
        light["failure"] = True
        s.start_failure(light)
        # Still off - start_failure passes when _onfailure is already True
        assert light["on"] is False


# ──────────────────────────────────────────────
# Full color change cycle: normal → failure → recovery
# ──────────────────────────────────────────────
class TestFailureColorCycle:
    """Test the complete failure cycle with color verification."""

    def test_light_on_failure_cycle(self):
        """Light default='on': GREEN → failure → BACKGROUND → recovery → GREEN."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]  # default='on'

        # Normal state: light is ON → GREEN
        assert s.determine_light_color(light) == C["GREEN"]

        # Trigger failure
        light["failure"] = True
        s.start_failure(light)

        # During failure: light is OFF → BACKGROUND (grey)
        assert light["on"] is False
        assert s.determine_light_color(light) == C["BACKGROUND"]

        # Stop failure (successful key press)
        s.stop_failure(light, success=True)

        # After recovery: light is ON again → GREEN
        assert light["on"] is True
        assert s.determine_light_color(light) == C["GREEN"]

    def test_light_off_failure_cycle(self):
        """Light default='off': BACKGROUND → failure → RED → recovery → BACKGROUND."""
        s = _make_sysmon()
        light = s.parameters["lights"]["2"]  # default='off'

        # Normal state: light is OFF → BACKGROUND
        assert s.determine_light_color(light) == C["BACKGROUND"]

        # Trigger failure
        light["failure"] = True
        s.start_failure(light)

        # During failure: light is ON → RED (its oncolor)
        assert light["on"] is True
        assert s.determine_light_color(light) == C["RED"]

        # Stop failure
        s.stop_failure(light, success=True)

        # After recovery: light is OFF again → BACKGROUND
        assert light["on"] is False
        assert s.determine_light_color(light) == C["BACKGROUND"]


# ──────────────────────────────────────────────
# stop_failure - Full failure recovery
# ──────────────────────────────────────────────
class TestStopFailure:
    """Test the actual Sysmon.stop_failure() method."""

    def test_resets_onfailure_flag(self):
        """Recovery clears the _onfailure flag."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        s.stop_failure(light, success=True)
        assert light["_onfailure"] is False

    def test_resets_failure_timer(self):
        """Recovery clears the failure timer."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        s.stop_failure(light, success=True)
        assert light["_failuretimer"] is None

    def test_success_logs_hit(self):
        """Successful response logs HIT."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        s.stop_failure(light, success=True)
        assert "HIT" in s.performance["signal_detection"]
        opportunities = [json.loads(value) for value in s.performance["opportunity"]]
        assert opportunities[0]["phase"] == "opened"
        assert opportunities[1]["phase"] == "closed"
        assert opportunities[1]["outcome"] == "HIT"
        assert opportunities[1]["target"] is True

    def test_timeout_logs_miss(self):
        """Timeout logs MISS."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        s.stop_failure(light, success=False)
        assert "MISS" in s.performance["signal_detection"]
        opportunities = [json.loads(value) for value in s.performance["opportunity"]]
        assert opportunities[-1]["outcome"] == "MISS"

    def test_automatic_resolution_is_attributed_and_uses_its_actual_window(self):
        """Automation cannot be reported as a participant HIT or a 10 s trial."""
        s = _make_sysmon()
        s.parameters["automaticsolver"] = True
        s.parameters["automaticsolverdelay"] = 1250
        light = s.parameters["lights"]["1"]
        light["failure"] = True

        s.start_failure(light)
        s.scenario_time = 1.25
        s.stop_failure(light, success=False)

        opened, closed = [
            json.loads(value) for value in s.performance["opportunity"]
        ]
        assert opened["duration_ms"] == 1250
        assert opened["deadline_s"] == 1.25
        assert opened["allocation_actor"] == "automation"
        assert opened["automation_active"] is True
        assert closed["scheduled_deadline_s"] == opened["deadline_s"]
        assert closed["response_actor"] == "automation"
        assert closed["automation_active"] is True
        assert closed["outcome"] == "HIT"

    def test_automated_nontarget_window_is_attributed_to_automation(self):
        s = _make_sysmon()
        s.parameters["automaticsolver"] = True
        s.parameters["nontargetduration"] = 2000

        s.open_nontarget_opportunity()
        s.scenario_time = 2.0
        s.close_nontarget_opportunity()

        opened, closed = [
            json.loads(value) for value in s.performance["opportunity"]
        ]
        assert opened["automation_active"] is True
        assert opened["allocation_actor"] == "automation"
        assert closed["automation_active"] is True
        assert closed["response_actor"] == "automation"

    def test_success_sets_freeze_timer(self):
        """Success freeze timer equals feedbackduration."""
        s = _make_sysmon()
        scale = s.parameters["scales"]["1"]
        scale["failure"] = True
        scale["side"] = 1
        s.start_failure(scale)
        s.stop_failure(scale, success=True)
        assert scale["_freezetimer"] == 1500  # feedbackduration

    def test_failure_sets_negative_feedback(self):
        """Timeout sets negative feedback type."""
        s = _make_sysmon()
        scale = s.parameters["scales"]["1"]
        scale["failure"] = True
        scale["side"] = 1
        s.start_failure(scale)
        s.stop_failure(scale, success=False)
        assert scale["_feedbacktype"] == "negative"
        assert scale["_feedbacktimer"] == 1500

    def test_success_sets_positive_feedback(self):
        """Success sets positive feedback type."""
        s = _make_sysmon()
        scale = s.parameters["scales"]["1"]
        scale["failure"] = True
        scale["side"] = 1
        s.start_failure(scale)
        s.stop_failure(scale, success=True)
        assert scale["_feedbacktype"] == "positive"

    def test_light_recovery_resets_on_state(self):
        """Light returns to default on-state."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]  # default='on'
        light["failure"] = True
        s.start_failure(light)
        assert light["on"] is False
        s.stop_failure(light, success=True)
        assert light["on"] is True  # Restored to default

    def test_scale_recovery_resets_zone(self):
        """Scale zone resets to neutral (0)."""
        s = _make_sysmon()
        scale = s.parameters["scales"]["1"]
        scale["failure"] = True
        scale["side"] = 1
        s.start_failure(scale)
        assert scale["_zone"] == 1
        s.stop_failure(scale, success=True)
        assert scale["_zone"] == 0  # Reset to neutral

    def test_resets_response_time(self):
        """Recovery zeroes out response time."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        light["_milliresponsetime"] = 2000
        s.stop_failure(light, success=True)
        assert light["_milliresponsetime"] == 0


class TestNonTargetOpportunities:
    def test_stalled_batch_rejects_nontarget_when_target_dispatch_is_pending(self):
        """A late batch may not silently overlap target and non-target evidence."""
        s = _make_sysmon()
        s.parameters["nontargetduration"] = 2000
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.scenario_time = 25.0

        s.open_nontarget_opportunity()

        assert getattr(s, "_nontarget_opportunity_id", None) is None
        rejected = json.loads(s.performance["opportunity"][-1])
        assert rejected["phase"] == "rejected"
        assert rejected["outcome"] == "INVALID_COLLAPSED_BATCH"
        assert rejected["target"] is False

        with patch("plugins.abstractplugin.AbstractPlugin.compute_next_plugin_state", return_value=True):
            s.compute_next_plugin_state()
        assert light["_onfailure"] is False

    def test_same_batch_nontarget_then_target_is_rejected_symmetrically(self):
        s = _make_sysmon()
        s.parameters["nontargetduration"] = 2000
        s.scenario_time = 10.0
        s._scenario_dispatch_context = {
            "scheduled_time_s": 10.0,
            "dispatch_time_s": 10.0,
            "source_line": 1,
        }
        s.open_nontarget_opportunity()
        s._scenario_dispatch_context = {
            "scheduled_time_s": 10.0,
            "dispatch_time_s": 10.0,
            "source_line": 2,
        }

        s.set_parameter("lights-1-failure", True)

        payloads = [json.loads(value) for value in s.performance["opportunity"]]
        assert payloads[-2]["outcome"] == "INVALID_COLLAPSED_BATCH"
        assert payloads[-2]["target"] is False
        assert payloads[-1]["outcome"] == "INVALID_COLLAPSED_BATCH"
        assert payloads[-1]["target"] is True
        assert s.parameters["lights"]["1"]["failure"] is False
        assert getattr(s, "_nontarget_opportunity_id", None) is None

    def test_same_batch_target_then_nontarget_rejects_both_orders(self):
        s = _make_sysmon()
        s.parameters["nontargetduration"] = 2000
        s.scenario_time = 10.0
        s._scenario_dispatch_context = {
            "scheduled_time_s": 10.0,
            "dispatch_time_s": 10.0,
            "source_line": 1,
        }
        s.set_parameter("lights-1-failure", True)
        s._scenario_dispatch_context = {
            "scheduled_time_s": 10.0,
            "dispatch_time_s": 10.0,
            "source_line": 2,
        }

        s.open_nontarget_opportunity()

        payloads = [json.loads(value) for value in s.performance["opportunity"]]
        rejected = [item for item in payloads if item["phase"] == "rejected"]
        assert [item["target"] for item in rejected] == [True, False]
        assert all(item["outcome"] == "INVALID_COLLAPSED_BATCH" for item in rejected)
        assert s.parameters["lights"]["1"]["failure"] is False
        assert getattr(s, "_nontarget_opportunity_id", None) is None

    def test_same_batch_target_target_with_different_durations_rejects_both(self):
        s = _make_sysmon()
        s.scenario_time = 10.0
        s._scenario_dispatch_context = {
            "scheduled_time_s": 10.0,
            "dispatch_time_s": 10.0,
            "source_line": 1,
        }
        s.parameters["alerttimeout"] = 5000
        s.set_parameter("lights-1-failure", True)
        s._scenario_dispatch_context = {
            "scheduled_time_s": 10.0,
            "dispatch_time_s": 10.0,
            "source_line": 2,
        }
        s.parameters["alerttimeout"] = 9000

        s.set_parameter("scales-1-failure", True)

        rejected = [
            json.loads(value)
            for value in s.performance["opportunity"]
            if json.loads(value)["phase"] == "rejected"
        ]
        assert [item["planned_duration_ms"] for item in rejected] == [5000, 9000]
        assert all(item["outcome"] == "INVALID_COLLAPSED_BATCH" for item in rejected)
        assert not any(gauge["failure"] for gauge in s.get_all_gauges())

    def test_protocol_window_closes_as_observed_correct_rejection(self):
        """Catch idle time being inferred instead of an explicit non-target trial."""
        s = _make_sysmon()
        s.parameters["nontargetduration"] = 2000

        s.open_nontarget_opportunity()
        s.scenario_time = 2.0
        s.close_nontarget_opportunity(false_alarm=False)

        opportunities = [json.loads(value) for value in s.performance["opportunity"]]
        assert opportunities == [
            {
                "allocation_actor": "participant",
                "automation_active": False,
                "close_lateness_tolerance_ms": 200,
                "deadline_s": 2.0,
                "duration_ms": 2000,
                "opened_scenario_time_s": 0,
                "opportunity_id": "sysmon-000001",
                "phase": "opened",
                "target": False,
            },
            {
                "automation_active": False,
                "closed_scenario_time_s": 2.0,
                "indicator": None,
                "lateness_ms": 0,
                "opened_scenario_time_s": 0,
                "opportunity_id": "sysmon-000001",
                "outcome": "CR",
                "phase": "closed",
                "reason": None,
                "response_time_ms": None,
                "response_actor": "participant",
                "scheduled_deadline_s": 2.0,
                "target": False,
            },
        ]

    def test_false_alarm_is_linked_to_active_non_target_opportunity(self):
        """Catch false responses with no observed non-target denominator."""
        s = _make_sysmon()
        s.parameters["nontargetduration"] = 2000
        s.open_nontarget_opportunity()

        with patch("plugins.abstractplugin.Window.MainWindow", MagicMock(modal_dialog=None)):
            s.do_on_key("F1", "press", False)

        opportunities = [json.loads(value) for value in s.performance["opportunity"]]
        assert opportunities[-1]["target"] is False
        assert opportunities[-1]["outcome"] == "FA"
        assert opportunities[-1]["indicator"] == "F1"
        assert "opportunity_unlinked_response" not in s.performance

    def test_window_uses_absolute_scenario_deadline_after_a_stalled_update(self):
        """A 2 s observation window cannot remain open after a 5 s GUI stall."""
        s = _make_sysmon()
        s.parameters["nontargetduration"] = 2000
        s.open_nontarget_opportunity()
        s.scenario_time = 5.0

        with patch("plugins.abstractplugin.AbstractPlugin.compute_next_plugin_state", return_value=True):
            s.compute_next_plugin_state()

        assert s._nontarget_opportunity_id is None
        closed = json.loads(s.performance["opportunity"][-1])
        assert closed["closed_scenario_time_s"] == 5.0
        assert closed["outcome"] == "INVALID_STALLED_WINDOW"
        assert closed["reason"] == "window_closed_after_update_stall"
        assert closed["lateness_ms"] == 3000


class TestStopOpportunityCleanup:
    def test_stop_invalidates_active_and_pending_target_evidence(self):
        from plugins.abstractplugin import AbstractPlugin

        s = _make_sysmon()
        active = s.parameters["lights"]["1"]
        active["failure"] = True
        s.start_failure(active)
        pending = s.parameters["scales"]["1"]
        pending["failure"] = True
        pending["_pending_alerttimeout_ms"] = 10_000
        pending["_pending_dispatch_context"] = {"scheduled_time_s": 0.0}

        with patch.object(AbstractPlugin, "stop") as parent_stop:
            s.stop()

        payloads = [json.loads(value) for value in s.performance["opportunity"]]
        assert any(
            payload["phase"] == "closed"
            and payload["reason"] == "task_stopped_before_outcome"
            for payload in payloads
        )
        assert any(
            payload["phase"] == "rejected"
            and payload["reason"] == "task_stopped_before_outcome"
            for payload in payloads
        )
        assert not any(gauge["failure"] for gauge in s.get_all_gauges())
        assert not s.get_gauges_on_failure()
        parent_stop.assert_called_once_with()

    def test_stop_invalidates_active_nontarget_evidence(self):
        from plugins.abstractplugin import AbstractPlugin

        s = _make_sysmon()
        s.parameters["nontargetduration"] = 2000
        s.open_nontarget_opportunity()

        with patch.object(AbstractPlugin, "stop") as parent_stop:
            s.stop()

        closed = json.loads(s.performance["opportunity"][-1])
        assert closed["phase"] == "closed"
        assert closed["reason"] == "task_stopped_before_outcome"
        assert s._nontarget_opportunity_id is None
        parent_stop.assert_called_once_with()


class TestAbsoluteFailureTiming:
    def test_failure_deadline_and_hit_rt_use_actual_scenario_elapsed_time(self):
        s = _make_sysmon()
        s.scenario_time = 5.0
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        s.scenario_time = 7.75

        s.stop_failure(light, success=True)

        assert s.performance["response_time"][-1] == 2750

    def test_failure_expires_after_stall_without_fixed_tick_drift(self):
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        s.scenario_time = 12.0

        with patch("plugins.abstractplugin.AbstractPlugin.compute_next_plugin_state", return_value=True):
            s.compute_next_plugin_state()

        assert light["_onfailure"] is False
        assert "signal_detection" not in s.performance
        closed = json.loads(s.performance["opportunity"][-1])
        assert closed["outcome"] == "INVALID_STALLED_WINDOW"
        assert closed["reason"] == "window_closed_after_update_stall"


# ──────────────────────────────────────────────
# Gauge helper methods
# ──────────────────────────────────────────────
class TestGaugeHelpers:
    """Test gauge filtering methods on actual Sysmon instance."""

    def test_get_all_gauges_count(self):
        """All gauges = 4 scales + 2 lights = 6."""
        s = _make_sysmon()
        assert len(s.get_all_gauges()) == 6  # 4 scales + 2 lights

    def test_get_scale_gauges_count(self):
        """4 scale gauges."""
        s = _make_sysmon()
        assert len(s.get_scale_gauges()) == 4

    def test_get_light_gauges_count(self):
        """2 light gauges."""
        s = _make_sysmon()
        assert len(s.get_light_gauges()) == 2

    def test_get_gauges_on_failure_empty(self):
        """No failures initially."""
        s = _make_sysmon()
        assert len(s.get_gauges_on_failure()) == 0

    def test_get_gauges_on_failure_after_start(self):
        """One gauge on failure after start_failure."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        assert len(s.get_gauges_on_failure()) == 1

    def test_get_gauge_by_key(self):
        """Finds gauge by its key name."""
        s = _make_sysmon()
        gauge = s.get_gauge_by_key("F5")
        assert gauge["name"] == "F5"

    def test_get_gauge_key_for_scale(self):
        """Returns scale number as string key."""
        s = _make_sysmon()
        scale = s.parameters["scales"]["2"]
        assert s.get_gauge_key(scale) == "2"

    def test_get_gauge_key_for_light(self):
        """Returns light number as string key."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        assert s.get_gauge_key(light) == "1"


# ──────────────────────────────────────────────
# Scale zones
# ──────────────────────────────────────────────
class TestScaleZones:
    """Test the zone classification for scale arrow positions."""

    def test_zone_mapping(self):
        """Positions 0, 5, 10 map to zones 1, 0, -1."""
        s = _make_sysmon()
        assert 0 in s.scale_zones[1]
        assert 5 in s.scale_zones[0]
        assert 10 in s.scale_zones[-1]

    def test_zone_boundaries(self):
        """Boundary positions are in correct zones."""
        s = _make_sysmon()
        assert 2 in s.scale_zones[1]  # Last in upper zone
        assert 3 in s.scale_zones[0]  # First in neutral zone
        assert 7 in s.scale_zones[0]  # Last in neutral zone
        assert 8 in s.scale_zones[-1]  # First in lower zone

    def test_zone_sizes(self):
        """Zones have 3, 5, 3 positions respectively."""
        s = _make_sysmon()
        assert len(s.scale_zones[1]) == 3  # 0, 1, 2
        assert len(s.scale_zones[0]) == 5  # 3, 4, 5, 6, 7
        assert len(s.scale_zones[-1]) == 3  # 8, 9, 10


# ──────────────────────────────────────────────
# Failure timer logic
# ──────────────────────────────────────────────
class TestFailureTimer:
    """Test failure timer decrement and response time tracking."""

    def test_timer_decrement_per_update(self):
        """Timer decreases by taskupdatetime each cycle."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)
        initial_timer = light["_failuretimer"]

        # Simulate one update cycle
        light["_failuretimer"] -= s.parameters["taskupdatetime"]
        light["_milliresponsetime"] += s.parameters["taskupdatetime"]

        assert light["_failuretimer"] == initial_timer - 200
        assert light["_milliresponsetime"] == 200

    def test_response_time_accumulates(self):
        """Response time increases each update cycle."""
        s = _make_sysmon()
        light = s.parameters["lights"]["1"]
        light["failure"] = True
        s.start_failure(light)

        # Simulate 5 update cycles
        for _ in range(5):
            light["_failuretimer"] -= s.parameters["taskupdatetime"]
            light["_milliresponsetime"] += s.parameters["taskupdatetime"]

        assert light["_milliresponsetime"] == 1000

    def test_get_response_timers(self):
        """Returns list of all 6 gauge response times."""
        s = _make_sysmon()
        timers = s.get_response_timers()
        assert len(timers) == 6
        assert all(t == 0 for t in timers)
