"""Main monitoring dashboard with live updates."""

from __future__ import annotations

import time
from collections.abc import Generator, Iterable, Iterator
from typing import Final

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from aircraft_monitor.events.base import Event, EventCategory, EventSeverity, create_event
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
DEFAULT_MAX_EVENTS: Final[int] = 5_000


def create_header(title: str, subtitle: str = "") -> Panel:
    """Create the dashboard header."""
    header_text = Text()
    header_text.append("═" * 18 + " ", style="bright_green")
    header_text.append(title, style="bold bright_green")
    header_text.append(" " + "═" * 18, style="bright_green")
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
        *,
        max_events: int = DEFAULT_MAX_EVENTS,
        headless: bool | None = None,
    ) -> None:
        """
        Initialize the monitoring dashboard.

        Args:
            theme: Color theme for the dashboard
            event_delay: Delay between events in seconds
            max_events: Hard limit on processed events per run to prevent runaway generators
            headless: If True, do not use full-screen live UI; if None, auto-detect
        """
        self._console = Console()
        self._theme = theme
        self._event_delay = max(MIN_EVENT_DELAY_SEC, min(MAX_EVENT_DELAY_SEC, event_delay))
        self._max_events = max(1, max_events)
        self._headless = (not self._console.is_terminal) if headless is None else headless

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

    def _sleep(self, seconds: float) -> None:
        """Sleep between frames (disabled in headless mode)."""
        if self._headless:
            return
        time.sleep(seconds)

    def _bounded_events(self, events: Iterable[Event], *, source: str) -> Iterator[Event]:
        """Yield up to max_events, then emit a hard-stop event and terminate."""
        count = 0
        for event in events:
            yield event
            count += 1
            if count >= self._max_events:
                yield create_event(
                    EventSeverity.CRITICAL,
                    EventCategory.SYSTEM,
                    "EVENT LIMIT REACHED",
                    f"Stopped after {self._max_events} events to prevent runaway simulation.",
                    source,
                    {"max_events": self._max_events},
                )
                return

    def _interleave_events(
        self,
        a_events: Iterable[Event],
        b_events: Iterable[Event],
    ) -> Iterator[Event]:
        """Interleave two finite iterables without materializing them."""
        a_iter = iter(a_events)
        b_iter = iter(b_events)

        a_done = False
        b_done = False

        # Bounded by exhaustion of both iterators.
        while not (a_done and b_done):
            if not a_done:
                try:
                    yield next(a_iter)
                except StopIteration:
                    a_done = True
            if not b_done:
                try:
                    yield next(b_iter)
                except StopIteration:
                    b_done = True

    def _create_uav_layout(self) -> Layout:
        """Create layout for UAV monitoring."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="center", ratio=3),
            Layout(name="right", ratio=2),
        )

        layout["right"].split_column(
            Layout(name="radar", ratio=2),
            Layout(name="mission", ratio=2),
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
            Layout(name="left", ratio=2),
            Layout(name="center", ratio=3),
            Layout(name="right", ratio=2),
        )

        layout["right"].split_column(
            Layout(name="radar", ratio=2),
            Layout(name="weapons", ratio=2),
            Layout(name="engines", ratio=1),
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
            Layout(name="left", ratio=2),
            Layout(name="center", ratio=3),
            Layout(name="right", ratio=2),
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
                "🛩️  UAV MONITORING SYSTEM",
                f"Tracking: {self._uav.callsign if self._uav else 'N/A'}",
            )
        )

        if self._uav_panel:
            layout["left"].update(self._uav_panel.render())

        layout["center"].update(self._event_log.render())

        layout["radar"].update(self._radar.render())
        layout["mission"].update(self._mission.render())

        layout["footer"].update(create_footer())

    def _render_fighter_layout(self, layout: Layout) -> None:
        """Render fighter monitoring layout."""
        layout["header"].update(
            create_header(
                "✈️  FIGHTER AIRCRAFT MONITORING",
                f"Pilot: {self._fighter.callsign if self._fighter else 'N/A'}",
            )
        )

        if self._fighter_panel:
            layout["left"].update(self._fighter_panel.render())

        layout["center"].update(self._event_log.render())

        layout["radar"].update(self._radar.render())
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
        events = self._bounded_events(event_generator, source=(self._uav.callsign if self._uav else "UAV"))

        if self._headless:
            for event in events:
                # Keep it readable in non-interactive output
                self._console.print(f"{event.format_timestamp()} {event.icon} {event.title} - {event.description}")
            return

        layout = self._create_uav_layout()

        with Live(layout, console=self._console, refresh_per_second=4, screen=True) as live:
            try:
                for event in events:
                    self._event_log.add_event(event)
                    self._update_radar()
                    self._update_mission()

                    self._render_uav_layout(layout)
                    live.update(layout)

                    self._sleep(self._event_delay)

                # Keep display up after completion
                self._sleep(3.0)

            except KeyboardInterrupt:
                pass

    def run_fighter_simulation(self, event_generator: Generator[Event, None, None]) -> None:
        """
        Run fighter monitoring simulation.

        Args:
            event_generator: Generator yielding fighter events
        """
        events = self._bounded_events(
            event_generator,
            source=(self._fighter.callsign if self._fighter else "FIGHTER"),
        )

        if self._headless:
            for event in events:
                self._console.print(f"{event.format_timestamp()} {event.icon} {event.title} - {event.description}")
            return

        layout = self._create_fighter_layout()

        with Live(layout, console=self._console, refresh_per_second=4, screen=True) as live:
            try:
                mission_start = time.time()

                for event in events:
                    self._event_log.add_event(event)
                    self._update_radar()
                    self._update_mission()
                    self._update_weapons()
                    self._update_engines()

                    if self._fighter:
                        self._fighter.mission_time_sec = int(time.time() - mission_start)

                    self._render_fighter_layout(layout)
                    live.update(layout)

                    self._sleep(self._event_delay)

                # Keep display up after completion
                self._sleep(3.0)

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
        combined_iter = self._interleave_events(uav_events, fighter_events)
        combined = self._bounded_events(
            combined_iter,
            source="JOINT",
        )

        if self._headless:
            for event in combined:
                self._console.print(f"{event.format_timestamp()} {event.icon} {event.title} - {event.description}")
            return

        layout = self._create_combined_layout()

        with Live(layout, console=self._console, refresh_per_second=4, screen=True) as live:
            try:
                mission_start = time.time()
                for event in combined:
                    self._event_log.add_event(event)
                    self._update_radar()
                    self._update_mission()
                    self._update_weapons()
                    self._update_engines()

                    if self._fighter:
                        self._fighter.mission_time_sec = int(time.time() - mission_start)

                    self._render_combined_layout(layout)
                    live.update(layout)

                    self._sleep(self._event_delay * 0.6)

                self._sleep(3.0)

            except KeyboardInterrupt:
                pass
