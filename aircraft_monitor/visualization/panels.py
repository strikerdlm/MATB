"""Rich UI panel components for aircraft monitoring.

This module aims to keep displayed values physically consistent and readable:
- Every numeric field is presented with units.
- Derived values (e.g., TAS in knots) are computed from already-simulated fields.
- Trend visuals are bounded (fixed history window) to avoid unbounded growth.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Final

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.table import Table
from rich.text import Text

from aircraft_monitor.events.base import Event
from aircraft_monitor.models.fighter import FighterAircraft, FighterStatus
from aircraft_monitor.models.uav import UAV, UAVStatus
from aircraft_monitor.visualization.themes import MILITARY_THEME, Theme

# Constants
MAX_EVENT_LOG_SIZE: Final[int] = 15
RADAR_DISPLAY_SIZE: Final[int] = 11
SPARKLINE_HISTORY: Final[int] = 30


SPARK_CHARS: Final[tuple[str, ...]] = ("▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")


def _clamp_int(value: int, low: int, high: int) -> int:
    """Clamp value into [low, high]."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def _format_deg(value: float, *, width: int = 3) -> str:
    """Format heading/bearing degrees as 000°."""
    deg = int(round(value)) % 360
    return f"{deg:0{width}d}°"


def _sparkline(values: deque[float], *, low: float | None = None, high: float | None = None) -> Text:
    """Render a bounded-history sparkline.

    Args:
        values: Deque of numeric values.
        low: Optional fixed lower bound for scaling.
        high: Optional fixed upper bound for scaling.

    Returns:
        Rich Text sparkline. Empty if no values.
    """
    if not values:
        return Text(" " * 8, style="dim")

    vmin = min(values) if low is None else float(low)
    vmax = max(values) if high is None else float(high)
    if vmax <= vmin:
        # Flat line.
        return Text(SPARK_CHARS[0] * min(len(values), 16), style="dim")

    chars: list[str] = []
    # Cap visible width to keep panels stable across terminals.
    take = min(len(values), 16)
    start = len(values) - take
    for i, v in enumerate(values):
        if i < start:
            continue
        t = (float(v) - vmin) / (vmax - vmin)
        idx = int(round(t * (len(SPARK_CHARS) - 1)))
        idx = _clamp_int(idx, 0, len(SPARK_CHARS) - 1)
        chars.append(SPARK_CHARS[idx])
    return Text("".join(chars), style="bright_green")


def _chip(label: str, *, style: str, pad: int = 1) -> Text:
    """Small status 'chip' with consistent styling."""
    text = Text(f"{' ' * pad}{label}{' ' * pad}")
    text.stylize(style)
    return text


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


@dataclass(slots=True)
class _History:
    """Bounded metric history for trend visuals."""

    altitude_ft: deque[float]
    speed: deque[float]
    fuel_pct: deque[float]
    battery_pct: deque[float]
    signal_pct: deque[float]
    g_force: deque[float]


