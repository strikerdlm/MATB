"""Base event classes for the monitoring system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventSeverity(Enum):
    """Event severity levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class EventCategory(Enum):
    """Event categories."""

    SYSTEM = "SYSTEM"
    NAVIGATION = "NAVIGATION"
    SENSOR = "SENSOR"
    WEAPON = "WEAPON"
    THREAT = "THREAT"
    COMMUNICATION = "COMM"
    ENGINE = "ENGINE"
    MISSION = "MISSION"
    PILOT = "PILOT"
    DEFENSIVE = "DEFENSIVE"


# Severity to rich color mapping
SEVERITY_COLORS: dict[EventSeverity, str] = {
    EventSeverity.DEBUG: "dim",
    EventSeverity.INFO: "cyan",
    EventSeverity.SUCCESS: "green",
    EventSeverity.WARNING: "yellow",
    EventSeverity.CRITICAL: "red",
    EventSeverity.EMERGENCY: "bold red on white",
}

# Category to emoji mapping
CATEGORY_ICONS: dict[EventCategory, str] = {
    EventCategory.SYSTEM: "⚙️ ",
    EventCategory.NAVIGATION: "🧭",
    EventCategory.SENSOR: "📡",
    EventCategory.WEAPON: "🎯",
    EventCategory.THREAT: "⚠️ ",
    EventCategory.COMMUNICATION: "📶",
    EventCategory.ENGINE: "🔧",
    EventCategory.MISSION: "🎖️ ",
    EventCategory.PILOT: "👨‍✈️",
    EventCategory.DEFENSIVE: "🛡️ ",
}


@dataclass(slots=True, frozen=True)
class Event:
    """
    Immutable event record.

    Attributes:
        timestamp: When the event occurred
        severity: Event severity level
        category: Event category
        title: Short event title
        description: Detailed event description
        source: Source of the event (callsign/system)
        data: Additional event data
    """

    timestamp: datetime
    severity: EventSeverity
    category: EventCategory
    title: str
    description: str
    source: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def color(self) -> str:
        """Get rich color for this event's severity."""
        return SEVERITY_COLORS.get(self.severity, "white")

    @property
    def icon(self) -> str:
        """Get icon for this event's category."""
        return CATEGORY_ICONS.get(self.category, "📋")

    def format_timestamp(self) -> str:
        """Format timestamp for display."""
        return self.timestamp.strftime("%H:%M:%S.%f")[:-3]


def create_event(
    severity: EventSeverity,
    category: EventCategory,
    title: str,
    description: str,
    source: str,
    data: dict[str, Any] | None = None,
) -> Event:
    """
    Factory function to create an event with current timestamp.

    Args:
        severity: Event severity level
        category: Event category
        title: Short event title
        description: Detailed description
        source: Event source identifier
        data: Optional additional data

    Returns:
        New Event instance
    """
    return Event(
        timestamp=datetime.now(),
        severity=severity,
        category=category,
        title=title,
        description=description,
        source=source,
        data=data if data is not None else {},
    )
