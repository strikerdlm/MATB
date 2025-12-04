"""Main monitoring dashboard with live updates."""

from __future__ import annotations

import time
from collections.abc import Generator
from typing import Final

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from aircraft_monitor.events.base import Event
from aircraft_monitor.models.fighter import FighterAircraft
from aircraft_monitor.models.uav import UAV
from aircraft_monitor.visualization.panels import (
    EnginePanel,
    EventLogPanel,
    FighterStatusPanel,
    MissionPanel,
    RadarPanel,
    UAVStatusPanel,
    WeaponsPanel,
)
from aircraft_monitor.visualization.themes import MILITARY_THEME, Theme

# Timing constants
DEFAULT_EVENT_DELAY_SEC: Final[float] = 0.8
MIN_EVENT_DELAY_SEC: Final[float] = 0.3
MAX_EVENT_DELAY_SEC: Final[float] = 2.0


def create_header(title: str, subtitle: str = "") -> Panel:
    """Create the dashboard header."""
    header_text = Text()
    header_text.append("═" * 20 + " ", style="bright_green")
    header_text.append(title, style="bold bright_green")
    header_text.append(" " + "═" * 20, style="bright_green")
    if subtitle:
        header_text.append(f"\n{subtitle}", style="dim cyan")

    return Panel(
        header_text,
        style="bright_green on black",
        border_style="bright_green",
    )


def create_footer() -> Panel:
    """Create the dashboard footer."""
    footer_text = Text()
    footer_text.append("Press ", style="dim")
    footer_text.append("Ctrl+C", style="bold cyan")
    footer_text.append(" to exit", style="dim")
    footer_text.append(" │ ", style="dim")
    footer_text.append("◈", style="bright_green")
    footer_text.append(" Aircraft Monitor v1.0", style="dim")

    return Panel(footer_text, style="dim", border_style="dim")


