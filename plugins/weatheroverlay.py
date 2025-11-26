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
        self._widget: Optional[Simpletext] = None

    def start(self) -> None:
        self.active_weather = None
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
        description = payload.strip()
        if not description:
            return
        self.active_weather = description
        self.log_performance('weather_set', description)

    def clear(self, payload: str) -> None:  # payload unused
        if self.active_weather is None:
            return
        self.log_performance('weather_clear', self.active_weather)
        self.active_weather = None

    # Helpers -----------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if self.active_weather:
            self._widget.set_text(self.active_weather)
        else:
            self._widget.set_text(_('No weather constraints.'))


