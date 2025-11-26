# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class HMDCue:
    label: str
    azimuth_deg: float
    elevation_deg: float
    expires_at: Optional[float]

    def as_text(self) -> str:
        return f'{self.label}: AZ {self.azimuth_deg:+05.1f}° | EL {self.elevation_deg:+05.1f}°'


class Hmdoverlay(AbstractPlugin):
    """Displays simple helmet-mounted display cueing information."""

    def __init__(self, label: str = '', taskplacement: str = 'topmid', taskupdatetime: int = 250) -> None:
        super().__init__(label or _('HMD Cue'), taskplacement, taskupdatetime)
        self.active_cue: Optional[HMDCue] = None
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'hmdtext',
            Simpletext,
            container=self.task_container,
            text=_('No HMD cue.'),
            font_size=F['SMALL'],
            y=0.7,
            wrap_width=0.95,
            color=C['WHITE'],
            bold=True,
        )

    def refresh_widgets(self) -> bool:
        self._expire_if_needed()
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands -------------------------------------------------
    def cue(self, payload: str) -> None:
        parts = [p.strip() for p in payload.split(',') if p.strip()]
        if len(parts) < 3:
            return
        label = parts[0]
        try:
            az = float(parts[1])
            el = float(parts[2])
        except ValueError:
            return
        duration = None
        if len(parts) > 3:
            try:
                duration = max(0.0, float(parts[3]))
            except ValueError:
                duration = None
        expires_at = self.scenario_time + duration if duration else None
        self.active_cue = HMDCue(label=label, azimuth_deg=az, elevation_deg=el, expires_at=expires_at)
        self.log_performance('hmd_cue', f'{label}:{az}:{el}:{duration if duration is not None else -1}')

    def clear(self, payload: str) -> None:
        if self.active_cue is None:
            return
        self.log_performance('hmd_clear', self.active_cue.label)
        self.active_cue = None

    # Helpers -----------------------------------------------------------
    def _expire_if_needed(self) -> None:
        if self.active_cue is not None and self.active_cue.expires_at is not None:
            if self.scenario_time >= self.active_cue.expires_at:
                self.active_cue = None

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if self.active_cue is None:
            self._widget.set_text(_('No HMD cue.'))
            return
        self._widget.set_text(self.active_cue.as_text())


