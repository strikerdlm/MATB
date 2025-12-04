"""Rich UI panel components for aircraft monitoring."""

from __future__ import annotations

from collections import deque
from typing import Final

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from aircraft_monitor.events.base import Event
from aircraft_monitor.models.fighter import FighterAircraft, FighterStatus
from aircraft_monitor.models.uav import UAV, UAVStatus
from aircraft_monitor.visualization.themes import MILITARY_THEME, Theme

# Constants
MAX_EVENT_LOG_SIZE: Final[int] = 15
RADAR_DISPLAY_SIZE: Final[int] = 11


def create_gauge(
    value: int,
    max_value: int = 100,
    width: int = 20,
    filled_char: str = "█",
    empty_char: str = "░",
    color: str = "green",
    warning_threshold: int = 30,
    critical_threshold: int = 15,
) -> Text:
    """
    Create a visual gauge bar.

    Args:
        value: Current value
        max_value: Maximum value
        width: Width of the gauge in characters
        filled_char: Character for filled portion
        empty_char: Character for empty portion
        color: Default color
        warning_threshold: Value below which to show warning color
        critical_threshold: Value below which to show critical color

    Returns:
        Rich Text object representing the gauge
    """
    percentage = min(100, max(0, (value / max_value) * 100))
    filled_width = int((percentage / 100) * width)
    empty_width = width - filled_width

    # Determine color based on value
    if value <= critical_threshold:
        gauge_color = "red"
    elif value <= warning_threshold:
        gauge_color = "yellow"
    else:
        gauge_color = color

    gauge = Text()
    gauge.append(filled_char * filled_width, style=gauge_color)
    gauge.append(empty_char * empty_width, style="dim")
    gauge.append(f" {value}%", style=gauge_color)

    return gauge


def create_heading_indicator(heading: int) -> Text:
    """Create a visual heading indicator."""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((heading + 22.5) % 360 / 45)
    direction = directions[idx]

    indicator = Text()
    indicator.append("  ↑  \n", style="bright_green")
    indicator.append(f" {direction:^3} ", style="bright_green bold")
    indicator.append(f"\n{heading:03d}°", style="cyan")

    return indicator


