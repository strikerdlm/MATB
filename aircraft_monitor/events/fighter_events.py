"""Fighter Aircraft event generation with realistic combat scenarios."""

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
from aircraft_monitor.models.fighter import (
    FighterStatus,
    MissileWarning,
    RadarContact,
    WeaponSystem,
    WeaponType,
)
from aircraft_monitor.simulation.physics import mach_to_knots

if TYPE_CHECKING:
    from aircraft_monitor.models.fighter import FighterAircraft


class FighterEventGenerator:
    """
    Generates realistic fighter aircraft combat events.

    Produces a sequence of events simulating a complete combat mission
    including startup, takeoff, combat air patrol, engagement,
    defensive maneuvers, and return to base.
    """

    def __init__(
        self,
        fighter: FighterAircraft,
        *,
        seed: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """
        Initialize event generator for a fighter aircraft.

        Args:
            fighter: The FighterAircraft instance to generate events for
            seed: Optional seed for deterministic event variation
            rng: Optional RNG to use (overrides seed when provided)
        """
        self._fighter = fighter
        self._rng = rng if rng is not None else random.Random(seed)

    def generate_startup_sequence(self) -> Generator[Event, None, None]:
        """Generate cockpit startup events."""
        self._fighter.status = FighterStatus.PREFLIGHT

        yield create_event(
            EventSeverity.INFO,
            EventCategory.PILOT,
            "COCKPIT ENTRY",
            f"Pilot {self._fighter.callsign} strapping in | {self._fighter.fighter_type.value}",
            self._fighter.callsign,
        )

        startup_items = [
            ("BATTERY", "Main battery ON | Electrical bus powered"),
            ("APU START", "Auxiliary Power Unit online | Hydraulics pressurizing"),
            ("AVIONICS", "Displays initializing | HUD aligned | MFDs online"),
            ("INS ALIGN", "Inertial Navigation System aligning | GPS acquired"),
            ("RADAR", f"AN/APG-77 initializing | Mode: {self._fighter.avionics.radar_mode}"),
            ("RWR", "Radar Warning Receiver active | Threat library loaded"),
            ("OXYGEN", f"O2 system nominal | {self._fighter.oxygen_percent}% available"),
        ]

        for item_name, item_detail in startup_items:
            yield create_event(
                EventSeverity.SUCCESS,
                EventCategory.SYSTEM,
                f"✓ {item_name}",
                item_detail,
                self._fighter.callsign,
            )

        # Load weapons
        self._fighter.weapons = [
            WeaponSystem(WeaponType.AAM_SHORT, 2, True, False),
            WeaponSystem(WeaponType.AAM_MEDIUM, 6, True, False),
            WeaponSystem(WeaponType.GUN, 480, True, False),
        ]

        weapons_str = ", ".join(f"{w.weapon_type.value} x{w.quantity}" for w in self._fighter.weapons)
        yield create_event(
            EventSeverity.INFO,
            EventCategory.WEAPON,
            "WEAPONS LOADED",
            f"Armament: {weapons_str}",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.SYSTEM,
            "PREFLIGHT COMPLETE",
            "All systems nominal | Ready for engine start",
            self._fighter.callsign,
        )

    def generate_engine_start(self) -> Generator[Event, None, None]:
        """Generate engine start sequence."""
        yield create_event(
            EventSeverity.INFO,
            EventCategory.ENGINE,
            "ENGINE 1 START",
            "Right engine spooling | RPM increasing",
            self._fighter.callsign,
        )

        self._fighter.engines.engine_1_rpm_percent = 65
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.ENGINE,
            "ENGINE 1 IDLE",
            f"Right engine at idle | RPM: {self._fighter.engines.engine_1_rpm_percent}% | EGT nominal",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.ENGINE,
            "ENGINE 2 START",
            "Left engine spooling | Cross-bleed start",
            self._fighter.callsign,
        )

        self._fighter.engines.engine_2_rpm_percent = 65
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.ENGINE,
            "ENGINE 2 IDLE",
            f"Left engine at idle | RPM: {self._fighter.engines.engine_2_rpm_percent}% | EGT nominal",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.ENGINE,
            "ENGINES NOMINAL",
            "Both engines stable | Ready to taxi",
            self._fighter.callsign,
        )

    def generate_takeoff_sequence(self) -> Generator[Event, None, None]:
        """Generate taxi and takeoff events."""
        self._fighter.status = FighterStatus.TAXIING

        yield create_event(
            EventSeverity.INFO,
            EventCategory.COMMUNICATION,
            "TAXI CLEARANCE",
            "Ground control: Cleared to runway 27L via Alpha",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.NAVIGATION,
            "TAXI",
            "Taxiing to runway | Flight controls check complete",
            self._fighter.callsign,
        )

        self._fighter.status = FighterStatus.TAKEOFF
        yield create_event(
            EventSeverity.INFO,
            EventCategory.COMMUNICATION,
            "TAKEOFF CLEARANCE",
            "Tower: Cleared for takeoff runway 27L | Wind 270 at 12",
            self._fighter.callsign,
        )

        self._fighter.landing_gear_down = False
        self._fighter.engines.afterburner_1_active = True
        self._fighter.engines.afterburner_2_active = True

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.ENGINE,
            "🔥 AFTERBURNER",
            "Full military power | AB zones 1-5 lit",
            self._fighter.callsign,
        )

        self._fighter.speed_mach = 0.25
        self._fighter.speed_knots = mach_to_knots(self._fighter.speed_mach, self._fighter.altitude_ft)
        yield create_event(
            EventSeverity.INFO,
            EventCategory.NAVIGATION,
            "ROTATE",
            f"V-rotate | Speed: {self._fighter.speed_knots} kts | Nose up 12°",
            self._fighter.callsign,
        )

        self._fighter.altitude_ft = 500
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.NAVIGATION,
            "AIRBORNE",
            "Positive rate | Gear up | Accelerating",
            self._fighter.callsign,
        )

        self._fighter.status = FighterStatus.CLIMBING
        self._fighter.engines.afterburner_1_active = False
        self._fighter.engines.afterburner_2_active = False

        for alt, mach in [(10000, 0.8), (25000, 0.92), (35000, 0.95)]:
            self._fighter.altitude_ft = alt
            self._fighter.speed_mach = mach
            self._fighter.speed_knots = mach_to_knots(mach, alt)
            yield create_event(
                EventSeverity.INFO,
                EventCategory.NAVIGATION,
                f"ALTITUDE {alt:,} FT",
                f"Mach {mach:.2f} | Heading {self._fighter.heading:03d}°",
                self._fighter.callsign,
            )

    def generate_cap_events(self) -> Generator[Event, None, None]:
        """Generate Combat Air Patrol events."""
        self._fighter.status = FighterStatus.PATROLLING

        yield create_event(
            EventSeverity.INFO,
            EventCategory.MISSION,
            "CAP STATION",
            "On station | Beginning Combat Air Patrol pattern",
            self._fighter.callsign,
        )

        # Add mission objectives
        self._fighter.mission_objectives = [
            ("Establish air superiority in sector ALPHA", False),
            ("Intercept unidentified contacts", False),
            ("Protect high-value assets", False),
            ("Maintain patrol for 90 minutes", False),
        ]

        yield create_event(
            EventSeverity.INFO,
            EventCategory.SENSOR,
            "RADAR SWEEP",
            f"Scanning sector | Mode: {self._fighter.avionics.radar_mode} | Range: 120nm",
            self._fighter.callsign,
        )

        # AWACS contact
        yield create_event(
            EventSeverity.INFO,
            EventCategory.COMMUNICATION,
            "AWACS CONTACT",
            "OVERLORD: Picture clean | No hostile contacts in sector",
            self._fighter.callsign,
        )

        self._fighter.avionics.datalink_active = True
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.COMMUNICATION,
            "DATALINK",
            "Link-16 established | Tactical picture updated",
            self._fighter.callsign,
        )

    def generate_contact_detection(self) -> Generator[Event, None, None]:
        """Generate radar contact detection events."""
        yield create_event(
            EventSeverity.WARNING,
            EventCategory.COMMUNICATION,
            "⚠️ AWACS ALERT",
            "OVERLORD: Bogey, bearing 045, 80 miles, angels 30, heading southwest",
            self._fighter.callsign,
        )

        # Add radar contacts
        contacts = [
            RadarContact("BOGEY-1", "UNKNOWN", "Unknown", 45, 80.0, 30000, 450, False, False),
            RadarContact("BOGEY-2", "UNKNOWN", "Unknown", 48, 82.0, 30000, 450, False, False),
        ]
        self._fighter.radar_contacts = contacts

        yield create_event(
            EventSeverity.WARNING,
            EventCategory.SENSOR,
            "RADAR CONTACT",
            f"2 contacts | Bearing: 045° | Range: 80nm | Angels: 30",
            self._fighter.callsign,
            {"contacts": 2},
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.MISSION,
            "INTERCEPT",
            "Turning to intercept heading | Climbing to angels 35",
            self._fighter.callsign,
        )

        self._fighter.heading = 45
        self._fighter.altitude_ft = 35000
        self._fighter.speed_mach = 1.2
        self._fighter.speed_knots = mach_to_knots(self._fighter.speed_mach, self._fighter.altitude_ft)
        self._fighter.engines.afterburner_1_active = True
        self._fighter.engines.afterburner_2_active = True

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.ENGINE,
            "🔥 SUPERCRUISE",
            f"Mach {self._fighter.speed_mach:.1f} | Afterburners engaged",
            self._fighter.callsign,
        )

    def generate_identification(self) -> Generator[Event, None, None]:
        """Generate target identification events."""
        yield create_event(
            EventSeverity.INFO,
            EventCategory.SENSOR,
            "IFF INTERROGATION",
            "Interrogating contacts | No friendly response",
            self._fighter.callsign,
        )

        # Update contacts to hostile
        for contact in self._fighter.radar_contacts:
            contact.classification = "HOSTILE"
            contact.aircraft_type = "Su-35 Flanker"
            contact.distance_nm = 45.0

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.THREAT,
            "🚨 HOSTILE CONFIRMED",
            "AWACS declares hostile | 2x Su-35 Flanker | Weapons free",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.WARNING,
            EventCategory.DEFENSIVE,
            "RWR SPIKE",
            "Enemy radar lock detected | Bearing: 045°",
            self._fighter.callsign,
        )

        self._fighter.defensive.rwr_active = True

    def generate_combat_engagement(self) -> Generator[Event, None, None]:
        """Generate combat engagement events."""
        self._fighter.status = FighterStatus.COMBAT
        self._fighter.master_arm = True

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.WEAPON,
            "MASTER ARM ON",
            "Weapons hot | Master arm enabled",
            self._fighter.callsign,
        )

        # Select weapon
        for weapon in self._fighter.weapons:
            if weapon.weapon_type == WeaponType.AAM_MEDIUM:
                weapon.selected = True
                break

        yield create_event(
            EventSeverity.INFO,
            EventCategory.WEAPON,
            "WEAPON SELECT",
            "AIM-120 AMRAAM selected | Fox 3 ready",
            self._fighter.callsign,
        )

        # Lock target
        if not self._fighter.radar_contacts:
            yield create_event(
                EventSeverity.CRITICAL,
                EventCategory.SENSOR,
                "NO TARGETS",
                "No radar contacts available to lock | Aborting engagement sequence",
                self._fighter.callsign,
            )
            return

        self._fighter.radar_contacts[0].is_locked = True
        yield create_event(
            EventSeverity.WARNING,
            EventCategory.SENSOR,
            "RADAR LOCK",
            "Target locked | Range: 35nm | Closure: 1200 kts",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.WEAPON,
            "IN RANGE",
            "Target in envelope | Solution valid",
            self._fighter.callsign,
        )

        # Fire missile
        for weapon in self._fighter.weapons:
            if weapon.weapon_type == WeaponType.AAM_MEDIUM:
                weapon.quantity -= 1
                break

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.WEAPON,
            "🚀 FOX THREE",
            "AMRAAM away | Guiding on bandit 1",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.WEAPON,
            "MISSILE TRACKING",
            "AMRAAM pitbull | Active guidance | Impact 12 seconds",
            self._fighter.callsign,
        )

        # First kill
        self._fighter.kills += 1
        if self._fighter.radar_contacts:
            _ = self._fighter.radar_contacts.pop(0)  # remove destroyed contact
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.WEAPON,
            "💥 SPLASH ONE",
            "Bandit 1 destroyed | Kill confirmed",
            self._fighter.callsign,
        )

    def generate_defensive_events(self) -> Generator[Event, None, None]:
        """Generate defensive maneuver events."""
        # Incoming missile
        warning = MissileWarning("AA-12", "R-77 Adder", 48, 8.5, False)
        self._fighter.missile_warnings = [warning]

        yield create_event(
            EventSeverity.EMERGENCY,
            EventCategory.DEFENSIVE,
            "🚨 MISSILE INBOUND",
            "MWS alert | R-77 tracking | Time to impact: 8.5 sec",
            self._fighter.callsign,
        )

        self._fighter.status = FighterStatus.EVADING

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.NAVIGATION,
            "BREAK RIGHT",
            "Hard defensive break | Pulling 7G",
            self._fighter.callsign,
        )

        self._fighter.g_force = 7.2
        self._fighter.heading = (self._fighter.heading + 120) % 360

        # Deploy countermeasures
        self._fighter.defensive.chaff_count -= 10
        self._fighter.defensive.flare_count -= 10
        warning.countermeasures_deployed = True

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.DEFENSIVE,
            "COUNTERMEASURES",
            f"Chaff/Flare dispensed | Remaining: C:{self._fighter.defensive.chaff_count} F:{self._fighter.defensive.flare_count}",
            self._fighter.callsign,
        )

        self._fighter.defensive.ecm_active = True
        yield create_event(
            EventSeverity.INFO,
            EventCategory.DEFENSIVE,
            "ECM ACTIVE",
            "Electronic jamming engaged | Spoofing missile seeker",
            self._fighter.callsign,
        )

        # Missile defeated
        self._fighter.missile_warnings = []
        self._fighter.g_force = 1.0
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.DEFENSIVE,
            "MISSILE DEFEATED",
            "Threat neutralized | Countermeasures effective",
            self._fighter.callsign,
        )

    def generate_second_engagement(self) -> Generator[Event, None, None]:
        """Generate second target engagement."""
        self._fighter.status = FighterStatus.ATTACKING

        yield create_event(
            EventSeverity.INFO,
            EventCategory.SENSOR,
            "RE-ACQUIRING",
            "Searching for remaining bandit...",
            self._fighter.callsign,
        )

        # Update remaining contact
        if self._fighter.radar_contacts:
            self._fighter.radar_contacts[0].distance_nm = 15.0
            self._fighter.radar_contacts[0].is_locked = True

        yield create_event(
            EventSeverity.WARNING,
            EventCategory.SENSOR,
            "CONTACT LOCKED",
            "Bandit 2 locked | Range: 15nm | Dogfight range",
            self._fighter.callsign,
        )

        # Switch to short range missile
        for weapon in self._fighter.weapons:
            weapon.selected = False
        for weapon in self._fighter.weapons:
            if weapon.weapon_type == WeaponType.AAM_SHORT:
                weapon.selected = True
                break

        yield create_event(
            EventSeverity.INFO,
            EventCategory.WEAPON,
            "SIDEWINDER",
            "AIM-9X selected | IR lock | Good tone",
            self._fighter.callsign,
        )

        for weapon in self._fighter.weapons:
            if weapon.weapon_type == WeaponType.AAM_SHORT:
                weapon.quantity -= 1
                break

        yield create_event(
            EventSeverity.CRITICAL,
            EventCategory.WEAPON,
            "🚀 FOX TWO",
            "Sidewinder away | Tracking hot",
            self._fighter.callsign,
        )

        self._fighter.kills += 1
        self._fighter.radar_contacts = []
        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.WEAPON,
            "💥 SPLASH TWO",
            "Bandit 2 destroyed | Engagement complete",
            self._fighter.callsign,
        )

        # Complete objectives
        if len(self._fighter.mission_objectives) >= 2:
            self._fighter.mission_objectives[0] = ("Establish air superiority in sector ALPHA", True)
            self._fighter.mission_objectives[1] = ("Intercept unidentified contacts", True)

    def generate_rtb_sequence(self) -> Generator[Event, None, None]:
        """Generate return to base events."""
        self._fighter.status = FighterStatus.RTB
        self._fighter.master_arm = False

        yield create_event(
            EventSeverity.INFO,
            EventCategory.COMMUNICATION,
            "AWACS",
            "OVERLORD: Sector clear | RTB approved | Good hunting",
            self._fighter.callsign,
        )

        yield create_event(
            EventSeverity.INFO,
            EventCategory.MISSION,
            "RTB",
            f"Returning to base | Fuel: {self._fighter.fuel_percent}% | Heading home",
            self._fighter.callsign,
        )

        self._fighter.fuel_percent = max(25, self._fighter.fuel_percent - self._rng.randint(10, 20))

        yield create_event(
            EventSeverity.INFO,
            EventCategory.NAVIGATION,
            "DESCENT",
            "Beginning descent | Speed: Mach 0.85",
            self._fighter.callsign,
        )

        self._fighter.altitude_ft = 10000
        self._fighter.speed_mach = 0.6
        self._fighter.speed_knots = mach_to_knots(self._fighter.speed_mach, self._fighter.altitude_ft)

        yield create_event(
            EventSeverity.INFO,
            EventCategory.COMMUNICATION,
            "APPROACH",
            "Tower: Cleared visual approach runway 27L",
            self._fighter.callsign,
        )

        self._fighter.status = FighterStatus.LANDING
        self._fighter.landing_gear_down = True

        yield create_event(
            EventSeverity.INFO,
            EventCategory.NAVIGATION,
            "FINAL",
            "On final | Gear down and locked | 3 green",
            self._fighter.callsign,
        )

        self._fighter.altitude_ft = 0
        self._fighter.speed_knots = 0
        self._fighter.speed_mach = 0.0

        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.NAVIGATION,
            "🛬 TOUCHDOWN",
            "Wheels down | Deploying drag chute",
            self._fighter.callsign,
        )

        # Complete remaining objectives
        if len(self._fighter.mission_objectives) >= 4:
            self._fighter.mission_objectives[2] = ("Protect high-value assets", True)
            self._fighter.mission_objectives[3] = ("Maintain patrol for 90 minutes", True)

        yield create_event(
            EventSeverity.SUCCESS,
            EventCategory.MISSION,
            "🎖️ MISSION COMPLETE",
            f"Kills: {self._fighter.kills} | All objectives complete | Outstanding performance",
            self._fighter.callsign,
        )

    def generate_full_mission(self) -> Generator[Event, None, None]:
        """Generate a complete combat mission event sequence."""
        yield from self.generate_startup_sequence()
        yield from self.generate_engine_start()
        yield from self.generate_takeoff_sequence()
        yield from self.generate_cap_events()
        yield from self.generate_contact_detection()
        yield from self.generate_identification()
        yield from self.generate_combat_engagement()
        yield from self.generate_defensive_events()
        yield from self.generate_second_engagement()
        yield from self.generate_rtb_sequence()
