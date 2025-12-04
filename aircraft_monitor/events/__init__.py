"""Event system for aircraft monitoring."""

from aircraft_monitor.events.base import Event, EventSeverity, EventCategory
from aircraft_monitor.events.uav_events import UAVEventGenerator
from aircraft_monitor.events.fighter_events import FighterEventGenerator

__all__ = [
    "Event",
    "EventSeverity",
    "EventCategory",
    "UAVEventGenerator",
    "FighterEventGenerator",
]