class UAVStatusPanel:
    """UAV status display panel."""

    def __init__(self, uav: UAV, theme: Theme = MILITARY_THEME) -> None:
        """Initialize UAV status panel."""
        self._uav = uav
        self._theme = theme
        self._hist = _History(
            altitude_ft=deque(maxlen=SPARKLINE_HISTORY),
            speed=deque(maxlen=SPARKLINE_HISTORY),
            fuel_pct=deque(maxlen=SPARKLINE_HISTORY),
            battery_pct=deque(maxlen=SPARKLINE_HISTORY),
            signal_pct=deque(maxlen=SPARKLINE_HISTORY),
            g_force=deque(maxlen=SPARKLINE_HISTORY),
        )

    def _tick(self) -> None:
        """Update bounded histories from current UAV state."""
        self._hist.altitude_ft.append(float(self._uav.altitude_ft))
        self._hist.speed.append(float(self._uav.speed_knots))
        self._hist.fuel_pct.append(float(self._uav.fuel_percent))
        self._hist.battery_pct.append(float(self._uav.battery_percent))
        self._hist.signal_pct.append(float(self._uav.signal_strength))

    def render(self) -> Panel:
        """Render the UAV status panel."""
        self._tick()

        top = Table.grid(padding=(0, 1))
        top.add_column(justify="left", ratio=1)
        top.add_column(justify="right")

        # Status chips
        status_colors = {
            UAVStatus.PREFLIGHT: "black on yellow",
            UAVStatus.LAUNCHING: "black on cyan",
            UAVStatus.CLIMBING: "black on bright_green",
            UAVStatus.CRUISING: "black on bright_green",
            UAVStatus.ON_STATION: "black on bright_green",
            UAVStatus.EXECUTING: "black on bright_yellow",
            UAVStatus.RTB: "black on yellow",
            UAVStatus.LANDING: "black on cyan",
            UAVStatus.EMERGENCY: "bold white on red",
            UAVStatus.OFFLINE: "bold white on red",
        }
        status_style = status_colors.get(self._uav.status, "bold white")
        chips = Text()
        chips.append_text(_chip(self._uav.status.value.upper(), style=status_style))
        chips.append(" ")
        chips.append_text(_chip(self._uav.uav_type.value, style="bold black on bright_cyan"))
        chips.append(" ")
        chips.append_text(_chip("AP" if self._uav.autopilot_engaged else "MAN", style="black on green" if self._uav.autopilot_engaged else "black on yellow"))
        top.add_row(chips, Text(self._uav.callsign, style="bold bright_green"))

        # Primary telemetry strip
        telem = Table.grid(padding=(0, 1))
        telem.add_column(ratio=1)
        telem.add_column(ratio=1)
        telem.add_column(ratio=1)
        telem.add_row(
            Text(f"ALT  {self._uav.altitude_ft:>6,} ft  ({int(round(self._uav.altitude_ft * 0.3048)):>5,} m)", style="white"),
            Text(f"IAS  {self._uav.speed_knots:>4} kt   ({int(round(self._uav.speed_knots * 0.514444)):>3} m/s)", style="white"),
            Text(f"HDG  {_format_deg(self._uav.heading)}", style="cyan"),
        )

        trends = Table.grid(padding=(0, 1))
        trends.add_column("Metric", style="dim", width=8)
        trends.add_column("Now", justify="right", width=6)
        trends.add_column("Trend", justify="left")
        trends.add_row("ALT", f"{self._uav.altitude_ft:,.0f}", _sparkline(self._hist.altitude_ft))
        trends.add_row("SPD", f"{self._uav.speed_knots:.0f}", _sparkline(self._hist.speed, low=0.0, high=300.0))
        trends.add_row("BAT", f"{self._uav.battery_percent:>3d}%", _sparkline(self._hist.battery_pct, low=0.0, high=100.0))
        trends.add_row("FUEL", f"{self._uav.fuel_percent:>3d}%", _sparkline(self._hist.fuel_pct, low=0.0, high=100.0))
        trends.add_row("LINK", f"{self._uav.signal_strength:>3d}%", _sparkline(self._hist.signal_pct, low=0.0, high=100.0))

        # Navigation / mission context
        nav = Table.grid(padding=(0, 1))
        nav.add_column("Label", style="cyan", width=10)
        nav.add_column("Value", style="white")
        wp = self._uav.get_current_waypoint()
        reached = sum(1 for w in self._uav.waypoints if w.is_reached)
        total = len(self._uav.waypoints)
        wp_text = wp.name if wp else "COMPLETE"
        nav.add_row("Mission", Text(self._uav.mission.value[:42], style="yellow"))
        nav.add_row("WP", Text(f"{wp_text}  ({reached}/{total})", style="yellow"))
        nav.add_row("Pos", Text(f"{self._uav.latitude:.4f}°, {self._uav.longitude:.4f}°", style="dim"))
        gps_style = "green" if self._uav.gps_satellites >= 6 else "yellow"
        nav.add_row("GPS", Text(f"{self._uav.gps_satellites} sats", style=gps_style))
        dl_style = "green" if self._uav.uplink_active else "bold white on red"
        nav.add_row("Datalink", Text(self._uav.datalink_status, style=dl_style))

        # Threats
        threat_count = len(self._uav.threats)
        if threat_count > 0:
            threat_badge = Text("⚠ THREATS", style="bold white on red")
            threat_line = Text(f"{threat_count} contact(s)", style="bold red")
        else:
            threat_badge = Text("THREAT", style="black on green")
            threat_line = Text("CLEAR", style="green")

        sensors = self._uav.sensors.active_sensors()
        sensors_text = Text(", ".join(sensors[:4]) if sensors else "None", style="cyan")
        lower = Group(
            nav,
            Text(""),
            threat_badge,
            threat_line,
            Text("Sensors", style="dim"),
            sensors_text,
        )

        content = Group(top, telem, Text(""), trends, Text(""), lower)

        return Panel(
            content,
            title="UAV STATUS",
            border_style=self._theme.border,
            padding=(0, 1),
        )


