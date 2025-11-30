"""VTOL flight phase and power manager."""

from __future__ import annotations

from typing import Dict, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin

try:
    _
except NameError:  # pragma: no cover - fallback when gettext not injected
    from builtins import _  # type: ignore[misc]
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
        # 2D VTOL status strip: one row per aircraft with phase, time-in-phase,
        # battery reserve, power multiplier, and alert tags. This remains a
        # text-only summary; all timing, power, and logging logic lives in
        # VtolModel and is unchanged.
        header = _('UAV | Phase        | t_phase | Batt (%)        | Power | Alerts')
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
            (
                f'uav={uav},phase={phase},power={info["power"]:.2f},'
                f'duration_s={info["duration"]:.2f}'
            ),
        )
        if info['pending_confirmation']:
            self._pending_started[uav] = self.scenario_time
            self._pending_overdue[uav] = False
            timeout = float(self.parameters['confirmationtimeout'])
            self.log_performance(
                'vtol_transition_pending',
                f'uav={uav},phase={phase},timeout_s={timeout:.1f}',
            )
        else:
            self._pending_started.pop(uav, None)
            self._pending_overdue.pop(uav, None)

    def confirm(self, payload: str) -> None:
        uav = payload.strip().upper()
        if not uav:
            return
        if self._model.confirm(uav):
            phase = self._model.ensure(uav, self.scenario_time).phase or 'idle'
            self.log_performance('vtol_transition_confirm', f'uav={uav},phase={phase}')
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
        self.log_performance('vtol_battery_set', f'uav={uav},capacity_s={capacity:.1f}')

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
        self.log_performance('stability_thresholds', f'warning={warn:.2f},critical={critical:.2f}')
        for uav, value in self._stability_values.items():
            self._evaluate_stability(uav, value, force=True)

    # Internal -----------------------------------------------------------
    def update(self, scenario_time: float) -> None:
        super().update(scenario_time)
        for uav in self._uav_list():
            remaining, changed_level = self._model.update_energy(uav, scenario_time)
            if changed_level is not None:
                self._log_energy_level(changed_level, uav, remaining)
            self._maybe_mark_overdue(uav, scenario_time)

    def _maybe_mark_overdue(self, uav: str, now: float) -> None:
        start = self._pending_started.get(uav)
        if start is None:
            return
        timeout = float(self.parameters['confirmationtimeout'])
        elapsed = now - start
        if elapsed >= timeout and not self._pending_overdue.get(uav):
            if self._model.mark_overdue(uav):
                self._pending_overdue[uav] = True
                self.log_performance(
                    'vtol_transition_overdue',
                    f'uav={uav},elapsed_s={elapsed:.2f},timeout_s={timeout:.2f}',
                )

    def _log_energy_level(self, level: str, uav: str, remaining: float) -> None:
        payload = f'uav={uav},remaining_s={remaining:.1f}'
        if level == 'warning':
            self.log_performance('vtol_power_warning', payload)
        elif level == 'critical':
            self.log_performance('vtol_power_critical', payload)
        elif level == 'empty':
            self.log_performance('vtol_power_empty', payload)

    def _format_summary(self) -> str:
        """Render a fixed-width VTOL status line per UAV.

        Each row shows phase, time in phase, remaining battery as a percentage
        plus a text-only progress bar, power multiplier, and alert tags. This
        function does not change any VTOL timing, power, or logging logic; it
        only formats the state tracked by :class:`VtolModel`.
        """
        lines = []
        for uav in self._uav_list():
            state = self._model.ensure(uav, self.scenario_time)

            # Phase and time-in-phase
            phase_label = (state.phase or 'idle').upper()
            phase_text = phase_label[:12].ljust(12)
            elapsed = max(0.0, self.scenario_time - state.phase_started_at)
            minutes, seconds = divmod(int(elapsed), 60)
            t_phase = f"{minutes:02d}:{seconds:02d}"

            # Battery reserve as percentage plus ASCII bar
            if state.battery_capacity > 0.0:
                ratio = max(0.0, min(1.0, state.battery_remaining / state.battery_capacity))
            else:
                ratio = 0.0
            batt_pct = int(round(ratio * 100.0))
            batt_bar = self.format_progress_bar(ratio, length=10)

            # Power multiplier and alert tags
            power = f"{state.power_multiplier:3.1f}x"
            alerts = state.warning_level.upper()
            if state.pending_confirmation:
                alerts += ' PENDING'
            if self._pending_overdue.get(uav):
                alerts += ' OVERDUE'
            if uav in self._stability_values:
                alerts += f" STB {self._stability_values[uav]:.2f}"

            line = (
                f"{uav:>4} | {phase_text} | {t_phase} | "
                f"{batt_pct:3d}% {batt_bar} | {power:>5} | {alerts}"
            )
            lines.append(line)

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
            self.log_performance('stability_critical', f'uav={uav},value={value:.2f}')
        elif new_state == 'warning':
            self.log_performance('stability_warning', f'uav={uav},value={value:.2f}')
        elif current in ('warning', 'critical'):
            self.log_performance('stability_recover', f'uav={uav},value={value:.2f}')

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
