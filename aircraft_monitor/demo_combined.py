"""
Combined Operations Demo.

Demonstrates monitoring multiple aircraft simultaneously with
coordinated UAV and fighter operations.

Usage:
    python -m aircraft_monitor.demo_combined
"""

from __future__ import annotations

import sys

from rich.console import Console

from aircraft_monitor.events.fighter_events import FighterEventGenerator
from aircraft_monitor.events.uav_events import UAVEventGenerator
from aircraft_monitor.models.fighter import FighterAircraft, FighterType
from aircraft_monitor.models.uav import UAV, UAVMission, UAVType
from aircraft_monitor.visualization.dashboard import MonitoringDashboard


def main() -> int:
    """Run the combined operations demonstration."""
    console = Console()

    console.print("\n[bold bright_green]═══ JOINT OPERATIONS CENTER ═══[/bold bright_green]\n")
    console.print("[bold cyan]Multi-Platform Monitoring Active[/bold cyan]\n")
    console.print("[yellow]UAV Platform:[/yellow]")
    console.print("  • Type: MQ-9 Reaper")
    console.print("  • Callsign: SHADOW-1")
    console.print("  • Mission: ISR Support\n")
    console.print("[yellow]Fighter Platform:[/yellow]")
    console.print("  • Type: F-22 Raptor")
    console.print("  • Callsign: VIPER")
    console.print("  • Mission: Combat Air Patrol\n")
    console.print("[dim]Initializing joint tactical datalink...[/dim]\n")

    try:
        import time
        if sys.stdout.isatty():
            time.sleep(2.0)

        # Create UAV
        uav = UAV(
            callsign="SHADOW-1",
            uav_type=UAVType.RECONNAISSANCE,
            mission=UAVMission.ISR,
            battery_percent=100,
            fuel_percent=100,
        )

        # Create fighter
        fighter = FighterAircraft(
            callsign="VIPER",
            tail_number="AF-192",
            fighter_type=FighterType.AIR_SUPERIORITY,
            fuel_percent=100,
        )

        # Create dashboard
        dashboard = MonitoringDashboard(event_delay=0.5)
        dashboard.set_uav(uav)
        dashboard.set_fighter(fighter)

        # Generate events
        uav_gen = UAVEventGenerator(uav)
        fighter_gen = FighterEventGenerator(fighter)

        # Run combined simulation
        dashboard.run_combined_simulation(
            uav_gen.generate_full_mission(),
            fighter_gen.generate_full_mission(),
        )

        console.print("\n[bold bright_green]✓ Joint Operations Complete[/bold bright_green]\n")
        return 0

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operations terminated by command.[/yellow]\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
