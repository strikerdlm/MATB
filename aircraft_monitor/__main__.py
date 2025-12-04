"""
Main entry point for the Aircraft Monitoring System.

Usage:
    python -m aircraft_monitor [mode]

Modes:
    uav      - Run UAV reconnaissance mission simulation
    fighter  - Run fighter combat mission simulation
    combined - Run combined operations simulation (default)
"""

from __future__ import annotations

import sys
from typing import Final

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from aircraft_monitor.simulation.engine import SimulationEngine

VALID_MODES: Final[frozenset[str]] = frozenset({"uav", "fighter", "combined"})


def print_banner(console: Console) -> None:
    """Print the application banner."""
    banner = Text()
    banner.append(
        """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ✈️  AIRCRAFT MONITORING SYSTEM  🛩️                          ║
    ║                                                               ║
    ║   Real-time UAV & Fighter Aircraft Operations Monitoring     ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """,
        style="bright_green",
    )

    console.print(banner)


def print_menu(console: Console) -> None:
    """Print the mode selection menu."""
    menu = Text()
    menu.append("\n  Select Simulation Mode:\n\n", style="bold cyan")
    menu.append("    [1] ", style="yellow")
    menu.append("uav", style="bold white")
    menu.append("      - MQ-9 Reaper Reconnaissance Mission\n", style="dim")
    menu.append("    [2] ", style="yellow")
    menu.append("fighter", style="bold white")
    menu.append("  - F-22 Raptor Combat Air Patrol\n", style="dim")
    menu.append("    [3] ", style="yellow")
    menu.append("combined", style="bold white")
    menu.append(" - Joint Operations (UAV + Fighter)\n", style="dim")

    console.print(Panel(menu, border_style="cyan"))


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    console = Console()

    # Parse command line arguments
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    else:
        # Interactive mode selection
        print_banner(console)
        print_menu(console)

        try:
            console.print("\n  Enter mode (uav/fighter/combined) or number: ", style="cyan", end="")
            user_input = input().strip().lower()

            # Map numbers to modes
            mode_map = {"1": "uav", "2": "fighter", "3": "combined"}
            mode = mode_map.get(user_input, user_input)

        except (KeyboardInterrupt, EOFError):
            console.print("\n\n  Cancelled.", style="yellow")
            return 0

    # Validate mode
    if mode not in VALID_MODES:
        console.print(
            f"\n  [red]Error:[/red] Invalid mode '{mode}'. "
            f"Valid modes: {', '.join(sorted(VALID_MODES))}\n"
        )
        return 1

    # Run simulation
    console.print(f"\n  [bright_green]Starting {mode.upper()} simulation...[/bright_green]\n")
    console.print("  [dim]Press Ctrl+C at any time to exit[/dim]\n")

    try:
        import time
        time.sleep(1.5)  # Brief pause before starting

        engine = SimulationEngine(event_delay=0.7)

        if mode == "uav":
            engine.run_uav_mission()
        elif mode == "fighter":
            engine.run_fighter_mission()
        else:  # combined
            engine.run_combined_mission()

        console.print("\n  [bright_green]✓ Simulation complete![/bright_green]\n")
        return 0

    except KeyboardInterrupt:
        console.print("\n\n  [yellow]Simulation terminated by user.[/yellow]\n")
        return 0
    except Exception as e:
        console.print(f"\n  [red]Error:[/red] {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
