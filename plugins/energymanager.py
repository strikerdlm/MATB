# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class EnergyEvent:
    name: str
    target_g: float
    duration: float
    scheduled_at: float
    delay: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    warning_emitted: bool = False

    def is_active(self) -> bool:
        return self.started_at is not None and self.completed_at is None

    def is_complete(self) -> bool:
        return self.completed_at is not None

    def remaining(self, now: float) -> float:
        if not self.is_active() or self.started_at is None:
            return self.duration
        elapsed = now - self.started_at
        return max(0.0, self.duration - elapsed)

    def time_to_start(self, now: float) -> float:
        if self.started_at is not None:
            return 0.0
        ready_at = self.scheduled_at + self.delay
        return max(0.0, ready_at - now)


class Energymanager(AbstractPlugin):
    """Monitors energy/g-envelope events for high-performance aircraft."""

    def __init__(self, label: str = '', taskplacement: str = 'bottommid', taskupdatetime: int = 250) -> None:
        super().__init__(label or _('Energy Manager'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'glimit': validation.is_positive_float,
            'energylimit': validation.is_positive_float,
            'energyreserve': validation.is_positive_float,
            'gwarningthreshold': validation.is_positive_float,
            'gwarningleadtime': validation.is_positive_float,
        }

        self.parameters.update({
            'glimit': 7.5,
            'energylimit': 120.0,   # cumulative g-seconds before fatigue
            'energyreserve': 100.0, # percent
            'gwarningthreshold': 5.0,
            'gwarningleadtime': 4.0,
        })

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['ORANGE'],
            'delayms': 0,
            'blinkdurationms': 400,
        })

        self.events: List[EnergyEvent] = []
        self.energy_reserve: float = float(self.parameters['energyreserve'])
        self.cumulative_g_seconds: float = 0.0
        self._widget: Optional[Simpletext] = None
        self._gauge_widget: Optional[Simpletext] = None

    # Lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self.energy_reserve = float(self.parameters['energyreserve'])
        self.cumulative_g_seconds = 0.0
        self.events = []
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('Event | Target G | Status | Remaining (s)')
        self.add_widget(
            'header',
            Simpletext,
            container=self.task_container,
            text=header,
            font_size=F['SMALL'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        self._widget = self.add_widget(
            'summary',
            Simpletext,
            container=self.task_container,
            text=_('Awaiting profile…'),
            font_size=F['SMALL'],
            y=0.6,
            wrap_width=0.95,
            color=C['WHITE'],
        )
        self._gauge_widget = self.add_widget(
            'gauge',
            Simpletext,
            container=self.task_container,
            text=_('G-meter idle.'),
            font_size=F['SMALL'],
            y=0.25,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def compute_next_plugin_state(self) -> bool:
        self._advance_events()
        self._maybe_emit_g_warning()
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        self._update_gauge()
        self._update_overdue()
        return True

    # Scenario commands -------------------------------------------------
    def event(self, payload: str) -> None:
        """
        payload: name,target_g,duration_seconds
        """
        parts = self._split(payload, 3)
        if not parts:
            return
        try:
            event = EnergyEvent(
                name=parts[0],
                target_g=float(parts[1]),
                duration=float(parts[2]),
                scheduled_at=self.scenario_time,
                delay=float(parts[3]) if len(parts) > 3 else 0.0,
            )
        except ValueError:
            return
        self.events.append(event)
        self.log_performance(
            'energy_event_schedule',
            f'{event.name}:{event.target_g}:{event.duration}:{event.delay}',
        )

    def overg(self, payload: str) -> None:
        try:
            gload = float(payload)
        except (TypeError, ValueError):
            return
        self.log_performance('energy_overg', gload)
        if gload > float(self.parameters['glimit']):
            overdue = self.parameters['taskfeedback']['overdue']
            overdue['active'] = True
            overdue['_is_visible'] = True

    def energy(self, payload: str) -> None:
        """
        Directly set energy reserve (0-100).
        """
        try:
            reserve = float(payload)
        except (TypeError, ValueError):
            return
        self.energy_reserve = max(0.0, min(100.0, reserve))
        self.log_performance('energy_set_reserve', self.energy_reserve)

    def warning(self, payload: str) -> None:
        """
        Configure g-onset warning threshold and lead time (seconds before start).
        payload: threshold_g,lead_time_sec
        """
        parts = self._split(payload, 2)
        if not parts:
            return
        try:
            threshold = float(parts[0])
            lead_time = float(parts[1])
        except (TypeError, ValueError):
            return
        self.parameters['gwarningthreshold'] = max(0.1, threshold)
        self.parameters['gwarningleadtime'] = max(0.5, lead_time)
        self.log_performance(
            'energy_warning_config',
            f"{self.parameters['gwarningthreshold']}:{self.parameters['gwarningleadtime']}",
        )

    # Helpers -----------------------------------------------------------
    def _split(self, payload: str, min_parts: int) -> Optional[List[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < min_parts:
            return None
        return parts

    def _advance_events(self) -> None:
        now = self.scenario_time
        # Start the first queued event if none active
        active = self._get_active_event()
        if active is None:
            next_event = next(
                (
                    event
                    for event in self.events
                    if not event.is_complete()
                    and event.started_at is None
                    and now >= event.scheduled_at + event.delay
                ),
                None,
            )
            if next_event is not None:
                next_event.started_at = now
                self.log_performance('energy_event_start', next_event.name)
                active = next_event

        if active is not None:
            remaining = active.remaining(now)
            if remaining <= 0:
                active.completed_at = now
                self._consume_energy(active)
                self.log_performance('energy_event_complete', active.name)

    def _consume_energy(self, event: EnergyEvent) -> None:
        cost = event.target_g * event.duration * 0.02
        self.cumulative_g_seconds += event.target_g * event.duration
        self.energy_reserve = max(0.0, self.energy_reserve - cost)

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        lines: List[str] = []
        now = self.scenario_time
        for event in self.events:
            status = _('Queued')
            remaining = event.duration
            if event.is_active():
                status = _('Active')
                remaining = event.remaining(now)
            elif event.is_complete():
                status = _('Complete')
                remaining = 0.0
            line = f"{event.name} | {event.target_g:.1f} | {status} | {remaining:5.1f}"
            lines.append(line)

        if not lines:
            lines.append(_('No events.'))

        lines.append(_('Energy reserve: {0:.1f}%').format(self.energy_reserve))
        lines.append(_('Cumulative g-seconds: {0:.1f} / {1:.1f}').format(
            self.cumulative_g_seconds, float(self.parameters['energylimit'])
        ))

        self._widget.set_text('\n'.join(lines))

    def _update_gauge(self) -> None:
        if self._gauge_widget is None:
            return
        limit = float(self.parameters['glimit'])
        threshold = float(self.parameters['gwarningthreshold'])
        active = self._get_active_event()
        upcoming = self._get_next_event()
        target = None
        context_line = ''
        now = self.scenario_time
        if active is not None:
            target = active.target_g
            context_line = _('Active {0} ({1:.1f}s remaining)').format(active.name, active.remaining(now))
        elif upcoming is not None:
            target = upcoming.target_g
            context_line = _('Next {0} in {1:.1f}s').format(upcoming.name, upcoming.time_to_start(now))
        else:
            self._gauge_widget.set_text(_('G-meter idle.'))
            return
        bar = self._build_gauge_bar(target, limit, threshold)
        metrics_line = _('Target {0:.1f}G | Limit {1:.1f}G | Warn {2:.1f}G').format(target, limit, threshold)
        self._gauge_widget.set_text('\n'.join([bar, context_line, metrics_line]))

    def _build_gauge_bar(self, target: float, limit: float, threshold: float) -> str:
        width = 24
        scale_max = max(limit, threshold, target, 0.1) * 1.1
        step = scale_max / (width - 1)
        bar = ['-' for _ in range(width)]

        def _mark(value: float, symbol: str) -> None:
            idx = int(round(value / step))
            idx = max(0, min(width - 1, idx))
            bar[idx] = symbol

        _mark(limit, 'L')
        _mark(threshold, 'W')
        _mark(target, 'T')
        return '[' + ''.join(bar) + ']'

    def _update_overdue(self) -> None:
        overdue = self.parameters['taskfeedback']['overdue']
        limit = float(self.parameters['energylimit'])
        energy_low = self.energy_reserve <= 10.0
        g_limit = self.cumulative_g_seconds >= limit
        overdue['active'] = True
        overdue['_is_visible'] = energy_low or g_limit
        if energy_low:
            self.log_performance('energy_alert', 'reserve_low')
        if g_limit:
            self.log_performance('energy_alert', 'cumulative_limit')

    def _maybe_emit_g_warning(self) -> None:
        threshold = float(self.parameters['gwarningthreshold'])
        lead_time = float(self.parameters['gwarningleadtime'])
        now = self.scenario_time
        for event in self.events:
            if event.warning_emitted:
                continue
            if event.target_g < threshold:
                continue
            if event.started_at is not None:
                continue
            if event.time_to_start(now) <= lead_time:
                event.warning_emitted = True
                self.log_performance('g_onset_warning', f'{event.name}:{event.target_g}:{event.time_to_start(now):.1f}')

    def _get_active_event(self) -> Optional[EnergyEvent]:
        return next((event for event in self.events if event.is_active()), None)

    def _get_next_event(self) -> Optional[EnergyEvent]:
        candidates = [
            event
            for event in self.events
            if event.started_at is None and not event.is_complete()
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda event: event.scheduled_at + event.delay)

