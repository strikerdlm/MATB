"""
UAV Operations Demo.

Demonstrates the UAV monitoring system with a complete reconnaissance mission.

Usage:
    python -m aircraft_monitor.demo_uav
"""

from __future__ import annotations

import sys

from rich.console import Console

from aircraft_monitor.events.uav_events import UAVEventGenerator
from aircraft_monitor.models.uav import UAV, UAVMission, UAVType
from aircraft_monitor.visualization.dashboard import MonitoringDashboard


def main() -> int:
    """Run the UAV demonstration mission."""
    console = Console()

    console.print("\n[bold bright_green]═══ UAV RECONNAISSANCE MISSION ═══[/bold bright_green]\n")
    console.print("[cyan]Platform:[/cyan] MQ-9 Reaper")
    console.print("[cyan]Mission:[/cyan] Intelligence, Surveillance, Reconnaissance")
    console.print("[cyan]Callsign:[/cyan] SHADOW-1")
    console.print("\n[dim]Initializing systems...[/dim]\n")

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
            gps_satellites=14,
            signal_strength=98,
        )

        # Create dashboard
        dashboard = MonitoringDashboard(event_delay=0.8)
        dashboard.set_uav(uav)

        # Generate and run mission
        event_generator = UAVEventGenerator(uav)
        dashboard.run_uav_simulation(event_generator.generate_full_mission())

        console.print("\n[bold bright_green]✓ UAV Mission Complete[/bold bright_green]\n")
        return 0

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Mission terminated by operator.[/yellow]\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
