"""
Main entry point for the Aircraft Monitoring System.

Usage:
    python -m aircraft_monitor [mode]

Modes:
    uav      - Run UAV reconnaissance mission simulation
    fighter  - Run fighter combat mission simulation
    combined - Run combined operations simulation (default)
    experiment - Run MATB-inspired human-factors protocol
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Final

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from aircraft_monitor.research import ResearchExperimentRunner, ResearchModality
from aircraft_monitor.simulation.engine import SimulationEngine

VALID_MODES: Final[frozenset[str]] = frozenset({"uav", "fighter", "combined", "experiment"})
DEFAULT_EVENT_DELAY_SEC: Final[float] = 0.7
MIN_EVENT_DELAY_SEC: Final[float] = 0.05
MAX_EVENT_DELAY_SEC: Final[float] = 5.0
DEFAULT_RESEARCH_SEED: Final[int] = 42


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
    menu.append("    [4] ", style="yellow")
    menu.append("experiment", style="bold white")
    menu.append(" - MATB-inspired human-factors protocol\n", style="dim")

    console.print(Panel(menu, border_style="cyan"))


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser for runtime options."""
    parser = argparse.ArgumentParser(
        prog="python -m aircraft_monitor",
        description="UAV and fighter aircraft monitoring simulator",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        help="Simulation mode: uav, fighter, combined, experiment",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force non-interactive output (no full-screen dashboard)",
    )
    parser.add_argument(
        "--event-delay",
        type=float,
        default=DEFAULT_EVENT_DELAY_SEC,
        help=(
            "Delay between events in seconds "
            f"({MIN_EVENT_DELAY_SEC}..{MAX_EVENT_DELAY_SEC})"
        ),
    )
    parser.add_argument(
        "--participant-id",
        default="pilot-001",
        help="Research participant identifier for experiment mode",
    )
    parser.add_argument(
        "--session-id",
        default="session-001",
        help="Research session identifier for experiment mode",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RESEARCH_SEED,
        help="Deterministic research scenario seed",
    )
    parser.add_argument(
        "--research-modality",
        choices=[modality.value for modality in ResearchModality],
        default=ResearchModality.COMBINED.value,
        help="Experiment modality: uas, fighter, or combined",
    )
    parser.add_argument(
        "--research-output-dir",
        type=Path,
        default=None,
        help="Directory for experiment JSONL and summary outputs",
    )
    return parser


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    console = Console()

    parser = build_parser()
    args = parser.parse_args()

    event_delay = args.event_delay
    if not math.isfinite(event_delay):
        console.print("\n  [red]Error:[/red] --event-delay must be finite.\n")
        return 1
    if event_delay < MIN_EVENT_DELAY_SEC or event_delay > MAX_EVENT_DELAY_SEC:
        console.print(
            f"\n  [red]Error:[/red] --event-delay must be between "
            f"{MIN_EVENT_DELAY_SEC} and {MAX_EVENT_DELAY_SEC} seconds.\n"
        )
        return 1

    # Parse mode (positional arg or interactive prompt)
    if args.mode:
        mode = args.mode.lower()
    else:
        # Non-interactive environments (e.g., redirected stdin) must not block on input().
        if not sys.stdin.isatty():
            mode = "combined"
        else:
            # Interactive mode selection
            print_banner(console)
            print_menu(console)

            try:
                console.print(
                    "\n  Enter mode (uav/fighter/combined/experiment) or number: ",
                    style="cyan",
                    end="",
                )
                user_input = input().strip().lower()

                # Map numbers to modes
                mode_map = {
                    "1": "uav",
                    "2": "fighter",
                    "3": "combined",
                    "4": "experiment",
                }
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
        if sys.stdout.isatty():
            time.sleep(1.5)  # Brief pause before starting

        engine = SimulationEngine(
            event_delay=event_delay,
            headless=True if args.headless else None,
        )

        if mode == "experiment":
            modality = ResearchModality(args.research_modality)
            output_dir = args.research_output_dir
            if output_dir is None:
                runner = ResearchExperimentRunner(
                    event_delay=event_delay,
                    headless=True if args.headless else None,
                )
            else:
                runner = ResearchExperimentRunner(
                    event_delay=event_delay,
                    headless=True if args.headless else None,
                    output_dir=output_dir,
                )
            runner.run_default_protocol(
                participant_id=args.participant_id,
                session_id=args.session_id,
                modality=modality,
                seed=args.seed,
            )
        elif mode == "uav":
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
