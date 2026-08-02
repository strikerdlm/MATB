from matb_integration.suas.engine.separation import SeparationMonitor
from .helpers import event_kinds, place_pair


def test_separation_alert_opens_and_closes_once(reference_world) -> None:
    monitor = SeparationMonitor(advisory_mm=300_000, critical_mm=150_000)
    place_pair(reference_world, 290_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_ADVISORY_OPENED"]
    assert monitor.step(reference_world) == ()
    place_pair(reference_world, 140_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_VIOLATION"]
    place_pair(reference_world, 400_000)
    assert event_kinds(monitor.step(reference_world)) == ["SEPARATION_ALERT_CLOSED"]
