# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from typing import Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


class Weatheroverlay(AbstractPlugin):
    """Displays mission-wide weather/visibility advisories."""

    def __init__(self, label: str = '', taskplacement: str = 'topmid', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('Weather / Visibility'), taskplacement, taskupdatetime)
        self.active_weather: Optional[str] = None
        self.visibility_penalty: float = 0.0
        self.affected_sensors: tuple[str, ...] = tuple()
        self._widget: Optional[Simpletext] = None

    def start(self) -> None:
        self.active_weather = None
        self.visibility_penalty = 0.0
        self.affected_sensors = tuple()
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'weather',
            Simpletext,
            container=self.task_container,
            text=_('No weather constraints.'),
            font_size=F['SMALL'],
            y=0.7,
            wrap_width=0.95,
            color=C['WHITE'],
            bold=True,
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands -------------------------------------------------
    def set(self, payload: str) -> None:
        parts = self._split(payload)
        if parts is None:
            return
        description = payload.strip()
        severity_token: Optional[str] = None
        sensors_token: Optional[str] = None
        if len(parts) >= 1:
            description = parts[0]
        if len(parts) > 1 and self._is_float(parts[1]):
            severity_token = parts[1]
            sensors_token = parts[2] if len(parts) > 2 else None
        elif len(parts) > 1 and not self._is_float(parts[1]):
            # Original payload likely used commas in plain text; keep full string.
            description = payload.strip()
        self.active_weather = description
        if severity_token is not None:
            self._apply_visibility(severity_token, sensors_token)
        self.log_performance('weather_set', description)

    def clear(self, payload: str) -> None:  # payload unused
        if self.active_weather is None:
            return
        self.log_performance('weather_clear', self.active_weather)
        self.active_weather = None
        if self.visibility_penalty > 0.0 or self.affected_sensors:
            self.visibility_penalty = 0.0
            self.affected_sensors = tuple()
            self.log_performance('visibility_impact_clear', 'manual')

    def impact(self, payload: str) -> None:
        """
        payload: severity(0-1)[,sensor_list]
        Example: weatheroverlay;impact;0.4,eo|ir
        """
        if not payload:
            return
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        severity = parts[0]
        sensors = parts[1] if len(parts) > 1 else None
        self._apply_visibility(severity, sensors)

    # Helpers -----------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if self.active_weather:
            penalty_txt = ''
            if self.visibility_penalty > 0.0:
                sensor_desc = ','.join(self.affected_sensors) if self.affected_sensors else _('all sensors')
                penalty_txt = _(' | Visibility -{0:.0%} ({1})').format(
                    self.visibility_penalty,
                    sensor_desc,
                )
            self._widget.set_text(f'{self.active_weather}{penalty_txt}')
            return
        self._widget.set_text(_('No weather constraints.'))

    def _apply_visibility(self, severity_raw: str, sensors_raw: Optional[str]) -> None:
        try:
            severity = float(severity_raw)
        except ValueError:
            severity = 0.0
        severity = self._clamp(severity, 0.0, 1.0)
        sensors: tuple[str, ...] = tuple()
        if sensors_raw:
            sensors = tuple(sensor.strip().lower() for sensor in sensors_raw.split('|') if sensor.strip())
        self.visibility_penalty = severity
        self.affected_sensors = sensors
        self.log_performance(
            'visibility_impact',
            f'{severity:.2f}:{"/".join(sensors) if sensors else "all"}',
        )
        self._update_widget()

    @staticmethod
    def _split(payload: str) -> Optional[list[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if not parts:
            return None
        return parts

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _is_float(value: str) -> bool:
        try:
            float(value)
        except ValueError:
            return False
        return True


