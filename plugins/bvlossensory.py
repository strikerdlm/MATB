# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from typing import Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Frame, Simpletext
from plugins.abstractplugin import AbstractPlugin


class Bvlossensory(AbstractPlugin):
    """Simulates BVLOS sensory cue deprivation (visual + audio)."""

    def __init__(self, label: str = '', taskplacement: str = 'fullscreen', taskupdatetime: int = 200) -> None:
        super().__init__(label or _('BVLOS Sensory Deprivation'), taskplacement, taskupdatetime)
        self.parameters.update({
            'visualcolor': (0, 0, 0, 220),
            'defaultduration': 15.0,
        })
        self.visual_level: float = 0.0
        self.visual_block_until: float = 0.0
        self.audio_level: float = 0.0
        self.audio_block_until: float = 0.0
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
            text=_('All sensory cues available.'),
            font_size=F['MEDIUM'],
            color=C['WHITE'],
            wrap_width=0.9,
            x=0.5,
            y=0.5,
        )

    def compute_next_plugin_state(self) -> bool:
        now = self.scenario_time
        changed = False
        if self.visual_block_until > 0.0 and now >= self.visual_block_until:
            self.visual_block_until = 0.0
            self.visual_level = 0.0
            changed = True
        if self.audio_block_until > 0.0 and now >= self.audio_block_until:
            self.audio_block_until = 0.0
            self.audio_level = 0.0
            changed = True
        if changed:
            self._apply_visual_state()
            self._update_status()
            self.log_performance('sensory_cue_restore', 'auto')
        return super().compute_next_plugin_state()

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_status()
        return True

    # Scenario commands --------------------------------------------------
    def apply(self, payload: str) -> None:
        """
        payload: channel(visual|audio|both),level(0-1),duration_seconds
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        channel = parts[0].strip().lower()
        level = self._clamp(parts[1])
        duration = self._parse_duration(parts[2])
        end_time = self.scenario_time + duration

        if channel in ('visual', 'both'):
            self.visual_level = level
            self.visual_block_until = end_time
            self._apply_visual_state()
        if channel in ('audio', 'both'):
            self.audio_level = level
            self.audio_block_until = end_time
        self._update_status()
        self.log_performance('sensory_cue_removed', f'{channel}:{level:.2f}:{duration:.1f}')

    def clear(self, payload: str) -> None:
        """payload: optional channel (visual|audio|both)."""
        channel = (payload or 'both').strip().lower()
        if channel in ('visual', 'both'):
            self.visual_level = 0.0
            self.visual_block_until = 0.0
            self._apply_visual_state()
        if channel in ('audio', 'both'):
            self.audio_level = 0.0
            self.audio_block_until = 0.0
        self._update_status()
        self.log_performance('sensory_cue_restore', channel or 'manual')

    # Helpers ------------------------------------------------------------
    def _apply_visual_state(self) -> None:
        if self._overlay is None:
            return
        if self.visual_level <= 0.0:
            self._overlay.hide()
            return
        base = self.parameters['visualcolor']
        alpha = int(self._keep_between(base[3] * self.visual_level, 0, 255))
        scaled = (base[0], base[1], base[2], alpha)
        self._overlay.set_fill_color(scaled)
        self._overlay.show()

    def _update_status(self) -> None:
        if self._status is None:
            return
        visual_txt = _('Visual cues {0}%').format(int(self.visual_level * 100))
        audio_txt = _('Audio cues {0}%').format(int(self.audio_level * 100))
        self._status.set_text(f'{visual_txt}\n{audio_txt}')

    def _split(self, payload: str, expected: int) -> Optional[list[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < expected:
            return None
        return parts

    def _clamp(self, value: str) -> float:
        try:
            numeric = float(value)
        except ValueError:
            numeric = 1.0
        return self._keep_between(numeric, 0.0, 1.0)

    def _parse_duration(self, value: str) -> float:
        try:
            duration = float(value)
        except ValueError:
            duration = float(self.parameters['defaultduration'])
        return max(0.5, duration)

    @staticmethod
    def _keep_between(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))