class FighterStatusPanel:
    """Fighter aircraft status display panel."""

    def __init__(self, fighter: FighterAircraft, theme: Theme = MILITARY_THEME) -> None:
        """Initialize fighter status panel."""
        self._fighter = fighter
        self._theme = theme
        self._hist = _History(
            altitude_ft=deque(maxlen=SPARKLINE_HISTORY),
            speed=deque(maxlen=SPARKLINE_HISTORY),
            fuel_pct=deque(maxlen=SPARKLINE_HISTORY),
            battery_pct=deque(maxlen=SPARKLINE_HISTORY),
            signal_pct=deque(maxlen=SPARKLINE_HISTORY),
            g_force=deque(maxlen=SPARKLINE_HISTORY),
        )

    def _tick(self) -> None:
        """Update bounded histories from current fighter state."""
        self._hist.altitude_ft.append(float(self._fighter.altitude_ft))
        self._hist.speed.append(float(self._fighter.speed_knots))
        self._hist.fuel_pct.append(float(self._fighter.fuel_percent))
        self._hist.g_force.append(float(self._fighter.g_force))

    def render(self) -> Panel:
        """Render the fighter status panel."""
        self._tick()

        header = Table.grid(padding=(0, 1))
        header.add_column(ratio=1)
        header.add_column(justify="right")

        # Status chips
        status_colors = {
            FighterStatus.HANGAR: "black on bright_black",
            FighterStatus.PREFLIGHT: "black on yellow",
            FighterStatus.TAXIING: "black on yellow",
            FighterStatus.TAKEOFF: "black on cyan",
            FighterStatus.CLIMBING: "black on bright_green",
            FighterStatus.CRUISING: "black on bright_green",
            FighterStatus.COMBAT: "bold white on red",
            FighterStatus.EVADING: "bold black on bright_yellow",
            FighterStatus.ATTACKING: "bold white on red",
            FighterStatus.PATROLLING: "black on bright_green",
            FighterStatus.REFUELING: "black on cyan",
            FighterStatus.RTB: "black on yellow",
            FighterStatus.LANDING: "black on cyan",
            FighterStatus.EMERGENCY: "bold white on red",
        }
        status_style = status_colors.get(self._fighter.status, "bold white")

        chips = Text()
        chips.append_text(_chip(self._fighter.status.value.upper(), style=status_style))
        chips.append(" ")
        chips.append_text(_chip(self._fighter.fighter_type.value, style="bold black on bright_cyan"))
        chips.append(" ")
        chips.append_text(_chip("ARM" if self._fighter.master_arm else "SAFE", style="bold white on red" if self._fighter.master_arm else "black on green"))
        if self._fighter.is_bingo_fuel():
            chips.append(" ")
            chips.append_text(_chip("BINGO", style="bold white on red"))

        right = Text(f"{self._fighter.callsign}  {self._fighter.tail_number}", style="bold bright_green")
        header.add_row(chips, right)

        # Primary flight strip (unit rich)
        strip = Table.grid(padding=(0, 1))
        strip.add_column(ratio=1)
        strip.add_column(ratio=1)
        strip.add_column(ratio=1)

        alt_m = int(round(self._fighter.altitude_ft * 0.3048))
        spd_ms = int(round(self._fighter.speed_knots * 0.514444))
        strip.add_row(
            Text(f"ALT  {self._fighter.altitude_ft:>6,} ft  ({alt_m:>5,} m)", style="white"),
            Text(f"TAS  {self._fighter.speed_knots:>4} kt  ({spd_ms:>3} m/s)", style="white"),
            Text(f"MACH {self._fighter.speed_mach:>4.2f}  HDG {_format_deg(self._fighter.heading)}", style="cyan"),
        )

        # Trends / limits
        trends = Table.grid(padding=(0, 1))
        trends.add_column("Metric", style="dim", width=8)
        trends.add_column("Now", justify="right", width=7)
        trends.add_column("Trend", justify="left")
        trends.add_row("ALT", f"{self._fighter.altitude_ft:,.0f}", _sparkline(self._hist.altitude_ft))
        trends.add_row("TAS", f"{self._fighter.speed_knots:.0f}", _sparkline(self._hist.speed, low=0.0, high=900.0))
        trends.add_row("FUEL", f"{self._fighter.fuel_percent:>3d}%", _sparkline(self._hist.fuel_pct, low=0.0, high=100.0))
        trends.add_row("G", f"{self._fighter.g_force:>3.1f}", _sparkline(self._hist.g_force, low=0.0, high=9.0))

        # Systems summary
        sys_tbl = Table.grid(padding=(0, 1))
        sys_tbl.add_column("Label", style="cyan", width=10)
        sys_tbl.add_column("Value", style="white")

        g_style = "bold white on red" if self._fighter.g_force >= 8.5 else "yellow" if self._fighter.g_force >= 7.0 else "green"
        sys_tbl.add_row("G-LOAD", Text(f"{self._fighter.g_force:.1f} G", style=g_style))
        sys_tbl.add_row("OXYGEN", Text(f"{self._fighter.oxygen_percent}%", style="green" if self._fighter.oxygen_percent >= 50 else "bold white on red"))
        sys_tbl.add_row("GEAR", Text("DOWN" if self._fighter.landing_gear_down else "UP", style="yellow" if self._fighter.landing_gear_down else "green"))
        sys_tbl.add_row("CANOPY", Text("CLOSED" if self._fighter.canopy_closed else "OPEN", style="green" if self._fighter.canopy_closed else "bold white on red"))
        sys_tbl.add_row("D/LINK", Text("LINK-16" if self._fighter.avionics.datalink_active else "OFFLINE", style="green" if self._fighter.avionics.datalink_active else "red"))
        sys_tbl.add_row("RADAR", Text(self._fighter.avionics.radar_mode, style="cyan" if self._fighter.avionics.radar_active else "dim"))

        # Tactical snapshot: target + missiles
        tactical = Table.grid(padding=(0, 1))
        tactical.add_column(ratio=1)

        locked = self._fighter.get_locked_target()
        if locked is None:
            tactical.add_row(Text("TARGET: NONE", style="dim"))
        else:
            lock_style = "bold white on red" if locked.classification == "HOSTILE" else "yellow"
            tactical.add_row(
                Text(
                    f"TARGET: {locked.contact_id}  {locked.aircraft_type}  {locked.classification}  "
                    f"BRG {_format_deg(locked.bearing)}  RNG {locked.distance_nm:.1f} nm  ALT {locked.altitude_ft:,} ft",
                    style=lock_style,
                )
            )

        if self._fighter.missile_warnings:
            for mw in self._fighter.missile_warnings[:2]:
                cm = "CM DEPLOYED" if mw.countermeasures_deployed else "NO CM"
                tactical.add_row(
                    Text(
                        f"MISSILE: {mw.missile_type}  BRG {_format_deg(mw.bearing)}  TTI {mw.time_to_impact_sec:0.1f}s  {cm}",
                        style="bold white on red",
                    )
                )
        else:
            tactical.add_row(Text("MISSILES: CLEAR", style="green"))

        kills_line = Text(f"KILLS: {self._fighter.kills}", style="bold yellow") if self._fighter.kills > 0 else Text("KILLS: 0", style="dim")
        cm_text = Text(
            f"CM: CHAFF {self._fighter.defensive.chaff_count}  FLARE {self._fighter.defensive.flare_count}  "
            f"ECM {'ON' if self._fighter.defensive.ecm_active else 'OFF'}",
            style="cyan" if self._fighter.defensive.ecm_active else "dim",
        )

        hostile_count = self._fighter.get_hostile_count()
        contacts = Text(
            f"RADAR: {len(self._fighter.radar_contacts)} contact(s)  |  HOSTILE: {hostile_count}",
            style="bold white on red" if hostile_count > 0 else "green",
        )

        content = Group(
            header,
            strip,
            Text(""),
            contacts,
            tactical,
            Text(""),
            trends,
            Text(""),
            sys_tbl,
            Text(""),
            kills_line,
            cm_text,
        )

        return Panel(
            content,
            title="FIGHTER STATUS",
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

        import math

        # Determine dynamic range for scientifically meaningful mapping.
        max_contact_nm = max((d for _, d, _ in self._contacts), default=0.0)
        # Keep a stable minimum range so empty screens don't collapse.
        max_range_nm = max(30.0, float(max_contact_nm) + 10.0)

        # Draw concentric circles (range rings) at 1/3 and 2/3 of display radius.
        ring_radii = [max(1, int(round((center - 1) * (1 / 3)))), max(1, int(round((center - 1) * (2 / 3))))]
        for r in ring_radii:
            for angle in range(0, 360, 15):
                x = int(center + r * math.cos(math.radians(angle)))
                y = int(center + r * math.sin(math.radians(angle)))
                if 0 <= x < size and 0 <= y < size and grid[y][x] == " ":
                    grid[y][x] = "·"

        # Draw cardinal directions
        grid[0][center] = "N"
        grid[size - 1][center] = "S"
        grid[center][0] = "W"
        grid[center][size - 1] = "E"

        # Draw center (own aircraft)
        grid[center][center] = "◈"

        # Draw sweep line
        sweep_rad = math.radians(self._sweep_angle)
        for r in range(1, center + 1):
            x = int(center + r * math.cos(sweep_rad))
            y = int(center - r * math.sin(sweep_rad))
            if 0 <= x < size and 0 <= y < size and grid[y][x] == " ":
                grid[y][x] = "░"

        # Draw contacts
        for bearing, distance, classification in self._contacts:
            # Normalize distance to grid
            if max_range_nm <= 0.0:
                continue
            r = min(center - 1, int(round((float(distance) / max_range_nm) * (center - 1))))
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

        # Legend with ring labels
        legend = Text()
        legend.append("\n◈", style="bright_green")
        legend.append(" Own  ", style="dim")
        legend.append("▲", style="red")
        legend.append(" Hostile  ", style="dim")
        legend.append("?", style="yellow")
        legend.append(" Unknown  ", style="dim")
        legend.append(f"RNG {max_range_nm:.0f} nm", style="dim cyan")

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
        grid = Table.grid(padding=(0, 1))
        grid.add_column("ENG", style="cyan", width=3)
        grid.add_column("RPM", justify="left")
        grid.add_column("AB", justify="right", width=3)

        e1_bar = create_gauge(self._engine1_rpm, width=16, color="cyan", warning_threshold=0, critical_threshold=0)
        e2_bar = create_gauge(self._engine2_rpm, width=16, color="cyan", warning_threshold=0, critical_threshold=0)
        ab1 = Text("🔥", style="bold orange1") if self._ab1_active else Text(" ", style="dim")
        ab2 = Text("🔥", style="bold orange1") if self._ab2_active else Text(" ", style="dim")
        grid.add_row("E1", e1_bar, ab1)
        grid.add_row("E2", e2_bar, ab2)

        egt_style = "bold white on red" if (self._engine1_temp >= 950 or self._engine2_temp >= 950) else "yellow" if (self._engine1_temp >= 850 or self._engine2_temp >= 850) else "dim"
        temps = Text(f"EGT  {self._engine1_temp}°C / {self._engine2_temp}°C", style=egt_style)

        content = Group(grid, Text(""), temps)

        return Panel(
            content,
            title="🔧 ENGINES",
            border_style=self._theme.border,
            padding=(0, 1),
        )
