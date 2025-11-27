# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Frame, Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class DataStorm:
    """Represents a temporary data overload event."""

    level: int
    expires_at: float
    channels: Tuple[str, ...]
    started_at: float


class Dataoverload(AbstractPlugin):
    """Simulates high-volume data bursts for workload studies."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomleft', taskupdatetime: int = 300) -> None:
        super().__init__(label or _('Data Overload'), taskplacement, taskupdatetime)
        self.parameters.update({
            'maxlevel': 5,
        })
        self.storms: List[DataStorm] = []
        self._overlay: Optional[Frame] = None
        self._status: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        if self.task_container is None:
            return
        self._overlay = self.add_widget(
            'overlay',
            Frame,
            container=self.task_container,
            fill_color=None,
            draw_order=self.m_draw + 5,
        )
        self._overlay.hide()
        self._status = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No overload.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.95,
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        before = len(self.storms)
        self.storms = [storm for storm in self.storms if storm.expires_at > now]
        if len(self.storms) != before:
            self._apply_overlay()
            self._update_status()
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_status()
        return True

    # Scenario commands --------------------------------------------------
    def storm(self, payload: str) -> None:
        """
        payload: level(1-max),duration_seconds,channels(separated by |)
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        level = self._parse_level(parts[0])
        duration = self._parse_duration(parts[1])
        channels = tuple(ch.strip() for ch in parts[2].split('|') if ch.strip())
        storm = DataStorm(
            level=level,
            expires_at=self.scenario_time + duration,
            channels=channels,
            started_at=self.scenario_time,
        )
        self.storms.append(storm)
        self._apply_overlay()
        self._update_status()
        channel_str = '|'.join(channels) if channels else 'all'
        self.log_performance('data_overload_detected', f'level={level};channels={channel_str};duration={duration:.1f}')

    def filter(self, payload: str) -> None:
        """
        payload: channel
        """
        channel = (payload or '').strip() or 'all'
        self.log_performance('information_filter_applied', channel)

    def miss(self, payload: str) -> None:
        """
        payload: channel[,detail]
        """
        parts = self._split(payload, 1)
        if parts is None:
            return
        detail = parts[1] if len(parts) > 1 else ''
        self.log_performance('critical_data_missed', f'{parts[0]}:{detail}')

    # Helpers ------------------------------------------------------------
    def _apply_overlay(self) -> None:
        if self._overlay is None:
            return
        if not self.storms:
            self._overlay.hide()
            return
        active_level = max(storm.level for storm in self.storms)
        alpha = self._keep_between(int(30 + active_level * 40), 30, 255)
        self._overlay.set_fill_color((C['RED'][0], C['RED'][1], C['RED'][2], alpha))
        self._overlay.show()

    def _update_status(self) -> None:
        if self._status is None:
            return
        if not self.storms:
            self._status.set_text(_('No overload.'))
            return
        entries = [
            _('Lvl {0} ({1} s)').format(
                storm.level,
                max(0, int(storm.expires_at - self.scenario_time)),
            )
            for storm in self.storms
        ]
        self._status.set_text(' | '.join(entries))

    def _split(self, payload: str, expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts

    def _parse_level(self, value: str) -> int:
        try:
            level = int(value)
        except ValueError:
            level = 1
        max_level = int(self.parameters['maxlevel'])
        return self._keep_between(level, 1, max_level)

    def _parse_duration(self, value: str) -> float:
        try:
            duration = float(value)
        except ValueError:
            duration = 10.0
        return max(1.0, duration)

    @staticmethod
    def _keep_between(value: int, low: int, high: int) -> int:
        return max(low, min(high, value))


