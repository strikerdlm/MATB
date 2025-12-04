"""UAV-specific event generation with realistic scenarios."""

from __future__ import annotations

import random
from collections.abc import Generator
from typing import TYPE_CHECKING

from aircraft_monitor.events.base import (
    Event,
    EventCategory,
    EventSeverity,
    create_event,
)
from aircraft_monitor.models.uav import (
    ThreatContact,
    UAVStatus,
    Waypoint,
)

if TYPE_CHECKING:
    from aircraft_monitor.models.uav import UAV


class UAVEventGenerator:
    """
    Generates realistic UAV operation events.

    Produces a sequence of events simulating a complete UAV mission
    including preflight, launch, navigation, mission execution,
    threat encounters, and return to base.
    """

    def __init__(self, uav: UAV) -> None:
        """
        Initialize event generator for a UAV.

        Args:
            uav: The UAV instance to generate events for
        """
        self._uav = uav
        self._event_counter = 0

    def generate_preflight_sequence(self) -> Generator[Event, None, None]:
        """Generate preflight check events."""
        self._uav.status = UAVStatus.PREFLIGHT

        yield create_event(
            EventSeverity.INFO,
            EventCategory.SYSTEM,
            "PREFLIGHT INITIATED",
            f"Beginning preflight checks for {self._uav.callsign}",
            self._uav.callsign,
        )

        checks = [
            ("Flight Control Surfaces", "Ailerons, elevators, rudder - NOMINAL"),
            ("Avionics Systems", "Navigation, communication, datalink - ONLINE"),
            ("Sensor Payload", f"Active sensors: {', '.join(self._uav.sensors.active_sensors())}"),
            ("Power Systems", f"Battery: {self._uav.battery_percent}% | Fuel: {self._uav.fuel_percent}%"),
            ("GPS Lock", f"Satellites acquired: {self._uav.gps_satellites}"),
            ("Datalink", f"Uplink established | Signal: {self._uav.signal_strength}%"),
            ("Autopilot", "Flight computer initialized | Mission waypoints loaded"),
        ]

        for check_name, check_detail in checks:
            yield create_event(
                EventSeverity.SUCCESS,
                EventCategory.SYSTEM,
                f"✓ {check_name}",
                check_detail,
                self._uav.callsign,
            )

        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.MISSION,
            "PREFLIGHT COMPLETE",
            f"All systems nominal. {self._uav.uav_type.value} ready for launch.",
            self._uav.callsign,
        )

    def generate_launch_sequence(self) -> Generator[Event, None, None]:
        """Generate launch events."""
        self._uav.status = UAVStatus.LAUNCHING

        yield create_event(
            EventSeverity.INFO,
            EventCategory.MISSION,
            "LAUNCH SEQUENCE",
            "Initiating launch sequence...",
            self._uav.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.ENGINE,
            "ENGINE START",
            "Propulsion system online | Thrust nominal",
            self._uav.callsign,
        )

        self._uav.speed_knots = 45
        yield create_event(
            EventSeverity.INFO,
            EventCategory.NAVIGATION,
            "TAXI COMPLETE",
            "Moving to runway | Ground speed: 45 kts",
            self._uav.callsign,
        )

        self._uav.speed_knots = 120
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.NAVIGATION,
            "AIRBORNE",
            "Liftoff successful | Climbing to cruise altitude",
            self._uav.callsign,
            {"ground_speed": 120},
        )

        self._uav.status = UAVStatus.CLIMBING
        for alt in [5000, 15000, 25000]:
            self._uav.altitude_ft = alt
            self._uav.speed_knots = min(180 + (alt // 1000), 280)
            yield create_event(
                EventSeverity.INFO,
                EventCategory.NAVIGATION,
                f"ALTITUDE {alt:,} FT",
                f"Climbing | Speed: {self._uav.speed_knots} kts | Heading: {self._uav.heading:03d}°",
                self._uav.callsign,
            )

        self._uav.status = UAVStatus.CRUISING
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.NAVIGATION,
            "CRUISE ALTITUDE",
            f"Level at {self._uav.altitude_ft:,} ft | Engaging autopilot",
            self._uav.callsign,
        )

    def generate_navigation_events(self) -> Generator[Event, None, None]:
        """Generate waypoint navigation events."""
        # Create mission waypoints
        waypoints = [
            Waypoint("ALPHA", 34.0522, -118.2437, 25000),
            Waypoint("BRAVO", 34.1522, -118.3437, 25000),
            Waypoint("CHARLIE", 34.2522, -118.4437, 28000),
            Waypoint("DELTA", 34.3522, -118.3437, 28000),
            Waypoint("ECHO", 34.2522, -118.2437, 25000),
        ]
        self._uav.waypoints = waypoints

        for idx, wp in enumerate(waypoints):
            self._uav.current_waypoint_idx = idx

            yield create_event(
                EventSeverity.INFO,
                EventCategory.NAVIGATION,
                f"STEERING TO {wp.name}",
                f"Next waypoint: {wp.name} | Alt: {wp.altitude_ft:,} ft",
                self._uav.callsign,
            )

            # Simulate flight to waypoint
            self._uav.latitude = wp.latitude
            self._uav.longitude = wp.longitude
            self._uav.altitude_ft = wp.altitude_ft
            self._uav.heading = (self._uav.heading + random.randint(10, 45)) % 360
            self._uav.battery_percent = max(10, self._uav.battery_percent - random.randint(3, 8))
            self._uav.fuel_percent = max(10, self._uav.fuel_percent - random.randint(2, 5))

            wp.is_reached = True
            yield create_event(
                EventSeverity.SUCCESS,
                EventCategory.NAVIGATION,
                f"WAYPOINT {wp.name} REACHED",
                f"Position: {wp.latitude:.4f}°N, {abs(wp.longitude):.4f}°W",
                self._uav.callsign,
                {"waypoint": wp.name, "index": idx + 1, "total": len(waypoints)},
            )

            self._uav.mission_progress = int(((idx + 1) / len(waypoints)) * 100)

    def generate_sensor_events(self) -> Generator[Event, None, None]:
        """Generate sensor and surveillance events."""
        self._uav.status = UAVStatus.ON_STATION

        yield create_event(
            EventSeverity.INFO,
            EventCategory.MISSION,
            "ON STATION",
            f"Entering surveillance area | Mission: {self._uav.mission.value}",
            self._uav.callsign,
        )

        sensor_activities = [
            ("EO CAMERA", "Electro-optical imaging active | Resolution: 4K | Zoom: 30x"),
            ("IR SENSOR", "Infrared scanning enabled | Detecting thermal signatures"),
            ("TARGET ACQUISITION", "Potential target identified | Grid: 34°12'N 118°24'W"),
            ("DATA RECORDING", "Mission data recording | Storage: 45% utilized"),
            ("IMAGE CAPTURE", "High-resolution imagery captured | Transmitting to ground station"),
            ("PATTERN ANALYSIS", "AI pattern recognition active | 3 objects of interest flagged"),
        ]

        for sensor_name, sensor_detail in sensor_activities:
            yield create_event(
                EventSeverity.INFO,
                EventCategory.SENSOR,
                sensor_name,
                sensor_detail,
                self._uav.callsign,
            )

        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.MISSION,
            "SURVEILLANCE COMPLETE",
            "Primary objectives captured | Data transmitted",
            self._uav.callsign,
        )

    def generate_threat_encounter(self) -> Generator[Event, None, None]:
        """Generate threat detection and response events."""
        # Add threat contacts
        threats = [
            ThreatContact("BANDIT-1", "Surface-to-Air Missile", 45, 12.5, "HIGH", True),
            ThreatContact("JAMMER-1", "Electronic Warfare", 120, 25.0, "MEDIUM", False),
        ]
        self._uav.threats = threats

        yield create_event(
            EventSeverity.WARNING,
            EventCategory.THREAT,
            "⚠️ THREAT DETECTED",
            f"SAM radar detected | Bearing: {threats[0].bearing}° | Range: {threats[0].distance_nm} nm",
            self._uav.callsign,
            {"threat_id": threats[0].threat_id},
        )

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.THREAT,
            "🚨 TRACKING RADAR",
            "SAM system tracking | Initiating evasive profile",
            self._uav.callsign,
        )

        # Evasive actions
        self._uav.altitude_ft = 35000
        self._uav.heading = (self._uav.heading + 90) % 360
        yield create_event(
            EventSeverity.WARNING,
            EventCategory.NAVIGATION,
            "EVASIVE MANEUVER",
            f"Climbing to {self._uav.altitude_ft:,} ft | New heading: {self._uav.heading:03d}°",
            self._uav.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.DEFENSIVE,
            "ECM ACTIVE",
            "Electronic countermeasures deployed | Jamming hostile radar",
            self._uav.callsign,
        )

        # Threat evaded
        self._uav.threats = []
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.DEFENSIVE,
            "THREAT EVADED",
            "SAM tracking lost | Resuming mission profile",
            self._uav.callsign,
        )

    def generate_communication_events(self) -> Generator[Event, None, None]:
        """Generate communication-related events."""
        # Signal degradation
        self._uav.signal_strength = 65
        yield create_event(
            EventSeverity.WARNING,
            EventCategory.COMMUNICATION,
            "SIGNAL DEGRADATION",
            f"Uplink signal strength: {self._uav.signal_strength}% | Switching to backup frequency",
            self._uav.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.COMMUNICATION,
            "FREQUENCY CHANGE",
            "Backup frequency established | Datalink restored",
            self._uav.callsign,
        )

        self._uav.signal_strength = 92
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.COMMUNICATION,
            "SIGNAL RESTORED",
            f"Full uplink restored | Signal: {self._uav.signal_strength}%",
            self._uav.callsign,
        )

    def generate_rtb_sequence(self) -> Generator[Event, None, None]:
        """Generate return to base events."""
        self._uav.status = UAVStatus.RTB

        yield create_event(
            EventSeverity.INFO,
            EventCategory.MISSION,
            "RTB INITIATED",
            f"Mission complete | Returning to base | Fuel: {self._uav.fuel_percent}%",
            self._uav.callsign,
        )

        self._uav.altitude_ft = 15000
        yield create_event(
            EventSeverity.INFO,
            EventCategory.NAVIGATION,
            "DESCENT",
            f"Descending to {self._uav.altitude_ft:,} ft | Speed: {self._uav.speed_knots} kts",
            self._uav.callsign,
        )

        self._uav.status = UAVStatus.LANDING
        yield create_event(
            EventSeverity.INFO,
            EventCategory.NAVIGATION,
            "FINAL APPROACH",
            "On glide slope | Gear down | Airspeed nominal",
            self._uav.callsign,
        )

        self._uav.altitude_ft = 0
        self._uav.speed_knots = 0
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.MISSION,
            "🛬 LANDING COMPLETE",
            f"Touchdown confirmed | Mission duration: {random.randint(180, 300)} minutes",
            self._uav.callsign,
        )

        self._uav.mission_progress = 100
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.MISSION,
            "🎖️ MISSION SUCCESS",
            f"All objectives completed | Battery: {self._uav.battery_percent}% | Fuel: {self._uav.fuel_percent}%",
            self._uav.callsign,
        )

    def generate_full_mission(self) -> Generator[Event, None, None]:
        """Generate a complete mission event sequence."""
        yield from self.generate_preflight_sequence()
        yield from self.generate_launch_sequence()
        yield from self.generate_navigation_events()
        yield from self.generate_sensor_events()
        yield from self.generate_threat_encounter()
        yield from self.generate_communication_events()
        yield from self.generate_rtb_sequence()
