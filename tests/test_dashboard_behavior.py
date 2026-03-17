"""Regression tests for dashboard timing and mission aggregation behavior."""

from __future__ import annotations

from collections.abc import Generator

from pytest import MonkeyPatch

from aircraft_monitor.events.base import Event, EventCategory, EventSeverity, create_event
from aircraft_monitor.models.fighter import FighterAircraft, FighterType
from aircraft_monitor.models.uav import UAV, UAVMission, UAVType, Waypoint
from aircraft_monitor.visualization.dashboard import MonitoringDashboard


def _one_event() -> Generator[Event, None, None]:
    """Yield a single deterministic event for smoke-style tests."""
    yield create_event(
        EventSeverity.INFO,
        EventCategory.SYSTEM,
        "TEST",
        "single event",
        "TEST-SRC",
    )


def test_headless_env_override_true(monkeypatch: MonkeyPatch) -> None:
    """Env override should force headless mode even if terminal is interactive."""
    monkeypatch.setenv("AIRCRAFT_MONITOR_HEADLESS", "true")
    dashboard = MonitoringDashboard(headless=None)
    assert dashboard._headless is True


def test_combined_mission_uses_joint_summary() -> None:
    """Combined mode should summarize both fighter and UAV progress."""
    uav = UAV(callsign="SHADOW-1", uav_type=UAVType.RECONNAISSANCE, mission=UAVMission.ISR)
    uav.waypoints = [
        Waypoint("ALPHA", 1.0, 1.0, 10000, True),
        Waypoint("BRAVO", 2.0, 2.0, 10000, False),
    ]
    fighter = FighterAircraft(callsign="VIPER", tail_number="AF-001", fighter_type=FighterType.AIR_SUPERIORITY)
    fighter.mission_objectives = [("Obj A", True), ("Obj B", False)]

    dashboard = MonitoringDashboard(headless=True)
    dashboard.set_uav(uav)
    dashboard.set_fighter(fighter)
    dashboard._start_mission_clock()
    dashboard._update_mission()

    assert dashboard._mission._mission_name == "JOINT TASK FORCE"
    assert len(dashboard._mission._objectives) == 3
    assert dashboard._mission._objectives[0] == ("Fighter objectives 1/2", False)
    assert dashboard._mission._objectives[1] == ("UAV waypoints 1/2", False)


def test_fighter_headless_simulation_smoke() -> None:
    """Fighter simulation should run in headless mode without crashing."""
    fighter = FighterAircraft(callsign="VIPER", tail_number="AF-192", fighter_type=FighterType.AIR_SUPERIORITY)
    dashboard = MonitoringDashboard(headless=True)
    dashboard.set_fighter(fighter)

    dashboard.run_fighter_simulation(_one_event())

    assert fighter.mission_time_sec >= 0
