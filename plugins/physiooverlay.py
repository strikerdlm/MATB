# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from typing import Optional

from core import validation
from core.widgets import Frame
from plugins.abstractplugin import AbstractPlugin


class Physiooverlay(AbstractPlugin):
    """Applies temporary visual overlays (e.g., hypoxia tunnel vision)."""

    def __init__(self, label: str = '', taskplacement: str = 'fullscreen', taskupdatetime: int = 100) -> None:
        super().__init__(label or _('Physio Overlay'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'defaultcolor': validation.is_color,
        }

        self.parameters.update({
            'defaultcolor': (0, 0, 0, 180),
        })

        self._overlay: Optional[Frame] = None
        self._visible_until: float = 0.0

    def create_widgets(self) -> None:
        super().create_widgets()
        self._overlay = self.add_widget(
            'overlay',
            Frame,
            container=self.container,
            fill_color=None,
            draw_order=self.m_draw + 50,
        )
        self._overlay.hide()

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        if self._overlay is not None and self._overlay.visible and now >= self._visible_until > 0:
            self._overlay.hide()
        return super().compute_next_plugin_state()

    # Scenario commands --------------------------------------------------
    def apply(self, payload: str) -> None:
        """
        payload: color_or_hex, duration_seconds
        """
        parts = [part.strip() for part in payload.split(',')] if payload else []
        if len(parts) < 2:
            return
        color, msg = validation.is_color(parts[0])
        if msg is not None:
            return
        try:
            duration = float(parts[1])
        except ValueError:
            return
        if self._overlay is None:
            return
        self._overlay.set_fill_color(color)
        self._overlay.show()
        self._visible_until = self.scenario_time + max(0.1, duration)
        self.log_performance('overlay_apply', f'{color}:{duration}')

    def clear(self, payload: str) -> None:
        if self._overlay is not None:
            self._overlay.hide()
        self._visible_until = 0.0
        self.log_performance('overlay_clear', 'manual')


