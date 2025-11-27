"""VTOL flight phase and power manager."""

from __future__ import annotations

from typing import Dict, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin
from plugins.vtolmanager_model import VtolModel


class Vtolmanager(AbstractPlugin):
    """Supervises VTOL flight phases, confirmations, and power draw."""

    _PHASE_ALIASES = {
        'takeoff': 'vertical_takeoff',
        'vertical_takeoff': 'vertical_takeoff',
        'transition': 'transition',
        'cruise': 'cruise',
        'return': 'transition_return',
        'transition_return': 'transition_return',
        'landing': 'vertical_landing',
        'vertical_landing': 'vertical_landing',
        'hover': 'vertical_takeoff',
    }

    _TRANSITION_PHASES = {'transition', 'transition_return'}

    def __init__(self, label: str = '', taskplacement: str = 'bottomright', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('VTOL Manager'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'uavs': validation.is_string,
            'batteryseconds': validation.is_positive_integer,
            'warningratio': validation.is_in_unit_interval,
            'criticalratio': validation.is_in_unit_interval,
            'confirmationtimeout': validation.is_positive_float,
        }

        self.parameters.update({
            'uavs': 'VTOL1,VTOL2',
            'batteryseconds': 2700,
            'warningratio': 0.25,
            'criticalratio': 0.1,
            'confirmationtimeout': 8.0,
            'phasepower': 'vertical_takeoff=1.4;transition=1.2;cruise=0.8;transition_return=1.1;vertical_landing=1.5',
            'stabilitywarn': 0.6,
            'stabilitycritical': 0.85,
        })

        self._widget: Optional[Simpletext] = None
        self._model = self._build_model()
        self._pending_started: Dict[str, float] = {}
        self._pending_overdue: Dict[str, bool] = {}
        self._stability_values: Dict[str, float] = {}
        self._stability_status: Dict[str, str] = {}

        overdue = self.parameters['taskfeedback']['overdue']
        overdue.update({'active': True, 'color': C['ORANGE'], 'delayms': 0, 'blinkdurationms': 400})

    # Lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self._model = self._build_model()
        self._pending_started.clear()
        self._pending_overdue.clear()
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('UAV | Phase | Battery (min) | Power x | Status')
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
            text=self._format_summary(),
            font_size=F['SMALL'],
            y=0.65,
            color=C['WHITE'],
            wrap_width=0.98,
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        if self._widget is not None:
            self._widget.set_text(self._format_summary())
        self._update_overdue_state()
        return True

    # Scenario commands --------------------------------------------------
    def phase(self, payload: str) -> None:
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < 2:
            return
        uav = parts[0].upper()
        phase = self._canonical_phase(parts[1])
        if phase is None:
            return
        info = self._model.set_phase(uav, phase, self.scenario_time)
        self.log_performance(
            'vtol_phase_change',
            f'{uav}:{phase}:{info["power"]}:{info["duration"]:.2f}',
        )
        if info['pending_confirmation']:
            self._pending_started[uav] = self.scenario_time
            self._pending_overdue[uav] = False
            self.log_performance('vtol_transition_pending', uav)
        else:
            self._pending_started.pop(uav, None)
            self._pending_overdue.pop(uav, None)

    def confirm(self, payload: str) -> None:
        uav = payload.strip().upper()
        if not uav:
            return
        if self._model.confirm(uav):
            self.log_performance('vtol_transition_confirm', uav)
            self._pending_started.pop(uav, None)
            self._pending_overdue.pop(uav, None)

    def battery(self, payload: str) -> None:
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) != 2:
            return
        uav = parts[0].upper()
        try:
            seconds = max(60.0, float(parts[1]))
        except ValueError:
            return
        capacity = self._model.set_battery(uav, seconds, self.scenario_time)
        self.log_performance('vtol_battery_set', f'{uav}:{capacity}')

    def stability(self, payload: str) -> None:
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) != 2:
            return
        uav = parts[0].upper()
        try:
            value = self._clamp(float(parts[1]), 0.0, 1.0)
        except ValueError:
            return
        self._stability_values[uav] = value
        self._evaluate_stability(uav, value)

    def stabilitythresholds(self, payload: str) -> None:
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) != 2:
            return
        try:
            warn = self._clamp(float(parts[0]), 0.0, 1.0)
            critical = self._clamp(float(parts[1]), 0.0, 1.0)
        except ValueError:
            return
        if warn >= critical:
            return
        self.parameters['stabilitywarn'] = warn
        self.parameters['stabilitycritical'] = critical
        self.log_performance('stability_thresholds', f'{warn:.2f}:{critical:.2f}')
        for uav, value in self._stability_values.items():
            self._evaluate_stability(uav, value, force=True)

    # Internal -----------------------------------------------------------
    def update(self, scenario_time: float) -> None:
        super().update(scenario_time)
        for uav in self._uav_list():
            _, changed_level = self._model.update_energy(uav, scenario_time)
            if changed_level == 'warning':
                self.log_performance('vtol_power_warning', uav)
            elif changed_level == 'critical':
                self.log_performance('vtol_power_critical', uav)
            elif changed_level == 'empty':
                self.log_performance('vtol_power_empty', uav)
            self._maybe_mark_overdue(uav, scenario_time)

    def _maybe_mark_overdue(self, uav: str, now: float) -> None:
        start = self._pending_started.get(uav)
        if start is None:
            return
        timeout = float(self.parameters['confirmationtimeout'])
        if now - start >= timeout and not self._pending_overdue.get(uav):
            if self._model.mark_overdue(uav):
                self._pending_overdue[uav] = True
                self.log_performance('vtol_transition_overdue', uav)

    def _format_summary(self) -> str:
        lines = []
        for uav in self._uav_list():
            state = self._model.ensure(uav, self.scenario_time)
            battery_minutes = state.battery_remaining / 60.0
            status = state.warning_level.upper()
            if state.pending_confirmation:
                status += ' | PENDING'
            stability_note = ''
            if uav in self._stability_values:
                stability_note = f" | STB {self._stability_values[uav]:.2f}"
            lines.append(
                f"{uav} | {state.phase or 'idle'} | {battery_minutes:5.1f} | "
                f"{state.power_multiplier:3.1f} | {status}{stability_note}"
            )
        return '\n'.join(lines) if lines else _('Awaiting VTOL assignments…')

    def _update_overdue_state(self) -> None:
        overdue = self.parameters['taskfeedback']['overdue']
        overdue['active'] = True
        has_pending = any(self._model.pending(uav) for uav in self._uav_list())
        critical = any(
            self._model.ensure(uav, self.scenario_time).warning_level in ('critical', 'empty')
            for uav in self._uav_list()
        )
        overdue['_is_visible'] = has_pending or critical

    def _uav_list(self) -> list[str]:
        return [name.strip().upper() for name in self.parameters['uavs'].split(',') if name.strip()]

    def _canonical_phase(self, phase: str) -> Optional[str]:
        key = phase.strip().lower()
        return self._PHASE_ALIASES.get(key)

    def _build_model(self) -> VtolModel:
        phase_power: Dict[str, float] = {}
        entries = self.parameters.get('phasepower', '')
        for token in entries.split(';'):
            if '=' not in token:
                continue
            key, value = token.split('=', 1)
            try:
                phase_power[key.strip()] = float(value.strip())
            except ValueError:
                continue
        if not phase_power:
            phase_power = {
                'vertical_takeoff': 1.4,
                'transition': 1.2,
                'cruise': 0.8,
                'transition_return': 1.1,
                'vertical_landing': 1.5,
            }
        return VtolModel(
            battery_seconds=float(self.parameters['batteryseconds']),
            phase_power=phase_power,
            confirm_phases=self._TRANSITION_PHASES,
            warning_ratio=float(self.parameters['warningratio']),
            critical_ratio=float(self.parameters['criticalratio']),
        )

    def _evaluate_stability(self, uav: str, value: float, force: bool = False) -> None:
        warn = float(self.parameters['stabilitywarn'])
        critical = float(self.parameters['stabilitycritical'])
        new_state = 'critical' if value >= critical else 'warning' if value >= warn else 'normal'
        current = self._stability_status.get(uav)
        if new_state == current and not force:
            return
        self._stability_status[uav] = new_state
        if new_state == 'critical':
            self.log_performance('stability_critical', f'{uav}:{value:.2f}')
        elif new_state == 'warning':
            self.log_performance('stability_warning', f'{uav}:{value:.2f}')
        elif current in ('warning', 'critical'):
            self.log_performance('stability_recover', f'{uav}:{value:.2f}')

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

