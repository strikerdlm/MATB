"""Simulation engine for running aircraft scenarios."""

from __future__ import annotations

from typing import Final

from aircraft_monitor.events.fighter_events import FighterEventGenerator
from aircraft_monitor.events.uav_events import UAVEventGenerator
from aircraft_monitor.models.fighter import FighterAircraft, FighterType
from aircraft_monitor.models.uav import UAV, UAVMission, UAVType
from aircraft_monitor.visualization.dashboard import MonitoringDashboard

# Default simulation parameters
DEFAULT_EVENT_DELAY: Final[float] = 0.7


class SimulationEngine:
    """
    Simulation engine for aircraft monitoring scenarios.

    Provides pre-configured scenarios for UAV and fighter operations.
    """

    def __init__(self, event_delay: float = DEFAULT_EVENT_DELAY) -> None:
        """
        Initialize the simulation engine.

        Args:
            event_delay: Delay between events in seconds
        """
        self._event_delay = event_delay

    def create_recon_uav(self) -> UAV:
        """Create a reconnaissance UAV configuration."""
        return UAV(
            callsign="SHADOW-1",
            uav_type=UAVType.RECONNAISSANCE,
            mission=UAVMission.ISR,
        )

    def create_surveillance_uav(self) -> UAV:
        """Create a surveillance UAV configuration."""
        return UAV(
            callsign="GLOBAL-7",
            uav_type=UAVType.SURVEILLANCE,
            mission=UAVMission.PATROL,
        )

    def create_f22_fighter(self) -> FighterAircraft:
        """Create an F-22 Raptor configuration."""
        return FighterAircraft(
            callsign="VIPER",
            tail_number="AF-192",
            fighter_type=FighterType.AIR_SUPERIORITY,
        )

    def create_f35_fighter(self) -> FighterAircraft:
        """Create an F-35 Lightning II configuration."""
        return FighterAircraft(
            callsign="PHANTOM",
            tail_number="AF-305",
            fighter_type=FighterType.MULTIROLE,
        )

    def run_uav_mission(self) -> None:
        """Run a complete UAV reconnaissance mission."""
        uav = self.create_recon_uav()
        dashboard = MonitoringDashboard(event_delay=self._event_delay)
        dashboard.set_uav(uav)

        event_gen = UAVEventGenerator(uav)
        dashboard.run_uav_simulation(event_gen.generate_full_mission())

    def run_fighter_mission(self) -> None:
        """Run a complete fighter combat mission."""
        fighter = self.create_f22_fighter()
        dashboard = MonitoringDashboard(event_delay=self._event_delay)
        dashboard.set_fighter(fighter)

        event_gen = FighterEventGenerator(fighter)
        dashboard.run_fighter_simulation(event_gen.generate_full_mission())

    def run_combined_mission(self) -> None:
        """Run a combined UAV and fighter mission."""
        uav = self.create_recon_uav()
        fighter = self.create_f22_fighter()

        dashboard = MonitoringDashboard(event_delay=self._event_delay)
        dashboard.set_uav(uav)
        dashboard.set_fighter(fighter)

        uav_gen = UAVEventGenerator(uav)
        fighter_gen = FighterEventGenerator(fighter)

        dashboard.run_combined_simulation(
            uav_gen.generate_full_mission(),
            fighter_gen.generate_full_mission(),
        )
