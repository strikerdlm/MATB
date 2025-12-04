"""Aircraft models for the monitoring system."""

from aircraft_monitor.models.uav import UAV, UAVType, UAVMission, UAVStatus
from aircraft_monitor.models.fighter import (
    FighterAircraft,
    FighterType,
    WeaponSystem,
    FighterStatus,
)

__all__ = [
    "UAV",
    "UAVType",
    "UAVMission",
    "UAVStatus",
    "FighterAircraft",
    "FighterType",
    "WeaponSystem",
    "FighterStatus",
]