class UAVStatusPanel:
    """UAV status display panel."""

    def __init__(self, uav: UAV, theme: Theme = MILITARY_THEME) -> None:
        """Initialize UAV status panel."""
        self._uav = uav
        self._theme = theme

    def render(self) -> Panel:
        """Render the UAV status panel."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="cyan", width=16)
        table.add_column("Value", style="white")

        # Status with color coding
        status_colors = {
            UAVStatus.PREFLIGHT: "yellow",
            UAVStatus.LAUNCHING: "cyan",
            UAVStatus.CLIMBING: "green",
            UAVStatus.CRUISING: "bright_green",
            UAVStatus.ON_STATION: "bright_green",
            UAVStatus.EXECUTING: "bright_yellow",
            UAVStatus.RTB: "yellow",
            UAVStatus.LANDING: "cyan",
            UAVStatus.EMERGENCY: "red",
            UAVStatus.OFFLINE: "red",
        }
        status_color = status_colors.get(self._uav.status, "white")
        status_text = Text(self._uav.status.value, style=f"bold {status_color}")
        table.add_row("Status", status_text)

        table.add_row("Type", Text(self._uav.uav_type.value, style="bright_cyan"))
        table.add_row("Mission", Text(self._uav.mission.value[:30], style="yellow"))

        # Altitude and Speed
        alt_text = Text(f"{self._uav.altitude_ft:,} ft", style="white")
        table.add_row("Altitude", alt_text)

        speed_text = Text(f"{self._uav.speed_knots} kts", style="white")
        table.add_row("Speed", speed_text)

        table.add_row("Heading", Text(f"{self._uav.heading:03d}°", style="cyan"))

        # Gauges
        table.add_row("Battery", create_gauge(self._uav.battery_percent, color="green"))
        table.add_row("Fuel", create_gauge(self._uav.fuel_percent, color="cyan"))
        table.add_row("Signal", create_gauge(self._uav.signal_strength, color="blue"))

        # GPS
        gps_style = "green" if self._uav.gps_satellites >= 6 else "yellow"
        table.add_row("GPS Sats", Text(f"{self._uav.gps_satellites} locked", style=gps_style))

        # Datalink
        datalink_style = "green" if self._uav.uplink_active else "red"
        table.add_row("Datalink", Text(self._uav.datalink_status, style=datalink_style))

        # Active sensors
        sensors = self._uav.sensors.active_sensors()
        sensor_text = Text(", ".join(sensors[:3]) if sensors else "None", style="cyan")
        table.add_row("Sensors", sensor_text)

        # Threats
        threat_count = len(self._uav.threats)
        if threat_count > 0:
            threat_style = "bold red"
            threat_text = f"⚠️ {threat_count} ACTIVE"
        else:
            threat_style = "green"
            threat_text = "CLEAR"
        table.add_row("Threats", Text(threat_text, style=threat_style))

        # Waypoint
        wp = self._uav.get_current_waypoint()
        wp_text = wp.name if wp else "COMPLETE"
        reached = sum(1 for w in self._uav.waypoints if w.is_reached)
        total = len(self._uav.waypoints)
        table.add_row("Waypoint", Text(f"{wp_text} ({reached}/{total})", style="yellow"))

        title = f"🛩️  {self._uav.callsign}"
        return Panel(
            table,
            title=title,
            border_style=self._theme.border,
            padding=(0, 1),
        )


class FighterStatusPanel:
    """Fighter aircraft status display panel."""

    def __init__(self, fighter: FighterAircraft, theme: Theme = MILITARY_THEME) -> None:
        """Initialize fighter status panel."""
        self._fighter = fighter
        self._theme = theme

    def render(self) -> Panel:
        """Render the fighter status panel."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="cyan", width=14)
        table.add_column("Value", style="white")

        # Status with color coding
        status_colors = {
            FighterStatus.HANGAR: "dim",
            FighterStatus.PREFLIGHT: "yellow",
            FighterStatus.TAXIING: "yellow",
            FighterStatus.TAKEOFF: "cyan",
            FighterStatus.CLIMBING: "green",
            FighterStatus.CRUISING: "bright_green",
            FighterStatus.COMBAT: "bold red",
            FighterStatus.EVADING: "bold yellow",
            FighterStatus.ATTACKING: "bold red",
            FighterStatus.PATROLLING: "bright_green",
            FighterStatus.REFUELING: "cyan",
            FighterStatus.RTB: "yellow",
            FighterStatus.LANDING: "cyan",
            FighterStatus.EMERGENCY: "bold red",
        }
        status_color = status_colors.get(self._fighter.status, "white")
        status_text = Text(self._fighter.status.value, style=f"bold {status_color}")
        table.add_row("Status", status_text)

        table.add_row("Aircraft", Text(self._fighter.fighter_type.value, style="bright_cyan"))
        table.add_row("Tail #", Text(self._fighter.tail_number, style="dim"))

        # Flight data
        table.add_row("Altitude", Text(f"{self._fighter.altitude_ft:,} ft", style="white"))
        table.add_row("Speed", Text(f"M {self._fighter.speed_mach:.2f}", style="white"))
        table.add_row("Heading", Text(f"{self._fighter.heading:03d}°", style="cyan"))

        # G-Force with warning
        g_style = "red" if self._fighter.g_force > 7 else "yellow" if self._fighter.g_force > 5 else "green"
        table.add_row("G-Force", Text(f"{self._fighter.g_force:.1f} G", style=g_style))

        # Fuel gauge
        table.add_row("Fuel", create_gauge(self._fighter.fuel_percent, color="cyan"))

        # Master arm
        arm_style = "bold red" if self._fighter.master_arm else "green"
        arm_text = "🔴 ARMED" if self._fighter.master_arm else "🟢 SAFE"
        table.add_row("Master Arm", Text(arm_text, style=arm_style))

        # Weapons
        weapons_ready = self._fighter.get_ready_weapons_count()
        table.add_row("Weapons", Text(f"{weapons_ready} ready", style="yellow"))

        # Radar contacts
        hostile_count = self._fighter.get_hostile_count()
        contact_style = "red" if hostile_count > 0 else "green"
        contact_text = f"⚠️ {hostile_count} HOSTILE" if hostile_count > 0 else "CLEAR"
        table.add_row("Contacts", Text(contact_text, style=contact_style))

        # Missiles
        if self._fighter.has_incoming_missiles():
            missile_text = Text("🚨 INCOMING!", style="bold white on red")
        else:
            missile_text = Text("CLEAR", style="green")
        table.add_row("Missiles", missile_text)

        # Kills
        if self._fighter.kills > 0:
            table.add_row("Kills", Text(f"💥 {self._fighter.kills}", style="bold yellow"))

        # Countermeasures
        cm_text = f"C:{self._fighter.defensive.chaff_count} F:{self._fighter.defensive.flare_count}"
        table.add_row("CM", Text(cm_text, style="cyan"))

        title = f"✈️  {self._fighter.callsign} | {self._fighter.tail_number}"
        return Panel(
            table,
            title=title,
            border_style=self._theme.border,
            padding=(0, 1),
        )