class MonitoringDashboard:
    """
    Main monitoring dashboard with live updates.

    Displays aircraft status, event logs, radar, and mission information
    in a rich terminal interface with automatic updates.
    """

    def __init__(
        self,
        theme: Theme = MILITARY_THEME,
        event_delay: float = DEFAULT_EVENT_DELAY_SEC,
    ) -> None:
        """
        Initialize the monitoring dashboard.

        Args:
            theme: Color theme for the dashboard
            event_delay: Delay between events in seconds
        """
        self._console = Console()
        self._theme = theme
        self._event_delay = max(MIN_EVENT_DELAY_SEC, min(MAX_EVENT_DELAY_SEC, event_delay))

        # Panels
        self._event_log = EventLogPanel(theme=theme)
        self._radar = RadarPanel(theme=theme)
        self._mission = MissionPanel(theme=theme)
        self._weapons = WeaponsPanel(theme=theme)
        self._engines = EnginePanel(theme=theme)

        # Aircraft references
        self._uav: UAV | None = None
        self._fighter: FighterAircraft | None = None
        self._uav_panel: UAVStatusPanel | None = None
        self._fighter_panel: FighterStatusPanel | None = None

    def set_uav(self, uav: UAV) -> None:
        """Set the UAV to monitor."""
        self._uav = uav
        self._uav_panel = UAVStatusPanel(uav, self._theme)

    def set_fighter(self, fighter: FighterAircraft) -> None:
        """Set the fighter aircraft to monitor."""
        self._fighter = fighter
        self._fighter_panel = FighterStatusPanel(fighter, self._theme)

    def _update_radar(self) -> None:
        """Update radar display from current aircraft."""
        contacts: list[tuple[int, float, str]] = []

        if self._fighter:
            for contact in self._fighter.radar_contacts:
                contacts.append((contact.bearing, contact.distance_nm, contact.classification))

        if self._uav:
            for threat in self._uav.threats:
                contacts.append((threat.bearing, threat.distance_nm, "HOSTILE"))

        self._radar.update_contacts(contacts)
        self._radar.advance_sweep()

    def _update_mission(self) -> None:
        """Update mission panel from current aircraft."""
        if self._fighter:
            self._mission.set_mission(
                "COMBAT AIR PATROL",
                list(self._fighter.mission_objectives),
            )
            self._mission.set_time(self._fighter.mission_time_sec)
        elif self._uav:
            self._mission.set_mission(
                self._uav.mission.value,
                [(f"Waypoint {w.name}", w.is_reached) for w in self._uav.waypoints],
            )

    def _update_weapons(self) -> None:
        """Update weapons panel from fighter."""
        if self._fighter:
            weapons = [
                (w.weapon_type.value, w.quantity, w.ready, w.selected)
                for w in self._fighter.weapons
            ]
            self._weapons.update_weapons(weapons)

    def _update_engines(self) -> None:
        """Update engine panel from fighter."""
        if self._fighter:
            self._engines.update(
                self._fighter.engines.engine_1_rpm_percent,
                self._fighter.engines.engine_2_rpm_percent,
                self._fighter.engines.engine_1_temp_c,
                self._fighter.engines.engine_2_temp_c,
                self._fighter.engines.afterburner_1_active,
                self._fighter.engines.afterburner_2_active,
            )

    def _create_uav_layout(self) -> Layout:
        """Create layout for UAV monitoring."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="center", ratio=2),
            Layout(name="right", ratio=1),
        )

        return layout

    def _create_fighter_layout(self) -> Layout:
        """Create layout for fighter monitoring."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="center", ratio=2),
            Layout(name="right", ratio=1),
        )

        layout["right"].split_column(
            Layout(name="weapons"),
            Layout(name="engines"),
        )

        return layout

    def _create_combined_layout(self) -> Layout:
        """Create layout for combined monitoring."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="center", ratio=2),
            Layout(name="right", ratio=1),
        )

        layout["left"].split_column(
            Layout(name="uav"),
            Layout(name="fighter"),
        )

        layout["right"].split_column(
            Layout(name="radar"),
            Layout(name="mission"),
        )

        return layout

    def _render_uav_layout(self, layout: Layout) -> None:
        """Render UAV monitoring layout."""
        layout["header"].update(
            create_header(
                "🛩️ UAV MONITORING SYSTEM",
                f"Tracking: {self._uav.callsign if self._uav else 'N/A'}",
            )
        )

        if self._uav_panel:
            layout["left"].update(self._uav_panel.render())

        layout["center"].update(self._event_log.render())

        # Right side: radar and mission
        right_content = Group(
            self._radar.render(),
            self._mission.render(),
        )
        layout["right"].update(Panel(right_content, border_style="dim", title="TACTICAL"))

        layout["footer"].update(create_footer())

    def _render_fighter_layout(self, layout: Layout) -> None:
        """Render fighter monitoring layout."""
        layout["header"].update(
            create_header(
                "✈️ FIGHTER AIRCRAFT MONITORING",
                f"Pilot: {self._fighter.callsign if self._fighter else 'N/A'}",
            )
        )

        if self._fighter_panel:
            layout["left"].update(self._fighter_panel.render())

        layout["center"].update(self._event_log.render())

        layout["weapons"].update(self._weapons.render())
        layout["engines"].update(self._engines.render())

        layout["footer"].update(create_footer())

    def _render_combined_layout(self, layout: Layout) -> None:
        """Render combined monitoring layout."""
        layout["header"].update(
            create_header(
                "🎖️ JOINT OPERATIONS CENTER",
                "Multi-Platform Monitoring Active",
            )
        )

        if self._uav_panel:
            layout["uav"].update(self._uav_panel.render())

        if self._fighter_panel:
            layout["fighter"].update(self._fighter_panel.render())

        layout["center"].update(self._event_log.render())

        layout["radar"].update(self._radar.render())
        layout["mission"].update(self._mission.render())

        layout["footer"].update(create_footer())

    def run_uav_simulation(self, event_generator: Generator[Event, None, None]) -> None:
        """
        Run UAV monitoring simulation.

        Args:
            event_generator: Generator yielding UAV events
        """
        layout = self._create_uav_layout()

        with Live(layout, console=self._console, refresh_per_second=4, screen=True) as live:
            try:
                for event in event_generator:
                    self._event_log.add_event(event)
                    self._update_radar()
                    self._update_mission()

                    self._render_uav_layout(layout)
                    live.update(layout)

                    time.sleep(self._event_delay)

                # Keep display up after completion
                time.sleep(3.0)

            except KeyboardInterrupt:
                pass

    def run_fighter_simulation(self, event_generator: Generator[Event, None, None]) -> None:
        """
        Run fighter monitoring simulation.

        Args:
            event_generator: Generator yielding fighter events
        """
        layout = self._create_fighter_layout()

        with Live(layout, console=self._console, refresh_per_second=4, screen=True) as live:
            try:
                mission_start = time.time()

                for event in event_generator:
                    self._event_log.add_event(event)
                    self._update_radar()
                    self._update_mission()
                    self._update_weapons()
                    self._update_engines()

                    if self._fighter:
                        self._fighter.mission_time_sec = int(time.time() - mission_start)

                    self._render_fighter_layout(layout)
                    live.update(layout)

                    time.sleep(self._event_delay)

                # Keep display up after completion
                time.sleep(3.0)

            except KeyboardInterrupt:
                pass

    def run_combined_simulation(
        self,
        uav_events: Generator[Event, None, None],
        fighter_events: Generator[Event, None, None],
    ) -> None:
        """
        Run combined UAV and fighter monitoring simulation.

        Args:
            uav_events: Generator yielding UAV events
            fighter_events: Generator yielding fighter events
        """
        layout = self._create_combined_layout()

        # Interleave events
        uav_list = list(uav_events)
        fighter_list = list(fighter_events)
        combined: list[Event] = []

        max_len = max(len(uav_list), len(fighter_list))
        for i in range(max_len):
            if i < len(uav_list):
                combined.append(uav_list[i])
            if i < len(fighter_list):
                combined.append(fighter_list[i])

        with Live(layout, console=self._console, refresh_per_second=4, screen=True) as live:
            try:
                for event in combined:
                    self._event_log.add_event(event)
                    self._update_radar()
                    self._update_mission()
                    self._update_weapons()
                    self._update_engines()

                    self._render_combined_layout(layout)
                    live.update(layout)

                    time.sleep(self._event_delay * 0.6)

                time.sleep(3.0)

            except KeyboardInterrupt:
                pass
