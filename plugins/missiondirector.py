# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from typing import Dict, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


class Missiondirector(AbstractPlugin):
    """Supervises multiple UAV timelines and automation states."""

    def __init__(self, label: str = '', taskplacement: str = 'bottommid', taskupdatetime: int = 1000) -> None:
        super().__init__(label or _('Mission Director'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'maxuavs': validation.is_positive_integer,
            'uavlabels': validation.is_string,
        }

        self.parameters.update({
            'maxuavs': 4,
            'uavlabels': 'UAV1,UAV2,UAV3,UAV4',
        })

        self.uav_state: Dict[str, Dict[str, Optional[str]]] = {}
        self._widgets: Dict[str, Simpletext] = {}

    def start(self) -> None:
        self._initialise_uavs()
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('UAV | Mission | Mode | Remaining | Alert')
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

        for idx, name in enumerate(self.uav_state.keys()):
            widget = self.add_widget(
                f'uav_{idx}',
                Simpletext,
                container=self.task_container,
                text=self._format_status(name),
                font_size=F['SMALL'],
                y=0.75 - idx * 0.2,
                color=C['WHITE'],
                wrap_width=0.95,
            )
            self._widgets[name] = widget

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        for name in self.uav_state.keys():
            self._widgets[name].set_text(self._format_status(name))
        return True

    # Scenario commands -------------------------------------------------
    def assign(self, payload: str) -> None:
        parts = self._split_payload(payload, expected_min=2)
        if not parts:
            return
        label = self._canonical_label(parts[0])
        if label not in self.uav_state:
            return
        mission = parts[1]
        duration = self._parse_duration(parts[2]) if len(parts) > 2 else 0
        self.uav_state[label].update({
            'mission': mission,
            'mode': _('Manual'),
            'start': self.scenario_time,
            'duration': duration,
            'alert': '',
        })
        self.log_performance('mission_assign', f'{label}:{mission}:{duration}')

    def complete(self, payload: str) -> None:
        label = self._canonical_label(payload)
        if label not in self.uav_state:
            return
        self.uav_state[label].update({
            'mission': _('Idle'),
            'mode': _('Manual'),
            'start': None,
            'duration': 0,
            'alert': '',
        })
        self.log_performance('mission_complete', label)

    def automation(self, payload: str) -> None:
        parts = self._split_payload(payload, expected_min=2)
        if not parts:
            return
        label = self._canonical_label(parts[0])
        if label not in self.uav_state:
            return
        mode = _('Auto') if parts[1].lower() in ('1', 'true', 'auto') else _('Manual')
        self.uav_state[label]['mode'] = mode
        self.log_performance('mission_mode', f'{label}:{mode}')

    def conflict(self, payload: str) -> None:
        parts = self._split_payload(payload, expected_min=2)
        if not parts:
            return
        label = self._canonical_label(parts[0])
        if label not in self.uav_state:
            return
        alert = _('Conflict: {}').format(parts[1])
        self.uav_state[label]['alert'] = alert
        self.log_performance('mission_alert', f'{label}:{alert}')
        self._set_overdue(True)

    def clearconflict(self, payload: str) -> None:
        label = self._canonical_label(payload)
        if label not in self.uav_state:
            return
        self.uav_state[label]['alert'] = ''
        any_alerts = any(uav.get('alert') for uav in self.uav_state.values())
        self._set_overdue(any_alerts)

    # Helpers -----------------------------------------------------------
    def _initialise_uavs(self) -> None:
        labels = [name.strip() for name in self.parameters['uavlabels'].split(',') if name.strip()]
        max_uavs = max(1, min(int(self.parameters['maxuavs']), 6))
        labels = labels[:max_uavs] if labels else [f'UAV{i+1}' for i in range(max_uavs)]
        self.uav_state = {
            label: {
                'mission': _('Idle'),
                'mode': _('Manual'),
                'start': None,
                'duration': 0,
                'alert': '',
            }
            for label in labels
        }

    def _canonical_label(self, label: str) -> str:
        label_normalised = label.strip().lower()
        for key in self.uav_state.keys():
            if key.lower() == label_normalised:
                return key
        return label

    def _split_payload(self, payload: str, expected_min: int) -> Optional[list]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < expected_min:
            return None
        return parts

    def _parse_duration(self, value: str) -> int:
        try:
            duration = int(float(value))
        except (TypeError, ValueError):
            return 0
        return max(0, duration)

    def _format_status(self, label: str) -> str:
        state = self.uav_state[label]
        remaining = self._remaining_time(state)
        alert = state.get('alert') or ''
        return f"{label} | {state['mission']} | {state['mode']} | {remaining} | {alert}"

    def _remaining_time(self, state: Dict[str, Optional[str]]) -> str:
        start = state.get('start')
        duration = state.get('duration') or 0
        if start is None or duration <= 0:
            return _('N/A')
        elapsed = max(0, self.scenario_time - start)
        remaining = max(0, duration - elapsed)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        return f'{minutes:02d}:{seconds:02d}'

    def _set_overdue(self, active: bool) -> None:
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = active