class EventLogPanel:
    """Scrolling event log panel."""

    def __init__(self, max_events: int = MAX_EVENT_LOG_SIZE, theme: Theme = MILITARY_THEME) -> None:
        """Initialize event log panel."""
        self._events: deque[Event] = deque(maxlen=max_events)
        self._theme = theme

    def add_event(self, event: Event) -> None:
        """Add an event to the log."""
        self._events.append(event)

    def clear(self) -> None:
        """Clear all events."""
        self._events.clear()

    def render(self) -> Panel:
        """Render the event log panel."""
        if not self._events:
            content = Text("Awaiting events...", style="dim italic")
        else:
            lines: list[Text] = []
            for event in self._events:
                line = Text()
                line.append(f"[{event.format_timestamp()}] ", style="dim")
                line.append(f"{event.icon} ", style="white")
                line.append(f"{event.title}", style=event.color)
                if event.description:
                    line.append(f"\n    └─ {event.description[:60]}", style="dim")
                lines.append(line)

            content = Group(*lines)

        return Panel(
            content,
            title="📋 EVENT LOG",
            border_style=self._theme.border,
            padding=(0, 1),
        )


class RadarPanel:
    """ASCII radar display panel."""

    def __init__(self, theme: Theme = MILITARY_THEME) -> None:
        """Initialize radar panel."""
        self._theme = theme
        self._contacts: list[tuple[int, float, str]] = []  # bearing, distance, classification
        self._sweep_angle = 0

    def update_contacts(self, contacts: list[tuple[int, float, str]]) -> None:
        """Update radar contacts."""
        self._contacts = contacts

    def advance_sweep(self) -> None:
        """Advance the radar sweep angle."""
        self._sweep_angle = (self._sweep_angle + 30) % 360

    def render(self) -> Panel:
        """Render the radar panel."""
        size = RADAR_DISPLAY_SIZE
        center = size // 2

        # Initialize grid
        grid = [[" " for _ in range(size)] for _ in range(size)]

        # Draw concentric circles (range rings)
        for r in [2, 4]:
            for angle in range(0, 360, 15):
                import math
                x = int(center + r * math.cos(math.radians(angle)))
                y = int(center + r * math.sin(math.radians(angle)))
                if 0 <= x < size and 0 <= y < size:
                    grid[y][x] = "·"

        # Draw cardinal directions
        grid[0][center] = "N"
        grid[size - 1][center] = "S"
        grid[center][0] = "W"
        grid[center][size - 1] = "E"

        # Draw center (own aircraft)
        grid[center][center] = "◈"

        # Draw sweep line
        import math
        sweep_rad = math.radians(self._sweep_angle)
        for r in range(1, center + 1):
            x = int(center + r * math.cos(sweep_rad))
            y = int(center - r * math.sin(sweep_rad))
            if 0 <= x < size and 0 <= y < size and grid[y][x] == " ":
                grid[y][x] = "░"

        # Draw contacts
        for bearing, distance, classification in self._contacts:
            # Normalize distance to grid
            r = min(center - 1, int((distance / 100) * center))
            rad = math.radians(90 - bearing)  # Convert bearing to math angle
            x = int(center + r * math.cos(rad))
            y = int(center - r * math.sin(rad))

            if 0 <= x < size and 0 <= y < size:
                if classification == "HOSTILE":
                    grid[y][x] = "▲"
                elif classification == "FRIENDLY":
                    grid[y][x] = "●"
                else:
                    grid[y][x] = "?"

        # Build display text
        radar_text = Text()
        for row in grid:
            for char in row:
                if char == "◈":
                    radar_text.append(char, style="bold bright_green")
                elif char == "▲":
                    radar_text.append(char, style="bold red")
                elif char == "●":
                    radar_text.append(char, style="bold blue")
                elif char == "?":
                    radar_text.append(char, style="bold yellow")
                elif char in "NSEW":
                    radar_text.append(char, style="cyan")
                elif char == "░":
                    radar_text.append(char, style="green")
                elif char == "·":
                    radar_text.append(char, style="dim green")
                else:
                    radar_text.append(char, style="dim")
            radar_text.append("\n")

        # Legend
        legend = Text()
        legend.append("\n◈", style="bright_green")
        legend.append(" Own  ", style="dim")
        legend.append("▲", style="red")
        legend.append(" Hostile  ", style="dim")
        legend.append("?", style="yellow")
        legend.append(" Unknown", style="dim")

        content = Group(Align.center(radar_text), Align.center(legend))

        return Panel(
            content,
            title="📡 RADAR",
            border_style=self._theme.border,
        )


