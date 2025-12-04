"""UAV (Unmanned Aerial Vehicle) model with realistic attributes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class UAVType(Enum):
    """Types of UAV platforms."""

    RECONNAISSANCE = "MQ-9 Reaper"
    SURVEILLANCE = "RQ-4 Global Hawk"
    TACTICAL = "MQ-1C Gray Eagle"
    CARGO = "MQ-25 Stingray"
    MICRO = "RQ-11 Raven"


class UAVMission(Enum):
    """UAV mission types."""

    ISR = "Intelligence, Surveillance, Reconnaissance"
    STRIKE = "Precision Strike"
    CARGO_DELIVERY = "Cargo Delivery"
    SEARCH_RESCUE = "Search and Rescue"
    PATROL = "Border Patrol"
    MAPPING = "Terrain Mapping"


class UAVStatus(Enum):
    """Operational status of UAV."""

    PREFLIGHT = "Pre-Flight Check"
    LAUNCHING = "Launching"
    CLIMBING = "Climbing to Altitude"
    CRUISING = "Cruising"
    ON_STATION = "On Station"
    EXECUTING = "Executing Mission"
    RTB = "Return to Base"
    LANDING = "Landing"
    EMERGENCY = "Emergency"
    OFFLINE = "Offline"


# Operational limits
MAX_ALTITUDE_FT: Final[int] = 50000
MAX_SPEED_KNOTS: Final[int] = 300
MAX_BATTERY_PERCENT: Final[int] = 100
MIN_BATTERY_CRITICAL: Final[int] = 15


@dataclass(slots=True)
class SensorPayload:
    """UAV sensor payload configuration."""

    electro_optical: bool = True
    infrared: bool = True
    synthetic_aperture_radar: bool = False
    signals_intelligence: bool = False
    lidar: bool = False

    def active_sensors(self) -> list[str]:
        """Return list of active sensor names."""
        sensors: list[str] = []
        if self.electro_optical:
            sensors.append("EO Camera")
        if self.infrared:
            sensors.append("IR Sensor")
        if self.synthetic_aperture_radar:
            sensors.append("SAR")
        if self.signals_intelligence:
            sensors.append("SIGINT")
        if self.lidar:
            sensors.append("LIDAR")
        return sensors


@dataclass(slots=True)
class Waypoint:
    """Navigation waypoint."""

    name: str
    latitude: float
    longitude: float
    altitude_ft: int
    is_reached: bool = False


@dataclass(slots=True)
class ThreatContact:
    """Detected threat information."""

    threat_id: str
    threat_type: str
    bearing: int  # degrees
    distance_nm: float  # nautical miles
    threat_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    is_tracking: bool = False


@dataclass(slots=True)
class UAV:
    """
    UAV aircraft model with comprehensive status tracking.

    Attributes:
        callsign: Unique identifier for the UAV
        uav_type: Type of UAV platform
        mission: Current mission type
        status: Current operational status
        battery_percent: Battery level (0-100)
        fuel_percent: Fuel level for hybrid UAVs (0-100)
        altitude_ft: Current altitude in feet
        speed_knots: Current speed in knots
        heading: Current heading in degrees (0-359)
        latitude: Current latitude
        longitude: Current longitude
        sensors: Sensor payload configuration
        waypoints: Mission waypoints
        threats: Detected threats
        signal_strength: Communication signal strength (0-100)
        gps_satellites: Number of GPS satellites locked
        mission_progress: Mission completion percentage (0-100)
    """

    callsign: str
    uav_type: UAVType
    mission: UAVMission
    status: UAVStatus = UAVStatus.PREFLIGHT
    battery_percent: int = 100
    fuel_percent: int = 100
    altitude_ft: int = 0
    speed_knots: int = 0
    heading: int = 0
    latitude: float = 0.0
    longitude: float = 0.0
    sensors: SensorPayload = field(default_factory=SensorPayload)
    waypoints: list[Waypoint] = field(default_factory=list)
    threats: list[ThreatContact] = field(default_factory=list)
    signal_strength: int = 100
    gps_satellites: int = 12
    mission_progress: int = 0
    uplink_active: bool = True
    datalink_status: str = "NOMINAL"
    autopilot_engaged: bool = True
    current_waypoint_idx: int = 0

    def get_current_waypoint(self) -> Waypoint | None:
        """Get current target waypoint."""
        if 0 <= self.current_waypoint_idx < len(self.waypoints):
            return self.waypoints[self.current_waypoint_idx]
        return None

    def advance_waypoint(self) -> bool:
        """Mark current waypoint as reached and advance to next."""
        if self.current_waypoint_idx < len(self.waypoints):
            self.waypoints[self.current_waypoint_idx].is_reached = True
            self.current_waypoint_idx += 1
            return self.current_waypoint_idx < len(self.waypoints)
        return False

    def is_battery_critical(self) -> bool:
        """Check if battery is at critical level."""
        return self.battery_percent < MIN_BATTERY_CRITICAL

    def get_active_threat_count(self) -> int:
        """Get count of active threats being tracked."""
        return sum(1 for t in self.threats if t.is_tracking)

    def get_highest_threat_level(self) -> str:
        """Get the highest threat level from all contacts."""
        levels = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        if not self.threats:
            return "NONE"
        max_level = max(levels.get(t.threat_level, 0) for t in self.threats)
        for level_name, level_val in levels.items():
            if level_val == max_level:
                return level_name
        return "NONE"
