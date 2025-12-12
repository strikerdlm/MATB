"""
Fighter Aircraft Demo.

Demonstrates the fighter monitoring system with a combat air patrol mission.

Usage:
    python -m aircraft_monitor.demo_fighter
"""

from __future__ import annotations

import sys

from rich.console import Console

from aircraft_monitor.events.fighter_events import FighterEventGenerator
from aircraft_monitor.models.fighter import FighterAircraft, FighterType
from aircraft_monitor.visualization.dashboard import MonitoringDashboard


def main() -> int:
    """Run the fighter demonstration mission."""
    console = Console()

    console.print("\n[bold bright_green]═══ COMBAT AIR PATROL MISSION ═══[/bold bright_green]\n")
    console.print("[cyan]Aircraft:[/cyan] F-22 Raptor")
    console.print("[cyan]Mission:[/cyan] Combat Air Patrol - Sector ALPHA")
    console.print("[cyan]Pilot:[/cyan] VIPER")
    console.print("[cyan]Tail #:[/cyan] AF-192")
    console.print("\n[dim]Initializing avionics...[/dim]\n")

    try:
        import time
        if sys.stdout.isatty():
            time.sleep(2.0)

        # Create fighter
        fighter = FighterAircraft(
            callsign="VIPER",
            tail_number="AF-192",
            fighter_type=FighterType.AIR_SUPERIORITY,
            fuel_percent=100,
            oxygen_percent=100,
        )

        # Create dashboard
        dashboard = MonitoringDashboard(event_delay=0.7)
        dashboard.set_fighter(fighter)

        # Generate and run mission
        event_generator = FighterEventGenerator(fighter)
        dashboard.run_fighter_simulation(event_generator.generate_full_mission())

        console.print("\n[bold bright_green]✓ Combat Mission Complete[/bold bright_green]\n")
        return 0

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Mission terminated by pilot.[/yellow]\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