class MissionPanel:
    """Mission objectives and progress panel."""

    def __init__(self, theme: Theme = MILITARY_THEME) -> None:
        """Initialize mission panel."""
        self._theme = theme
        self._objectives: list[tuple[str, bool]] = []
        self._mission_time = 0
        self._mission_name = "UNKNOWN"

    def set_mission(self, name: str, objectives: list[tuple[str, bool]]) -> None:
        """Set mission name and objectives."""
        self._mission_name = name
        self._objectives = objectives

    def update_objective(self, index: int, completed: bool) -> None:
        """Update objective completion status."""
        if 0 <= index < len(self._objectives):
            name = self._objectives[index][0]
            self._objectives[index] = (name, completed)

    def set_time(self, seconds: int) -> None:
        """Set mission elapsed time."""
        self._mission_time = seconds

    def render(self) -> Panel:
        """Render the mission panel."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", width=3)
        table.add_column("Objective")

        if not self._objectives:
            table.add_row("", Text("No objectives loaded", style="dim italic"))
        else:
            for objective, completed in self._objectives:
                if completed:
                    status = Text("✓", style="bold green")
                    obj_text = Text(objective[:40], style="dim")
                else:
                    status = Text("○", style="yellow")
                    obj_text = Text(objective[:40], style="white")
                table.add_row(status, obj_text)

        # Calculate progress
        if self._objectives:
            completed_count = sum(1 for _, done in self._objectives if done)
            total = len(self._objectives)
            progress_pct = int((completed_count / total) * 100)

            progress_bar = create_gauge(
                progress_pct,
                width=25,
                filled_char="━",
                empty_char="─",
                color="bright_green",
                warning_threshold=0,
                critical_threshold=0,
            )
        else:
            progress_bar = Text("─" * 25, style="dim")

        # Format time
        minutes = self._mission_time // 60
        seconds = self._mission_time % 60
        time_text = Text(f"⏱️ {minutes:02d}:{seconds:02d}", style="cyan")

        content = Group(
            table,
            Text(""),
            Text("Progress: ", style="dim"),
            progress_bar,
            Text(""),
            time_text,
        )

        return Panel(
            content,
            title=f"🎖️ MISSION: {self._mission_name}",
            border_style=self._theme.border,
            padding=(0, 1),
        )


class WeaponsPanel:
    """Weapons status panel for fighters."""

    def __init__(self, theme: Theme = MILITARY_THEME) -> None:
        """Initialize weapons panel."""
        self._theme = theme
        self._weapons: list[tuple[str, int, bool, bool]] = []  # name, qty, ready, selected

    def update_weapons(self, weapons: list[tuple[str, int, bool, bool]]) -> None:
        """Update weapons list."""
        self._weapons = weapons

    def render(self) -> Panel:
        """Render the weapons panel."""
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Weapon", style="cyan")
        table.add_column("Qty", justify="center")
        table.add_column("Status", justify="center")

        for name, qty, ready, selected in self._weapons:
            # Format name (shorten if needed)
            short_name = name.split()[-1] if len(name) > 12 else name

            # Quantity
            qty_style = "red" if qty == 0 else "yellow" if qty <= 2 else "green"
            qty_text = Text(str(qty), style=qty_style)

            # Status
            if selected:
                status = Text("◉ SEL", style="bold bright_yellow")
            elif ready:
                status = Text("● RDY", style="green")
            else:
                status = Text("○ ---", style="dim")

            table.add_row(short_name, qty_text, status)

        return Panel(
            table,
            title="🎯 WEAPONS",
            border_style=self._theme.border,
            padding=(0, 1),
        )


class EnginePanel:
    """Engine status panel."""

    def __init__(self, theme: Theme = MILITARY_THEME) -> None:
        """Initialize engine panel."""
        self._theme = theme
        self._engine1_rpm = 0
        self._engine2_rpm = 0
        self._engine1_temp = 0
        self._engine2_temp = 0
        self._ab1_active = False
        self._ab2_active = False

    def update(
        self,
        e1_rpm: int,
        e2_rpm: int,
        e1_temp: int,
        e2_temp: int,
        ab1: bool,
        ab2: bool,
    ) -> None:
        """Update engine status."""
        self._engine1_rpm = e1_rpm
        self._engine2_rpm = e2_rpm
        self._engine1_temp = e1_temp
        self._engine2_temp = e2_temp
        self._ab1_active = ab1
        self._ab2_active = ab2

    def render(self) -> Panel:
        """Render the engine panel."""
        lines: list[Text] = []

        # Engine 1
        e1_bar = create_gauge(self._engine1_rpm, width=15, color="cyan", warning_threshold=0, critical_threshold=0)
        ab1_indicator = Text(" 🔥", style="bold orange1") if self._ab1_active else Text("   ", style="dim")
        e1_line = Text("E1: ", style="cyan")
        lines.append(Group(e1_line, e1_bar, ab1_indicator))

        # Engine 2
        e2_bar = create_gauge(self._engine2_rpm, width=15, color="cyan", warning_threshold=0, critical_threshold=0)
        ab2_indicator = Text(" 🔥", style="bold orange1") if self._ab2_active else Text("   ", style="dim")
        e2_line = Text("E2: ", style="cyan")
        lines.append(Group(e2_line, e2_bar, ab2_indicator))

        # Temps
        temp_line = Text(f"EGT: {self._engine1_temp}°C / {self._engine2_temp}°C", style="dim")
        lines.append(temp_line)

        content = Group(*lines)

        return Panel(
            content,
            title="🔧 ENGINES",
            border_style=self._theme.border,
            padding=(0, 1),
        )
