# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from typing import Any, Dict, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F, STATUS_COLORS
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


class Missiondirector(AbstractPlugin):
    """Supervises multiple UAV timelines and automation states.

    Per update_plan.md Section 3.1:
    - Fixed column headers: UAV | Mission | Mode | Task | Endurance | Alert
    - Monospaced font for column alignment
    - Progress bars for mission and endurance time remaining
    - Mode highlighted (AUTO in distinct color)
    - Alert fields in WARNING/CRITICAL colors
    """

    def __init__(self, label: str = '', taskplacement: str = 'bottommid', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('Mission Director'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'maxuavs': validation.is_positive_integer,
            'uavlabels': validation.is_string,
            'defaultendurancewarningsec': validation.is_positive_integer,
        }

        self.parameters.update({
            'maxuavs': 4,
            'uavlabels': 'UAV1,UAV2,UAV3,UAV4',
            'defaultendurancewarningsec': 300,
        })

        self.uav_state: Dict[str, Dict[str, Any]] = {}
        self._widgets: Dict[str, Simpletext] = {}

    def start(self) -> None:
        self._initialise_uavs()
        super().start()

    def create_widgets(self) -> None:
        """Create a compact, aeronautically inspired mission status table.

        The layout is kept strictly 2D and text-based so that timing and
        workload metrics remain comparable to legacy MATB/MATB-II studies,
        while column alignment and abbreviations mirror standard UAS mission
        summary strips (UAV, mission, mode, task and endurance times, alerts).
        """
        super().create_widgets()
        # Header with progress bar columns (per update_plan.md 3.1)
        header = _('UAV | MISSION  | MODE | TASK   [PROG] | ENDUR  [PROG] | ALERTS')
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

        # One line per UAV label in a fixed order to aid scan patterns
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
        self._update_endurance_alerts()
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
        self._refresh_overdue_indicator()

    def clearconflict(self, payload: str) -> None:
        label = self._canonical_label(payload)
        if label not in self.uav_state:
            return
        self.uav_state[label]['alert'] = ''
        self._refresh_overdue_indicator()

    def endurance(self, payload: str) -> None:
        parts = self._split_payload(payload, expected_min=2)
        if not parts:
            return
        label = self._canonical_label(parts[0])
        if label not in self.uav_state:
            return
        duration_sec = self._parse_duration(parts[1])
        threshold_sec = self._parse_duration(parts[2]) if len(parts) > 2 else int(
            self.parameters.get('defaultendurancewarningsec', 300)
        )
        state = self.uav_state[label]
        state['endurance_start'] = self.scenario_time
        state['endurance_duration'] = max(0, duration_sec)
        state['endurance_threshold'] = max(0, threshold_sec)
        state['endurance_alerted'] = False
        self.log_performance('mission_endurance_set', f'{label}:{duration_sec}:{threshold_sec}')
        self._refresh_overdue_indicator()

    def handover(self, payload: str) -> None:
        parts = self._split_payload(payload, expected_min=2)
        if not parts:
            return
        label = self._canonical_label(parts[0])
        if label not in self.uav_state:
            return
        target = parts[1]
        status = parts[2].lower() if len(parts) > 2 else 'start'
        state = self.uav_state[label]
        if status in ('start', 'init', 'initiate', 'begin'):
            state['handover_active'] = True
            state['handover_target'] = target
            self.log_performance('mission_handover_initiate', f'{label}:{target}')
        elif status in ('complete', 'end', 'stop'):
            state['handover_active'] = False
            self.log_performance('mission_handover_complete', f'{label}:{target}')

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
                'endurance_start': None,
                'endurance_duration': 0,
                'endurance_threshold': int(self.parameters.get('defaultendurancewarningsec', 300)),
                'endurance_alerted': False,
                'handover_active': False,
                'handover_target': '',
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
        """Format a single UAV status line with progress bars.

        Per update_plan.md Section 3.1:
        - Fixed-width columns for scan efficiency
        - Progress bars for task and endurance time remaining
        - Mode highlighted (AUTO vs MAN)
        - Alert tags appended with visual indicators
        """
        state = self.uav_state[label]

        # Callsign / vehicle identifier (left-aligned, 4 chars)
        callsign = f"{label:<4}"

        # Mission name in uppercase, trimmed/padded to 8 chars
        mission_raw = str(state.get('mission', ''))
        mission = mission_raw.upper()[:8].ljust(8)

        # Mode: AUTO vs MAN (manual) in 4-character field
        mode_raw = str(state.get('mode', ''))
        mode_upper = mode_raw.upper()
        mode_abbrev = 'AUTO' if 'AUTO' in mode_upper else 'MAN '

        # Task timer with progress bar (time remaining in current mission segment)
        task_time, task_frac = self._remaining_time_with_fraction(state)
        task_bar = self.format_progress_bar(task_frac, length=6) if task_frac is not None else '------'

        # Endurance timer with progress bar
        endurance_time, endurance_frac = self._remaining_endurance_with_fraction(state)
        endurance_bar = self.format_progress_bar(endurance_frac, length=6) if endurance_frac is not None else '------'

        # Alert field aggregates conflict / handover / endurance tags
        alert = self._format_alert(state)

        # Format: UAV | MISSION | MODE | TASK mm:ss [bar] | ENDUR mm:ss [bar] | ALERT
        return f"{callsign} | {mission} | {mode_abbrev} | {task_time:>5} {task_bar} | {endurance_time:>5} {endurance_bar} | {alert}"

    def _remaining_time(self, state: Dict[str, Any]) -> str:
        start = state.get('start')
        duration = state.get('duration') or 0
        if start is None or duration <= 0:
            return _('N/A')
        elapsed = max(0, self.scenario_time - start)
        remaining = max(0, duration - elapsed)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        return f'{minutes:02d}:{seconds:02d}'

    def _remaining_time_with_fraction(self, state: Dict[str, Any]) -> tuple[str, Optional[float]]:
        """Return time remaining string and fraction (0.0-1.0) for progress bar."""
        start = state.get('start')
        duration = state.get('duration') or 0
        if start is None or duration <= 0:
            return _('N/A'), None
        elapsed = max(0.0, self.scenario_time - start)
        remaining = max(0.0, duration - elapsed)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        fraction = remaining / duration if duration > 0 else 0.0
        return f'{minutes:02d}:{seconds:02d}', fraction

    def _format_endurance(self, state: Dict[str, Any]) -> str:
        remaining = self._remaining_endurance(state)
        if remaining is None:
            return _('N/A')
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        return f'{minutes:02d}:{seconds:02d}'

    def _remaining_endurance(self, state: Dict[str, Any]) -> Optional[float]:
        start = state.get('endurance_start')
        duration = float(state.get('endurance_duration') or 0)
        if start is None or duration <= 0:
            return None
        elapsed = max(0.0, self.scenario_time - float(start))
        return max(0.0, duration - elapsed)

    def _remaining_endurance_with_fraction(self, state: Dict[str, Any]) -> tuple[str, Optional[float]]:
        """Return endurance remaining string and fraction (0.0-1.0) for progress bar."""
        start = state.get('endurance_start')
        duration = float(state.get('endurance_duration') or 0)
        if start is None or duration <= 0:
            return _('N/A'), None
        elapsed = max(0.0, self.scenario_time - float(start))
        remaining = max(0.0, duration - elapsed)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        fraction = remaining / duration if duration > 0 else 0.0
        return f'{minutes:02d}:{seconds:02d}', fraction

    def _format_alert(self, state: Dict[str, Any]) -> str:
        segments = []
        alert_text = state.get('alert')
        if alert_text:
            segments.append(str(alert_text))
        if state.get('handover_active'):
            target = state.get('handover_target') or _('Unknown')
            segments.append(_('Handover→{}').format(target))
        if state.get('endurance_alerted'):
            segments.append(_('Endurance Low'))
        return ' '.join(segments).strip()

    def _update_endurance_alerts(self) -> None:
        updated = False
        for label, state in self.uav_state.items():
            remaining = self._remaining_endurance(state)
            threshold = float(state.get('endurance_threshold') or 0)
            if remaining is None or threshold <= 0:
                if state.get('endurance_alerted'):
                    state['endurance_alerted'] = False
                    updated = True
                continue
            if remaining <= threshold:
                if not state.get('endurance_alerted'):
                    state['endurance_alerted'] = True
                    self.log_performance('mission_endurance_low', f'{label}:{remaining:.1f}')
                    updated = True
            elif state.get('endurance_alerted'):
                state['endurance_alerted'] = False
                updated = True
        if updated:
            self._refresh_overdue_indicator()

    def _refresh_overdue_indicator(self) -> None:
        has_conflict = any(bool(state.get('alert')) for state in self.uav_state.values())
        has_endurance_issue = any(state.get('endurance_alerted') for state in self.uav_state.values())
        self._set_overdue(has_conflict or has_endurance_issue)

    def _set_overdue(self, active: bool) -> None:
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        overdue['_is_visible'] = active

