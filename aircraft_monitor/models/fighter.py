"""Fighter Aircraft model with realistic combat systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final


class FighterType(Enum):
    """Types of fighter aircraft."""

    AIR_SUPERIORITY = "F-22 Raptor"
    MULTIROLE = "F-35 Lightning II"
    STRIKE = "F-15E Strike Eagle"
    INTERCEPTOR = "F-16 Fighting Falcon"
    NAVAL = "F/A-18 Super Hornet"
    STEALTH_BOMBER = "B-2 Spirit"


class FighterStatus(Enum):
    """Fighter operational status."""

    HANGAR = "In Hangar"
    PREFLIGHT = "Pre-Flight"
    TAXIING = "Taxiing"
    TAKEOFF = "Taking Off"
    CLIMBING = "Climbing"
    CRUISING = "Cruising"
    COMBAT = "Combat Engaged"
    EVADING = "Evasive Maneuvers"
    ATTACKING = "Attack Run"
    PATROLLING = "Combat Air Patrol"
    REFUELING = "Aerial Refueling"
    RTB = "Return to Base"
    LANDING = "Landing"
    EMERGENCY = "Emergency"


class WeaponType(Enum):
    """Types of weapons."""

    AAM_SHORT = "AIM-9X Sidewinder"
    AAM_MEDIUM = "AIM-120 AMRAAM"
    AAM_LONG = "AIM-260 JATM"
    AGM = "AGM-88 HARM"
    BOMB_GUIDED = "GBU-31 JDAM"
    BOMB_CLUSTER = "CBU-97 SFW"
    GUN = "M61A2 Vulcan"


# Operational limits
MAX_G_FORCE: Final[float] = 9.0
MAX_ALTITUDE_FT: Final[int] = 65000
MAX_SPEED_MACH: Final[float] = 2.5
BINGO_FUEL_PERCENT: Final[int] = 25


@dataclass(slots=True)
class WeaponSystem:
    """Aircraft weapon system."""

    weapon_type: WeaponType
    quantity: int
    ready: bool = True
    selected: bool = False


@dataclass(slots=True)
class RadarContact:
    """Radar contact information."""

    contact_id: str
    classification: str  # FRIENDLY, HOSTILE, UNKNOWN
    aircraft_type: str
    bearing: int  # degrees
    distance_nm: float
    altitude_ft: int
    speed_knots: int
    is_locked: bool = False
    is_jamming: bool = False


@dataclass(slots=True)
class MissileWarning:
    """Incoming missile warning."""

    missile_id: str
    missile_type: str
    bearing: int
    time_to_impact_sec: float
    countermeasures_deployed: bool = False


@dataclass(slots=True)
class DefensiveSystems:
    """Defensive countermeasure systems."""

    chaff_count: int = 60
    flare_count: int = 60
    ecm_active: bool = False
    rwr_active: bool = True  # Radar Warning Receiver
    mws_active: bool = True  # Missile Warning System
    jamming_active: bool = False


@dataclass(slots=True)
class AvionicsSystems:
    """Avionics and sensor systems."""

    radar_active: bool = True
    radar_mode: str = "SEARCH"  # SEARCH, TRACK, GROUND_MAP, TERRAIN_FOLLOW
    irst_active: bool = False  # Infrared Search and Track
    datalink_active: bool = True
    hud_active: bool = True
    targeting_pod_active: bool = False
    nav_system: str = "GPS/INS"
    autopilot_engaged: bool = False


@dataclass(slots=True)
class EngineStatus:
    """Engine status information."""

    engine_1_rpm_percent: int = 85
    engine_2_rpm_percent: int = 85
    engine_1_temp_c: int = 650
    engine_2_temp_c: int = 650
    afterburner_1_active: bool = False
    afterburner_2_active: bool = False
    engine_1_status: str = "NOMINAL"
    engine_2_status: str = "NOMINAL"


@dataclass(slots=True)
class FighterAircraft:
    """
    Fighter Aircraft model with comprehensive combat systems.

    Attributes:
        callsign: Pilot callsign
        tail_number: Aircraft tail number
        fighter_type: Type of fighter
        status: Current operational status
        fuel_percent: Fuel remaining (0-100)
        altitude_ft: Current altitude
        speed_mach: Current speed in Mach
        heading: Current heading (0-359)
        g_force: Current G-force
        weapons: Loaded weapons
        radar_contacts: Detected radar contacts
        missile_warnings: Active missile warnings
        defensive: Defensive systems status
        avionics: Avionics systems status
        engines: Engine status
    """

    callsign: str
    tail_number: str
    fighter_type: FighterType
    status: FighterStatus = FighterStatus.HANGAR
    fuel_percent: int = 100
    altitude_ft: int = 0
    speed_mach: float = 0.0
    speed_knots: int = 0
    heading: int = 0
    g_force: float = 1.0
    latitude: float = 0.0
    longitude: float = 0.0
    weapons: list[WeaponSystem] = field(default_factory=list)
    radar_contacts: list[RadarContact] = field(default_factory=list)
    missile_warnings: list[MissileWarning] = field(default_factory=list)
    defensive: DefensiveSystems = field(default_factory=DefensiveSystems)
    avionics: AvionicsSystems = field(default_factory=AvionicsSystems)
    engines: EngineStatus = field(default_factory=EngineStatus)
    master_arm: bool = False
    landing_gear_down: bool = True
    canopy_closed: bool = True
    oxygen_percent: int = 100
    mission_time_sec: int = 0
    kills: int = 0
    mission_objectives: list[tuple[str, bool]] = field(default_factory=list)

    def is_bingo_fuel(self) -> bool:
        """Check if fuel is at bingo (minimum for RTB)."""
        return self.fuel_percent <= BINGO_FUEL_PERCENT

    def get_hostile_count(self) -> int:
        """Count hostile radar contacts."""
        return sum(1 for c in self.radar_contacts if c.classification == "HOSTILE")

    def get_locked_target(self) -> RadarContact | None:
        """Get currently locked radar target."""
        for contact in self.radar_contacts:
            if contact.is_locked:
                return contact
        return None

    def has_incoming_missiles(self) -> bool:
        """Check if there are incoming missiles."""
        return len(self.missile_warnings) > 0

    def get_ready_weapons_count(self) -> int:
        """Get total count of ready weapons."""
        return sum(w.quantity for w in self.weapons if w.ready)

    def get_selected_weapon(self) -> WeaponSystem | None:
        """Get currently selected weapon."""
        for weapon in self.weapons:
            if weapon.selected:
                return weapon
        return None

    def get_mission_completion(self) -> float:
        """Get mission completion percentage."""
        if not self.mission_objectives:
            return 0.0
        completed = sum(1 for _, done in self.mission_objectives if done)
        return (completed / len(self.mission_objectives)) * 100

    def is_under_threat(self) -> bool:
        """Check if aircraft is under active threat."""
        return self.has_incoming_missiles() or self.get_hostile_count() > 0
