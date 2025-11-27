# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass(slots=True)
class DualTaskState:
    """Tracks the current dual-task training phase."""

    phase: str
    sensor_task: str
    secondary_task: str
    sensor_metric: Optional[float] = None
    secondary_metric: Optional[float] = None
    switches: int = 0


class Dualtasksensor(AbstractPlugin):
    """Guides dual-task training (sensor + secondary MATB task)."""

    def __init__(self, label: str = '', taskplacement: str = 'bottomleft', taskupdatetime: int = 250) -> None:
        super().__init__(label or _('Dual-Task Sensor Trainer'), taskplacement, taskupdatetime)
        self.state: Optional[DualTaskState] = None
        self._widget: Optional[Simpletext] = None

    def create_widgets(self) -> None:
        super().create_widgets()
        self._widget = self.add_widget(
            'status',
            Simpletext,
            container=self.task_container,
            text=_('No dual-task phase active.'),
            font_size=F['SMALL'],
            color=C['WHITE'],
            wrap_width=0.95,
            x=0.5,
            y=0.5,
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        return True

    # Scenario commands --------------------------------------------------
    def start(self, payload: str) -> None:
        """
        payload: phase,sensor_task,secondary_task
        """
        parts = self._split(payload, 3)
        if parts is None:
            return
        self.state = DualTaskState(
            phase=parts[0],
            sensor_task=parts[1],
            secondary_task=parts[2],
        )
        self.log_performance('dual_task_phase_start', f'{parts[0]}:{parts[1]}:{parts[2]}')
        self._update_widget()

    def switch(self, payload: str) -> None:
        """payload: task name (sensor or secondary)"""
        if self.state is None:
            return
        task = payload.strip() if payload else ''
        self.state.switches += 1
        self.log_performance('dual_task_switch', f'{self.state.phase}:{task}:{self.state.switches}')
        self._update_widget()

    def metric(self, payload: str) -> None:
        """
        payload: task,value
        task must match sensor_task or secondary_task.
        """
        if self.state is None:
            return
        parts = self._split(payload, 2)
        if parts is None:
            return
        try:
            value = float(parts[1])
        except ValueError:
            return
        task = parts[0]
        if task == self.state.sensor_task:
            self.state.sensor_metric = value
        elif task == self.state.secondary_task:
            self.state.secondary_metric = value
        else:
            return
        self.log_performance('dual_task_metric', f'{self.state.phase}:{task}:{value:.3f}')
        self._update_widget()

    def complete(self, payload: str) -> None:
        """payload: optional note string."""
        if self.state is None:
            return
        sensor_value = self.state.sensor_metric if self.state.sensor_metric is not None else 0.0
        secondary_value = (
            self.state.secondary_metric if self.state.secondary_metric is not None else 0.0
        )
        delta = sensor_value - secondary_value
        ratio = secondary_value / sensor_value if sensor_value != 0 else 0.0
        note = (payload or '').strip()
        self.log_performance(
            'dual_task_performance',
            (
                f'phase={self.state.phase};sensor={self.state.sensor_task}:{sensor_value:.3f};'
                f'secondary={self.state.secondary_task}:{secondary_value:.3f};'
                f'delta={delta:.3f};ratio={ratio:.3f};switches={self.state.switches};note={note}'
            ),
        )
        self.state = None
        self._update_widget()

    # Helpers ------------------------------------------------------------
    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if self.state is None:
            self._widget.set_text(_('No dual-task phase active.'))
            return
        sensor_val = '--' if self.state.sensor_metric is None else f'{self.state.sensor_metric:.2f}'
        secondary_val = (
            '--' if self.state.secondary_metric is None else f'{self.state.secondary_metric:.2f}'
        )
        self._widget.set_text(
            _('Phase: {0}\nSensor ({1}): {2}\nSecondary ({3}): {4}\nSwitches: {5}').format(
                self.state.phase,
                self.state.sensor_task,
                sensor_val,
                self.state.secondary_task,
                secondary_val,
                self.state.switches,
            )
        )

    @staticmethod
    def _split(payload: Optional[str], expected: int) -> Optional[list[str]]:
        if payload is None:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected:
            return None
        return parts


